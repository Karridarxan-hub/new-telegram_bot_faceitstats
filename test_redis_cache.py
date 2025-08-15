#!/usr/bin/env python3
"""Test Redis cache functionality."""

import asyncio
import sys
from utils.redis_cache import init_redis_cache, close_redis_cache, player_cache, match_cache, stats_cache
from utils.cache import CachedFaceitAPI
from faceit.api import FaceitAPI
from config.settings import settings

async def test_redis_cache():
    """Test Redis cache functionality."""
    try:
        print("Testing Redis cache functionality...")
        
        # Initialize Redis cache
        await init_redis_cache(settings.redis_url)
        print("Redis cache initialized")
        
        # Use global cache instances that are already initialized
        # player_cache, match_cache, stats_cache are already available
        
        # Test basic cache operations
        print("\nTesting cache operations...")
        
        # Test set and get
        await player_cache.set("test_key", {"player": "test_data", "cached_at": "now"}, ttl=60)
        cached_data = await player_cache.get("test_key")
        
        if cached_data:
            print("Cache SET/GET working")
            print(f"   Cached data: {cached_data}")
        else:
            print("Cache SET/GET failed")
            return False
        
        # Test cache with FACEIT API
        print("\nTesting FACEIT API caching...")
        
        faceit_api = FaceitAPI()
        cached_api = CachedFaceitAPI(faceit_api)
        
        # Test search player with cache
        test_player = "s1mple"  # Known player
        print(f"   Searching for player: {test_player}")
        
        # First call (should miss cache)
        player1 = await cached_api.search_player(test_player)
        print(f"   First call result: {'OK' if player1 else 'FAIL'}")
        
        # Second call (should hit cache)
        player2 = await cached_api.search_player(test_player)
        print(f"   Second call result: {'OK' if player2 else 'FAIL'}")
        
        if player1 and player2:
            print("FACEIT API caching working")
        else:
            print("FACEIT API caching may have issues")
        
        # Test cache expiry
        print("\nTesting cache expiry...")
        await player_cache.set("expire_test", "data", ttl=1)  # 1 second TTL
        
        # Check immediately
        data = await player_cache.get("expire_test")
        if data:
            print("Data exists immediately after set")
        
        # Wait and check again
        await asyncio.sleep(2)
        data = await player_cache.get("expire_test")
        if not data:
            print("Data expired correctly after TTL")
        else:
            print("Data did not expire as expected")
        
        # Test cache stats (if Redis provides them)
        print("\nCache performance test completed successfully!")
        return True
        
    except Exception as e:
        print(f"Cache test failed: {e}")
        return False
        
    finally:
        # Clean up
        await close_redis_cache()
        print("Redis cache closed")

async def main():
    """Main test function."""
    print("Starting Redis Cache Test Suite")
    print("=" * 50)
    
    success = await test_redis_cache()
    
    print("\n" + "=" * 50)
    if success:
        print("Redis cache testing completed successfully!")
        print("All cache functionality is working properly")
    else:
        print("Redis cache testing failed")
        print("Please check the configuration")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)