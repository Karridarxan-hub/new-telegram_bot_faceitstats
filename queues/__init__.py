"""Queue management system for FACEIT Telegram Bot.

This package provides a comprehensive queue system built on top of Redis Queue (RQ)
for handling CPU-intensive operations and background tasks in the FACEIT Telegram Bot.

Components:
- manager: Queue management and orchestration
- jobs: Background job definitions for FACEIT operations  
- config: Queue configuration and settings
- monitoring: Queue monitoring and failure handling

Key Features:
- Multiple queue priorities (high, default, low)
- Job monitoring and failure handling
- Retry mechanisms with exponential backoff
- Performance metrics and analytics
- Integration with existing Redis infrastructure
"""

from .manager import QueueManager
from .jobs import (
    analyze_match_job,
    generate_player_report_job,
    process_bulk_analysis_job,
    monitor_matches_job,
    update_player_cache_job,
    calculate_team_stats_job,
    generate_analytics_report_job
)
from .config import QueueConfig, get_queue_config
from .monitoring import QueueMonitor

__all__ = [
    'QueueManager',
    'QueueConfig',
    'QueueMonitor',
    'get_queue_config',
    'analyze_match_job',
    'generate_player_report_job',
    'process_bulk_analysis_job',
    'monitor_matches_job',
    'update_player_cache_job',
    'calculate_team_stats_job',
    'generate_analytics_report_job'
]

__version__ = "1.0.0"