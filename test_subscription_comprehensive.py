#!/usr/bin/env python3
"""
Comprehensive Subscription System Testing Suite

This script tests all aspects of the FACEIT Telegram bot's subscription system:
- Subscription tier validation and limits
- Payment processing with Telegram Stars
- Rate limiting and usage tracking
- Referral system functionality
- Business logic validation
- Security and error handling

Author: Claude Code Payment Integration Specialist
"""

import asyncio
import sys
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import uuid

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.models import SubscriptionTier, PaymentStatus
from services.subscription import SubscriptionService
from database.repositories.subscription import SubscriptionRepository, PaymentRepository
from database.repositories.user import UserRepository
from utils.storage import storage as json_storage

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SubscriptionSystemTester:
    """Comprehensive subscription system testing suite."""
    
    def __init__(self):
        """Initialize test suite with repositories and service."""
        self.subscription_repo = SubscriptionRepository()
        self.payment_repo = PaymentRepository()
        self.user_repo = UserRepository()
        self.subscription_service = SubscriptionService(
            self.subscription_repo,
            self.payment_repo,
            self.user_repo
        )
        
        # Test configuration
        self.test_users = []
        self.test_payments = []
        self.test_results = {
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'test_details': []
        }
        
        # Expected subscription limits
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
        
        # Expected pricing (in Telegram Stars)
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

    async def setup_test_environment(self):
        """Set up test environment with sample data."""
        logger.info("Setting up test environment...")
        
        try:
            # Create test users in JSON storage (legacy system)
            for i in range(1, 6):
                telegram_user_id = 1000000 + i
                test_user_data = {
                    'user_id': telegram_user_id,
                    'faceit_player_id': f'test_player_{i}',
                    'faceit_nickname': f'TestPlayer{i}',
                    'waiting_for_nickname': False,
                    'created_at': datetime.now().isoformat()
                }
                
                await json_storage.save_user_data(test_user_data)
                self.test_users.append(telegram_user_id)
                
            logger.info(f"Created {len(self.test_users)} test users")
            
        except Exception as e:
            logger.error(f"Failed to setup test environment: {e}")
            raise

    async def run_test(self, test_name: str, test_func, *args, **kwargs) -> bool:
        """Run a single test and record results."""
        self.test_results['total_tests'] += 1
        
        try:
            logger.info(f"Running test: {test_name}")
            start_time = datetime.now()
            
            result = await test_func(*args, **kwargs)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            if result:
                self.test_results['passed_tests'] += 1
                status = "PASS"
                logger.info(f"✅ {test_name} - PASSED ({execution_time:.2f}s)")
            else:
                self.test_results['failed_tests'] += 1
                status = "FAIL"
                logger.error(f"❌ {test_name} - FAILED ({execution_time:.2f}s)")
            
            self.test_results['test_details'].append({
                'test_name': test_name,
                'status': status,
                'execution_time': execution_time,
                'timestamp': datetime.now().isoformat()
            })
            
            return result
            
        except Exception as e:
            self.test_results['failed_tests'] += 1
            logger.error(f"❌ {test_name} - ERROR: {e}")
            
            self.test_results['test_details'].append({
                'test_name': test_name,
                'status': "ERROR",
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
            
            return False

    # ========================= SUBSCRIPTION TIER TESTS =========================

    async def test_subscription_tier_limits(self) -> bool:
        """Test subscription tier limits validation."""
        try:
            # Test service pricing configuration
            service_pricing = self.subscription_service.PRICING
            service_limits = self.subscription_service.TIER_LIMITS
            
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
            
            logger.info("✅ All subscription tier limits validated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Subscription tier limits test failed: {e}")
            return False

    async def test_rate_limiting_enforcement(self) -> bool:
        """Test rate limiting enforcement for different tiers."""
        try:
            if not self.test_users:
                logger.error("No test users available")
                return False
            
            telegram_user_id = self.test_users[0]
            
            # Test FREE tier rate limiting (10 requests/day)
            logger.info("Testing FREE tier rate limiting...")
            
            # Get user subscription (should be FREE by default)
            subscription_result = await self.subscription_service.get_user_subscription(telegram_user_id)
            if not subscription_result.success:
                logger.error(f"Failed to get user subscription: {subscription_result.error}")
                return False
            
            subscription_data = subscription_result.data
            if subscription_data["tier"] != "free":
                logger.error(f"Expected FREE tier, got {subscription_data['tier']}")
                return False
            
            # Test rate limit checking
            for request_num in range(12):  # Try 12 requests (should fail after 10)
                rate_limit_result = await self.subscription_service.check_rate_limit(telegram_user_id)
                
                if request_num < 10:
                    # First 10 requests should be allowed
                    if not rate_limit_result.success:
                        logger.error(f"Request {request_num + 1} should be allowed but was rejected")
                        return False
                    
                    # Increment usage
                    usage_result = await self.subscription_service.increment_usage(telegram_user_id)
                    if not usage_result.success:
                        logger.error(f"Failed to increment usage for request {request_num + 1}")
                        return False
                else:
                    # Requests 11+ should be rejected
                    if rate_limit_result.success:
                        logger.error(f"Request {request_num + 1} should be rejected but was allowed")
                        return False
                    
                    # Should be a RateLimitError
                    if "rate limit" not in str(rate_limit_result.error).lower():
                        logger.error(f"Expected rate limit error, got: {rate_limit_result.error}")
                        return False
            
            logger.info("✅ FREE tier rate limiting working correctly")
            
            # Test PREMIUM tier upgrade and limits
            logger.info("Testing PREMIUM tier upgrade...")
            
            # Upgrade to PREMIUM
            upgrade_result = await self.subscription_service.process_successful_payment(
                telegram_user_id=telegram_user_id,
                payment_payload=f"premium_monthly_{telegram_user_id}",
                telegram_payment_charge_id="test_charge_123",
                provider_payment_charge_id="provider_charge_123"
            )
            
            if not upgrade_result.success:
                logger.error(f"Failed to upgrade to PREMIUM: {upgrade_result.error}")
                return False
            
            # Verify PREMIUM limits (100 requests/day)
            subscription_result = await self.subscription_service.get_user_subscription(telegram_user_id)
            if not subscription_result.success:
                logger.error(f"Failed to get updated subscription: {subscription_result.error}")
                return False
            
            updated_subscription = subscription_result.data
            if updated_subscription["tier"] != "premium":
                logger.error(f"Expected PREMIUM tier after upgrade, got {updated_subscription['tier']}")
                return False
            
            if updated_subscription["limits"]["daily_requests"] != 100:
                logger.error(f"Expected 100 daily requests for PREMIUM, got {updated_subscription['limits']['daily_requests']}")
                return False
            
            logger.info("✅ Rate limiting enforcement test passed")
            return True
            
        except Exception as e:
            logger.error(f"Rate limiting test failed: {e}")
            return False

    # ========================= PAYMENT PROCESSING TESTS =========================

    async def test_payment_invoice_creation(self) -> bool:
        """Test payment invoice creation for different tiers and durations."""
        try:
            if not self.test_users:
                logger.error("No test users available")
                return False
            
            telegram_user_id = self.test_users[1]
            
            # Test PREMIUM monthly invoice
            logger.info("Testing PREMIUM monthly invoice creation...")
            
            invoice_result = await self.subscription_service.create_payment_invoice(
                telegram_user_id=telegram_user_id,
                tier=SubscriptionTier.PREMIUM,
                duration="monthly"
            )
            
            if not invoice_result.success:
                logger.error(f"Failed to create PREMIUM monthly invoice: {invoice_result.error}")
                return False
            
            invoice_data = invoice_result.data
            
            # Validate invoice structure
            required_fields = ["payment_id", "title", "description", "payload", "currency", "prices", "tier", "duration", "duration_days"]
            for field in required_fields:
                if field not in invoice_data:
                    logger.error(f"Missing field in invoice: {field}")
                    return False
            
            # Validate pricing
            if invoice_data["prices"][0]["amount"] != 199:
                logger.error(f"Expected PREMIUM monthly price 199, got {invoice_data['prices'][0]['amount']}")
                return False
            
            if invoice_data["currency"] != "XTR":
                logger.error(f"Expected currency XTR, got {invoice_data['currency']}")
                return False
            
            if invoice_data["duration_days"] != 30:
                logger.error(f"Expected 30 days for monthly, got {invoice_data['duration_days']}")
                return False
            
            logger.info("✅ PREMIUM monthly invoice creation successful")
            
            # Test PRO yearly invoice
            logger.info("Testing PRO yearly invoice creation...")
            
            pro_invoice_result = await self.subscription_service.create_payment_invoice(
                telegram_user_id=telegram_user_id,
                tier=SubscriptionTier.PRO,
                duration="yearly"
            )
            
            if not pro_invoice_result.success:
                logger.error(f"Failed to create PRO yearly invoice: {pro_invoice_result.error}")
                return False
            
            pro_invoice = pro_invoice_result.data
            
            if pro_invoice["prices"][0]["amount"] != 2999:
                logger.error(f"Expected PRO yearly price 2999, got {pro_invoice['prices'][0]['amount']}")
                return False
            
            if pro_invoice["duration_days"] != 365:
                logger.error(f"Expected 365 days for yearly, got {pro_invoice['duration_days']}")
                return False
            
            logger.info("✅ PRO yearly invoice creation successful")
            
            # Test invalid tier
            invalid_invoice_result = await self.subscription_service.create_payment_invoice(
                telegram_user_id=telegram_user_id,
                tier=SubscriptionTier.FREE,  # Should not be allowed
                duration="monthly"
            )
            
            if invalid_invoice_result.success:
                logger.error("FREE tier invoice creation should fail but succeeded")
                return False
            
            logger.info("✅ Invalid tier invoice creation correctly rejected")
            
            return True
            
        except Exception as e:
            logger.error(f"Payment invoice creation test failed: {e}")
            return False

    async def test_payment_processing_flow(self) -> bool:
        """Test complete payment processing flow."""
        try:
            if not self.test_users:
                logger.error("No test users available")
                return False
            
            telegram_user_id = self.test_users[2]
            
            # Step 1: Create payment invoice
            logger.info("Step 1: Creating payment invoice...")
            
            invoice_result = await self.subscription_service.create_payment_invoice(
                telegram_user_id=telegram_user_id,
                tier=SubscriptionTier.PREMIUM,
                duration="monthly"
            )
            
            if not invoice_result.success:
                logger.error(f"Failed to create invoice: {invoice_result.error}")
                return False
            
            invoice = invoice_result.data
            payment_payload = invoice["payload"]
            
            logger.info(f"✅ Invoice created with payload: {payment_payload}")
            
            # Step 2: Process successful payment
            logger.info("Step 2: Processing successful payment...")
            
            payment_result = await self.subscription_service.process_successful_payment(
                telegram_user_id=telegram_user_id,
                payment_payload=payment_payload,
                telegram_payment_charge_id="test_charge_456",
                provider_payment_charge_id="provider_charge_456"
            )
            
            if not payment_result.success:
                logger.error(f"Failed to process payment: {payment_result.error}")
                return False
            
            payment_data = payment_result.data
            
            # Validate payment processing results
            if payment_data["subscription"]["tier"] != "premium":
                logger.error(f"Expected PREMIUM tier after payment, got {payment_data['subscription']['tier']}")
                return False
            
            if not payment_data["payment_completed"]:
                logger.error("Payment should be marked as completed")
                return False
            
            logger.info("✅ Payment processed successfully")
            
            # Step 3: Verify subscription upgrade
            logger.info("Step 3: Verifying subscription upgrade...")
            
            subscription_result = await self.subscription_service.get_user_subscription(telegram_user_id)
            if not subscription_result.success:
                logger.error(f"Failed to get updated subscription: {subscription_result.error}")
                return False
            
            subscription = subscription_result.data
            
            if subscription["tier"] != "premium":
                logger.error(f"Subscription not upgraded correctly: {subscription['tier']}")
                return False
            
            if subscription["limits"]["daily_requests"] != 100:
                logger.error(f"PREMIUM limits not applied: {subscription['limits']['daily_requests']}")
                return False
            
            # Check expiration date
            if not subscription["expires_at"]:
                logger.error("PREMIUM subscription should have expiration date")
                return False
            
            logger.info("✅ Subscription upgrade verified")
            
            # Step 4: Test invalid payment payload
            logger.info("Step 4: Testing invalid payment payload...")
            
            invalid_result = await self.subscription_service.process_successful_payment(
                telegram_user_id=telegram_user_id,
                payment_payload="invalid_payload_format",
                telegram_payment_charge_id="test_charge_invalid",
                provider_payment_charge_id="provider_charge_invalid"
            )
            
            if invalid_result.success:
                logger.error("Invalid payment payload should fail but succeeded")
                return False
            
            logger.info("✅ Invalid payment payload correctly rejected")
            
            return True
            
        except Exception as e:
            logger.error(f"Payment processing flow test failed: {e}")
            return False

    # ========================= REFERRAL SYSTEM TESTS =========================

    async def test_referral_system(self) -> bool:
        """Test referral system functionality."""
        try:
            if len(self.test_users) < 2:
                logger.error("Need at least 2 test users for referral testing")
                return False
            
            referrer_id = self.test_users[3]
            referee_id = self.test_users[4]
            
            # Step 1: Generate referral code for referrer
            logger.info("Step 1: Generating referral code...")
            
            referral_result = await self.subscription_service.generate_referral_code(referrer_id)
            if not referral_result.success:
                logger.error(f"Failed to generate referral code: {referral_result.error}")
                return False
            
            referral_code = referral_result.data
            logger.info(f"✅ Generated referral code: {referral_code}")
            
            # Step 2: Apply referral code by referee
            logger.info("Step 2: Applying referral code...")
            
            apply_result = await self.subscription_service.apply_referral_code(
                telegram_user_id=referee_id,
                referral_code=referral_code
            )
            
            if not apply_result.success:
                logger.error(f"Failed to apply referral code: {apply_result.error}")
                return False
            
            apply_data = apply_result.data
            
            if not apply_data["success"]:
                logger.error("Referral application should be successful")
                return False
            
            if apply_data["bonus_tier"] != "premium":
                logger.error(f"Expected PREMIUM bonus tier, got {apply_data['bonus_tier']}")
                return False
            
            if apply_data["bonus_days"] != 7:
                logger.error(f"Expected 7 bonus days, got {apply_data['bonus_days']}")
                return False
            
            logger.info("✅ Referral code applied successfully")
            
            # Step 3: Verify both users got bonuses
            logger.info("Step 3: Verifying referral bonuses...")
            
            # Check referee subscription
            referee_subscription = await self.subscription_service.get_user_subscription(referee_id)
            if not referee_subscription.success:
                logger.error(f"Failed to get referee subscription: {referee_subscription.error}")
                return False
            
            referee_data = referee_subscription.data
            if referee_data["tier"] != "premium":
                logger.error(f"Referee should have PREMIUM tier, got {referee_data['tier']}")
                return False
            
            # Check referrer subscription (should get 30 days bonus)
            referrer_subscription = await self.subscription_service.get_user_subscription(referrer_id)
            if not referrer_subscription.success:
                logger.error(f"Failed to get referrer subscription: {referrer_subscription.error}")
                return False
            
            referrer_data = referrer_subscription.data
            if referrer_data["tier"] != "premium":
                logger.error(f"Referrer should have PREMIUM tier, got {referrer_data['tier']}")
                return False
            
            logger.info("✅ Referral bonuses verified")
            
            # Step 4: Test invalid referral scenarios
            logger.info("Step 4: Testing invalid referral scenarios...")
            
            # Try to apply same code again (should fail)
            duplicate_result = await self.subscription_service.apply_referral_code(
                telegram_user_id=referee_id,
                referral_code=referral_code
            )
            
            if duplicate_result.success:
                logger.error("Duplicate referral application should fail but succeeded")
                return False
            
            # Try invalid referral code
            invalid_result = await self.subscription_service.apply_referral_code(
                telegram_user_id=self.test_users[0],
                referral_code="INVALID123"
            )
            
            if invalid_result.success:
                logger.error("Invalid referral code should fail but succeeded")
                return False
            
            logger.info("✅ Invalid referral scenarios correctly handled")
            
            return True
            
        except Exception as e:
            logger.error(f"Referral system test failed: {e}")
            return False

    # ========================= BUSINESS LOGIC TESTS =========================

    async def test_subscription_expiration(self) -> bool:
        """Test subscription expiration handling."""
        try:
            # Note: This test would require database access to test subscription expiration
            # For now, we'll test the business logic through the service
            
            logger.info("Testing subscription expiration logic...")
            
            # Test expiring subscriptions check
            expiring_result = await self.subscription_service.get_expiring_subscriptions(days_ahead=7)
            
            if not expiring_result.success:
                logger.error(f"Failed to get expiring subscriptions: {expiring_result.error}")
                return False
            
            expiring_data = expiring_result.data
            logger.info(f"Found {len(expiring_data)} expiring subscriptions")
            
            # Test subscription expiration check
            expire_result = await self.subscription_service.check_and_expire_subscriptions()
            
            if not expire_result.success:
                logger.error(f"Failed to check expired subscriptions: {expire_result.error}")
                return False
            
            expire_data = expire_result.data
            logger.info(f"Expired {expire_data['expired_count']} subscriptions")
            
            logger.info("✅ Subscription expiration logic working")
            return True
            
        except Exception as e:
            logger.error(f"Subscription expiration test failed: {e}")
            return False

    async def test_analytics_and_reporting(self) -> bool:
        """Test analytics and reporting functionality."""
        try:
            logger.info("Testing subscription analytics...")
            
            # Get subscription analytics
            analytics_result = await self.subscription_service.get_subscription_analytics()
            
            if not analytics_result.success:
                logger.error(f"Failed to get analytics: {analytics_result.error}")
                return False
            
            analytics = analytics_result.data
            
            # Validate analytics structure
            required_sections = ["subscription_overview", "revenue_overview", "analysis_period", "performance_metrics"]
            for section in required_sections:
                if section not in analytics:
                    logger.error(f"Missing analytics section: {section}")
                    return False
            
            logger.info("✅ Analytics structure validated")
            
            # Validate subscription overview
            sub_overview = analytics["subscription_overview"]
            if "total_subscriptions" not in sub_overview:
                logger.error("Missing total_subscriptions in overview")
                return False
            
            if "tier_distribution" not in sub_overview:
                logger.error("Missing tier_distribution in overview")
                return False
            
            logger.info("✅ Subscription overview validated")
            
            # Validate revenue overview
            revenue_overview = analytics["revenue_overview"]
            if "total_revenue" not in revenue_overview:
                logger.error("Missing total_revenue in overview")
                return False
            
            if "total_payments" not in revenue_overview:
                logger.error("Missing total_payments in overview")
                return False
            
            logger.info("✅ Revenue overview validated")
            
            return True
            
        except Exception as e:
            logger.error(f"Analytics test failed: {e}")
            return False

    # ========================= SECURITY TESTS =========================

    async def test_payment_security(self) -> bool:
        """Test payment security measures."""
        try:
            if not self.test_users:
                logger.error("No test users available")
                return False
            
            telegram_user_id = self.test_users[0]
            
            logger.info("Testing payment security measures...")
            
            # Test user ID mismatch in payment payload
            logger.info("Testing user ID mismatch protection...")
            
            # Create legitimate invoice
            invoice_result = await self.subscription_service.create_payment_invoice(
                telegram_user_id=telegram_user_id,
                tier=SubscriptionTier.PREMIUM,
                duration="monthly"
            )
            
            if not invoice_result.success:
                logger.error(f"Failed to create test invoice: {invoice_result.error}")
                return False
            
            # Try to process payment with mismatched user ID
            different_user_id = telegram_user_id + 999
            mismatch_result = await self.subscription_service.process_successful_payment(
                telegram_user_id=different_user_id,  # Different user
                payment_payload=invoice_result.data["payload"],  # Original user's payload
                telegram_payment_charge_id="test_charge_security",
                provider_payment_charge_id="provider_charge_security"
            )
            
            if mismatch_result.success:
                logger.error("Payment with mismatched user ID should fail but succeeded")
                return False
            
            if "mismatch" not in str(mismatch_result.error).lower():
                logger.error(f"Expected user ID mismatch error, got: {mismatch_result.error}")
                return False
            
            logger.info("✅ User ID mismatch protection working")
            
            # Test malformed payment payload
            logger.info("Testing malformed payload protection...")
            
            malformed_result = await self.subscription_service.process_successful_payment(
                telegram_user_id=telegram_user_id,
                payment_payload="malformed_payload_without_proper_format",
                telegram_payment_charge_id="test_charge_malformed",
                provider_payment_charge_id="provider_charge_malformed"
            )
            
            if malformed_result.success:
                logger.error("Malformed payload should fail but succeeded")
                return False
            
            logger.info("✅ Malformed payload protection working")
            
            # Test invalid tier in processing
            logger.info("Testing invalid tier protection...")
            
            invalid_tier_result = await self.subscription_service.process_successful_payment(
                telegram_user_id=telegram_user_id,
                payment_payload=f"invalid_tier_monthly_{telegram_user_id}",
                telegram_payment_charge_id="test_charge_invalid_tier",
                provider_payment_charge_id="provider_charge_invalid_tier"
            )
            
            if invalid_tier_result.success:
                logger.error("Invalid tier should fail but succeeded")
                return False
            
            logger.info("✅ Invalid tier protection working")
            
            return True
            
        except Exception as e:
            logger.error(f"Payment security test failed: {e}")
            return False

    # ========================= USER EXPERIENCE TESTS =========================

    async def test_user_experience_flow(self) -> bool:
        """Test complete user experience flow."""
        try:
            if not self.test_users:
                logger.error("No test users available")
                return False
            
            telegram_user_id = self.test_users[0]
            
            logger.info("Testing complete user experience flow...")
            
            # Step 1: New user gets default subscription
            logger.info("Step 1: Checking default subscription...")
            
            subscription_result = await self.subscription_service.get_user_subscription(
                telegram_user_id=telegram_user_id,
                include_usage_stats=True
            )
            
            if not subscription_result.success:
                logger.error(f"Failed to get user subscription: {subscription_result.error}")
                return False
            
            subscription = subscription_result.data
            
            if subscription["tier"] != "free":
                logger.error(f"New user should have FREE tier, got {subscription['tier']}")
                return False
            
            if not subscription["usage"]["can_make_request"]:
                logger.error("New user should be able to make requests")
                return False
            
            if subscription["usage"]["remaining_requests"] != 10:
                logger.error(f"New user should have 10 remaining requests, got {subscription['usage']['remaining_requests']}")
                return False
            
            logger.info("✅ Default subscription correct")
            
            # Step 2: User makes some requests
            logger.info("Step 2: Testing request usage...")
            
            for i in range(5):
                rate_check = await self.subscription_service.check_rate_limit(telegram_user_id)
                if not rate_check.success:
                    logger.error(f"Request {i+1} should be allowed")
                    return False
                
                usage_increment = await self.subscription_service.increment_usage(telegram_user_id)
                if not usage_increment.success:
                    logger.error(f"Failed to increment usage for request {i+1}")
                    return False
            
            # Check updated usage
            updated_subscription = await self.subscription_service.get_user_subscription(
                telegram_user_id=telegram_user_id,
                include_usage_stats=True
            )
            
            if not updated_subscription.success:
                logger.error("Failed to get updated subscription")
                return False
            
            updated_data = updated_subscription.data
            if updated_data["usage"]["remaining_requests"] != 5:
                logger.error(f"Should have 5 remaining requests, got {updated_data['usage']['remaining_requests']}")
                return False
            
            logger.info("✅ Request usage tracking working")
            
            # Step 3: User upgrades subscription
            logger.info("Step 3: Testing subscription upgrade...")
            
            # Create and process payment
            invoice_result = await self.subscription_service.create_payment_invoice(
                telegram_user_id=telegram_user_id,
                tier=SubscriptionTier.PREMIUM,
                duration="monthly"
            )
            
            if not invoice_result.success:
                logger.error(f"Failed to create upgrade invoice: {invoice_result.error}")
                return False
            
            payment_result = await self.subscription_service.process_successful_payment(
                telegram_user_id=telegram_user_id,
                payment_payload=invoice_result.data["payload"],
                telegram_payment_charge_id="test_charge_upgrade",
                provider_payment_charge_id="provider_charge_upgrade"
            )
            
            if not payment_result.success:
                logger.error(f"Failed to process upgrade payment: {payment_result.error}")
                return False
            
            # Verify upgrade
            upgraded_subscription = await self.subscription_service.get_user_subscription(
                telegram_user_id=telegram_user_id,
                include_usage_stats=True
            )
            
            if not upgraded_subscription.success:
                logger.error("Failed to get upgraded subscription")
                return False
            
            upgraded_data = upgraded_subscription.data
            if upgraded_data["tier"] != "premium":
                logger.error(f"Should be PREMIUM tier after upgrade, got {upgraded_data['tier']}")
                return False
            
            if upgraded_data["limits"]["daily_requests"] != 100:
                logger.error(f"Should have 100 daily requests after upgrade, got {upgraded_data['limits']['daily_requests']}")
                return False
            
            if not upgraded_data["limits"]["advanced_analytics"]:
                logger.error("Should have advanced analytics after PREMIUM upgrade")
                return False
            
            logger.info("✅ Subscription upgrade working")
            
            return True
            
        except Exception as e:
            logger.error(f"User experience flow test failed: {e}")
            return False

    # ========================= MAIN TEST RUNNER =========================

    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all subscription system tests."""
        logger.info("🚀 Starting comprehensive subscription system testing...")
        
        try:
            # Setup test environment
            await self.setup_test_environment()
            
            # Run all test categories
            test_categories = [
                ("Subscription Tier Validation", self.test_subscription_tier_limits),
                ("Rate Limiting Enforcement", self.test_rate_limiting_enforcement),
                ("Payment Invoice Creation", self.test_payment_invoice_creation),
                ("Payment Processing Flow", self.test_payment_processing_flow),
                ("Referral System", self.test_referral_system),
                ("Subscription Expiration", self.test_subscription_expiration),
                ("Analytics and Reporting", self.test_analytics_and_reporting),
                ("Payment Security", self.test_payment_security),
                ("User Experience Flow", self.test_user_experience_flow),
            ]
            
            logger.info(f"Running {len(test_categories)} test categories...")
            
            for test_name, test_func in test_categories:
                await self.run_test(test_name, test_func)
            
            # Calculate overall results
            success_rate = (self.test_results['passed_tests'] / self.test_results['total_tests']) * 100 if self.test_results['total_tests'] > 0 else 0
            
            # Generate final report
            final_report = {
                'test_execution_summary': {
                    'total_tests': self.test_results['total_tests'],
                    'passed_tests': self.test_results['passed_tests'],
                    'failed_tests': self.test_results['failed_tests'],
                    'success_rate': round(success_rate, 2),
                    'execution_time': datetime.now().isoformat()
                },
                'detailed_results': self.test_results['test_details'],
                'quality_rating': self._calculate_quality_rating(success_rate),
                'production_readiness_assessment': self._assess_production_readiness(success_rate),
                'recommendations': self._generate_recommendations()
            }
            
            return final_report
            
        except Exception as e:
            logger.error(f"Test execution failed: {e}")
            return {
                'error': str(e),
                'test_execution_summary': self.test_results,
                'quality_rating': 1,
                'production_readiness_assessment': 'Not Ready - Testing Failed'
            }

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
        """Assess production readiness based on test results."""
        if success_rate >= 95:
            return "Production Ready - Excellent Quality"
        elif success_rate >= 90:
            return "Production Ready - High Quality"
        elif success_rate >= 85:
            return "Production Ready - Good Quality with Minor Issues"
        elif success_rate >= 80:
            return "Conditionally Ready - Address Failed Tests"
        elif success_rate >= 70:
            return "Development Phase - Significant Issues Found"
        else:
            return "Not Ready - Major Issues Require Resolution"

    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on test results."""
        recommendations = []
        
        failed_tests = [test for test in self.test_results['test_details'] if test['status'] != 'PASS']
        
        if not failed_tests:
            recommendations.append("All tests passed! System is ready for production deployment.")
            recommendations.append("Consider implementing additional monitoring for payment processing.")
            recommendations.append("Set up automated testing in CI/CD pipeline.")
        else:
            recommendations.append("Review and fix failed test cases before production deployment.")
            
            for test in failed_tests:
                if 'payment' in test['test_name'].lower():
                    recommendations.append("Critical: Payment processing issues detected - require immediate attention.")
                elif 'security' in test['test_name'].lower():
                    recommendations.append("Security issues found - must be resolved before production.")
                elif 'rate' in test['test_name'].lower():
                    recommendations.append("Rate limiting issues detected - review subscription limits.")
        
        # General recommendations
        recommendations.extend([
            "Implement comprehensive logging for payment transactions.",
            "Set up monitoring dashboards for subscription metrics.",
            "Create automated backup procedures for payment data.",
            "Implement fraud detection mechanisms.",
            "Add comprehensive error handling for edge cases.",
            "Set up alerting for failed payments and subscription issues."
        ])
        
        return recommendations

    async def cleanup_test_environment(self):
        """Clean up test environment after testing."""
        logger.info("Cleaning up test environment...")
        
        try:
            # Clean up test users from JSON storage
            for user_id in self.test_users:
                try:
                    await json_storage.delete_user(user_id)
                except:
                    pass  # Ignore cleanup errors
            
            logger.info("Test environment cleaned up successfully")
            
        except Exception as e:
            logger.warning(f"Cleanup failed (non-critical): {e}")


async def main():
    """Main test execution function."""
    print("=" * 80)
    print("FACEIT TELEGRAM BOT - SUBSCRIPTION SYSTEM TESTING")
    print("=" * 80)
    print()
    
    tester = SubscriptionSystemTester()
    
    try:
        # Run comprehensive tests
        results = await tester.run_all_tests()
        
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
        print(f"Production Readiness: {results['production_readiness_assessment']}")
        
        print(f"\n{'='*80}")
        print("DETAILED TEST RESULTS")
        print("=" * 80)
        
        for test in results['detailed_results']:
            status_emoji = "✅" if test['status'] == 'PASS' else "❌"
            execution_time = test.get('execution_time', 'N/A')
            print(f"{status_emoji} {test['test_name']} - {test['status']} ({execution_time}s)")
            if test['status'] == 'ERROR' and 'error' in test:
                print(f"   Error: {test['error']}")
        
        print(f"\n{'='*80}")
        print("RECOMMENDATIONS")
        print("=" * 80)
        
        for i, recommendation in enumerate(results['recommendations'], 1):
            print(f"{i}. {recommendation}")
        
        # Save detailed results to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"subscription_test_results_{timestamp}.json"
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n📄 Detailed results saved to: {results_file}")
        
        # Final assessment
        print(f"\n{'='*80}")
        print("FINAL ASSESSMENT")
        print("=" * 80)
        
        if results['quality_rating'] >= 8:
            print("🟢 SUBSCRIPTION SYSTEM: HIGH QUALITY")
            print("✅ Ready for production deployment")
        elif results['quality_rating'] >= 6:
            print("🟡 SUBSCRIPTION SYSTEM: ACCEPTABLE QUALITY")
            print("⚠️  Address failed tests before production")
        else:
            print("🔴 SUBSCRIPTION SYSTEM: NEEDS IMPROVEMENT")
            print("❌ Not ready for production - resolve issues first")
        
        return results['quality_rating']
        
    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        print(f"\n❌ TESTING FAILED: {e}")
        return 0
    
    finally:
        # Cleanup
        try:
            await tester.cleanup_test_environment()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(main())