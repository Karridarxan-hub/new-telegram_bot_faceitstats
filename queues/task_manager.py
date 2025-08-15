"""Task queue manager for background job orchestration.

Provides a unified interface for managing background tasks, job scheduling,
monitoring, and integration with the existing service layer.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Callable
from enum import Enum
import uuid

from redis import Redis
from rq import Queue, Worker
from rq.job import Job
from rq.registry import StartedJobRegistry, FinishedJobRegistry, FailedJobRegistry
from rq.exceptions import NoSuchJobError

from config.settings import settings
from .tasks import (
    # Match Analysis Tasks
    analyze_match_task,
    bulk_analyze_matches_task,
    generate_match_report_task,
    calculate_team_stats_task,
    analyze_player_performance_task,
    
    # Player Monitoring Tasks
    monitor_player_matches_task,
    update_player_statistics_task,
    batch_update_players_task,
    check_elo_changes_task,
    track_player_activity_task,
    
    # Cache Management Tasks
    warm_cache_task,
    cleanup_expired_cache_task,
    optimize_cache_usage_task,
    refresh_popular_data_task,
    cache_health_check_task,
    
    # Notification Tasks
    send_match_notification_task,
    send_bulk_notifications_task,
    schedule_reminder_task,
    send_analytics_report_task,
    broadcast_announcement_task,
    
    # Analytics Tasks
    generate_user_analytics_task,
    calculate_global_statistics_task,
    generate_performance_report_task,
    track_usage_metrics_task,
    create_monthly_report_task
)

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Task priority levels."""
    CRITICAL = "faceit_bot_critical"     # Immediate processing
    HIGH = "faceit_bot_high"            # User-facing requests
    DEFAULT = "faceit_bot_default"       # Regular background tasks
    LOW = "faceit_bot_low"              # Maintenance and analytics


