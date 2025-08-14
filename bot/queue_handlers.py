"""Queue-specific handlers for background task processing."""

import logging
import asyncio
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

from aiogram import Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode

from queues.task_manager import get_task_manager, TaskPriority, TaskStatus
from bot.callbacks import TaskCallback
from bot.progress import ProgressTracker, format_progress_message
from utils.storage import storage

logger = logging.getLogger(__name__)

# Global instances
task_manager = get_task_manager()
progress_tracker = ProgressTracker()

# Store active tasks for users
user_active_tasks: Dict[int, List[str]] = {}


async def handle_background_task_request(
    message: Message,
    task_type: str,
    task_params: Dict[str, Any],
    priority: TaskPriority = TaskPriority.HIGH,
    show_progress: bool = True,
    completion_callback: Optional[Callable] = None
) -> Optional[str]:
    """
    Handle background task request with progress tracking.
    
    Args:
        message: Telegram message object
        task_type: Type of task to enqueue
        task_params: Parameters for the task
        priority: Task priority level
        show_progress: Whether to show progress updates
        completion_callback: Callback for task completion
        
    Returns:
        Task ID if successful, None otherwise
    """
    user_id = message.from_user.id
    
    try:
        # Check user's active tasks
        active_tasks = user_active_tasks.get(user_id, [])
        if len(active_tasks) >= 3:  # Limit concurrent tasks per user
            await message.answer(
                "⚠️ <b>Слишком много активных задач</b>\n\n"
                "У вас уже есть 3 активные задачи. Пожалуйста, дождитесь их завершения.",
                parse_mode=ParseMode.HTML
            )
            return None
        
        # Enqueue appropriate task based on type
        task_id = None
        
        if task_type == "match_analysis":
            task_id = task_manager.enqueue_match_analysis(
                match_url_or_id=task_params['match_url'],
                user_id=user_id,
                force_refresh=task_params.get('force_refresh', False),
                priority=priority
            )
            
        elif task_type == "player_performance":
            task_id = task_manager.enqueue_player_performance_analysis(
                player_id=task_params['player_id'],
                analysis_period_days=task_params.get('period_days', 30),
                include_detailed_stats=task_params.get('detailed', True),
                priority=priority
            )
            
        elif task_type == "bulk_analysis":
            task_id = task_manager.enqueue_bulk_match_analysis(
                match_urls=task_params['match_urls'],
                user_id=user_id,
                options=task_params.get('options', {})
            )
            
        elif task_type == "user_analytics":
            task_id = task_manager.enqueue_user_analytics(
                user_id=user_id,
                analysis_period_days=task_params.get('period_days', 30),
                detailed_analysis=task_params.get('detailed', True)
            )
            
        else:
            await message.answer(
                "❌ Неподдерживаемый тип задачи",
                parse_mode=ParseMode.HTML
            )
            return None
        
        if not task_id:
            await message.answer(
                "❌ Не удалось поставить задачу в очередь",
                parse_mode=ParseMode.HTML
            )
            return None
        
        # Track user's active task
        if user_id not in user_active_tasks:
            user_active_tasks[user_id] = []
        user_active_tasks[user_id].append(task_id)
        
        # Set up progress tracking if requested
        if show_progress:
            await start_progress_tracking(message, task_id, task_type)
        
        # Set up completion callback
        if completion_callback:
            callback = TaskCallback(
                task_id=task_id,
                user_id=user_id,
                callback_func=completion_callback,
                bot=message.bot
            )
            await callback.register()
        
        logger.info(f"Enqueued {task_type} task {task_id} for user {user_id}")
        return task_id
        
    except Exception as e:
        logger.error(f"Error handling background task request: {e}")
        await message.answer(
            "❌ Произошла ошибка при обработке запроса",
            parse_mode=ParseMode.HTML
        )
        return None


async def start_progress_tracking(message: Message, task_id: str, task_type: str):
    """Start progress tracking for a background task."""
    try:
        # Send initial progress message
        progress_message = await message.answer(
            "⏳ <b>Задача добавлена в очередь...</b>\n\n"
            f"🆔 ID задачи: <code>{task_id}</code>\n"
            f"📋 Тип: {_get_task_type_name(task_type)}\n"
            f"🕒 Статус: В очереди",
            parse_mode=ParseMode.HTML,
            reply_markup=_get_task_control_keyboard(task_id)
        )
        
        # Start progress monitoring
        await progress_tracker.start_tracking(
            task_id=task_id,
            user_id=message.from_user.id,
            bot=message.bot,
            progress_message_id=progress_message.message_id,
            chat_id=message.chat.id,
            task_type=task_type
        )
        
    except Exception as e:
        logger.error(f"Error starting progress tracking for task {task_id}: {e}")


