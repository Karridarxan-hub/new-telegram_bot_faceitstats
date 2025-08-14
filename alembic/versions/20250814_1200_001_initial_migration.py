"""Initial migration - Create all database tables for FACEIT Bot

Revision ID: 001
Revises: 
Create Date: 2025-08-14 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Apply migration changes to upgrade the database schema.
    
    This function creates all the initial tables for the FACEIT Telegram Bot
    including users, subscriptions, match analyses, caching tables, and more.
    """
    
    # Create users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('faceit_player_id', sa.String(length=255), nullable=True),
        sa.Column('faceit_nickname', sa.String(length=255), nullable=True),
        sa.Column('last_checked_match_id', sa.String(length=255), nullable=True),
        sa.Column('waiting_for_nickname', sa.Boolean(), nullable=True, default=False),
        sa.Column('language', sa.String(length=10), nullable=True, default='ru'),
        sa.Column('notifications_enabled', sa.Boolean(), nullable=True, default=True),
        sa.Column('total_requests', sa.Integer(), nullable=True, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    
    # Create indexes for users table
    op.create_index('ix_users_user_id', 'users', ['user_id'])
    op.create_index('ix_users_faceit_player_id', 'users', ['faceit_player_id'])
    op.create_index('ix_users_faceit_nickname', 'users', ['faceit_nickname'])

    # Create user_subscriptions table
    op.create_table('user_subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tier', sa.Enum('FREE', 'PREMIUM', 'PRO', name='subscriptiontier'), nullable=True, default='FREE'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('auto_renew', sa.Boolean(), nullable=True, default=False),
        sa.Column('payment_method', sa.String(length=100), nullable=True),
        sa.Column('daily_requests', sa.Integer(), nullable=True, default=0),
        sa.Column('last_reset_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('referred_by_user_id', sa.Integer(), nullable=True),
        sa.Column('referral_code', sa.String(length=20), nullable=True),
        sa.Column('referrals_count', sa.Integer(), nullable=True, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
        sa.UniqueConstraint('referral_code')
    )
    
    # Create indexes for user_subscriptions table
    op.create_index('ix_user_subscriptions_referred_by_user_id', 'user_subscriptions', ['referred_by_user_id'])
    op.create_index('ix_user_subscriptions_referral_code', 'user_subscriptions', ['referral_code'])

    # Create match_analyses table
    op.create_table('match_analyses',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('match_id', sa.String(length=255), nullable=False),
        sa.Column('match_url', sa.Text(), nullable=True),
        sa.Column('game', sa.String(length=50), nullable=True, default='cs2'),
        sa.Column('region', sa.String(length=50), nullable=True),
        sa.Column('map_name', sa.String(length=100), nullable=True),
        sa.Column('status', sa.Enum('SCHEDULED', 'CONFIGURING', 'READY', 'ONGOING', 'FINISHED', 'CANCELLED', name='matchstatus'), nullable=True, default='SCHEDULED'),
        sa.Column('competition_name', sa.String(length=255), nullable=True),
        sa.Column('competition_type', sa.String(length=100), nullable=True),
        sa.Column('team1_analysis', sa.JSON(), nullable=True),
        sa.Column('team2_analysis', sa.JSON(), nullable=True),
        sa.Column('match_prediction', sa.JSON(), nullable=True),
        sa.Column('analysis_version', sa.String(length=20), nullable=True, default='1.0'),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('cached_data_used', sa.Boolean(), nullable=True, default=False),
        sa.Column('configured_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for match_analyses table
    op.create_index('ix_match_analyses_match_id', 'match_analyses', ['match_id'])
    op.create_index('idx_match_analyses_user_created', 'match_analyses', ['user_id', 'created_at'])
    op.create_index('idx_match_analyses_match_status', 'match_analyses', ['match_id', 'status'])
    op.create_index('idx_match_analyses_game_region', 'match_analyses', ['game', 'region'])

    # Create player_stats_cache table
    op.create_table('player_stats_cache',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('player_id', sa.String(length=255), nullable=False),
        sa.Column('nickname', sa.String(length=255), nullable=False),
        sa.Column('game', sa.String(length=50), nullable=True, default='cs2'),
        sa.Column('avatar', sa.Text(), nullable=True),
        sa.Column('country', sa.String(length=10), nullable=True),
        sa.Column('skill_level', sa.Integer(), nullable=True),
        sa.Column('faceit_elo', sa.Integer(), nullable=True),
        sa.Column('winrate', sa.Float(), nullable=True),
        sa.Column('avg_kd', sa.Float(), nullable=True),
        sa.Column('avg_adr', sa.Float(), nullable=True),
        sa.Column('hltv_rating', sa.Float(), nullable=True),
        sa.Column('recent_form', sa.String(length=50), nullable=True),
        sa.Column('danger_level', sa.Integer(), nullable=True),
        sa.Column('player_role', sa.String(length=50), nullable=True),
        sa.Column('match_history_stats', sa.JSON(), nullable=True),
        sa.Column('map_performance', sa.JSON(), nullable=True),
        sa.Column('weapon_preferences', sa.JSON(), nullable=True),
        sa.Column('clutch_stats', sa.JSON(), nullable=True),
        sa.Column('cache_version', sa.String(length=20), nullable=True, default='1.0'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('player_id', 'game', name='uq_player_stats_cache_player_game')
    )
    
    # Create indexes for player_stats_cache table
    op.create_index('ix_player_stats_cache_player_id', 'player_stats_cache', ['player_id'])
    op.create_index('ix_player_stats_cache_nickname', 'player_stats_cache', ['nickname'])
    op.create_index('idx_player_stats_cache_player_game', 'player_stats_cache', ['player_id', 'game'])
    op.create_index('idx_player_stats_cache_nickname_game', 'player_stats_cache', ['nickname', 'game'])
    op.create_index('idx_player_stats_cache_expires_at', 'player_stats_cache', ['expires_at'])

    # Create payments table
    op.create_table('payments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('telegram_payment_charge_id', sa.String(length=255), nullable=True),
        sa.Column('provider_payment_charge_id', sa.String(length=255), nullable=True),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=True, default='XTR'),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('subscription_tier', sa.Enum('FREE', 'PREMIUM', 'PRO', name='subscriptiontier'), nullable=False),
        sa.Column('subscription_duration', sa.String(length=20), nullable=False),
        sa.Column('duration_days', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'COMPLETED', 'FAILED', 'REFUNDED', name='paymentstatus'), nullable=True, default='PENDING'),
        sa.Column('payment_method', sa.String(length=100), nullable=True, default='telegram_stars'),
        sa.Column('payment_payload', sa.Text(), nullable=True),
        sa.Column('invoice_title', sa.String(length=255), nullable=True),
        sa.Column('invoice_description', sa.Text(), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('telegram_payment_charge_id'),
        sa.CheckConstraint('amount > 0', name='chk_payments_amount_positive')
    )
    
    # Create indexes for payments table
    op.create_index('idx_payments_user_created', 'payments', ['user_id', 'created_at'])
    op.create_index('idx_payments_status_created', 'payments', ['status', 'created_at'])
    op.create_index('idx_payments_tier_duration', 'payments', ['subscription_tier', 'subscription_duration'])

    # Create match_cache table
    op.create_table('match_cache',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('match_id', sa.String(length=255), nullable=False),
        sa.Column('match_data', sa.JSON(), nullable=False),
        sa.Column('match_stats', sa.JSON(), nullable=True),
        sa.Column('cache_version', sa.String(length=20), nullable=True, default='1.0'),
        sa.Column('data_source', sa.String(length=50), nullable=True, default='faceit_api'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('access_count', sa.Integer(), nullable=True, default=0),
        sa.Column('last_accessed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('match_id')
    )
    
    # Create indexes for match_cache table
    op.create_index('ix_match_cache_match_id', 'match_cache', ['match_id'])
    op.create_index('idx_match_cache_expires_at', 'match_cache', ['expires_at'])
    op.create_index('idx_match_cache_access_count', 'match_cache', ['access_count'])

    # Create system_settings table
    op.create_table('system_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('key', sa.String(length=255), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('value_type', sa.String(length=50), nullable=True, default='string'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True, default='general'),
        sa.Column('is_public', sa.Boolean(), nullable=True, default=False),
        sa.Column('validation_rule', sa.Text(), nullable=True),
        sa.Column('default_value', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )
    
    # Create indexes for system_settings table
    op.create_index('ix_system_settings_key', 'system_settings', ['key'])
    op.create_index('idx_system_settings_category', 'system_settings', ['category'])
    op.create_index('idx_system_settings_public', 'system_settings', ['is_public'])

    # Create analytics table
    op.create_table('analytics',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('metric_name', sa.String(length=255), nullable=False),
        sa.Column('metric_type', sa.String(length=50), nullable=True, default='counter'),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period', sa.String(length=20), nullable=True, default='daily'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for analytics table
    op.create_index('ix_analytics_metric_name', 'analytics', ['metric_name'])
    op.create_index('ix_analytics_timestamp', 'analytics', ['timestamp'])
    op.create_index('idx_analytics_metric_timestamp', 'analytics', ['metric_name', 'timestamp'])
    op.create_index('idx_analytics_period_timestamp', 'analytics', ['period', 'timestamp'])
    op.create_index('idx_analytics_type_timestamp', 'analytics', ['metric_type', 'timestamp'])

    # Create trigger for updated_at columns
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    # Add triggers to all tables with updated_at columns
    tables_with_updated_at = [
        'users', 'user_subscriptions', 'match_analyses', 
        'player_stats_cache', 'payments', 'match_cache', 
        'system_settings'
    ]
    
    for table in tables_with_updated_at:
        op.execute(f"""
            CREATE TRIGGER update_{table}_updated_at 
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
        """)


def downgrade() -> None:
    """
    Revert migration changes to downgrade the database schema.
    
    This function removes all tables and related database objects created
    in the upgrade function.
    
    WARNING: This will result in complete data loss. Ensure you have proper
    backups before running this downgrade in production.
    """
    
    # Drop all triggers first
    tables_with_updated_at = [
        'users', 'user_subscriptions', 'match_analyses', 
        'player_stats_cache', 'payments', 'match_cache', 
        'system_settings'
    ]
    
    for table in tables_with_updated_at:
        op.execute(f"DROP TRIGGER IF EXISTS update_{table}_updated_at ON {table};")
    
    # Drop the trigger function
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")
    
    # Drop all tables (order matters due to foreign keys)
    op.drop_table('analytics')
    op.drop_table('system_settings')
    op.drop_table('match_cache')
    op.drop_table('payments')
    op.drop_table('player_stats_cache')
    op.drop_table('match_analyses')
    op.drop_table('user_subscriptions')
    op.drop_table('users')
    
    # Drop custom enums
    op.execute('DROP TYPE IF EXISTS paymentstatus;')
    op.execute('DROP TYPE IF EXISTS matchstatus;')
    op.execute('DROP TYPE IF EXISTS subscriptiontier;')