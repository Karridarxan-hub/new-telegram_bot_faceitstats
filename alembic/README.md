# Alembic Migration Environment

This directory contains the Alembic migration environment for the FACEIT Telegram Bot PostgreSQL migration.

## Structure

- `env.py` - Migration environment with async SQLAlchemy 2.0 support
- `script.py.mako` - Template for generating migration files
- `versions/` - Directory containing individual migration files

## Features

- **Async Support**: Full async/await support with SQLAlchemy 2.0
- **Environment Variables**: Automatic loading of DATABASE_URL from environment
- **Error Handling**: Comprehensive error handling and logging
- **Model Auto-Import**: Automatic discovery of all database models
- **Transaction Safety**: Proper transaction handling for migrations
- **Connection Optimization**: Migration-specific connection settings

## Usage

The migration environment is automatically configured when you run Alembic commands. The environment supports both online and offline migration modes.

### Online Mode (Default)
Uses a live database connection for migrations:
```bash
alembic upgrade head
```

### Offline Mode
Generates SQL scripts without database connection:
```bash
alembic upgrade head --sql
```

## Configuration

The environment automatically loads configuration from:
1. Environment variables (DATABASE_URL)
2. Application settings (config/settings.py)
3. Database configuration (config/database.py)

## Model Discovery

The environment automatically imports all models from `database.models` to ensure complete schema coverage during autogenerate operations.