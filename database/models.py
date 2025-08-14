"""SQLAlchemy database models for FACEIT Telegram Bot.

This module contains all database models using SQLAlchemy 2.0 async patterns.
Designed to migrate from JSON-based storage to PostgreSQL.
"""

import uuid
from datetime import datetime, timedelta
from enum import Enum as PyEnum
from typing import Optional, Dict, Any, List

from sqlalchemy import (
    String, Integer, Boolean, DateTime, Float, Text, JSON,
    ForeignKey, Enum, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship
)
from sqlalchemy.sql import func


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models."""
    pass


class SubscriptionTier(PyEnum):
    """Subscription tier enumeration."""
    FREE = "free"
    PREMIUM = "premium"
    PRO = "pro"


class MatchStatus(PyEnum):
    """Match status enumeration."""
    SCHEDULED = "scheduled"
    CONFIGURING = "configuring"
    READY = "ready"
    ONGOING = "ongoing"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class PaymentStatus(PyEnum):
    """Payment status enumeration."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class User(Base):
    """User model - migrated from UserData JSON structure."""
    
    __tablename__ = "users"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Core user data
    user_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    faceit_player_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    faceit_nickname: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    last_checked_match_id: Mapped[Optional[str]] = mapped_column(String(255))
    waiting_for_nickname: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # User preferences
    language: Mapped[str] = mapped_column(String(10), default="ru")
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Analytics and tracking
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    subscription: Mapped["UserSubscription"] = relationship(
        "UserSubscription",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )
    match_analyses: Mapped[List["MatchAnalysis"]] = relationship(
        "MatchAnalysis",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    player_stats_cache: Mapped[List["PlayerStatsCache"]] = relationship(
        "PlayerStatsCache",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    payments: Mapped[List["Payment"]] = relationship(
        "Payment",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, nickname='{self.faceit_nickname}')>"


class UserSubscription(Base):
    """User subscription model - migrated from UserSubscription JSON structure."""
    
    __tablename__ = "user_subscriptions"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Foreign key to user
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True
    )
    
    # Subscription details
    tier: Mapped[SubscriptionTier] = mapped_column(
        Enum(SubscriptionTier), 
        default=SubscriptionTier.FREE
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_method: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Usage tracking
    daily_requests: Mapped[int] = mapped_column(Integer, default=0)
    last_reset_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Referral system
    referred_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    referral_code: Mapped[Optional[str]] = mapped_column(String(20), unique=True, index=True)
    referrals_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="subscription")
    
    def __repr__(self) -> str:
        return f"<UserSubscription(tier={self.tier.value}, expires_at={self.expires_at})>"


class MatchAnalysis(Base):
    """Match analysis history model - stores analyzed matches data."""
    
    __tablename__ = "match_analyses"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Foreign key to user who requested the analysis
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE")
    )
    
    # Match identification
    match_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    match_url: Mapped[Optional[str]] = mapped_column(Text)
    
    # Match basic info
    game: Mapped[Optional[str]] = mapped_column(String(50), default="cs2")
    region: Mapped[Optional[str]] = mapped_column(String(50))
    map_name: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[MatchStatus] = mapped_column(Enum(MatchStatus), default=MatchStatus.SCHEDULED)
    
    # Match details
    competition_name: Mapped[Optional[str]] = mapped_column(String(255))
    competition_type: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Analysis results (stored as JSON for flexibility)
    team1_analysis: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    team2_analysis: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    match_prediction: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Analysis metadata
    analysis_version: Mapped[str] = mapped_column(String(20), default="1.0")
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    cached_data_used: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Match timing
    configured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="match_analyses")
    
    # Indexes
    __table_args__ = (
        Index("idx_match_analyses_user_created", "user_id", "created_at"),
        Index("idx_match_analyses_match_status", "match_id", "status"),
        Index("idx_match_analyses_game_region", "game", "region"),
    )
    
    def __repr__(self) -> str:
        return f"<MatchAnalysis(match_id='{self.match_id}', status={self.status.value})>"


