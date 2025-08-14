# JSON to PostgreSQL Migration Procedures

This document provides step-by-step procedures for migrating FACEIT Telegram Bot data from JSON file storage to PostgreSQL database.

## Overview

The migration system safely transfers user data, subscriptions, and analytics from `data.json` to PostgreSQL while preserving all relationships and data integrity.

## Pre-Migration Checklist

### 1. System Requirements

- [ ] Python 3.8+ installed
- [ ] PostgreSQL 12+ database running
- [ ] Required Python packages installed (`pip install -r requirements.txt`)
- [ ] Database connection configured in `.env`
- [ ] Sufficient disk space (2x JSON file size minimum)
- [ ] Bot stopped or in maintenance mode

### 2. Database Preparation

```sql
-- Ensure database exists
CREATE DATABASE faceit_bot_db;

-- Run Alembic migrations to create tables
alembic upgrade head
```

### 3. Backup Current State

```bash
# Backup JSON file
cp data.json data.json.backup.$(date +%Y%m%d_%H%M%S)

# Backup database (if contains data)
pg_dump -U username -h localhost faceit_bot_db > db_backup_$(date +%Y%m%d_%H%M%S).sql
```

## Migration Procedures

### Procedure 1: Standard Migration (Recommended)

This is the recommended approach for most scenarios.

#### Step 1: Validate Data Structure

```bash
# Validate JSON file structure
python -m migration.cli validate data.json --database --report validation_report.md

# Review validation report
cat validation_report.md
```

**Expected Output:**
```
✅ JSON Structure: VALID
✅ Database State: VALID
Statistics:
• total_users: 1234
• users_with_faceit: 1100
• subscription_distribution: {'free': 1000, 'premium': 200, 'pro': 34}
```

#### Step 2: Dry Run Migration

```bash
# Perform dry run to test migration process
python -m migration.cli migrate data.json --dry-run --batch-size 100

# Review dry run results
```

**Expected Output:**
```
🧪 Dry run completed
   Would migrate: 1234 users
   Would fail: 0 users
   Validation issues: 0
✅ Ready for actual migration!
```

#### Step 3: Execute Migration

```bash
# Run full migration with backup and validation
python -m migration.cli migrate data.json --backup --truncate --batch-size 100
```

**Expected Output:**
```
✅ MIGRATION COMPLETED
📊 Statistics:
   • Total users: 1234
   • Migrated: 1234
   • Failed: 0
   • Success rate: 100.0%
   • Duration: 45.2 seconds
💾 Backup: backups/data_20241201_143022.json
```

#### Step 4: Verify Migration

```bash
# Check migration status
python -m migration.cli status

# Verify data integrity
python -c "
import asyncio
from migration import DataValidator
async def verify():
    validator = DataValidator('data.json')
    await validator.load_json_data()
    result = await validator.validate_migration_integrity({'users': []})
    print('Verification:', 'PASSED' if result.is_valid else 'FAILED')
asyncio.run(verify())
"
```

### Procedure 2: Large Dataset Migration (1000+ Users)

For large datasets, use optimized settings.

#### Step 1: Analyze Dataset

```bash
# Check file size and estimate time
ls -lh data.json
python -c "
import json
with open('data.json') as f:
    data = json.load(f)
    users = len(data.get('users', []))
    print(f'Users: {users}')
    print(f'Estimated time: {users * 0.1 / 60:.1f} minutes')
"
```

#### Step 2: Configure for Performance

```bash
# Use larger batches and more concurrency
python -m migration.cli migrate data.json \
    --batch-size 500 \
    --max-concurrent 15 \
    --truncate \
    --backup
```

#### Step 3: Monitor Progress

```bash
# In another terminal, monitor progress
tail -f migration.log

# Check memory usage
python -c "
import psutil
p = psutil.Process()
print(f'Memory: {p.memory_info().rss / 1024 / 1024:.1f} MB')
"
```

### Procedure 3: Safe Migration with Manual Verification

For critical production data, use this procedure.

#### Step 1: Multiple Validation Rounds

```bash
# Round 1: Structure validation
python -m migration.cli validate data.json --report validation_1.md

# Round 2: Database state validation  
python -m migration.cli validate data.json --database --report validation_2.md

# Round 3: Sample data validation
python -c "
import json, random
with open('data.json') as f:
    data = json.load(f)
    sample = random.sample(data.get('users', []), min(10, len(data.get('users', []))))
    print('Sample user IDs:', [u.get('user_id') for u in sample])
"
```

