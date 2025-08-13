"""Data storage utilities."""

import json
import asyncio
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
from pydantic import BaseModel

from config.settings import settings

logger = logging.getLogger(__name__)


class UserData(BaseModel):
    """User data model."""
    user_id: int
    faceit_player_id: Optional[str] = None
    faceit_nickname: Optional[str] = None
    last_checked_match_id: Optional[str] = None


class DataStorage:
    """JSON file storage for user data."""
    
    def __init__(self, file_path: Optional[str] = None):
        self.file_path = Path(file_path or settings.data_file_path)
        self._lock = asyncio.Lock()
    
    async def _read_data(self) -> Dict[str, Any]:
        """Read data from file."""
        try:
            if self.file_path.exists():
                async with asyncio.to_thread(self.file_path.read_text, encoding="utf-8") as content:
                    return json.loads(content)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read data file: {e}")
        
        return {"users": []}
    
    async def _write_data(self, data: Dict[str, Any]) -> None:
        """Write data to file."""
        try:
            json_content = json.dumps(data, indent=2, ensure_ascii=False)
            async with asyncio.to_thread(
                self.file_path.write_text, 
                json_content, 
                encoding="utf-8"
            ):
                pass
        except OSError as e:
            logger.error(f"Failed to write data file: {e}")
            raise
    
    async def get_user(self, user_id: int) -> Optional[UserData]:
        """Get user by ID."""
        async with self._lock:
            data = await self._read_data()
            users = data.get("users", [])
            
            for user_dict in users:
                if user_dict.get("user_id") == user_id:
                    try:
                        return UserData(**user_dict)
                    except Exception as e:
                        logger.error(f"Failed to parse user data: {e}")
                        return None
            
            return None
    
    async def save_user(self, user_data: UserData) -> None:
        """Save or update user data."""
        async with self._lock:
            data = await self._read_data()
            users = data.get("users", [])
            
            # Find existing user
            user_index = None
            for i, user_dict in enumerate(users):
                if user_dict.get("user_id") == user_data.user_id:
                    user_index = i
                    break
            
            # Update or add user
            user_dict = user_data.dict()
            if user_index is not None:
                users[user_index] = user_dict
            else:
                users.append(user_dict)
            
            data["users"] = users
            await self._write_data(data)
            
            logger.info(f"Saved user data for user {user_data.user_id}")
    
    async def get_all_users(self) -> List[UserData]:
        """Get all users with FACEIT accounts."""
        async with self._lock:
            data = await self._read_data()
            users = data.get("users", [])
            
            result = []
            for user_dict in users:
                try:
                    user = UserData(**user_dict)
                    if user.faceit_player_id:  # Only users with FACEIT accounts
                        result.append(user)
                except Exception as e:
                    logger.error(f"Failed to parse user data: {e}")
            
            return result
    
    async def update_last_checked_match(
        self, 
        user_id: int, 
        match_id: str
    ) -> None:
        """Update last checked match ID for user."""
        user = await self.get_user(user_id)
        if user:
            user.last_checked_match_id = match_id
            await self.save_user(user)
            logger.info(f"Updated last checked match for user {user_id}: {match_id}")


# Global storage instance
storage = DataStorage()