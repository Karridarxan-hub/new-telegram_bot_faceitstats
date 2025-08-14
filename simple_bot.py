#!/usr/bin/env python3
"""Simple FACEIT Bot without queue system for testing."""

import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config.settings import settings, validate_settings
from faceit.api import FaceitAPI
from utils.storage import storage, UserData, SubscriptionTier
from utils.formatter import MessageFormatter

# Setup logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create router
router = Router()

# Initialize FACEIT API
faceit_api = FaceitAPI()

# States for conversation flow
class ProfileStates(StatesGroup):
    waiting_nickname = State()


def get_main_menu():
    """Get main menu keyboard."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Моя статистика"), KeyboardButton(text="🎮 Последний матч")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🔍 Найти игрока")],
            [KeyboardButton(text="⚔️ Анализ матча"), KeyboardButton(text="💎 Подписка")],
            [KeyboardButton(text="ℹ️ Помощь"), KeyboardButton(text="⚡ Быстрый поиск")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command."""
    logger.info(f"Start command from user {message.from_user.id}")
    
    # Check if user already has account linked
    user = await storage.get_user(message.from_user.id)
    
    welcome_text = """🎮 <b>FACEIT Telegram Bot</b>

Добро пожаловать! Я помогу вам анализировать FACEIT матчи и отслеживать статистику игроков.

<b>🚀 Основные возможности:</b>
📊 Детальная статистика игроков
⚔️ Анализ матчей с рекомендациями  
📈 Отслеживание прогресса
🎯 Анализ уровня противников
💎 Premium функции

<b>💡 Быстрый старт:</b>
• Используйте кнопки меню ниже
• Или просто напишите FACEIT никнейм для поиска

<b>📋 Команды:</b>
/profile никнейм - профиль игрока
/link никнейм - привязать аккаунт
/stats - моя статистика  
/help - подробная помощь"""
    
    if user and user.faceit_nickname:
        welcome_text += f"\n\n✅ <b>Привязанный аккаунт:</b> {user.faceit_nickname}"
        # Show main menu
        await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())
    else:
        welcome_text += "\n\n🎯 <b>Напишите FACEIT никнейм для быстрого поиска:</b>"
        await message.answer(welcome_text, parse_mode=ParseMode.HTML)
        await state.set_state(ProfileStates.waiting_nickname)


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    """Profile command handler."""
    logger.info(f"Profile command from user {message.from_user.id}")
    
    # Extract nickname from command
    args = message.text.split()[1:] if message.text else []
    if not args:
        await message.answer("Использование: /profile <nickname>\n\nПример: /profile s1mple")
        return
    
    nickname = args[0]
    
    try:
        await message.answer("🔍 Ищу игрока...")
        
        # Search for player
        player = await faceit_api.search_player(nickname)
        
        if not player:
            await message.answer(f"❌ Игрок <b>{nickname}</b> не найден", parse_mode=ParseMode.HTML)
            return
        
        # Format player info
        profile_text = MessageFormatter.format_player_info(player)
        
        await message.answer(profile_text, parse_mode=ParseMode.HTML)
        logger.info(f"Profile shown for player {player.nickname}")
        
    except Exception as e:
        logger.error(f"Error in profile command: {e}")
        await message.answer("❌ Произошла ошибка при получении профиля игрока")


