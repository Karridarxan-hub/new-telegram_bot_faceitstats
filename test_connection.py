#!/usr/bin/env python3
"""
PostgreSQL connection test script for FACEIT Telegram Bot.

This script tests database connectivity and validates that:
1. Environment variables are loaded correctly
2. Database connection can be established
3. Basic queries work
4. Schema information can be retrieved

Usage:
    python test_connection.py

Environment variables required:
    DATABASE_URL - PostgreSQL connection string
"""

import asyncio
import os
import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_basic_connection():
    """Test basic database connection using asyncpg directly."""
    logger.info("=" * 60)
    logger.info("FACEIT Bot Database Connection Test")
    logger.info("=" * 60)
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv('.env.docker')  # Load Docker environment for testing
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("❌ DATABASE_URL environment variable is not set")
        logger.info("💡 Expected format: postgresql+asyncpg://user:password@host:port/database")
        return False
    
    # For local testing, replace 'postgres' hostname with 'localhost'
    if '@postgres:' in database_url:
        database_url = database_url.replace('@postgres:', '@localhost:')
        logger.info("🔄 Replaced 'postgres' hostname with 'localhost' for local testing")
    
    # Parse and display connection info (without credentials)
    logger.info(f"🔗 Database URL: {database_url.split('@')[0] if '@' in database_url else 'No credentials'}@***")
    
    try:
        import asyncpg
        
        # Convert SQLAlchemy URL to asyncpg format
        asyncpg_url = database_url.replace('postgresql+asyncpg://', 'postgresql://')
        
        logger.info("🔄 Testing direct asyncpg connection...")
        
        # Test connection
        conn = await asyncpg.connect(asyncpg_url)
        
        # Test basic query
        result = await conn.fetchval('SELECT version()')
        logger.info(f"✅ Connected successfully!")
        logger.info(f"📊 PostgreSQL version: {result.split()[1] if result else 'Unknown'}")
        
        # Test database info
        db_name = await conn.fetchval('SELECT current_database()')
        logger.info(f"📋 Database name: {db_name}")
        
        # Test connection count
        conn_count = await conn.fetchval(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
        )
        logger.info(f"🔗 Active connections: {conn_count}")
        
        await conn.close()
        logger.info("✅ Basic connection test passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Connection test failed: {e}")
        return False


async def test_sqlalchemy_connection():
    """Test database connection using SQLAlchemy async engine."""
    logger.info("\n" + "-" * 40)
    logger.info("Testing SQLAlchemy Async Connection")
    logger.info("-" * 40)
    
    try:
        from config.database import create_database_config_from_env
        from database.connection import DatabaseConnectionManager
        
        # For local testing, temporarily set modified DATABASE_URL
        original_db_url = os.getenv('DATABASE_URL')
        if original_db_url and '@postgres:' in original_db_url:
            modified_db_url = original_db_url.replace('@postgres:', '@localhost:')
            os.environ['DATABASE_URL'] = modified_db_url
            logger.info("🔄 Using localhost for database connection")
        
        # Create database config
        db_config = create_database_config_from_env()
        logger.info(f"📝 Database config: {db_config.environment} environment")
        logger.info(f"🔄 Pool enabled: {db_config.enable_connection_pooling}")
        logger.info(f"📊 Pool size: {db_config.pool_size}")
        
        # Restore original URL
        if original_db_url:
            os.environ['DATABASE_URL'] = original_db_url
        
        # Test connection manager
        logger.info("🔄 Initializing database connection manager...")
        db_manager = DatabaseConnectionManager(db_config)
        await db_manager.initialize()
        
        # Test health check
        logger.info("🔄 Running health check...")
        health_info = await db_manager.health_check()
        logger.info(f"💚 Health status: {health_info.get('status', 'unknown')}")
        
        if health_info.get('database_version'):
            logger.info(f"📊 Database version: {health_info['database_version']}")
        if health_info.get('active_connections'):
            logger.info(f"🔗 Active connections: {health_info['active_connections']}")
        if health_info.get('database_size'):
            logger.info(f"💾 Database size: {health_info['database_size']}")
            
        # Test session creation
        logger.info("🔄 Testing session creation...")
        from sqlalchemy import text
        async with db_manager.get_session() as session:
            result = await session.execute(
                text("SELECT 1 as test_value, NOW() as current_time")
            )
            row = result.fetchone()
            logger.info(f"✅ Session test: value={row[0]}, time={row[1]}")
        
        # Clean up
        await db_manager.close()
        logger.info("✅ SQLAlchemy connection test passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ SQLAlchemy connection test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


async def test_database_schema():
    """Test database schema information."""
    logger.info("\n" + "-" * 40)
    logger.info("Testing Database Schema")
    logger.info("-" * 40)
    
    try:
        from config.database import create_database_config_from_env
        from database.connection import DatabaseConnectionManager
        
        # For local testing, temporarily set modified DATABASE_URL
        original_db_url = os.getenv('DATABASE_URL')
        if original_db_url and '@postgres:' in original_db_url:
            modified_db_url = original_db_url.replace('@postgres:', '@localhost:')
            os.environ['DATABASE_URL'] = modified_db_url
        
        db_config = create_database_config_from_env()
        db_manager = DatabaseConnectionManager(db_config)
        
        # Restore original URL
        if original_db_url:
            os.environ['DATABASE_URL'] = original_db_url
        await db_manager.initialize()
        
        # Test schema queries
        from sqlalchemy import text
        async with db_manager.get_session() as session:
            # Check if Alembic version table exists
            result = await session.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = 'alembic_version'
                )
            """))
            has_alembic = result.scalar()
            logger.info(f"📋 Alembic version table exists: {has_alembic}")
            
            # List all tables
            result = await session.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result.fetchall()]
            
            if tables:
                logger.info(f"📋 Tables found ({len(tables)}):")
                for table in tables:
                    logger.info(f"   • {table}")
            else:
                logger.info("📋 No tables found - database is empty")
            
            # Check for application tables
            expected_tables = [
                'users', 'user_subscriptions', 'match_analyses',
                'player_stats_cache', 'payments', 'match_cache',
                'system_settings', 'analytics'
            ]
            
            missing_tables = [t for t in expected_tables if t not in tables]
            if missing_tables:
                logger.warning(f"⚠️  Missing expected tables: {', '.join(missing_tables)}")
            else:
                logger.info("✅ All expected tables are present!")
        
        await db_manager.close()
        logger.info("✅ Schema test completed!")
        return len(missing_tables) == 0
        
    except Exception as e:
        logger.error(f"❌ Schema test failed: {e}")
        return False


async def main():
    """Run all connection tests."""
    logger.info("🚀 Starting PostgreSQL connection tests...")
    
    tests_passed = 0
    total_tests = 3
    
    # Test 1: Basic connection
    if await test_basic_connection():
        tests_passed += 1
    
    # Test 2: SQLAlchemy connection
    if await test_sqlalchemy_connection():
        tests_passed += 1
    
    # Test 3: Database schema
    if await test_database_schema():
        tests_passed += 1
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Tests passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        logger.info("🎉 All tests passed! Database connection is working correctly.")
        return 0
    else:
        logger.error("❌ Some tests failed. Check the logs above for details.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("🛑 Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)