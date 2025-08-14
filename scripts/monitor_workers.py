#!/usr/bin/env python3
"""
Worker monitoring and metrics collection system for FACEIT Bot.
Provides real-time monitoring, alerting, and performance metrics.
"""

import asyncio
import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import argparse
from pathlib import Path
import subprocess
import aiohttp
import psutil

# Add project root to path
project_root = Path(__file__).parent.parent
import sys
sys.path.insert(0, str(project_root))

from config.settings import settings
from queues.task_manager import get_task_manager
from utils.redis_cache import get_redis_cache

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('monitor.log')
    ]
)

logger = logging.getLogger(__name__)


class WorkerMonitor:
    """Worker monitoring and metrics system."""
    
    def __init__(self):
        self.task_manager = None
        self.redis_cache = None
        self.running = False
        self.metrics_history = []
        self.alert_thresholds = {
            "queue_depth": 100,
            "failed_jobs": 10,
            "worker_down_time": 300,  # 5 minutes
            "memory_usage": 85,  # percentage
            "cpu_usage": 90,  # percentage
            "redis_memory": 80,  # percentage
        }
        
    async def initialize(self):
        """Initialize monitoring system."""
        try:
            self.task_manager = get_task_manager()
            await self.task_manager.initialize()
            
            self.redis_cache = get_redis_cache()
            if not self.redis_cache.client:
                await self.redis_cache.connect()
            
            logger.info("Worker monitor initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize monitor: {e}")
            return False
    
    def get_docker_container_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get Docker container statistics."""
        try:
            result = subprocess.run([
                "docker", "stats", "--no-stream", "--format",
                "table {{.Container}}\\t{{.CPUPerc}}\\t{{.MemPerc}}\\t{{.MemUsage}}\\t{{.NetIO}}\\t{{.BlockIO}}"
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"Failed to get Docker stats: {result.stderr}")
                return {}
            
            stats = {}
            lines = result.stdout.strip().split('\\n')[1:]  # Skip header
            
            for line in lines:
                if not line.strip():
                    continue
                    
                parts = line.split()
                if len(parts) >= 6:
                    container = parts[0]
                    cpu_percent = float(parts[1].replace('%', ''))
                    mem_percent = float(parts[2].replace('%', ''))
                    mem_usage = parts[3]
                    net_io = parts[4]
                    block_io = parts[5]
                    
                    # Filter FACEIT bot containers
                    if 'faceit' in container.lower():
                        stats[container] = {
                            'cpu_percent': cpu_percent,
                            'memory_percent': mem_percent,
                            'memory_usage': mem_usage,
                            'network_io': net_io,
                            'block_io': block_io,
                            'timestamp': datetime.now().isoformat()
                        }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting Docker container stats: {e}")
            return {}
    
    async def get_redis_metrics(self) -> Dict[str, Any]:
        """Get Redis server metrics."""
        try:
            if not self.redis_cache or not self.redis_cache.client:
                return {"error": "Redis not connected"}
            
            info = await self.redis_cache.client.info()
            
            return {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "used_memory_peak": info.get("used_memory_peak", 0),
                "used_memory_peak_human": info.get("used_memory_peak_human", "0B"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0),
                "redis_version": info.get("redis_version", "unknown"),
                "maxmemory": info.get("maxmemory", 0),
                "maxmemory_human": info.get("maxmemory_human", "0B"),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting Redis metrics: {e}")
            return {"error": str(e)}
    
    async def get_queue_metrics(self) -> Dict[str, Any]:
        """Get detailed queue metrics."""
        try:
            stats = self.task_manager.get_queue_stats()
            health = self.task_manager.health_check()
            
            total_queued = total_running = total_finished = total_failed = 0
            queue_details = {}
            
            for queue_name, queue_stats in stats.items():
                if isinstance(queue_stats, dict) and "error" not in queue_stats:
                    queued = queue_stats.get("queued_jobs", 0)
                    running = queue_stats.get("started_jobs", 0)
                    finished = queue_stats.get("finished_jobs", 0)
                    failed = queue_stats.get("failed_jobs", 0)
                    
                    total_queued += queued
                    total_running += running
                    total_finished += finished
                    total_failed += failed
                    
                    queue_details[queue_name] = {
                        "queued": queued,
                        "running": running,
                        "finished": finished,
                        "failed": failed,
                        "throughput": queue_stats.get("jobs_per_minute", 0)
                    }
            
            return {
                "redis_status": health.get("redis_connection", "unknown"),
                "active_tasks": health.get("active_tasks", 0),
                "scheduled_tasks": health.get("scheduled_tasks", 0),
                "totals": {
                    "queued": total_queued,
                    "running": total_running,
                    "finished": total_finished,
                    "failed": total_failed,
                    "success_rate": round((total_finished / (total_finished + total_failed) * 100), 2) if (total_finished + total_failed) > 0 else 100
                },
                "queue_details": queue_details,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting queue metrics: {e}")
            return {"error": str(e)}
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Get system resource metrics."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                "cpu": {
                    "usage_percent": cpu_percent,
                    "count": psutil.cpu_count()
                },
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "used": memory.used,
                    "percent": memory.percent
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.percent
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            return {"error": str(e)}
    
    async def collect_metrics(self) -> Dict[str, Any]:
        """Collect all metrics."""
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "docker_containers": self.get_docker_container_stats(),
            "redis": await self.get_redis_metrics(),
            "queues": await self.get_queue_metrics(),
            "system": self.get_system_metrics()
        }
        
        # Add to history
        self.metrics_history.append(metrics)
        
        # Keep only last 100 metrics (about 50 minutes at 30s interval)
        if len(self.metrics_history) > 100:
            self.metrics_history = self.metrics_history[-100:]
        
        return metrics
    
    def check_alerts(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for alert conditions."""
        alerts = []
        
        try:
            # Check queue depth alerts
            queue_metrics = metrics.get("queues", {})
            if isinstance(queue_metrics, dict) and "totals" in queue_metrics:
                queued_jobs = queue_metrics["totals"].get("queued", 0)
                if queued_jobs > self.alert_thresholds["queue_depth"]:
                    alerts.append({
                        "type": "queue_depth",
                        "severity": "warning",
                        "message": f"High queue depth: {queued_jobs} jobs queued",
                        "value": queued_jobs,
                        "threshold": self.alert_thresholds["queue_depth"],
                        "timestamp": datetime.now().isoformat()
                    })
                
                # Check failed jobs
                failed_jobs = queue_metrics["totals"].get("failed", 0)
                if failed_jobs > self.alert_thresholds["failed_jobs"]:
                    alerts.append({
                        "type": "failed_jobs",
                        "severity": "error",
                        "message": f"High number of failed jobs: {failed_jobs}",
                        "value": failed_jobs,
                        "threshold": self.alert_thresholds["failed_jobs"],
                        "timestamp": datetime.now().isoformat()
                    })
            
            # Check container resource usage
            containers = metrics.get("docker_containers", {})
            for container_name, container_stats in containers.items():
                if isinstance(container_stats, dict):
                    # Memory alerts
                    mem_percent = container_stats.get("memory_percent", 0)
                    if mem_percent > self.alert_thresholds["memory_usage"]:
                        alerts.append({
                            "type": "high_memory",
                            "severity": "warning",
                            "message": f"High memory usage in {container_name}: {mem_percent}%",
                            "container": container_name,
                            "value": mem_percent,
                            "threshold": self.alert_thresholds["memory_usage"],
                            "timestamp": datetime.now().isoformat()
                        })
                    
                    # CPU alerts
                    cpu_percent = container_stats.get("cpu_percent", 0)
                    if cpu_percent > self.alert_thresholds["cpu_usage"]:
                        alerts.append({
                            "type": "high_cpu",
                            "severity": "warning", 
                            "message": f"High CPU usage in {container_name}: {cpu_percent}%",
                            "container": container_name,
                            "value": cpu_percent,
                            "threshold": self.alert_thresholds["cpu_usage"],
                            "timestamp": datetime.now().isoformat()
                        })
            
            # Check Redis memory usage
            redis_metrics = metrics.get("redis", {})
            if isinstance(redis_metrics, dict) and "used_memory" in redis_metrics:
                max_memory = redis_metrics.get("maxmemory", 0)
                used_memory = redis_metrics.get("used_memory", 0)
                
                if max_memory > 0:
                    redis_mem_percent = (used_memory / max_memory) * 100
                    if redis_mem_percent > self.alert_thresholds["redis_memory"]:
                        alerts.append({
                            "type": "redis_memory",
                            "severity": "warning",
                            "message": f"High Redis memory usage: {redis_mem_percent:.1f}%",
                            "value": redis_mem_percent,
                            "threshold": self.alert_thresholds["redis_memory"],
                            "timestamp": datetime.now().isoformat()
                        })
        
        except Exception as e:
            logger.error(f"Error checking alerts: {e}")
        
        return alerts
    
    async def send_webhook_alert(self, alert: Dict[str, Any]) -> bool:
        """Send alert via webhook (if configured)."""
        webhook_url = getattr(settings, 'monitoring_webhook_url', None)
        
        if not webhook_url:
            return False
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "text": f"🚨 FACEIT Bot Alert: {alert['message']}",
                    "alert": alert
                }
                
                async with session.post(webhook_url, json=payload, timeout=10) as response:
                    if response.status == 200:
                        logger.info(f"Sent webhook alert: {alert['type']}")
                        return True
                    else:
                        logger.error(f"Webhook alert failed: {response.status}")
                        return False
        
        except Exception as e:
            logger.error(f"Error sending webhook alert: {e}")
            return False
    
    async def process_alerts(self, alerts: List[Dict[str, Any]]):
        """Process and handle alerts."""
        for alert in alerts:
            logger.warning(f"ALERT [{alert['type']}]: {alert['message']}")
            
            # Send webhook if configured
            await self.send_webhook_alert(alert)
    
    async def generate_report(self) -> Dict[str, Any]:
        """Generate monitoring report."""
        if not self.metrics_history:
            return {"error": "No metrics data available"}
        
        latest = self.metrics_history[-1]
        
        # Calculate trends if we have enough data
        trends = {}
        if len(self.metrics_history) >= 10:
            # Compare last 10 minutes with current
            old_metrics = self.metrics_history[-10]
            
            # Queue trends
            old_queued = old_metrics.get("queues", {}).get("totals", {}).get("queued", 0)
            current_queued = latest.get("queues", {}).get("totals", {}).get("queued", 0)
            trends["queue_trend"] = "up" if current_queued > old_queued else "down" if current_queued < old_queued else "stable"
            
            # Resource trends
            old_containers = old_metrics.get("docker_containers", {})
            current_containers = latest.get("docker_containers", {})
            
            cpu_trend = memory_trend = "stable"
            for container in current_containers:
                if container in old_containers:
                    old_cpu = old_containers[container].get("cpu_percent", 0)
                    current_cpu = current_containers[container].get("cpu_percent", 0)
                    if abs(current_cpu - old_cpu) > 10:
                        cpu_trend = "up" if current_cpu > old_cpu else "down"
            
            trends["cpu_trend"] = cpu_trend
            trends["memory_trend"] = memory_trend
        
        return {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_containers": len(latest.get("docker_containers", {})),
                "redis_status": latest.get("redis", {}).get("redis_version", "unknown"),
                "queue_health": latest.get("queues", {}).get("redis_status", "unknown"),
                "total_queued_jobs": latest.get("queues", {}).get("totals", {}).get("queued", 0),
                "total_running_jobs": latest.get("queues", {}).get("totals", {}).get("running", 0),
                "success_rate": latest.get("queues", {}).get("totals", {}).get("success_rate", 0)
            },
            "trends": trends,
            "alerts_summary": {
                "last_hour_alerts": len([m for m in self.metrics_history if "alerts" in m]),
                "types": list(set([a["type"] for m in self.metrics_history if "alerts" in m for a in m["alerts"]]))
            },
            "latest_metrics": latest
        }
    
    async def start_monitoring(self, interval: int = 30):
        """Start monitoring loop."""
        if not await self.initialize():
            logger.error("Failed to initialize monitoring")
            return
        
        self.running = True
        logger.info(f"Starting worker monitoring (interval: {interval}s)")
        
        try:
            while self.running:
                # Collect metrics
                metrics = await self.collect_metrics()
                
                # Check for alerts
                alerts = self.check_alerts(metrics)
                if alerts:
                    metrics["alerts"] = alerts
                    await self.process_alerts(alerts)
                
                # Log summary
                queue_metrics = metrics.get("queues", {})
                if isinstance(queue_metrics, dict) and "totals" in queue_metrics:
                    totals = queue_metrics["totals"]
                    logger.info(
                        f"Monitoring: {totals.get('queued', 0)} queued, "
                        f"{totals.get('running', 0)} running, "
                        f"{len(metrics.get('docker_containers', {}))} containers, "
                        f"{len(alerts)} alerts"
                    )
                
                await asyncio.sleep(interval)
                
        except KeyboardInterrupt:
            logger.info("Monitoring interrupted by user")
        except Exception as e:
            logger.error(f"Monitoring error: {e}")
        finally:
            self.running = False
            logger.info("Worker monitoring stopped")
    
    def stop(self):
        """Stop monitoring."""
        self.running = False


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="FACEIT Bot Worker Monitor")
    parser.add_argument("--interval", "-i", type=int, default=30, help="Monitoring interval in seconds")
    parser.add_argument("--report", "-r", action="store_true", help="Generate report and exit")
    parser.add_argument("--status", "-s", action="store_true", help="Show current status and exit")
    
    args = parser.parse_args()
    
    monitor = WorkerMonitor()
    
    if args.report:
        if await monitor.initialize():
            # Collect some metrics first
            for _ in range(3):
                await monitor.collect_metrics()
                await asyncio.sleep(1)
            
            report = await monitor.generate_report()
            print(json.dumps(report, indent=2))
        else:
            print("Failed to initialize monitor")
        return
    
    if args.status:
        if await monitor.initialize():
            metrics = await monitor.collect_metrics()
            print(json.dumps(metrics, indent=2))
        else:
            print("Failed to initialize monitor")
        return
    
    try:
        await monitor.start_monitoring(args.interval)
    except KeyboardInterrupt:
        logger.info("Shutting down monitor...")
        monitor.stop()


if __name__ == "__main__":
    asyncio.run(main())