@router.message(Command("link"))
async def cmd_link(message: Message):
    """Link FACEIT account command."""
    logger.info(f"Link command from user {message.from_user.id}")
    
    # Extract nickname from command
    args = message.text.split()[1:] if message.text else []
    if not args:
        await message.answer("Использование: /link <nickname>\n\nПример: /link s1mple")
        return
    
    nickname = args[0]
    
    try:
        await message.answer("🔍 Проверяю игрока...")
        
        # Search for player
        player = await faceit_api.search_player(nickname)
        
        if not player:
            await message.answer(f"❌ Игрок <b>{nickname}</b> не найден", parse_mode=ParseMode.HTML)
            return
        user_id = message.from_user.id
        
        # Store user data
        user_data = {
            "telegram_id": user_id,
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "faceit_player_id": player.player_id,
            "faceit_nickname": player.nickname,
            "linked_at": datetime.now().isoformat()
        }
        
        await storage.store_user_data(user_id, user_data)
        
        await message.answer(
            f"✅ <b>Аккаунт привязан!</b>\n\n"
            f"🎮 FACEIT: <b>{player.nickname}</b>\n"
            f"📊 Уровень: <b>{getattr(player, 'skill_level', 'N/A')}</b>\n\n"
            f"Теперь вы можете использовать /stats для просмотра статистики",
            parse_mode=ParseMode.HTML
        )
        logger.info(f"User {user_id} linked to FACEIT player {player.nickname}")
        
    except Exception as e:
        logger.error(f"Error in link command: {e}")
        await message.answer("❌ Произошла ошибка при привязке аккаунта")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Stats command handler."""
    logger.info(f"Stats command from user {message.from_user.id}")
    
    try:
        user_id = message.from_user.id
        user = await storage.get_user(user_id)
        
        if not user or not user.faceit_player_id:
            await message.answer(
                "❌ Сначала привяжите FACEIT аккаунт командой /link <nickname>"
            )
            return
        
        await message.answer("📊 Получаю вашу статистику...")
        
        # Get player details
        player = await faceit_api.get_player_by_id(user.faceit_player_id)
        
        if not player:
            await message.answer("❌ Ошибка получения статистики")
            return
        
        # Format stats
        stats_text = MessageFormatter.format_player_info(player)
        
        await message.answer(stats_text, parse_mode=ParseMode.HTML)
        logger.info(f"Stats shown for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        await message.answer("❌ Произошла ошибка при получении статистики")


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Help command handler."""
    help_text = """🤖 <b>FACEIT Telegram Bot - Полное руководство</b>

<b>🚀 Основные команды:</b>
/start - Главное меню и быстрый поиск
/profile никнейм - Профиль любого игрока
/link никнейм - Привязать FACEIT аккаунт
/stats - Ваша статистика (после привязки)
/help - Это руководство

<b>🎮 Кнопки меню:</b>
📊 <b>Моя статистика</b> - ваши показатели
👤 <b>Профиль</b> - ваш привязанный профиль
🔍 <b>Найти игрока</b> - поиск по никнейму
⚔️ <b>Анализ матча</b> - анализ матчей (в разработке)
💎 <b>Подписка</b> - управление подпиской
ℹ️ <b>Помощь</b> - это меню

<b>⚡ Быстрый поиск:</b>
• После /start просто напишите никнейм
• Или используйте кнопку "🔍 Найти игрока"
• Пример: напишите "s1mple" для поиска

<b>🔗 Привязка аккаунта:</b>
1. Используйте /link никнейм
2. Или найдите игрока и нажмите кнопку привязки
3. После привязки доступна кнопка "📊 Моя статистика"

<b>📊 Что показывает бот:</b>
• Детальная статистика CS2
• Уровень навыка и ELO
• Информация о стране игрока
• История игр (в разработке)

<b>🚧 В разработке:</b>
• Анализ матчей с рекомендациями
• Отслеживание прогресса
• Premium подписки
• Уведомления о новых матчах

<b>💡 Советы:</b>
• Используйте кнопки для удобства
• Все функции бесплатны
• Данные обновляются в реальном времени"""
    
    await message.answer(help_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())