async def handle_task_status_check(callback_query: CallbackQuery):
    """Handle task status check from inline button."""
    try:
        await callback_query.answer()
        
        # Extract task ID from callback data
        task_id = callback_query.data.split(":")[-1]
        
        # Get task status
        status = task_manager.get_task_status(task_id)
        
        # Update progress message
        await update_progress_display(
            callback_query.bot,
            callback_query.message.chat.id,
            callback_query.message.message_id,
            task_id,
            status
        )
        
    except Exception as e:
        logger.error(f"Error handling task status check: {e}")
        await callback_query.answer("❌ Ошибка при получении статуса задачи", show_alert=True)


async def handle_task_cancellation(callback_query: CallbackQuery):
    """Handle task cancellation from inline button."""
    try:
        await callback_query.answer()
        
        # Extract task ID from callback data
        task_id = callback_query.data.split(":")[-1]
        user_id = callback_query.from_user.id
        
        # Cancel the task
        success = task_manager.cancel_task(task_id)
        
        if success:
            # Remove from user's active tasks
            if user_id in user_active_tasks:
                user_active_tasks[user_id] = [
                    t for t in user_active_tasks[user_id] if t != task_id
                ]
            
            # Update message
            await callback_query.message.edit_text(
                "🚫 <b>Задача отменена</b>\n\n"
                f"🆔 ID: <code>{task_id}</code>\n"
                f"⏰ Отменена: {datetime.now().strftime('%H:%M:%S')}",
                parse_mode=ParseMode.HTML
            )
        else:
            await callback_query.answer("❌ Не удалось отменить задачу", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error handling task cancellation: {e}")
        await callback_query.answer("❌ Ошибка при отмене задачи", show_alert=True)


async def update_progress_display(
    bot: Bot,
    chat_id: int,
    message_id: int,
    task_id: str,
    status: Dict[str, Any]
):
    """Update progress display with current task status."""
    try:
        task_status = status.get("status", "unknown")
        progress_data = status.get("progress", {})
        
        # Format progress message
        progress_text = format_progress_message(task_id, status)
        
        # Create appropriate keyboard based on status
        if task_status in ["queued", "started"]:
            keyboard = _get_task_control_keyboard(task_id)
        else:
            keyboard = None
        
        # Update message
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=progress_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error updating progress display: {e}")


async def handle_task_completion(task_id: str, result: Dict[str, Any]):
    """Handle task completion notification."""
    try:
        # Remove from active tasks
        for user_id, tasks in user_active_tasks.items():
            if task_id in tasks:
                user_active_tasks[user_id].remove(task_id)
                
                # Stop progress tracking
                await progress_tracker.stop_tracking(task_id)
                
                # Trigger completion callback if registered
                await TaskCallback.trigger_completion(task_id, result)
                break
                
        logger.info(f"Task {task_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Error handling task completion: {e}")


async def handle_task_failure(task_id: str, error: str):
    """Handle task failure notification."""
    try:
        # Remove from active tasks
        for user_id, tasks in user_active_tasks.items():
            if task_id in tasks:
                user_active_tasks[user_id].remove(task_id)
                
                # Stop progress tracking
                await progress_tracker.stop_tracking(task_id)
                
                # Trigger failure callback if registered
                await TaskCallback.trigger_failure(task_id, error)
                break
                
        logger.warning(f"Task {task_id} failed: {error}")
        
    except Exception as e:
        logger.error(f"Error handling task failure: {e}")


def _get_task_type_name(task_type: str) -> str:
    """Get human-readable task type name."""
    names = {
        "match_analysis": "Анализ матча",
        "player_performance": "Анализ игрока",
        "bulk_analysis": "Массовый анализ",
        "user_analytics": "Пользовательская аналитика"
    }
    return names.get(task_type, task_type.title())


def _get_task_control_keyboard(task_id: str) -> InlineKeyboardMarkup:
    """Create keyboard for task control."""
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


async def get_user_active_tasks(user_id: int) -> List[Dict[str, Any]]:
    """Get list of active tasks for a user."""
    active_tasks = user_active_tasks.get(user_id, [])
    task_details = []
    
    for task_id in active_tasks:
        try:
            status = task_manager.get_task_status(task_id)
            task_details.append({
                "task_id": task_id,
                "status": status
            })
        except Exception as e:
            logger.error(f"Error getting status for task {task_id}: {e}")
    
    return task_details


async def cleanup_completed_tasks():
    """Clean up completed and failed tasks from tracking."""
    try:
        for user_id, tasks in list(user_active_tasks.items()):
            active = []
            
            for task_id in tasks:
                try:
                    status = task_manager.get_task_status(task_id)
                    task_status = status.get("status", "unknown")
                    
                    if task_status in ["queued", "started"]:
                        active.append(task_id)
                    else:
                        # Task is completed or failed, stop tracking
                        await progress_tracker.stop_tracking(task_id)
                        
                except Exception:
                    # If we can't get status, assume task is dead
                    continue
            
            if active:
                user_active_tasks[user_id] = active
            else:
                del user_active_tasks[user_id]
                
        logger.debug("Cleaned up completed tasks from tracking")
        
    except Exception as e:
        logger.error(f"Error cleaning up completed tasks: {e}")