class TaskStatus(Enum):
    """Task execution status."""
    QUEUED = "queued"
    STARTED = "started"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskManager:
    """
    Central task queue manager for FACEIT bot operations.
    
    Provides unified interface for:
    - Enqueueing background tasks
    - Monitoring task progress
    - Managing job queues
    - Handling task failures and retries
    - Scheduling recurring tasks
    """
    
    def __init__(self, redis_connection: Optional[Redis] = None):
        """Initialize task manager."""
        self.redis = redis_connection or Redis.from_url(
            settings.redis_url,
            password=getattr(settings, 'redis_password', None)
        )
        
        # Initialize queues with different priorities
        self.queues = {
            TaskPriority.CRITICAL: Queue('faceit_bot_critical', connection=self.redis),
            TaskPriority.HIGH: Queue('faceit_bot_high', connection=self.redis),
            TaskPriority.DEFAULT: Queue('faceit_bot_default', connection=self.redis),
            TaskPriority.LOW: Queue('faceit_bot_low', connection=self.redis)
        }
        
        # Task registry for tracking
        self._active_tasks: Dict[str, Job] = {}
        self._scheduled_tasks: Dict[str, Dict[str, Any]] = {}
        
        logger.info("Task manager initialized with Redis queues")
    
    # Match Analysis Task Management
    
    def enqueue_match_analysis(
        self,
        match_url_or_id: str,
        user_id: int,
        force_refresh: bool = False,
        priority: TaskPriority = TaskPriority.HIGH,
        callback: Optional[Callable] = None
    ) -> str:
        """
        Enqueue match analysis task.
        
        Args:
            match_url_or_id: FACEIT match URL or ID
            user_id: Telegram user ID requesting analysis
            force_refresh: Whether to force refresh cached data
            priority: Task priority level
            callback: Optional callback function for completion
            
        Returns:
            Task ID for tracking
        """
        try:
            job = self.queues[priority].enqueue(
                analyze_match_task,
                match_url_or_id,
                user_id,
                force_refresh,
                job_timeout=600,  # 10 minutes
                retry=3
            )
            
            task_id = job.id
            self._active_tasks[task_id] = job
            
            # Set callback if provided
            if callback:
                job.meta['callback'] = callback
                job.save_meta()
            
            logger.info(f"Enqueued match analysis task {task_id} for user {user_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue match analysis task: {e}")
            raise
    
    def enqueue_bulk_match_analysis(
        self,
        match_urls: List[str],
        user_id: int,
        options: Optional[Dict[str, Any]] = None
    ) -> str:
        """Enqueue bulk match analysis task."""
        try:
            job = self.queues[TaskPriority.LOW].enqueue(
                bulk_analyze_matches_task,
                match_urls,
                user_id,
                options,
                job_timeout=3600,  # 1 hour
                retry=2
            )
            
            task_id = job.id
            self._active_tasks[task_id] = job
            
            logger.info(f"Enqueued bulk analysis task {task_id} for {len(match_urls)} matches")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue bulk analysis task: {e}")
            raise
    
    def enqueue_player_performance_analysis(
        self,
        player_id: str,
        analysis_period_days: int = 30,
        include_detailed_stats: bool = True,
        priority: TaskPriority = TaskPriority.DEFAULT
    ) -> str:
        """Enqueue player performance analysis task."""
        try:
            job = self.queues[priority].enqueue(
                analyze_player_performance_task,
                player_id,
                analysis_period_days,
                include_detailed_stats,
                job_timeout=600,
                retry=2
            )
            
            task_id = job.id
            self._active_tasks[task_id] = job
            
            logger.info(f"Enqueued player performance analysis {task_id} for player {player_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue player performance analysis: {e}")
            raise
    
    # Player Monitoring Task Management
    
    def enqueue_player_monitoring(
        self,
        player_ids: Optional[List[str]] = None,
        check_period_hours: int = 24,
        send_notifications: bool = True
    ) -> str:
        """Enqueue player monitoring task."""
        try:
            job = self.queues[TaskPriority.DEFAULT].enqueue(
                monitor_player_matches_task,
                player_ids,
                check_period_hours,
                send_notifications,
                job_timeout=3600,
                retry=2
            )
            
            task_id = job.id
            self._active_tasks[task_id] = job
            
            logger.info(f"Enqueued player monitoring task {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue player monitoring task: {e}")
            raise
    
    def enqueue_batch_player_update(
        self,
        batch_size: int = 50,
        update_interval_hours: int = 6,
        priority_players: Optional[List[str]] = None
    ) -> str:
        """Enqueue batch player update task."""
        try:
            job = self.queues[TaskPriority.LOW].enqueue(
                batch_update_players_task,
                batch_size,
                update_interval_hours,
                priority_players,
                job_timeout=7200,  # 2 hours
                retry=1
            )
            
            task_id = job.id
            self._active_tasks[task_id] = job
            
            logger.info(f"Enqueued batch player update task {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue batch player update: {e}")
            raise
    
    def enqueue_elo_tracking(
        self,
        player_ids: Optional[List[str]] = None,
        notification_threshold: int = 50
    ) -> str:
        """Enqueue ELO change tracking task."""
        try:
            job = self.queues[TaskPriority.DEFAULT].enqueue(
                check_elo_changes_task,
                player_ids,
                notification_threshold,
                True,  # track_all_changes
                job_timeout=1800,
                retry=2
            )
            
            task_id = job.id
            self._active_tasks[task_id] = job
            
            logger.info(f"Enqueued ELO tracking task {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue ELO tracking task: {e}")
            raise
    
    # Cache Management Task Management
    
    def enqueue_cache_warming(
        self,
        warm_type: str = "popular_data",
        priority_items: Optional[List[str]] = None,
        force_refresh: bool = False
    ) -> str:
        """Enqueue cache warming task."""
        try:
            job = self.queues[TaskPriority.LOW].enqueue(
                warm_cache_task,
                warm_type,
                priority_items,
                force_refresh,
                job_timeout=3600,
                retry=2
            )
            
            task_id = job.id
            self._active_tasks[task_id] = job
            
            logger.info(f"Enqueued cache warming task {task_id} (type: {warm_type})")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue cache warming task: {e}")
            raise
    
    def enqueue_cache_cleanup(
        self,
        cleanup_type: str = "expired",
        max_items_to_remove: int = 1000,
        dry_run: bool = False
    ) -> str:
        """Enqueue cache cleanup task."""
        try:
            job = self.queues[TaskPriority.LOW].enqueue(
                cleanup_expired_cache_task,
                cleanup_type,
                max_items_to_remove,
                dry_run,
                job_timeout=1800,
                retry=1
            )
            
            task_id = job.id
            self._active_tasks[task_id] = job
            
            logger.info(f"Enqueued cache cleanup task {task_id} (type: {cleanup_type})")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue cache cleanup task: {e}")
            raise
    
    def enqueue_cache_optimization(
        self,
        optimization_type: str = "comprehensive",
        target_memory_reduction_mb: int = 100
    ) -> str:
        """Enqueue cache optimization task."""
        try:
            job = self.queues[TaskPriority.LOW].enqueue(
                optimize_cache_usage_task,
                optimization_type,
                target_memory_reduction_mb,
                job_timeout=2400,
                retry=1
            )
            
            task_id = job.id
            self._active_tasks[task_id] = job
            
            logger.info(f"Enqueued cache optimization task {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue cache optimization task: {e}")
            raise
    
    # Notification Task Management
    
    def enqueue_match_notification(
        self,
        user_id: int,
        match_id: str,
        notification_data: Optional[Dict[str, Any]] = None,
        priority: TaskPriority = TaskPriority.HIGH
    ) -> str:
        """Enqueue match notification task."""
        try:
            job = self.queues[priority].enqueue(
                send_match_notification_task,
                user_id,
                match_id,
                notification_data,
                job_timeout=300,
                retry=3
            )
            
            task_id = job.id
            self._active_tasks[task_id] = job
            
            logger.info(f"Enqueued match notification task {task_id} for user {user_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue match notification: {e}")
            raise
    
    def enqueue_bulk_notifications(
        self,
        notification_type: str,
        recipients: List[int],
        message_template: str,
        personalization_data: Optional[Dict[int, Dict[str, Any]]] = None,
        batch_size: int = 10
    ) -> str:
        """Enqueue bulk notification task."""
        try:
            job = self.queues[TaskPriority.DEFAULT].enqueue(
                send_bulk_notifications_task,
                notification_type,
                recipients,
                message_template,
                personalization_data,
                batch_size,
                1000,  # delay_between_batches_ms
                job_timeout=1800,
                retry=2
            )
            
            task_id = job.id
            self._active_tasks[task_id] = job
            
            logger.info(f"Enqueued bulk notifications task {task_id} for {len(recipients)} users")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue bulk notifications: {e}")
            raise
    
    def enqueue_announcement_broadcast(
        self,
        announcement: str,
        target_users: str = "all",
        user_filters: Optional[Dict[str, Any]] = None,
        scheduling_options: Optional[Dict[str, Any]] = None
    ) -> str:
        """Enqueue announcement broadcast task."""
        try:
            job = self.queues[TaskPriority.DEFAULT].enqueue(
                broadcast_announcement_task,
                announcement,
                target_users,
                user_filters,
                scheduling_options,
                job_timeout=3600,
                retry=2
            )
            
            task_id = job.id
            self._active_tasks[task_id] = job
            
            logger.info(f"Enqueued announcement broadcast task {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue announcement broadcast: {e}")
            raise
    
    # Analytics Task Management
    
    def enqueue_user_analytics(
        self,
        user_id: int,
        analysis_period_days: int = 30,
        detailed_analysis: bool = True,
        include_predictions: bool = False
    ) -> str:
        """Enqueue user analytics generation task."""
        try:
            job = self.queues[TaskPriority.DEFAULT].enqueue(
                generate_user_analytics_task,
                user_id,
                analysis_period_days,
                detailed_analysis,
                include_predictions,
                job_timeout=1800,
                retry=2
            )
            
            task_id = job.id
            self._active_tasks[task_id] = job
            
            logger.info(f"Enqueued user analytics task {task_id} for user {user_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue user analytics task: {e}")
            raise
    
    def enqueue_global_statistics(
        self,
        include_trends: bool = True,
        detailed_breakdown: bool = True,
        time_periods: Optional[List[int]] = None
    ) -> str:
        """Enqueue global statistics calculation task."""
        try:
            job = self.queues[TaskPriority.LOW].enqueue(
                calculate_global_statistics_task,
                include_trends,
                detailed_breakdown,
                time_periods,
                job_timeout=3600,
                retry=1
            )
            
            task_id = job.id
            self._active_tasks[task_id] = job
            
            logger.info(f"Enqueued global statistics task {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue global statistics task: {e}")
            raise
    
    def enqueue_monthly_report(
        self,
        target_month: Optional[str] = None,
        include_user_reports: bool = True,
        include_global_stats: bool = True,
        detailed_analysis: bool = True
    ) -> str:
        """Enqueue monthly report generation task."""
        try:
            job = self.queues[TaskPriority.LOW].enqueue(
                create_monthly_report_task,
                target_month,
                include_user_reports,
                include_global_stats,
                detailed_analysis,
                job_timeout=3600,
                retry=1
            )
            
            task_id = job.id
            self._active_tasks[task_id] = job
            
            logger.info(f"Enqueued monthly report task {task_id} for {target_month or 'previous month'}")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to enqueue monthly report task: {e}")
            raise
    
    # Task Monitoring and Management
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get current status of a task."""
        try:
            job = Job.fetch(task_id, connection=self.redis)
            
            status = TaskStatus.QUEUED
            if job.is_started:
                status = TaskStatus.STARTED
            elif job.is_finished:
                status = TaskStatus.FINISHED
            elif job.is_failed:
                status = TaskStatus.FAILED
            elif job.is_cancelled:
                status = TaskStatus.CANCELLED
            
            result = {
                "task_id": task_id,
                "status": status.value,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "ended_at": job.ended_at.isoformat() if job.ended_at else None,
                "progress": job.meta.get('progress', {}) if job.meta else {},
                "result": job.result if job.is_finished else None,
                "failure_info": {
                    "exception": str(job.exc_info) if job.is_failed and job.exc_info else None,
                    "traceback": job.meta.get('traceback') if job.meta else None
                } if job.is_failed else None
            }
            
            return result
            
        except NoSuchJobError:
            return {
                "task_id": task_id,
                "status": "not_found",
                "error": "Task not found"
            }
        except Exception as e:
            logger.error(f"Error getting task status for {task_id}: {e}")
            return {
                "task_id": task_id,
                "status": "error",
                "error": str(e)
            }
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a queued or running task."""
        try:
            job = Job.fetch(task_id, connection=self.redis)
            
            if job.is_finished or job.is_failed:
                return False  # Cannot cancel completed tasks
            
            job.cancel()
            
            # Remove from active tasks
            if task_id in self._active_tasks:
                del self._active_tasks[task_id]
            
            logger.info(f"Cancelled task {task_id}")
            return True
            
        except NoSuchJobError:
            logger.warning(f"Attempted to cancel non-existent task {task_id}")
            return False
        except Exception as e:
            logger.error(f"Error cancelling task {task_id}: {e}")
            return False
    
    def get_queue_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all queues."""
        stats = {}
        
        for priority, queue in self.queues.items():
            try:
                stats[priority.value] = {
                    "queued_jobs": len(queue),
                    "started_jobs": len(StartedJobRegistry(queue=queue)),
                    "finished_jobs": len(FinishedJobRegistry(queue=queue)),
                    "failed_jobs": len(FailedJobRegistry(queue=queue))
                }
            except Exception as e:
                logger.error(f"Error getting stats for queue {priority.value}: {e}")
                stats[priority.value] = {"error": str(e)}
        
        return stats
    
    def cleanup_finished_tasks(self, older_than_hours: int = 24) -> int:
        """Clean up finished tasks older than specified hours."""
        cleaned_count = 0
        cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
        
        for priority, queue in self.queues.items():
            try:
                finished_registry = FinishedJobRegistry(queue=queue)
                
                # Get finished job IDs
                job_ids = finished_registry.get_job_ids()
                
                for job_id in job_ids:
                    try:
                        job = Job.fetch(job_id, connection=self.redis)
                        if job.ended_at and job.ended_at < cutoff_time:
                            finished_registry.remove(job_id)
                            cleaned_count += 1
                    except NoSuchJobError:
                        continue
                    
            except Exception as e:
                logger.error(f"Error cleaning up finished tasks in queue {priority.value}: {e}")
        
        logger.info(f"Cleaned up {cleaned_count} finished tasks older than {older_than_hours} hours")
        return cleaned_count
    
    def retry_failed_task(self, task_id: str) -> Optional[str]:
        """Retry a failed task."""
        try:
            failed_job = Job.fetch(task_id, connection=self.redis)
            
            if not failed_job.is_failed:
                logger.warning(f"Task {task_id} is not in failed state")
                return None
            
            # Create new job with same parameters
            new_job = failed_job.retry()
            new_task_id = new_job.id
            
            self._active_tasks[new_task_id] = new_job
            
            logger.info(f"Retrying failed task {task_id} as new task {new_task_id}")
            return new_task_id
            
        except Exception as e:
            logger.error(f"Error retrying failed task {task_id}: {e}")
            return None
    
    # Scheduled Task Management
    
    def schedule_recurring_task(
        self,
        task_name: str,
        task_function: Callable,
        schedule_interval_minutes: int,
        task_args: tuple = (),
        task_kwargs: Dict[str, Any] = None,
        priority: TaskPriority = TaskPriority.DEFAULT
    ) -> str:
        """Schedule a recurring task."""
        schedule_id = str(uuid.uuid4())
        
        if task_kwargs is None:
            task_kwargs = {}
        
        scheduled_task = {
            "schedule_id": schedule_id,
            "task_name": task_name,
            "task_function": task_function,
            "interval_minutes": schedule_interval_minutes,
            "task_args": task_args,
            "task_kwargs": task_kwargs,
            "priority": priority,
            "last_run": None,
            "next_run": datetime.now() + timedelta(minutes=schedule_interval_minutes),
            "enabled": True,
            "run_count": 0
        }
        
        self._scheduled_tasks[schedule_id] = scheduled_task
        
        logger.info(f"Scheduled recurring task '{task_name}' (ID: {schedule_id}) to run every {schedule_interval_minutes} minutes")
        return schedule_id
    
    def process_scheduled_tasks(self) -> int:
        """Process due scheduled tasks."""
        now = datetime.now()
        processed_count = 0
        
        for schedule_id, task_info in self._scheduled_tasks.items():
            if not task_info["enabled"]:
                continue
            
            if now >= task_info["next_run"]:
                try:
                    # Enqueue the scheduled task
                    job = self.queues[task_info["priority"]].enqueue(
                        task_info["task_function"],
                        *task_info["task_args"],
                        **task_info["task_kwargs"]
                    )
                    
                    # Update task info
                    task_info["last_run"] = now
                    task_info["next_run"] = now + timedelta(minutes=task_info["interval_minutes"])
                    task_info["run_count"] += 1
                    
                    processed_count += 1
                    
                    logger.info(f"Executed scheduled task '{task_info['task_name']}' (job: {job.id})")
                    
                except Exception as e:
                    logger.error(f"Error executing scheduled task '{task_info['task_name']}': {e}")
        
        return processed_count
    
    def disable_scheduled_task(self, schedule_id: str) -> bool:
        """Disable a scheduled task."""
        if schedule_id in self._scheduled_tasks:
            self._scheduled_tasks[schedule_id]["enabled"] = False
            logger.info(f"Disabled scheduled task {schedule_id}")
            return True
        return False
    
    def enable_scheduled_task(self, schedule_id: str) -> bool:
        """Enable a scheduled task."""
        if schedule_id in self._scheduled_tasks:
            self._scheduled_tasks[schedule_id]["enabled"] = True
            logger.info(f"Enabled scheduled task {schedule_id}")
            return True
        return False
    
    def get_scheduled_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all scheduled tasks."""
        return {
            schedule_id: {
                "task_name": info["task_name"],
                "interval_minutes": info["interval_minutes"],
                "enabled": info["enabled"],
                "last_run": info["last_run"].isoformat() if info["last_run"] else None,
                "next_run": info["next_run"].isoformat() if info["next_run"] else None,
                "run_count": info["run_count"]
            }
            for schedule_id, info in self._scheduled_tasks.items()
        }
    
    # Health and Monitoring
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check on task management system."""
        try:
            # Test Redis connection
            self.redis.ping()
            redis_healthy = True
        except Exception as e:
            redis_healthy = False
            redis_error = str(e)
        
        # Get queue statistics
        queue_stats = self.get_queue_stats()
        
        # Count active tasks
        active_task_count = len(self._active_tasks)
        scheduled_task_count = len(self._scheduled_tasks)
        
        health_status = {
            "redis_connection": "healthy" if redis_healthy else "unhealthy",
            "redis_error": redis_error if not redis_healthy else None,
            "active_tasks": active_task_count,
            "scheduled_tasks": scheduled_task_count,
            "queue_statistics": queue_stats,
            "timestamp": datetime.now().isoformat()
        }
        
        return health_status
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Get comprehensive system metrics."""
        try:
            # Redis info
            redis_info = self.redis.info()
            
            # Queue statistics
            queue_stats = self.get_queue_stats()
            
            # Calculate total jobs across all states
            total_queued = sum(stats.get("queued_jobs", 0) for stats in queue_stats.values())
            total_started = sum(stats.get("started_jobs", 0) for stats in queue_stats.values())
            total_finished = sum(stats.get("finished_jobs", 0) for stats in queue_stats.values())
            total_failed = sum(stats.get("failed_jobs", 0) for stats in queue_stats.values())
            
            metrics = {
                "redis_metrics": {
                    "connected_clients": redis_info.get("connected_clients", 0),
                    "used_memory": redis_info.get("used_memory", 0),
                    "used_memory_human": redis_info.get("used_memory_human", "0B"),
                    "total_commands_processed": redis_info.get("total_commands_processed", 0),
                    "keyspace_hits": redis_info.get("keyspace_hits", 0),
                    "keyspace_misses": redis_info.get("keyspace_misses", 0)
                },
                "job_statistics": {
                    "total_queued": total_queued,
                    "total_started": total_started,
                    "total_finished": total_finished,
                    "total_failed": total_failed,
                    "total_jobs": total_queued + total_started + total_finished + total_failed,
                    "success_rate": round((total_finished / max(total_finished + total_failed, 1)) * 100, 2)
                },
                "queue_details": queue_stats,
                "task_management": {
                    "active_tasks_tracked": len(self._active_tasks),
                    "scheduled_tasks": len(self._scheduled_tasks),
                    "enabled_scheduled_tasks": len([t for t in self._scheduled_tasks.values() if t["enabled"]])
                },
                "timestamp": datetime.now().isoformat()
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }


# Global task manager instance
task_manager = TaskManager()


def get_task_manager() -> TaskManager:
    """Get the global task manager instance."""
    return task_manager


# Convenience functions for common operations

def enqueue_match_analysis(match_url: str, user_id: int, **kwargs) -> str:
    """Convenience function to enqueue match analysis."""
    return task_manager.enqueue_match_analysis(match_url, user_id, **kwargs)


def enqueue_player_monitoring(**kwargs) -> str:
    """Convenience function to enqueue player monitoring."""
    return task_manager.enqueue_player_monitoring(**kwargs)


def enqueue_cache_warming(**kwargs) -> str:
    """Convenience function to enqueue cache warming."""
    return task_manager.enqueue_cache_warming(**kwargs)


def get_task_status(task_id: str) -> Dict[str, Any]:
    """Convenience function to get task status."""
    return task_manager.get_task_status(task_id)