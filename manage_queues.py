#!/usr/bin/env python3
"""Queue management utility script."""

import asyncio
import sys
import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.settings import settings, validate_settings
from queues.manager import QueueManager, get_queue_manager
from queues.config import QueuePriority
from queues.monitoring import QueueMonitor, get_queue_monitor, AlertLevel


class QueueManagementCLI:
    """Command-line interface for queue management."""
    
    def __init__(self):
        self.queue_manager: Optional[QueueManager] = None
        self.queue_monitor: Optional[QueueMonitor] = None
    
    async def initialize(self):
        """Initialize managers."""
        validate_settings()
        
        self.queue_manager = get_queue_manager()
        await self.queue_manager.initialize()
        
        if settings.queue_enable_monitoring:
            self.queue_monitor = get_queue_monitor()
            await self.queue_monitor.initialize()
    
    async def cleanup(self):
        """Cleanup resources."""
        if self.queue_monitor:
            await self.queue_monitor.cleanup()
        if self.queue_manager:
            await self.queue_manager.cleanup()
    
    async def show_detailed_status(self):
        """Show detailed queue status."""
        stats = self.queue_manager.get_queue_stats()
        
        print("=" * 60)
        print("🚀 FACEIT BOT QUEUE SYSTEM STATUS")
        print("=" * 60)
        print(f"📅 Timestamp: {stats['timestamp']}")
        print(f"👥 Active Workers: {stats['workers']}")
        print(f"📊 Total Jobs: {stats['total_jobs']}")
        print(f"   ⏳ Queued: {stats['queued_jobs']}")
        print(f"   🔄 Started: {stats['started_jobs']}")
        print(f"   ✅ Finished: {stats['finished_jobs']}")
        print(f"   ❌ Failed: {stats['failed_jobs']}")
        print()
        
        # Individual queue details
        print("📋 QUEUE DETAILS:")
        for queue_name, queue_stats in stats['queues'].items():
            if 'error' in queue_stats:
                print(f"   ❌ {queue_name}: ERROR - {queue_stats['error']}")
                continue
            
            print(f"   📦 {queue_name.upper()} QUEUE:")
            print(f"      Queued: {queue_stats['queued']}")
            print(f"      Started: {queue_stats['started']}")
            print(f"      Finished: {queue_stats['finished']}")
            print(f"      Failed: {queue_stats['failed']}")
            
            # Calculate success rate
            total = queue_stats['finished'] + queue_stats['failed']
            if total > 0:
                success_rate = (queue_stats['finished'] / total) * 100
                print(f"      Success Rate: {success_rate:.1f}%")
            print()
        
        # Health information
        if self.queue_monitor:
            health = self.queue_monitor.get_system_health_summary()
            print("🏥 SYSTEM HEALTH:")
            print(f"   Status: {health['status'].upper()}")
            print(f"   Health Score: {health['health_score']}/100")
            print(f"   Total Alerts: {health['alerts']['total']}")
            if health['alerts']['critical'] > 0:
                print(f"   ⚠️  Critical Alerts: {health['alerts']['critical']}")
            if health['alerts']['error'] > 0:
                print(f"   🔴 Error Alerts: {health['alerts']['error']}")
            if health['alerts']['warning'] > 0:
                print(f"   🟡 Warning Alerts: {health['alerts']['warning']}")
            print()
    
    async def show_recent_alerts(self, hours: int = 24):
        """Show recent alerts."""
        if not self.queue_monitor:
            print("❌ Monitoring not enabled")
            return
        
        alerts = self.queue_monitor.get_recent_alerts(hours)
        
        print(f"🚨 RECENT ALERTS (Last {hours} hours)")
        print("=" * 50)
        
        if not alerts:
            print("✅ No alerts in the specified time period")
            return
        
        for alert in alerts[:20]:  # Show last 20 alerts
            level_emoji = {
                AlertLevel.INFO: "ℹ️",
                AlertLevel.WARNING: "⚠️",
                AlertLevel.ERROR: "🔴",
                AlertLevel.CRITICAL: "💥"
            }
            
            print(f"{level_emoji.get(alert.level, '❓')} [{alert.level.value.upper()}] "
                  f"{alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   {alert.message}")
            if alert.queue_name:
                print(f"   Queue: {alert.queue_name}")
            if alert.details:
                print(f"   Details: {json.dumps(alert.details, indent=2)}")
            print()
    
    async def test_job_submission(self):
        """Test job submission to all queues."""
        print("🧪 TESTING JOB SUBMISSION")
        print("=" * 30)
        
        # Test job for each priority
        test_jobs = []
        
        for priority in QueuePriority:
            try:
                # Create a simple test job
                from queues.jobs import update_player_cache_job
                
                job = self.queue_manager.enqueue_job(
                    update_player_cache_job,
                    priority=priority,
                    job_id=f"test_job_{priority.value}_{datetime.now().timestamp()}",
                    timeout=60,
                    cache_type="test",
                    identifiers=["test_player"]
                )
                
                test_jobs.append((priority, job))
                print(f"✅ Submitted test job to {priority.value} queue: {job.id}")
                
            except Exception as e:
                print(f"❌ Failed to submit test job to {priority.value} queue: {e}")
        
        # Wait a bit and check results
        print("\n⏳ Waiting for jobs to process...")
        await asyncio.sleep(5)
        
        print("\n📋 TEST RESULTS:")
        for priority, job in test_jobs:
            try:
                job.refresh()
                status = job.get_status()
                print(f"   {priority.value} queue: {status}")
                
                if status == 'finished':
                    print(f"      Result: {job.result}")
                elif status == 'failed':
                    print(f"      Error: {job.exc_info}")
                    
            except Exception as e:
                print(f"   {priority.value} queue: Error checking status - {e}")
    
    async def generate_monitoring_report(self, hours: int = 24, output_file: Optional[str] = None):
        """Generate comprehensive monitoring report."""
        if not self.queue_monitor:
            print("❌ Monitoring not enabled")
            return
        
        report = await self.queue_monitor.generate_monitoring_report(hours)
        
        if output_file:
            # Save to file
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            print(f"📝 Report saved to {output_file}")
        else:
            # Print to console
            print(json.dumps(report, indent=2, default=str))
    
    async def requeue_failed_jobs(self, queues: Optional[List[str]] = None):
        """Requeue failed jobs."""
        if queues:
            # Requeue specific queues
            total_requeued = 0
            for queue_name in queues:
                try:
                    priority = QueuePriority(queue_name)
                    count = self.queue_manager.requeue_failed_jobs(priority)
                    total_requeued += count
                    print(f"✅ Requeued {count} failed jobs from {queue_name} queue")
                except ValueError:
                    print(f"❌ Invalid queue name: {queue_name}")
            
            print(f"🔄 Total requeued jobs: {total_requeued}")
        else:
            # Requeue all failed jobs
            total_requeued = 0
            for priority in QueuePriority:
                count = self.queue_manager.requeue_failed_jobs(priority)
                total_requeued += count
                if count > 0:
                    print(f"✅ Requeued {count} failed jobs from {priority.value} queue")
            
            print(f"🔄 Total requeued jobs: {total_requeued}")
    
    async def clear_queues(self, queues: Optional[List[str]] = None, confirm: bool = False):
        """Clear queues with confirmation."""
        if not confirm:
            print("⚠️  This will permanently delete all jobs in the specified queues.")
            response = input("Are you sure? Type 'yes' to continue: ")
            if response.lower() != 'yes':
                print("❌ Operation cancelled")
                return
        
        if queues:
            # Clear specific queues
            total_cleared = 0
            for queue_name in queues:
                try:
                    priority = QueuePriority(queue_name)
                    count = self.queue_manager.clear_queue(priority)
                    total_cleared += count
                    print(f"🗑️  Cleared {count} jobs from {queue_name} queue")
                except ValueError:
                    print(f"❌ Invalid queue name: {queue_name}")
            
            print(f"🧹 Total cleared jobs: {total_cleared}")
        else:
            # Clear all queues
            total_cleared = self.queue_manager.clear_all_queues()
            print(f"🧹 Cleared {total_cleared} jobs from all queues")
    
    async def show_job_details(self, job_id: str):
        """Show detailed job information."""
        job = self.queue_manager.get_job(job_id)
        
        if not job:
            print(f"❌ Job {job_id} not found")
            return
        
        print(f"🔍 JOB DETAILS: {job_id}")
        print("=" * 50)
        print(f"Status: {job.get_status()}")
        print(f"Function: {job.func_name}")
        print(f"Queue: {job.origin}")
        print(f"Created: {job.created_at}")
        print(f"Enqueued: {job.enqueued_at}")
        print(f"Started: {job.started_at}")
        print(f"Ended: {job.ended_at}")
        print(f"Timeout: {job.timeout}")
        print(f"Retries: {job.retries_left if hasattr(job, 'retries_left') else 'N/A'}")
        
        if job.args:
            print(f"Arguments: {job.args}")
        if job.kwargs:
            print(f"Keyword Arguments: {job.kwargs}")
        
        if job.result:
            print("Result:")
            print(json.dumps(job.result, indent=2, default=str))
        
        if job.exc_info:
            print("Error Information:")
            print(job.exc_info)


