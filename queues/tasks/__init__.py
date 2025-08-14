"""Background tasks package for FACEIT operations.

Provides comprehensive background task system for:
- Match analysis operations
- Player monitoring and statistics updates
- Cache management and optimization
- User notifications and alerts
- Analytics and reporting
- API rate limit management
"""

from .match_analysis import (
    analyze_match_task,
    bulk_analyze_matches_task,
    generate_match_report_task,
    calculate_team_stats_task,
    analyze_player_performance_task
)

from .player_monitoring import (
    monitor_player_matches_task,
    update_player_statistics_task,
    batch_update_players_task,
    check_elo_changes_task,
    track_player_activity_task
)

from .cache_management import (
    warm_cache_task,
    cleanup_expired_cache_task,
    optimize_cache_usage_task,
    refresh_popular_data_task,
    cache_health_check_task
)

from .notifications import (
    send_match_notification_task,
    send_bulk_notifications_task,
    schedule_reminder_task,
    send_analytics_report_task,
    broadcast_announcement_task
)

from .analytics import (
    generate_user_analytics_task,
    calculate_global_statistics_task,
    generate_performance_report_task,
    track_usage_metrics_task,
    create_monthly_report_task
)

__all__ = [
    # Match Analysis Tasks
    'analyze_match_task',
    'bulk_analyze_matches_task', 
    'generate_match_report_task',
    'calculate_team_stats_task',
    'analyze_player_performance_task',
    
    # Player Monitoring Tasks
    'monitor_player_matches_task',
    'update_player_statistics_task',
    'batch_update_players_task',
    'check_elo_changes_task',
    'track_player_activity_task',
    
    # Cache Management Tasks
    'warm_cache_task',
    'cleanup_expired_cache_task',
    'optimize_cache_usage_task',
    'refresh_popular_data_task',
    'cache_health_check_task',
    
    # Notification Tasks
    'send_match_notification_task',
    'send_bulk_notifications_task',
    'schedule_reminder_task',
    'send_analytics_report_task',
    'broadcast_announcement_task',
    
    # Analytics Tasks
    'generate_user_analytics_task',
    'calculate_global_statistics_task',
    'generate_performance_report_task',
    'track_usage_metrics_task',
    'create_monthly_report_task'
]
