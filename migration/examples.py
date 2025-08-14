"""Example usage of the JSON to PostgreSQL migration system.

This file demonstrates various ways to use the migration system,
from simple migrations to complex scenarios with custom validation.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any

from migration import (
    DataMigration, DataValidator, DataMapper, 
    MigrationUtils, ValidationError, MigrationError
)

# Configure logging for examples
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def example_basic_migration():
    """
    Example 1: Basic migration with default settings.
    
    This is the simplest way to migrate your JSON data to PostgreSQL.
    """
    print("=" * 60)
    print("EXAMPLE 1: Basic Migration")
    print("=" * 60)
    
    try:
        # Create migration instance with default settings
        migration = DataMigration(json_file_path="data.json")
        
        # Run migration
        result = await migration.migrate()
        
        # Display results
        if result.success:
            print(f"✅ Migration successful!")
            print(f"   Users migrated: {result.migrated_users}")
            print(f"   Duration: {(result.end_time - result.start_time).total_seconds():.1f}s")
        else:
            print(f"❌ Migration failed!")
            print(f"   Errors: {len(result.errors)}")
            for error in result.errors[:3]:
                print(f"   - {error}")
        
    except Exception as e:
        print(f"❌ Migration failed with exception: {e}")


async def example_dry_run_migration():
    """
    Example 2: Dry run migration to test without affecting database.
    
    Always run a dry run first to validate your data and migration process.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Dry Run Migration")
    print("=" * 60)
    
    try:
        migration = DataMigration(
            json_file_path="data.json",
            batch_size=50,  # Smaller batches for testing
            max_concurrent=3
        )
        
        # Perform dry run
        result = await migration.migrate(dry_run=True)
        
        print(f"🧪 Dry run completed")
        print(f"   Would migrate: {result.migrated_users} users")
        print(f"   Would fail: {result.failed_users} users")
        print(f"   Validation issues: {len(result.errors) + len(result.warnings)}")
        
        if result.success:
            print("✅ Ready for actual migration!")
        else:
            print("❌ Fix issues before migration:")
            for error in result.errors[:5]:
                print(f"   - {error}")
        
    except Exception as e:
        print(f"❌ Dry run failed: {e}")


async def example_advanced_migration():
    """
    Example 3: Advanced migration with custom settings and full validation.
    
    This example shows how to configure all migration options for production use.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Advanced Migration")
    print("=" * 60)
    
    try:
        # Advanced configuration
        migration = DataMigration(
            json_file_path="data.json",
            batch_size=200,          # Larger batches for performance
            max_concurrent=10,       # More concurrent operations
            create_backup=True,      # Always backup in production
            validate_before=True,    # Pre-migration validation
            validate_after=True      # Post-migration validation
        )
        
        # Show estimated time
        json_data = MigrationUtils.parse_json_safely("data.json")
        user_count = len(json_data.get('users', []))
        estimated_time, time_str = MigrationUtils.estimate_migration_time(user_count)
        
        print(f"📊 Migration Plan:")
        print(f"   Users to migrate: {user_count}")
        print(f"   Estimated time: {time_str}")
        print(f"   Batch size: 200")
        print(f"   Concurrent operations: 10")
        
        # Execute migration with full options
        result = await migration.migrate(
            truncate_tables=True,  # Clean start
            dry_run=False
        )
        
        # Detailed result analysis
        summary = result.get_summary()
        print(f"\n📋 Migration Results:")
        for key, value in summary.items():
            if key not in ['errors', 'warnings']:
                print(f"   {key}: {value}")
        
        if result.backup_path:
            print(f"💾 Backup available: {result.backup_path}")
        
    except Exception as e:
        print(f"❌ Advanced migration failed: {e}")


async def example_validation_workflow():
    """
    Example 4: Comprehensive data validation workflow.
    
    Shows how to validate JSON data, database state, and migration integrity.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Validation Workflow")
    print("=" * 60)
    
    try:
        validator = DataValidator("data.json")
        
        # Step 1: Load and validate JSON structure
        print("🔍 Step 1: Validating JSON structure...")
        await validator.load_json_data()
        json_result = validator.validate_json_structure()
        
        print(f"   Status: {'✅ Valid' if json_result.is_valid else '❌ Invalid'}")
        print(f"   Users found: {json_result.stats.get('total_users', 0)}")
        print(f"   Errors: {len(json_result.errors)}")
        print(f"   Warnings: {len(json_result.warnings)}")
        
        # Step 2: Validate database state
        print("\n🔍 Step 2: Validating database state...")
        db_result = await validator.validate_database_state()
        
        print(f"   Database users: {db_result.stats.get('db_total_users', 0)}")
        print(f"   Database status: {'✅ Ready' if db_result.is_valid else '❌ Issues found'}")
        
        # Step 3: Generate validation report
        print("\n📄 Step 3: Generating validation report...")
        report = validator.generate_validation_report(
            [json_result, db_result],
            "validation_report.md"
        )
        
        print(f"   Report saved: validation_report.md")
        print(f"   Report length: {len(report)} characters")
        
        # Decision logic
        if json_result.is_valid and db_result.is_valid:
            print("\n✅ All validations passed - Ready for migration!")
        else:
            print("\n❌ Validation issues found - Review before migration")
        
    except ValidationError as e:
        print(f"❌ Validation workflow failed: {e}")


