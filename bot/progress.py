"""Progress tracking utilities for background tasks."""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

from queues.task_manager import get_task_manager, TaskStatus

logger = logging.getLogger(__name__)

# Global task manager
task_manager = get_task_manager()


@dataclass
class ProgressTracker:
    """Tracks progress for background tasks."""
    
    def __init__(self):
        self.tracked_tasks: Dict[str, Dict[str, Any]] = {}
        self.update_interval = 10  # seconds
        self.max_update_failures = 3
    
    async def start_tracking(
        self,
        task_id: str,
        user_id: int,
        bot: Bot,
        progress_message_id: int,
        chat_id: int,
        task_type: str
    ):
        """Start tracking progress for a task."""
        self.tracked_tasks[task_id] = {
            "user_id": user_id,
            "bot": bot,
            "progress_message_id": progress_message_id,
            "chat_id": chat_id,
            "task_type": task_type,
            "last_update": datetime.now(),
            "update_failures": 0,
            "started_at": datetime.now()
        }
        
        # Start monitoring task
        asyncio.create_task(self._monitor_task_progress(task_id))
        logger.debug(f"Started tracking progress for task {task_id}")
    
    async def stop_tracking(self, task_id: str):
        """Stop tracking progress for a task."""
        if task_id in self.tracked_tasks:
            del self.tracked_tasks[task_id]
            logger.debug(f"Stopped tracking progress for task {task_id}")
    
    async def _monitor_task_progress(self, task_id: str):
        """Monitor task progress and update message."""
        while task_id in self.tracked_tasks:
            try:
                task_info = self.tracked_tasks[task_id]
                
                # Get current task status
                status = task_manager.get_task_status(task_id)
                task_status = status.get("status", "unknown")
                
                # Check if task is completed or failed
                if task_status in ["finished", "failed", "cancelled", "not_found"]:
                    await self._handle_task_completion(task_id, status)
                    break
                
                # Update progress message
                await self._update_progress_message(task_id, status)
                
                # Wait before next check
                await asyncio.sleep(self.update_interval)
                
            except Exception as e:
                logger.error(f"Error monitoring task {task_id}: {e}")
                
                # Increment failure counter
                if task_id in self.tracked_tasks:
                    self.tracked_tasks[task_id]["update_failures"] += 1
                    
                    # Stop tracking if too many failures
                    if self.tracked_tasks[task_id]["update_failures"] >= self.max_update_failures:
                        logger.warning(f"Stopping progress tracking for task {task_id} due to repeated failures")
                        await self.stop_tracking(task_id)
                        break
                
                await asyncio.sleep(self.update_interval)
    
    async def _update_progress_message(self, task_id: str, status: Dict[str, Any]):
        """Update progress message with current status."""
        if task_id not in self.tracked_tasks:
            return
        
        task_info = self.tracked_tasks[task_id]
        
        try:
            # Format progress message
            progress_text = format_progress_message(task_id, status)
            
            # Create keyboard
            keyboard = create_progress_keyboard(task_id, status.get("status", "unknown"))
            
            # Update message
            await task_info["bot"].edit_message_text(
                chat_id=task_info["chat_id"],
                message_id=task_info["progress_message_id"],
                text=progress_text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            
            # Update last update time
            task_info["last_update"] = datetime.now()
            task_info["update_failures"] = 0  # Reset failure counter on success
            
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                # Message hasn't changed, this is fine
                pass
            else:
                logger.warning(f"Telegram error updating progress for task {task_id}: {e}")
                task_info["update_failures"] += 1
        
        except Exception as e:
            logger.error(f"Error updating progress message for task {task_id}: {e}")
            task_info["update_failures"] += 1
    
    async def _handle_task_completion(self, task_id: str, status: Dict[str, Any]):
        """Handle task completion."""
        if task_id not in self.tracked_tasks:
            return
        
        task_info = self.tracked_tasks[task_id]
        task_status = status.get("status", "unknown")
        
        try:
            # Create final message
            if task_status == "finished":
                final_text = (
                    f"✅ <b>Задача выполнена успешно!</b>\n\n"
                    f"🆔 ID: <code>{task_id}</code>\n"
                    f"📋 Тип: {get_task_type_name(task_info['task_type'])}\n"
                    f"⏰ Завершено: {datetime.now().strftime('%H:%M:%S')}\n\n"
                    f"🎉 Результат будет отправлен отдельным сообщением."
                )
            elif task_status == "failed":
                error_info = status.get("failure_info", {})
                error_msg = error_info.get("exception", "Неизвестная ошибка")
                
                final_text = (
                    f"❌ <b>Задача завершилась с ошибкой</b>\n\n"
                    f"🆔 ID: <code>{task_id}</code>\n"
                    f"📋 Тип: {get_task_type_name(task_info['task_type'])}\n"
                    f"⏰ Завершено: {datetime.now().strftime('%H:%M:%S')}\n\n"
                    f"❗ <b>Ошибка:</b> {error_msg}"
                )
            elif task_status == "cancelled":
                final_text = (
                    f"🚫 <b>Задача отменена</b>\n\n"
                    f"🆔 ID: <code>{task_id}</code>\n"
                    f"📋 Тип: {get_task_type_name(task_info['task_type'])}\n"
                    f"⏰ Отменено: {datetime.now().strftime('%H:%M:%S')}"
                )
            else:
                final_text = (
                    f"❓ <b>Задача завершена с неизвестным статусом</b>\n\n"
                    f"🆔 ID: <code>{task_id}</code>\n"
                    f"📋 Тип: {get_task_type_name(task_info['task_type'])}\n"
                    f"📊 Статус: {task_status}"
                )
            
            # Update final message (no keyboard)
            await task_info["bot"].edit_message_text(
                chat_id=task_info["chat_id"],
                message_id=task_info["progress_message_id"],
                text=final_text,
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            logger.error(f"Error handling task completion for {task_id}: {e}")
        
        finally:
            # Stop tracking
            await self.stop_tracking(task_id)
    
    def get_tracked_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get all currently tracked tasks."""
        return self.tracked_tasks.copy()
    
    async def cleanup_stale_tasks(self, max_age_hours: int = 2):
        """Clean up stale task tracking."""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        stale_tasks = []
        
        for task_id, task_info in self.tracked_tasks.items():
            if task_info["started_at"] < cutoff_time:
                stale_tasks.append(task_id)
        
        for task_id in stale_tasks:
            await self.stop_tracking(task_id)
        
        if stale_tasks:
            logger.info(f"Cleaned up {len(stale_tasks)} stale task trackers")


def format_progress_message(task_id: str, status: Dict[str, Any]) -> str:
    """Format progress message based on task status."""
    task_status = status.get("status", "unknown")
    progress_data = status.get("progress", {})
    
    # Base information
    message = f"🔄 <b>Выполнение задачи</b>\n\n"
    message += f"🆔 ID: <code>{task_id}</code>\n"
    
    # Status
    status_emoji = {
        "queued": "⏳",
        "started": "🔄",
        "finished": "✅",
        "failed": "❌",
        "cancelled": "🚫"
    }
    
    status_text = {
        "queued": "В очереди",
        "started": "Выполняется",
        "finished": "Завершено",
        "failed": "Ошибка",
        "cancelled": "Отменено"
    }
    
    emoji = status_emoji.get(task_status, "❓")
    text = status_text.get(task_status, task_status.title())
    
    message += f"📊 Статус: {emoji} {text}\n"
    
    # Add progress information if available
    if progress_data:
        current_step = progress_data.get("current_step", 0)
        total_steps = progress_data.get("total_steps", 0)
        current_operation = progress_data.get("current_operation", "")
        progress_percentage = progress_data.get("progress_percentage", 0)
        
        if total_steps > 0:
            message += f"📈 Прогресс: {current_step}/{total_steps} ({progress_percentage}%)\n"
            
            # Create progress bar
            bar_length = 10
            filled_length = int(bar_length * (current_step / total_steps))
            bar = "█" * filled_length + "░" * (bar_length - filled_length)
            message += f"📊 [{bar}]\n"
        
        if current_operation:
            message += f"⚙️ Операция: {current_operation}\n"
        
        # Show errors if any
        errors = progress_data.get("errors", [])
        if errors:
            message += f"⚠️ Предупреждения: {len(errors)}\n"
    
    # Add timing information
    created_at = status.get("created_at")
    started_at = status.get("started_at")
    
    if started_at:
        start_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
        duration = datetime.now() - start_time.replace(tzinfo=None)
        message += f"⏱️ Время выполнения: {format_duration(duration)}\n"
    elif created_at:
        create_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        wait_time = datetime.now() - create_time.replace(tzinfo=None)
        message += f"⏳ Время в очереди: {format_duration(wait_time)}\n"
    
    return message


def create_progress_keyboard(task_id: str, task_status: str) -> Optional[InlineKeyboardMarkup]:
    """Create keyboard for progress tracking."""
    if task_status in ["finished", "failed", "cancelled"]:
        return None
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=f"task_status:{task_id}"
            ),
            InlineKeyboardButton(
                text="🚫 Отменить",
                callback_data=f"task_cancel:{task_id}"
            )
        ]
    ])


def get_task_type_name(task_type: str) -> str:
    """Get human-readable task type name."""
    names = {
        "match_analysis": "Анализ матча",
        "player_performance": "Анализ игрока",
        "bulk_analysis": "Массовый анализ",
        "user_analytics": "Пользовательская аналитика",
        "player_monitoring": "Мониторинг игроков",
        "cache_warming": "Прогрев кэша",
        "notifications": "Уведомления"
    }
    return names.get(task_type, task_type.replace('_', ' ').title())


def format_duration(duration: timedelta) -> str:
    """Format duration in human-readable format."""
    total_seconds = int(duration.total_seconds())
    
    if total_seconds < 60:
        return f"{total_seconds}с"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}м {seconds}с"
    else:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}ч {minutes}м"


async def send_progress_message(
    bot: Bot,
    chat_id: int,
    task_id: str,
    task_type: str,
    initial_message: str = None
) -> int:
    """Send initial progress message and return message ID."""
    if initial_message is None:
        initial_message = (
            f"⏳ <b>Задача добавлена в очередь</b>\n\n"
            f"🆔 ID: <code>{task_id}</code>\n"
            f"📋 Тип: {get_task_type_name(task_type)}\n"
            f"📊 Статус: В очереди"
        )
    
    keyboard = create_progress_keyboard(task_id, "queued")
    
    message = await bot.send_message(
        chat_id=chat_id,
        text=initial_message,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    
    return message.message_id


# Global progress tracker instance
progress_tracker = ProgressTracker()