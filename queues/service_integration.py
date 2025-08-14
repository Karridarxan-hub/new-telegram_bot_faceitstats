"""Integration layer for existing services with background tasks.

This module provides adapters and integration points to seamlessly integrate
background tasks with the existing service layer, allowing for gradual migration
from synchronous to asynchronous task processing.
"""

import logging
from typing import Dict, List, Optional, Any, Union, Callable
from datetime import datetime
import asyncio
from functools import wraps

from .task_manager import TaskManager, TaskPriority, get_task_manager
from services.base import BaseService, ServiceResult, ServiceError

logger = logging.getLogger(__name__)


class TaskIntegrationMixin:
    """
    Mixin class that adds background task capabilities to existing services.
    
    Services can inherit from this mixin to gain access to background task
    functionality while maintaining their existing synchronous interfaces.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._task_manager = get_task_manager()
        self._pending_tasks: Dict[str, Dict[str, Any]] = {}
    
    def _enqueue_task(
        self,
        task_function: Callable,
        *args,
        priority: TaskPriority = TaskPriority.DEFAULT,
        timeout: int = 600,
        retry: int = 2,
        callback: Optional[Callable] = None,
        **kwargs
    ) -> str:
        """Enqueue a background task and return task ID."""
        try:
            # Get appropriate queue based on priority
            queue = self._task_manager.queues[priority]
            
            # Enqueue the task
            job = queue.enqueue(
                task_function,
                *args,
                **kwargs,
                job_timeout=timeout,
                retry=retry
            )
            
            task_id = job.id
            
            # Track the task
            self._pending_tasks[task_id] = {
                "function": task_function.__name__,
                "enqueued_at": datetime.now(),
                "priority": priority.value,
                "callback": callback,
                "args": args,
                "kwargs": kwargs
            }
            
            # Set callback if provided
            if callback:
                job.meta['callback'] = callback
                job.save_meta()
            
            logger.info(f"Enqueued task {task_function.__name__} with ID {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue task {task_function.__name__}: {e}")
            raise ServiceError(f"Failed to enqueue background task: {e}")
    
    def _wait_for_task_result(
        self,
        task_id: str,
        timeout_seconds: int = 300,
        poll_interval: float = 1.0
    ) -> Any:
        """
        Wait for a task to complete and return its result.
        
        This allows services to optionally wait for background tasks when
        immediate results are needed.
        """
        import time
        from rq import Job
        from rq.exceptions import NoSuchJobError
        
        start_time = time.time()
        
        try:
            job = Job.fetch(task_id, connection=self._task_manager.redis)
            
            while time.time() - start_time < timeout_seconds:
                if job.is_finished:
                    # Clean up tracking
                    if task_id in self._pending_tasks:
                        del self._pending_tasks[task_id]
                    
                    return job.result
                
                elif job.is_failed:
                    error_msg = f"Task {task_id} failed: {job.exc_info}"
                    logger.error(error_msg)
                    raise ServiceError(error_msg)
                
                elif job.is_cancelled:
                    error_msg = f"Task {task_id} was cancelled"
                    logger.warning(error_msg)
                    raise ServiceError(error_msg)
                
                time.sleep(poll_interval)
            
            # Timeout reached
            raise ServiceError(f"Task {task_id} timed out after {timeout_seconds} seconds")
            
        except NoSuchJobError:
            raise ServiceError(f"Task {task_id} not found")
    
    def _get_task_progress(self, task_id: str) -> Dict[str, Any]:
        """Get progress information for a task."""
        return self._task_manager.get_task_status(task_id)
    
    def _cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task."""
        success = self._task_manager.cancel_task(task_id)
        
        if success and task_id in self._pending_tasks:
            del self._pending_tasks[task_id]
        
        return success
    
    def get_pending_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get information about pending tasks for this service."""
        return self._pending_tasks.copy()


class AsyncMatchService(TaskIntegrationMixin):
    """
    Async-enabled wrapper for the existing MatchService.
    
    Provides background task processing for CPU-intensive match analysis
    while maintaining the same interface as the original service.
    """
    
    def __init__(self, original_service):
        super().__init__()
        self._original_service = original_service
    
    async def analyze_match_async(
        self,
        telegram_user_id: int,
        match_url_or_id: str,
        force_refresh: bool = False,
        wait_for_result: bool = False,
        timeout_seconds: int = 300
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Analyze match using background tasks.
        
        Args:
            telegram_user_id: User requesting analysis
            match_url_or_id: Match URL or ID
            force_refresh: Force cache refresh
            wait_for_result: If True, wait for task completion
            timeout_seconds: Timeout for waiting
            
        Returns:
            ServiceResult with task ID or analysis results
        """
        try:
            # Enqueue the match analysis task
            task_id = self._task_manager.enqueue_match_analysis(
                match_url_or_id,
                telegram_user_id,
                force_refresh,
                priority=TaskPriority.HIGH
            )
            
            if wait_for_result:
                # Wait for the task to complete
                try:
                    result = self._wait_for_task_result(task_id, timeout_seconds)
                    
                    if result.get("success"):
                        return ServiceResult.success_result(
                            result,
                            metadata={"task_id": task_id, "background_processed": True}
                        )
                    else:
                        return ServiceResult.error_result(
                            ServiceError(result.get("error", "Analysis failed"))
                        )
                        
                except Exception as e:
                    return ServiceResult.error_result(
                        ServiceError(f"Background analysis failed: {e}")
                    )
            else:
                # Return task ID for tracking
                return ServiceResult.success_result({
                    "task_id": task_id,
                    "status": "enqueued",
                    "message": "Match analysis started in background",
                    "progress_url": f"/api/tasks/{task_id}/status"
                })
        
        except Exception as e:
            logger.error(f"Error in async match analysis: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to start background analysis: {e}")
            )
    
    def analyze_match_bulk_async(
        self,
        telegram_user_id: int,
        match_urls: List[str],
        options: Optional[Dict[str, Any]] = None
    ) -> ServiceResult[Dict[str, Any]]:
        """Analyze multiple matches in background."""
        try:
            task_id = self._task_manager.enqueue_bulk_match_analysis(
                match_urls,
                telegram_user_id,
                options
            )
            
            return ServiceResult.success_result({
                "task_id": task_id,
                "status": "enqueued",
                "match_count": len(match_urls),
                "message": f"Bulk analysis of {len(match_urls)} matches started",
                "estimated_completion": f"{len(match_urls) * 30} seconds"
            })
            
        except Exception as e:
            return ServiceResult.error_result(
                ServiceError(f"Failed to start bulk analysis: {e}")
            )
    
    # Delegate other methods to original service
    def __getattr__(self, name):
        """Delegate unknown methods to the original service."""
        return getattr(self._original_service, name)