@router.message(ProfileStates.waiting_nickname)
async def process_nickname(message: Message, state: FSMContext):
    """Process nickname after /start command."""
    nickname = message.text.strip()
    logger.info(f"Processing nickname '{nickname}' from user {message.from_user.id}")
    
    if not nickname:
        await message.answer("❌ Пожалуйста, введите корректный никнейм:")
        return
    
    try:
        await message.answer("🔍 Ищу игрока...")
        
        # Search for player
        player = await faceit_api.search_player(nickname)
        
        if not player:
            await message.answer(
                f"❌ Игрок <b>{nickname}</b> не найден\n\n"
                f"💡 Попробуйте:\n"
                f"• Проверить правильность написания\n"
                f"• Написать полный никнейм\n"
                f"• Написать другой никнейм\n\n"
                f"Или используйте команды:\n"
                f"/profile никнейм - поиск профиля\n"
                f"/help - помощь",
                parse_mode=ParseMode.HTML
            )
            await state.clear()
            return
        
        # Format player info
        profile_text = MessageFormatter.format_player_info(player)
        
        # Create action buttons
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=f"🔗 Привязать {nickname}", callback_data=f"link_{nickname}"),
                InlineKeyboardButton(text="🔍 Найти другого", callback_data="search_another")
            ],
            [
                InlineKeyboardButton(text="📊 Моя статистика", callback_data="my_stats"),
                InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")
            ]
        ])
        
        profile_text += f"\n\n💡 <b>Выберите действие:</b>"
        
        await message.answer(profile_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        await state.clear()
        
        logger.info(f"Profile shown for player {player.nickname}")
        
    except Exception as e:
        logger.error(f"Error processing nickname: {e}")
        await message.answer(
            "❌ Произошла ошибка при поиске игрока\n\n"
            "Попробуйте еще раз или используйте /help для помощи"
        )
        await state.clear()


# Button handlers
@router.message(F.text == "📊 Моя статистика")
async def btn_my_stats(message: Message):
    """Handle 'My Stats' button."""
    await cmd_stats(message)


@router.message(F.text == "👤 Профиль")  
async def btn_profile(message: Message, state: FSMContext):
    """Handle 'Profile' button."""
    user = await storage.get_user(message.from_user.id)
    
    if user and user.faceit_nickname:
        # Show linked account profile
        try:
            player = await faceit_api.get_player_by_id(user.faceit_player_id)
            if player:
                profile_text = MessageFormatter.format_player_info(player)
                await message.answer(profile_text, parse_mode=ParseMode.HTML)
            else:
                await message.answer("❌ Ошибка получения профиля")
        except Exception as e:
            logger.error(f"Error getting profile: {e}")
            await message.answer("❌ Ошибка получения профиля")
    else:
        await message.answer(
            "❌ Аккаунт не привязан\n\n"
            "Используйте /link никнейм для привязки аккаунта"
        )


@router.message(F.text == "🔍 Найти игрока")
async def btn_find_player(message: Message, state: FSMContext):
    """Handle 'Find Player' button."""
    await message.answer("🔍 <b>Поиск игрока</b>\n\nНапишите FACEIT никнейм:", parse_mode=ParseMode.HTML)
    await state.set_state(ProfileStates.waiting_nickname)


@router.message(F.text == "⚡ Быстрый поиск")
async def btn_quick_search(message: Message, state: FSMContext):
    """Handle 'Quick Search' button."""
    await btn_find_player(message, state)


@router.message(F.text == "⚔️ Анализ матча")
async def btn_match_analysis(message: Message):
    """Handle 'Match Analysis' button."""
    await message.answer(
        "⚔️ <b>Анализ матча</b>\n\n"
        "🚧 Функция временно недоступна\n"
        "Анализ матчей находится в разработке.\n\n"
        "💡 Пока что вы можете:\n"
        "• Посмотреть статистику игроков\n"
        "• Найти профиль любого игрока\n"
        "• Привязать свой аккаунт для отслеживания",
        parse_mode=ParseMode.HTML
    )


@router.message(F.text == "💎 Подписка")
async def btn_subscription(message: Message):
    """Handle 'Subscription' button."""
    user = await storage.get_user(message.from_user.id)
    
    if user and user.subscription:
        tier = user.subscription.tier
        if tier == SubscriptionTier.FREE:
            status_text = "🆓 Бесплатная"
        elif tier == SubscriptionTier.PREMIUM:
            status_text = "💎 Premium"  
        elif tier == SubscriptionTier.PRO:
            status_text = "👑 Pro"
        else:
            status_text = "🆓 Бесплатная"
            
        await message.answer(
            f"💎 <b>Ваша подписка</b>\n\n"
            f"📋 Текущий план: {status_text}\n"
            f"📊 Использовано запросов: {user.subscription.requests_used}/{user.subscription.requests_limit}\n\n"
            f"🚧 Управление подпиской временно недоступно",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.answer(
            "💎 <b>Подписка</b>\n\n"
            "🆓 У вас бесплатный план\n"
            "🚧 Управление подпиской временно недоступно",
            parse_mode=ParseMode.HTML
        )


@router.message(F.text == "ℹ️ Помощь")
async def btn_help(message: Message):
    """Handle 'Help' button."""
    await cmd_help(message)


# Callback handlers for inline keyboard buttons
@router.callback_query(F.data.startswith("link_"))
async def callback_link_account(callback: CallbackQuery):
    """Handle account linking callback."""
    await callback.answer()
    
    nickname = callback.data.replace("link_", "")
    
    try:
        await callback.message.edit_text("🔍 Проверяю игрока...")
        
        # Search for player
        player = await faceit_api.search_player(nickname)
        
        if not player:
            await callback.message.edit_text(
                f"❌ Игрок <b>{nickname}</b> не найден",
                parse_mode=ParseMode.HTML
            )
            return
        
        user_id = callback.from_user.id
        
        # Store user data
        user_data = {
            "telegram_id": user_id,
            "username": callback.from_user.username,
            "first_name": callback.from_user.first_name,
            "faceit_player_id": player.player_id,
            "faceit_nickname": player.nickname,
            "linked_at": datetime.now().isoformat()
        }
        
        await storage.store_user_data(user_id, user_data)
        
        await callback.message.edit_text(
            f"✅ <b>Аккаунт привязан!</b>\n\n"
            f"🎮 FACEIT: <b>{player.nickname}</b>\n"
            f"📊 Уровень: <b>{getattr(player, 'skill_level', 'N/A')}</b>\n\n"
            f"Теперь вы можете использовать кнопку \"📊 Моя статистика\"",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu()
        )
        logger.info(f"User {user_id} linked to FACEIT player {player.nickname}")
        
    except Exception as e:
        logger.error(f"Error in link callback: {e}")
        await callback.message.edit_text("❌ Произошла ошибка при привязке аккаунта")


@router.callback_query(F.data == "search_another")
async def callback_search_another(callback: CallbackQuery, state: FSMContext):
    """Handle search another player callback."""
    await callback.answer()
    
    await callback.message.edit_text(
        "🔍 <b>Поиск игрока</b>\n\nНапишите FACEIT никнейм:",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(ProfileStates.waiting_nickname)


@router.callback_query(F.data == "my_stats")
async def callback_my_stats(callback: CallbackQuery):
    """Handle my stats callback."""
    await callback.answer()
    
    try:
        user_id = callback.from_user.id
        user = await storage.get_user(user_id)
        
        if not user or not user.faceit_player_id:
            await callback.message.edit_text(
                "❌ Сначала привяжите FACEIT аккаунт\n\n"
                "Используйте /link никнейм для привязки аккаунта",
                parse_mode=ParseMode.HTML
            )
            return
        
        await callback.message.edit_text("📊 Получаю вашу статистику...")
        
        # Get player details
        player = await faceit_api.get_player_by_id(user.faceit_player_id)
        
        if not player:
            await callback.message.edit_text("❌ Ошибка получения статистики")
            return
        
        # Format stats
        stats_text = MessageFormatter.format_player_info(player)
        
        await callback.message.edit_text(stats_text, parse_mode=ParseMode.HTML)
        logger.info(f"Stats shown for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error in stats callback: {e}")
        await callback.message.edit_text("❌ Произошла ошибка при получении статистики")


@router.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery):
    """Handle help callback."""
    await callback.answer()
    
    help_text = """🤖 <b>FACEIT Telegram Bot</b>

<b>🚀 Основные команды:</b>
/start - Главное меню и быстрый поиск
/profile никнейм - Профиль любого игрока
/link никнейм - Привязать FACEIT аккаунт
/stats - Ваша статистика (после привязки)
/help - Подробная помощь

<b>⚡ Быстрый поиск:</b>
• После /start просто напишите никнейм
• Или используйте кнопку "🔍 Найти игрока"

<b>🔗 Привязка аккаунта:</b>
• Найдите игрока и нажмите кнопку привязки
• После привязки доступна кнопка "📊 Моя статистика"

<b>💡 Советы:</b>
• Используйте кнопки меню для удобства
• Все функции бесплатны"""
    
    await callback.message.edit_text(
        help_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Найти игрока", callback_data="search_another")],
            [InlineKeyboardButton(text="📊 Моя статистика", callback_data="my_stats")]
        ])
    )


