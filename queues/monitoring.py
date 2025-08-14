"""Queue monitoring and failure handling utilities."""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import json

import redis
from rq import Queue, Worker, Connection
from rq.job import Job
from rq.registry import StartedJobRegistry, FinishedJobRegistry, FailedJobRegistry, DeferredJobRegistry
from rq.exceptions import NoSuchJobError, InvalidJobOperationError

from .config import QueueConfig, QueuePriority, JobStatus, get_queue_config

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class QueueAlert:
    """Queue system alert."""
    level: AlertLevel
    message: str
    queue_name: Optional[str] = None
    job_id: Optional[str] = None
    worker_name: Optional[str] = None
    timestamp: datetime = None
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.details is None:
            self.details = {}


@dataclass
class QueueMetrics:
    """Queue performance metrics."""
    queue_name: str
    total_jobs: int = 0
    queued_jobs: int = 0
    started_jobs: int = 0
    finished_jobs: int = 0
    failed_jobs: int = 0
    deferred_jobs: int = 0
    
    # Performance metrics
    avg_processing_time: float = 0.0
    success_rate: float = 0.0
    failure_rate: float = 0.0
    
    # Worker metrics
    active_workers: int = 0
    idle_workers: int = 0
    
    # Timestamps
    last_job_finished: Optional[datetime] = None
    last_job_failed: Optional[datetime] = None
    last_updated: datetime = None
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.now()
        
        # Calculate rates
        if self.total_jobs > 0:
            self.success_rate = (self.finished_jobs / self.total_jobs) * 100
            self.failure_rate = (self.failed_jobs / self.total_jobs) * 100