class PlayerStatsCache(Base):
    """Player statistics cache model - optimizes API calls."""
    
    __tablename__ = "player_stats_cache"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Foreign key to user (optional - can cache for any user)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE")
    )
    
    # Player identification
    player_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    nickname: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Game context
    game: Mapped[str] = mapped_column(String(50), default="cs2")
    
    # Player basic info
    avatar: Mapped[Optional[str]] = mapped_column(Text)
    country: Mapped[Optional[str]] = mapped_column(String(10))
    skill_level: Mapped[Optional[int]] = mapped_column(Integer)
    faceit_elo: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Recent performance metrics (calculated from recent matches)
    winrate: Mapped[Optional[float]] = mapped_column(Float)
    avg_kd: Mapped[Optional[float]] = mapped_column(Float)
    avg_adr: Mapped[Optional[float]] = mapped_column(Float)
    hltv_rating: Mapped[Optional[float]] = mapped_column(Float)
    
    # Analysis data (JSON for flexibility)
    recent_form: Mapped[Optional[str]] = mapped_column(String(50))  # "WWLWW" format
    danger_level: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5 scale
    player_role: Mapped[Optional[str]] = mapped_column(String(50))  # AWPer, Rifler, etc.
    
    # Detailed stats (stored as JSON)
    match_history_stats: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    map_performance: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    weapon_preferences: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    clutch_stats: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Cache management
    cache_version: Mapped[str] = mapped_column(String(20), default="1.0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="player_stats_cache")
    
    # Indexes and constraints
    __table_args__ = (
        Index("idx_player_stats_cache_player_game", "player_id", "game"),
        Index("idx_player_stats_cache_nickname_game", "nickname", "game"),
        Index("idx_player_stats_cache_expires_at", "expires_at"),
        UniqueConstraint("player_id", "game", name="uq_player_stats_cache_player_game"),
    )
    
    def __repr__(self) -> str:
        return f"<PlayerStatsCache(nickname='{self.nickname}', game='{self.game}', expires_at={self.expires_at})>"


class Payment(Base):
    """Payment history model - tracks subscription payments."""
    
    __tablename__ = "payments"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Foreign key to user
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE")
    )
    
    # Payment identification
    telegram_payment_charge_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    provider_payment_charge_id: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Payment details
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # Amount in Telegram Stars
    currency: Mapped[str] = mapped_column(String(10), default="XTR")  # Telegram Stars
    description: Mapped[str] = mapped_column(Text)
    
    # Subscription details
    subscription_tier: Mapped[SubscriptionTier] = mapped_column(Enum(SubscriptionTier))
    subscription_duration: Mapped[str] = mapped_column(String(20))  # monthly, yearly
    duration_days: Mapped[int] = mapped_column(Integer)
    
    # Payment status
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    payment_method: Mapped[str] = mapped_column(String(100), default="telegram_stars")
    
    # Telegram payment payload
    payment_payload: Mapped[Optional[str]] = mapped_column(Text)
    
    # Additional metadata
    invoice_title: Mapped[Optional[str]] = mapped_column(String(255))
    invoice_description: Mapped[Optional[str]] = mapped_column(Text)
    
    # Processing details
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="payments")
    
    # Indexes
    __table_args__ = (
        Index("idx_payments_user_created", "user_id", "created_at"),
        Index("idx_payments_status_created", "status", "created_at"),
        Index("idx_payments_tier_duration", "subscription_tier", "subscription_duration"),
        CheckConstraint("amount > 0", name="chk_payments_amount_positive"),
    )
    
    def __repr__(self) -> str:
        return f"<Payment(amount={self.amount}, status={self.status.value}, tier={self.subscription_tier.value})>"


