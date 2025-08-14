"""Command-line interface for JSON to PostgreSQL migration.

Provides interactive and batch command-line interface for managing
the migration process with comprehensive options and safety features.
"""

import argparse
import asyncio
import logging
import json
import sys
from typing import Optional, Dict, Any
from pathlib import Path
import signal

from .migrate_data import DataMigration, MigrationResult
from .validator import DataValidator
from .utils import MigrationUtils, DatabaseUtils
from config.settings import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('migration.log')
    ]
)
logger = logging.getLogger(__name__)


class MigrationCLI:
    """Command-line interface for data migration operations."""
    
    def __init__(self):
        self.current_migration = None
        self.interrupted = False
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle interrupt signals gracefully."""
        print("\n⚠️  Migration interrupted by user. Cleaning up...")
        self.interrupted = True
        if self.current_migration:
            # The migration system should handle this gracefully
            pass
    
    async def run(self):
        """Main entry point for CLI."""
        parser = self._create_parser()
        args = parser.parse_args()
        
        # Set log level
        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        elif args.quiet:
            logging.getLogger().setLevel(logging.WARNING)
        
        try:
            # Execute command
            if args.command == 'migrate':
                await self._cmd_migrate(args)
            elif args.command == 'validate':
                await self._cmd_validate(args)
            elif args.command == 'status':
                await self._cmd_status(args)
            elif args.command == 'rollback':
                await self._cmd_rollback(args)
            elif args.command == 'backup':
                await self._cmd_backup(args)
            else:
                parser.print_help()
                
        except KeyboardInterrupt:
            print("\n⚠️  Operation cancelled by user")
            sys.exit(1)
        except Exception as e:
            logger.error(f"CLI error: {e}")
            print(f"❌ Error: {e}")
            sys.exit(1)
    
    def _create_parser(self) -> argparse.ArgumentParser:
        """Create argument parser with all commands and options."""
        parser = argparse.ArgumentParser(
            description="FACEIT Telegram Bot - JSON to PostgreSQL Migration Tool",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Validate JSON data structure
  python -m migration.cli validate data.json
  
  # Perform dry run migration
  python -m migration.cli migrate data.json --dry-run
  
  # Full migration with backup
  python -m migration.cli migrate data.json --backup --truncate
  
  # Check migration status
  python -m migration.cli status
  
  # Rollback last migration
  python -m migration.cli rollback --confirm
            """
        )
        
        # Global options
        parser.add_argument('--verbose', '-v', action='store_true',
                          help='Enable verbose logging')
        parser.add_argument('--quiet', '-q', action='store_true',
                          help='Enable quiet mode (warnings and errors only)')
        parser.add_argument('--config', type=str,
                          help='Path to configuration file')
        
        # Subcommands
        subparsers = parser.add_subparsers(dest='command', help='Available commands')
        
        # Migrate command
        migrate_parser = subparsers.add_parser('migrate', help='Run data migration')
        migrate_parser.add_argument('json_file', type=str,
                                  help='Path to JSON data file')
        migrate_parser.add_argument('--batch-size', type=int, default=100,
                                  help='Batch size for processing (default: 100)')
        migrate_parser.add_argument('--max-concurrent', type=int, default=5,
                                  help='Maximum concurrent operations (default: 5)')
        migrate_parser.add_argument('--dry-run', action='store_true',
                                  help='Perform dry run without actual data insertion')
        migrate_parser.add_argument('--no-backup', action='store_true',
                                  help='Skip creating backup before migration')
        migrate_parser.add_argument('--no-validate-before', action='store_true',
                                  help='Skip pre-migration validation')
        migrate_parser.add_argument('--no-validate-after', action='store_true',
                                  help='Skip post-migration validation')
        migrate_parser.add_argument('--truncate', action='store_true',
                                  help='Truncate target tables before migration')
        migrate_parser.add_argument('--force', action='store_true',
                                  help='Force migration even if validation fails')
        
        # Validate command
        validate_parser = subparsers.add_parser('validate', help='Validate data structure')
        validate_parser.add_argument('json_file', type=str,
                                   help='Path to JSON data file')
        validate_parser.add_argument('--database', action='store_true',
                                   help='Also validate database state')
        validate_parser.add_argument('--report', type=str,
                                   help='Path to save validation report')
        
        # Status command
        status_parser = subparsers.add_parser('status', help='Show migration status')
        status_parser.add_argument('--json', action='store_true',
                                 help='Output in JSON format')
        
        # Rollback command
        rollback_parser = subparsers.add_parser('rollback', help='Rollback migration')
        rollback_parser.add_argument('--backup-path', type=str,
                                   help='Path to backup file for restoration')
        rollback_parser.add_argument('--migration-id', type=str,
                                   help='Specific migration ID to rollback')
        rollback_parser.add_argument('--confirm', action='store_true',
                                   help='Confirm rollback without interactive prompt')
        
        # Backup command
        backup_parser = subparsers.add_parser('backup', help='Create backup of JSON data')
        backup_parser.add_argument('json_file', type=str,
                                 help='Path to JSON data file')
        backup_parser.add_argument('--output-dir', type=str, default='backups',
                                 help='Output directory for backup (default: backups)')
        
        return parser
    
    async def _cmd_migrate(self, args):
        """Execute migration command."""
        print("🚀 Starting JSON to PostgreSQL migration...")
        print(f"📁 Source file: {args.json_file}")
        
        # Check if source file exists
        if not Path(args.json_file).exists():
            print(f"❌ Source file not found: {args.json_file}")
            sys.exit(1)
        
        # Create migration instance
        migration = DataMigration(
            json_file_path=args.json_file,
            batch_size=args.batch_size,
            max_concurrent=args.max_concurrent,
            create_backup=not args.no_backup,
            validate_before=not args.no_validate_before,
            validate_after=not args.no_validate_after
        )
        
        self.current_migration = migration
        
        # Display migration parameters
        print(f"⚙️  Configuration:")
        print(f"   • Batch size: {args.batch_size}")
        print(f"   • Max concurrent: {args.max_concurrent}")
        print(f"   • Dry run: {args.dry_run}")
        print(f"   • Create backup: {not args.no_backup}")
        print(f"   • Truncate tables: {args.truncate}")
        print(f"   • Validate before: {not args.no_validate_before}")
        print(f"   • Validate after: {not args.no_validate_after}")
        
        # Confirm if not dry run
        if not args.dry_run and not args.force:
            if not self._confirm_migration():
                print("❌ Migration cancelled by user")
                return
        
        # Execute migration
        try:
            result = await migration.migrate(
                truncate_tables=args.truncate,
                dry_run=args.dry_run
            )
            
            # Display results
            self._display_migration_result(result, args.dry_run)
            
            if not result.success:
                sys.exit(1)
                
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            logger.exception("Migration failed with exception")
            sys.exit(1)
        finally:
            self.current_migration = None
    
    async def _cmd_validate(self, args):
        """Execute validation command."""
        print("🔍 Validating data structure...")
        print(f"📁 Source file: {args.json_file}")
        
        if not Path(args.json_file).exists():
            print(f"❌ Source file not found: {args.json_file}")
            sys.exit(1)
        
        validator = DataValidator(args.json_file)
        
        try:
            # Load and validate JSON
            await validator.load_json_data()
            json_result = validator.validate_json_structure()
            
            results = [json_result]
            
            # Validate database if requested
            if args.database:
                print("🔍 Validating database state...")
                db_result = await validator.validate_database_state()
                results.append(db_result)
            
            # Display results
            self._display_validation_results(results)
            
            # Generate report if requested
            if args.report:
                report = validator.generate_validation_report(results, args.report)
                print(f"📄 Validation report saved to: {args.report}")
            
            # Exit with error code if validation failed
            if not all(result.is_valid for result in results):
                sys.exit(1)
                
        except Exception as e:
            print(f"❌ Validation failed: {e}")
            logger.exception("Validation failed with exception")
            sys.exit(1)
    
    async def _cmd_status(self, args):
        """Execute status command."""
        print("📊 Checking migration status...")
        
        try:
            # Create a dummy migration instance to get status
            migration = DataMigration(json_file_path="dummy")
            status = await migration.get_migration_status()
            
            if args.json:
                print(json.dumps(status, indent=2))
            else:
                self._display_status(status)
                
        except Exception as e:
            print(f"❌ Failed to get status: {e}")
            logger.exception("Status check failed")
            sys.exit(1)
    
    async def _cmd_rollback(self, args):
        """Execute rollback command."""
        print("⏪ Rolling back migration...")
        
        # Confirm rollback
        if not args.confirm:
            if not self._confirm_rollback():
                print("❌ Rollback cancelled by user")
                return
        
        try:
            migration = DataMigration(json_file_path="dummy")
            success = await migration.rollback_migration(
                backup_path=args.backup_path,
                migration_log_id=args.migration_id
            )
            
            if success:
                print("✅ Migration rollback completed successfully")
            else:
                print("❌ Migration rollback failed")
                sys.exit(1)
                
        except Exception as e:
            print(f"❌ Rollback failed: {e}")
            logger.exception("Rollback failed with exception")
            sys.exit(1)
    
    async def _cmd_backup(self, args):
        """Execute backup command."""
        print("💾 Creating backup...")
        print(f"📁 Source file: {args.json_file}")
        
        if not Path(args.json_file).exists():
            print(f"❌ Source file not found: {args.json_file}")
            sys.exit(1)
        
        try:
            from .utils import BackupManager
            backup_manager = BackupManager(args.json_file, args.output_dir)
            backup_path = backup_manager.create_backup()
            
            print(f"✅ Backup created: {backup_path}")
            
        except Exception as e:
            print(f"❌ Backup failed: {e}")
            logger.exception("Backup failed with exception")
            sys.exit(1)
    
    def _confirm_migration(self) -> bool:
        """Confirm migration with user input."""
        print("\n⚠️  This will modify your PostgreSQL database.")
        print("   Make sure you have proper backups before proceeding.")
        response = input("   Do you want to continue? [y/N]: ").strip().lower()
        return response in ['y', 'yes']
    
    def _confirm_rollback(self) -> bool:
        """Confirm rollback with user input."""
        print("\n⚠️  This will clear migrated data from PostgreSQL database.")
        print("   This action cannot be undone without proper backups.")
        response = input("   Do you want to continue? [y/N]: ").strip().lower()
        return response in ['y', 'yes']
    
    def _display_migration_result(self, result: MigrationResult, dry_run: bool):
        """Display migration results in a formatted way."""
        print("\n" + "="*60)
        print("📋 MIGRATION RESULTS")
        print("="*60)
        
        status_icon = "✅" if result.success else "❌"
        mode = "DRY RUN" if dry_run else "MIGRATION"
        print(f"{status_icon} {mode} {'COMPLETED' if result.success else 'FAILED'}")
        
        print(f"\n📊 Statistics:")
        print(f"   • Total users: {result.total_users}")
        print(f"   • Migrated: {result.migrated_users}")
        print(f"   • Failed: {result.failed_users}")
        
        if result.total_users > 0:
            success_rate = (result.migrated_users / result.total_users) * 100
            print(f"   • Success rate: {success_rate:.1f}%")
        
        if result.end_time and result.start_time:
            duration = (result.end_time - result.start_time).total_seconds()
            print(f"   • Duration: {duration:.1f} seconds")
        
        if result.backup_path:
            print(f"\n💾 Backup: {result.backup_path}")
        
        if result.errors:
            print(f"\n❌ Errors ({len(result.errors)}):")
            for error in result.errors[:5]:  # Show first 5 errors
                print(f"   • {error}")
            if len(result.errors) > 5:
                print(f"   ... and {len(result.errors) - 5} more errors")
        
        if result.warnings:
            print(f"\n⚠️  Warnings ({len(result.warnings)}):")
            for warning in result.warnings[:3]:  # Show first 3 warnings
                print(f"   • {warning}")
            if len(result.warnings) > 3:
                print(f"   ... and {len(result.warnings) - 3} more warnings")
        
        print("="*60)
    
    def _display_validation_results(self, results):
        """Display validation results."""
        print("\n" + "="*60)
        print("🔍 VALIDATION RESULTS")
        print("="*60)
        
        for i, result in enumerate(results):
            validation_type = "JSON Structure" if i == 0 else "Database State"
            status_icon = "✅" if result.is_valid else "❌"
            print(f"{status_icon} {validation_type}: {'VALID' if result.is_valid else 'INVALID'}")
            
            if result.stats:
                print(f"   Statistics:")
                for key, value in result.stats.items():
                    print(f"   • {key}: {value}")
            
            if result.errors:
                print(f"   Errors ({len(result.errors)}):")
                for error in result.errors[:3]:
                    print(f"   • {error}")
                if len(result.errors) > 3:
                    print(f"   ... and {len(result.errors) - 3} more errors")
            
            if result.warnings:
                print(f"   Warnings ({len(result.warnings)}):")
                for warning in result.warnings[:3]:
                    print(f"   • {warning}")
                if len(result.warnings) > 3:
                    print(f"   ... and {len(result.warnings) - 3} more warnings")
            
            print("")
        
        print("="*60)
    
    def _display_status(self, status: Dict[str, Any]):
        """Display migration status."""
        print("\n" + "="*60)
        print("📊 MIGRATION STATUS")
        print("="*60)
        
        # Database status
        db_status = status.get('database_status', {})
        print(f"🗄️  Database:")
        print(f"   • Users: {db_status.get('users', 0)}")
        print(f"   • Subscriptions: {db_status.get('subscriptions', 0)}")
        connection_icon = "✅" if db_status.get('connection_ok') else "❌"
        print(f"   • Connection: {connection_icon}")
        
        # Source file status
        source_info = status.get('source_file', {})
        print(f"\n📁 Source File:")
        print(f"   • Path: {source_info.get('path', 'Unknown')}")
        exists_icon = "✅" if source_info.get('exists') else "❌"
        print(f"   • Exists: {exists_icon}")
        if source_info.get('size'):
            size_str = MigrationUtils.format_file_size(source_info['size'])
            print(f"   • Size: {size_str}")
        
        # Recent migrations
        recent = status.get('recent_migrations', [])
        if recent:
            print(f"\n📋 Recent Migrations:")
            for migration in recent[:3]:
                status_map = {
                    'success': '✅',
                    'failed': '❌',
                    'running': '⏳',
                    'rolled_back': '⏪'
                }
                status_icon = status_map.get(migration.get('status'), '❓')
                print(f"   {status_icon} {migration.get('start_time', 'Unknown')[:19]} - "
                      f"{migration.get('status', 'Unknown')} "
                      f"({migration.get('processed_items', 0)}/{migration.get('total_items', 0)})")
        
        print("="*60)


async def main():
    """Main entry point for the CLI."""
    cli = MigrationCLI()
    await cli.run()


if __name__ == "__main__":
    asyncio.run(main())