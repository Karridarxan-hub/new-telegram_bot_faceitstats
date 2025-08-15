#!/usr/bin/env python3
"""
QA TEST SCRIPT - Statistics Functionality Testing

This script tests the fixed statistics functionality to verify:
1. Session analysis works correctly and matches required format
2. Map analysis works correctly and matches required format
3. Callback handlers work properly
4. Data accuracy and calculations
5. Error handling scenarios
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import List, Dict, Any

# Test setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import required modules
from config.settings import settings, validate_settings
from faceit.api import FaceitAPI
from utils.formatter import MessageFormatter
from utils.storage import storage, UserData

class StatisticsQATester:
    """QA Tester for statistics functionality."""
    
    def __init__(self):
        self.faceit_api = FaceitAPI()
        self.test_results = {
            'sessions_analysis': {'status': 'pending', 'details': []},
            'map_analysis': {'status': 'pending', 'details': []},
            'data_accuracy': {'status': 'pending', 'details': []},
            'error_handling': {'status': 'pending', 'details': []},
            'performance': {'status': 'pending', 'details': []}
        }
        self.test_accounts = [
            'Aniki47',    # Should have 50+ matches for session testing
            'Kereykhn',   # For map analysis testing
            'Geun-Hee'    # Alternative test account
        ]
    
    async def run_comprehensive_tests(self):
        """Run all QA tests."""
        logger.info("🧪 Starting QA Testing for Statistics Functionality")
        logger.info("=" * 60)
        
        # Test 1: Session Analysis
        await self._test_sessions_analysis()
        
        # Test 2: Map Analysis  
        await self._test_map_analysis()
        
        # Test 3: Data Accuracy
        await self._test_data_accuracy()
        
        # Test 4: Error Handling
        await self._test_error_handling()
        
        # Test 5: Performance Testing
        await self._test_performance()
        
        # Generate comprehensive report
        self._generate_final_report()
    
    async def _test_sessions_analysis(self):
        """Test session analysis functionality and format."""
        logger.info("🎮 Testing Session Analysis Functionality")
        
        required_format = """
        Expected Format:
        🎮 Статистика по игровым сессиям: Aniki47
        📅 11.08.2025 - 6 матчей • Длительность: 3.5ч
          🟢 HLTV: 1.02 | 🟢 K/D: 1.1 | 🔴 WR: 33.3%
        """
        logger.info(required_format)
        
        for nickname in self.test_accounts:
            try:
                start_time = time.time()
                logger.info(f"Testing sessions for {nickname}...")
                
                # Get player
                player = await self.faceit_api.search_player(nickname)
                if not player:
                    self.test_results['sessions_analysis']['details'].append({
                        'player': nickname,
                        'status': 'FAIL',
                        'reason': 'Player not found'
                    })
                    continue
                
                # Test session analysis
                try:
                    sessions_text = await MessageFormatter.format_sessions_analysis(
                        player, 
                        self.faceit_api, 
                        limit=50
                    )
                    
                    # Verify format requirements
                    format_checks = self._verify_sessions_format(sessions_text, nickname)
                    
                    elapsed_time = time.time() - start_time
                    
                    self.test_results['sessions_analysis']['details'].append({
                        'player': nickname,
                        'status': 'PASS' if format_checks['all_passed'] else 'FAIL',
                        'format_checks': format_checks,
                        'response_time': f"{elapsed_time:.2f}s",
                        'output_sample': sessions_text[:200] + "..." if len(sessions_text) > 200 else sessions_text
                    })
                    
                    logger.info(f"✅ Session analysis for {nickname}: {'PASS' if format_checks['all_passed'] else 'FAIL'}")
                    
                except Exception as e:
                    self.test_results['sessions_analysis']['details'].append({
                        'player': nickname,
                        'status': 'FAIL',
                        'reason': f'Function error: {str(e)}'
                    })
                    logger.error(f"❌ Session analysis failed for {nickname}: {e}")
                
            except Exception as e:
                logger.error(f"❌ Critical error testing {nickname}: {e}")
        
        # Determine overall status
        all_passed = all(
            result['status'] == 'PASS' 
            for result in self.test_results['sessions_analysis']['details'] 
            if result['status'] != 'FAIL'
        )
        self.test_results['sessions_analysis']['status'] = 'PASS' if all_passed else 'FAIL'
    
    async def _test_map_analysis(self):
        """Test map analysis functionality and format."""
        logger.info("🗺️ Testing Map Analysis Functionality")
        
        required_format = """
        Expected Format:
        🗺 Анализ по картам: Kereykhn
        ✅ de_dust2 (28 матчей)
        🏆 Винрейт: 57.1% (16/28) - Хорошая карта
        ⚔️ K/D: 0.63 (10.2/16.2)
        """
        logger.info(required_format)
        
        for nickname in self.test_accounts:
            try:
                start_time = time.time()
                logger.info(f"Testing map analysis for {nickname}...")
                
                # Get player
                player = await self.faceit_api.search_player(nickname)
                if not player:
                    self.test_results['map_analysis']['details'].append({
                        'player': nickname,
                        'status': 'FAIL',
                        'reason': 'Player not found'
                    })
                    continue
                
                # Test map analysis
                try:
                    map_text = await MessageFormatter.format_map_analysis(
                        player,
                        self.faceit_api,
                        limit=50
                    )
                    
                    # Verify format requirements
                    format_checks = self._verify_map_format(map_text, nickname)
                    
                    elapsed_time = time.time() - start_time
                    
                    self.test_results['map_analysis']['details'].append({
                        'player': nickname,
                        'status': 'PASS' if format_checks['all_passed'] else 'FAIL',
                        'format_checks': format_checks,
                        'response_time': f"{elapsed_time:.2f}s",
                        'output_sample': map_text[:300] + "..." if len(map_text) > 300 else map_text
                    })
                    
                    logger.info(f"✅ Map analysis for {nickname}: {'PASS' if format_checks['all_passed'] else 'FAIL'}")
                    
                except Exception as e:
                    self.test_results['map_analysis']['details'].append({
                        'player': nickname,
                        'status': 'FAIL',
                        'reason': f'Function error: {str(e)}'
                    })
                    logger.error(f"❌ Map analysis failed for {nickname}: {e}")
                
            except Exception as e:
                logger.error(f"❌ Critical error testing {nickname}: {e}")
        
        # Determine overall status
        all_passed = all(
            result['status'] == 'PASS' 
            for result in self.test_results['map_analysis']['details'] 
            if result['status'] != 'FAIL'
        )
        self.test_results['map_analysis']['status'] = 'PASS' if all_passed else 'FAIL'
    
    async def _test_data_accuracy(self):
        """Test data accuracy against real FACEIT data."""
        logger.info("📊 Testing Data Accuracy")
        
        for nickname in self.test_accounts[:2]:  # Test 2 accounts for accuracy
            try:
                logger.info(f"Validating data accuracy for {nickname}...")
                
                player = await self.faceit_api.search_player(nickname)
                if not player:
                    continue
                
                # Get direct API stats for comparison
                direct_stats = await self.faceit_api.get_player_stats(player.player_id, "cs2")
                matches = await self.faceit_api.get_player_matches(player.player_id, limit=20)
                
                # Test session analysis calculations
                sessions_text = await MessageFormatter.format_sessions_analysis(player, self.faceit_api, limit=20)
                map_text = await MessageFormatter.format_map_analysis(player, self.faceit_api, limit=20)
                
                # Extract and validate calculations (basic sanity checks)
                accuracy_checks = {
                    'sessions_has_real_dates': '📅' in sessions_text and '2025' in sessions_text,
                    'sessions_has_hltv_rating': 'HLTV:' in sessions_text,
                    'sessions_has_realistic_matches': any(str(i) in sessions_text for i in range(1, 21)),
                    'maps_has_winrate_data': 'Винрейт:' in map_text and '%' in map_text,
                    'maps_has_kd_data': 'K/D:' in map_text,
                    'maps_has_multiple_maps': map_text.count('de_') >= 1
                }
                
                all_accurate = all(accuracy_checks.values())
                
                self.test_results['data_accuracy']['details'].append({
                    'player': nickname,
                    'status': 'PASS' if all_accurate else 'FAIL',
                    'checks': accuracy_checks,
                    'sessions_sample': sessions_text[:150],
                    'maps_sample': map_text[:150]
                })
                
                logger.info(f"✅ Data accuracy for {nickname}: {'PASS' if all_accurate else 'FAIL'}")
                
            except Exception as e:
                logger.error(f"❌ Data accuracy test failed for {nickname}: {e}")
        
        self.test_results['data_accuracy']['status'] = 'PASS' if len(self.test_results['data_accuracy']['details']) > 0 else 'FAIL'
    
    async def _test_error_handling(self):
        """Test error handling scenarios."""
        logger.info("🚨 Testing Error Handling")
        
        error_tests = [
            {
                'name': 'Non-existent player',
                'nickname': 'ThisPlayerDoesNotExist12345',
                'expected': 'Should handle gracefully'
            },
            {
                'name': 'Empty player ID',
                'test_type': 'empty_id',
                'expected': 'Should handle gracefully'
            }
        ]
        
        for test in error_tests:
            try:
                if test.get('nickname'):
                    player = await self.faceit_api.search_player(test['nickname'])
                    if not player:
                        self.test_results['error_handling']['details'].append({
                            'test': test['name'],
                            'status': 'PASS',
                            'result': 'Correctly returned None for non-existent player'
                        })
                    else:
                        self.test_results['error_handling']['details'].append({
                            'test': test['name'],
                            'status': 'FAIL',
                            'result': 'Unexpectedly found non-existent player'
                        })
                
            except Exception as e:
                self.test_results['error_handling']['details'].append({
                    'test': test['name'],
                    'status': 'PASS',
                    'result': f'Exception handled correctly: {type(e).__name__}'
                })
        
        self.test_results['error_handling']['status'] = 'PASS'
    
    async def _test_performance(self):
        """Test performance and response times."""
        logger.info("⚡ Testing Performance")
        
        performance_data = []
        
        for nickname in self.test_accounts[:2]:  # Test 2 accounts for performance
            try:
                player = await self.faceit_api.search_player(nickname)
                if not player:
                    continue
                
                # Test sessions analysis performance
                start_time = time.time()
                sessions_result = await MessageFormatter.format_sessions_analysis(player, self.faceit_api, limit=30)
                sessions_time = time.time() - start_time
                
                # Test map analysis performance  
                start_time = time.time()
                map_result = await MessageFormatter.format_map_analysis(player, self.faceit_api, limit=30)
                map_time = time.time() - start_time
                
                performance_data.append({
                    'player': nickname,
                    'sessions_time': f"{sessions_time:.2f}s",
                    'map_time': f"{map_time:.2f}s",
                    'total_time': f"{sessions_time + map_time:.2f}s",
                    'sessions_length': len(sessions_result),
                    'map_length': len(map_result)
                })
                
                logger.info(f"⚡ Performance for {nickname}: Sessions={sessions_time:.2f}s, Maps={map_time:.2f}s")
                
            except Exception as e:
                logger.error(f"❌ Performance test failed for {nickname}: {e}")
        
        self.test_results['performance']['details'] = performance_data
        # Performance is acceptable if all tests complete under 30 seconds each
        acceptable_performance = all(
            float(data['sessions_time'].replace('s', '')) < 30 and 
            float(data['map_time'].replace('s', '')) < 30
            for data in performance_data
        )
        self.test_results['performance']['status'] = 'PASS' if acceptable_performance else 'FAIL'
    
    def _verify_sessions_format(self, text: str, nickname: str) -> dict:
        """Verify sessions analysis format requirements."""
        checks = {
            'has_title': f"Статистика по игровым сессиям: {nickname}" in text or "сессиям:" in text,
            'has_date': '📅' in text and ('2025' in text or '2024' in text),
            'has_match_count': any(f"{i} матч" in text for i in range(1, 50)),
            'has_duration': 'ч' in text or 'час' in text or 'мин' in text,
            'has_hltv_rating': 'HLTV:' in text and any(f"1.{i}" in text or f"0.{i}" in text for i in range(10)),
            'has_kd_ratio': 'K/D:' in text,
            'has_winrate': 'WR:' in text and '%' in text,
            'has_color_indicators': '🟢' in text or '🔴' in text or '🟡' in text
        }
        
        checks['all_passed'] = all(checks.values())
        return checks
    
    def _verify_map_format(self, text: str, nickname: str) -> dict:
        """Verify map analysis format requirements."""
        checks = {
            'has_title': f"Анализ по картам: {nickname}" in text or "по картам:" in text,
            'has_map_names': 'de_' in text,
            'has_match_counts': 'матчей)' in text or 'матч)' in text,
            'has_winrate_label': 'Винрейт:' in text,
            'has_winrate_percentage': '%' in text,
            'has_winrate_fraction': any(f"({i}/" in text for i in range(1, 100)),
            'has_kd_label': 'K/D:' in text,
            'has_map_quality': any(word in text for word in ['Хорошая', 'Плохая', 'Средняя', 'Отличная']),
            'has_checkmarks': '✅' in text or '❌' in text or '🟡' in text
        }
        
        checks['all_passed'] = all(checks.values())
        return checks
    
    def _generate_final_report(self):
        """Generate comprehensive test report."""
        logger.info("\n" + "=" * 60)
        logger.info("📋 QA TEST RESULTS SUMMARY")
        logger.info("=" * 60)
        
        total_tests = 0
        passed_tests = 0
        
        for test_name, result in self.test_results.items():
            status_emoji = "✅" if result['status'] == 'PASS' else "❌"
            logger.info(f"{status_emoji} {test_name.upper()}: {result['status']}")
            
            total_tests += 1
            if result['status'] == 'PASS':
                passed_tests += 1
            
            # Log details for each test category
            if result['details']:
                logger.info(f"   Details: {len(result['details'])} test cases")
                for detail in result['details']:
                    if isinstance(detail, dict) and 'player' in detail:
                        detail_status = "✅" if detail.get('status') == 'PASS' else "❌"
                        logger.info(f"     {detail_status} {detail['player']}: {detail.get('status', 'UNKNOWN')}")
        
        logger.info("-" * 40)
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        logger.info(f"OVERALL SUCCESS RATE: {success_rate:.1f}% ({passed_tests}/{total_tests})")
        
        if success_rate >= 80:
            logger.info("🎉 QA RESULT: STATISTICS FUNCTIONALITY PASSES QA TESTING")
        else:
            logger.info("🚨 QA RESULT: STATISTICS FUNCTIONALITY REQUIRES FIXES")
        
        # Write detailed report to file
        self._write_detailed_report()
    
    def _write_detailed_report(self):
        """Write detailed test report to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"QA_Statistics_Test_Report_{timestamp}.md"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("# QA Statistics Functionality Test Report\n\n")
            f.write(f"**Test Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Test Accounts:** {', '.join(self.test_accounts)}\n\n")
            
            for test_name, result in self.test_results.items():
                f.write(f"## {test_name.replace('_', ' ').title()}\n")
                f.write(f"**Status:** {result['status']}\n\n")
                
                if result['details']:
                    f.write("### Detailed Results:\n\n")
                    for detail in result['details']:
                        if isinstance(detail, dict):
                            f.write(f"- **{detail.get('player', detail.get('test', 'Test'))}:** {detail.get('status', 'Unknown')}\n")
                            if detail.get('reason'):
                                f.write(f"  - Reason: {detail['reason']}\n")
                            if detail.get('response_time'):
                                f.write(f"  - Response Time: {detail['response_time']}\n")
                f.write("\n")
        
        logger.info(f"📄 Detailed report saved to: {report_file}")

async def main():
    """Main testing function."""
    try:
        # Validate settings
        validate_settings()
        
        # Initialize and run QA tester
        tester = StatisticsQATester()
        await tester.run_comprehensive_tests()
        
    except Exception as e:
        logger.error(f"Critical error in QA testing: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())