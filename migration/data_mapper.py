"""Data Mapper for JSON to PostgreSQL field mapping.

Handles the conversion between JSON storage format and PostgreSQL model fields,
ensuring proper data type conversion and relationship mapping.
"""

import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from enum import Enum
import uuid

from database.models import SubscriptionTier, PaymentStatus, MatchStatus
from utils.storage import UserData, UserSubscription as JSONUserSubscription

logger = logging.getLogger(__name__)


class MappingError(Exception):
    """Exception raised when data mapping fails."""
    pass


class DataMapper:
    """Maps JSON storage data to PostgreSQL model data."""
    
    def __init__(self):
        """Initialize data mapper with field mappings."""
        self.user_field_mapping = {
            # Direct mappings
            'user_id': 'user_id',
            'faceit_player_id': 'faceit_player_id',
            'faceit_nickname': 'faceit_nickname',
            'last_checked_match_id': 'last_checked_match_id',
            'waiting_for_nickname': 'waiting_for_nickname',
            'language': 'language',
            'notifications_enabled': 'notifications_enabled',
            'total_requests': 'total_requests',
            
            # Datetime fields that need conversion
            'created_at': 'created_at',
            'last_active_at': 'last_active_at',
        }
        
        self.subscription_field_mapping = {
            'tier': 'tier',
            'expires_at': 'expires_at',
            'auto_renew': 'auto_renew',
            'payment_method': 'payment_method',
            'daily_requests': 'daily_requests',
            'last_reset_date': 'last_reset_date',
            'referred_by': 'referred_by_user_id',
            'referral_code': 'referral_code',
            'referrals_count': 'referrals_count',
        }
    
    def map_user_data(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map JSON user data to PostgreSQL User model data.
        
        Args:
            json_data: JSON user data dictionary
            
        Returns:
            Mapped data for PostgreSQL User model
            
        Raises:
            MappingError: When mapping fails
        """
        try:
            mapped_data = {}
            
            # Map direct fields
            for json_field, pg_field in self.user_field_mapping.items():
                if json_field in json_data:
                    value = json_data[json_field]
                    
                    # Handle datetime conversion
                    if json_field in ['created_at', 'last_active_at'] and value:
                        if isinstance(value, str):
                            try:
                                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                            except ValueError as e:
                                logger.warning(f"Invalid datetime format for {json_field}: {value}. Using current time.")
                                value = datetime.now() if json_field == 'created_at' else None
                        elif isinstance(value, datetime):
                            pass  # Already a datetime
                        else:
                            value = None
                    
                    mapped_data[pg_field] = value
            
            # Set defaults for missing fields
            if 'created_at' not in mapped_data or not mapped_data['created_at']:
                mapped_data['created_at'] = datetime.now()
            
            if 'language' not in mapped_data:
                mapped_data['language'] = 'ru'
            
            if 'notifications_enabled' not in mapped_data:
                mapped_data['notifications_enabled'] = True
            
            if 'total_requests' not in mapped_data:
                mapped_data['total_requests'] = 0
            
            if 'waiting_for_nickname' not in mapped_data:
                mapped_data['waiting_for_nickname'] = False
            
            # Add PostgreSQL-specific fields
            mapped_data['id'] = uuid.uuid4()  # Generate new UUID
            mapped_data['updated_at'] = datetime.now()
            
            logger.debug(f"Mapped user data for user_id: {mapped_data.get('user_id')}")
            return mapped_data
            
        except Exception as e:
            raise MappingError(f"Failed to map user data: {e}")
    
    def map_subscription_data(
        self, 
        json_data: Dict[str, Any], 
        user_uuid: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Map JSON subscription data to PostgreSQL UserSubscription model data.
        
        Args:
            json_data: JSON user data containing subscription info
            user_uuid: UUID of the associated user
            
        Returns:
            Mapped data for PostgreSQL UserSubscription model
            
        Raises:
            MappingError: When mapping fails
        """
        try:
            subscription_json = json_data.get('subscription', {})
            mapped_data = {
                'id': uuid.uuid4(),
                'user_id': user_uuid,
                'created_at': datetime.now(),
                'updated_at': datetime.now(),
            }
            
            # Map subscription fields
            for json_field, pg_field in self.subscription_field_mapping.items():
                if json_field in subscription_json:
                    value = subscription_json[json_field]
                    
                    # Handle tier enum conversion
                    if json_field == 'tier':
                        if isinstance(value, str):
                            try:
                                value = SubscriptionTier(value.lower())
                            except ValueError:
                                logger.warning(f"Invalid subscription tier: {value}. Using FREE.")
                                value = SubscriptionTier.FREE
                        else:
                            value = SubscriptionTier.FREE
                    
                    # Handle datetime conversion
                    elif json_field in ['expires_at', 'last_reset_date'] and value:
                        if isinstance(value, str):
                            try:
                                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                            except ValueError:
                                logger.warning(f"Invalid datetime format for {json_field}: {value}")
                                value = None
                        elif isinstance(value, datetime):
                            pass  # Already a datetime
                        else:
                            value = None
                    
                    mapped_data[pg_field] = value
            
            # Set defaults for missing fields
            if 'tier' not in mapped_data:
                mapped_data['tier'] = SubscriptionTier.FREE
            
            if 'daily_requests' not in mapped_data:
                mapped_data['daily_requests'] = 0
                
            if 'referrals_count' not in mapped_data:
                mapped_data['referrals_count'] = 0
                
            if 'auto_renew' not in mapped_data:
                mapped_data['auto_renew'] = False
            
            logger.debug(f"Mapped subscription data for user_id: {user_uuid}")
            return mapped_data
            
        except Exception as e:
            raise MappingError(f"Failed to map subscription data: {e}")
    
    def create_analytics_entries(
        self, 
        json_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Create analytics entries from JSON data for PostgreSQL Analytics model.
        
        Args:
            json_data: Complete JSON data structure
            
        Returns:
            List of analytics entries to insert
        """
        try:
            analytics_entries = []
            current_time = datetime.now()
            
            # Total users metric
            total_users = len(json_data.get('users', []))
            analytics_entries.append({
                'id': uuid.uuid4(),
                'metric_name': 'total_users',
                'metric_type': 'gauge',
                'value': float(total_users),
                'timestamp': current_time,
                'period': 'daily',
                'created_at': current_time,
                'tags': {'migration': 'json_to_postgresql'}
            })
            
            # Users with FACEIT accounts
            users_with_faceit = sum(
                1 for user in json_data.get('users', []) 
                if user.get('faceit_player_id')
            )
            analytics_entries.append({
                'id': uuid.uuid4(),
                'metric_name': 'users_with_faceit',
                'metric_type': 'gauge',
                'value': float(users_with_faceit),
                'timestamp': current_time,
                'period': 'daily',
                'created_at': current_time,
                'tags': {'migration': 'json_to_postgresql'}
            })
            
            # Subscription distribution
            subscription_stats = {'free': 0, 'premium': 0, 'pro': 0}
            for user in json_data.get('users', []):
                tier = user.get('subscription', {}).get('tier', 'free')
                subscription_stats[tier] = subscription_stats.get(tier, 0) + 1
            
            for tier, count in subscription_stats.items():
                analytics_entries.append({
                    'id': uuid.uuid4(),
                    'metric_name': f'subscription_{tier}_users',
                    'metric_type': 'gauge',
                    'value': float(count),
                    'timestamp': current_time,
                    'period': 'daily',
                    'created_at': current_time,
                    'tags': {'migration': 'json_to_postgresql', 'tier': tier}
                })
            
            logger.info(f"Created {len(analytics_entries)} analytics entries")
            return analytics_entries
            
        except Exception as e:
            logger.error(f"Failed to create analytics entries: {e}")
            return []
    
    def validate_mapped_user(self, mapped_data: Dict[str, Any]) -> bool:
        """
        Validate mapped user data before database insertion.
        
        Args:
            mapped_data: Mapped user data
            
        Returns:
            True if valid, False otherwise
        """
        required_fields = ['id', 'user_id', 'created_at']
        
        for field in required_fields:
            if field not in mapped_data or mapped_data[field] is None:
                logger.error(f"Missing required field in user data: {field}")
                return False
        
        # Validate user_id is positive integer
        if not isinstance(mapped_data['user_id'], int) or mapped_data['user_id'] <= 0:
            logger.error(f"Invalid user_id: {mapped_data['user_id']}")
            return False
        
        # Validate UUID format
        if not isinstance(mapped_data['id'], uuid.UUID):
            logger.error(f"Invalid UUID format: {mapped_data['id']}")
            return False
        
        # Validate datetime fields
        datetime_fields = ['created_at', 'updated_at', 'last_active_at']
        for field in datetime_fields:
            if field in mapped_data and mapped_data[field] is not None:
                if not isinstance(mapped_data[field], datetime):
                    logger.error(f"Invalid datetime format in field {field}: {mapped_data[field]}")
                    return False
        
        return True
    
    def validate_mapped_subscription(self, mapped_data: Dict[str, Any]) -> bool:
        """
        Validate mapped subscription data before database insertion.
        
        Args:
            mapped_data: Mapped subscription data
            
        Returns:
            True if valid, False otherwise
        """
        required_fields = ['id', 'user_id', 'tier', 'created_at']
        
        for field in required_fields:
            if field not in mapped_data or mapped_data[field] is None:
                logger.error(f"Missing required field in subscription data: {field}")
                return False
        
        # Validate tier is SubscriptionTier enum
        if not isinstance(mapped_data['tier'], SubscriptionTier):
            logger.error(f"Invalid subscription tier: {mapped_data['tier']}")
            return False
        
        # Validate UUIDs
        uuid_fields = ['id', 'user_id']
        for field in uuid_fields:
            if not isinstance(mapped_data[field], uuid.UUID):
                logger.error(f"Invalid UUID format in field {field}: {mapped_data[field]}")
                return False
        
        # Validate integer fields
        integer_fields = ['daily_requests', 'referrals_count']
        for field in integer_fields:
            if field in mapped_data and mapped_data[field] is not None:
                if not isinstance(mapped_data[field], int) or mapped_data[field] < 0:
                    logger.error(f"Invalid integer value in field {field}: {mapped_data[field]}")
                    return False
        
        return True
    
    def get_mapping_summary(self) -> Dict[str, Any]:
        """
        Get summary of field mappings for documentation.
        
        Returns:
            Dictionary containing mapping information
        """
        return {
            'user_mappings': self.user_field_mapping,
            'subscription_mappings': self.subscription_field_mapping,
            'supported_conversions': {
                'datetime_fields': ['created_at', 'last_active_at', 'expires_at', 'last_reset_date'],
                'enum_fields': ['tier'],
                'uuid_fields': ['id', 'user_id (in relationships)'],
                'boolean_fields': ['waiting_for_nickname', 'notifications_enabled', 'auto_renew'],
                'integer_fields': ['user_id', 'total_requests', 'daily_requests', 'referrals_count']
            }
        }