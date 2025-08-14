"""Task completion callbacks for background jobs."""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import Message
from aiogram.enums import ParseMode

from utils.formatter import MessageFormatter
from utils.match_analyzer import format_match_analysis
from utils.storage import storage

logger = logging.getLogger(__name__)

# Global registry for callbacks
_callback_registry: Dict[str, "TaskCallback"] = {}


@dataclass
class TaskCallback:
    """Task completion callback handler."""
    task_id: str
    user_id: int
    callback_func: Optional[Callable] = None
    bot: Optional[Bot] = None
    chat_id: Optional[int] = None
    original_message_id: Optional[int] = None
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    async def register(self):
        """Register callback for task completion."""
        _callback_registry[self.task_id] = self
        logger.debug(f"Registered callback for task {self.task_id}")
    
    async def unregister(self):
        """Unregister callback."""
        if self.task_id in _callback_registry:
            del _callback_registry[self.task_id]
            logger.debug(f"Unregistered callback for task {self.task_id}")
    
    async def trigger(self, result: Dict[str, Any]):
        """Trigger callback with result."""
        try:
            if self.callback_func:
                # Call custom callback function
                await self.callback_func(self.task_id, result, self.user_id)
            else:
                # Default behavior based on task type
                await self._handle_default_callback(result)
                
        except Exception as e:
            logger.error(f"Error triggering callback for task {self.task_id}: {e}")
        finally:
            # Always unregister after triggering
            await self.unregister()
    
    async def trigger_failure(self, error: str):
        """Trigger callback for failed task."""
        try:
            if self.bot and self.user_id:
                await self.bot.send_message(
                    chat_id=self.user_id,
                    text=f"❌ <b>Задача завершилась с ошибкой</b>\n\n"
                         f"🆔 ID: <code>{self.task_id}</code>\n"
                         f"❗ Ошибка: {error}",
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            logger.error(f"Error sending failure notification for task {self.task_id}: {e}")
        finally:
            await self.unregister()
    
    async def _handle_default_callback(self, result: Dict[str, Any]):
        """Handle default callback behavior based on result."""
        if not self.bot or not self.user_id:
            return
        
        success = result.get("success", False)
        
        if not success:
            # Send error message
            error = result.get("error", "Неизвестная ошибка")
            await self.bot.send_message(
                chat_id=self.user_id,
                text=f"❌ <b>Задача завершилась с ошибкой</b>\n\n"
                     f"🆔 ID: <code>{self.task_id}</code>\n"
                     f"❗ Ошибка: {error}",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Handle successful completion based on result type
        await self._send_success_notification(result)
    
    async def _send_success_notification(self, result: Dict[str, Any]):
        """Send success notification with results."""
        try:
            # Determine result type and send appropriate message
            if "formatted_message" in result:
                # Match analysis result
                await self._send_match_analysis_result(result)
            elif "performance" in result and "trends" in result:
                # Player performance result
                await self._send_player_performance_result(result)
            elif "results" in result and "total_matches" in result:
                # Bulk analysis result
                await self._send_bulk_analysis_result(result)
            else:
                # Generic success message
                await self._send_generic_success(result)
                
        except Exception as e:
            logger.error(f"Error sending success notification: {e}")
    
    async def _send_match_analysis_result(self, result: Dict[str, Any]):
        """Send match analysis result."""
        formatted_message = result.get("formatted_message", "")
        
        # Check if message is too long and needs to be split
        if len(formatted_message) > 4096:
            # Split into multiple messages
            parts = self._split_long_message(formatted_message)
            
            for i, part in enumerate(parts):
                if i == 0:
                    await self.bot.send_message(
                        chat_id=self.user_id,
                        text=f"✅ <b>Анализ матча завершён!</b>\n\n{part}",
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await self.bot.send_message(
                        chat_id=self.user_id,
                        text=f"<b>Продолжение анализа...</b>\n\n{part}",
                        parse_mode=ParseMode.HTML
                    )
        else:
            await self.bot.send_message(
                chat_id=self.user_id,
                text=f"✅ <b>Анализ матча завершён!</b>\n\n{formatted_message}",
                parse_mode=ParseMode.HTML
            )
    
    async def _send_player_performance_result(self, result: Dict[str, Any]):
        """Send player performance analysis result."""
        player_info = result.get("player", {})
        performance = result.get("performance", {})
        insights = result.get("insights", {})
        
        message = "📊 <b>Анализ игрока завершён!</b>\n\n"
        message += f"👤 <b>Игрок:</b> {player_info.get('nickname', 'Неизвестно')}\n"
        message += f"🎯 <b>Уровень:</b> {player_info.get('skill_level', 0)}\n"
        message += f"⚡ <b>ELO:</b> {player_info.get('faceit_elo', 0)}\n\n"
        
        # Performance metrics
        if performance:
            message += "📈 <b>Показатели:</b>\n"
            message += f"• Винрейт: {performance.get('winrate', 0)}%\n"
            message += f"• K/D: {performance.get('avg_kd', 0)}\n"
            message += f"• ADR: {performance.get('avg_adr', 0)}\n"
            message += f"• HLTV Rating: {performance.get('hltv_rating', 0)}\n\n"
        
        # Insights
        if insights:
            assessment = insights.get('overall_assessment', '')
            if assessment:
                message += f"🎯 <b>Оценка:</b> {assessment}\n"
            
            form_analysis = insights.get('form_analysis', '')
            if form_analysis:
                message += f"📊 <b>Форма:</b> {form_analysis}\n"
        
        await self.bot.send_message(
            chat_id=self.user_id,
            text=message,
            parse_mode=ParseMode.HTML
        )
    
    async def _send_bulk_analysis_result(self, result: Dict[str, Any]):
        """Send bulk analysis result."""
        total = result.get("total_matches", 0)
        successful = result.get("successful_analyses", 0)
        failed = result.get("failed_analyses", 0)
        success_rate = result.get("success_rate", 0)
        
        message = "📊 <b>Массовый анализ завершён!</b>\n\n"
        message += f"📈 <b>Результаты:</b>\n"
        message += f"• Всего матчей: {total}\n"
        message += f"• Успешно: {successful}\n"
        message += f"• Ошибки: {failed}\n"
        message += f"• Успешность: {success_rate}%\n\n"
        
        if successful > 0:
            message += "✅ Все успешные анализы были сохранены и доступны для просмотра."
        
        await self.bot.send_message(
            chat_id=self.user_id,
            text=message,
            parse_mode=ParseMode.HTML
        )
    
    async def _send_generic_success(self, result: Dict[str, Any]):
        """Send generic success message."""
        await self.bot.send_message(
            chat_id=self.user_id,
            text=f"✅ <b>Задача выполнена успешно!</b>\n\n"
                 f"🆔 ID: <code>{self.task_id}</code>\n"
                 f"⏰ Завершено: {datetime.now().strftime('%H:%M:%S')}",
            parse_mode=ParseMode.HTML
        )
    
    def _split_long_message(self, message: str) -> List[str]:
        """Split long message into parts."""
        parts = []
        current_part = ""
        lines = message.split('\n')
        
        for line in lines:
            if len(current_part + line + '\n') > 4000:
                if current_part:
                    parts.append(current_part.strip())
                    current_part = line + '\n'
                else:
                    parts.append(line)
            else:
                current_part += line + '\n'
        
        if current_part:
            parts.append(current_part.strip())
        
        return parts


# Global functions for callback management

async def register_match_analysis_callback(
    task_id: str,
    user_id: int,
    bot: Bot,
    chat_id: Optional[int] = None,
    message_id: Optional[int] = None
):
    """Register callback for match analysis task."""
    callback = TaskCallback(
        task_id=task_id,
        user_id=user_id,
        bot=bot,
        chat_id=chat_id or user_id,
        original_message_id=message_id
    )
    await callback.register()


async def register_player_performance_callback(
    task_id: str,
    user_id: int,
    bot: Bot,
    chat_id: Optional[int] = None
):
    """Register callback for player performance analysis task."""
    callback = TaskCallback(
        task_id=task_id,
        user_id=user_id,
        bot=bot,
        chat_id=chat_id or user_id
    )
    await callback.register()


async def register_custom_callback(
    task_id: str,
    user_id: int,
    callback_func: Callable,
    bot: Bot
):
    """Register custom callback for task."""
    callback = TaskCallback(
        task_id=task_id,
        user_id=user_id,
        callback_func=callback_func,
        bot=bot
    )
    await callback.register()


async def trigger_completion(task_id: str, result: Dict[str, Any]):
    """Trigger completion callback for task."""
    if task_id in _callback_registry:
        callback = _callback_registry[task_id]
        await callback.trigger(result)
    else:
        logger.warning(f"No callback registered for completed task {task_id}")


async def trigger_failure(task_id: str, error: str):
    """Trigger failure callback for task."""
    if task_id in _callback_registry:
        callback = _callback_registry[task_id]
        await callback.trigger_failure(error)
    else:
        logger.warning(f"No callback registered for failed task {task_id}")


def get_registered_callbacks() -> Dict[str, TaskCallback]:
    """Get all registered callbacks."""
    return _callback_registry.copy()


async def cleanup_expired_callbacks(max_age_hours: int = 24):
    """Clean up expired callbacks."""
    cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
    
    expired_tasks = []
    for task_id, callback in _callback_registry.items():
        if callback.created_at and callback.created_at.timestamp() < cutoff_time:
            expired_tasks.append(task_id)
    
    for task_id in expired_tasks:
        if task_id in _callback_registry:
            await _callback_registry[task_id].unregister()
    
    if expired_tasks:
        logger.info(f"Cleaned up {len(expired_tasks)} expired callbacks")


# Add these methods to TaskCallback class
TaskCallback.trigger_completion = staticmethod(trigger_completion)
TaskCallback.trigger_failure = staticmethod(trigger_failure)