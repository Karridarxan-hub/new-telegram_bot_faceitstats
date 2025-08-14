# JSON to PostgreSQL Data Migration System

This comprehensive migration system transfers data from JSON file storage to PostgreSQL database while maintaining data integrity, relationships, and providing robust error handling and rollback capabilities.

## Features

- **Complete Data Mapping**: Converts JSON user data and subscriptions to PostgreSQL models
- **Batch Processing**: Efficient processing of large datasets with configurable batch sizes
- **Progress Tracking**: Real-time progress reporting during migration
- **Data Validation**: Pre and post-migration validation to ensure data integrity
- **Backup & Rollback**: Automatic backup creation and rollback capabilities
- **Error Handling**: Comprehensive error handling with detailed logging
- **Concurrent Processing**: Parallel processing with semaphore limiting
- **CLI Interface**: Interactive command-line interface for all operations
- **Migration Logging**: Database logging of all migration operations

## Architecture

### Core Components

1. **DataMapper** (`data_mapper.py`): Handles JSON to PostgreSQL field mapping
2. **DataValidator** (`validator.py`): Validates data consistency and integrity
3. **MigrationUtils** (`utils.py`): Helper functions and utility classes
4. **DataMigration** (`migrate_data.py`): Main migration orchestration
5. **MigrationCLI** (`cli.py`): Command-line interface

### Data Flow

```
JSON File → Validation → Mapping → Batch Processing → PostgreSQL
    ↓           ↓           ↓            ↓              ↓
  Backup    Structure   Field Map   Parallel      Database
 Creation   Checking    Conversion  Processing    Insertion
```

## Installation

The migration system is part of the FACEIT Telegram Bot project. Ensure you have:

1. Python 3.8+
2. PostgreSQL database configured
3. Required dependencies installed:

```bash
pip install -r requirements.txt
```

## Quick Start

### 1. Validate Your Data

Before migrating, validate your JSON data structure:

```bash
python -m migration.cli validate data.json
```

### 2. Dry Run Migration

Test the migration without affecting the database:

```bash
python -m migration.cli migrate data.json --dry-run
```

### 3. Full Migration

Perform the actual migration with backup:

```bash
python -m migration.cli migrate data.json --backup --truncate
```

## Command-Line Interface

### Available Commands

#### `migrate` - Run Data Migration

```bash
python -m migration.cli migrate <json_file> [options]
```

**Options:**
- `--batch-size N`: Batch size for processing (default: 100)
- `--max-concurrent N`: Maximum concurrent operations (default: 5)
- `--dry-run`: Perform dry run without actual data insertion
- `--no-backup`: Skip creating backup before migration
- `--truncate`: Truncate target tables before migration
- `--force`: Force migration even if validation fails

**Example:**
```bash
python -m migration.cli migrate data.json --batch-size 50 --max-concurrent 10 --truncate
```

#### `validate` - Validate Data Structure

```bash
python -m migration.cli validate <json_file> [options]
```

**Options:**
- `--database`: Also validate database state
- `--report <path>`: Save validation report to file

**Example:**
```bash
python -m migration.cli validate data.json --database --report validation_report.md
```

#### `status` - Show Migration Status

```bash
python -m migration.cli status [options]
```

**Options:**
- `--json`: Output in JSON format

#### `rollback` - Rollback Migration

```bash
python -m migration.cli rollback [options]
```

**Options:**
- `--backup-path <path>`: Path to backup file for restoration
- `--confirm`: Confirm rollback without interactive prompt

#### `backup` - Create Backup

```bash
python -m migration.cli backup <json_file> [options]
```

**Options:**
- `--output-dir <dir>`: Output directory for backup (default: backups)

### Global Options

- `--verbose, -v`: Enable verbose logging
- `--quiet, -q`: Enable quiet mode (warnings and errors only)
- `--config <path>`: Path to configuration file

## Programming Interface

### Basic Usage

```python
import asyncio
from migration import DataMigration

async def migrate_data():
    migration = DataMigration(
        json_file_path="data.json",
        batch_size=100,
        max_concurrent=5
    )
    
    result = await migration.migrate(
        truncate_tables=True,
        dry_run=False
    )
    
    if result.success:
        print(f"Migration completed: {result.migrated_users} users")
    else:
        print(f"Migration failed: {result.errors}")

# Run migration
asyncio.run(migrate_data())
```

### Advanced Usage with Validation

```python
import asyncio
from migration import DataValidator, DataMigration

async def advanced_migration():
    # Validate data first
    validator = DataValidator("data.json")
    await validator.load_json_data()
    validation_result = validator.validate_json_structure()
    
    if not validation_result.is_valid:
        print("Validation failed:", validation_result.errors)
        return
    
    # Perform migration
    migration = DataMigration(
        json_file_path="data.json",
        batch_size=200,
        max_concurrent=10,
        validate_before=True,
        validate_after=True
    )
    
    result = await migration.migrate(truncate_tables=True)
    
    # Check results
    summary = result.get_summary()
    print(f"Migration summary: {summary}")

asyncio.run(advanced_migration())
```