#### Step 2: Staged Migration

```bash
# First: Dry run with small sample
head -n 100 data.json > data_sample.json
echo '}' >> data_sample.json
python -m migration.cli migrate data_sample.json --dry-run

# Second: Real migration with small sample
python -m migration.cli migrate data_sample.json --truncate --backup

# Third: Verify sample migration
python -m migration.cli status
```

#### Step 3: Full Migration

```bash
# Full migration after successful sample
python -m migration.cli migrate data.json --truncate --backup --batch-size 200
```

### Procedure 4: Migration with Error Recovery

For scenarios where errors are expected.

#### Step 1: Enable Maximum Logging

```bash
# Enable verbose logging
python -m migration.cli migrate data.json \
    --verbose \
    --batch-size 50 \
    --max-concurrent 5 \
    --backup \
    --truncate 2>&1 | tee migration_detailed.log
```

#### Step 2: Analyze Errors

```bash
# If migration fails, analyze errors
grep "ERROR" migration_detailed.log
grep "Failed to migrate user" migration_detailed.log

# Check partial migration status
python -m migration.cli status --json | jq '.database_status'
```

#### Step 3: Recovery Actions

```bash
# Option A: Rollback and fix data
python -m migration.cli rollback --confirm

# Option B: Continue from last successful batch (if implementation supports)
# Option C: Manual data cleanup and retry
```

## Post-Migration Procedures

### 1. Verification Checklist

- [ ] User count matches between JSON and database
- [ ] All FACEIT accounts properly linked
- [ ] Subscription data preserved
- [ ] No orphaned records
- [ ] Sample users manually verified

```bash
# Verification commands
python -c "
import asyncio, json
from database.connection import get_async_session
from database.models import User, UserSubscription
from sqlalchemy import select, func

async def verify():
    with open('data.json') as f:
        json_data = json.load(f)
    json_users = len(json_data.get('users', []))
    
    async with get_async_session() as session:
        db_users = await session.scalar(select(func.count(User.id)))
        db_subs = await session.scalar(select(func.count(UserSubscription.id)))
    
    print(f'JSON users: {json_users}')
    print(f'DB users: {db_users}') 
    print(f'DB subscriptions: {db_subs}')
    print(f'Match: {json_users == db_users == db_subs}')

asyncio.run(verify())
"
```

### 2. Application Configuration Update

Update your bot configuration to use PostgreSQL:

```python
# config/settings.py
USE_POSTGRESQL = True
USE_JSON_STORAGE = False

# Update imports in main.py
from database.repositories.user import UserRepository
from services.user import UserService

# Replace DataStorage with repositories
# storage = DataStorage()  # Remove
user_service = UserService()  # Add
```

### 3. Performance Testing

```bash
# Test database performance
python -c "
import asyncio, time
from database.repositories.user import UserRepository

async def test_performance():
    repo = UserRepository()
    
    start = time.time()
    users = await repo.get_users_with_faceit_accounts(limit=100)
    end = time.time()
    
    print(f'Fetched {len(users)} users in {end-start:.3f}s')

asyncio.run(test_performance())
"
```

### 4. Cleanup

```bash
# Archive old JSON file
mkdir -p archives/$(date +%Y%m)
mv data.json archives/$(date +%Y%m)/data.json.$(date +%Y%m%d_%H%M%S)

# Update .gitignore if needed
echo "data.json.backup.*" >> .gitignore
echo "migration.log" >> .gitignore
echo "validation_report.md" >> .gitignore
```

## Rollback Procedures

### Emergency Rollback

If migration fails critically:

```bash
# Immediate rollback
python -m migration.cli rollback --confirm

# Or with specific backup
python -m migration.cli rollback --backup-path backups/data_20241201_143022.json
```

### Planned Rollback

If you need to revert after migration:

```bash
# 1. Stop the bot application
systemctl stop faceit-bot  # or your process manager

# 2. Clear database tables
python -c "
import asyncio
from migration.utils import DatabaseUtils

async def clear_db():
    tables = ['user_subscriptions', 'match_analyses', 'payments', 'users']
    for table in tables:
        await DatabaseUtils.truncate_table(table, cascade=True)
        print(f'Cleared {table}')

asyncio.run(clear_db())
"

# 3. Restore JSON file
cp data.json.backup.20241201_143022 data.json

# 4. Update configuration back to JSON
# config/settings.py: USE_POSTGRESQL = False

# 5. Restart bot with JSON storage
systemctl start faceit-bot
```