class MatchCache(Base):
    """Match cache model - stores frequently accessed match data."""
    
    __tablename__ = "match_cache"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Match identification
    match_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    
    # Match details (stored as JSON for API compatibility)
    match_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    match_stats: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Cache metadata
    cache_version: Mapped[str] = mapped_column(String(20), default="1.0")
    data_source: Mapped[str] = mapped_column(String(50), default="faceit_api")
    
    # Cache management
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Indexes
    __table_args__ = (
        Index("idx_match_cache_expires_at", "expires_at"),
        Index("idx_match_cache_access_count", "access_count"),
    )
    
    def __repr__(self) -> str:
        return f"<MatchCache(match_id='{self.match_id}', expires_at={self.expires_at})>"


class SystemSettings(Base):
    """System settings model - stores bot configuration."""
    
    __tablename__ = "system_settings"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Setting identification
    key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    value: Mapped[Optional[str]] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(String(50), default="string")  # string, int, float, bool, json
    
    # Setting metadata
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100), default="general")
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Validation (JSON schema or regex pattern)
    validation_rule: Mapped[Optional[str]] = mapped_column(Text)
    default_value: Mapped[Optional[str]] = mapped_column(Text)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Indexes
    __table_args__ = (
        Index("idx_system_settings_category", "category"),
        Index("idx_system_settings_public", "is_public"),
    )
    
    def __repr__(self) -> str:
        return f"<SystemSettings(key='{self.key}', category='{self.category}')>"


class Analytics(Base):
    """Analytics model - stores usage statistics and metrics."""
    
    __tablename__ = "analytics"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Metric identification
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    metric_type: Mapped[str] = mapped_column(String(50), default="counter")  # counter, gauge, histogram
    
    # Metric value
    value: Mapped[float] = mapped_column(Float, nullable=False)
    tags: Mapped[Optional[Dict[str, str]]] = mapped_column(JSON)  # Additional metadata
    
    # Time-based data
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(20), default="daily")  # daily, hourly, monthly
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Indexes
    __table_args__ = (
        Index("idx_analytics_metric_timestamp", "metric_name", "timestamp"),
        Index("idx_analytics_period_timestamp", "period", "timestamp"),
        Index("idx_analytics_type_timestamp", "metric_type", "timestamp"),
    )
    
    def __repr__(self) -> str:
        return f"<Analytics(metric='{self.metric_name}', value={self.value}, timestamp={self.timestamp})>"


# Migration helper functions for JSON to PostgreSQL migration
class MigrationHelper:
    """Helper class for migrating from JSON storage to PostgreSQL."""
    
    @staticmethod
    def convert_user_data_from_json(json_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert UserData JSON to User model data."""
        user_data = {
            'user_id': json_data['user_id'],
            'faceit_player_id': json_data.get('faceit_player_id'),
            'faceit_nickname': json_data.get('faceit_nickname'),
            'last_checked_match_id': json_data.get('last_checked_match_id'),
            'waiting_for_nickname': json_data.get('waiting_for_nickname', False),
            'language': json_data.get('language', 'ru'),
            'notifications_enabled': json_data.get('notifications_enabled', True),
            'total_requests': json_data.get('total_requests', 0),
            'created_at': datetime.fromisoformat(json_data['created_at']) if json_data.get('created_at') else datetime.now(),
            'last_active_at': datetime.fromisoformat(json_data['last_active_at']) if json_data.get('last_active_at') else None,
        }
        
        return user_data
    
    @staticmethod
    def convert_subscription_from_json(json_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert UserSubscription JSON to UserSubscription model data."""
        subscription_data = json_data.get('subscription', {})
        
        return {
            'tier': SubscriptionTier(subscription_data.get('tier', 'free')),
            'expires_at': datetime.fromisoformat(subscription_data['expires_at']) if subscription_data.get('expires_at') else None,
            'auto_renew': subscription_data.get('auto_renew', False),
            'payment_method': subscription_data.get('payment_method'),
            'daily_requests': subscription_data.get('daily_requests', 0),
            'last_reset_date': datetime.fromisoformat(subscription_data['last_reset_date']) if subscription_data.get('last_reset_date') else None,
            'referred_by_user_id': subscription_data.get('referred_by'),
            'referral_code': subscription_data.get('referral_code'),
            'referrals_count': subscription_data.get('referrals_count', 0),
        }