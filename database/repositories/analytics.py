"""
Analytics Repository implementation for usage metrics and statistics.

Provides analytics and metrics functionality including:
- Usage metrics tracking and aggregation
- Performance statistics and monitoring
- User behavior analytics
- System health metrics
- Revenue and business analytics
- Real-time dashboards and reporting
"""

import logging
from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime, timedelta
from enum import Enum
import uuid

from sqlalchemy import select, and_, func, desc, asc, text, distinct, case
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from database.models import (
    Analytics, User, UserSubscription, MatchAnalysis, Payment,
    SubscriptionTier, MatchStatus, PaymentStatus
)
from database.connection import DatabaseOperationError
from utils.redis_cache import stats_cache
from .base import BaseRepository

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """Metric type enumeration."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    RATE = "rate"


class AnalyticsCreateData:
    """Data class for creating analytics entries."""
    def __init__(
        self,
        metric_name: str,
        value: float,
        metric_type: str = MetricType.COUNTER,
        tags: Optional[Dict[str, str]] = None,
        timestamp: Optional[datetime] = None,
        period: str = "daily"
    ):
        self.metric_name = metric_name
        self.value = value
        self.metric_type = metric_type
        self.tags = tags or {}
        self.timestamp = timestamp or datetime.now()
        self.period = period


class AnalyticsRepository(BaseRepository[Analytics, AnalyticsCreateData, Dict]):
    """
    Repository for Analytics entity management.
    
    Provides comprehensive analytics functionality with:
    - Metrics collection and aggregation
    - Performance monitoring and alerting
    - User behavior analytics
    - Business intelligence and reporting
    - Real-time dashboard data
    - System health monitoring
    """
    
    def __init__(self):
        """Initialize analytics repository with Redis cache."""
        super().__init__(Analytics, stats_cache)
    
    # Core metrics operations
    async def record_metric(
        self,
        metric_name: str,
        value: float,
        metric_type: str = MetricType.COUNTER,
        tags: Optional[Dict[str, str]] = None,
        timestamp: Optional[datetime] = None
    ) -> Analytics:
        """
        Record a metric value.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            metric_type: Type of metric
            tags: Optional tags for filtering
            timestamp: Optional timestamp (defaults to now)
            
        Returns:
            Created analytics entry
        """
        try:
            async with self.get_session() as session:
                analytics = Analytics(
                    metric_name=metric_name,
                    value=value,
                    metric_type=metric_type,
                    tags=tags or {},
                    timestamp=timestamp or datetime.now(),
                    created_at=datetime.now()
                )
                
                session.add(analytics)
                await session.flush()
                await session.refresh(analytics)
                
                logger.debug(f"Recorded metric {metric_name}={value}")
                return analytics
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in record_metric: {e}")
            raise DatabaseOperationError(f"Failed to record metric: {e}")
    
    async def record_batch_metrics(
        self,
        metrics: List[Dict[str, Any]]
    ) -> List[Analytics]:
        """
        Record multiple metrics in batch.
        
        Args:
            metrics: List of metric dictionaries
            
        Returns:
            List of created analytics entries
        """
        try:
            async with self.get_session() as session:
                analytics_entries = []
                
                for metric in metrics:
                    analytics = Analytics(
                        metric_name=metric['name'],
                        value=metric['value'],
                        metric_type=metric.get('type', MetricType.COUNTER),
                        tags=metric.get('tags', {}),
                        timestamp=metric.get('timestamp', datetime.now()),
                        created_at=datetime.now()
                    )
                    analytics_entries.append(analytics)
                
                session.add_all(analytics_entries)
                await session.flush()
                
                logger.info(f"Recorded batch of {len(analytics_entries)} metrics")
                return analytics_entries
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in record_batch_metrics: {e}")
            raise DatabaseOperationError(f"Failed to record batch metrics: {e}")
    
    # Usage analytics
    async def get_user_activity_metrics(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "daily"
    ) -> Dict[str, Any]:
        """
        Get user activity metrics over time period.
        
        Args:
            start_date: Start of analysis period
            end_date: End of analysis period
            granularity: Time granularity (hourly, daily, weekly)
            
        Returns:
            Dictionary with user activity metrics
        """
        try:
            async with self.get_session() as session:
                # Active users over time
                if granularity == "hourly":
                    date_trunc = "hour"
                elif granularity == "weekly":
                    date_trunc = "week"
                else:  # daily
                    date_trunc = "day"
                
                active_users_stmt = (
                    select(
                        func.date_trunc(date_trunc, User.last_active_at).label('period'),
                        func.count(distinct(User.id)).label('active_users')
                    )
                    .where(
                        and_(
                            User.last_active_at >= start_date,
                            User.last_active_at <= end_date
                        )
                    )
                    .group_by('period')
                    .order_by('period')
                )
                
                active_users_result = await session.execute(active_users_stmt)
                active_users_data = [
                    {
                        "period": row.period.isoformat(),
                        "active_users": row.active_users
                    }
                    for row in active_users_result
                ]
                
                # New users over time
                new_users_stmt = (
                    select(
                        func.date_trunc(date_trunc, User.created_at).label('period'),
                        func.count(User.id).label('new_users')
                    )
                    .where(
                        and_(
                            User.created_at >= start_date,
                            User.created_at <= end_date
                        )
                    )
                    .group_by('period')
                    .order_by('period')
                )
                
                new_users_result = await session.execute(new_users_stmt)
                new_users_data = [
                    {
                        "period": row.period.isoformat(),
                        "new_users": row.new_users
                    }
                    for row in new_users_result
                ]
                
                # Request volume over time
                requests_stmt = (
                    select(
                        func.date_trunc(date_trunc, MatchAnalysis.created_at).label('period'),
                        func.count(MatchAnalysis.id).label('requests')
                    )
                    .where(
                        and_(
                            MatchAnalysis.created_at >= start_date,
                            MatchAnalysis.created_at <= end_date
                        )
                    )
                    .group_by('period')
                    .order_by('period')
                )
                
                requests_result = await session.execute(requests_stmt)
                requests_data = [
                    {
                        "period": row.period.isoformat(),
                        "requests": row.requests
                    }
                    for row in requests_result
                ]
                
                return {
                    "active_users": active_users_data,
                    "new_users": new_users_data,
                    "requests": requests_data,
                    "granularity": granularity,
                    "period": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat()
                    }
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_user_activity_metrics: {e}")
            return {"error": str(e)}
    
    async def get_user_engagement_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive user engagement statistics.
        
        Returns:
            Dictionary with engagement statistics
        """
        try:
            async with self.get_session() as session:
                # User retention (users active in last 7 days vs last 30 days)
                week_ago = datetime.now() - timedelta(days=7)
                month_ago = datetime.now() - timedelta(days=30)
                
                weekly_active_stmt = select(func.count(distinct(User.id))).where(
                    User.last_active_at >= week_ago
                )
                weekly_active_result = await session.execute(weekly_active_stmt)
                weekly_active = weekly_active_result.scalar() or 0
                
                monthly_active_stmt = select(func.count(distinct(User.id))).where(
                    User.last_active_at >= month_ago
                )
                monthly_active_result = await session.execute(monthly_active_stmt)
                monthly_active = monthly_active_result.scalar() or 0
                
                # Average requests per user
                avg_requests_stmt = select(func.avg(User.total_requests))
                avg_requests_result = await session.execute(avg_requests_stmt)
                avg_requests = avg_requests_result.scalar() or 0
                
                # User lifecycle distribution
                lifecycle_stmt = (
                    select(
                        case(
                            (User.total_requests == 0, 'inactive'),
                            (User.total_requests <= 5, 'new'),
                            (User.total_requests <= 20, 'engaged'),
                            (User.total_requests <= 100, 'active'),
                            else_='power_user'
                        ).label('lifecycle_stage'),
                        func.count(User.id).label('count')
                    )
                    .group_by('lifecycle_stage')
                )
                
                lifecycle_result = await session.execute(lifecycle_stmt)
                lifecycle_distribution = {
                    row.lifecycle_stage: row.count for row in lifecycle_result
                }
                
                # FACEIT integration rate
                total_users_stmt = select(func.count(User.id))
                total_users_result = await session.execute(total_users_stmt)
                total_users = total_users_result.scalar() or 0
                
                linked_users_stmt = select(func.count(User.id)).where(
                    User.faceit_player_id.is_not(None)
                )
                linked_users_result = await session.execute(linked_users_stmt)
                linked_users = linked_users_result.scalar() or 0
                
                return {
                    "active_users": {
                        "weekly": weekly_active,
                        "monthly": monthly_active,
                        "retention_rate": round((weekly_active / monthly_active * 100) if monthly_active > 0 else 0, 2)
                    },
                    "engagement": {
                        "average_requests_per_user": round(avg_requests, 2),
                        "lifecycle_distribution": lifecycle_distribution
                    },
                    "integration": {
                        "total_users": total_users,
                        "linked_users": linked_users,
                        "link_rate": round((linked_users / total_users * 100) if total_users > 0 else 0, 2)
                    }
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_user_engagement_stats: {e}")
            return {"error": str(e)}
    
    # Performance analytics
    async def get_performance_metrics(
        self,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get system performance metrics.
        
        Args:
            hours: Number of hours to analyze
            
        Returns:
            Dictionary with performance metrics
        """
        try:
            since_time = datetime.now() - timedelta(hours=hours)
            
            async with self.get_session() as session:
                # Analysis processing times
                processing_times_stmt = (
                    select(
                        func.avg(MatchAnalysis.processing_time_ms).label('avg_time'),
                        func.percentile_cont(0.5).within_group(MatchAnalysis.processing_time_ms).label('median_time'),
                        func.percentile_cont(0.95).within_group(MatchAnalysis.processing_time_ms).label('p95_time'),
                        func.max(MatchAnalysis.processing_time_ms).label('max_time')
                    )
                    .where(
                        and_(
                            MatchAnalysis.created_at >= since_time,
                            MatchAnalysis.processing_time_ms.is_not(None)
                        )
                    )
                )
                
                processing_result = await session.execute(processing_times_stmt)
                processing_stats = processing_result.first()
                
                # Cache hit rate
                total_analyses_stmt = select(func.count(MatchAnalysis.id)).where(
                    MatchAnalysis.created_at >= since_time
                )
                total_analyses_result = await session.execute(total_analyses_stmt)
                total_analyses = total_analyses_result.scalar() or 0
                
                cached_analyses_stmt = select(func.count(MatchAnalysis.id)).where(
                    and_(
                        MatchAnalysis.created_at >= since_time,
                        MatchAnalysis.cached_data_used == True
                    )
                )
                cached_analyses_result = await session.execute(cached_analyses_stmt)
                cached_analyses = cached_analyses_result.scalar() or 0
                
                # Error rate (failed analyses)
                failed_analyses_stmt = select(func.count(MatchAnalysis.id)).where(
                    and_(
                        MatchAnalysis.created_at >= since_time,
                        MatchAnalysis.status == MatchStatus.CANCELLED
                    )
                )
                failed_analyses_result = await session.execute(failed_analyses_stmt)
                failed_analyses = failed_analyses_result.scalar() or 0
                
                # Request volume by hour
                hourly_volume_stmt = (
                    select(
                        func.extract('hour', MatchAnalysis.created_at).label('hour'),
                        func.count(MatchAnalysis.id).label('requests')
                    )
                    .where(MatchAnalysis.created_at >= since_time)
                    .group_by('hour')
                    .order_by('hour')
                )
                
                hourly_volume_result = await session.execute(hourly_volume_stmt)
                hourly_volume = [
                    {"hour": int(row.hour), "requests": row.requests}
                    for row in hourly_volume_result
                ]
                
                return {
                    "processing_times": {
                        "average_ms": round(processing_stats.avg_time or 0, 2),
                        "median_ms": round(processing_stats.median_time or 0, 2),
                        "p95_ms": round(processing_stats.p95_time or 0, 2),
                        "max_ms": processing_stats.max_time or 0
                    },
                    "cache_performance": {
                        "total_requests": total_analyses,
                        "cache_hits": cached_analyses,
                        "hit_rate": round((cached_analyses / total_analyses * 100) if total_analyses > 0 else 0, 2)
                    },
                    "reliability": {
                        "total_requests": total_analyses,
                        "failed_requests": failed_analyses,
                        "error_rate": round((failed_analyses / total_analyses * 100) if total_analyses > 0 else 0, 2)
                    },
                    "volume": hourly_volume,
                    "period_hours": hours
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_performance_metrics: {e}")
            return {"error": str(e)}
    
    # Business analytics
    async def get_revenue_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive revenue analytics.
        
        Args:
            start_date: Start of analysis period
            end_date: End of analysis period
            
        Returns:
            Dictionary with revenue analytics
        """
        try:
            if not start_date:
                start_date = datetime.now() - timedelta(days=30)
            if not end_date:
                end_date = datetime.now()
            
            async with self.get_session() as session:
                # Total revenue
                revenue_stmt = (
                    select(func.sum(Payment.amount).label('total_revenue'))
                    .where(
                        and_(
                            Payment.status == PaymentStatus.COMPLETED,
                            Payment.created_at >= start_date,
                            Payment.created_at <= end_date
                        )
                    )
                )
                
                revenue_result = await session.execute(revenue_stmt)
                total_revenue = revenue_result.scalar() or 0
                
                # Revenue by tier
                tier_revenue_stmt = (
                    select(
                        Payment.subscription_tier,
                        Payment.subscription_duration,
                        func.sum(Payment.amount).label('revenue'),
                        func.count(Payment.id).label('payments')
                    )
                    .where(
                        and_(
                            Payment.status == PaymentStatus.COMPLETED,
                            Payment.created_at >= start_date,
                            Payment.created_at <= end_date
                        )
                    )
                    .group_by(Payment.subscription_tier, Payment.subscription_duration)
                )
                
                tier_revenue_result = await session.execute(tier_revenue_stmt)
                tier_breakdown = {}
                for row in tier_revenue_result:
                    key = f"{row.subscription_tier.value}_{row.subscription_duration}"
                    tier_breakdown[key] = {
                        "revenue": row.revenue,
                        "payments": row.payments,
                        "average_payment": round(row.revenue / row.payments, 2) if row.payments > 0 else 0
                    }
                
                # Revenue over time (daily)
                daily_revenue_stmt = (
                    select(
                        func.date_trunc('day', Payment.created_at).label('date'),
                        func.sum(Payment.amount).label('revenue'),
                        func.count(Payment.id).label('payments')
                    )
                    .where(
                        and_(
                            Payment.status == PaymentStatus.COMPLETED,
                            Payment.created_at >= start_date,
                            Payment.created_at <= end_date
                        )
                    )
                    .group_by('date')
                    .order_by('date')
                )
                
                daily_revenue_result = await session.execute(daily_revenue_stmt)
                daily_revenue = [
                    {
                        "date": row.date.isoformat(),
                        "revenue": row.revenue,
                        "payments": row.payments
                    }
                    for row in daily_revenue_result
                ]
                
                # Subscription conversions
                total_users_stmt = select(func.count(User.id))
                total_users_result = await session.execute(total_users_stmt)
                total_users = total_users_result.scalar() or 0
                
                paid_users_stmt = (
                    select(func.count(distinct(UserSubscription.user_id)))
                    .where(UserSubscription.tier != SubscriptionTier.FREE)
                )
                paid_users_result = await session.execute(paid_users_stmt)
                paid_users = paid_users_result.scalar() or 0
                
                return {
                    "revenue": {
                        "total": total_revenue,
                        "tier_breakdown": tier_breakdown,
                        "daily_data": daily_revenue
                    },
                    "conversions": {
                        "total_users": total_users,
                        "paid_users": paid_users,
                        "conversion_rate": round((paid_users / total_users * 100) if total_users > 0 else 0, 2)
                    },
                    "period": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat()
                    }
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_revenue_analytics: {e}")
            return {"error": str(e)}
    
    # Real-time dashboard
    async def get_realtime_dashboard(self) -> Dict[str, Any]:
        """
        Get real-time dashboard metrics.
        
        Returns:
            Dictionary with real-time metrics
        """
        try:
            now = datetime.now()
            hour_ago = now - timedelta(hours=1)
            day_ago = now - timedelta(days=1)
            
            async with self.get_session() as session:
                # Current active users (last hour)
                current_active_stmt = select(func.count(distinct(User.id))).where(
                    User.last_active_at >= hour_ago
                )
                current_active_result = await session.execute(current_active_stmt)
                current_active = current_active_result.scalar() or 0
                
                # Requests in last hour
                hourly_requests_stmt = select(func.count(MatchAnalysis.id)).where(
                    MatchAnalysis.created_at >= hour_ago
                )
                hourly_requests_result = await session.execute(hourly_requests_stmt)
                hourly_requests = hourly_requests_result.scalar() or 0
                
                # New users today
                daily_users_stmt = select(func.count(User.id)).where(
                    User.created_at >= day_ago
                )
                daily_users_result = await session.execute(daily_users_stmt)
                daily_users = daily_users_result.scalar() or 0
                
                # Revenue today
                daily_revenue_stmt = (
                    select(func.sum(Payment.amount))
                    .where(
                        and_(
                            Payment.status == PaymentStatus.COMPLETED,
                            Payment.created_at >= day_ago
                        )
                    )
                )
                daily_revenue_result = await session.execute(daily_revenue_stmt)
                daily_revenue = daily_revenue_result.scalar() or 0
                
                # System health indicators
                recent_errors_stmt = select(func.count(MatchAnalysis.id)).where(
                    and_(
                        MatchAnalysis.created_at >= hour_ago,
                        MatchAnalysis.status == MatchStatus.CANCELLED
                    )
                )
                recent_errors_result = await session.execute(recent_errors_stmt)
                recent_errors = recent_errors_result.scalar() or 0
                
                error_rate = round((recent_errors / hourly_requests * 100) if hourly_requests > 0 else 0, 2)
                
                return {
                    "users": {
                        "active_now": current_active,
                        "new_today": daily_users
                    },
                    "activity": {
                        "requests_last_hour": hourly_requests,
                        "revenue_today": daily_revenue
                    },
                    "health": {
                        "error_rate": error_rate,
                        "errors_last_hour": recent_errors
                    },
                    "timestamp": now.isoformat()
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_realtime_dashboard: {e}")
            return {"error": str(e)}
    
    # Data aggregation
    async def aggregate_daily_metrics(self, date: datetime) -> Dict[str, Any]:
        """
        Aggregate metrics for a specific day.
        
        Args:
            date: Date to aggregate metrics for
            
        Returns:
            Dictionary with aggregated metrics
        """
        try:
            start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day + timedelta(days=1)
            
            async with self.get_session() as session:
                # Daily active users
                dau_stmt = select(func.count(distinct(User.id))).where(
                    and_(
                        User.last_active_at >= start_of_day,
                        User.last_active_at < end_of_day
                    )
                )
                dau_result = await session.execute(dau_stmt)
                daily_active_users = dau_result.scalar() or 0
                
                # New users
                new_users_stmt = select(func.count(User.id)).where(
                    and_(
                        User.created_at >= start_of_day,
                        User.created_at < end_of_day
                    )
                )
                new_users_result = await session.execute(new_users_stmt)
                new_users = new_users_result.scalar() or 0
                
                # Total requests
                requests_stmt = select(func.count(MatchAnalysis.id)).where(
                    and_(
                        MatchAnalysis.created_at >= start_of_day,
                        MatchAnalysis.created_at < end_of_day
                    )
                )
                requests_result = await session.execute(requests_stmt)
                total_requests = requests_result.scalar() or 0
                
                # Revenue
                revenue_stmt = (
                    select(func.sum(Payment.amount))
                    .where(
                        and_(
                            Payment.status == PaymentStatus.COMPLETED,
                            Payment.created_at >= start_of_day,
                            Payment.created_at < end_of_day
                        )
                    )
                )
                revenue_result = await session.execute(revenue_stmt)
                daily_revenue = revenue_result.scalar() or 0
                
                # Store aggregated metrics
                metrics_to_record = [
                    {"name": "daily_active_users", "value": daily_active_users},
                    {"name": "new_users", "value": new_users},
                    {"name": "total_requests", "value": total_requests},
                    {"name": "revenue", "value": daily_revenue}
                ]
                
                await self.record_batch_metrics([
                    {
                        **metric,
                        "timestamp": start_of_day,
                        "period": "daily"
                    }
                    for metric in metrics_to_record
                ])
                
                return {
                    "date": date.date().isoformat(),
                    "daily_active_users": daily_active_users,
                    "new_users": new_users,
                    "total_requests": total_requests,
                    "revenue": daily_revenue
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in aggregate_daily_metrics: {e}")
            return {"error": str(e)}
    
    # Cleanup operations
    async def cleanup_old_metrics(self, days_old: int = 90) -> int:
        """
        Clean up old metrics data to save space.
        
        Args:
            days_old: Age threshold in days
            
        Returns:
            Number of deleted metrics
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_old)
            
            async with self.get_session() as session:
                stmt = select(Analytics.id).where(Analytics.timestamp < cutoff_date)
                result = await session.execute(stmt)
                old_ids = [row.id for row in result]
                
                if old_ids:
                    deleted_count = await self.delete_batch(old_ids)
                    logger.info(f"Cleaned up {deleted_count} old metrics")
                    return deleted_count
                
                return 0
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in cleanup_old_metrics: {e}")
            return 0