@router.message()
async def handle_messages(message: Message):
    """Handle all other messages."""
    text = message.text
    
    if not text:
        return
    
    # Check if message contains FACEIT match URL
    if "faceit.com" in text and "/room/" in text:
        await message.answer(
            "🔍 Обнаружена ссылка на матч FACEIT!\n\n"
            "🚧 <b>Анализ матчей временно недоступен</b>\n"
            "Функция находится в разработке. Пожалуйста, попробуйте позже.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Default response for unrecognized messages
    await message.answer(
        "🤔 Я вас не понимаю.\n\n"
        "💡 <b>Используйте:</b>\n"
        "• Кнопки меню ниже\n"
        "• /help - подробная помощь\n"
        "• /profile никнейм - поиск игрока\n\n"
        "Или отправьте ссылку на матч FACEIT для анализа.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu()
    )


async def main():
    """Main function."""
    try:
        # Validate settings
        logger.info("Validating settings...")
        validate_settings()
        
        # Create bot instance
        logger.info("Creating bot instance...")
        default_properties = DefaultBotProperties(parse_mode=ParseMode.HTML)
        bot = Bot(token=settings.telegram_bot_token, default=default_properties)
        
        # Create dispatcher with FSM storage
        dp = Dispatcher(storage=MemoryStorage())
        dp.include_router(router)
        
        # Test bot token
        me = await bot.get_me()
        logger.info(f"Bot @{me.username} started successfully!")
        logger.info(f"Bot ID: {me.id}")
        logger.info(f"Bot Name: {me.first_name}")
        
        # Start polling
        logger.info("Starting polling...")
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise
    finally:
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())