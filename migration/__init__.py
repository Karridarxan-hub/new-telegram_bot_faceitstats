"""JSON to PostgreSQL Data Migration System for FACEIT Telegram Bot.

This package provides comprehensive migration utilities to transfer data from 
JSON file storage to PostgreSQL database while maintaining data integrity and relationships.

Modules:
- data_mapper: Field mapping between JSON and PostgreSQL models
- validator: Data validation and consistency checking
- utils: Migration helper functions and utilities
- migrate_data: Main migration script
- cli: Command-line interface for migration operations
"""

__version__ = "1.0.0"
__author__ = "FACEIT Telegram Bot Migration System"

from .data_mapper import DataMapper, MappingError
from .validator import DataValidator, ValidationError
from .utils import MigrationUtils, MigrationError
from .migrate_data import DataMigration
from .cli import MigrationCLI

__all__ = [
    "DataMapper", 
    "DataValidator", 
    "MigrationUtils", 
    "DataMigration",
    "MigrationCLI",
    "MappingError",
    "ValidationError", 
    "MigrationError"
]