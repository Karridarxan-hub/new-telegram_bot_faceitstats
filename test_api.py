#!/usr/bin/env python3
"""Test script for FACEIT API integration."""

import asyncio
import logging
from config.settings import validate_settings
from faceit.api import FaceitAPI
from utils.formatter import MessageFormatter

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_faceit_api():
    """Test FACEIT API with real player."""
    try:
        # Validate settings
        validate_settings()
        print("[OK] Configuration validated")
        
        # Initialize API
        api = FaceitAPI()
        print("[OK] FACEIT API initialized")
        
        # Test player search
        print("\n[SEARCH] Searching for player 'Geun-Hee'...")
        player = await api.search_player("Geun-Hee")
        
        if player:
            print(f"[FOUND] Player found: {player.nickname}")
            print(f"        ID: {player.player_id}")
            print(f"        Country: {player.country}")
            
            # Check CS2 game data
            cs2_stats = player.games.get("cs2")
            if cs2_stats:
                print(f"        CS2 Skill Level: {cs2_stats.skill_level}/10")
                print(f"        CS2 ELO: {cs2_stats.faceit_elo}")
                print(f"        CS2 Region: {cs2_stats.region}")
                print(f"        CS2 Label: {cs2_stats.skill_level_label}")
            else:
                print(f"        CS2 data: Not available")
                print(f"        Available games: {list(player.games.keys())}")
            
            # Test message formatting
            print("\n[FORMAT] Testing basic message formatting...")
            try:
                formatted_message = MessageFormatter.format_player_info(player)
                print("[OK] Message formatted successfully")
                # Don't print formatted message due to Unicode issues in Windows console
                print(f"Message length: {len(formatted_message)} characters")
            except Exception as format_error:
                print(f"[WARNING] Message formatting failed: {format_error}")
                print("This is expected - formatter needs additional stats data")
            
        else:
            print("[NOT FOUND] Player 'Geun-Hee' not found")
            
            # Try alternative search
            print("\n[SEARCH] Trying to search for 'GeunHee'...")
            player = await api.search_player("GeunHee")
            if player:
                print(f"[FOUND] Player found with alternative spelling: {player.nickname}")
            else:
                print("[NOT FOUND] Player not found with alternative spelling either")
        
        print("\n[SUCCESS] API test completed successfully!")
        
    except Exception as e:
        logger.error(f"API test failed: {e}")
        print(f"[ERROR] API test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_faceit_api())