def background_task(
    priority: TaskPriority = TaskPriority.DEFAULT,
    timeout: int = 600,
    retry: int = 2,
    async_mode: bool = False
):
    """
    Decorator to automatically convert service methods to background tasks.
    
    Args:
        priority: Task priority level
        timeout: Task timeout in seconds
        retry: Number of retry attempts
        async_mode: If True, returns task ID immediately; if False, waits for result
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Check if the service has task integration
            if not hasattr(self, '_enqueue_task'):
                logger.warning(f"Service {self.__class__.__name__} does not have task integration")
                return func(self, *args, **kwargs)
            
            # Enqueue the task
            task_id = self._enqueue_task(
                func,
                self,
                *args,
                priority=priority,
                timeout=timeout,
                retry=retry,
                **kwargs
            )
            
            if async_mode:
                # Return task tracking information
                return ServiceResult.success_result({
                    "task_id": task_id,
                    "status": "enqueued",
                    "async": True
                })
            else:
                # Wait for result (blocking)
                try:
                    result = self._wait_for_task_result(task_id, timeout)
                    return result
                except Exception as e:
                    return ServiceResult.error_result(ServiceError(str(e)))
        
        return wrapper
    return decorator


class BackgroundServiceAdapter:
    """
    Adapter to wrap existing services with background task capabilities.
    
    This class can wrap any existing service and provide background task
    processing for specified methods.
    """
    
    def __init__(
        self,
        service_instance,
        background_methods: List[str] = None,
        task_manager: Optional[TaskManager] = None
    ):
        """
        Initialize service adapter.
        
        Args:
            service_instance: The original service instance
            background_methods: List of method names to run in background
            task_manager: Optional task manager instance
        """
        self._service = service_instance
        self._background_methods = set(background_methods or [])
        self._task_manager = task_manager or get_task_manager()
        self._pending_tasks: Dict[str, Dict[str, Any]] = {}
    
    def __getattr__(self, name: str) -> Any:
        """
        Intercept method calls and optionally run them in background.
        """
        attr = getattr(self._service, name)
        
        # If it's not a method or not in background methods, return as-is
        if not callable(attr) or name not in self._background_methods:
            return attr
        
        # Create a background-enabled wrapper
        def background_wrapper(*args, **kwargs):
            # Check for special background control parameters
            run_in_background = kwargs.pop('_background', True)
            wait_for_result = kwargs.pop('_wait', False)
            task_priority = kwargs.pop('_priority', TaskPriority.DEFAULT)
            
            if not run_in_background:
                # Run synchronously
                return attr(*args, **kwargs)
            
            # Enqueue in background
            try:
                queue = self._task_manager.queues[task_priority]
                job = queue.enqueue(attr, *args, **kwargs)
                
                task_id = job.id
                self._pending_tasks[task_id] = {
                    "method": name,
                    "enqueued_at": datetime.now(),
                    "args": args,
                    "kwargs": kwargs
                }
                
                if wait_for_result:
                    # Wait for completion
                    import time
                    from rq import Job
                    
                    start_time = time.time()
                    timeout = 300  # 5 minutes default
                    
                    while time.time() - start_time < timeout:
                        job.refresh()
                        
                        if job.is_finished:
                            return job.result
                        elif job.is_failed:
                            raise ServiceError(f"Background task failed: {job.exc_info}")
                        
                        time.sleep(1)
                    
                    raise ServiceError("Background task timed out")
                else:
                    # Return task tracking info
                    return ServiceResult.success_result({
                        "task_id": task_id,
                        "method": name,
                        "status": "enqueued"
                    })
                    
            except Exception as e:
                logger.error(f"Failed to enqueue background task for {name}: {e}")
                raise ServiceError(f"Failed to start background task: {e}")
        
        return background_wrapper
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get status of a background task."""
        return self._task_manager.get_task_status(task_id)
    
    def get_pending_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get all pending tasks for this service."""
        return self._pending_tasks.copy()


def integrate_service_with_tasks(
    service_instance,
    background_methods: List[str] = None
) -> BackgroundServiceAdapter:
    """
    Convenience function to integrate a service with background tasks.
    
    Args:
        service_instance: The service to integrate
        background_methods: Methods to run in background
        
    Returns:
        Wrapped service with background task capabilities
    """
    return BackgroundServiceAdapter(service_instance, background_methods)


# Integration helpers for specific services

def create_async_match_service(match_service):
    """Create async-enabled match service wrapper."""
    return AsyncMatchService(match_service)


def setup_background_monitoring():
    """Set up recurring background monitoring tasks."""
    task_manager = get_task_manager()
    
    # Schedule player monitoring every 30 minutes
    task_manager.schedule_recurring_task(
        "player_monitoring",
        lambda: task_manager.enqueue_player_monitoring(),
        30,  # 30 minutes
        priority=TaskPriority.DEFAULT
    )
    
    # Schedule cache cleanup daily
    task_manager.schedule_recurring_task(
        "daily_cache_cleanup",
        lambda: task_manager.enqueue_cache_cleanup("expired", 1000, False),
        1440,  # 24 hours
        priority=TaskPriority.LOW
    )
    
    # Schedule cache warming every 6 hours
    task_manager.schedule_recurring_task(
        "cache_warming",
        lambda: task_manager.enqueue_cache_warming("popular_data"),
        360,  # 6 hours
        priority=TaskPriority.LOW
    )
    
    # Schedule batch player updates every 4 hours
    task_manager.schedule_recurring_task(
        "batch_player_updates",
        lambda: task_manager.enqueue_batch_player_update(50, 6),
        240,  # 4 hours
        priority=TaskPriority.LOW
    )
    
    # Schedule ELO tracking every hour
    task_manager.schedule_recurring_task(
        "elo_tracking",
        lambda: task_manager.enqueue_elo_tracking(),
        60,  # 1 hour
        priority=TaskPriority.DEFAULT
    )
    
    # Schedule global statistics daily
    task_manager.schedule_recurring_task(
        "daily_global_stats",
        lambda: task_manager.enqueue_global_statistics(True, True),
        1440,  # 24 hours
        priority=TaskPriority.LOW
    )
    
    logger.info("Background monitoring tasks scheduled")


async def start_task_scheduler():
    """Start the task scheduler for recurring tasks."""
    task_manager = get_task_manager()
    
    while True:
        try:
            # Process scheduled tasks
            processed = task_manager.process_scheduled_tasks()
            
            if processed > 0:
                logger.info(f"Processed {processed} scheduled tasks")
            
            # Clean up old finished tasks
            if datetime.now().hour == 2:  # Run cleanup at 2 AM
                cleaned = task_manager.cleanup_finished_tasks(48)  # Keep 48 hours
                logger.info(f"Cleaned up {cleaned} old finished tasks")
            
        except Exception as e:
            logger.error(f"Error in task scheduler: {e}")
        
        # Wait 5 minutes before next check
        await asyncio.sleep(300)


# Task result handlers

def handle_match_analysis_result(task_result: Dict[str, Any], user_id: int):
    """Handle completed match analysis task result."""
    if task_result.get("success"):
        # Send notification to user with results
        formatted_message = task_result.get("formatted_message", "Analysis completed!")
        
        # Enqueue notification
        task_manager = get_task_manager()
        task_manager.enqueue_match_notification(
            user_id,
            task_result.get("match_id", ""),
            {"analysis_result": task_result}
        )
    else:
        # Handle analysis failure
        error_msg = task_result.get("error", "Analysis failed")
        logger.error(f"Match analysis failed for user {user_id}: {error_msg}")


def handle_analytics_report_result(task_result: Dict[str, Any], user_id: int):
    """Handle completed analytics report task result."""
    if task_result.get("success"):
        # Send analytics report notification
        task_manager = get_task_manager()
        task_manager.enqueue_analytics_report_notification(
            user_id,
            task_result["analytics"],
            "comprehensive",
            False  # No attachments for now
        )
    else:
        logger.error(f"Analytics generation failed for user {user_id}: {task_result.get('error')}")


# Export key integration components
__all__ = [
    "TaskIntegrationMixin",
    "AsyncMatchService", 
    "background_task",
    "BackgroundServiceAdapter",
    "integrate_service_with_tasks",
    "create_async_match_service",
    "setup_background_monitoring",
    "start_task_scheduler"
]