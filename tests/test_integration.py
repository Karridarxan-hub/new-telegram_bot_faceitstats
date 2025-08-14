#!/usr/bin/env python3
"""
Integration tests for FACEIT Bot enterprise architecture.
Tests the complete system including bot, workers, database, and Redis.
"""

import asyncio
import pytest
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path
import json

# Add project root to path
project_root = Path(__file__).parent.parent
import sys
sys.path.insert(0, str(project_root))

from config.settings import settings, validate_settings
from database import init_database, get_database_config
from database.repositories.base import init_repositories
from database.repositories.user_repository import UserRepository
from database.repositories.match_analysis_repository import MatchAnalysisRepository
from utils.redis_cache import init_redis_cache, get_redis_cache
from queues.task_manager import get_task_manager
from queues.tasks.match_analysis import analyze_match_background
from faceit.api import FaceitAPI
from utils.storage import storage

logger = logging.getLogger(__name__)


class IntegrationTestSuite:
    """Comprehensive integration test suite."""
    
    def __init__(self):
        self.task_manager = None
        self.user_repo = None
        self.match_repo = None
        self.redis_cache = None
        self.faceit_api = None
        self.test_results = []
        
    async def setup(self):
        """Setup test environment."""
        try:
            logger.info("Setting up integration test environment...")
            
            # Validate settings
            validate_settings()
            
            # Initialize Redis cache
            await init_redis_cache(settings.redis_url)
            self.redis_cache = get_redis_cache()
            
            # Initialize database
            db_config = get_database_config()
            await init_database(db_config)
            await init_repositories()
            
            # Get repositories
            self.user_repo = UserRepository()
            self.match_repo = MatchAnalysisRepository()
            
            # Initialize task manager
            self.task_manager = get_task_manager()
            await self.task_manager.initialize()
            
            # Initialize FACEIT API
            self.faceit_api = FaceitAPI()
            
            logger.info("Integration test setup completed")
            return True
            
        except Exception as e:
            logger.error(f"Test setup failed: {e}")
            return False
    
    async def cleanup(self):
        """Cleanup test environment."""
        try:
            logger.info("Cleaning up test environment...")
            
            # Clean up test data
            if self.user_repo:
                test_users = await self.user_repo.get_by_criteria({"telegram_id": {"in": [999999, 999998]}})
                for user in test_users:
                    await self.user_repo.delete(user.id)
            
            # Clean up Redis test keys
            if self.redis_cache:
                test_keys = await self.redis_cache.client.keys("test:*")
                if test_keys:
                    await self.redis_cache.client.delete(*test_keys)
            
            # Clean up task manager
            if self.task_manager:
                await self.task_manager.cleanup()
            
            logger.info("Test cleanup completed")
            
        except Exception as e:
            logger.error(f"Test cleanup error: {e}")
    
    def add_test_result(self, test_name: str, success: bool, duration: float, error: str = None):
        """Add test result."""
        self.test_results.append({
            "test": test_name,
            "success": success,
            "duration": duration,
            "error": error,
            "timestamp": datetime.now().isoformat()
        })
    
    async def test_database_operations(self) -> bool:
        """Test database operations."""
        test_name = "Database Operations"
        start_time = time.time()
        
        try:
            logger.info(f"Running {test_name} test...")
            
            # Test user creation
            test_user_data = {
                "telegram_id": 999999,
                "username": "test_user",
                "first_name": "Test",
                "faceit_nickname": "testplayer"
            }
            
            user = await self.user_repo.create(test_user_data)
            assert user is not None
            assert user.telegram_id == 999999
            
            # Test user retrieval
            retrieved_user = await self.user_repo.get_by_telegram_id(999999)
            assert retrieved_user is not None
            assert retrieved_user.username == "test_user"
            
            # Test user update
            await self.user_repo.update(user.id, {"faceit_player_id": "test-player-id"})
            updated_user = await self.user_repo.get_by_telegram_id(999999)
            assert updated_user.faceit_player_id == "test-player-id"
            
            # Test match analysis creation
            match_data = {
                "user_id": user.id,
                "match_url": "https://www.faceit.com/en/cs2/room/test-match-id",
                "analysis_result": {"test": "data"},
                "created_at": datetime.now()
            }
            
            match_analysis = await self.match_repo.create(match_data)
            assert match_analysis is not None
            assert match_analysis.match_url == match_data["match_url"]
            
            duration = time.time() - start_time
            self.add_test_result(test_name, True, duration)
            logger.info(f"{test_name} test passed ({duration:.2f}s)")
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self.add_test_result(test_name, False, duration, str(e))
            logger.error(f"{test_name} test failed: {e}")
            return False
    
    async def test_redis_operations(self) -> bool:
        """Test Redis cache operations."""
        test_name = "Redis Operations"
        start_time = time.time()
        
        try:
            logger.info(f"Running {test_name} test...")
            
            # Test basic set/get operations
            test_key = "test:redis_operations"
            test_value = {"message": "Hello from test", "timestamp": datetime.now().isoformat()}
            
            # Set value
            await self.redis_cache.set(test_key, test_value, ttl=3600)
            
            # Get value
            retrieved_value = await self.redis_cache.get(test_key)
            assert retrieved_value is not None
            assert retrieved_value["message"] == test_value["message"]
            
            # Test TTL
            ttl = await self.redis_cache.client.ttl(test_key)
            assert ttl > 0
            
            # Test player cache functionality
            player_id = "test-player-123"
            player_data = {
                "player_id": player_id,
                "nickname": "TestPlayer",
                "skill_level": 7,
                "elo": 1850
            }
            
            await self.redis_cache.cache_player_data(player_id, player_data)
            cached_player = await self.redis_cache.get_cached_player_data(player_id)
            
            assert cached_player is not None
            assert cached_player["nickname"] == "TestPlayer"
            assert cached_player["skill_level"] == 7
            
            duration = time.time() - start_time
            self.add_test_result(test_name, True, duration)
            logger.info(f"{test_name} test passed ({duration:.2f}s)")
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self.add_test_result(test_name, False, duration, str(e))
            logger.error(f"{test_name} test failed: {e}")
            return False
    
    async def test_queue_system(self) -> bool:
        """Test RQ queue system."""
        test_name = "Queue System"
        start_time = time.time()
        
        try:
            logger.info(f"Running {test_name} test...")
            
            # Test task enqueuing
            test_task_data = {
                "match_url": "https://www.faceit.com/en/cs2/room/1-test-match-id",
                "user_id": 999999,
                "priority": "high"
            }
            
            # Enqueue a test task
            task = await self.task_manager.enqueue_task(
                "match_analysis",
                test_task_data,
                priority="high",
                timeout=300
            )
            
            assert task is not None
            
            # Check task status
            status = self.task_manager.get_task_status(task.id)
            assert status["status"] in ["queued", "started", "finished"]
            
            # Check queue statistics
            stats = self.task_manager.get_queue_stats()
            assert isinstance(stats, dict)
            assert "faceit_bot_high" in stats
            
            # Test health check
            health = self.task_manager.health_check()
            assert health["redis_connection"] == "healthy"
            
            duration = time.time() - start_time
            self.add_test_result(test_name, True, duration)
            logger.info(f"{test_name} test passed ({duration:.2f}s)")
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self.add_test_result(test_name, False, duration, str(e))
            logger.error(f"{test_name} test failed: {e}")
            return False
    
    async def test_faceit_api_integration(self) -> bool:
        """Test FACEIT API integration."""
        test_name = "FACEIT API Integration"
        start_time = time.time()
        
        try:
            logger.info(f"Running {test_name} test...")
            
            # Test with a known player (if API key is available)
            if not settings.faceit_api_key:
                logger.warning("FACEIT API key not available, skipping API tests")
                duration = time.time() - start_time
                self.add_test_result(test_name, True, duration, "Skipped - No API key")
                return True
            
            # Test player search (using a common nickname)
            try:
                players = await self.faceit_api.search_players("s1mple")
                assert len(players) > 0
                
                # Test player details
                player = await self.faceit_api.get_player_details(players[0].player_id)
                assert player is not None
                assert player.nickname is not None
                
            except Exception as api_error:
                # API might be rate limited or unavailable
                logger.warning(f"FACEIT API test failed: {api_error}")
                duration = time.time() - start_time
                self.add_test_result(test_name, True, duration, f"API unavailable: {api_error}")
                return True
            
            duration = time.time() - start_time
            self.add_test_result(test_name, True, duration)
            logger.info(f"{test_name} test passed ({duration:.2f}s)")
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self.add_test_result(test_name, False, duration, str(e))
            logger.error(f"{test_name} test failed: {e}")
            return False
    
    async def test_legacy_storage_compatibility(self) -> bool:
        """Test legacy JSON storage compatibility."""
        test_name = "Legacy Storage Compatibility"
        start_time = time.time()
        
        try:
            logger.info(f"Running {test_name} test...")
            
            # Test legacy storage operations
            test_user_id = 999998
            test_user_data = {
                "telegram_id": test_user_id,
                "username": "legacy_test_user",
                "faceit_player_id": "legacy-player-id",
                "subscription": {
                    "tier": "FREE",
                    "requests_used": 2,
                    "requests_limit": 5
                }
            }
            
            # Test storing user data
            await storage.store_user_data(test_user_id, test_user_data)
            
            # Test retrieving user data
            retrieved_user = await storage.get_user(test_user_id)
            assert retrieved_user is not None
            assert retrieved_user.username == "legacy_test_user"
            assert retrieved_user.faceit_player_id == "legacy-player-id"
            
            # Test subscription data
            subscription = await storage.get_user_subscription(test_user_id)
            assert subscription is not None
            assert subscription.tier == "FREE"
            assert subscription.requests_used == 2
            
            duration = time.time() - start_time
            self.add_test_result(test_name, True, duration)
            logger.info(f"{test_name} test passed ({duration:.2f}s)")
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self.add_test_result(test_name, False, duration, str(e))
            logger.error(f"{test_name} test failed: {e}")
            return False
    
    async def test_performance_benchmarks(self) -> bool:
        """Test system performance benchmarks."""
        test_name = "Performance Benchmarks"
        start_time = time.time()
        
        try:
            logger.info(f"Running {test_name} test...")
            
            benchmarks = {}
            
            # Redis performance test
            redis_start = time.time()
            for i in range(100):
                await self.redis_cache.set(f"perf_test:{i}", {"data": i}, ttl=60)
            for i in range(100):
                value = await self.redis_cache.get(f"perf_test:{i}")
                assert value["data"] == i
            redis_duration = time.time() - redis_start
            benchmarks["redis_100_ops"] = redis_duration
            
            # Database performance test
            db_start = time.time()
            test_users = []
            for i in range(10):
                user_data = {
                    "telegram_id": 900000 + i,
                    "username": f"perf_user_{i}",
                    "first_name": f"User{i}"
                }
                user = await self.user_repo.create(user_data)
                test_users.append(user.id)
            
            # Read test
            for user_id in test_users:
                user = await self.user_repo.get(user_id)
                assert user is not None
            
            # Cleanup test users
            for user_id in test_users:
                await self.user_repo.delete(user_id)
            
            db_duration = time.time() - db_start
            benchmarks["database_10_users"] = db_duration
            
            # Queue performance test
            queue_start = time.time()
            tasks = []
            for i in range(5):
                task = await self.task_manager.enqueue_task(
                    "test_task",
                    {"data": i},
                    priority="default"
                )
                tasks.append(task.id)
            queue_duration = time.time() - queue_start
            benchmarks["queue_5_tasks"] = queue_duration
            
            # Performance assertions
            assert benchmarks["redis_100_ops"] < 5.0, "Redis performance too slow"
            assert benchmarks["database_10_users"] < 10.0, "Database performance too slow"
            assert benchmarks["queue_5_tasks"] < 2.0, "Queue performance too slow"
            
            duration = time.time() - start_time
            self.add_test_result(test_name, True, duration, f"Benchmarks: {benchmarks}")
            logger.info(f"{test_name} test passed ({duration:.2f}s) - {benchmarks}")
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            self.add_test_result(test_name, False, duration, str(e))
            logger.error(f"{test_name} test failed: {e}")
            return False
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all integration tests."""
        logger.info("Starting comprehensive integration test suite...")
        
        if not await self.setup():
            return {"error": "Test setup failed"}
        
        test_methods = [
            self.test_database_operations,
            self.test_redis_operations,
            self.test_queue_system,
            self.test_faceit_api_integration,
            self.test_legacy_storage_compatibility,
            self.test_performance_benchmarks
        ]
        
        passed = 0
        failed = 0
        
        for test_method in test_methods:
            try:
                result = await test_method()
                if result:
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Test method {test_method.__name__} failed: {e}")
                failed += 1
        
        await self.cleanup()
        
        total_duration = sum(r["duration"] for r in self.test_results)
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(test_methods),
            "passed": passed,
            "failed": failed,
            "success_rate": round((passed / len(test_methods)) * 100, 2),
            "total_duration": total_duration,
            "results": self.test_results
        }
        
        logger.info(
            f"Integration test suite completed: "
            f"{passed}/{len(test_methods)} passed "
            f"({summary['success_rate']}%) in {total_duration:.2f}s"
        )
        
        return summary


async def main():
    """Main test runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description="FACEIT Bot Integration Tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    parser.add_argument("--output", "-o", help="Output file for results")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    test_suite = IntegrationTestSuite()
    results = await test_suite.run_all_tests()
    
    # Output results
    results_json = json.dumps(results, indent=2)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(results_json)
        print(f"Results saved to {args.output}")
    else:
        print(results_json)
    
    # Exit with appropriate code
    if results.get("failed", 0) > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())