async def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(description="FACEIT Bot Queue Management")
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show queue status')
    
    # Alerts command
    alerts_parser = subparsers.add_parser('alerts', help='Show recent alerts')
    alerts_parser.add_argument('--hours', type=int, default=24, help='Hours to look back')
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Test job submission')
    
    # Report command
    report_parser = subparsers.add_parser('report', help='Generate monitoring report')
    report_parser.add_argument('--hours', type=int, default=24, help='Hours to include in report')
    report_parser.add_argument('--output', '-o', help='Output file (JSON format)')
    
    # Requeue command
    requeue_parser = subparsers.add_parser('requeue', help='Requeue failed jobs')
    requeue_parser.add_argument('queues', nargs='*', choices=[p.value for p in QueuePriority],
                                help='Specific queues to requeue (default: all)')
    
    # Clear command
    clear_parser = subparsers.add_parser('clear', help='Clear queues')
    clear_parser.add_argument('queues', nargs='*', choices=[p.value for p in QueuePriority],
                              help='Specific queues to clear (default: all)')
    clear_parser.add_argument('--yes', action='store_true', help='Skip confirmation')
    
    # Job details command
    job_parser = subparsers.add_parser('job', help='Show job details')
    job_parser.add_argument('job_id', help='Job ID to inspect')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    cli = QueueManagementCLI()
    
    try:
        await cli.initialize()
        
        if args.command == 'status':
            await cli.show_detailed_status()
        elif args.command == 'alerts':
            await cli.show_recent_alerts(args.hours)
        elif args.command == 'test':
            await cli.test_job_submission()
        elif args.command == 'report':
            await cli.generate_monitoring_report(args.hours, args.output)
        elif args.command == 'requeue':
            await cli.requeue_failed_jobs(args.queues)
        elif args.command == 'clear':
            await cli.clear_queues(args.queues, args.yes)
        elif args.command == 'job':
            await cli.show_job_details(args.job_id)
    
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    
    finally:
        await cli.cleanup()


if __name__ == '__main__':
    asyncio.run(main())