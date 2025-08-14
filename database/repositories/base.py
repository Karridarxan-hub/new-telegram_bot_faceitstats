"""
Base Repository implementation with common CRUD operations.

Provides abstract base class for all repositories with:
- Common CRUD operations (Create, Read, Update, Delete)
- Batch operations for performance
- Filtering, sorting, and pagination
- Transaction management
- Error handling and logging
- Redis cache integration
- Type safety with generics
"""

import logging
from abc import ABC, abstractmethod
from typing import (
    TypeVar, Generic, Optional, List, Dict, Any, Union, 
    Type, Sequence, Callable, Tuple
)
from datetime import datetime, timedelta
import uuid
from contextlib import asynccontextmanager

from sqlalchemy import select, update, delete, func, and_, or_, desc, asc, text
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, NoResultFound
from sqlalchemy.sql import Select

from database.models import Base
from database.connection import get_db_session, DatabaseOperationError
from utils.redis_cache import RedisCache, cache_player_data, cache_stats_data

logger = logging.getLogger(__name__)

# Type variables for generic repository
ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")


class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType], ABC):
    """
    Abstract base repository with common CRUD operations.
    
    Provides generic methods for database operations with:
    - Full async/await support
    - Redis caching integration
    - Error handling and logging
    - Pagination and filtering
    - Batch operations
    - Transaction management
    """
    
    def __init__(self, model: Type[ModelType], cache: Optional[RedisCache] = None):
        """
        Initialize repository with model class and optional cache.
        
        Args:
            model: SQLAlchemy model class
            cache: Optional Redis cache instance
        """
        self.model = model
        self.cache = cache
        self._table_name = model.__tablename__
    
    @asynccontextmanager
    async def get_session(self):
        """Get database session with automatic transaction management."""
        async with get_db_session() as session:
            try:
                yield session
            except Exception as e:
                await session.rollback()
                logger.error(f"Repository transaction rolled back: {e}")
                raise
    
    # Cache key generation
    def _cache_key(self, prefix: str, *args: Any) -> str:
        """Generate cache key with consistent format."""
        key_parts = [self._table_name, prefix]
        key_parts.extend(str(arg) for arg in args if arg is not None)
        return ":".join(key_parts)
    
    async def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get value from cache if available."""
        if not self.cache or not self.cache.is_connected():
            return None
        
        try:
            return await self.cache.get(key)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None
    
    async def _set_cache(self, key: str, value: Any, ttl: int = 300) -> None:
        """Set value in cache if available."""
        if not self.cache or not self.cache.is_connected():
            return
        
        try:
            await self.cache.set(key, value, ttl)
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
    
    async def _invalidate_cache(self, pattern: str) -> None:
        """Invalidate cache entries matching pattern."""
        if not self.cache or not self.cache.is_connected():
            return
        
        try:
            keys = await self.cache.get_keys_pattern(pattern)
            for key in keys:
                await self.cache.delete(key)
        except Exception as e:
            logger.warning(f"Cache invalidation error: {e}")
    
    # Basic CRUD operations
    async def get_by_id(self, id: Union[int, str, uuid.UUID]) -> Optional[ModelType]:
        """
        Get entity by ID with caching support.
        
        Args:
            id: Entity ID
            
        Returns:
            Entity instance or None if not found
        """
        cache_key = self._cache_key("id", id)
        
        # Try cache first
        cached_result = await self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            async with self.get_session() as session:
                stmt = select(self.model).where(self.model.id == id)
                result = await session.execute(stmt)
                entity = result.scalar_one_or_none()
                
                # Cache result
                if entity:
                    await self._set_cache(cache_key, entity, 300)
                
                return entity
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_by_id: {e}")
            raise DatabaseOperationError(f"Failed to get {self._table_name} by id: {e}")
    
    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[str] = None,
        order_desc: bool = False,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ModelType]:
        """
        Get all entities with filtering, sorting, and pagination.
        
        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            order_by: Column name to order by
            order_desc: Whether to order in descending order
            filters: Dictionary of field filters
            
        Returns:
            List of entities
        """
        try:
            async with self.get_session() as session:
                stmt = select(self.model)
                
                # Apply filters
                if filters:
                    conditions = []
                    for field, value in filters.items():
                        if hasattr(self.model, field):
                            column = getattr(self.model, field)
                            if isinstance(value, list):
                                conditions.append(column.in_(value))
                            elif isinstance(value, dict) and 'like' in value:
                                conditions.append(column.like(f"%{value['like']}%"))
                            elif isinstance(value, dict) and 'gte' in value:
                                conditions.append(column >= value['gte'])
                            elif isinstance(value, dict) and 'lte' in value:
                                conditions.append(column <= value['lte'])
                            else:
                                conditions.append(column == value)
                    
                    if conditions:
                        stmt = stmt.where(and_(*conditions))
                
                # Apply ordering
                if order_by and hasattr(self.model, order_by):
                    column = getattr(self.model, order_by)
                    if order_desc:
                        stmt = stmt.order_by(desc(column))
                    else:
                        stmt = stmt.order_by(asc(column))
                else:
                    # Default ordering by created_at if available
                    if hasattr(self.model, 'created_at'):
                        stmt = stmt.order_by(desc(self.model.created_at))
                
                # Apply pagination
                stmt = stmt.offset(skip).limit(limit)
                
                result = await session.execute(stmt)
                return result.scalars().all()
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_all: {e}")
            raise DatabaseOperationError(f"Failed to get all {self._table_name}: {e}")
    
    async def create(self, obj_in: CreateSchemaType) -> ModelType:
        """
        Create new entity.
        
        Args:
            obj_in: Data for creating entity
            
        Returns:
            Created entity
        """
        try:
            async with self.get_session() as session:
                # Convert input to dict if it's a Pydantic model
                if hasattr(obj_in, 'dict'):
                    create_data = obj_in.dict(exclude_unset=True)
                elif hasattr(obj_in, 'model_dump'):
                    create_data = obj_in.model_dump(exclude_unset=True)
                else:
                    create_data = obj_in
                
                # Create entity instance
                db_obj = self.model(**create_data)
                
                session.add(db_obj)
                await session.flush()  # Flush to get ID
                await session.refresh(db_obj)  # Refresh to get all fields
                
                # Invalidate related caches
                await self._invalidate_cache(f"{self._table_name}:*")
                
                logger.info(f"Created {self._table_name} with id: {db_obj.id}")
                return db_obj
                
        except IntegrityError as e:
            logger.error(f"Integrity error in create: {e}")
            raise DatabaseOperationError(f"Failed to create {self._table_name}: Duplicate or invalid data")
        except SQLAlchemyError as e:
            logger.error(f"Database error in create: {e}")
            raise DatabaseOperationError(f"Failed to create {self._table_name}: {e}")
    
    async def update(
        self, 
        id: Union[int, str, uuid.UUID], 
        obj_in: Union[UpdateSchemaType, Dict[str, Any]]
    ) -> Optional[ModelType]:
        """
        Update entity by ID.
        
        Args:
            id: Entity ID
            obj_in: Update data
            
        Returns:
            Updated entity or None if not found
        """
        try:
            async with self.get_session() as session:
                # Get existing entity
                stmt = select(self.model).where(self.model.id == id)
                result = await session.execute(stmt)
                db_obj = result.scalar_one_or_none()
                
                if not db_obj:
                    return None
                
                # Convert input to dict
                if hasattr(obj_in, 'dict'):
                    update_data = obj_in.dict(exclude_unset=True)
                elif hasattr(obj_in, 'model_dump'):
                    update_data = obj_in.model_dump(exclude_unset=True)
                else:
                    update_data = obj_in
                
                # Apply updates
                for field, value in update_data.items():
                    if hasattr(db_obj, field):
                        setattr(db_obj, field, value)
                
                # Set updated_at if available
                if hasattr(db_obj, 'updated_at'):
                    db_obj.updated_at = datetime.now()
                
                await session.flush()
                await session.refresh(db_obj)
                
                # Invalidate caches
                await self._invalidate_cache(f"{self._table_name}:*")
                
                logger.info(f"Updated {self._table_name} with id: {id}")
                return db_obj
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in update: {e}")
            raise DatabaseOperationError(f"Failed to update {self._table_name}: {e}")
    
    async def delete(self, id: Union[int, str, uuid.UUID]) -> bool:
        """
        Delete entity by ID.
        
        Args:
            id: Entity ID
            
        Returns:
            True if deleted, False if not found
        """
        try:
            async with self.get_session() as session:
                stmt = delete(self.model).where(self.model.id == id)
                result = await session.execute(stmt)
                
                deleted = result.rowcount > 0
                
                if deleted:
                    # Invalidate caches
                    await self._invalidate_cache(f"{self._table_name}:*")
                    logger.info(f"Deleted {self._table_name} with id: {id}")
                
                return deleted
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in delete: {e}")
            raise DatabaseOperationError(f"Failed to delete {self._table_name}: {e}")
    
    # Batch operations
    async def create_batch(self, objects: List[CreateSchemaType]) -> List[ModelType]:
        """
        Create multiple entities in batch.
        
        Args:
            objects: List of create data
            
        Returns:
            List of created entities
        """
        try:
            async with self.get_session() as session:
                db_objects = []
                
                for obj_in in objects:
                    if hasattr(obj_in, 'dict'):
                        create_data = obj_in.dict(exclude_unset=True)
                    elif hasattr(obj_in, 'model_dump'):
                        create_data = obj_in.model_dump(exclude_unset=True)
                    else:
                        create_data = obj_in
                    
                    db_obj = self.model(**create_data)
                    db_objects.append(db_obj)
                
                session.add_all(db_objects)
                await session.flush()
                
                # Refresh all objects
                for db_obj in db_objects:
                    await session.refresh(db_obj)
                
                # Invalidate caches
                await self._invalidate_cache(f"{self._table_name}:*")
                
                logger.info(f"Created batch of {len(db_objects)} {self._table_name} records")
                return db_objects
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in create_batch: {e}")
            raise DatabaseOperationError(f"Failed to create batch {self._table_name}: {e}")
    
    async def update_batch(
        self, 
        updates: List[Dict[str, Any]]
    ) -> int:
        """
        Update multiple entities in batch.
        
        Args:
            updates: List of update dictionaries with 'id' and update fields
            
        Returns:
            Number of updated records
        """
        try:
            async with self.get_session() as session:
                updated_count = 0
                
                for update_data in updates:
                    if 'id' not in update_data:
                        continue
                    
                    entity_id = update_data.pop('id')
                    
                    # Set updated_at if available
                    if hasattr(self.model, 'updated_at'):
                        update_data['updated_at'] = datetime.now()
                    
                    stmt = (
                        update(self.model)
                        .where(self.model.id == entity_id)
                        .values(**update_data)
                    )
                    
                    result = await session.execute(stmt)
                    updated_count += result.rowcount
                
                # Invalidate caches
                await self._invalidate_cache(f"{self._table_name}:*")
                
                logger.info(f"Updated batch of {updated_count} {self._table_name} records")
                return updated_count
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in update_batch: {e}")
            raise DatabaseOperationError(f"Failed to update batch {self._table_name}: {e}")
    
    async def delete_batch(self, ids: List[Union[int, str, uuid.UUID]]) -> int:
        """
        Delete multiple entities in batch.
        
        Args:
            ids: List of entity IDs
            
        Returns:
            Number of deleted records
        """
        try:
            async with self.get_session() as session:
                stmt = delete(self.model).where(self.model.id.in_(ids))
                result = await session.execute(stmt)
                
                deleted_count = result.rowcount
                
                if deleted_count > 0:
                    # Invalidate caches
                    await self._invalidate_cache(f"{self._table_name}:*")
                    logger.info(f"Deleted batch of {deleted_count} {self._table_name} records")
                
                return deleted_count
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in delete_batch: {e}")
            raise DatabaseOperationError(f"Failed to delete batch {self._table_name}: {e}")
    
    # Query helpers
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count entities with optional filters.
        
        Args:
            filters: Dictionary of field filters
            
        Returns:
            Number of matching entities
        """
        try:
            async with self.get_session() as session:
                stmt = select(func.count(self.model.id))
                
                # Apply filters
                if filters:
                    conditions = []
                    for field, value in filters.items():
                        if hasattr(self.model, field):
                            column = getattr(self.model, field)
                            if isinstance(value, list):
                                conditions.append(column.in_(value))
                            else:
                                conditions.append(column == value)
                    
                    if conditions:
                        stmt = stmt.where(and_(*conditions))
                
                result = await session.execute(stmt)
                return result.scalar() or 0
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in count: {e}")
            raise DatabaseOperationError(f"Failed to count {self._table_name}: {e}")
    
    async def exists(self, id: Union[int, str, uuid.UUID]) -> bool:
        """
        Check if entity exists by ID.
        
        Args:
            id: Entity ID
            
        Returns:
            True if entity exists
        """
        try:
            async with self.get_session() as session:
                stmt = select(self.model.id).where(self.model.id == id)
                result = await session.execute(stmt)
                return result.scalar_one_or_none() is not None
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in exists: {e}")
            return False
    
    # Advanced queries
    async def find_one(
        self, 
        filters: Dict[str, Any],
        order_by: Optional[str] = None,
        order_desc: bool = False
    ) -> Optional[ModelType]:
        """
        Find single entity by filters.
        
        Args:
            filters: Dictionary of field filters
            order_by: Optional ordering column
            order_desc: Whether to order in descending order
            
        Returns:
            First matching entity or None
        """
        results = await self.get_all(
            skip=0, 
            limit=1, 
            order_by=order_by,
            order_desc=order_desc,
            filters=filters
        )
        return results[0] if results else None
    
    async def find_by_field(
        self, 
        field: str, 
        value: Any,
        limit: int = 100
    ) -> List[ModelType]:
        """
        Find entities by single field value.
        
        Args:
            field: Field name
            value: Field value
            limit: Maximum results to return
            
        Returns:
            List of matching entities
        """
        return await self.get_all(
            limit=limit,
            filters={field: value}
        )
    
    # Relationship loading
    async def get_with_relationships(
        self, 
        id: Union[int, str, uuid.UUID],
        relationships: List[str]
    ) -> Optional[ModelType]:
        """
        Get entity with eager-loaded relationships.
        
        Args:
            id: Entity ID
            relationships: List of relationship names to load
            
        Returns:
            Entity with loaded relationships or None
        """
        try:
            async with self.get_session() as session:
                stmt = select(self.model).where(self.model.id == id)
                
                # Add relationship loading
                for rel_name in relationships:
                    if hasattr(self.model, rel_name):
                        rel_attr = getattr(self.model, rel_name)
                        # Use selectinload for collections, joinedload for single relations
                        if hasattr(rel_attr.property, 'collection_class'):
                            stmt = stmt.options(selectinload(rel_attr))
                        else:
                            stmt = stmt.options(joinedload(rel_attr))
                
                result = await session.execute(stmt)
                return result.unique().scalar_one_or_none()
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_with_relationships: {e}")
            raise DatabaseOperationError(f"Failed to get {self._table_name} with relationships: {e}")
    
    # Analytics and statistics
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get repository statistics.
        
        Returns:
            Dictionary with statistics
        """
        try:
            async with self.get_session() as session:
                total_count = await self.count()
                
                stats = {
                    "total_records": total_count,
                    "table_name": self._table_name,
                }
                
                # Add time-based stats if created_at exists
                if hasattr(self.model, 'created_at'):
                    # Records created in last 24 hours
                    yesterday = datetime.now() - timedelta(days=1)
                    recent_count = await self.count(
                        filters={'created_at': {'gte': yesterday}}
                    )
                    stats["recent_records"] = recent_count
                
                return stats
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_stats: {e}")
            return {"error": str(e)}