"""Configuration settings for FACEIT Telegram Bot."""

import os
from pydantic import BaseSettings, Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""
    
    # Telegram Bot configuration
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(None, env="TELEGRAM_CHAT_ID")
    
    # FACEIT API configuration
    faceit_api_key: str = Field(..., env="FACEIT_API_KEY")
    faceit_api_base_url: str = Field(
        "https://open.faceit.com/data/v4", 
        env="FACEIT_API_BASE_URL"
    )
    
    # Monitoring settings
    check_interval_minutes: int = Field(10, env="CHECK_INTERVAL_MINUTES")
    
    # Logging
    log_level: str = Field("INFO", env="LOG_LEVEL")
    
    # Data storage
    data_file_path: str = Field("data.json", env="DATA_FILE_PATH")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()


def validate_settings() -> None:
    """Validate required settings."""
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    if not settings.faceit_api_key:
        raise ValueError("FACEIT_API_KEY is required")
    
    print("✅ Configuration validated successfully")