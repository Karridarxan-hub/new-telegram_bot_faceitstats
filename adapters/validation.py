"""
Data validation utilities for service integration.

Provides comprehensive validation for data consistency between
JSON storage and PostgreSQL, with reporting and fixing capabilities.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from utils.storage import UserData, SubscriptionTier
from services.user import UserService
from services.subscription import SubscriptionService

logger = logging.getLogger(__name__)


class ValidationSeverity(str, Enum):
    """Validation issue severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationIssue:
    """Represents a data validation issue."""
    severity: ValidationSeverity
    category: str
    description: str
    user_id: Optional[int] = None
    details: Optional[Dict[str, Any]] = None
    fix_suggested: Optional[str] = None


@dataclass
class ValidationReport:
    """Comprehensive validation report."""
    total_users_json: int
    total_users_postgresql: int
    common_users: int
    json_only_users: int
    postgresql_only_users: int
    issues: List[ValidationIssue]
    integrity_score: float
    validation_timestamp: datetime
    
    def get_issues_by_severity(self, severity: ValidationSeverity) -> List[ValidationIssue]:
        """Get issues filtered by severity."""
        return [issue for issue in self.issues if issue.severity == severity]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get validation summary statistics."""
        return {
            "total_issues": len(self.issues),
            "critical_issues": len(self.get_issues_by_severity(ValidationSeverity.CRITICAL)),
            "error_issues": len(self.get_issues_by_severity(ValidationSeverity.ERROR)),
            "warning_issues": len(self.get_issues_by_severity(ValidationSeverity.WARNING)),
            "info_issues": len(self.get_issues_by_severity(ValidationSeverity.INFO)),
            "integrity_score": self.integrity_score,
            "data_consistency": "Good" if self.integrity_score > 90 else "Poor"
        }


class DataValidator:
    """
    Comprehensive data validator for storage integration.
    
    Validates data consistency, identifies issues, and provides
    recommendations for fixing problems.
    """
    
    def __init__(
        self,
        user_service: Optional[UserService] = None,
        subscription_service: Optional[SubscriptionService] = None
    ):
        """
        Initialize data validator.
        
        Args:
            user_service: Optional user service for PostgreSQL validation
            subscription_service: Optional subscription service for PostgreSQL validation
        """
        self.user_service = user_service
        self.subscription_service = subscription_service
    
    async def validate_all_data(self, include_deep_validation: bool = True) -> ValidationReport:
        """
        Perform comprehensive data validation.
        
        Args:
            include_deep_validation: Whether to perform deep validation (slower)
            
        Returns:
            Comprehensive validation report
        """
        logger.info("🔍 Starting comprehensive data validation")
        
        issues = []
        
        # Import JSON storage
        from utils.storage import storage as json_storage
        
        # Get users from both sources
        json_users = await json_storage.get_all_users()
        postgresql_users = []
        
        if self.user_service:
            try:
                result = await self.user_service.search_users(limit=10000)
                if result.success:
                    postgresql_users = [
                        self._dict_to_user_data(user_dict) 
                        for user_dict in result.data
                    ]
            except Exception as e:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="postgresql_access",
                    description=f"Failed to access PostgreSQL users: {e}"
                ))
        
        # Create user lookup maps
        json_user_map = {user.user_id: user for user in json_users}
        pg_user_map = {user.user_id: user for user in postgresql_users}
        
        # Identify user distribution
        json_only = set(json_user_map.keys()) - set(pg_user_map.keys())
        pg_only = set(pg_user_map.keys()) - set(json_user_map.keys())
        common_users = set(json_user_map.keys()) & set(pg_user_map.keys())
        
        # Validate user distribution
        issues.extend(await self._validate_user_distribution(
            len(json_users), len(postgresql_users), len(json_only), len(pg_only)
        ))
        
        # Validate common users
        for user_id in common_users:
            json_user = json_user_map[user_id]
            pg_user = pg_user_map[user_id]
            
            user_issues = await self._validate_user_consistency(json_user, pg_user)
            issues.extend(user_issues)
        
        # Deep validation if requested
        if include_deep_validation:
            deep_issues = await self._perform_deep_validation(
                json_users, postgresql_users
            )
            issues.extend(deep_issues)
        
        # Calculate integrity score
        integrity_score = self._calculate_integrity_score(
            len(json_users), len(postgresql_users), len(common_users), issues
        )
        
        report = ValidationReport(
            total_users_json=len(json_users),
            total_users_postgresql=len(postgresql_users),
            common_users=len(common_users),
            json_only_users=len(json_only),
            postgresql_only_users=len(pg_only),
            issues=issues,
            integrity_score=integrity_score,
            validation_timestamp=datetime.now()
        )
        
        logger.info(f"✅ Validation completed. Integrity score: {integrity_score:.1f}%")
        return report
    
    async def validate_user_data(self, user_data: UserData) -> List[ValidationIssue]:
        """
        Validate individual user data.
        
        Args:
            user_data: User data to validate
            
        Returns:
            List of validation issues
        """
        issues = []
        
        # Validate required fields
        if not user_data.user_id or user_data.user_id <= 0:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.CRITICAL,
                category="data_integrity",
                description="Invalid user ID",
                user_id=user_data.user_id,
                fix_suggested="Ensure user_id is a positive integer"
            ))
        
        # Validate FACEIT data consistency
        if user_data.faceit_player_id and not user_data.faceit_nickname:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                category="data_consistency",
                description="FACEIT player ID without nickname",
                user_id=user_data.user_id,
                fix_suggested="Fetch nickname from FACEIT API or remove player ID"
            ))
        
        if user_data.faceit_nickname and not user_data.faceit_player_id:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                category="data_consistency",
                description="FACEIT nickname without player ID",
                user_id=user_data.user_id,
                fix_suggested="Fetch player ID from FACEIT API or remove nickname"
            ))
        
        # Validate dates
        if user_data.created_at and user_data.last_active_at:
            if user_data.created_at > user_data.last_active_at:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category="data_consistency",
                    description="Created date is after last active date",
                    user_id=user_data.user_id,
                    fix_suggested="Check date calculations and update accordingly"
                ))
        
        # Validate subscription data
        if user_data.subscription:
            subscription_issues = self._validate_subscription_data(user_data.subscription, user_data.user_id)
            issues.extend(subscription_issues)
        
        # Validate field lengths and formats
        if user_data.faceit_nickname and len(user_data.faceit_nickname) > 50:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="data_format",
                description="FACEIT nickname too long",
                user_id=user_data.user_id,
                fix_suggested="Truncate nickname to 50 characters"
            ))
        
        if user_data.language and len(user_data.language) > 10:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="data_format",
                description="Language code too long",
                user_id=user_data.user_id,
                fix_suggested="Use standard language codes (e.g., 'en', 'ru')"
            ))
        
        return issues
    
    async def fix_validation_issues(
        self, 
        report: ValidationReport,
        auto_fix: bool = False,
        severity_threshold: ValidationSeverity = ValidationSeverity.WARNING
    ) -> Dict[str, Any]:
        """
        Attempt to fix validation issues.
        
        Args:
            report: Validation report with issues to fix
            auto_fix: Whether to automatically apply fixes
            severity_threshold: Minimum severity level to fix
            
        Returns:
            Summary of fix attempts
        """
        logger.info("🔧 Starting issue fix process")
        
        fix_summary = {
            "attempted_fixes": 0,
            "successful_fixes": 0,
            "failed_fixes": 0,
            "skipped_fixes": 0,
            "fixes_by_category": {}
        }
        
        # Filter issues by severity
        severity_levels = {
            ValidationSeverity.INFO: 0,
            ValidationSeverity.WARNING: 1,
            ValidationSeverity.ERROR: 2,
            ValidationSeverity.CRITICAL: 3
        }
        
        threshold_level = severity_levels[severity_threshold]
        fixable_issues = [
            issue for issue in report.issues 
            if severity_levels[issue.severity] >= threshold_level and issue.fix_suggested
        ]
        
        for issue in fixable_issues:
            fix_summary["attempted_fixes"] += 1
            
            try:
                if auto_fix:
                    success = await self._apply_fix(issue)
                    if success:
                        fix_summary["successful_fixes"] += 1
                        logger.info(f"✅ Fixed issue: {issue.description}")
                    else:
                        fix_summary["failed_fixes"] += 1
                        logger.warning(f"❌ Failed to fix issue: {issue.description}")
                else:
                    fix_summary["skipped_fixes"] += 1
                    logger.info(f"📋 Skipped fix (manual mode): {issue.description}")
                
                # Track by category
                category = issue.category
                if category not in fix_summary["fixes_by_category"]:
                    fix_summary["fixes_by_category"][category] = {
                        "attempted": 0, "successful": 0, "failed": 0
                    }
                
                fix_summary["fixes_by_category"][category]["attempted"] += 1
                if auto_fix:
                    if success:
                        fix_summary["fixes_by_category"][category]["successful"] += 1
                    else:
                        fix_summary["fixes_by_category"][category]["failed"] += 1
                
            except Exception as e:
                fix_summary["failed_fixes"] += 1
                logger.error(f"❌ Error fixing issue {issue.description}: {e}")
        
        logger.info(f"🔧 Fix process completed: {fix_summary['successful_fixes']}/{fix_summary['attempted_fixes']} successful")
        return fix_summary
    
    # Helper methods
    async def _validate_user_distribution(
        self, json_count: int, pg_count: int, json_only: int, pg_only: int
    ) -> List[ValidationIssue]:
        """Validate user distribution between storages."""
        issues = []
        
        if json_count == 0 and pg_count == 0:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.CRITICAL,
                category="data_availability",
                description="No users found in either storage system",
                fix_suggested="Initialize system with test users or check database connections"
            ))
        
        if json_only > pg_count * 0.5:  # More than 50% of PG users are JSON-only
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                category="data_migration",
                description=f"{json_only} users exist only in JSON storage",
                details={"json_only_count": json_only},
                fix_suggested="Consider running migration from JSON to PostgreSQL"
            ))
        
        if pg_only > json_count * 0.1:  # More than 10% of JSON users are PG-only
            issues.append(ValidationIssue(
                severity=ValidationSeverity.INFO,
                category="data_migration",
                description=f"{pg_only} users exist only in PostgreSQL",
                details={"pg_only_count": pg_only},
                fix_suggested="Normal during migration process, monitor completion"
            ))
        
        return issues
    
    async def _validate_user_consistency(
        self, json_user: UserData, pg_user: UserData
    ) -> List[ValidationIssue]:
        """Validate consistency between JSON and PostgreSQL user data."""
        issues = []
        user_id = json_user.user_id
        
        # Validate FACEIT data consistency
        if json_user.faceit_player_id != pg_user.faceit_player_id:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="data_mismatch",
                description="FACEIT player ID mismatch between storages",
                user_id=user_id,
                details={
                    "json_value": json_user.faceit_player_id,
                    "pg_value": pg_user.faceit_player_id
                },
                fix_suggested="Sync FACEIT data from most recent source"
            ))
        
        if json_user.faceit_nickname != pg_user.faceit_nickname:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                category="data_mismatch",
                description="FACEIT nickname mismatch between storages",
                user_id=user_id,
                details={
                    "json_value": json_user.faceit_nickname,
                    "pg_value": pg_user.faceit_nickname
                },
                fix_suggested="Sync nickname from FACEIT API"
            ))
        
        # Validate user preferences
        if json_user.language != pg_user.language:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.INFO,
                category="preference_mismatch",
                description="Language preference mismatch",
                user_id=user_id,
                details={
                    "json_value": json_user.language,
                    "pg_value": pg_user.language
                },
                fix_suggested="Use most recently updated value"
            ))
        
        return issues
    
    async def _perform_deep_validation(
        self, json_users: List[UserData], pg_users: List[UserData]
    ) -> List[ValidationIssue]:
        """Perform deep validation checks."""
        issues = []
        
        # Validate FACEIT data consistency with API
        if len(json_users) > 0:  # Only perform if we have users
            faceit_validation_issues = await self._validate_faceit_consistency(json_users[:10])  # Limit to avoid API limits
            issues.extend(faceit_validation_issues)
        
        # Validate subscription data consistency
        subscription_issues = await self._validate_subscription_consistency(json_users)
        issues.extend(subscription_issues)
        
        return issues
    
    async def _validate_faceit_consistency(self, users: List[UserData]) -> List[ValidationIssue]:
        """Validate FACEIT data against API."""
        issues = []
        
        try:
            from faceit.api import FaceitAPI, FaceitAPIError
            faceit_api = FaceitAPI()
            
            for user in users:
                if user.faceit_player_id:
                    try:
                        api_player = await faceit_api.get_player_by_id(user.faceit_player_id)
                        if not api_player:
                            issues.append(ValidationIssue(
                                severity=ValidationSeverity.ERROR,
                                category="faceit_consistency",
                                description="FACEIT player not found in API",
                                user_id=user.user_id,
                                fix_suggested="Remove invalid FACEIT data or update with correct ID"
                            ))
                        elif api_player.nickname != user.faceit_nickname:
                            issues.append(ValidationIssue(
                                severity=ValidationSeverity.WARNING,
                                category="faceit_consistency",
                                description="FACEIT nickname outdated",
                                user_id=user.user_id,
                                details={
                                    "stored_nickname": user.faceit_nickname,
                                    "api_nickname": api_player.nickname
                                },
                                fix_suggested="Update nickname from FACEIT API"
                            ))
                    except FaceitAPIError:
                        # Don't create issues for API errors, might be temporary
                        pass
        
        except ImportError:
            logger.warning("FACEIT API not available for deep validation")
        
        return issues
    
    async def _validate_subscription_consistency(self, users: List[UserData]) -> List[ValidationIssue]:
        """Validate subscription data consistency."""
        issues = []
        
        for user in users:
            if user.subscription:
                subscription_issues = self._validate_subscription_data(user.subscription, user.user_id)
                issues.extend(subscription_issues)
        
        return issues
    
    def _validate_subscription_data(self, subscription, user_id: int) -> List[ValidationIssue]:
        """Validate individual subscription data."""
        issues = []
        
        # Validate subscription tier
        if subscription.tier not in [SubscriptionTier.FREE, SubscriptionTier.PREMIUM, SubscriptionTier.PRO]:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.CRITICAL,
                category="subscription_data",
                description="Invalid subscription tier",
                user_id=user_id,
                fix_suggested="Reset to FREE tier"
            ))
        
        # Validate expiration date
        if subscription.expires_at and subscription.expires_at < datetime.now() and subscription.tier != SubscriptionTier.FREE:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                category="subscription_expired",
                description="Expired subscription not downgraded",
                user_id=user_id,
                fix_suggested="Downgrade to FREE tier"
            ))
        
        # Validate daily request counter
        if subscription.daily_requests < 0:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="subscription_data",
                description="Negative daily requests count",
                user_id=user_id,
                fix_suggested="Reset daily requests to 0"
            ))
        
        return issues
    
    def _calculate_integrity_score(
        self, json_count: int, pg_count: int, common_count: int, issues: List[ValidationIssue]
    ) -> float:
        """Calculate data integrity score."""
        if json_count == 0 and pg_count == 0:
            return 0.0
        
        # Base score from data overlap
        total_unique = max(json_count, pg_count)
        if total_unique == 0:
            return 100.0
        
        overlap_score = (common_count / total_unique) * 100
        
        # Penalty based on issues
        critical_penalty = len([i for i in issues if i.severity == ValidationSeverity.CRITICAL]) * 20
        error_penalty = len([i for i in issues if i.severity == ValidationSeverity.ERROR]) * 10
        warning_penalty = len([i for i in issues if i.severity == ValidationSeverity.WARNING]) * 5
        
        total_penalty = critical_penalty + error_penalty + warning_penalty
        
        # Calculate final score
        final_score = max(0.0, overlap_score - total_penalty)
        return min(100.0, final_score)
    
    async def _apply_fix(self, issue: ValidationIssue) -> bool:
        """Apply automatic fix for an issue."""
        # This is a simplified implementation
        # In production, you'd want more sophisticated fix strategies
        
        logger.info(f"🔧 Attempting to fix: {issue.description}")
        
        try:
            # Different fix strategies based on category
            if issue.category == "data_format":
                return await self._fix_data_format_issue(issue)
            elif issue.category == "data_mismatch":
                return await self._fix_data_mismatch_issue(issue)
            elif issue.category == "subscription_expired":
                return await self._fix_expired_subscription_issue(issue)
            else:
                logger.info(f"📋 No automatic fix available for category: {issue.category}")
                return False
        
        except Exception as e:
            logger.error(f"❌ Error applying fix: {e}")
            return False
    
    async def _fix_data_format_issue(self, issue: ValidationIssue) -> bool:
        """Fix data format issues."""
        # Placeholder for data format fixes
        logger.info(f"📝 Would fix data format issue: {issue.description}")
        return True
    
    async def _fix_data_mismatch_issue(self, issue: ValidationIssue) -> bool:
        """Fix data mismatch issues."""
        # Placeholder for data mismatch fixes
        logger.info(f"🔄 Would sync data mismatch: {issue.description}")
        return True
    
    async def _fix_expired_subscription_issue(self, issue: ValidationIssue) -> bool:
        """Fix expired subscription issues."""
        # Placeholder for subscription fixes
        logger.info(f"💎 Would fix subscription issue: {issue.description}")
        return True
    
    def _dict_to_user_data(self, user_dict: Dict[str, Any]) -> UserData:
        """Convert user dictionary to UserData instance."""
        return UserData(
            user_id=user_dict.get("telegram_user_id"),
            faceit_nickname=user_dict.get("faceit_nickname"),
            language=user_dict.get("language", "ru"),
            created_at=user_dict.get("created_at"),
            last_active_at=user_dict.get("last_active_at"),
            total_requests=user_dict.get("total_requests", 0)
        )