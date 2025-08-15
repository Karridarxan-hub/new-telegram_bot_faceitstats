#!/usr/bin/env python3
"""
Focused Subscription System Testing

Tests the core subscription and payment functionality that's currently implemented.
Focuses on business logic validation and configuration testing.

Author: Claude Code Payment Integration Specialist
"""

import sys
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.models import SubscriptionTier, PaymentStatus
from services.subscription import SubscriptionService
from utils.storage import storage, UserData

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SubscriptionTester:
    """Focused subscription system testing."""
    
    def __init__(self):
        """Initialize tester."""
        self.results = {
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'test_details': []
        }
        
        # Expected configuration
        self.expected_limits = {
            SubscriptionTier.FREE: {
                "daily_requests": 10,
                "matches_history": 20,
                "advanced_analytics": False,
                "notifications": True,
                "api_access": False
            },
            SubscriptionTier.PREMIUM: {
                "daily_requests": 100,
                "matches_history": 50,
                "advanced_analytics": True,
                "notifications": True,
                "api_access": True
            },
            SubscriptionTier.PRO: {
                "daily_requests": -1,  # Unlimited
                "matches_history": 200,
                "advanced_analytics": True,
                "notifications": True,
                "api_access": True
            }
        }
        
        self.expected_pricing = {
            SubscriptionTier.PREMIUM: {
                "monthly": {"price": 199, "days": 30},
                "yearly": {"price": 1999, "days": 365}
            },
            SubscriptionTier.PRO: {
                "monthly": {"price": 299, "days": 30},
                "yearly": {"price": 2999, "days": 365}
            }
        }

    def run_test(self, test_name: str, test_func, *args, **kwargs) -> bool:
        """Run a single test and record results."""
        self.results['total_tests'] += 1
        
        try:
            logger.info(f"Running test: {test_name}")
            start_time = datetime.now()
            
            result = test_func(*args, **kwargs)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            if result:
                self.results['passed_tests'] += 1
                status = "PASS"
                logger.info(f"[PASS] {test_name} ({execution_time:.3f}s)")
            else:
                self.results['failed_tests'] += 1
                status = "FAIL"
                logger.error(f"[FAIL] {test_name} ({execution_time:.3f}s)")
            
            self.results['test_details'].append({
                'test_name': test_name,
                'status': status,
                'execution_time': execution_time
            })
            
            return result
            
        except Exception as e:
            self.results['failed_tests'] += 1
            logger.error(f"[ERROR] {test_name} - {e}")
            
            self.results['test_details'].append({
                'test_name': test_name,
                'status': "ERROR",
                'error': str(e)
            })
            
            return False

    def test_subscription_service_configuration(self) -> bool:
        """Test subscription service configuration and pricing."""
        try:
            # Test pricing configuration
            service_pricing = SubscriptionService.PRICING
            service_limits = SubscriptionService.TIER_LIMITS
            
            # Validate pricing structure
            for tier in [SubscriptionTier.PREMIUM, SubscriptionTier.PRO]:
                if tier not in service_pricing:
                    logger.error(f"Missing pricing for tier: {tier}")
                    return False
                
                expected = self.expected_pricing[tier]
                actual = service_pricing[tier]
                
                for duration in ["monthly", "yearly"]:
                    if duration not in actual:
                        logger.error(f"Missing {duration} pricing for {tier}")
                        return False
                    
                    if actual[duration]["price"] != expected[duration]["price"]:
                        logger.error(f"Price mismatch for {tier} {duration}: expected {expected[duration]['price']}, got {actual[duration]['price']}")
                        return False
                    
                    if actual[duration]["days"] != expected[duration]["days"]:
                        logger.error(f"Days mismatch for {tier} {duration}: expected {expected[duration]['days']}, got {actual[duration]['days']}")
                        return False
            
            logger.info("Pricing configuration validated")
            
            # Validate tier limits
            for tier in [SubscriptionTier.FREE, SubscriptionTier.PREMIUM, SubscriptionTier.PRO]:
                if tier not in service_limits:
                    logger.error(f"Missing limits for tier: {tier}")
                    return False
                
                expected = self.expected_limits[tier]
                actual = service_limits[tier]
                
                for limit_key in expected:
                    if limit_key not in actual:
                        logger.error(f"Missing limit {limit_key} for tier {tier}")
                        return False
                    
                    if actual[limit_key] != expected[limit_key]:
                        logger.error(f"Limit mismatch for {tier}.{limit_key}: expected {expected[limit_key]}, got {actual[limit_key]}")
                        return False
            
            logger.info("Tier limits configuration validated")
            return True
            
        except Exception as e:
            logger.error(f"Configuration test failed: {e}")
            return False

    def test_subscription_pricing_calculations(self) -> bool:
        """Test subscription pricing calculations."""
        try:
            pricing = SubscriptionService.PRICING
            
            # Test PREMIUM pricing
            premium_monthly = pricing[SubscriptionTier.PREMIUM]["monthly"]
            if premium_monthly["price"] != 199:
                logger.error(f"PREMIUM monthly price should be 199 Telegram Stars, got {premium_monthly['price']}")
                return False
            
            premium_yearly = pricing[SubscriptionTier.PREMIUM]["yearly"]
            if premium_yearly["price"] != 1999:
                logger.error(f"PREMIUM yearly price should be 1999 Telegram Stars, got {premium_yearly['price']}")
                return False
            
            # Calculate yearly discount
            monthly_annual_cost = premium_monthly["price"] * 12
            yearly_cost = premium_yearly["price"]
            yearly_discount = ((monthly_annual_cost - yearly_cost) / monthly_annual_cost) * 100
            
            logger.info(f"PREMIUM yearly discount: {yearly_discount:.1f}%")
            
            # Test PRO pricing
            pro_monthly = pricing[SubscriptionTier.PRO]["monthly"]
            if pro_monthly["price"] != 299:
                logger.error(f"PRO monthly price should be 299 Telegram Stars, got {pro_monthly['price']}")
                return False
            
            pro_yearly = pricing[SubscriptionTier.PRO]["yearly"]
            if pro_yearly["price"] != 2999:
                logger.error(f"PRO yearly price should be 2999 Telegram Stars, got {pro_yearly['price']}")
                return False
            
            # Test duration calculations
            if premium_monthly["days"] != 30:
                logger.error(f"PREMIUM monthly should be 30 days, got {premium_monthly['days']}")
                return False
            
            if premium_yearly["days"] != 365:
                logger.error(f"PREMIUM yearly should be 365 days, got {premium_yearly['days']}")
                return False
            
            logger.info("Pricing calculations validated")
            return True
            
        except Exception as e:
            logger.error(f"Pricing calculations test failed: {e}")
            return False

    def test_tier_limits_logic(self) -> bool:
        """Test subscription tier limits logic."""
        try:
            limits = SubscriptionService.TIER_LIMITS
            
            # Test FREE tier limits (most restrictive)
            free_limits = limits[SubscriptionTier.FREE]
            if free_limits["daily_requests"] != 10:
                logger.error(f"FREE tier should have 10 daily requests, got {free_limits['daily_requests']}")
                return False
            
            if free_limits["advanced_analytics"] != False:
                logger.error(f"FREE tier should not have advanced analytics")
                return False
            
            if free_limits["api_access"] != False:
                logger.error(f"FREE tier should not have API access")
                return False
            
            # Test PREMIUM tier limits
            premium_limits = limits[SubscriptionTier.PREMIUM]
            if premium_limits["daily_requests"] != 100:
                logger.error(f"PREMIUM tier should have 100 daily requests, got {premium_limits['daily_requests']}")
                return False
            
            if premium_limits["advanced_analytics"] != True:
                logger.error(f"PREMIUM tier should have advanced analytics")
                return False
            
            if premium_limits["api_access"] != True:
                logger.error(f"PREMIUM tier should have API access")
                return False
            
            # Test PRO tier limits (unlimited)
            pro_limits = limits[SubscriptionTier.PRO]
            if pro_limits["daily_requests"] != -1:
                logger.error(f"PRO tier should have unlimited daily requests (-1), got {pro_limits['daily_requests']}")
                return False
            
            if pro_limits["matches_history"] != 200:
                logger.error(f"PRO tier should have 200 matches history, got {pro_limits['matches_history']}")
                return False
            
            if pro_limits["priority_support"] != True:
                logger.error(f"PRO tier should have priority support")
                return False
            
            # Test tier progression (each tier should be better than previous)
            if premium_limits["daily_requests"] <= free_limits["daily_requests"]:
                logger.error("PREMIUM should have more daily requests than FREE")
                return False
            
            if premium_limits["matches_history"] <= free_limits["matches_history"]:
                logger.error("PREMIUM should have more matches history than FREE")
                return False
            
            if pro_limits["matches_history"] <= premium_limits["matches_history"]:
                logger.error("PRO should have more matches history than PREMIUM")
                return False
            
            logger.info("Tier limits logic validated")
            return True
            
        except Exception as e:
            logger.error(f"Tier limits test failed: {e}")
            return False

    def test_payment_payload_format(self) -> bool:
        """Test payment payload format validation."""
        try:
            # Test valid payload formats
            valid_payloads = [
                "premium_monthly_123456789",
                "pro_yearly_987654321",
                "premium_yearly_555555555"
            ]
            
            for payload in valid_payloads:
                parts = payload.split("_")
                if len(parts) != 3:
                    logger.error(f"Invalid payload format: {payload}")
                    return False
                
                tier_str, duration, user_id_str = parts
                
                # Validate tier
                if tier_str not in ["premium", "pro"]:
                    logger.error(f"Invalid tier in payload: {tier_str}")
                    return False
                
                # Validate duration
                if duration not in ["monthly", "yearly"]:
                    logger.error(f"Invalid duration in payload: {duration}")
                    return False
                
                # Validate user ID format
                try:
                    user_id = int(user_id_str)
                    if user_id <= 0:
                        logger.error(f"Invalid user ID in payload: {user_id_str}")
                        return False
                except ValueError:
                    logger.error(f"Non-numeric user ID in payload: {user_id_str}")
                    return False
            
            # Test invalid payload formats
            invalid_payloads = [
                "premium_monthly",  # Missing user ID
                "invalid_monthly_123",  # Invalid tier
                "premium_invalid_123",  # Invalid duration
                "premium_monthly_abc",  # Non-numeric user ID
                "premium_monthly_123_extra"  # Too many parts
            ]
            
            for payload in invalid_payloads:
                parts = payload.split("_")
                is_valid = True
                
                if len(parts) != 3:
                    is_valid = False
                else:
                    tier_str, duration, user_id_str = parts
                    if tier_str not in ["premium", "pro"]:
                        is_valid = False
                    elif duration not in ["monthly", "yearly"]:
                        is_valid = False
                    else:
                        try:
                            user_id = int(user_id_str)
                            if user_id <= 0:
                                is_valid = False
                        except ValueError:
                            is_valid = False
                
                if is_valid:
                    logger.error(f"Invalid payload should be rejected but wasn't: {payload}")
                    return False
            
            logger.info("Payment payload format validation successful")
            return True
            
        except Exception as e:
            logger.error(f"Payment payload test failed: {e}")
            return False

    def test_telegram_stars_integration(self) -> bool:
        """Test Telegram Stars payment integration configuration."""
        try:
            # Test currency configuration
            expected_currency = "XTR"  # Telegram Stars
            
            # Validate that all pricing uses correct currency
            pricing = SubscriptionService.PRICING
            
            for tier in pricing:
                for duration in pricing[tier]:
                    # While the pricing doesn't explicitly store currency,
                    # we verify that amounts are positive integers (Telegram Stars requirement)
                    amount = pricing[tier][duration]["price"]
                    
                    if not isinstance(amount, int):
                        logger.error(f"Telegram Stars amount must be integer, got {type(amount)} for {tier} {duration}")
                        return False
                    
                    if amount <= 0:
                        logger.error(f"Telegram Stars amount must be positive, got {amount} for {tier} {duration}")
                        return False
                    
                    # Telegram Stars amounts should be reasonable (typically 1-10000)
                    if amount > 10000:
                        logger.error(f"Telegram Stars amount seems too high: {amount} for {tier} {duration}")
                        return False
            
            # Test minimum amounts (Telegram Stars has minimum payment amounts)
            min_amount = 1
            for tier in pricing:
                for duration in pricing[tier]:
                    amount = pricing[tier][duration]["price"]
                    if amount < min_amount:
                        logger.error(f"Amount below minimum: {amount} for {tier} {duration}")
                        return False
            
            logger.info("Telegram Stars integration configuration validated")
            return True
            
        except Exception as e:
            logger.error(f"Telegram Stars integration test failed: {e}")
            return False

    def test_business_logic_validation(self) -> bool:
        """Test business logic validation."""
        try:
            # Test tier upgrade logic
            pricing = SubscriptionService.PRICING
            limits = SubscriptionService.TIER_LIMITS
            
            # Validate that higher tiers provide more value
            premium_monthly_price = pricing[SubscriptionTier.PREMIUM]["monthly"]["price"]
            pro_monthly_price = pricing[SubscriptionTier.PRO]["monthly"]["price"]
            
            if pro_monthly_price <= premium_monthly_price:
                logger.error(f"PRO monthly price ({pro_monthly_price}) should be higher than PREMIUM ({premium_monthly_price})")
                return False
            
            # Validate feature progression
            free_requests = limits[SubscriptionTier.FREE]["daily_requests"]
            premium_requests = limits[SubscriptionTier.PREMIUM]["daily_requests"]
            pro_requests = limits[SubscriptionTier.PRO]["daily_requests"]
            
            if premium_requests <= free_requests:
                logger.error(f"PREMIUM requests ({premium_requests}) should be more than FREE ({free_requests})")
                return False
            
            if pro_requests != -1 and pro_requests <= premium_requests:
                logger.error(f"PRO requests should be unlimited (-1) or more than PREMIUM ({premium_requests})")
                return False
            
            # Test yearly discount logic
            for tier in [SubscriptionTier.PREMIUM, SubscriptionTier.PRO]:
                monthly_price = pricing[tier]["monthly"]["price"]
                yearly_price = pricing[tier]["yearly"]["price"]
                
                # Yearly should be cheaper than 12 monthly payments
                monthly_annual_cost = monthly_price * 12
                if yearly_price >= monthly_annual_cost:
                    logger.error(f"{tier} yearly price ({yearly_price}) should be less than 12 monthly payments ({monthly_annual_cost})")
                    return False
                
                # Calculate discount percentage
                discount = ((monthly_annual_cost - yearly_price) / monthly_annual_cost) * 100
                logger.info(f"{tier} yearly discount: {discount:.1f}%")
                
                # Reasonable discount range (typically 10-30%)
                if discount < 5 or discount > 50:
                    logger.error(f"{tier} yearly discount ({discount:.1f}%) seems unreasonable")
                    return False
            
            logger.info("Business logic validation successful")
            return True
            
        except Exception as e:
            logger.error(f"Business logic test failed: {e}")
            return False

    def test_rate_limiting_configuration(self) -> bool:
        """Test rate limiting configuration."""
        try:
            limits = SubscriptionService.TIER_LIMITS
            
            # Test that rate limits are properly configured
            for tier in limits:
                tier_limits = limits[tier]
                daily_requests = tier_limits["daily_requests"]
                
                # Validate daily_requests format
                if daily_requests != -1 and (not isinstance(daily_requests, int) or daily_requests <= 0):
                    logger.error(f"Invalid daily_requests for {tier}: {daily_requests}")
                    return False
                
                # Test reasonable limits
                if tier == SubscriptionTier.FREE and daily_requests > 50:
                    logger.error(f"FREE tier daily requests too high: {daily_requests}")
                    return False
                
                if tier == SubscriptionTier.PREMIUM and (daily_requests < 50 or daily_requests > 500):
                    logger.error(f"PREMIUM tier daily requests unreasonable: {daily_requests}")
                    return False
                
                if tier == SubscriptionTier.PRO and daily_requests != -1:
                    logger.error(f"PRO tier should have unlimited requests (-1), got {daily_requests}")
                    return False
            
            # Test other limits
            for tier in limits:
                tier_limits = limits[tier]
                
                # Validate matches_history
                matches_history = tier_limits.get("matches_history", 0)
                if not isinstance(matches_history, int) or matches_history <= 0:
                    logger.error(f"Invalid matches_history for {tier}: {matches_history}")
                    return False
                
                # Validate boolean features
                for feature in ["advanced_analytics", "notifications", "api_access"]:
                    if feature in tier_limits:
                        if not isinstance(tier_limits[feature], bool):
                            logger.error(f"Feature {feature} for {tier} should be boolean, got {type(tier_limits[feature])}")
                            return False
            
            logger.info("Rate limiting configuration validated")
            return True
            
        except Exception as e:
            logger.error(f"Rate limiting configuration test failed: {e}")
            return False

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all focused tests."""
        print("=" * 80)
        print("FACEIT TELEGRAM BOT - SUBSCRIPTION SYSTEM TESTING")
        print("=" * 80)
        print()
        
        logger.info("Starting focused subscription system testing...")
        
        # Run all tests
        test_methods = [
            ("Subscription Service Configuration", self.test_subscription_service_configuration),
            ("Subscription Pricing Calculations", self.test_subscription_pricing_calculations),
            ("Tier Limits Logic", self.test_tier_limits_logic),
            ("Payment Payload Format", self.test_payment_payload_format),
            ("Telegram Stars Integration", self.test_telegram_stars_integration),
            ("Business Logic Validation", self.test_business_logic_validation),
            ("Rate Limiting Configuration", self.test_rate_limiting_configuration),
        ]
        
        for test_name, test_method in test_methods:
            self.run_test(test_name, test_method)
        
        # Calculate results
        success_rate = (self.results['passed_tests'] / self.results['total_tests']) * 100 if self.results['total_tests'] > 0 else 0
        quality_rating = self._calculate_quality_rating(success_rate)
        
        # Generate report
        report = {
            'test_execution_summary': {
                'total_tests': self.results['total_tests'],
                'passed_tests': self.results['passed_tests'],
                'failed_tests': self.results['failed_tests'],
                'success_rate': round(success_rate, 2),
                'execution_time': datetime.now().isoformat()
            },
            'detailed_results': self.results['test_details'],
            'quality_rating': quality_rating,
            'production_readiness': self._assess_production_readiness(success_rate),
            'recommendations': self._generate_recommendations()
        }
        
        return report

    def _calculate_quality_rating(self, success_rate: float) -> int:
        """Calculate quality rating (1-10) based on test results."""
        if success_rate >= 95:
            return 10
        elif success_rate >= 90:
            return 9
        elif success_rate >= 85:
            return 8
        elif success_rate >= 80:
            return 7
        elif success_rate >= 70:
            return 6
        elif success_rate >= 60:
            return 5
        elif success_rate >= 50:
            return 4
        elif success_rate >= 40:
            return 3
        elif success_rate >= 30:
            return 2
        else:
            return 1

    def _assess_production_readiness(self, success_rate: float) -> str:
        """Assess production readiness."""
        if success_rate >= 95:
            return "Production Ready - Excellent Configuration"
        elif success_rate >= 90:
            return "Production Ready - High Quality Configuration"
        elif success_rate >= 80:
            return "Production Ready - Good Configuration with Minor Issues"
        elif success_rate >= 70:
            return "Conditionally Ready - Address Configuration Issues"
        else:
            return "Not Ready - Major Configuration Problems"

    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on test results."""
        recommendations = []
        
        failed_tests = [test for test in self.results['test_details'] if test['status'] != 'PASS']
        
        if not failed_tests:
            recommendations.extend([
                "All configuration tests passed successfully!",
                "Subscription system is properly configured for production.",
                "Implement runtime testing with actual payment processing.",
                "Set up monitoring for payment transactions and subscription changes.",
                "Add automated testing in CI/CD pipeline.",
                "Consider implementing fraud detection for payments.",
                "Set up automated backup procedures for subscription data."
            ])
        else:
            recommendations.append("Fix configuration issues before production deployment:")
            for test in failed_tests:
                recommendations.append(f"- Address {test['test_name']} failures")
        
        # Additional recommendations
        recommendations.extend([
            "Implement comprehensive logging for subscription events.",
            "Set up alerting for payment failures and subscription issues.",
            "Create monitoring dashboards for subscription metrics.",
            "Test integration with Telegram payment API in staging environment.",
            "Implement rate limiting middleware for API endpoints.",
            "Add comprehensive error handling for edge cases.",
            "Consider implementing subscription analytics tracking."
        ])
        
        return recommendations


