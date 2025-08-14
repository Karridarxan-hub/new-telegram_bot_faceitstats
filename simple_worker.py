#!/usr/bin/env python3
"""Simple RQ worker for production deployment."""

import os
import sys
import asyncio
import logging
import signal
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import redis
from rq import Worker, Queue, Connection

from config.settings import settings, validate_settings
from utils.redis_cache import init_redis_cache
from database import init_database, get_database_config
from database.repositories.base import init_repositories

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/app/logs/worker.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)


class FaceitWorker(Worker):
    """Custom RQ Worker with async initialization."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initialized = False
    
    def perform_job(self, job, queue):
        """Perform job with async initialization."""
        if not self._initialized:
            asyncio.run(self._init_async())
            self._initialized = True
        
        return super().perform_job(job, queue)
    
    async def _init_async(self):
        """Initialize async dependencies."""
        try:
            # Initialize Redis cache
            await init_redis_cache(settings.redis_url)
            
            # Initialize database
            db_config = get_database_config()
            await init_database(db_config)
            await init_repositories()
            
            logger.info("Worker async initialization completed")
        except Exception as e:
            logger.error(f"Failed to initialize worker: {e}")
            raise


def get_redis_connection():
    """Get Redis connection."""
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=10,
        socket_timeout=10,
        retry_on_timeout=True
    )


def get_queues(connection, worker_type='all'):
    """Get queues based on worker type."""
    queue_mapping = {
        'critical': ['faceit_bot_critical'],
        'high': ['faceit_bot_high'],
        'default': ['faceit_bot_default'],
        'low': ['faceit_bot_low'],
        'priority': ['faceit_bot_critical', 'faceit_bot_high'],
        'bulk': ['faceit_bot_default', 'faceit_bot_low'],
        'all': ['faceit_bot_critical', 'faceit_bot_high', 'faceit_bot_default', 'faceit_bot_low']
    }
    
    queue_names = queue_mapping.get(worker_type, queue_mapping['all'])
    return [Queue(name, connection=connection) for name in queue_names]


def main():
    """Main entry point."""
    # Validate settings
    try:
        validate_settings()
        logger.info("Settings validation passed")
    except Exception as e:
        logger.error(f"Settings validation failed: {e}")
        sys.exit(1)
    
    # Get worker configuration from environment
    worker_type = os.environ.get('WORKER_TYPE', 'all')
    worker_name = os.environ.get('WORKER_NAME', f'faceit-worker-{os.getpid()}')
    
    logger.info(f"Starting worker: {worker_name}")
    logger.info(f"Worker type: {worker_type}")
    logger.info(f"PID: {os.getpid()}")
    
    try:
        # Connect to Redis
        connection = get_redis_connection()
        connection.ping()  # Test connection
        logger.info("Connected to Redis successfully")
        
        # Get queues
        queues = get_queues(connection, worker_type)
        queue_names = [q.name for q in queues]
        logger.info(f"Listening on queues: {queue_names}")
        
        # Create worker
        worker = FaceitWorker(
            queues,
            name=worker_name,
            connection=connection
        )
        
        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            worker.request_stop()
            sys.exit(0)
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        # Start worker
        logger.info("Starting worker, waiting for jobs...")
        worker.work(
            burst=False,
            logging_level=logging.INFO
        )
        
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker error: {e}")
        sys.exit(1)
    finally:
        logger.info("Worker shutdown complete")


if __name__ == '__main__':
    main()