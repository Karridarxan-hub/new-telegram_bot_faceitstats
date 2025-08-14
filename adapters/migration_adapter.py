"""
Migration Adapter for data migration between JSON and PostgreSQL.

Provides utilities for migrating data between storage backends with
validation, rollback capabilities, and progress tracking.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Callable
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from utils.storage import storage as json_storage, UserData, SubscriptionTier
from services.user import UserService
from services.subscription import SubscriptionService
from database.repositories.user import UserRepository
from database.repositories.subscription import SubscriptionRepository

logger = logging.getLogger(__name__)


class MigrationDirection(str, Enum):
    """Migration direction options."""
    JSON_TO_POSTGRESQL = "json_to_postgresql"
    POSTGRESQL_TO_JSON = "postgresql_to_json"
    BIDIRECTIONAL_SYNC = "bidirectional_sync"


class MigrationStatus(str, Enum):
    """Migration status options."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class MigrationResult:
    """Result of a migration operation."""
    status: MigrationStatus
    total_users: int
    migrated_users: int
    failed_users: int
    errors: List[str]
    duration_seconds: float
    rollback_data: Optional[Dict[str, Any]] = None


@dataclass
class UserMigrationData:
    """Data for migrating a single user."""
    user_id: int
    user_data: UserData
    migration_success: bool = False
    error_message: Optional[str] = None
    rollback_data: Optional[Dict[str, Any]] = None


