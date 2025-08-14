"""Queue management system for FACEIT Telegram Bot."""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import asdict

import redis
from rq import Queue, Worker, Connection, get_current_job
from rq.job import Job
from rq.registry import StartedJobRegistry, FinishedJobRegistry, FailedJobRegistry
from rq.exceptions import NoSuchJobError, InvalidJobOperationError

from .config import (
    QueueConfig, QueuePriority, JobStatus, get_queue_config,
    get_queue_name, get_worker_name, QUEUE_CONFIGS
)

logger = logging.getLogger(__name__)


class QueueManager:
    """Central queue management system."""
    
    def __init__(self, config: Optional[QueueConfig] = None):
        """Initialize queue manager."""
        self.config = config or get_queue_config()
        self.redis_conn = None
        self.queues: Dict[QueuePriority, Queue] = {}
        self.workers: Dict[str, Worker] = {}
        self._initialized = False
        
    async def initialize(self) -> None:
        """Initialize Redis connection and queues."""
        if self._initialized:
            logger.warning("Queue manager already initialized")
            return
            
        try:
            # Setup Redis connection
            self.redis_conn = redis.from_url(
                self.config.redis_url,
                password=self.config.redis_password,
                max_connections=self.config.redis_max_connections,
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )
            
            # Test connection
            await asyncio.get_event_loop().run_in_executor(
                None, self.redis_conn.ping
            )
            
            # Initialize queues for each priority
            for priority in QueuePriority:
                queue_name = get_queue_name(priority)
                self.queues[priority] = Queue(
                    name=queue_name,
                    connection=self.redis_conn,
                    default_timeout=self.config.queue_settings[priority.value]['timeout']
                )
                
            self._initialized = True
            logger.info(f"Queue manager initialized with {len(self.queues)} queues")
            
        except Exception as e:
            logger.error(f"Failed to initialize queue manager: {e}")
            raise
    
    async def cleanup(self) -> None:
        """Cleanup resources."""
        try:
            # Stop all workers
            await self.stop_all_workers()
            
            # Close Redis connection
            if self.redis_conn:
                self.redis_conn.close()
                
            self._initialized = False
            logger.info("Queue manager cleaned up successfully")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def enqueue_job(
        self,
        func: Callable,
        priority: QueuePriority = QueuePriority.DEFAULT,
        job_id: Optional[str] = None,
        timeout: Optional[int] = None,
        result_ttl: Optional[int] = None,
        failure_ttl: Optional[int] = None,
        retry: Optional[int] = None,
        **kwargs
    ) -> Job:
        """Enqueue a job to specified priority queue."""
        if not self._initialized:
            raise RuntimeError("Queue manager not initialized")
            
        queue = self.queues[priority]
        
        # Use config defaults if not specified
        if timeout is None:
            timeout = self.config.queue_settings[priority.value]['timeout']
        if result_ttl is None:
            result_ttl = self.config.result_ttl
        if failure_ttl is None:
            failure_ttl = self.config.failure_ttl
        if retry is None:
            retry = self.config.max_retries
            
        try:
            job = queue.enqueue(
                func,
                job_id=job_id,
                job_timeout=timeout,
                result_ttl=result_ttl,
                failure_ttl=failure_ttl,
                retry=retry,
                **kwargs
            )
            
            logger.info(
                f"Enqueued job {job.id} to {priority.value} queue: {func.__name__}"
            )
            return job
            
        except Exception as e:
            logger.error(f"Failed to enqueue job: {e}")
            raise
    
    def enqueue_match_analysis(
        self,
        match_url_or_id: str,
        user_id: int,
        priority: QueuePriority = QueuePriority.HIGH
    ) -> Job:
        """Enqueue match analysis job."""
        from .jobs import analyze_match_job
        
        return self.enqueue_job(
            analyze_match_job,
            priority=priority,
            job_id=f"match_analysis_{user_id}_{datetime.now().timestamp()}",
            match_url_or_id=match_url_or_id,
            user_id=user_id
        )
    
    def enqueue_player_report(
        self,
        player_id: str,
        user_id: int,
        priority: QueuePriority = QueuePriority.DEFAULT
    ) -> Job:
        """Enqueue player report generation."""
        from .jobs import generate_player_report_job
        
        return self.enqueue_job(
            generate_player_report_job,
            priority=priority,
            job_id=f"player_report_{player_id}_{user_id}",
            player_id=player_id,
            user_id=user_id
        )
    
    def enqueue_bulk_analysis(
        self,
        match_ids: List[str],
        user_id: int,
        priority: QueuePriority = QueuePriority.LOW
    ) -> Job:
        """Enqueue bulk match analysis."""
        from .jobs import process_bulk_analysis_job
        
        return self.enqueue_job(
            process_bulk_analysis_job,
            priority=priority,
            job_id=f"bulk_analysis_{user_id}_{datetime.now().timestamp()}",
            timeout=1800,  # 30 minutes for bulk operations
            match_ids=match_ids,
            user_id=user_id
        )
    
    def enqueue_match_monitoring(
        self,
        user_ids: Optional[List[int]] = None,
        priority: QueuePriority = QueuePriority.DEFAULT
    ) -> Job:
        """Enqueue match monitoring job."""
        from .jobs import monitor_matches_job
        
        return self.enqueue_job(
            monitor_matches_job,
            priority=priority,
            job_id=f"match_monitoring_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            user_ids=user_ids
        )
    
    def enqueue_cache_update(
        self,
        cache_type: str,
        identifiers: List[str],
        priority: QueuePriority = QueuePriority.LOW
    ) -> Job:
        """Enqueue cache update job."""
        from .jobs import update_player_cache_job
        
        return self.enqueue_job(
            update_player_cache_job,
            priority=priority,
            job_id=f"cache_update_{cache_type}_{datetime.now().timestamp()}",
            cache_type=cache_type,
            identifiers=identifiers
        )
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        try:
            return Job.fetch(job_id, connection=self.redis_conn)
        except Exception:
            return None
    
    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        """Get job status."""
        job = self.get_job(job_id)
        if not job:
            return None
            
        status_mapping = {
            'queued': JobStatus.QUEUED,
            'started': JobStatus.STARTED,
            'finished': JobStatus.FINISHED,
            'failed': JobStatus.FAILED,
            'deferred': JobStatus.DEFERRED,
            'canceled': JobStatus.CANCELED
        }
        
        return status_mapping.get(job.get_status(), None)
    
    def get_job_result(self, job_id: str) -> Optional[Any]:
        """Get job result."""
        job = self.get_job(job_id)
        return job.result if job else None
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job."""
        try:
            job = self.get_job(job_id)
            if job and job.get_status() in ['queued', 'deferred']:
                job.cancel()
                logger.info(f"Cancelled job {job_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            return False
    
    def get_queue_info(self, priority: QueuePriority) -> Dict[str, Any]:
        """Get queue information."""
        if priority not in self.queues:
            return {}
            
        queue = self.queues[priority]
        
        try:
            return {
                'name': queue.name,
                'priority': priority.value,
                'length': len(queue),
                'jobs': [job.id for job in queue.jobs],
                'is_empty': queue.is_empty(),
                'config': QUEUE_CONFIGS[priority]
            }
        except Exception as e:
            logger.error(f"Error getting queue info for {priority.value}: {e}")
            return {}
    
    def get_all_queues_info(self) -> Dict[str, Any]:
        """Get information about all queues."""
        return {
            priority.value: self.get_queue_info(priority)
            for priority in QueuePriority
        }
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get comprehensive queue statistics."""
        stats = {
            'total_jobs': 0,
            'queued_jobs': 0,
            'started_jobs': 0,
            'finished_jobs': 0,
            'failed_jobs': 0,
            'queues': {},
            'workers': len(self.workers),
            'timestamp': datetime.now().isoformat()
        }
        
        for priority in QueuePriority:
            queue = self.queues.get(priority)
            if not queue:
                continue
                
            try:
                # Get registries
                started_registry = StartedJobRegistry(queue.name, connection=self.redis_conn)
                finished_registry = FinishedJobRegistry(queue.name, connection=self.redis_conn)
                failed_registry = FailedJobRegistry(queue.name, connection=self.redis_conn)
                
                queue_stats = {
                    'queued': len(queue),
                    'started': len(started_registry),
                    'finished': len(finished_registry.get_job_ids()),
                    'failed': len(failed_registry.get_job_ids())
                }
                
                stats['queues'][priority.value] = queue_stats
                stats['queued_jobs'] += queue_stats['queued']
                stats['started_jobs'] += queue_stats['started']
                stats['finished_jobs'] += queue_stats['finished']
                stats['failed_jobs'] += queue_stats['failed']
                
            except Exception as e:
                logger.error(f"Error getting stats for queue {priority.value}: {e}")
                stats['queues'][priority.value] = {'error': str(e)}
        
        stats['total_jobs'] = (
            stats['queued_jobs'] + stats['started_jobs'] + 
            stats['finished_jobs'] + stats['failed_jobs']
        )
        
        return stats
    
    def create_worker(
        self,
        worker_name: Optional[str] = None,
        queues: Optional[List[QueuePriority]] = None
    ) -> Worker:
        """Create a new worker."""
        if not self._initialized:
            raise RuntimeError("Queue manager not initialized")
        
        if worker_name is None:
            worker_name = get_worker_name(len(self.workers))
            
        if queues is None:
            queues = list(QueuePriority)
        
        queue_objects = [self.queues[priority] for priority in queues]
        
        worker = Worker(
            queues=queue_objects,
            connection=self.redis_conn,
            name=worker_name,
            default_result_ttl=self.config.result_ttl,
            default_worker_ttl=self.config.worker_ttl
        )
        
        self.workers[worker_name] = worker
        logger.info(f"Created worker {worker_name} for queues: {[q.value for q in queues]}")
        
        return worker
    
    async def start_worker(self, worker_name: str) -> None:
        """Start a worker in a separate thread."""
        if worker_name not in self.workers:
            raise ValueError(f"Worker {worker_name} not found")
            
        worker = self.workers[worker_name]
        
        try:
            # Run worker in executor to prevent blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, worker.work, self.config.burst_timeout)
            
        except Exception as e:
            logger.error(f"Error running worker {worker_name}: {e}")
            raise
    
    async def stop_worker(self, worker_name: str) -> None:
        """Stop a specific worker."""
        if worker_name in self.workers:
            worker = self.workers[worker_name]
            worker.request_stop()
            del self.workers[worker_name]
            logger.info(f"Stopped worker {worker_name}")
    
    async def stop_all_workers(self) -> None:
        """Stop all workers."""
        for worker_name in list(self.workers.keys()):
            await self.stop_worker(worker_name)
    
    def clear_queue(self, priority: QueuePriority) -> int:
        """Clear all jobs from a queue."""
        if priority not in self.queues:
            return 0
            
        queue = self.queues[priority]
        job_count = len(queue)
        queue.empty()
        
        logger.info(f"Cleared {job_count} jobs from {priority.value} queue")
        return job_count
    
    def clear_all_queues(self) -> int:
        """Clear all queues."""
        total_cleared = 0
        for priority in QueuePriority:
            total_cleared += self.clear_queue(priority)
        return total_cleared
    
    def requeue_failed_jobs(self, priority: QueuePriority) -> int:
        """Requeue failed jobs in a specific queue."""
        if priority not in self.queues:
            return 0
            
        queue = self.queues[priority]
        failed_registry = FailedJobRegistry(queue.name, connection=self.redis_conn)
        
        requeued_count = 0
        for job_id in failed_registry.get_job_ids():
            try:
                job = Job.fetch(job_id, connection=self.redis_conn)
                if job:
                    job.requeue()
                    requeued_count += 1
            except Exception as e:
                logger.error(f"Failed to requeue job {job_id}: {e}")
        
        logger.info(f"Requeued {requeued_count} failed jobs from {priority.value} queue")
        return requeued_count


# Global queue manager instance
queue_manager = QueueManager()


async def initialize_queue_system() -> QueueManager:
    """Initialize the global queue system."""
    await queue_manager.initialize()
    return queue_manager


async def cleanup_queue_system() -> None:
    """Cleanup the global queue system."""
    await queue_manager.cleanup()


def get_queue_manager() -> QueueManager:
    """Get the global queue manager instance."""
    return queue_manager