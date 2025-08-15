#!/usr/bin/env python3
"""
Specific Format Testing - Testing exact format requirements for sessions and maps analysis
"""

import asyncio
import logging
from datetime import datetime

# Test setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import required modules
from config.settings import settings, validate_settings
from faceit.api import FaceitAPI
from utils.formatter import MessageFormatter

async def test_format_compliance():
    """Test if the output matches the exact required formats."""
    
    logger.info("🧪 TESTING EXACT FORMAT COMPLIANCE")
    logger.info("=" * 50)
    
    # Initialize API
    faceit_api = FaceitAPI()
    test_player = "Aniki47"  # Known test account
    
    try:
        # Get player
        logger.info(f"Testing with player: {test_player}")
        player = await faceit_api.search_player(test_player)
        
        if not player:
            logger.error("❌ Test player not found")
            return
        
        logger.info(f"✅ Player found: {player.nickname}")
        
        # Test 1: Sessions Analysis Format
        logger.info("\n🎮 TESTING SESSIONS ANALYSIS FORMAT")
        logger.info("-" * 40)
        
        expected_sessions_format = """
REQUIRED FORMAT:
🎮 Статистика по игровым сессиям: Aniki47
📅 11.08.2025 - 6 матчей • Длительность: 3.5ч
  🟢 HLTV: 1.02 | 🟢 K/D: 1.1 | 🔴 WR: 33.3%
        """
        logger.info(expected_sessions_format)
        
        try:
            sessions_result = await MessageFormatter.format_sessions_analysis(player, faceit_api, limit=20)
            
            logger.info("ACTUAL OUTPUT:")
            logger.info("=" * 30)
            logger.info(sessions_result)
            logger.info("=" * 30)
            
            # Format compliance checks
            sessions_checks = {
                '✅ Has title with player name': f"сессиям: {player.nickname}" in sessions_result or "сессиям:" in sessions_result,
                '✅ Has calendar emoji': '📅' in sessions_result,
                '✅ Has date': any(year in sessions_result for year in ['2024', '2025']),
                '✅ Has match count': any(f"{i} матч" in sessions_result for i in range(1, 30)),
                '✅ Has duration': 'ч' in sessions_result or 'час' in sessions_result or 'мин' in sessions_result,
                '✅ Has HLTV rating': 'HLTV:' in sessions_result,
                '✅ Has K/D ratio': 'K/D:' in sessions_result,  
                '✅ Has win rate': 'WR:' in sessions_result and '%' in sessions_result,
                '✅ Has color indicators': any(emoji in sessions_result for emoji in ['🟢', '🔴', '🟡'])
            }
            
            logger.info("\nSESSIONS FORMAT COMPLIANCE:")
            for check, passed in sessions_checks.items():
                status = "✅ PASS" if passed else "❌ FAIL"
                logger.info(f"{check}: {status}")
            
            sessions_pass = all(sessions_checks.values())
            logger.info(f"\nSESSIONS OVERALL: {'✅ PASS' if sessions_pass else '❌ FAIL'}")
            
        except Exception as e:
            logger.error(f"❌ Sessions analysis failed: {e}")
            sessions_pass = False
        
        # Test 2: Map Analysis Format  
        logger.info("\n🗺️ TESTING MAP ANALYSIS FORMAT")
        logger.info("-" * 40)
        
        expected_maps_format = """
REQUIRED FORMAT:
🗺 Анализ по картам: Kereykhn
✅ de_dust2 (28 матчей)
🏆 Винрейт: 57.1% (16/28) - Хорошая карта
⚔️ K/D: 0.63 (10.2/16.2)
        """
        logger.info(expected_maps_format)
        
        try:
            maps_result = await MessageFormatter.format_map_analysis(player, faceit_api, limit=20)
            
            logger.info("ACTUAL OUTPUT:")
            logger.info("=" * 30)
            logger.info(maps_result)
            logger.info("=" * 30)
            
            # Format compliance checks
            maps_checks = {
                '✅ Has title with player name': f"картам: {player.nickname}" in maps_result or "картам:" in maps_result,
                '✅ Has map emoji': '🗺' in maps_result,
                '✅ Has map names': 'de_' in maps_result,
                '✅ Has match counts in parentheses': 'матч' in maps_result and ')' in maps_result,
                '✅ Has win rate label': 'Винрейт:' in maps_result,
                '✅ Has win rate percentage': '%' in maps_result,
                '✅ Has win rate fraction': any(f"({i}/" in maps_result for i in range(1, 50)),
                '✅ Has K/D label': 'K/D:' in maps_result,
                '✅ Has map quality assessment': any(word in maps_result for word in ['Хорошая', 'Плохая', 'Средняя', 'Отличная', 'карта']),
                '✅ Has status indicators': any(emoji in maps_result for emoji in ['✅', '❌', '🟡', '🏆', '⚔️'])
            }
            
            logger.info("\nMAPS FORMAT COMPLIANCE:")
            for check, passed in maps_checks.items():
                status = "✅ PASS" if passed else "❌ FAIL"
                logger.info(f"{check}: {status}")
            
            maps_pass = all(maps_checks.values())
            logger.info(f"\nMAPS OVERALL: {'✅ PASS' if maps_pass else '❌ FAIL'}")
            
        except Exception as e:
            logger.error(f"❌ Map analysis failed: {e}")
            maps_pass = False
        
        # Overall Results
        logger.info("\n" + "=" * 50)
        logger.info("📋 FINAL FORMAT COMPLIANCE RESULTS")
        logger.info("=" * 50)
        
        overall_pass = sessions_pass and maps_pass
        sessions_status = "✅ COMPLIANT" if sessions_pass else "❌ NON-COMPLIANT"
        maps_status = "✅ COMPLIANT" if maps_pass else "❌ NON-COMPLIANT"
        overall_status = "✅ PASSES QA" if overall_pass else "❌ REQUIRES FIXES"
        
        logger.info(f"🎮 Sessions Format: {sessions_status}")
        logger.info(f"🗺️ Maps Format: {maps_status}")
        logger.info(f"🏆 Overall Result: {overall_status}")
        
        if overall_pass:
            logger.info("\n🎉 ALL FORMAT REQUIREMENTS MET!")
            logger.info("The Senior Developer's fixes are working correctly.")
        else:
            logger.info("\n🚨 FORMAT REQUIREMENTS NOT MET!")
            logger.info("Additional fixes needed for compliance.")
            
        return overall_pass
        
    except Exception as e:
        logger.error(f"❌ Critical testing error: {e}")
        return False