class MigrationAdapter:
    """
    Adapter for migrating data between JSON and PostgreSQL storage.
    
    Provides comprehensive migration capabilities with validation,
    rollback support, and progress tracking.
    """
    
    def __init__(
        self,
        user_service: UserService,
        subscription_service: SubscriptionService,
        user_repository: UserRepository,
        subscription_repository: SubscriptionRepository
    ):
        """
        Initialize migration adapter.
        
        Args:
            user_service: PostgreSQL user service
            subscription_service: PostgreSQL subscription service
            user_repository: PostgreSQL user repository
            subscription_repository: PostgreSQL subscription repository
        """
        self.user_service = user_service
        self.subscription_service = subscription_service
        self.user_repo = user_repository
        self.subscription_repo = subscription_repository
        
        self._migration_progress: Dict[str, Any] = {}
        self._rollback_data: Dict[str, List[Dict[str, Any]]] = {}
    
    async def migrate_all_users(
        self,
        direction: MigrationDirection = MigrationDirection.JSON_TO_POSTGRESQL,
        batch_size: int = 50,
        validation_mode: bool = True,
        progress_callback: Optional[Callable] = None
    ) -> MigrationResult:
        """
        Migrate all users between storage backends.
        
        Args:
            direction: Migration direction
            batch_size: Number of users to process in each batch
            validation_mode: Whether to validate data before migration
            progress_callback: Optional callback for progress updates
            
        Returns:
            MigrationResult with operation details
        """
        start_time = datetime.now()
        migration_id = f"migration_{int(start_time.timestamp())}"
        
        logger.info(f"Starting user migration: {direction.value}")
        
        try:
            # Initialize progress tracking
            self._migration_progress[migration_id] = {
                "status": MigrationStatus.IN_PROGRESS,
                "direction": direction,
                "start_time": start_time,
                "total_users": 0,
                "processed_users": 0,
                "failed_users": 0,
                "errors": []
            }
            
            # Get source users
            if direction == MigrationDirection.JSON_TO_POSTGRESQL:
                source_users = await json_storage.get_all_users()
            elif direction == MigrationDirection.POSTGRESQL_TO_JSON:
                source_users = await self._get_postgresql_users()
            else:
                # Bidirectional sync - get users from both sources
                json_users = await json_storage.get_all_users()
                pg_users = await self._get_postgresql_users()
                source_users = self._merge_user_lists(json_users, pg_users)
            
            total_users = len(source_users)
            self._migration_progress[migration_id]["total_users"] = total_users
            
            if total_users == 0:
                logger.warning("No users found for migration")
                return MigrationResult(
                    status=MigrationStatus.COMPLETED,
                    total_users=0,
                    migrated_users=0,
                    failed_users=0,
                    errors=[],
                    duration_seconds=0.0
                )
            
            # Process users in batches
            migrated_users = 0
            failed_users = 0
            errors = []
            
            for i in range(0, total_users, batch_size):
                batch = source_users[i:i + batch_size]
                batch_results = await self._migrate_user_batch(
                    batch, direction, validation_mode
                )
                
                # Update counters
                for result in batch_results:
                    if result.migration_success:
                        migrated_users += 1
                    else:
                        failed_users += 1
                        if result.error_message:
                            errors.append(f"User {result.user_id}: {result.error_message}")
                
                # Update progress
                processed = i + len(batch)
                self._migration_progress[migration_id]["processed_users"] = processed
                self._migration_progress[migration_id]["failed_users"] = failed_users
                
                # Call progress callback if provided
                if progress_callback:
                    await progress_callback({
                        "migration_id": migration_id,
                        "total": total_users,
                        "processed": processed,
                        "migrated": migrated_users,
                        "failed": failed_users,
                        "percentage": round((processed / total_users) * 100, 1)
                    })
                
                logger.info(f"Migration progress: {processed}/{total_users} users processed")
                
                # Small delay between batches to prevent overwhelming the database
                await asyncio.sleep(0.1)
            
            # Determine final status
            if failed_users == 0:
                final_status = MigrationStatus.COMPLETED
            elif migrated_users > 0:
                final_status = MigrationStatus.COMPLETED  # Partial success
            else:
                final_status = MigrationStatus.FAILED
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # Update progress
            self._migration_progress[migration_id]["status"] = final_status
            self._migration_progress[migration_id]["duration"] = duration
            
            result = MigrationResult(
                status=final_status,
                total_users=total_users,
                migrated_users=migrated_users,
                failed_users=failed_users,
                errors=errors[:100],  # Limit error list size
                duration_seconds=duration,
                rollback_data=self._rollback_data.get(migration_id)
            )
            
            logger.info(f"Migration completed: {migrated_users}/{total_users} users migrated")
            return result
        
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            self._migration_progress[migration_id]["status"] = MigrationStatus.FAILED
            
            return MigrationResult(
                status=MigrationStatus.FAILED,
                total_users=0,
                migrated_users=0,
                failed_users=0,
                errors=[str(e)],
                duration_seconds=(datetime.now() - start_time).total_seconds()
            )
    
    async def migrate_single_user(
        self,
        user_id: int,
        direction: MigrationDirection = MigrationDirection.JSON_TO_POSTGRESQL,
        validation_mode: bool = True
    ) -> UserMigrationData:
        """
        Migrate a single user between storage backends.
        
        Args:
            user_id: Telegram user ID
            direction: Migration direction
            validation_mode: Whether to validate data before migration
            
        Returns:
            UserMigrationData with migration results
        """
        try:
            logger.info(f"Migrating user {user_id}: {direction.value}")
            
            # Get source user data
            if direction == MigrationDirection.JSON_TO_POSTGRESQL:
                user_data = await json_storage.get_user(user_id)
                if not user_data:
                    return UserMigrationData(
                        user_id=user_id,
                        user_data=None,
                        migration_success=False,
                        error_message="User not found in JSON storage"
                    )
                
                # Migrate to PostgreSQL
                success, error = await self._migrate_user_to_postgresql(user_data, validation_mode)
                
            elif direction == MigrationDirection.POSTGRESQL_TO_JSON:
                user_data = await self._get_postgresql_user(user_id)
                if not user_data:
                    return UserMigrationData(
                        user_id=user_id,
                        user_data=None,
                        migration_success=False,
                        error_message="User not found in PostgreSQL storage"
                    )
                
                # Migrate to JSON
                success, error = await self._migrate_user_to_json(user_data, validation_mode)
            
            else:
                # Bidirectional sync
                success, error = await self._sync_user_bidirectional(user_id, validation_mode)
                user_data = await json_storage.get_user(user_id)  # Get updated data
            
            return UserMigrationData(
                user_id=user_id,
                user_data=user_data,
                migration_success=success,
                error_message=error if not success else None
            )
        
        except Exception as e:
            logger.error(f"Error migrating user {user_id}: {e}")
            return UserMigrationData(
                user_id=user_id,
                user_data=None,
                migration_success=False,
                error_message=str(e)
            )
    
    async def validate_migration_integrity(self) -> Dict[str, Any]:
        """
        Validate data integrity between JSON and PostgreSQL storage.
        
        Returns:
            Validation results
        """
        logger.info("Starting migration integrity validation")
        
        try:
            # Get users from both storages
            json_users = await json_storage.get_all_users()
            pg_users = await self._get_postgresql_users()
            
            # Create lookup maps
            json_user_map = {user.user_id: user for user in json_users}
            pg_user_map = {user.user_id: user for user in pg_users}
            
            # Find discrepancies
            json_only = set(json_user_map.keys()) - set(pg_user_map.keys())
            pg_only = set(pg_user_map.keys()) - set(json_user_map.keys())
            common_users = set(json_user_map.keys()) & set(pg_user_map.keys())
            
            # Validate common users
            data_mismatches = []
            for user_id in common_users:
                json_user = json_user_map[user_id]
                pg_user = pg_user_map[user_id]
                
                mismatches = self._compare_user_data(json_user, pg_user)
                if mismatches:
                    data_mismatches.append({
                        "user_id": user_id,
                        "mismatches": mismatches
                    })
            
            validation_result = {
                "total_json_users": len(json_users),
                "total_postgresql_users": len(pg_users),
                "common_users": len(common_users),
                "json_only_users": list(json_only),
                "postgresql_only_users": list(pg_only),
                "data_mismatches": data_mismatches,
                "integrity_score": self._calculate_integrity_score(
                    len(json_users), len(pg_users), len(common_users), len(data_mismatches)
                ),
                "validation_timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"Integrity validation completed. Score: {validation_result['integrity_score']}%")
            return validation_result
        
        except Exception as e:
            logger.error(f"Error during integrity validation: {e}")
            return {
                "error": str(e),
                "validation_timestamp": datetime.now().isoformat()
            }
    
    async def rollback_migration(self, migration_id: str) -> bool:
        """
        Rollback a completed migration using stored rollback data.
        
        Args:
            migration_id: ID of migration to rollback
            
        Returns:
            Success status
        """
        try:
            logger.info(f"Starting rollback for migration {migration_id}")
            
            rollback_data = self._rollback_data.get(migration_id)
            if not rollback_data:
                logger.error(f"No rollback data found for migration {migration_id}")
                return False
            
            # Implement rollback logic based on migration direction
            # This is a simplified implementation - in production you might want more sophisticated rollback
            logger.warning("Rollback functionality not fully implemented - manual intervention required")
            return False
        
        except Exception as e:
            logger.error(f"Error during rollback: {e}")
            return False
    
    # Helper methods
    async def _migrate_user_batch(
        self,
        users: List[UserData],
        direction: MigrationDirection,
        validation_mode: bool
    ) -> List[UserMigrationData]:
        """Migrate a batch of users."""
        results = []
        
        for user in users:
            try:
                if direction == MigrationDirection.JSON_TO_POSTGRESQL:
                    success, error = await self._migrate_user_to_postgresql(user, validation_mode)
                elif direction == MigrationDirection.POSTGRESQL_TO_JSON:
                    success, error = await self._migrate_user_to_json(user, validation_mode)
                else:
                    success, error = await self._sync_user_bidirectional(user.user_id, validation_mode)
                
                results.append(UserMigrationData(
                    user_id=user.user_id,
                    user_data=user,
                    migration_success=success,
                    error_message=error if not success else None
                ))
            
            except Exception as e:
                logger.error(f"Error migrating user {user.user_id}: {e}")
                results.append(UserMigrationData(
                    user_id=user.user_id,
                    user_data=user,
                    migration_success=False,
                    error_message=str(e)
                ))
        
        return results
    
    async def _migrate_user_to_postgresql(
        self,
        user_data: UserData,
        validation_mode: bool
    ) -> Tuple[bool, Optional[str]]:
        """Migrate single user from JSON to PostgreSQL."""
        try:
            # Validate data if required
            if validation_mode:
                validation_error = self._validate_user_data(user_data)
                if validation_error:
                    return False, validation_error
            
            # Create user in PostgreSQL
            result = await self.user_service.create_user(
                user_data.user_id,
                user_data.faceit_nickname,
                user_data.language
            )
            
            if not result.success:
                return False, result.error.message if result.error else "Unknown error"
            
            # Migrate subscription data
            if user_data.subscription and user_data.subscription.tier != SubscriptionTier.FREE:
                sub_result = await self.subscription_service.upgrade_subscription(
                    user_data.user_id,
                    user_data.subscription.tier,
                    30  # Default duration
                )
                
                if not sub_result.success:
                    logger.warning(f"Failed to migrate subscription for user {user_data.user_id}")
            
            return True, None
        
        except Exception as e:
            return False, str(e)
    
    async def _migrate_user_to_json(
        self,
        user_data: UserData,
        validation_mode: bool
    ) -> Tuple[bool, Optional[str]]:
        """Migrate single user from PostgreSQL to JSON."""
        try:
            # Validate data if required
            if validation_mode:
                validation_error = self._validate_user_data(user_data)
                if validation_error:
                    return False, validation_error
            
            # Save to JSON storage
            await json_storage.save_user(user_data)
            return True, None
        
        except Exception as e:
            return False, str(e)
    
    async def _sync_user_bidirectional(
        self,
        user_id: int,
        validation_mode: bool
    ) -> Tuple[bool, Optional[str]]:
        """Synchronize user data between both storages."""
        try:
            json_user = await json_storage.get_user(user_id)
            pg_user = await self._get_postgresql_user(user_id)
            
            # Determine which version is newer/more complete
            if json_user and pg_user:
                # Both exist - sync newer to older
                if json_user.last_active_at and pg_user.last_active_at:
                    if json_user.last_active_at > pg_user.last_active_at:
                        # JSON is newer - update PostgreSQL
                        success, error = await self._migrate_user_to_postgresql(json_user, validation_mode)
                    else:
                        # PostgreSQL is newer - update JSON
                        success, error = await self._migrate_user_to_json(pg_user, validation_mode)
                else:
                    # Can't determine - sync from JSON to PostgreSQL as default
                    success, error = await self._migrate_user_to_postgresql(json_user, validation_mode)
            elif json_user:
                # Only in JSON - migrate to PostgreSQL
                success, error = await self._migrate_user_to_postgresql(json_user, validation_mode)
            elif pg_user:
                # Only in PostgreSQL - migrate to JSON
                success, error = await self._migrate_user_to_json(pg_user, validation_mode)
            else:
                return False, "User not found in either storage"
            
            return success, error
        
        except Exception as e:
            return False, str(e)
    
    async def _get_postgresql_users(self) -> List[UserData]:
        """Get all users from PostgreSQL storage."""
        try:
            result = await self.user_service.search_users(limit=10000)
            if not result.success:
                return []
            
            users = []
            for user_dict in result.data:
                user_data = UserData(
                    user_id=user_dict["telegram_user_id"],
                    faceit_nickname=user_dict.get("faceit_nickname"),
                    language=user_dict.get("language", "ru"),
                    created_at=user_dict.get("created_at"),
                    last_active_at=user_dict.get("last_active_at"),
                    total_requests=user_dict.get("total_requests", 0)
                )
                users.append(user_data)
            
            return users
        
        except Exception as e:
            logger.error(f"Error getting PostgreSQL users: {e}")
            return []
    
    async def _get_postgresql_user(self, user_id: int) -> Optional[UserData]:
        """Get single user from PostgreSQL storage."""
        try:
            result = await self.user_service.get_user_profile(user_id, include_subscription=True)
            if not result.success:
                return None
            
            profile = result.data
            return UserData(
                user_id=profile["user_id"],
                faceit_player_id=profile.get("faceit_player_id"),
                faceit_nickname=profile.get("faceit_nickname"),
                waiting_for_nickname=profile.get("waiting_for_nickname", False),
                language=profile.get("language", "ru"),
                notifications_enabled=profile.get("notifications_enabled", True),
                created_at=profile.get("created_at"),
                last_active_at=profile.get("last_active_at"),
                total_requests=profile.get("total_requests", 0)
            )
        
        except Exception as e:
            logger.error(f"Error getting PostgreSQL user {user_id}: {e}")
            return None
    
    def _validate_user_data(self, user_data: UserData) -> Optional[str]:
        """Validate user data before migration."""
        if not user_data:
            return "User data is None"
        
        if not user_data.user_id or user_data.user_id <= 0:
            return "Invalid user ID"
        
        if user_data.faceit_nickname and len(user_data.faceit_nickname) > 50:
            return "FACEIT nickname too long"
        
        if user_data.language and len(user_data.language) > 10:
            return "Language code too long"
        
        return None
    
    def _compare_user_data(self, json_user: UserData, pg_user: UserData) -> List[str]:
        """Compare user data between storages."""
        mismatches = []
        
        if json_user.faceit_player_id != pg_user.faceit_player_id:
            mismatches.append("faceit_player_id")
        
        if json_user.faceit_nickname != pg_user.faceit_nickname:
            mismatches.append("faceit_nickname")
        
        if json_user.language != pg_user.language:
            mismatches.append("language")
        
        return mismatches
    
    def _merge_user_lists(self, json_users: List[UserData], pg_users: List[UserData]) -> List[UserData]:
        """Merge user lists from both storages."""
        user_map = {}
        
        # Add all users
        for user in json_users + pg_users:
            user_map[user.user_id] = user
        
        return list(user_map.values())
    
    def _calculate_integrity_score(
        self,
        json_count: int,
        pg_count: int,
        common_count: int,
        mismatch_count: int
    ) -> float:
        """Calculate data integrity score."""
        if json_count == 0 and pg_count == 0:
            return 100.0
        
        total_unique = max(json_count, pg_count)
        if total_unique == 0:
            return 100.0
        
        consistency_score = (common_count / total_unique) * 100
        mismatch_penalty = (mismatch_count / max(common_count, 1)) * 10
        
        return max(0.0, consistency_score - mismatch_penalty)
    
    def get_migration_status(self, migration_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a migration operation."""
        return self._migration_progress.get(migration_id)
    
    def get_all_migration_statuses(self) -> Dict[str, Any]:
        """Get status of all migration operations."""
        return dict(self._migration_progress)