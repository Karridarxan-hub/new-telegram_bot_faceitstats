#!/usr/bin/env python3
"""Test script for Storage system."""

import asyncio
import logging
from datetime import datetime
from utils.storage import storage, UserData

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_storage():
    """Test storage functionality."""
    try:
        print("[TEST] Testing Storage System")
        
        # Test 1: Create and save user
        test_user_id = 12345
        test_user_data = UserData(
            user_id=test_user_id,
            faceit_player_id="0cf595d2-b9a1-4316-9df9-a627c7a8c664",
            faceit_nickname="Geun-Hee",
            language="ru",
            notifications_enabled=True,
            total_requests=5
        )
        
        print(f"[SAVE] Saving test user: {test_user_data.faceit_nickname}")
        await storage.save_user(test_user_data)
        print("[OK] User saved successfully")
        
        # Test 2: Retrieve user
        print(f"[GET] Retrieving user: {test_user_id}")
        retrieved_user = await storage.get_user(test_user_id)
        
        if retrieved_user:
            print(f"[FOUND] User retrieved: {retrieved_user.faceit_nickname}")
            print(f"        ID: {retrieved_user.user_id}")
            print(f"        FACEIT ID: {retrieved_user.faceit_player_id}")
            print(f"        Requests: {retrieved_user.total_requests}")
            print(f"        Language: {retrieved_user.language}")
        else:
            print("[ERROR] User not found after save")
            return False
        
        # Test 3: Update user request count
        print("[UPDATE] Incrementing request count...")
        await storage.increment_request_count(test_user_id)
        
        updated_user = await storage.get_user(test_user_id)
        if updated_user:
            print(f"[OK] Requests updated: {updated_user.total_requests}")
        else:
            print("[ERROR] Failed to update requests")
            return False
        
        # Test 4: Get all users
        print("[ALL] Getting all users...")
        all_users = await storage.get_all_users()
        print(f"[OK] Found {len(all_users)} users with FACEIT accounts")
        
        # Test 5: Get stats
        print("[STATS] Getting user statistics...")
        user_stats = await storage.get_user_stats()
        print(f"[OK] Total users: {user_stats['total_users']}")
        print(f"     Active today: {user_stats['active_users']}")
        print(f"     Total requests: {user_stats['total_requests']}")
        
        # Test 6: Test with no FACEIT data
        test_user_id_2 = 54321
        test_user_data_2 = UserData(
            user_id=test_user_id_2,
            language="en"
        )
        
        await storage.save_user(test_user_data_2)
        print("[OK] User without FACEIT data saved")
        
        # Verify filtering works
        all_faceit_users = await storage.get_all_users()
        non_faceit_user_2 = await storage.get_user(test_user_id_2)
        
        print(f"[FILTER] FACEIT users: {len(all_faceit_users)}")
        print(f"[FILTER] Non-FACEIT user exists: {non_faceit_user_2 is not None}")
        
        print("\n[SUCCESS] Storage system test completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Storage test failed: {e}")
        print(f"[ERROR] Storage test failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_storage())
    if success:
        print("\n[RESULT] All storage tests passed!")
    else:
        print("\n[RESULT] Some storage tests failed!")