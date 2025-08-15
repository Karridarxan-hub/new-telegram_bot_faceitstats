"""Admin queue management commands and utilities."""

import logging
from typing import Dict, List, Optional, Any

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.enums import ParseMode

from queues.task_manager import get_task_manager, TaskPriority, TaskStatus
from utils.admin import AdminManager
from bot.queue_handlers import user_active_tasks, get_user_active_tasks, cleanup_completed_tasks
from bot.callbacks import get_registered_callbacks, cleanup_expired_callbacks

logger = logging.getLogger(__name__)

# Create admin queue router
admin_queue_router = Router()

# Global task manager
task_manager = get_task_manager()


@admin_queue_router.message(Command("admin_queue_status"))
async def cmd_admin_queue_status(message: Message) -> None:
    """Admin command: Get queue system status."""
    if not AdminManager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав доступа")
        return
    
    try:
        # Get queue statistics
        stats = task_manager.get_queue_stats()
        
        # Get Redis connection status
        redis_status = "🟢 Подключен" if task_manager.is_redis_available() else "🔴 Недоступен"
        
        # Build status message
        status_message = (
            "📊 <b>Статус системы очередей</b>\n\n"
            f"🔴 <b>Redis:</b> {redis_status}\n\n"
            f"📝 <b>Статистика очередей:</b>\n"
        )
        
        if "error" in stats:
            status_message += f"❌ Ошибка: {stats['error']}"
        else:
            # Queue statistics
            for queue_name, queue_stats in stats.items():
                if isinstance(queue_stats, dict):
                    total_jobs = queue_stats.get('total_jobs', 0)
                    queued_jobs = queue_stats.get('queued_jobs', 0)
                    started_jobs = queue_stats.get('started_jobs', 0)
                    finished_jobs = queue_stats.get('finished_jobs', 0)
                    failed_jobs = queue_stats.get('failed_jobs', 0)
                    
                    status_message += f"\n🔸 <b>{queue_name}:</b>\n"
                    status_message += f"  📊 Всего: {total_jobs}\n"
                    status_message += f"  ⏳ В очереди: {queued_jobs}\n"
                    status_message += f"  🔄 Выполняется: {started_jobs}\n"
                    status_message += f"  ✅ Завершено: {finished_jobs}\n"
                    status_message += f"  ❌ Ошибки: {failed_jobs}\n"
        
        # Get active users count
        active_users = len(user_active_tasks) if user_active_tasks else 0
        status_message += f"\n👥 <b>Активных пользователей:</b> {active_users}"
        
        # Create action keyboard
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_queue_refresh"),
                InlineKeyboardButton(text="📈 Метрики", callback_data="admin_queue_metrics")
            ],
            [
                InlineKeyboardButton(text="🧹 Очистить", callback_data="admin_queue_cleanup"),
                InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_queue_users")
            ]
        ])
        
        await message.answer(status_message, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        await message.answer("❌ Ошибка при получении статуса очередей")


@admin_queue_router.message(Command("admin_queue_metrics"))
async def cmd_admin_queue_metrics(message: Message) -> None:
    """Admin command: Get detailed queue metrics."""
    if not AdminManager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав доступа")
        return
    
    try:
        # Get system metrics
        metrics = task_manager.get_system_metrics()
        
        if "error" in metrics:
            await message.answer(f"❌ Ошибка получения метрик: {metrics['error']}")
            return
        
        # Format metrics message
        metrics_message = "📈 <b>Детальные метрики системы</b>\n\n"
        
        # Redis metrics
        redis_metrics = metrics.get("redis_metrics", {})
        metrics_message += "🔴 <b>Redis:</b>\n"
        metrics_message += f"• Подключения: {redis_metrics.get('connected_clients', 0)}\n"
        metrics_message += f"• Память: {redis_metrics.get('used_memory_human', '0B')}\n"
        metrics_message += f"• Команды: {redis_metrics.get('total_commands_processed', 0):,}\n"
        
        keyspace_hits = redis_metrics.get('keyspace_hits', 0)
        keyspace_misses = redis_metrics.get('keyspace_misses', 0)
        if keyspace_hits + keyspace_misses > 0:
            hit_rate = round((keyspace_hits / (keyspace_hits + keyspace_misses)) * 100, 1)
            metrics_message += f"• Hit Rate: {hit_rate}%\n"
        
        metrics_message += "\n"
        
        # Job statistics
        job_stats = metrics.get("job_statistics", {})
        metrics_message += "📊 <b>Статистика задач:</b>\n"
        metrics_message += f"• Всего задач: {job_stats.get('total_jobs', 0):,}\n"
        metrics_message += f"• В очереди: {job_stats.get('total_queued', 0)}\n"
        metrics_message += f"• Выполняется: {job_stats.get('total_started', 0)}\n"
        metrics_message += f"• Завершено: {job_stats.get('total_finished', 0):,}\n"
        metrics_message += f"• Ошибки: {job_stats.get('total_failed', 0)}\n"
        metrics_message += f"• Успешность: {job_stats.get('success_rate', 0)}%\n\n"
        
        # Task management
        task_mgmt = metrics.get("task_management", {})
        metrics_message += "🎯 <b>Управление задачами:</b>\n"
        metrics_message += f"• Отслеживается: {task_mgmt.get('active_tasks_tracked', 0)}\n"
        metrics_message += f"• Запланировано: {task_mgmt.get('scheduled_tasks', 0)}\n"
        metrics_message += f"• Активно: {task_mgmt.get('enabled_scheduled_tasks', 0)}\n\n"
        
        await message.answer(metrics_message, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error getting queue metrics: {e}")
        await message.answer("❌ Ошибка при получении метрик очередей")