"""Data Validation utilities for migration consistency checking.

Provides comprehensive validation of data integrity before, during, 
and after migration from JSON to PostgreSQL.
"""

import logging
import json
import asyncio
from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime
from pathlib import Path
import uuid

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, UserSubscription, SubscriptionTier
from database.connection import get_async_session
from utils.storage import DataStorage, UserData

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Exception raised when data validation fails."""
    pass


class ValidationResult:
    """Container for validation results."""
    
    def __init__(self):
        self.is_valid = True
        self.errors = []
        self.warnings = []
        self.stats = {}
        
    def add_error(self, message: str):
        """Add an error to the validation result."""
        self.errors.append(message)
        self.is_valid = False
        logger.error(f"Validation error: {message}")
        
    def add_warning(self, message: str):
        """Add a warning to the validation result."""
        self.warnings.append(message)
        logger.warning(f"Validation warning: {message}")
        
    def set_stat(self, key: str, value: Any):
        """Set a statistic value."""
        self.stats[key] = value
        
    def get_summary(self) -> Dict[str, Any]:
        """Get validation summary."""
        return {
            'is_valid': self.is_valid,
            'error_count': len(self.errors),
            'warning_count': len(self.warnings),
            'errors': self.errors,
            'warnings': self.warnings,
            'stats': self.stats
        }


class DataValidator:
    """Validates data consistency and integrity during migration."""
    
    def __init__(self, json_file_path: str):
        """
        Initialize data validator.
        
        Args:
            json_file_path: Path to the JSON data file
        """
        self.json_file_path = Path(json_file_path)
        self.json_data = None
        
    async def load_json_data(self) -> Dict[str, Any]:
        """
        Load and parse JSON data file.
        
        Returns:
            Parsed JSON data
            
        Raises:
            ValidationError: When JSON file cannot be loaded
        """
        try:
            if not self.json_file_path.exists():
                raise ValidationError(f"JSON file not found: {self.json_file_path}")
            
            content = self.json_file_path.read_text(encoding='utf-8')
            self.json_data = json.loads(content)
            
            logger.info(f"Loaded JSON data from {self.json_file_path}")
            return self.json_data
            
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON format: {e}")
        except Exception as e:
            raise ValidationError(f"Failed to load JSON data: {e}")
    
    def validate_json_structure(self) -> ValidationResult:
        """
        Validate JSON data structure and content.
        
        Returns:
            ValidationResult with structure validation results
        """
        result = ValidationResult()
        
        if not self.json_data:
            result.add_error("JSON data not loaded")
            return result
        
        # Check top-level structure
        if not isinstance(self.json_data, dict):
            result.add_error("JSON data must be a dictionary")
            return result
        
        if 'users' not in self.json_data:
            result.add_error("Missing 'users' key in JSON data")
            return result
        
        users_data = self.json_data['users']
        if not isinstance(users_data, list):
            result.add_error("'users' must be a list")
            return result
        
        result.set_stat('total_users', len(users_data))
        
        # Validate each user record
        user_ids_seen = set()
        users_with_faceit = 0
        subscription_tiers = {'free': 0, 'premium': 0, 'pro': 0, 'unknown': 0}
        
        for i, user in enumerate(users_data):
            user_errors = self._validate_user_record(user, i)
            result.errors.extend(user_errors)
            
            if user_errors:
                result.is_valid = False
            
            # Track user_id uniqueness
            user_id = user.get('user_id')
            if user_id:
                if user_id in user_ids_seen:
                    result.add_error(f"Duplicate user_id found: {user_id}")
                user_ids_seen.add(user_id)
            
            # Count users with FACEIT accounts
            if user.get('faceit_player_id'):
                users_with_faceit += 1
            
            # Count subscription tiers
            subscription = user.get('subscription', {})
            tier = subscription.get('tier', 'free').lower()
            subscription_tiers[tier if tier in subscription_tiers else 'unknown'] += 1
        
        result.set_stat('users_with_faceit', users_with_faceit)
        result.set_stat('subscription_distribution', subscription_tiers)
        result.set_stat('unique_user_ids', len(user_ids_seen))
        
        logger.info(f"JSON structure validation completed. Valid: {result.is_valid}")
        return result
    
    def _validate_user_record(self, user: Dict[str, Any], index: int) -> List[str]:
        """
        Validate individual user record.
        
        Args:
            user: User data dictionary
            index: Index of user in the list
            
        Returns:
            List of validation error messages
        """
        errors = []
        
        # Check required fields
        if 'user_id' not in user:
            errors.append(f"User {index}: Missing required field 'user_id'")
        elif not isinstance(user['user_id'], int) or user['user_id'] <= 0:
            errors.append(f"User {index}: Invalid user_id: {user['user_id']}")
        
        # Validate optional fields
        if 'faceit_player_id' in user and user['faceit_player_id']:
            if not isinstance(user['faceit_player_id'], str):
                errors.append(f"User {index}: faceit_player_id must be a string")
        
        if 'faceit_nickname' in user and user['faceit_nickname']:
            if not isinstance(user['faceit_nickname'], str):
                errors.append(f"User {index}: faceit_nickname must be a string")
        
        # Validate datetime fields
        datetime_fields = ['created_at', 'last_active_at']
        for field in datetime_fields:
            if field in user and user[field]:
                if not self._is_valid_datetime_string(user[field]):
                    errors.append(f"User {index}: Invalid datetime format in {field}: {user[field]}")
        
        # Validate subscription if present
        if 'subscription' in user:
            subscription_errors = self._validate_subscription_record(user['subscription'], index)
            errors.extend(subscription_errors)
        
        return errors
    
    def _validate_subscription_record(self, subscription: Dict[str, Any], user_index: int) -> List[str]:
        """
        Validate subscription record.
        
        Args:
            subscription: Subscription data dictionary
            user_index: Index of parent user
            
        Returns:
            List of validation error messages
        """
        errors = []
        
        if not isinstance(subscription, dict):
            errors.append(f"User {user_index}: subscription must be a dictionary")
            return errors
        
        # Validate tier
        if 'tier' in subscription:
            tier = subscription['tier']
            valid_tiers = ['free', 'premium', 'pro']
            if tier not in valid_tiers:
                errors.append(f"User {user_index}: Invalid subscription tier: {tier}")
        
        # Validate integer fields
        integer_fields = ['daily_requests', 'referrals_count']
        for field in integer_fields:
            if field in subscription and subscription[field] is not None:
                if not isinstance(subscription[field], int) or subscription[field] < 0:
                    errors.append(f"User {user_index}: Invalid {field}: {subscription[field]}")
        
        # Validate boolean fields
        boolean_fields = ['auto_renew']
        for field in boolean_fields:
            if field in subscription and subscription[field] is not None:
                if not isinstance(subscription[field], bool):
                    errors.append(f"User {user_index}: {field} must be boolean")
        
        # Validate datetime fields
        datetime_fields = ['expires_at', 'last_reset_date']
        for field in datetime_fields:
            if field in subscription and subscription[field]:
                if not self._is_valid_datetime_string(subscription[field]):
                    errors.append(f"User {user_index}: Invalid datetime format in {field}: {subscription[field]}")
        
        # Validate referral fields
        if 'referred_by' in subscription and subscription['referred_by']:
            if not isinstance(subscription['referred_by'], int) or subscription['referred_by'] <= 0:
                errors.append(f"User {user_index}: Invalid referred_by: {subscription['referred_by']}")
        
        return errors
    
    def _is_valid_datetime_string(self, datetime_str: str) -> bool:
        """
        Check if string is a valid datetime format.
        
        Args:
            datetime_str: Datetime string to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            if isinstance(datetime_str, str):
                datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                return True
        except (ValueError, TypeError):
            pass
        
        return False
    
    async def validate_database_state(self) -> ValidationResult:
        """
        Validate current PostgreSQL database state.
        
        Returns:
            ValidationResult with database validation results
        """
        result = ValidationResult()
        
        try:
            async with get_async_session() as session:
                # Check if tables exist and are accessible
                await self._check_table_accessibility(session, result)
                
                # Get database statistics
                await self._collect_database_stats(session, result)
                
                # Check data consistency
                await self._check_data_consistency(session, result)
                
        except Exception as e:
            result.add_error(f"Database validation failed: {e}")
        
        return result
    
    async def _check_table_accessibility(self, session: AsyncSession, result: ValidationResult):
        """Check if all required tables are accessible."""
        tables_to_check = ['users', 'user_subscriptions']
        
        for table_name in tables_to_check:
            try:
                if table_name == 'users':
                    await session.execute(select(User).limit(1))
                elif table_name == 'user_subscriptions':
                    await session.execute(select(UserSubscription).limit(1))
                
                logger.debug(f"Table {table_name} is accessible")
            except Exception as e:
                result.add_error(f"Table {table_name} is not accessible: {e}")
    
    async def _collect_database_stats(self, session: AsyncSession, result: ValidationResult):
        """Collect database statistics."""
        try:
            # Count total users
            users_count = await session.scalar(select(func.count(User.id)))
            result.set_stat('db_total_users', users_count)
            
            # Count users with FACEIT accounts
            faceit_users_count = await session.scalar(
                select(func.count(User.id)).where(User.faceit_player_id.isnot(None))
            )
            result.set_stat('db_users_with_faceit', faceit_users_count)
            
            # Count subscriptions by tier
            subscription_stats = {}
            for tier in SubscriptionTier:
                count = await session.scalar(
                    select(func.count(UserSubscription.id))
                    .where(UserSubscription.tier == tier)
                )
                subscription_stats[tier.value] = count
            
            result.set_stat('db_subscription_distribution', subscription_stats)
            
        except Exception as e:
            result.add_error(f"Failed to collect database stats: {e}")
    
    async def _check_data_consistency(self, session: AsyncSession, result: ValidationResult):
        """Check data consistency in the database."""
        try:
            # Check for orphaned subscriptions
            orphaned_subs = await session.scalar(
                select(func.count(UserSubscription.id))
                .outerjoin(User, UserSubscription.user_id == User.id)
                .where(User.id.is_(None))
            )
            
            if orphaned_subs > 0:
                result.add_warning(f"Found {orphaned_subs} orphaned subscriptions")
            
            # Check for users without subscriptions
            users_without_subs = await session.scalar(
                select(func.count(User.id))
                .outerjoin(UserSubscription, User.id == UserSubscription.user_id)
                .where(UserSubscription.user_id.is_(None))
            )
            
            if users_without_subs > 0:
                result.add_warning(f"Found {users_without_subs} users without subscriptions")
            
        except Exception as e:
            result.add_error(f"Data consistency check failed: {e}")
    
    async def validate_migration_integrity(
        self, 
        pre_migration_data: Dict[str, Any]
    ) -> ValidationResult:
        """
        Validate data integrity after migration by comparing JSON and PostgreSQL data.
        
        Args:
            pre_migration_data: Original JSON data before migration
            
        Returns:
            ValidationResult with migration integrity validation
        """
        result = ValidationResult()
        
        try:
            # Load current database state
            db_result = await self.validate_database_state()
            
            # Compare counts
            json_user_count = len(pre_migration_data.get('users', []))
            db_user_count = db_result.stats.get('db_total_users', 0)
            
            if json_user_count != db_user_count:
                result.add_error(
                    f"User count mismatch: JSON has {json_user_count}, "
                    f"DB has {db_user_count}"
                )
            else:
                result.set_stat('user_count_match', True)
            
            # Compare FACEIT users
            json_faceit_count = sum(
                1 for user in pre_migration_data.get('users', []) 
                if user.get('faceit_player_id')
            )
            db_faceit_count = db_result.stats.get('db_users_with_faceit', 0)
            
            if json_faceit_count != db_faceit_count:
                result.add_error(
                    f"FACEIT users count mismatch: JSON has {json_faceit_count}, "
                    f"DB has {db_faceit_count}"
                )
            else:
                result.set_stat('faceit_count_match', True)
            
            # Compare subscription distribution
            json_subscription_stats = self._count_json_subscriptions(pre_migration_data)
            db_subscription_stats = db_result.stats.get('db_subscription_distribution', {})
            
            for tier in ['free', 'premium', 'pro']:
                json_count = json_subscription_stats.get(tier, 0)
                db_count = db_subscription_stats.get(tier, 0)
                
                if json_count != db_count:
                    result.add_error(
                        f"Subscription tier {tier} mismatch: "
                        f"JSON has {json_count}, DB has {db_count}"
                    )
            
            # Validate specific user records
            await self._validate_user_data_integrity(pre_migration_data, result)
            
        except Exception as e:
            result.add_error(f"Migration integrity validation failed: {e}")
        
        return result
    
    def _count_json_subscriptions(self, json_data: Dict[str, Any]) -> Dict[str, int]:
        """Count subscription tiers in JSON data."""
        stats = {'free': 0, 'premium': 0, 'pro': 0}
        
        for user in json_data.get('users', []):
            subscription = user.get('subscription', {})
            tier = subscription.get('tier', 'free').lower()
            if tier in stats:
                stats[tier] += 1
        
        return stats
    
    async def _validate_user_data_integrity(
        self, 
        json_data: Dict[str, Any], 
        result: ValidationResult
    ):
        """Validate individual user data integrity between JSON and database."""
        try:
            async with get_async_session() as session:
                # Sample validation - check a few users
                users_to_check = json_data.get('users', [])[:10]  # Check first 10 users
                
                for json_user in users_to_check:
                    user_id = json_user.get('user_id')
                    if not user_id:
                        continue
                    
                    # Find corresponding database user
                    db_user = await session.scalar(
                        select(User).where(User.user_id == user_id)
                    )
                    
                    if not db_user:
                        result.add_error(f"User {user_id} not found in database")
                        continue
                    
                    # Check key fields match
                    if json_user.get('faceit_player_id') != db_user.faceit_player_id:
                        result.add_error(
                            f"User {user_id}: FACEIT player ID mismatch"
                        )
                    
                    if json_user.get('faceit_nickname') != db_user.faceit_nickname:
                        result.add_error(
                            f"User {user_id}: FACEIT nickname mismatch"
                        )
                    
                    # Check subscription
                    json_subscription = json_user.get('subscription', {})
                    if db_user.subscription:
                        json_tier = json_subscription.get('tier', 'free')
                        db_tier = db_user.subscription.tier.value
                        
                        if json_tier != db_tier:
                            result.add_error(
                                f"User {user_id}: Subscription tier mismatch"
                            )
                    elif json_subscription:
                        result.add_error(
                            f"User {user_id}: Has subscription in JSON but not in DB"
                        )
                
        except Exception as e:
            result.add_error(f"User data integrity check failed: {e}")
    
    def generate_validation_report(
        self, 
        results: List[ValidationResult], 
        output_path: Optional[str] = None
    ) -> str:
        """
        Generate comprehensive validation report.
        
        Args:
            results: List of validation results
            output_path: Optional path to save the report
            
        Returns:
            Report content as string
        """
        report_lines = []
        report_lines.append("# Data Migration Validation Report")
        report_lines.append(f"Generated at: {datetime.now().isoformat()}")
        report_lines.append("")
        
        for i, result in enumerate(results):
            report_lines.append(f"## Validation {i + 1}")
            report_lines.append(f"**Status:** {'PASS' if result.is_valid else 'FAIL'}")
            report_lines.append(f"**Errors:** {len(result.errors)}")
            report_lines.append(f"**Warnings:** {len(result.warnings)}")
            report_lines.append("")
            
            if result.errors:
                report_lines.append("### Errors:")
                for error in result.errors:
                    report_lines.append(f"- {error}")
                report_lines.append("")
            
            if result.warnings:
                report_lines.append("### Warnings:")
                for warning in result.warnings:
                    report_lines.append(f"- {warning}")
                report_lines.append("")
            
            if result.stats:
                report_lines.append("### Statistics:")
                for key, value in result.stats.items():
                    report_lines.append(f"- **{key}:** {value}")
                report_lines.append("")
        
        report_content = "\n".join(report_lines)
        
        if output_path:
            Path(output_path).write_text(report_content, encoding='utf-8')
            logger.info(f"Validation report saved to {output_path}")
        
        return report_content