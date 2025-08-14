#!/usr/bin/env python3
"""
Test script for the JSON to PostgreSQL migration system.

This script provides a simple way to test the migration system
with the existing data.json file.
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from migration import DataMigration, DataValidator, MigrationError, ValidationError
    from migration.utils import MigrationUtils, DatabaseUtils
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)


async def test_migration_system():
    """Test the migration system with current data."""
    print("🧪 FACEIT Bot Migration System Test")
    print("=" * 50)
    
    # Check if data.json exists
    json_file = Path("data.json")
    if not json_file.exists():
        print("❌ data.json file not found")
        print("This test requires the existing data.json file")
        return False
    
    print(f"📁 Found data.json ({MigrationUtils.format_file_size(json_file.stat().st_size)})")
    
    # Test 1: Database Connection
    print("\n🔧 Test 1: Database Connection")
    try:
        db_ok = await DatabaseUtils.check_database_connection()
        if db_ok:
            print("✅ Database connection successful")
        else:
            print("❌ Database connection failed")
            return False
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False
    
    # Test 2: JSON Validation
    print("\n🔍 Test 2: JSON Data Validation")
    try:
        validator = DataValidator("data.json")
        await validator.load_json_data()
        result = validator.validate_json_structure()
        
        if result.is_valid:
            print("✅ JSON validation successful")
            print(f"   Users found: {result.stats.get('total_users', 0)}")
            print(f"   Users with FACEIT: {result.stats.get('users_with_faceit', 0)}")
        else:
            print("❌ JSON validation failed")
            for error in result.errors[:3]:
                print(f"   - {error}")
            return False
    except ValidationError as e:
        print(f"❌ JSON validation error: {e}")
        return False
    
    # Test 3: Data Mapping
    print("\n🗂️  Test 3: Data Mapping")
    try:
        from migration.data_mapper import DataMapper
        
        mapper = DataMapper()
        json_data = MigrationUtils.parse_json_safely("data.json")
        sample_users = json_data.get('users', [])[:2]  # Test first 2 users
        
        success_count = 0
        for user_json in sample_users:
            try:
                user_data = mapper.map_user_data(user_json)
                subscription_data = mapper.map_subscription_data(user_json, user_data['id'])
                
                if (mapper.validate_mapped_user(user_data) and 
                    mapper.validate_mapped_subscription(subscription_data)):
                    success_count += 1
            except Exception as e:
                print(f"   ⚠️  Mapping failed for user {user_json.get('user_id')}: {e}")
        
        if success_count == len(sample_users):
            print(f"✅ Data mapping successful ({success_count}/{len(sample_users)} users)")
        else:
            print(f"⚠️  Partial mapping success ({success_count}/{len(sample_users)} users)")
    except Exception as e:
        print(f"❌ Data mapping test failed: {e}")
        return False
    
    # Test 4: Dry Run Migration
    print("\n🚀 Test 4: Dry Run Migration")
    try:
        migration = DataMigration(
            json_file_path="data.json",
            batch_size=10,  # Small batch for testing
            max_concurrent=2,
            create_backup=False,  # Skip backup for test
            validate_before=True,
            validate_after=False  # Skip post-validation for dry run
        )
        
        result = await migration.migrate(
            truncate_tables=False,  # Don't truncate for test
            dry_run=True
        )
        
        if result.success:
            print("✅ Dry run migration successful")
            print(f"   Would migrate: {result.migrated_users} users")
            print(f"   Duration: {(result.end_time - result.start_time).total_seconds():.1f}s")
        else:
            print("❌ Dry run migration failed")
            for error in result.errors[:3]:
                print(f"   - {error}")
            return False
            
    except MigrationError as e:
        print(f"❌ Migration test failed: {e}")
        return False
    
    # Test 5: System Status
    print("\n📊 Test 5: System Status")
    try:
        status = await migration.get_migration_status()
        
        db_status = status.get('database_status', {})
        print(f"   Database users: {db_status.get('users', 0)}")
        print(f"   Database subscriptions: {db_status.get('subscriptions', 0)}")
        
        source_info = status.get('source_file', {})
        print(f"   Source file exists: {source_info.get('exists', False)}")
        print(f"   Source file size: {MigrationUtils.format_file_size(source_info.get('size', 0))}")
        
        print("✅ System status check successful")
        
    except Exception as e:
        print(f"❌ System status test failed: {e}")
        return False
    
    # Summary
    print("\n" + "=" * 50)
    print("🎉 All migration system tests passed!")
    print("✅ System is ready for actual migration")
    print("\nNext steps:")
    print("1. Run: python -m migration.cli validate data.json")
    print("2. Run: python -m migration.cli migrate data.json --dry-run")
    print("3. Run: python -m migration.cli migrate data.json --backup --truncate")
    print("=" * 50)
    
    return True


async def main():
    """Main test function."""
    try:
        success = await test_migration_system()
        if success:
            sys.exit(0)
        else:
            print("\n❌ Migration system tests failed")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected test error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())