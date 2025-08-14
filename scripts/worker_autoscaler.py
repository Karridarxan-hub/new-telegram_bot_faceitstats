#!/usr/bin/env python3
"""
Auto-scaling system for FACEIT Bot workers.
Monitors queue depth and automatically scales worker containers.
"""

import asyncio
import logging
import os
import subprocess
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import argparse
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
import sys
sys.path.insert(0, str(project_root))

from config.settings import settings
from queues.task_manager import get_task_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('autoscaler.log')
    ]
)

logger = logging.getLogger(__name__)


class WorkerAutoscaler:
    """Auto-scaling manager for worker containers."""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config = self._load_config(config_file)
        self.task_manager = None
        self.running = False
        self.last_scale_time = {}
        
    def _load_config(self, config_file: Optional[str] = None) -> Dict:
        """Load autoscaler configuration."""
        default_config = {
            "check_interval": 30,  # seconds
            "scaling_cooldown": 300,  # 5 minutes
            "docker_compose_file": "docker-compose.yml",
            "workers": {
                "worker-priority": {
                    "min_instances": 1,
                    "max_instances": 5,
                    "target_queue_length": 10,
                    "scale_up_threshold": 20,
                    "scale_down_threshold": 5,
                    "queues": ["faceit_bot_critical", "faceit_bot_high"],
                    "enabled": True
                },
                "worker-default": {
                    "min_instances": 1,
                    "max_instances": 3,
                    "target_queue_length": 15,
                    "scale_up_threshold": 30,
                    "scale_down_threshold": 5,
                    "queues": ["faceit_bot_default"],
                    "enabled": True
                },
                "worker-bulk": {
                    "min_instances": 1,
                    "max_instances": 2,
                    "target_queue_length": 20,
                    "scale_up_threshold": 40,
                    "scale_down_threshold": 10,
                    "queues": ["faceit_bot_low"],
                    "enabled": True
                }
            },
            "metrics": {
                "cpu_threshold": 80,  # CPU percentage
                "memory_threshold": 85,  # Memory percentage
                "enable_resource_scaling": True
            }
        }
        
        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    user_config = json.load(f)
                    default_config.update(user_config)
                logger.info(f"Loaded configuration from {config_file}")
            except Exception as e:
                logger.error(f"Failed to load config file: {e}")
        
        return default_config
    
    async def initialize(self):
        """Initialize the autoscaler."""
        try:
            self.task_manager = get_task_manager()
            await self.task_manager.initialize()
            
            # Initialize last scale times
            for worker_name in self.config["workers"].keys():
                self.last_scale_time[worker_name] = datetime.min
            
            logger.info("Worker autoscaler initialized")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize autoscaler: {e}")
            return False
    
    def get_current_instances(self, worker_name: str) -> int:
        """Get current number of running instances for a worker."""
        try:
            result = subprocess.run([
                "docker-compose", "ps", "-q", worker_name
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                instances = len([line for line in result.stdout.strip().split('\n') if line])
                return instances
            else:
                logger.error(f"Failed to get instances for {worker_name}: {result.stderr}")
                return 1  # Default to 1 instance
                
        except Exception as e:
            logger.error(f"Error getting instances for {worker_name}: {e}")
            return 1
    
    async def get_queue_metrics(self, worker_config: Dict) -> Tuple[int, int]:
        """Get queue metrics for worker queues."""
        try:
            stats = self.task_manager.get_queue_stats()
            total_queued = 0
            total_running = 0
            
            for queue_name in worker_config["queues"]:
                queue_stats = stats.get(queue_name, {})
                if isinstance(queue_stats, dict) and "error" not in queue_stats:
                    total_queued += queue_stats.get("queued_jobs", 0)
                    total_running += queue_stats.get("started_jobs", 0)
            
            return total_queued, total_running
            
        except Exception as e:
            logger.error(f"Error getting queue metrics: {e}")
            return 0, 0
    
    def get_container_resource_usage(self, worker_name: str) -> Dict[str, float]:
        """Get resource usage for worker containers."""
        try:
            result = subprocess.run([
                "docker", "stats", "--no-stream", "--format",
                "table {{.Container}}\\t{{.CPUPerc}}\\t{{.MemPerc}}"
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                return {"cpu": 0.0, "memory": 0.0}
            
            cpu_usage = []
            memory_usage = []
            
            for line in result.stdout.strip().split('\\n')[1:]:  # Skip header
                if worker_name in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        cpu = float(parts[1].replace('%', ''))
                        memory = float(parts[2].replace('%', ''))
                        cpu_usage.append(cpu)
                        memory_usage.append(memory)
            
            avg_cpu = sum(cpu_usage) / len(cpu_usage) if cpu_usage else 0.0
            avg_memory = sum(memory_usage) / len(memory_usage) if memory_usage else 0.0
            
            return {"cpu": avg_cpu, "memory": avg_memory}
            
        except Exception as e:
            logger.error(f"Error getting resource usage for {worker_name}: {e}")
            return {"cpu": 0.0, "memory": 0.0}
    
    def can_scale(self, worker_name: str) -> bool:
        """Check if scaling is allowed (cooldown period)."""
        cooldown = timedelta(seconds=self.config["scaling_cooldown"])
        last_scale = self.last_scale_time.get(worker_name, datetime.min)
        return datetime.now() - last_scale >= cooldown
    
    def scale_worker(self, worker_name: str, target_instances: int) -> bool:
        """Scale worker to target number of instances."""
        try:
            current_instances = self.get_current_instances(worker_name)
            
            if current_instances == target_instances:
                return True
            
            logger.info(f"Scaling {worker_name} from {current_instances} to {target_instances} instances")
            
            result = subprocess.run([
                "docker-compose", "up", "-d", "--scale",
                f"{worker_name}={target_instances}"
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                self.last_scale_time[worker_name] = datetime.now()
                logger.info(f"Successfully scaled {worker_name} to {target_instances} instances")
                return True
            else:
                logger.error(f"Failed to scale {worker_name}: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error scaling {worker_name}: {e}")
            return False
    
    async def evaluate_scaling_decision(self, worker_name: str, worker_config: Dict) -> Optional[int]:
        """Evaluate if scaling is needed and return target instances."""
        if not worker_config.get("enabled", True):
            return None
        
        if not self.can_scale(worker_name):
            return None
        
        current_instances = self.get_current_instances(worker_name)
        queued_jobs, running_jobs = await self.get_queue_metrics(worker_config)
        
        min_instances = worker_config["min_instances"]
        max_instances = worker_config["max_instances"]
        scale_up_threshold = worker_config["scale_up_threshold"]
        scale_down_threshold = worker_config["scale_down_threshold"]
        
        # Resource-based scaling
        if self.config["metrics"]["enable_resource_scaling"]:
            resource_usage = self.get_container_resource_usage(worker_name)
            cpu_threshold = self.config["metrics"]["cpu_threshold"]
            memory_threshold = self.config["metrics"]["memory_threshold"]
            
            if (resource_usage["cpu"] > cpu_threshold or 
                resource_usage["memory"] > memory_threshold):
                logger.info(f"{worker_name} high resource usage: CPU={resource_usage['cpu']:.1f}%, Memory={resource_usage['memory']:.1f}%")
                if current_instances < max_instances:
                    return min(current_instances + 1, max_instances)
        
        # Queue-based scaling
        if queued_jobs >= scale_up_threshold and current_instances < max_instances:
            logger.info(f"{worker_name} scaling up: {queued_jobs} queued jobs (threshold: {scale_up_threshold})")
            return min(current_instances + 1, max_instances)
        
        elif queued_jobs <= scale_down_threshold and current_instances > min_instances:
            # Additional check: make sure we're not too busy
            if running_jobs < current_instances:
                logger.info(f"{worker_name} scaling down: {queued_jobs} queued jobs (threshold: {scale_down_threshold})")
                return max(current_instances - 1, min_instances)
        
        return None
    
    async def run_scaling_cycle(self):
        """Run one scaling evaluation cycle."""
        try:
            logger.debug("Running scaling evaluation cycle")
            
            for worker_name, worker_config in self.config["workers"].items():
                target_instances = await self.evaluate_scaling_decision(worker_name, worker_config)
                
                if target_instances is not None:
                    success = self.scale_worker(worker_name, target_instances)
                    if success:
                        logger.info(f"Scaled {worker_name} to {target_instances} instances")
                    else:
                        logger.error(f"Failed to scale {worker_name}")
        
        except Exception as e:
            logger.error(f"Error in scaling cycle: {e}")
    
    async def start(self):
        """Start the autoscaler main loop."""
        if not await self.initialize():
            logger.error("Failed to initialize autoscaler")
            return
        
        self.running = True
        logger.info("Worker autoscaler started")
        
        try:
            while self.running:
                await self.run_scaling_cycle()
                await asyncio.sleep(self.config["check_interval"])
                
        except KeyboardInterrupt:
            logger.info("Autoscaler interrupted by user")
        except Exception as e:
            logger.error(f"Autoscaler error: {e}")
        finally:
            self.running = False
            logger.info("Worker autoscaler stopped")
    
    def stop(self):
        """Stop the autoscaler."""
        self.running = False
        logger.info("Autoscaler stop requested")
    
    async def get_status(self) -> Dict:
        """Get autoscaler status."""
        status = {
            "running": self.running,
            "config": self.config,
            "workers": {}
        }
        
        for worker_name, worker_config in self.config["workers"].items():
            if worker_config.get("enabled", True):
                current_instances = self.get_current_instances(worker_name)
                queued_jobs, running_jobs = await self.get_queue_metrics(worker_config)
                resource_usage = self.get_container_resource_usage(worker_name)
                
                status["workers"][worker_name] = {
                    "current_instances": current_instances,
                    "min_instances": worker_config["min_instances"],
                    "max_instances": worker_config["max_instances"],
                    "queued_jobs": queued_jobs,
                    "running_jobs": running_jobs,
                    "resource_usage": resource_usage,
                    "can_scale": self.can_scale(worker_name),
                    "last_scale_time": self.last_scale_time.get(worker_name, datetime.min).isoformat()
                }
        
        return status


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="FACEIT Bot Worker Autoscaler")
    parser.add_argument("--config", "-c", help="Configuration file path")
    parser.add_argument("--status", "-s", action="store_true", help="Show status and exit")
    parser.add_argument("--dry-run", "-d", action="store_true", help="Dry run mode (no actual scaling)")
    
    args = parser.parse_args()
    
    autoscaler = WorkerAutoscaler(args.config)
    
    if args.status:
        if await autoscaler.initialize():
            status = await autoscaler.get_status()
            print(json.dumps(status, indent=2, default=str))
        else:
            print("Failed to initialize autoscaler")
        return
    
    if args.dry_run:
        logger.info("Running in dry-run mode - no actual scaling will occur")
        # Override scaling function to do nothing
        autoscaler.scale_worker = lambda name, instances: True
    
    try:
        await autoscaler.start()
    except KeyboardInterrupt:
        logger.info("Shutting down autoscaler...")
        autoscaler.stop()


if __name__ == "__main__":
    asyncio.run(main())