class QueueMonitor:
    """Queue monitoring and alerting system."""
    
    def __init__(self, config: Optional[QueueConfig] = None):
        """Initialize queue monitor."""
        self.config = config or get_queue_config()
        self.redis_conn = None
        self.alerts: List[QueueAlert] = []
        self.metrics_history: Dict[str, List[QueueMetrics]] = {}
        self.alert_handlers: List = []
        self._monitoring = False
        self._monitor_task = None
        
    async def initialize(self) -> None:
        """Initialize Redis connection."""
        try:
            self.redis_conn = redis.from_url(
                self.config.redis_url,
                password=self.config.redis_password,
                decode_responses=True
            )
            await asyncio.get_event_loop().run_in_executor(None, self.redis_conn.ping)
            logger.info("Queue monitor initialized")
        except Exception as e:
            logger.error(f"Failed to initialize queue monitor: {e}")
            raise
    
    async def start_monitoring(self, interval: Optional[int] = None) -> None:
        """Start continuous monitoring."""
        if self._monitoring:
            logger.warning("Monitoring already running")
            return
        
        if interval is None:
            interval = self.config.job_monitoring_interval
        
        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop(interval))
        logger.info(f"Started queue monitoring with {interval}s interval")
    
    async def stop_monitoring(self) -> None:
        """Stop continuous monitoring."""
        if not self._monitoring:
            return
        
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped queue monitoring")
    
    async def _monitoring_loop(self, interval: int) -> None:
        """Main monitoring loop."""
        while self._monitoring:
            try:
                await self.collect_metrics()
                await self.check_queue_health()
                await self.cleanup_old_alerts()
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(interval)
    
    async def collect_metrics(self) -> Dict[str, QueueMetrics]:
        """Collect metrics for all queues."""
        metrics = {}
        
        for priority in QueuePriority:
            queue_name = f"faceit_bot_{priority.value}"
            try:
                queue_metrics = await self._collect_queue_metrics(queue_name)
                metrics[queue_name] = queue_metrics
                
                # Store metrics history
                if queue_name not in self.metrics_history:
                    self.metrics_history[queue_name] = []
                
                self.metrics_history[queue_name].append(queue_metrics)
                
                # Keep only recent metrics (last 24 hours)
                cutoff_time = datetime.now() - timedelta(hours=24)
                self.metrics_history[queue_name] = [
                    m for m in self.metrics_history[queue_name] 
                    if m.last_updated >= cutoff_time
                ]
                
            except Exception as e:
                logger.error(f"Failed to collect metrics for {queue_name}: {e}")
                await self._create_alert(
                    AlertLevel.ERROR,
                    f"Failed to collect metrics for {queue_name}: {e}",
                    queue_name=queue_name
                )
        
        return metrics
    
    async def _collect_queue_metrics(self, queue_name: str) -> QueueMetrics:
        """Collect metrics for a specific queue."""
        def _get_metrics():
            queue = Queue(name=queue_name, connection=self.redis_conn)
            
            # Get registries
            started_registry = StartedJobRegistry(queue_name, connection=self.redis_conn)
            finished_registry = FinishedJobRegistry(queue_name, connection=self.redis_conn)
            failed_registry = FailedJobRegistry(queue_name, connection=self.redis_conn)
            deferred_registry = DeferredJobRegistry(queue_name, connection=self.redis_conn)
            
            # Get job counts
            queued_jobs = len(queue)
            started_jobs = len(started_registry)
            finished_job_ids = finished_registry.get_job_ids()
            failed_job_ids = failed_registry.get_job_ids()
            deferred_jobs = len(deferred_registry)
            
            # Calculate processing times and get last job times
            finished_jobs = []
            failed_jobs = []
            last_finished = None
            last_failed = None
            
            # Get recent finished jobs
            for job_id in finished_job_ids[:50]:  # Last 50 jobs
                try:
                    job = Job.fetch(job_id, connection=self.redis_conn)
                    if job and job.ended_at and job.started_at:
                        processing_time = (job.ended_at - job.started_at).total_seconds()
                        finished_jobs.append(processing_time)
                        if not last_finished or job.ended_at > last_finished:
                            last_finished = job.ended_at
                except:
                    continue
            
            # Get recent failed jobs
            for job_id in failed_job_ids[:20]:  # Last 20 failed jobs
                try:
                    job = Job.fetch(job_id, connection=self.redis_conn)
                    if job and job.ended_at:
                        if not last_failed or job.ended_at > last_failed:
                            last_failed = job.ended_at
                        failed_jobs.append(job)
                except:
                    continue
            
            # Get worker info
            workers = Worker.all(queue=queue)
            active_workers = len([w for w in workers if w.state == 'busy'])
            idle_workers = len([w for w in workers if w.state == 'idle'])
            
            # Calculate averages
            avg_processing_time = sum(finished_jobs) / len(finished_jobs) if finished_jobs else 0
            
            return QueueMetrics(
                queue_name=queue_name,
                total_jobs=queued_jobs + started_jobs + len(finished_job_ids) + len(failed_job_ids),
                queued_jobs=queued_jobs,
                started_jobs=started_jobs,
                finished_jobs=len(finished_job_ids),
                failed_jobs=len(failed_job_ids),
                deferred_jobs=deferred_jobs,
                avg_processing_time=avg_processing_time,
                active_workers=active_workers,
                idle_workers=idle_workers,
                last_job_finished=last_finished,
                last_job_failed=last_failed
            )
        
        return await asyncio.get_event_loop().run_in_executor(None, _get_metrics)
    
    async def check_queue_health(self) -> List[QueueAlert]:
        """Check queue health and generate alerts."""
        alerts = []
        
        for priority in QueuePriority:
            queue_name = f"faceit_bot_{priority.value}"
            
            if queue_name not in self.metrics_history:
                continue
                
            recent_metrics = self.metrics_history[queue_name]
            if not recent_metrics:
                continue
            
            latest_metrics = recent_metrics[-1]
            
            # Check for high failure rate
            if latest_metrics.failure_rate > 20:  # More than 20% failures
                alert = await self._create_alert(
                    AlertLevel.WARNING,
                    f"High failure rate in {queue_name}: {latest_metrics.failure_rate:.1f}%",
                    queue_name=queue_name,
                    details={"failure_rate": latest_metrics.failure_rate}
                )
                alerts.append(alert)
            
            # Check for queue backup
            if latest_metrics.queued_jobs > 50:
                alert = await self._create_alert(
                    AlertLevel.WARNING,
                    f"Queue backup detected in {queue_name}: {latest_metrics.queued_jobs} jobs queued",
                    queue_name=queue_name,
                    details={"queued_jobs": latest_metrics.queued_jobs}
                )
                alerts.append(alert)
            
            # Check for no workers
            if latest_metrics.active_workers == 0 and latest_metrics.idle_workers == 0:
                alert = await self._create_alert(
                    AlertLevel.ERROR,
                    f"No workers available for {queue_name}",
                    queue_name=queue_name,
                    details={"workers": 0}
                )
                alerts.append(alert)
            
            # Check for slow processing
            if latest_metrics.avg_processing_time > 300:  # More than 5 minutes
                alert = await self._create_alert(
                    AlertLevel.WARNING,
                    f"Slow job processing in {queue_name}: {latest_metrics.avg_processing_time:.1f}s average",
                    queue_name=queue_name,
                    details={"avg_processing_time": latest_metrics.avg_processing_time}
                )
                alerts.append(alert)
            
            # Check for stale jobs (no activity in last hour)
            if latest_metrics.last_job_finished:
                time_since_last = datetime.now() - latest_metrics.last_job_finished
                if time_since_last > timedelta(hours=1) and latest_metrics.queued_jobs > 0:
                    alert = await self._create_alert(
                        AlertLevel.WARNING,
                        f"Stale jobs in {queue_name}: no activity for {time_since_last}",
                        queue_name=queue_name,
                        details={"stale_duration": str(time_since_last)}
                    )
                    alerts.append(alert)
        
        return alerts
    
    async def _create_alert(
        self,
        level: AlertLevel,
        message: str,
        queue_name: Optional[str] = None,
        job_id: Optional[str] = None,
        worker_name: Optional[str] = None,
        details: Optional[Dict] = None
    ) -> QueueAlert:
        """Create and store an alert."""
        alert = QueueAlert(
            level=level,
            message=message,
            queue_name=queue_name,
            job_id=job_id,
            worker_name=worker_name,
            details=details or {}
        )
        
        self.alerts.append(alert)
        
        # Log the alert
        log_func = {
            AlertLevel.INFO: logger.info,
            AlertLevel.WARNING: logger.warning,
            AlertLevel.ERROR: logger.error,
            AlertLevel.CRITICAL: logger.critical
        }[level]
        
        log_func(f"Queue Alert [{level.value.upper()}]: {message}")
        
        # Notify alert handlers
        for handler in self.alert_handlers:
            try:
                await handler(alert)
            except Exception as e:
                logger.error(f"Error in alert handler: {e}")
        
        return alert
    
    async def cleanup_old_alerts(self) -> None:
        """Remove old alerts."""
        cutoff_time = datetime.now() - timedelta(hours=24)
        original_count = len(self.alerts)
        self.alerts = [alert for alert in self.alerts if alert.timestamp >= cutoff_time]
        
        removed_count = original_count - len(self.alerts)
        if removed_count > 0:
            logger.debug(f"Cleaned up {removed_count} old alerts")
    
    def add_alert_handler(self, handler) -> None:
        """Add an alert handler function."""
        self.alert_handlers.append(handler)
    
    def get_recent_alerts(
        self,
        hours: int = 24,
        level: Optional[AlertLevel] = None,
        queue_name: Optional[str] = None
    ) -> List[QueueAlert]:
        """Get recent alerts with optional filtering."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        filtered_alerts = [
            alert for alert in self.alerts
            if alert.timestamp >= cutoff_time
        ]
        
        if level:
            filtered_alerts = [alert for alert in filtered_alerts if alert.level == level]
        
        if queue_name:
            filtered_alerts = [alert for alert in filtered_alerts if alert.queue_name == queue_name]
        
        return sorted(filtered_alerts, key=lambda x: x.timestamp, reverse=True)
    
    def get_queue_metrics_history(
        self,
        queue_name: str,
        hours: int = 24
    ) -> List[QueueMetrics]:
        """Get metrics history for a specific queue."""
        if queue_name not in self.metrics_history:
            return []
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [
            metrics for metrics in self.metrics_history[queue_name]
            if metrics.last_updated >= cutoff_time
        ]
    
    def get_system_health_summary(self) -> Dict[str, Any]:
        """Get overall system health summary."""
        total_alerts = len(self.alerts)
        critical_alerts = len([a for a in self.alerts if a.level == AlertLevel.CRITICAL])
        error_alerts = len([a for a in self.alerts if a.level == AlertLevel.ERROR])
        warning_alerts = len([a for a in self.alerts if a.level == AlertLevel.WARNING])
        
        # Calculate health score (0-100)
        health_score = 100
        health_score -= critical_alerts * 20
        health_score -= error_alerts * 10
        health_score -= warning_alerts * 5
        health_score = max(0, health_score)
        
        # Determine overall status
        if critical_alerts > 0:
            status = "critical"
        elif error_alerts > 0:
            status = "error"
        elif warning_alerts > 0:
            status = "warning"
        else:
            status = "healthy"
        
        # Queue summaries
        queue_summaries = {}
        for queue_name, metrics_list in self.metrics_history.items():
            if metrics_list:
                latest = metrics_list[-1]
                queue_summaries[queue_name] = {
                    "total_jobs": latest.total_jobs,
                    "queued_jobs": latest.queued_jobs,
                    "success_rate": latest.success_rate,
                    "failure_rate": latest.failure_rate,
                    "active_workers": latest.active_workers
                }
        
        return {
            "status": status,
            "health_score": health_score,
            "alerts": {
                "total": total_alerts,
                "critical": critical_alerts,
                "error": error_alerts,
                "warning": warning_alerts
            },
            "queues": queue_summaries,
            "last_updated": datetime.now().isoformat()
        }
    
    async def generate_monitoring_report(self, hours: int = 24) -> Dict[str, Any]:
        """Generate comprehensive monitoring report."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        report = {
            "period": f"Last {hours} hours",
            "generated_at": datetime.now().isoformat(),
            "system_health": self.get_system_health_summary(),
            "alerts": [asdict(alert) for alert in self.get_recent_alerts(hours)],
            "queue_metrics": {},
            "performance_summary": {}
        }
        
        # Add detailed queue metrics
        for queue_name, metrics_list in self.metrics_history.items():
            recent_metrics = [m for m in metrics_list if m.last_updated >= cutoff_time]
            if recent_metrics:
                latest = recent_metrics[-1]
                
                # Calculate trends
                if len(recent_metrics) > 1:
                    first = recent_metrics[0]
                    job_trend = latest.total_jobs - first.total_jobs
                    success_trend = latest.success_rate - first.success_rate
                else:
                    job_trend = 0
                    success_trend = 0
                
                report["queue_metrics"][queue_name] = {
                    "current": asdict(latest),
                    "trends": {
                        "job_change": job_trend,
                        "success_rate_change": success_trend
                    },
                    "data_points": len(recent_metrics)
                }
        
        # Performance summary
        all_recent_metrics = []
        for metrics_list in self.metrics_history.values():
            all_recent_metrics.extend([
                m for m in metrics_list if m.last_updated >= cutoff_time
            ])
        
        if all_recent_metrics:
            avg_processing_time = sum(m.avg_processing_time for m in all_recent_metrics) / len(all_recent_metrics)
            avg_success_rate = sum(m.success_rate for m in all_recent_metrics) / len(all_recent_metrics)
            total_jobs_processed = sum(m.finished_jobs + m.failed_jobs for m in all_recent_metrics)
            
            report["performance_summary"] = {
                "avg_processing_time": round(avg_processing_time, 2),
                "avg_success_rate": round(avg_success_rate, 2),
                "total_jobs_processed": total_jobs_processed,
                "data_points": len(all_recent_metrics)
            }
        
        return report
    
    async def cleanup(self) -> None:
        """Cleanup monitoring resources."""
        await self.stop_monitoring()
        if self.redis_conn:
            self.redis_conn.close()


# Global monitor instance
queue_monitor = QueueMonitor()


async def initialize_queue_monitoring() -> QueueMonitor:
    """Initialize the global queue monitoring system."""
    await queue_monitor.initialize()
    return queue_monitor


async def cleanup_queue_monitoring() -> None:
    """Cleanup the global queue monitoring system."""
    await queue_monitor.cleanup()


def get_queue_monitor() -> QueueMonitor:
    """Get the global queue monitor instance."""
    return queue_monitor