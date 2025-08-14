"""Queue configuration for RQ system."""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum

from config.settings import settings


class QueuePriority(Enum):
    """Queue priority levels."""
    HIGH = "high"
    DEFAULT = "default"
    LOW = "low"


class JobStatus(Enum):
    """Job status enumeration."""
    QUEUED = "queued"
    STARTED = "started"
    FINISHED = "finished"
    FAILED = "failed"
    DEFERRED = "deferred"
    CANCELED = "canceled"


@dataclass
class QueueConfig:
    """Configuration for queue system."""
    
    # Redis connection
    redis_url: str
    redis_password: Optional[str] = None
    redis_max_connections: int = 10
    
    # Queue settings
    default_timeout: int = 300  # 5 minutes
    high_priority_timeout: int = 180  # 3 minutes
    low_priority_timeout: int = 600  # 10 minutes
    
    # Worker settings
    max_workers: int = 4
    worker_ttl: int = 420  # 7 minutes
    job_monitoring_interval: int = 30  # 30 seconds
    
    # Retry settings
    max_retries: int = 3
    retry_delays: List[int] = None  # Will be set in __post_init__
    
    # Job result TTL
    result_ttl: int = 3600  # 1 hour
    failure_ttl: int = 86400  # 24 hours
    
    # Performance settings
    connection_pool_size: int = 20
    burst_timeout: int = 60
    
    # Monitoring settings
    enable_monitoring: bool = True
    metrics_retention_days: int = 7
    
    # Queue-specific settings
    queue_settings: Dict[str, Dict] = None
    
    def __post_init__(self):
        """Initialize default values after creation."""
        if self.retry_delays is None:
            self.retry_delays = [10, 30, 90]  # Exponential backoff: 10s, 30s, 90s
            
        if self.queue_settings is None:
            self.queue_settings = {
                QueuePriority.HIGH.value: {
                    'timeout': self.high_priority_timeout,
                    'max_jobs': 50,
                    'description': 'High priority jobs (real-time analysis)'
                },
                QueuePriority.DEFAULT.value: {
                    'timeout': self.default_timeout,
                    'max_jobs': 100,
                    'description': 'Standard priority jobs (match analysis)'
                },
                QueuePriority.LOW.value: {
                    'timeout': self.low_priority_timeout,
                    'max_jobs': 200,
                    'description': 'Low priority jobs (batch processing, reports)'
                }
            }


def get_queue_config() -> QueueConfig:
    """Get queue configuration from application settings."""
    return QueueConfig(
        redis_url=settings.redis_url,
        redis_password=settings.redis_password,
        redis_max_connections=settings.redis_max_connections,
        
        # Get queue-specific settings from environment
        default_timeout=int(os.getenv('QUEUE_DEFAULT_TIMEOUT', '300')),
        high_priority_timeout=int(os.getenv('QUEUE_HIGH_PRIORITY_TIMEOUT', '180')),
        low_priority_timeout=int(os.getenv('QUEUE_LOW_PRIORITY_TIMEOUT', '600')),
        
        max_workers=int(os.getenv('QUEUE_MAX_WORKERS', '4')),
        worker_ttl=int(os.getenv('QUEUE_WORKER_TTL', '420')),
        job_monitoring_interval=int(os.getenv('QUEUE_MONITORING_INTERVAL', '30')),
        
        max_retries=int(os.getenv('QUEUE_MAX_RETRIES', '3')),
        result_ttl=int(os.getenv('QUEUE_RESULT_TTL', '3600')),
        failure_ttl=int(os.getenv('QUEUE_FAILURE_TTL', '86400')),
        
        connection_pool_size=int(os.getenv('QUEUE_CONNECTION_POOL_SIZE', '20')),
        burst_timeout=int(os.getenv('QUEUE_BURST_TIMEOUT', '60')),
        
        enable_monitoring=os.getenv('QUEUE_ENABLE_MONITORING', 'true').lower() == 'true',
        metrics_retention_days=int(os.getenv('QUEUE_METRICS_RETENTION_DAYS', '7')),
    )


def get_job_timeout(priority: QueuePriority) -> int:
    """Get timeout for specific queue priority."""
    config = get_queue_config()
    return config.queue_settings[priority.value]['timeout']


def get_queue_name(priority: QueuePriority) -> str:
    """Get queue name for specific priority."""
    return f"faceit_bot_{priority.value}"


def get_worker_name(worker_id: int = 0) -> str:
    """Get worker name with ID."""
    return f"faceit_worker_{worker_id}"


# Queue-specific configurations
ANALYSIS_QUEUE_CONFIG = {
    'name': get_queue_name(QueuePriority.HIGH),
    'priority': QueuePriority.HIGH,
    'description': 'Real-time match analysis requests',
    'max_concurrent_jobs': 5,
    'timeout': get_job_timeout(QueuePriority.HIGH)
}

MONITORING_QUEUE_CONFIG = {
    'name': get_queue_name(QueuePriority.DEFAULT),
    'priority': QueuePriority.DEFAULT,
    'description': 'Match monitoring and notifications',
    'max_concurrent_jobs': 10,
    'timeout': get_job_timeout(QueuePriority.DEFAULT)
}

REPORTING_QUEUE_CONFIG = {
    'name': get_queue_name(QueuePriority.LOW),
    'priority': QueuePriority.LOW,
    'description': 'Analytics reports and bulk processing',
    'max_concurrent_jobs': 3,
    'timeout': get_job_timeout(QueuePriority.LOW)
}

# All queue configurations
QUEUE_CONFIGS = {
    QueuePriority.HIGH: ANALYSIS_QUEUE_CONFIG,
    QueuePriority.DEFAULT: MONITORING_QUEUE_CONFIG,
    QueuePriority.LOW: REPORTING_QUEUE_CONFIG
}