## Troubleshooting Guide

### Common Issues and Solutions

#### 1. Database Connection Errors

```bash
# Test connection manually
python -c "
import asyncio
from database.connection import get_async_session
async def test():
    try:
        async with get_async_session() as session:
            await session.execute('SELECT 1')
        print('✅ Database connection OK')
    except Exception as e:
        print(f'❌ Database connection failed: {e}')
asyncio.run(test())
"
```

**Solutions:**
- Check PostgreSQL is running: `systemctl status postgresql`
- Verify connection string in `.env`
- Check firewall/network settings
- Verify database exists and permissions

#### 2. JSON Validation Errors

```bash
# Check JSON syntax
python -m json.tool data.json > /dev/null && echo "Valid JSON" || echo "Invalid JSON"

# Find specific issues
python -c "
import json
try:
    with open('data.json') as f:
        data = json.load(f)
    print('JSON structure valid')
    users = data.get('users', [])
    print(f'Users array: {len(users)} items')
    for i, user in enumerate(users[:5]):
        required = ['user_id']
        missing = [f for f in required if f not in user]
        if missing:
            print(f'User {i}: missing {missing}')
except Exception as e:
    print(f'JSON error: {e}')
"
```

**Solutions:**
- Fix JSON syntax errors
- Ensure required fields exist
- Check datetime format consistency
- Validate user_id uniqueness

#### 3. Memory Issues

```bash
# Check memory usage during migration
python -c "
import psutil
print(f'Available memory: {psutil.virtual_memory().available / 1024 / 1024:.1f} MB')
print(f'Memory percent used: {psutil.virtual_memory().percent}%')
"
```

**Solutions:**
- Reduce batch size: `--batch-size 25`
- Reduce concurrency: `--max-concurrent 2`
- Close other applications
- Consider migration in chunks

#### 4. Migration Timeout

```bash
# Check for long-running operations
python -c "
import asyncio
from migration.utils import DatabaseUtils

async def check_locks():
    # Implementation depends on your database monitoring setup
    print('Check PostgreSQL logs for slow queries')

asyncio.run(check_locks())
"
```

**Solutions:**
- Increase database timeout settings
- Check database performance
- Reduce batch size and concurrency
- Monitor database locks

#### 5. Partial Migration Recovery

```bash
# Check what was migrated
python -m migration.cli status

# Get detailed counts
python -c "
import asyncio
from database.connection import get_async_session
from database.models import User
from sqlalchemy import select, func

async def check_partial():
    async with get_async_session() as session:
        count = await session.scalar(select(func.count(User.id)))
        print(f'Migrated users: {count}')
        
        # Get user ID range
        if count > 0:
            min_id = await session.scalar(select(func.min(User.user_id)))
            max_id = await session.scalar(select(func.max(User.user_id)))
            print(f'User ID range: {min_id} - {max_id}')

asyncio.run(check_partial())
"
```

**Recovery Options:**
1. Complete rollback and restart
2. Continue migration with remaining data
3. Manual data reconciliation

## Migration Checklist Template

Use this checklist for each migration:

```
FACEIT Bot JSON to PostgreSQL Migration Checklist

PRE-MIGRATION:
□ JSON file backup created
□ Database backup created (if applicable)
□ Bot application stopped
□ Database connection verified
□ JSON structure validated
□ Disk space sufficient (2x file size)
□ Migration plan reviewed

MIGRATION:
□ Dry run completed successfully
□ Migration parameters configured
□ Migration executed
□ No critical errors encountered
□ Migration logs reviewed

POST-MIGRATION:
□ User count verification passed
□ Sample data verification passed
□ Application configuration updated
□ Bot application restarted
□ Performance test completed
□ Old JSON file archived
□ Backup files organized

SIGN-OFF:
Date: ________________
Executed by: ________________
Verified by: ________________
```

## Best Practices

1. **Always test first**: Use dry runs and small samples
2. **Monitor progress**: Watch logs and system resources
3. **Keep backups**: Multiple backup points for recovery
4. **Validate thoroughly**: Check data integrity at each step
5. **Document everything**: Log all decisions and issues
6. **Plan for rollback**: Have recovery procedures ready
7. **Test in staging**: Use production-like environment first
8. **Communicate**: Notify users of maintenance windows
9. **Incremental approach**: Break large migrations into phases
10. **Review and learn**: Document lessons learned for next time