async def example_error_handling_and_recovery():
    """
    Example 5: Error handling and recovery scenarios.
    
    Demonstrates how to handle migration failures and recover gracefully.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 5: Error Handling & Recovery")
    print("=" * 60)
    
    migration = None
    
    try:
        # Attempt migration with potential issues
        migration = DataMigration(
            json_file_path="data.json",
            batch_size=100,
            create_backup=True  # Important for recovery
        )
        
        print("🚀 Starting migration with error handling...")
        result = await migration.migrate()
        
        # Check for partial success
        if result.migrated_users > 0 and result.failed_users > 0:
            print("⚠️  Partial migration completed")
            print(f"   Success: {result.migrated_users}")
            print(f"   Failed: {result.failed_users}")
            print(f"   Success rate: {result.get_summary()['success_rate']}%")
            
            # Decide whether to rollback or continue
            if result.get_summary()['success_rate'] < 90:
                print("📊 Success rate too low - initiating rollback...")
                await migration.rollback_migration(result.backup_path)
                print("⏪ Rollback completed")
            else:
                print("📊 Success rate acceptable - keeping partial results")
        
        elif not result.success:
            print("❌ Migration completely failed")
            print("🔍 Error analysis:")
            
            # Categorize errors
            mapping_errors = [e for e in result.errors if 'mapping' in e.lower()]
            db_errors = [e for e in result.errors if 'database' in e.lower()]
            validation_errors = [e for e in result.errors if 'validation' in e.lower()]
            
            if mapping_errors:
                print(f"   📋 Data mapping issues: {len(mapping_errors)}")
            if db_errors:
                print(f"   🗄️  Database issues: {len(db_errors)}")
            if validation_errors:
                print(f"   🔍 Validation issues: {len(validation_errors)}")
            
            # Automatic recovery attempt
            if result.backup_path:
                print("🔧 Attempting automatic recovery...")
                recovery_success = await migration.rollback_migration(result.backup_path)
                if recovery_success:
                    print("✅ Recovery successful - data restored")
                else:
                    print("❌ Recovery failed - manual intervention needed")
        
        else:
            print("✅ Migration completed successfully!")
        
    except MigrationError as e:
        print(f"❌ Migration system error: {e}")
        if migration:
            print("🔧 Attempting emergency rollback...")
            await migration.rollback_migration()
    
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        print("🆘 Check logs and consider manual recovery")


async def example_batch_processing_optimization():
    """
    Example 6: Optimizing batch processing for large datasets.
    
    Shows how to configure batch processing for different dataset sizes.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 6: Batch Processing Optimization")
    print("=" * 60)
    
    try:
        # Analyze dataset first
        json_data = MigrationUtils.parse_json_safely("data.json")
        user_count = len(json_data.get('users', []))
        file_size = Path("data.json").stat().st_size
        
        print(f"📊 Dataset Analysis:")
        print(f"   Users: {user_count}")
        print(f"   File size: {MigrationUtils.format_file_size(file_size)}")
        
        # Determine optimal settings based on size
        if user_count < 1000:
            batch_size, max_concurrent = 100, 5
            strategy = "Small dataset - standard settings"
        elif user_count < 10000:
            batch_size, max_concurrent = 200, 10
            strategy = "Medium dataset - optimized settings"
        else:
            batch_size, max_concurrent = 500, 15
            strategy = "Large dataset - high-performance settings"
        
        print(f"📈 Optimization Strategy: {strategy}")
        print(f"   Batch size: {batch_size}")
        print(f"   Concurrent operations: {max_concurrent}")
        
        # Calculate memory usage estimate
        memory_info = MigrationUtils.get_memory_usage()
        if memory_info:
            print(f"   Current memory: {memory_info.get('rss_mb', 0):.1f} MB")
        
        # Execute with optimized settings
        migration = DataMigration(
            json_file_path="data.json",
            batch_size=batch_size,
            max_concurrent=max_concurrent
        )
        
        # Monitor performance
        start_memory = MigrationUtils.get_memory_usage()
        
        result = await migration.migrate(dry_run=True)  # Dry run for demo
        
        end_memory = MigrationUtils.get_memory_usage()
        
        if start_memory and end_memory:
            memory_delta = end_memory.get('rss_mb', 0) - start_memory.get('rss_mb', 0)
            print(f"💾 Memory usage delta: {memory_delta:.1f} MB")
        
        print(f"⚡ Performance Results:")
        print(f"   Processing rate: {result.migrated_users / max(1, (result.end_time - result.start_time).total_seconds()):.1f} users/sec")
        
    except Exception as e:
        print(f"❌ Batch optimization example failed: {e}")


