"""Migration utility functions and helper classes.

Provides common functionality needed across the migration system including
progress tracking, error handling, backup management, and batch processing.
"""

import logging
import asyncio
import json
import shutil
import time
from typing import Dict, Any, List, Optional, Callable, AsyncIterator, Tuple
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from database.connection import get_async_session

logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Base exception for migration operations."""
    pass


class ProgressTracker:
    """Tracks and reports migration progress."""
    
    def __init__(self, total_items: int, description: str = "Migration"):
        self.total_items = total_items
        self.processed_items = 0
        self.failed_items = 0
        self.start_time = time.time()
        self.description = description
        self.last_report_time = 0
        self.report_interval = 5.0  # Report every 5 seconds
        
    def update(self, processed: int = 1, failed: int = 0):
        """Update progress counters."""
        self.processed_items += processed
        self.failed_items += failed
        
        # Report progress at intervals
        current_time = time.time()
        if current_time - self.last_report_time >= self.report_interval:
            self.report_progress()
            self.last_report_time = current_time
    
    def report_progress(self):
        """Report current progress."""
        elapsed = time.time() - self.start_time
        percentage = (self.processed_items / self.total_items * 100) if self.total_items > 0 else 0
        
        if self.processed_items > 0:
            rate = self.processed_items / elapsed
            eta = (self.total_items - self.processed_items) / rate if rate > 0 else 0
        else:
            rate = 0
            eta = 0
        
        logger.info(
            f"{self.description}: {self.processed_items}/{self.total_items} "
            f"({percentage:.1f}%) - {rate:.1f} items/sec - "
            f"ETA: {eta:.0f}s - Failed: {self.failed_items}"
        )
    
    def get_final_report(self) -> Dict[str, Any]:
        """Get final migration report."""
        elapsed = time.time() - self.start_time
        success_rate = ((self.processed_items - self.failed_items) / self.processed_items * 100) if self.processed_items > 0 else 0
        
        return {
            'total_items': self.total_items,
            'processed_items': self.processed_items,
            'failed_items': self.failed_items,
            'success_rate': round(success_rate, 2),
            'elapsed_time': round(elapsed, 2),
            'average_rate': round(self.processed_items / elapsed, 2) if elapsed > 0 else 0,
            'description': self.description
        }


class BackupManager:
    """Manages backup and restore operations for migration safety."""
    
    def __init__(self, source_file: str, backup_dir: str = "backups"):
        self.source_file = Path(source_file)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
        
    def create_backup(self) -> str:
        """
        Create a backup of the source file.
        
        Returns:
            Path to the backup file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{self.source_file.stem}_{timestamp}{self.source_file.suffix}"
        backup_path = self.backup_dir / backup_filename
        
        try:
            shutil.copy2(self.source_file, backup_path)
            logger.info(f"Backup created: {backup_path}")
            return str(backup_path)
        except Exception as e:
            raise MigrationError(f"Failed to create backup: {e}")
    
    def restore_backup(self, backup_path: str):
        """
        Restore from backup file.
        
        Args:
            backup_path: Path to backup file
        """
        try:
            shutil.copy2(backup_path, self.source_file)
            logger.info(f"Restored from backup: {backup_path}")
        except Exception as e:
            raise MigrationError(f"Failed to restore backup: {e}")
    
    def list_backups(self) -> List[str]:
        """
        List available backup files.
        
        Returns:
            List of backup file paths
        """
        pattern = f"{self.source_file.stem}_*{self.source_file.suffix}"
        backups = list(self.backup_dir.glob(pattern))
        return sorted([str(backup) for backup in backups], reverse=True)


class BatchProcessor:
    """Processes data in batches for efficient migration."""
    
    def __init__(self, batch_size: int = 100, max_concurrent: int = 5):
        self.batch_size = batch_size
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
    async def process_batches(
        self,
        items: List[Any],
        processor_func: Callable,
        progress_tracker: Optional[ProgressTracker] = None
    ) -> List[Tuple[bool, Any, Optional[str]]]:
        """
        Process items in batches with concurrency control.
        
        Args:
            items: List of items to process
            processor_func: Async function to process each item
            progress_tracker: Optional progress tracker
            
        Returns:
            List of (success, result, error_message) tuples
        """
        results = []
        
        # Split items into batches
        batches = [
            items[i:i + self.batch_size] 
            for i in range(0, len(items), self.batch_size)
        ]
        
        logger.info(f"Processing {len(items)} items in {len(batches)} batches")
        
        for batch_index, batch in enumerate(batches):
            batch_results = await self._process_single_batch(
                batch, processor_func, batch_index, progress_tracker
            )
            results.extend(batch_results)
        
        return results
    
    async def _process_single_batch(
        self,
        batch: List[Any],
        processor_func: Callable,
        batch_index: int,
        progress_tracker: Optional[ProgressTracker]
    ) -> List[Tuple[bool, Any, Optional[str]]]:
        """Process a single batch of items."""
        async with self.semaphore:
            tasks = []
            
            for item in batch:
                task = asyncio.create_task(
                    self._process_single_item(item, processor_func)
                )
                tasks.append(task)
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results and update progress
            processed_results = []
            for result in batch_results:
                if isinstance(result, Exception):
                    processed_results.append((False, None, str(result)))
                    if progress_tracker:
                        progress_tracker.update(processed=1, failed=1)
                else:
                    processed_results.append(result)
                    if progress_tracker:
                        progress_tracker.update(processed=1)
            
            logger.debug(f"Completed batch {batch_index + 1} with {len(batch)} items")
            return processed_results
    
    async def _process_single_item(
        self,
        item: Any,
        processor_func: Callable
    ) -> Tuple[bool, Any, Optional[str]]:
        """Process a single item with error handling."""
        try:
            result = await processor_func(item)
            return (True, result, None)
        except Exception as e:
            logger.error(f"Failed to process item: {e}")
            return (False, None, str(e))