## Data Mapping

### JSON to PostgreSQL Field Mapping

#### User Data

| JSON Field | PostgreSQL Field | Type | Notes |
|------------|------------------|------|-------|
| `user_id` | `user_id` | `int` | Telegram user ID |
| `faceit_player_id` | `faceit_player_id` | `str` | FACEIT player UUID |
| `faceit_nickname` | `faceit_nickname` | `str` | FACEIT username |
| `language` | `language` | `str` | User language preference |
| `created_at` | `created_at` | `datetime` | Account creation time |

#### Subscription Data

| JSON Field | PostgreSQL Field | Type | Notes |
|------------|------------------|------|-------|
| `tier` | `tier` | `enum` | FREE, PREMIUM, PRO |
| `expires_at` | `expires_at` | `datetime` | Subscription expiry |
| `daily_requests` | `daily_requests` | `int` | Daily API request count |
| `referred_by` | `referred_by_user_id` | `int` | Referrer user ID |

## Configuration

### Environment Variables

Set these in your `.env` file:

```bash
# Database connection
DATABASE_URL=postgresql://user:pass@localhost/dbname

# Migration settings
MIGRATION_BATCH_SIZE=100
MIGRATION_MAX_CONCURRENT=5
MIGRATION_BACKUP_DIR=backups
```

### Migration Settings

Configure in `config/settings.py`:

```python
class MigrationSettings:
    batch_size: int = 100
    max_concurrent: int = 5
    backup_enabled: bool = True
    validation_enabled: bool = True
```

## Error Handling

The migration system provides comprehensive error handling:

### Error Types

1. **MappingError**: Data field mapping failures
2. **ValidationError**: Data structure validation failures  
3. **MigrationError**: General migration operation failures
4. **DatabaseOperationError**: Database connection/query failures

### Error Recovery

- **Backup Restoration**: Automatic backup creation before migration
- **Transaction Rollback**: Database transactions for atomic operations
- **Partial Migration Recovery**: Continue from last successful batch
- **Detailed Error Logging**: Complete error logs with context

### Example Error Handling

```python
try:
    result = await migration.migrate()
    if not result.success:
        print("Migration failed with errors:")
        for error in result.errors:
            print(f"- {error}")
        
        # Rollback if needed
        await migration.rollback_migration(result.backup_path)
        
except MigrationError as e:
    logger.error(f"Migration system error: {e}")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
```

## Performance Considerations

### Optimization Settings

- **Batch Size**: Larger batches (200-500) for better throughput
- **Concurrency**: Limit concurrent operations to avoid database overload
- **Memory Usage**: Monitor memory usage for large datasets
- **Connection Pooling**: Use connection pooling for better performance

### Recommended Settings by Dataset Size

| Dataset Size | Batch Size | Max Concurrent | Expected Time |
|--------------|------------|----------------|---------------|
| < 1,000 users | 100 | 5 | < 1 minute |
| 1,000-10,000 | 200 | 10 | 1-5 minutes |
| 10,000-100,000 | 500 | 15 | 5-30 minutes |
| > 100,000 | 1000 | 20 | 30+ minutes |

## Troubleshooting

### Common Issues

1. **Database Connection Failures**
   ```bash
   # Check database connectivity
   python -m migration.cli status
   ```

2. **JSON Validation Errors**
   ```bash
   # Validate JSON structure
   python -m migration.cli validate data.json --report issues.md
   ```

3. **Memory Issues with Large Datasets**
   ```bash
   # Use smaller batch sizes
   python -m migration.cli migrate data.json --batch-size 50
   ```

4. **Migration Interruption**
   ```bash
   # Check status and rollback if needed
   python -m migration.cli status
   python -m migration.cli rollback --confirm
   ```

### Debugging

Enable verbose logging:

```bash
python -m migration.cli migrate data.json --verbose
```

Check migration logs:

```bash
tail -f migration.log
```

## Testing

### Unit Tests

Run unit tests for individual components:

```bash
python -m pytest migration/tests/
```

### Integration Tests

Test the complete migration flow:

```bash
python -m pytest migration/tests/test_integration.py
```

### Performance Tests

Benchmark migration performance:

```bash
python migration/tests/performance_test.py
```

## Contributing

When contributing to the migration system:

1. Follow the existing code structure
2. Add comprehensive error handling
3. Include unit tests for new features
4. Update documentation for API changes
5. Test with various dataset sizes

## License

This migration system is part of the FACEIT Telegram Bot project and follows the same licensing terms.

## Support

For issues or questions:

1. Check the troubleshooting section
2. Review migration logs
3. Create an issue with detailed error information
4. Include your dataset size and system specifications