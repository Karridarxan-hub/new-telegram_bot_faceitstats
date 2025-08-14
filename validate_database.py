#!/usr/bin/env python3
"""
Database validation utility for FACEIT Telegram Bot.

This script validates the database setup and provides information about:
1. Connection status
2. Schema integrity 
3. Available tables and their structure
4. Alembic migration status

Usage:
    python validate_database.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


async def validate_database_setup():
    """Validate complete database setup."""
    print("=" * 60)
    print("FACEIT Telegram Bot - Database Validation")
    print("=" * 60)
    
    # Load environment
    from dotenv import load_dotenv
    load_dotenv('.env.docker')
    
    # Import our modules
    from config.database import create_database_config_from_env
    from database.connection import DatabaseConnectionManager
    from sqlalchemy import text
    
    # Set up environment for local testing
    original_db_url = os.getenv('DATABASE_URL')
    if original_db_url and '@postgres:' in original_db_url:
        modified_db_url = original_db_url.replace('@postgres:', '@localhost:')
        os.environ['DATABASE_URL'] = modified_db_url
        print("Using localhost for database connection")
    
    try:
        # Initialize database
        db_config = create_database_config_from_env()
        db_manager = DatabaseConnectionManager(db_config)
        await db_manager.initialize()
        
        print(f"Database Environment: {db_config.environment}")
        print(f"Connection Pooling: {'Enabled' if db_config.enable_connection_pooling else 'Disabled'}")
        print(f"Pool Size: {db_config.pool_size}")
        
        # Get health info
        health_info = await db_manager.health_check()
        print(f"Health Status: {health_info.get('status', 'unknown')}")
        print(f"Database Version: {health_info.get('database_version', 'unknown')}")
        print(f"Database Size: {health_info.get('database_size', 'unknown')}")
        print(f"Active Connections: {health_info.get('active_connections', 'unknown')}")
        
        # Validate schema
        async with db_manager.get_session() as session:
            # Check Alembic version
            result = await session.execute(text(
                "SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1"
            ))
            version = result.scalar()
            print(f"Alembic Version: {version if version else 'Not found'}")
            
            # List all tables with row counts
            result = await session.execute(text("""
                SELECT 
                    t.table_name,
                    COALESCE(s.n_tup_ins, 0) as row_count
                FROM information_schema.tables t
                LEFT JOIN pg_stat_user_tables s ON t.table_name = s.relname
                WHERE t.table_schema = 'public' 
                AND t.table_type = 'BASE TABLE'
                ORDER BY t.table_name
            """))
            
            tables_info = result.fetchall()
            
            print("\nDatabase Tables:")
            print("-" * 40)
            for table_name, row_count in tables_info:
                print(f"  {table_name:<25} {row_count:>10} rows")
            
            # Check constraints and indexes
            result = await session.execute(text("""
                SELECT 
                    schemaname,
                    tablename,
                    indexname,
                    indexdef
                FROM pg_indexes 
                WHERE schemaname = 'public'
                ORDER BY tablename, indexname
            """))
            
            indexes = result.fetchall()
            print(f"\nDatabase Indexes: {len(indexes)} total")
            
            # Check foreign keys
            result = await session.execute(text("""
                SELECT 
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc 
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = 'public'
                ORDER BY tc.table_name
            """))
            
            foreign_keys = result.fetchall()
            print(f"Foreign Key Constraints: {len(foreign_keys)} total")
            
            # Test basic operations
            print("\nTesting Basic Operations:")
            print("-" * 40)
            
            # Test insert into system_settings (with UUID generation)
            await session.execute(text("""
                INSERT INTO system_settings (id, key, value, description, category)
                VALUES (gen_random_uuid(), 'test_key', 'test_value', 'Test setting for validation', 'test')
                ON CONFLICT (key) DO UPDATE SET 
                    value = EXCLUDED.value,
                    updated_at = NOW()
            """))
            print("  INSERT operation: SUCCESS")
            
            # Test select
            result = await session.execute(text(
                "SELECT COUNT(*) FROM system_settings WHERE key = 'test_key'"
            ))
            count = result.scalar()
            print(f"  SELECT operation: SUCCESS ({count} rows)")
            
            # Test update
            await session.execute(text(
                "UPDATE system_settings SET description = 'Updated test setting' WHERE key = 'test_key'"
            ))
            print("  UPDATE operation: SUCCESS")
            
            # Test delete
            await session.execute(text(
                "DELETE FROM system_settings WHERE key = 'test_key'"
            ))
            print("  DELETE operation: SUCCESS")
            
            await session.commit()
        
        await db_manager.close()
        
        print("\n" + "=" * 60)
        print("Database validation completed successfully!")
        print("The FACEIT Telegram Bot database is ready for use.")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\nDatabase validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Restore original environment
        if original_db_url:
            os.environ['DATABASE_URL'] = original_db_url


if __name__ == "__main__":
    try:
        success = asyncio.run(validate_database_setup())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nValidation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nValidation failed with error: {e}")
        sys.exit(1)