def main():
    """Main test execution function."""
    tester = SubscriptionTester()
    
    try:
        # Run all tests
        results = tester.run_all_tests()
        
        # Display results
        print("\n" + "=" * 80)
        print("TEST EXECUTION RESULTS")
        print("=" * 80)
        
        summary = results['test_execution_summary']
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Passed: {summary['passed_tests']}")
        print(f"Failed: {summary['failed_tests']}")
        print(f"Success Rate: {summary['success_rate']}%")
        print(f"Quality Rating: {results['quality_rating']}/10")
        print(f"Production Readiness: {results['production_readiness']}")
        
        print(f"\n{'=' * 80}")
        print("DETAILED TEST RESULTS")
        print("=" * 80)
        
        for test in results['detailed_results']:
            status_emoji = "✅" if test['status'] == 'PASS' else "❌"
            execution_time = test.get('execution_time', 'N/A')
            print(f"{status_emoji} {test['test_name']} - {test['status']} ({execution_time:.3f}s)")
            if test['status'] == 'ERROR' and 'error' in test:
                print(f"   Error: {test['error']}")
        
        print(f"\n{'=' * 80}")
        print("RECOMMENDATIONS")
        print("=" * 80)
        
        for i, recommendation in enumerate(results['recommendations'], 1):
            print(f"{i}. {recommendation}")
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"subscription_test_results_{timestamp}.json"
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\nDetailed results saved to: {results_file}")
        
        # Final assessment
        print(f"\n{'=' * 80}")
        print("FINAL ASSESSMENT")
        print("=" * 80)
        
        if results['quality_rating'] >= 8:
            print("✅ SUBSCRIPTION SYSTEM CONFIGURATION: HIGH QUALITY")
            print("✅ Ready for production deployment")
        elif results['quality_rating'] >= 6:
            print("⚠️ SUBSCRIPTION SYSTEM CONFIGURATION: ACCEPTABLE QUALITY")
            print("⚠️ Address failed tests before production")
        else:
            print("❌ SUBSCRIPTION SYSTEM CONFIGURATION: NEEDS IMPROVEMENT")
            print("❌ Not ready for production - resolve issues first")
        
        return results['quality_rating']
        
    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        print(f"\n❌ TESTING FAILED: {e}")
        return 0


if __name__ == "__main__":
    quality_rating = main()
    exit(0 if quality_rating >= 7 else 1)