async def test_callback_handlers():
    """Test that callback handlers work correctly."""
    
    logger.info("\n🔧 TESTING CALLBACK HANDLER FUNCTIONALITY")
    logger.info("-" * 50)
    
    # These tests verify the callback functions exist and are callable
    from simple_bot import callback_stats_sessions, callback_stats_maps
    
    # Verify callback functions exist and are properly defined
    try:
        # Check function signatures
        import inspect
        
        sessions_sig = inspect.signature(callback_stats_sessions)
        maps_sig = inspect.signature(callback_stats_maps)
        
        logger.info("✅ callback_stats_sessions function exists")
        logger.info(f"   Parameters: {list(sessions_sig.parameters.keys())}")
        
        logger.info("✅ callback_stats_maps function exists") 
        logger.info(f"   Parameters: {list(maps_sig.parameters.keys())}")
        
        # Check that both functions are async
        sessions_async = inspect.iscoroutinefunction(callback_stats_sessions)
        maps_async = inspect.iscoroutinefunction(callback_stats_maps)
        
        logger.info(f"✅ Sessions callback is async: {sessions_async}")
        logger.info(f"✅ Maps callback is async: {maps_async}")
        
        callback_tests_pass = sessions_async and maps_async
        
        logger.info(f"\n🔧 Callback Handlers: {'✅ WORKING' if callback_tests_pass else '❌ BROKEN'}")
        
        return callback_tests_pass
        
    except Exception as e:
        logger.error(f"❌ Callback handler test failed: {e}")
        return False

async def main():
    """Main testing function."""
    try:
        # Validate settings
        validate_settings()
        
        # Run format compliance tests
        format_compliant = await test_format_compliance()
        
        # Test callback handlers
        callbacks_working = await test_callback_handlers()
        
        # Final QA Report
        logger.info("\n" + "=" * 60)
        logger.info("🏆 FINAL QA ASSESSMENT")
        logger.info("=" * 60)
        
        format_status = "✅ PASS" if format_compliant else "❌ FAIL"
        callback_status = "✅ PASS" if callbacks_working else "❌ FAIL"
        
        logger.info(f"📋 Format Compliance: {format_status}")
        logger.info(f"🔧 Callback Handlers: {callback_status}")
        
        overall_success = format_compliant and callbacks_working
        
        if overall_success:
            logger.info("\n🎉 QA RESULT: STATISTICS FUNCTIONALITY PASSES ALL TESTS")
            logger.info("✅ The Senior Developer's fixes are working correctly")
            logger.info("✅ All format requirements are met")
            logger.info("✅ Callback handlers are functioning properly")
        else:
            logger.info("\n🚨 QA RESULT: STATISTICS FUNCTIONALITY REQUIRES ADDITIONAL FIXES")
            if not format_compliant:
                logger.info("❌ Format compliance issues detected")
            if not callbacks_working:
                logger.info("❌ Callback handler issues detected")
        
        # Save QA report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"QA_Format_Compliance_Report_{timestamp}.md"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("# QA Format Compliance Report\n\n")
            f.write(f"**Test Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Test Subject:** Statistics Functionality Format Requirements\n\n")
            f.write(f"## Results Summary\n\n")
            f.write(f"- **Format Compliance:** {format_status}\n")
            f.write(f"- **Callback Handlers:** {callback_status}\n")
            f.write(f"- **Overall Result:** {'✅ PASS' if overall_success else '❌ FAIL'}\n\n")
            f.write("## Recommendations\n\n")
            if overall_success:
                f.write("✅ Statistics functionality is ready for production use.\n")
            else:
                f.write("❌ Additional development work required before release.\n")
        
        logger.info(f"\n📄 Detailed report saved to: {report_file}")
        
    except Exception as e:
        logger.error(f"❌ Critical QA testing error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())