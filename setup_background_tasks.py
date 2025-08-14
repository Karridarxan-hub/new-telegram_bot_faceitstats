"""Setup script for background task system.

This script configures and initializes the background task system for the
FACEIT Telegram bot, setting up Redis queues, workers, and scheduled tasks.

Usage:
    python setup_background_tasks.py --mode [setup|worker|scheduler|status]
"""

import argparse
import asyncio
import logging
import sys
import time
from typing import List
import signal
import os

# Setup path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings
from queues.task_manager import TaskManager, TaskPriority, get_task_manager
from queues.service_integration import setup_background_monitoring, start_task_scheduler

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BackgroundTaskSetup:
    """Setup and management for background task system."""
    
    def __init__(self):
        self.task_manager = get_task_manager()
        self.workers = []
        self.running = True
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False
        
        # Stop all workers
        for worker in self.workers:
            try:
                worker.request_stop()
            except Exception as e:
                logger.error(f"Error stopping worker: {e}")
        
        sys.exit(0)
    
    def setup_system(self):
        """Setup the background task system."""
        logger.info("Setting up background task system...")
        
        try:
            # Test Redis connection
            logger.info("Testing Redis connection...")
            health = self.task_manager.health_check()
            
            if health.get("redis_connection") != "healthy":
                logger.error(f"Redis connection failed: {health.get('redis_error')}")
                return False
            
            logger.info("✅ Redis connection successful")
            
            # Setup scheduled tasks
            logger.info("Setting up scheduled background tasks...")
            setup_background_monitoring()
            
            scheduled_tasks = self.task_manager.get_scheduled_tasks()
            logger.info(f"✅ Scheduled {len(scheduled_tasks)} recurring tasks:")
            
            for task_id, task_info in scheduled_tasks.items():
                logger.info(f"  - {task_info['task_name']} (every {task_info['interval_minutes']} minutes)")
            
            # Test task enqueueing
            logger.info("Testing task enqueueing...")
            test_task_id = self.task_manager.enqueue_cache_warming("popular_data", None, False)
            logger.info(f"✅ Test task enqueued with ID: {test_task_id}")
            
            # Display queue statistics
            self._display_queue_stats()
            
            logger.info("🚀 Background task system setup complete!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Setup failed: {e}")
            return False
    
    def start_workers(self, worker_count: int = None):
        """Start RQ workers for processing tasks."""
        if worker_count is None:
            worker_count = getattr(settings, 'background_worker_count', 4)
        
        logger.info(f"Starting {worker_count} background workers...")
        
        try:
            from rq import Worker
            
            # Create workers for different queue priorities
            queue_configs = [
                # Critical tasks - 1 dedicated worker
                {
                    "queues": [self.task_manager.queues[TaskPriority.CRITICAL]],
                    "name": "critical_worker",
                    "count": 1
                },
                # High priority tasks - 2 workers
                {
                    "queues": [
                        self.task_manager.queues[TaskPriority.HIGH],
                        self.task_manager.queues[TaskPriority.CRITICAL]
                    ],
                    "name": "high_priority_worker",
                    "count": min(2, worker_count)
                },
                # Default and low priority tasks - remaining workers
                {
                    "queues": [
                        self.task_manager.queues[TaskPriority.DEFAULT],
                        self.task_manager.queues[TaskPriority.LOW],
                        self.task_manager.queues[TaskPriority.HIGH]
                    ],
                    "name": "general_worker",
                    "count": max(1, worker_count - 3)
                }
            ]
            
            for config in queue_configs:
                for i in range(config["count"]):
                    worker_name = f"{config['name']}_{i+1}"
                    worker = Worker(
                        config["queues"],
                        connection=self.task_manager.redis,
                        name=worker_name
                    )
                    
                    self.workers.append(worker)
                    logger.info(f"✅ Created worker: {worker_name}")
            
            # Start workers in separate threads/processes
            logger.info("Starting worker processes...")
            
            if len(self.workers) == 1:
                # Single worker - run directly
                worker = self.workers[0]
                logger.info(f"Starting single worker: {worker.name}")
                worker.work(with_scheduler=True)
            else:
                # Multiple workers - use multiprocessing
                import multiprocessing as mp
                
                def run_worker(worker_config, worker_index):
                    """Run a worker in a separate process."""
                    try:
                        worker_name = f"{worker_config['name']}_{worker_index + 1}"
                        worker = Worker(
                            [self.task_manager.queues[p] for p in worker_config.get('priorities', [TaskPriority.DEFAULT])],
                            connection=self.task_manager.redis,
                            name=worker_name
                        )
                        
                        logger.info(f"Worker {worker_name} starting...")
                        worker.work()
                        
                    except Exception as e:
                        logger.error(f"Worker {worker_name} failed: {e}")
                
                # Start worker processes
                processes = []
                worker_idx = 0
                
                for config in queue_configs:
                    for i in range(config["count"]):
                        process = mp.Process(
                            target=run_worker,
                            args=(config, i),
                            name=f"worker_{worker_idx}"
                        )
                        process.start()
                        processes.append(process)
                        worker_idx += 1
                
                logger.info(f"✅ Started {len(processes)} worker processes")
                
                # Wait for processes
                try:
                    for process in processes:
                        process.join()
                except KeyboardInterrupt:
                    logger.info("Terminating worker processes...")
                    for process in processes:
                        process.terminate()
                        process.join(timeout=5)
                        if process.is_alive():
                            process.kill()
            
        except Exception as e:
            logger.error(f"❌ Failed to start workers: {e}")
            return False
    
    def start_scheduler(self):
        """Start the task scheduler for recurring tasks."""
        logger.info("Starting task scheduler...")
        
        try:
            # Run the scheduler
            asyncio.run(start_task_scheduler())
            
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
        except Exception as e:
            logger.error(f"❌ Scheduler failed: {e}")
    
    def show_status(self):
        """Display current system status."""
        logger.info("📊 Background Task System Status")
        logger.info("=" * 50)
        
        try:
            # Health check
            health = self.task_manager.health_check()
            logger.info(f"Redis Connection: {health.get('redis_connection', 'unknown')}")
            logger.info(f"Active Tasks: {health.get('active_tasks', 0)}")
            logger.info(f"Scheduled Tasks: {health.get('scheduled_tasks', 0)}")
            
            # Queue statistics
            self._display_queue_stats()
            
            # System metrics
            metrics = self.task_manager.get_system_metrics()
            if "error" not in metrics:
                job_stats = metrics.get("job_statistics", {})
                logger.info(f"\n📈 Job Statistics:")
                logger.info(f"  Total Jobs: {job_stats.get('total_jobs', 0)}")
                logger.info(f"  Success Rate: {job_stats.get('success_rate', 0)}%")
                logger.info(f"  Queued: {job_stats.get('total_queued', 0)}")
                logger.info(f"  Running: {job_stats.get('total_started', 0)}")
                logger.info(f"  Finished: {job_stats.get('total_finished', 0)}")
                logger.info(f"  Failed: {job_stats.get('total_failed', 0)}")
                
                # Redis metrics
                redis_metrics = metrics.get("redis_metrics", {})
                logger.info(f"\n🔧 Redis Metrics:")
                logger.info(f"  Memory Usage: {redis_metrics.get('used_memory_human', 'N/A')}")
                logger.info(f"  Connected Clients: {redis_metrics.get('connected_clients', 0)}")
                logger.info(f"  Commands Processed: {redis_metrics.get('total_commands_processed', 0)}")
            
            # Scheduled tasks
            scheduled = self.task_manager.get_scheduled_tasks()
            if scheduled:
                logger.info(f"\n⏰ Scheduled Tasks ({len(scheduled)}):")
                for task_id, task_info in scheduled.items():
                    status = "✅ Enabled" if task_info["enabled"] else "❌ Disabled"
                    logger.info(f"  - {task_info['task_name']}: {status}")
                    logger.info(f"    Interval: {task_info['interval_minutes']} minutes")
                    logger.info(f"    Next Run: {task_info.get('next_run', 'N/A')}")
                    logger.info(f"    Run Count: {task_info.get('run_count', 0)}")
            
        except Exception as e:
            logger.error(f"❌ Failed to get status: {e}")
    
    def _display_queue_stats(self):
        """Display queue statistics."""
        try:
            queue_stats = self.task_manager.get_queue_stats()
            logger.info(f"\n🔄 Queue Statistics:")
            
            for queue_name, stats in queue_stats.items():
                if "error" in stats:
                    logger.error(f"  {queue_name}: Error - {stats['error']}")
                else:
                    logger.info(f"  {queue_name}:")
                    logger.info(f"    Queued: {stats.get('queued_jobs', 0)}")
                    logger.info(f"    Running: {stats.get('started_jobs', 0)}")
                    logger.info(f"    Finished: {stats.get('finished_jobs', 0)}")
                    logger.info(f"    Failed: {stats.get('failed_jobs', 0)}")
        
        except Exception as e:
            logger.error(f"Error getting queue stats: {e}")
    
    def cleanup_system(self):
        """Clean up old tasks and optimize the system."""
        logger.info("🧹 Cleaning up background task system...")
        
        try:
            # Clean up finished tasks older than 48 hours
            cleaned_count = self.task_manager.cleanup_finished_tasks(48)
            logger.info(f"✅ Cleaned up {cleaned_count} old finished tasks")
            
            # Enqueue cache cleanup
            cache_cleanup_id = self.task_manager.enqueue_cache_cleanup("expired", 2000, False)
            logger.info(f"✅ Enqueued cache cleanup task: {cache_cleanup_id}")
            
            # Enqueue cache optimization
            cache_opt_id = self.task_manager.enqueue_cache_optimization("memory", 50)
            logger.info(f"✅ Enqueued cache optimization task: {cache_opt_id}")
            
            logger.info("🚀 Cleanup tasks completed!")
            
        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Background Task System Setup")
    parser.add_argument(
        "mode",
        choices=["setup", "worker", "scheduler", "status", "cleanup"],
        help="Operation mode"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of worker processes (default: 4)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    setup = BackgroundTaskSetup()
    
    try:
        if args.mode == "setup":
            logger.info("🔧 Setting up background task system...")
            success = setup.setup_system()
            sys.exit(0 if success else 1)
            
        elif args.mode == "worker":
            logger.info("👷 Starting background workers...")
            setup.start_workers(args.workers)
            
        elif args.mode == "scheduler":
            logger.info("⏰ Starting task scheduler...")
            setup.start_scheduler()
            
        elif args.mode == "status":
            logger.info("📊 Displaying system status...")
            setup.show_status()
            
        elif args.mode == "cleanup":
            logger.info("🧹 Running system cleanup...")
            setup.cleanup_system()
    
    except KeyboardInterrupt:
        logger.info("\n👋 Shutdown requested by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Operation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()