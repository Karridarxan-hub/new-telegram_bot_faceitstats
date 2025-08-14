"""
Integration Adapters Package.

This package provides adapters and integration points between the new
PostgreSQL ORM services and the existing JSON-based bot system.

Features:
- Storage abstraction for dual JSON/PostgreSQL support
- Migration utilities for data migration
- Bot handler integration adapters
- Configuration management for runtime switching
- Data validation and consistency checks
"""

from .storage_adapter import StorageAdapter
from .migration_adapter import MigrationAdapter
from .bot_integration import BotIntegrationAdapter

__all__ = ["StorageAdapter", "MigrationAdapter", "BotIntegrationAdapter"]