class DatabaseUtils:
    """Database utility functions for migration operations."""
    
    @staticmethod
    async def check_database_connection() -> bool:
        """
        Check if database connection is working.
        
        Returns:
            True if connection is successful
        """
        try:
            async with get_async_session() as session:
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False
    
    @staticmethod
    async def get_table_count(table_name: str) -> int:
        """
        Get row count for a table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Number of rows in the table
        """
        try:
            async with get_async_session() as session:
                result = await session.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")
                )
                return result.scalar() or 0
        except Exception as e:
            logger.error(f"Failed to get count for table {table_name}: {e}")
            return 0
    
    @staticmethod
    async def truncate_table(table_name: str, cascade: bool = False):
        """
        Truncate a table.
        
        Args:
            table_name: Name of the table to truncate
            cascade: Whether to cascade to dependent tables
        """
        try:
            cascade_clause = " CASCADE" if cascade else ""
            async with get_async_session() as session:
                await session.execute(
                    text(f"TRUNCATE TABLE {table_name}{cascade_clause}")
                )
                await session.commit()
                logger.info(f"Truncated table: {table_name}")
        except Exception as e:
            raise MigrationError(f"Failed to truncate table {table_name}: {e}")
    
    @staticmethod
    async def create_migration_log_table():
        """Create migration log table for tracking migrations."""
        try:
            async with get_async_session() as session:
                await session.execute(text("""
                    CREATE TABLE IF NOT EXISTS migration_logs (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        migration_type VARCHAR(100) NOT NULL,
                        start_time TIMESTAMP WITH TIME ZONE NOT NULL,
                        end_time TIMESTAMP WITH TIME ZONE,
                        status VARCHAR(20) NOT NULL DEFAULT 'running',
                        total_items INTEGER DEFAULT 0,
                        processed_items INTEGER DEFAULT 0,
                        failed_items INTEGER DEFAULT 0,
                        error_message TEXT,
                        metadata JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
                await session.commit()
                logger.info("Migration log table created/verified")
        except Exception as e:
            logger.error(f"Failed to create migration log table: {e}")
    
    @staticmethod
    async def log_migration_start(
        migration_type: str,
        total_items: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log migration start.
        
        Args:
            migration_type: Type of migration
            total_items: Total items to process
            metadata: Optional metadata
            
        Returns:
            Migration log ID
        """
        try:
            log_id = str(uuid.uuid4())
            async with get_async_session() as session:
                await session.execute(text("""
                    INSERT INTO migration_logs 
                    (id, migration_type, start_time, total_items, metadata)
                    VALUES (:id, :migration_type, :start_time, :total_items, :metadata)
                """), {
                    'id': log_id,
                    'migration_type': migration_type,
                    'start_time': datetime.now(),
                    'total_items': total_items,
                    'metadata': json.dumps(metadata) if metadata else None
                })
                await session.commit()
                return log_id
        except Exception as e:
            logger.error(f"Failed to log migration start: {e}")
            return str(uuid.uuid4())  # Return a dummy ID to avoid breaking the flow
    
    @staticmethod
    async def log_migration_end(
        log_id: str,
        status: str,
        processed_items: int,
        failed_items: int,
        error_message: Optional[str] = None
    ):
        """
        Log migration end.
        
        Args:
            log_id: Migration log ID
            status: Migration status (success, failed, partial)
            processed_items: Number of processed items
            failed_items: Number of failed items
            error_message: Optional error message
        """
        try:
            async with get_async_session() as session:
                await session.execute(text("""
                    UPDATE migration_logs 
                    SET end_time = :end_time,
                        status = :status,
                        processed_items = :processed_items,
                        failed_items = :failed_items,
                        error_message = :error_message
                    WHERE id = :id
                """), {
                    'id': log_id,
                    'end_time': datetime.now(),
                    'status': status,
                    'processed_items': processed_items,
                    'failed_items': failed_items,
                    'error_message': error_message
                })
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to log migration end: {e}")


class MigrationLock:
    """Prevents concurrent migration operations."""
    
    def __init__(self, lock_name: str = "data_migration"):
        self.lock_name = lock_name
        self.lock_acquired = False
        self.lock_id = str(uuid.uuid4())
    
    @asynccontextmanager
    async def acquire(self, timeout: int = 300):
        """
        Acquire migration lock with timeout.
        
        Args:
            timeout: Lock timeout in seconds
        """
        try:
            await self._acquire_lock(timeout)
            self.lock_acquired = True
            logger.info(f"Migration lock acquired: {self.lock_name}")
            yield
        finally:
            if self.lock_acquired:
                await self._release_lock()
                logger.info(f"Migration lock released: {self.lock_name}")
    
    async def _acquire_lock(self, timeout: int):
        """Acquire the actual lock."""
        end_time = time.time() + timeout
        
        while time.time() < end_time:
            try:
                async with get_async_session() as session:
                    # Try to acquire lock using advisory lock
                    result = await session.execute(
                        text("SELECT pg_try_advisory_lock(:lock_key)"),
                        {'lock_key': hash(self.lock_name) % (2**31)}
                    )
                    
                    if result.scalar():
                        return  # Lock acquired
                    
                    # Wait and retry
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Error acquiring lock: {e}")
                await asyncio.sleep(1)
        
        raise MigrationError(f"Failed to acquire migration lock within {timeout} seconds")
    
    async def _release_lock(self):
        """Release the migration lock."""
        try:
            async with get_async_session() as session:
                await session.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {'lock_key': hash(self.lock_name) % (2**31)}
                )
        except Exception as e:
            logger.error(f"Error releasing lock: {e}")


class MigrationUtils:
    """Collection of utility functions for migration operations."""
    
    @staticmethod
    def parse_json_safely(file_path: str) -> Dict[str, Any]:
        """
        Parse JSON file with error handling.
        
        Args:
            file_path: Path to JSON file
            
        Returns:
            Parsed JSON data
            
        Raises:
            MigrationError: When JSON parsing fails
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise MigrationError(f"Invalid JSON in {file_path}: {e}")
        except FileNotFoundError:
            raise MigrationError(f"JSON file not found: {file_path}")
        except Exception as e:
            raise MigrationError(f"Failed to read JSON file {file_path}: {e}")
    
    @staticmethod
    def estimate_migration_time(
        total_items: int,
        sample_size: int = 10,
        time_per_item: float = 0.1
    ) -> Tuple[float, str]:
        """
        Estimate migration time.
        
        Args:
            total_items: Total number of items to migrate
            sample_size: Sample size for estimation
            time_per_item: Estimated time per item in seconds
            
        Returns:
            Tuple of (estimated_seconds, human_readable_time)
        """
        estimated_seconds = total_items * time_per_item
        
        if estimated_seconds < 60:
            human_time = f"{estimated_seconds:.0f} seconds"
        elif estimated_seconds < 3600:
            human_time = f"{estimated_seconds / 60:.1f} minutes"
        else:
            hours = estimated_seconds / 3600
            human_time = f"{hours:.1f} hours"
        
        return estimated_seconds, human_time
    
    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """
        Format file size in human-readable format.
        
        Args:
            size_bytes: File size in bytes
            
        Returns:
            Formatted file size string
        """
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    @staticmethod
    async def wait_for_database_ready(
        max_retries: int = 30,
        retry_delay: float = 1.0
    ):
        """
        Wait for database to be ready.
        
        Args:
            max_retries: Maximum number of connection attempts
            retry_delay: Delay between retries in seconds
            
        Raises:
            MigrationError: When database is not ready after max_retries
        """
        for attempt in range(max_retries):
            if await DatabaseUtils.check_database_connection():
                logger.info("Database is ready for migration")
                return
            
            logger.info(f"Database not ready, attempt {attempt + 1}/{max_retries}")
            await asyncio.sleep(retry_delay)
        
        raise MigrationError("Database is not ready for migration")
    
    @staticmethod
    def get_memory_usage() -> Dict[str, float]:
        """
        Get current memory usage statistics.
        
        Returns:
            Dictionary with memory usage information
        """
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            
            return {
                'rss_mb': memory_info.rss / 1024 / 1024,
                'vms_mb': memory_info.vms / 1024 / 1024,
                'percent': process.memory_percent()
            }
        except ImportError:
            logger.warning("psutil not available, memory usage not tracked")
            return {}
        except Exception as e:
            logger.error(f"Failed to get memory usage: {e}")
            return {}