async def example_custom_data_mapping():
    """
    Example 7: Custom data mapping and transformation.
    
    Shows how to extend the data mapper for custom field transformations.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 7: Custom Data Mapping")
    print("=" * 60)
    
    try:
        # Create custom data mapper
        mapper = DataMapper()
        
        # Load sample JSON data
        json_data = MigrationUtils.parse_json_safely("data.json")
        sample_users = json_data.get('users', [])[:3]  # First 3 users
        
        print(f"🔄 Demonstrating data mapping for {len(sample_users)} users:")
        
        for i, user_json in enumerate(sample_users):
            print(f"\n👤 User {i + 1} (ID: {user_json.get('user_id')}):")
            
            # Map user data
            try:
                user_data = mapper.map_user_data(user_json)
                print(f"   ✅ User mapping successful")
                print(f"   📋 Fields mapped: {len(user_data)}")
                
                # Show some mapped fields
                key_fields = ['user_id', 'faceit_nickname', 'language', 'created_at']
                for field in key_fields:
                    if field in user_data:
                        value = user_data[field]
                        if hasattr(value, 'isoformat'):  # datetime
                            value = value.isoformat()[:19]
                        print(f"      {field}: {value}")
                
                # Map subscription data
                subscription_data = mapper.map_subscription_data(user_json, user_data['id'])
                print(f"   ✅ Subscription mapping successful")
                print(f"      tier: {subscription_data['tier'].value}")
                print(f"      daily_requests: {subscription_data['daily_requests']}")
                
                # Validate mapped data
                user_valid = mapper.validate_mapped_user(user_data)
                sub_valid = mapper.validate_mapped_subscription(subscription_data)
                
                validation_status = "✅ Valid" if (user_valid and sub_valid) else "❌ Invalid"
                print(f"   🔍 Validation: {validation_status}")
                
            except Exception as e:
                print(f"   ❌ Mapping failed: {e}")
        
        # Show mapping summary
        mapping_summary = mapper.get_mapping_summary()
        print(f"\n📋 Mapping Summary:")
        print(f"   User fields: {len(mapping_summary['user_mappings'])}")
        print(f"   Subscription fields: {len(mapping_summary['subscription_mappings'])}")
        
    except Exception as e:
        print(f"❌ Custom mapping example failed: {e}")


async def example_migration_monitoring():
    """
    Example 8: Migration monitoring and status tracking.
    
    Shows how to monitor migration progress and check system status.
    """
    print("\n" + "=" * 60)
    print("EXAMPLE 8: Migration Monitoring")
    print("=" * 60)
    
    try:
        # Create migration instance for status checking
        migration = DataMigration(json_file_path="data.json")
        
        # Check migration status
        print("📊 Checking migration status...")
        status = await migration.get_migration_status()
        
        # Display database status
        db_status = status.get('database_status', {})
        print(f"🗄️  Database Status:")
        print(f"   Users: {db_status.get('users', 0)}")
        print(f"   Subscriptions: {db_status.get('subscriptions', 0)}")
        print(f"   Connection: {'✅ OK' if db_status.get('connection_ok') else '❌ Failed'}")
        
        # Display source file status
        source_info = status.get('source_file', {})
        print(f"\n📁 Source File Status:")
        print(f"   Path: {source_info.get('path')}")
        print(f"   Exists: {'✅ Yes' if source_info.get('exists') else '❌ No'}")
        if source_info.get('size'):
            print(f"   Size: {MigrationUtils.format_file_size(source_info['size'])}")
        
        # Display recent migrations
        recent_migrations = status.get('recent_migrations', [])
        if recent_migrations:
            print(f"\n📋 Recent Migration History:")
            for migration_record in recent_migrations[:3]:
                status_icon = {
                    'success': '✅',
                    'failed': '❌', 
                    'running': '⏳',
                    'rolled_back': '⏪'
                }.get(migration_record.get('status'), '❓')
                
                print(f"   {status_icon} {migration_record.get('start_time', 'Unknown')[:19]}")
                print(f"      Status: {migration_record.get('status', 'Unknown')}")
                print(f"      Items: {migration_record.get('processed_items', 0)}/{migration_record.get('total_items', 0)}")
        else:
            print(f"\n📋 No recent migration history found")
        
        # System health check
        print(f"\n🏥 System Health Check:")
        
        # Check database connection
        db_ok = await DatabaseUtils.check_database_connection()
        print(f"   Database connection: {'✅ OK' if db_ok else '❌ Failed'}")
        
        # Check source file
        source_exists = Path("data.json").exists()
        print(f"   Source file: {'✅ Available' if source_exists else '❌ Missing'}")
        
        # Memory usage
        memory_info = MigrationUtils.get_memory_usage()
        if memory_info:
            print(f"   Memory usage: {memory_info.get('rss_mb', 0):.1f} MB ({memory_info.get('percent', 0):.1f}%)")
        
        # Overall system status
        system_ready = db_ok and source_exists
        print(f"\n🎯 System Status: {'✅ Ready for migration' if system_ready else '❌ Issues detected'}")
        
    except Exception as e:
        print(f"❌ Monitoring example failed: {e}")


async def run_all_examples():
    """Run all examples in sequence."""
    print("🚀 Starting Migration System Examples")
    print("=" * 60)
    
    examples = [
        example_basic_migration,
        example_dry_run_migration, 
        example_advanced_migration,
        example_validation_workflow,
        example_error_handling_and_recovery,
        example_batch_processing_optimization,
        example_custom_data_mapping,
        example_migration_monitoring
    ]
    
    for i, example_func in enumerate(examples, 1):
        try:
            print(f"\n🔍 Running Example {i}/{len(examples)}: {example_func.__name__}")
            await example_func()
            print(f"✅ Example {i} completed successfully")
        except Exception as e:
            print(f"❌ Example {i} failed: {e}")
            logger.exception(f"Example {i} failed with exception")
        
        # Small delay between examples
        await asyncio.sleep(1)
    
    print("\n" + "=" * 60)
    print("🏁 All examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    # Run all examples
    asyncio.run(run_all_examples())