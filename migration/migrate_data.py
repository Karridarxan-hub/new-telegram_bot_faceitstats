"""Main Data Migration Script for JSON to PostgreSQL.

Orchestrates the complete migration process from JSON file storage to PostgreSQL,
including data validation, mapping, batch processing, and rollback capabilities.
"""

import logging
import asyncio
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select

from database.models import User, UserSubscription, Analytics
from database.connection import get_async_session
from .data_mapper import DataMapper, MappingError
from .validator import DataValidator, ValidationError
from .utils import (
    MigrationUtils, ProgressTracker, BackupManager, BatchProcessor,
    DatabaseUtils, MigrationLock, MigrationError
)

logger = logging.getLogger(__name__)


class MigrationResult:
    """Container for migration results."""
    
    def __init__(self):
        self.success = False
        self.total_users = 0
        self.migrated_users = 0
        self.failed_users = 0
        self.errors = []
        self.warnings = []
        self.start_time = datetime.now()
        self.end_time = None
        self.backup_path = None
        self.migration_log_id = None
        
    def add_error(self, error: str):
        """Add an error message."""
        self.errors.append(error)
        logger.error(error)
        
    def add_warning(self, warning: str):
        """Add a warning message."""
        self.warnings.append(warning)
        logger.warning(warning)
        
    def finalize(self):
        """Finalize the migration result."""
        self.end_time = datetime.now()
        self.success = (self.failed_users == 0 and len(self.errors) == 0)
        
    def get_summary(self) -> Dict[str, Any]:
        """Get migration summary."""
        duration = (self.end_time - self.start_time) if self.end_time else None
        
        return {
            'success': self.success,
            'total_users': self.total_users,
            'migrated_users': self.migrated_users,
            'failed_users': self.failed_users,
            'success_rate': round((self.migrated_users / self.total_users * 100) if self.total_users > 0 else 0, 2),
            'duration_seconds': duration.total_seconds() if duration else None,
            'errors_count': len(self.errors),
            'warnings_count': len(self.warnings),
            'errors': self.errors,
            'warnings': self.warnings,
            'backup_path': self.backup_path,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None
        }


