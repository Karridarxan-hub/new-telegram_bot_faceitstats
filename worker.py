#!/usr/bin/env python3
"""Worker script for running RQ background workers."""

import asyncio
import logging
import signal
import sys
import argparse
from typing import List, Optional
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.settings import settings, validate_settings
from queues.manager import QueueManager, get_queue_manager
from queues.config import QueuePriority, get_queue_config
from queues.monitoring import QueueMonitor, get_queue_monitor

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('worker.log')
    ]
)

logger = logging.getLogger(__name__)


class WorkerManager:
    """Manager for RQ workers."""
    
    def __init__(self):
        self.queue_manager: Optional[QueueManager] = None
        self.queue_monitor: Optional[QueueMonitor] = None
        self.workers = []
        self.running = False
        self.shutdown_event = asyncio.Event()
        
    async def initialize(self):
        """Initialize worker manager."""
        try:
            # Validate settings
            validate_settings()
            
            # Initialize queue manager
            self.queue_manager = get_queue_manager()
            await self.queue_manager.initialize()
            
            # Initialize monitoring if enabled
            if settings.queue_enable_monitoring:
                self.queue_monitor = get_queue_monitor()
                await self.queue_monitor.initialize()
                await self.queue_monitor.start_monitoring()
            
            logger.info("Worker manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize worker manager: {e}")
            raise
    
    async def start_workers(
        self,
        num_workers: Optional[int] = None,
        queues: Optional[List[QueuePriority]] = None,
        worker_names: Optional[List[str]] = None
    ):
        """Start worker processes."""
        if not self.queue_manager:
            raise RuntimeError("Queue manager not initialized")
        
        if num_workers is None:
            num_workers = settings.queue_max_workers
        
        if queues is None:
            queues = list(QueuePriority)
        
        logger.info(f"Starting {num_workers} workers for queues: {[q.value for q in queues]}")
        
        # Create and start workers
        for i in range(num_workers):
            worker_name = worker_names[i] if worker_names and i < len(worker_names) else f"worker_{i}"
            
            try:
                worker = self.queue_manager.create_worker(worker_name, queues)
                self.workers.append(worker)
                
                # Start worker in background task
                task = asyncio.create_task(
                    self._run_worker(worker, worker_name),
                    name=f"worker_task_{worker_name}"
                )
                
                logger.info(f"Started worker: {worker_name}")
                
            except Exception as e:
                logger.error(f"Failed to start worker {worker_name}: {e}")
        
        self.running = True
        logger.info(f"Successfully started {len(self.workers)} workers")
    
    async def _run_worker(self, worker, worker_name: str):
        """Run a single worker."""
        try:
            while self.running and not self.shutdown_event.is_set():
                try:
                    # Work with burst to handle graceful shutdown
                    await asyncio.get_event_loop().run_in_executor(
                        None, 
                        worker.work,
                        settings.queue_burst_timeout
                    )
                    
                    # Short break between bursts
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Worker {worker_name} encountered error: {e}")
                    await asyncio.sleep(5)  # Wait before retrying
                    
        except asyncio.CancelledError:
            logger.info(f"Worker {worker_name} cancelled")
        except Exception as e:
            logger.error(f"Unexpected error in worker {worker_name}: {e}")
        finally:
            logger.info(f"Worker {worker_name} stopped")
    
    async def stop_workers(self):
        """Stop all workers gracefully."""
        if not self.running:
            return
        
        logger.info("Stopping workers...")
        self.running = False
        self.shutdown_event.set()
        
        # Request stop for all workers
        for worker in self.workers:
            try:
                worker.request_stop()
            except Exception as e:
                logger.error(f"Error stopping worker {worker.name}: {e}")
        
        # Cancel all worker tasks
        worker_tasks = [task for task in asyncio.all_tasks() if task.get_name().startswith("worker_task_")]
        if worker_tasks:
            logger.info(f"Cancelling {len(worker_tasks)} worker tasks")
            for task in worker_tasks:
                task.cancel()
            
            # Wait for tasks to complete
            try:
                await asyncio.wait_for(
                    asyncio.gather(*worker_tasks, return_exceptions=True),
                    timeout=30
                )
            except asyncio.TimeoutError:
                logger.warning("Worker tasks did not complete within timeout")
        
        self.workers.clear()
        logger.info("All workers stopped")
    
    async def cleanup(self):
        """Cleanup resources."""
        try:
            await self.stop_workers()
            
            if self.queue_monitor:
                await self.queue_monitor.cleanup()
            
            if self.queue_manager:
                await self.queue_manager.cleanup()
                
            logger.info("Worker manager cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def get_status(self) -> dict:
        """Get worker status."""
        return {
            "running": self.running,
            "num_workers": len(self.workers),
            "workers": [
                {
                    "name": worker.name,
                    "state": worker.state,
                    "current_job": worker.get_current_job_id() if hasattr(worker, 'get_current_job_id') else None
                }
                for worker in self.workers
            ],
            "queue_manager_initialized": self.queue_manager is not None,
            "monitor_enabled": self.queue_monitor is not None
        }


async def run_worker_daemon(args):
    """Run worker daemon."""
    worker_manager = WorkerManager()
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        asyncio.create_task(shutdown_handler())
    
    async def shutdown_handler():
        await worker_manager.cleanup()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Initialize
        await worker_manager.initialize()
        
        # Parse queue priorities
        queues = []
        if args.queues:
            for queue_name in args.queues:
                try:
                    priority = QueuePriority(queue_name)
                    queues.append(priority)
                except ValueError:
                    logger.error(f"Invalid queue name: {queue_name}")
                    sys.exit(1)
        
        # Start workers
        await worker_manager.start_workers(
            num_workers=args.workers,
            queues=queues or None,
            worker_names=args.names
        )
        
        # Keep running until shutdown
        logger.info("Workers started. Press Ctrl+C to stop.")
        while worker_manager.running:
            await asyncio.sleep(1)
            
            # Print status periodically
            if args.verbose:
                status = worker_manager.get_status()
                logger.info(f"Status: {len(status['workers'])} workers running")
    
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Worker daemon error: {e}")
        raise
    finally:
        await worker_manager.cleanup()


async def show_status():
    """Show queue and worker status."""
    try:
        queue_manager = get_queue_manager()
        await queue_manager.initialize()
        
        # Get queue stats
        stats = queue_manager.get_queue_stats()
        
        print("\n=== FACEIT Bot Queue Status ===")
        print(f"Timestamp: {stats['timestamp']}")
        print(f"Total Jobs: {stats['total_jobs']}")
        print(f"Active Workers: {stats['workers']}")
        print()
        
        # Queue details
        for queue_name, queue_stats in stats['queues'].items():
            if 'error' in queue_stats:
                print(f"❌ {queue_name}: Error - {queue_stats['error']}")
                continue
                
            print(f"📋 {queue_name}:")
            print(f"   Queued: {queue_stats['queued']}")
            print(f"   Started: {queue_stats['started']}")
            print(f"   Finished: {queue_stats['finished']}")
            print(f"   Failed: {queue_stats['failed']}")
            print()
        
        # Monitoring status
        if settings.queue_enable_monitoring:
            monitor = get_queue_monitor()
            await monitor.initialize()
            
            health = monitor.get_system_health_summary()
            print(f"🏥 System Health: {health['status'].upper()} (Score: {health['health_score']}/100)")
            print(f"   Alerts: {health['alerts']['total']} total ({health['alerts']['critical']} critical)")
            print()
        
        await queue_manager.cleanup()
        
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        sys.exit(1)


async def clear_queues(queue_names: Optional[List[str]] = None):
    """Clear specified queues or all queues."""
    try:
        queue_manager = get_queue_manager()
        await queue_manager.initialize()
        
        if queue_names:
            total_cleared = 0
            for queue_name in queue_names:
                try:
                    priority = QueuePriority(queue_name)
                    cleared = queue_manager.clear_queue(priority)
                    total_cleared += cleared
                    print(f"Cleared {cleared} jobs from {queue_name} queue")
                except ValueError:
                    print(f"Invalid queue name: {queue_name}")
        else:
            total_cleared = queue_manager.clear_all_queues()
            print(f"Cleared {total_cleared} jobs from all queues")
        
        await queue_manager.cleanup()
        
    except Exception as e:
        logger.error(f"Error clearing queues: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="FACEIT Bot Queue Worker")
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Worker command
    worker_parser = subparsers.add_parser('work', help='Start workers')
    worker_parser.add_argument('--workers', '-w', type=int, default=None,
                               help=f'Number of workers (default: {settings.queue_max_workers})')
    worker_parser.add_argument('--queues', '-q', nargs='+', 
                               choices=[p.value for p in QueuePriority],
                               help='Queues to process (default: all)')
    worker_parser.add_argument('--names', '-n', nargs='+',
                               help='Worker names')
    worker_parser.add_argument('--verbose', '-v', action='store_true',
                               help='Verbose logging')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show queue status')
    
    # Clear command
    clear_parser = subparsers.add_parser('clear', help='Clear queues')
    clear_parser.add_argument('queues', nargs='*', 
                              choices=[p.value for p in QueuePriority],
                              help='Queues to clear (default: all)')
    
    args = parser.parse_args()
    
    if args.command == 'work':
        asyncio.run(run_worker_daemon(args))
    elif args.command == 'status':
        asyncio.run(show_status())
    elif args.command == 'clear':
        asyncio.run(clear_queues(args.queues if args.queues else None))
    else:
        parser.print_help()


if __name__ == '__main__':
    main()