class DataMigration:
    """Main class for orchestrating JSON to PostgreSQL data migration."""
    
    def __init__(
        self,
        json_file_path: str,
        batch_size: int = 100,
        max_concurrent: int = 5,
        create_backup: bool = True,
        validate_before: bool = True,
        validate_after: bool = True
    ):
        """
        Initialize data migration.
        
        Args:
            json_file_path: Path to the JSON data file
            batch_size: Number of records to process per batch
            max_concurrent: Maximum concurrent operations
            create_backup: Whether to create backup before migration
            validate_before: Whether to validate data before migration
            validate_after: Whether to validate data after migration
        """
        self.json_file_path = Path(json_file_path)
        self.batch_size = batch_size
        self.max_concurrent = max_concurrent
        self.create_backup = create_backup
        self.validate_before = validate_before
        self.validate_after = validate_after
        
        # Initialize components
        self.data_mapper = DataMapper()
        self.validator = DataValidator(str(self.json_file_path))
        self.batch_processor = BatchProcessor(batch_size, max_concurrent)
        self.migration_lock = MigrationLock("json_to_postgresql_migration")
        
        if self.create_backup:
            self.backup_manager = BackupManager(str(self.json_file_path))
    
    async def migrate(
        self,
        truncate_tables: bool = False,
        dry_run: bool = False
    ) -> MigrationResult:
        """
        Execute the complete migration process.
        
        Args:
            truncate_tables: Whether to truncate target tables before migration
            dry_run: Whether to perform a dry run without actual data insertion
            
        Returns:
            MigrationResult with migration details
        """
        result = MigrationResult()
        
        try:
            async with self.migration_lock.acquire(timeout=300):
                # Initialize migration logging
                await DatabaseUtils.create_migration_log_table()
                result.migration_log_id = await DatabaseUtils.log_migration_start(
                    migration_type="json_to_postgresql",
                    total_items=0,  # Will be updated after loading data
                    metadata={
                        'source_file': str(self.json_file_path),
                        'batch_size': self.batch_size,
                        'dry_run': dry_run,
                        'truncate_tables': truncate_tables
                    }
                )
                
                # Step 1: Pre-migration validation
                if self.validate_before:
                    logger.info("Starting pre-migration validation...")
                    await self._validate_preconditions(result)
                    if not result.success and len(result.errors) > 0:
                        return result
                
                # Step 2: Load and validate JSON data
                logger.info("Loading JSON data...")
                json_data = await self._load_and_validate_json(result)
                if not json_data:
                    return result
                
                result.total_users = len(json_data.get('users', []))
                
                # Update migration log with total items
                await DatabaseUtils.log_migration_end(
                    result.migration_log_id,
                    status='running',
                    processed_items=0,
                    failed_items=0
                )
                
                # Step 3: Create backup
                if self.create_backup and not dry_run:
                    logger.info("Creating backup...")
                    result.backup_path = self.backup_manager.create_backup()
                
                # Step 4: Prepare database
                if truncate_tables and not dry_run:
                    await self._prepare_database(result)
                
                # Step 5: Migrate data
                logger.info(f"Starting migration of {result.total_users} users...")
                await self._migrate_users(json_data, result, dry_run)
                
                # Step 6: Migrate analytics data
                if not dry_run:
                    logger.info("Migrating analytics data...")
                    await self._migrate_analytics(json_data, result)
                
                # Step 7: Post-migration validation
                if self.validate_after and not dry_run:
                    logger.info("Starting post-migration validation...")
                    await self._validate_migration_integrity(json_data, result)
                
                result.finalize()
                
                # Log final result
                await DatabaseUtils.log_migration_end(
                    result.migration_log_id,
                    status='success' if result.success else 'failed',
                    processed_items=result.migrated_users,
                    failed_items=result.failed_users,
                    error_message='; '.join(result.errors) if result.errors else None
                )
                
                logger.info(f"Migration completed. Success: {result.success}")
                return result
                
        except Exception as e:
            result.add_error(f"Migration failed with exception: {e}")
            result.finalize()
            
            if result.migration_log_id:
                await DatabaseUtils.log_migration_end(
                    result.migration_log_id,
                    status='failed',
                    processed_items=result.migrated_users,
                    failed_items=result.failed_users,
                    error_message=str(e)
                )
            
            return result
    
    async def _validate_preconditions(self, result: MigrationResult):
        """Validate preconditions for migration."""
        # Check if source file exists
        if not self.json_file_path.exists():
            result.add_error(f"Source JSON file not found: {self.json_file_path}")
            return
        
        # Check database connectivity
        if not await DatabaseUtils.check_database_connection():
            result.add_error("Cannot connect to PostgreSQL database")
            return
        
        # Check file size and estimate time
        file_size = self.json_file_path.stat().st_size
        file_size_str = MigrationUtils.format_file_size(file_size)
        logger.info(f"Source file size: {file_size_str}")
        
        if file_size > 100 * 1024 * 1024:  # 100MB
            result.add_warning(f"Large file detected ({file_size_str}). Migration may take a long time.")
    
    async def _load_and_validate_json(self, result: MigrationResult) -> Optional[Dict[str, Any]]:
        """Load and validate JSON data structure."""
        try:
            # Load JSON data
            json_data = await self.validator.load_json_data()
            
            # Validate structure
            validation_result = self.validator.validate_json_structure()
            
            if not validation_result.is_valid:
                for error in validation_result.errors:
                    result.add_error(f"JSON validation error: {error}")
                return None
            
            for warning in validation_result.warnings:
                result.add_warning(f"JSON validation warning: {warning}")
            
            logger.info(f"JSON validation completed. Users found: {validation_result.stats.get('total_users', 0)}")
            return json_data
            
        except ValidationError as e:
            result.add_error(f"JSON validation failed: {e}")
            return None
    
    async def _prepare_database(self, result: MigrationResult):
        """Prepare database for migration."""
        try:
            # Truncate tables in correct order (considering foreign keys)
            tables_to_truncate = [
                'user_subscriptions',
                'match_analyses',
                'player_stats_cache',
                'payments',
                'users'
            ]
            
            for table_name in tables_to_truncate:
                try:
                    await DatabaseUtils.truncate_table(table_name, cascade=True)
                    logger.info(f"Truncated table: {table_name}")
                except Exception as e:
                    result.add_warning(f"Could not truncate table {table_name}: {e}")
            
        except Exception as e:
            result.add_error(f"Failed to prepare database: {e}")
    
    async def _migrate_users(
        self,
        json_data: Dict[str, Any],
        result: MigrationResult,
        dry_run: bool
    ):
        """Migrate user data with batch processing."""
        users_data = json_data.get('users', [])
        
        if not users_data:
            result.add_warning("No users found in JSON data")
            return
        
        # Create progress tracker
        progress_tracker = ProgressTracker(
            total_items=len(users_data),
            description="User Migration"
        )
        
        # Process users in batches
        batch_results = await self.batch_processor.process_batches(
            items=users_data,
            processor_func=lambda user_data: self._migrate_single_user(user_data, dry_run),
            progress_tracker=progress_tracker
        )
        
        # Process results
        for success, user_result, error_message in batch_results:
            if success:
                result.migrated_users += 1
            else:
                result.failed_users += 1
                if error_message:
                    result.add_error(f"User migration error: {error_message}")
        
        # Log final progress
        progress_tracker.report_progress()
        final_report = progress_tracker.get_final_report()
        logger.info(f"User migration completed: {final_report}")
    
    async def _migrate_single_user(
        self,
        user_json: Dict[str, Any],
        dry_run: bool
    ) -> Dict[str, Any]:
        """
        Migrate a single user and their subscription.
        
        Args:
            user_json: User data from JSON
            dry_run: Whether this is a dry run
            
        Returns:
            Migration result for the user
        """
        user_id = user_json.get('user_id')
        
        try:
            # Map user data
            user_data = self.data_mapper.map_user_data(user_json)
            
            # Validate mapped user data
            if not self.data_mapper.validate_mapped_user(user_data):
                raise MigrationError(f"Invalid user data for user_id {user_id}")
            
            # Map subscription data
            subscription_data = self.data_mapper.map_subscription_data(
                user_json, user_data['id']
            )
            
            # Validate mapped subscription data
            if not self.data_mapper.validate_mapped_subscription(subscription_data):
                raise MigrationError(f"Invalid subscription data for user_id {user_id}")
            
            if dry_run:
                logger.debug(f"Dry run: Would migrate user {user_id}")
                return {'user_id': user_id, 'status': 'dry_run_success'}
            
            # Insert into database
            async with get_async_session() as session:
                # Create user
                user = User(**user_data)
                session.add(user)
                await session.flush()
                
                # Create subscription
                subscription = UserSubscription(**subscription_data)
                session.add(subscription)
                
                await session.commit()
                
            logger.debug(f"Successfully migrated user {user_id}")
            return {'user_id': user_id, 'status': 'success', 'db_id': str(user.id)}
            
        except Exception as e:
            logger.error(f"Failed to migrate user {user_id}: {e}")
            raise MigrationError(f"User {user_id} migration failed: {e}")
    
    async def _migrate_analytics(
        self,
        json_data: Dict[str, Any],
        result: MigrationResult
    ):
        """Migrate analytics data."""
        try:
            analytics_entries = self.data_mapper.create_analytics_entries(json_data)
            
            if not analytics_entries:
                result.add_warning("No analytics entries to migrate")
                return
            
            async with get_async_session() as session:
                for entry in analytics_entries:
                    analytics = Analytics(**entry)
                    session.add(analytics)
                
                await session.commit()
            
            logger.info(f"Migrated {len(analytics_entries)} analytics entries")
            
        except Exception as e:
            result.add_error(f"Analytics migration failed: {e}")
    
    async def _validate_migration_integrity(
        self,
        original_json_data: Dict[str, Any],
        result: MigrationResult
    ):
        """Validate migration integrity by comparing original and migrated data."""
        try:
            validation_result = await self.validator.validate_migration_integrity(
                original_json_data
            )
            
            for error in validation_result.errors:
                result.add_error(f"Migration integrity error: {error}")
            
            for warning in validation_result.warnings:
                result.add_warning(f"Migration integrity warning: {warning}")
            
            if validation_result.is_valid:
                logger.info("Migration integrity validation passed")
            else:
                logger.error("Migration integrity validation failed")
                
        except Exception as e:
            result.add_error(f"Migration integrity validation failed: {e}")
    
    async def rollback_migration(
        self,
        backup_path: Optional[str] = None,
        migration_log_id: Optional[str] = None
    ) -> bool:
        """
        Rollback migration by restoring from backup and clearing database.
        
        Args:
            backup_path: Path to backup file
            migration_log_id: Migration log ID for tracking
            
        Returns:
            True if rollback successful
        """
        try:
            logger.info("Starting migration rollback...")
            
            # Clear database tables
            await self._prepare_database(MigrationResult())
            
            # Restore backup if provided
            if backup_path and self.create_backup:
                self.backup_manager.restore_backup(backup_path)
                logger.info("Backup restored successfully")
            
            # Log rollback
            if migration_log_id:
                await DatabaseUtils.log_migration_end(
                    migration_log_id,
                    status='rolled_back',
                    processed_items=0,
                    failed_items=0,
                    error_message="Migration rolled back by user request"
                )
            
            logger.info("Migration rollback completed")
            return True
            
        except Exception as e:
            logger.error(f"Migration rollback failed: {e}")
            return False
    
    async def get_migration_status(self) -> Dict[str, Any]:
        """
        Get current migration status from database.
        
        Returns:
            Dictionary with migration status information
        """
        try:
            async with get_async_session() as session:
                # Get database counts
                user_count = await DatabaseUtils.get_table_count('users')
                subscription_count = await DatabaseUtils.get_table_count('user_subscriptions')
                
                # Get recent migration logs
                result = await session.execute(text("""
                    SELECT migration_type, start_time, end_time, status, 
                           total_items, processed_items, failed_items
                    FROM migration_logs 
                    WHERE migration_type = 'json_to_postgresql'
                    ORDER BY created_at DESC 
                    LIMIT 5
                """))
                
                recent_migrations = []
                for row in result:
                    recent_migrations.append({
                        'migration_type': row.migration_type,
                        'start_time': row.start_time.isoformat() if row.start_time else None,
                        'end_time': row.end_time.isoformat() if row.end_time else None,
                        'status': row.status,
                        'total_items': row.total_items,
                        'processed_items': row.processed_items,
                        'failed_items': row.failed_items
                    })
                
                return {
                    'database_status': {
                        'users': user_count,
                        'subscriptions': subscription_count,
                        'connection_ok': await DatabaseUtils.check_database_connection()
                    },
                    'recent_migrations': recent_migrations,
                    'source_file': {
                        'path': str(self.json_file_path),
                        'exists': self.json_file_path.exists(),
                        'size': self.json_file_path.stat().st_size if self.json_file_path.exists() else 0
                    }
                }
                
        except Exception as e:
            logger.error(f"Failed to get migration status: {e}")
            return {'error': str(e)}