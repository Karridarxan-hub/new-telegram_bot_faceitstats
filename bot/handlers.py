"""Bot command handlers."""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode

from faceit.api import FaceitAPI, FaceitAPIError
from utils.storage import storage, UserData
from utils.formatter import MessageFormatter
from utils.admin import AdminManager
from utils.match_analyzer import MatchAnalyzer, format_match_analysis
from queues.task_manager import get_task_manager, TaskPriority
from bot.queue_handlers import handle_background_task_request
from bot.progress import send_progress_message, create_progress_keyboard
from utils.cache import get_cache_stats, clear_all_caches
from config.version import get_version, get_build_info
from utils.cs2_advanced_formatter import format_cs2_advanced_stats, format_weapon_stats, format_map_specific_progress
from utils.formatter_addon import format_player_playstyle

logger = logging.getLogger(__name__)

router = Router()
faceit_api = FaceitAPI()


# Global match analyzer
match_analyzer = MatchAnalyzer(faceit_api)

# Global task manager
task_manager = get_task_manager()


def get_main_menu():
    """Get main menu keyboard."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Моя статистика"), KeyboardButton(text="🎮 Последний матч")],
            [KeyboardButton(text="📋 История матчей"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="📈 Анализ формы"), KeyboardButton(text="🔍 Найти игрока")],
            [KeyboardButton(text="⚔️ Анализ матча"), KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard


def get_stats_menu():
    """Get statistics menu with subdivisions."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Общая статистика", callback_data="stats_general"),
            InlineKeyboardButton(text="📈 Детальная статистика", callback_data="stats_detailed")
        ],
        [
            InlineKeyboardButton(text="🗺️ Карты", callback_data="stats_maps"),
            InlineKeyboardButton(text="🔫 Оружие", callback_data="stats_weapons")
        ],
        [
            InlineKeyboardButton(text="🎮 Матчи (10)", callback_data="stats_10"),
            InlineKeyboardButton(text="🔥 Матчи (30)", callback_data="stats_30")
        ],
        [
            InlineKeyboardButton(text="📅 Матчи (60)", callback_data="stats_60"),
            InlineKeyboardButton(text="🎪 Сессии", callback_data="stats_sessions")
        ],
        [
            InlineKeyboardButton(text="🎯 Стиль игры", callback_data="stats_playstyle")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")
        ]
    ])
    return keyboard

def get_analysis_menu():
    """Get analysis period selection menu."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 20 матчей", callback_data="analysis_10"),
                InlineKeyboardButton(text="📈 60 матчей", callback_data="analysis_30")
            ],
            [
                InlineKeyboardButton(text="📉 100 матчей", callback_data="analysis_60"), 
                InlineKeyboardButton(text="🎮 Статистика по сессиям", callback_data="sessions_analysis")
            ],
            [
                InlineKeyboardButton(text="🗺 Анализ карт", callback_data="maps_analysis"),
                InlineKeyboardButton(text="⚡ Быстрый обзор", callback_data="today_summary")
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ]
    )
    return keyboard


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Handle /start command."""
    # Check if user already has account linked
    user = await storage.get_user(message.from_user.id)
    
    if user and user.faceit_player_id:
        # User already linked, show main menu
        welcome_text = f"""
<b>🎮 Добро пожаловать обратно!</b>

Привязанный аккаунт: <b>{user.faceit_nickname}</b>

Используйте меню ниже для просмотра статистики и анализа матчей.
"""
        await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())
    else:
        # New user, ask for nickname
        welcome_text = """
<b>🎮 Добро пожаловать в FACEIT Stats Bot!</b>

Этот бот поможет вам отслеживать статистику ваших матчей в CS2 на платформе FACEIT.

<b>Напишите ваш никнейм в FACEIT:</b>
"""
        
        # Set user state to waiting for nickname
        if not user:
            user = UserData(user_id=message.from_user.id)
        user.waiting_for_nickname = True
        await storage.save_user(user)
        
        await message.answer(welcome_text, parse_mode=ParseMode.HTML)


@router.message(F.text == "🔍 Найти игрока")
async def menu_find_player(message: Message) -> None:
    """Handle find player menu."""
    user = await storage.get_user(message.from_user.id)
    
    # Set user state to waiting for nickname
    if not user:
        user = UserData(user_id=message.from_user.id)
    user.waiting_for_nickname = True
    await storage.save_user(user)
    
    await message.answer(
        "🔍 <b>Поиск игрока</b>\n\nВведите никнейм игрока в FACEIT для привязки к вашему аккаунту:\n\nПример: <code>s1mple</code>",
        parse_mode=ParseMode.HTML
    )


@router.message(F.text == "👤 Профиль")
async def menu_profile(message: Message) -> None:
    """Handle profile menu."""
    await cmd_profile(message)


@router.message(F.text == "📊 Моя статистика")
async def menu_stats(message: Message) -> None:
    """Handle stats menu."""
    await cmd_stats(message)


@router.message(F.text == "🎮 Последний матч")
async def menu_last_match(message: Message) -> None:
    """Handle last match menu."""
    await cmd_last_match(message)


@router.message(F.text == "📋 История матчей")
async def menu_matches(message: Message) -> None:
    """Handle matches history menu."""
    await cmd_matches(message)


@router.message(F.text == "ℹ️ Помощь")
async def menu_help(message: Message) -> None:
    """Handle help menu."""
    await cmd_help(message)


@router.message(F.text == "📈 Анализ формы")
async def menu_analysis(message: Message) -> None:
    """Handle analysis menu."""
    user = await storage.get_user(message.from_user.id)
    if not user or not user.faceit_player_id:
        await message.answer(
            "❌ Сначала привяжите свой FACEIT аккаунт командой /setplayer\n\nИли нажмите \"🔍 Найти игрока\" в меню.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu()
        )
        return
    
    await message.answer(
        "📈 <b>Анализ формы</b>\n\nВыберите период для анализа:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_analysis_menu()
    )


@router.message(F.text == "⚔️ Анализ матча")
async def menu_match_analysis(message: Message) -> None:
    """Handle match analysis menu."""
    await message.answer(
        "⚔️ <b>Анализ матча перед игрой</b>\n\n"
        "Отправьте ссылку на матч FACEIT для получения подробного анализа противников:\n\n"
        "📋 <b>Что вы получите:</b>\n"
        "• 💀 Анализ опасных игроков\n"
        "• 🎯 Слабые места противников\n"
        "• 📊 Статистика и форма игроков\n"
        "• 💡 Тактические рекомендации\n"
        "• ⚡ Анализ ролей (AWP/Rifle/Support)\n\n"
        "Пример ссылки:\n"
        "<code>https://www.faceit.com/en/cs2/room/1-abc-def-ghi</code>\n\n"
        "Или используйте команду: <code>/analyze [ссылка]</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu()
    )




@router.message(Command("setplayer"))
async def cmd_set_player(message: Message) -> None:
    """Handle /setplayer command."""
    if not message.text:
        return
        
    args = message.text.split()[1:]
    if not args:
        await message.answer(
            "Укажите ваш никнеим в FACEIT.\n"
            "Пример: <code>/setplayer YourNickname</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    nickname = " ".join(args).strip()
    await message.answer(f"🔍 Ищу игрока {nickname}...", parse_mode=ParseMode.HTML)
    
    try:
        player = await faceit_api.search_player(nickname)
        if not player:
            await message.answer(
                f"❌ Игрок с никнеймом \"{nickname}\" не найден. "
                "Проверьте правильность написания.",
                parse_mode=ParseMode.HTML
            )
            return
        
        user_data = UserData(
            user_id=message.from_user.id,
            faceit_player_id=player.player_id,
            faceit_nickname=player.nickname
        )
        await storage.save_user(user_data)
        
        player_info = MessageFormatter.format_player_info(player, None, None)
        success_text = f"✅ Игрок успешно привязан!\n\n{player_info}"
        
        await message.answer(success_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())
        logger.info(f"User {message.from_user.id} linked player {player.nickname}")
        
    except FaceitAPIError as e:
        logger.error(f"FACEIT API error in set_player: {e}")
        await message.answer(
            "❌ Произошла ошибка при поиске игрока. Попробуйте позже.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Unexpected error in set_player: {e}")
        await message.answer(
            "❌ Произошла непредвиденная ошибка.",
            parse_mode=ParseMode.HTML
        )


# Handle text that looks like a nickname (for when user just types nickname)
@router.message(F.text.regexp(r'^[a-zA-Z0-9_-]{3,16}$'))
async def handle_nickname_input(message: Message) -> None:
    """Handle nickname input without command."""
    user = await storage.get_user(message.from_user.id)
    
    # Check if user is waiting for nickname or doesn't have linked account
    if (user and user.waiting_for_nickname) or (not user or not user.faceit_player_id):
        nickname = message.text.strip()
        await message.answer(f"🔍 Ищу игрока {nickname}...", parse_mode=ParseMode.HTML)
        
        try:
            player = await faceit_api.search_player(nickname)
            if not player:
                await message.answer(
                    f"❌ Игрок с никнеймом \"{nickname}\" не найден.\n\n"
                    f"Попробуйте:\n"
                    f"• Проверить написание\n"
                    f"• Использовать команду: <code>/setplayer {nickname}</code>",
                    parse_mode=ParseMode.HTML
                )
                return
            
            # Create or update user data
            if not user:
                user = UserData(user_id=message.from_user.id)
            
            user.faceit_player_id = player.player_id
            user.faceit_nickname = player.nickname
            user.waiting_for_nickname = False
            await storage.save_user(user)
            
            player_info = MessageFormatter.format_player_info(player, None, None)
            success_text = f"✅ Игрок успешно привязан!\n\n{player_info}"
            
            await message.answer(success_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())
            logger.info(f"User {message.from_user.id} linked player {player.nickname}")
            
        except FaceitAPIError as e:
            logger.error(f"FACEIT API error in nickname_input: {e}")
            await message.answer(
                "❌ Произошла ошибка при поиске игрока. Попробуйте позже.",
                parse_mode=ParseMode.HTML
            )


@router.message(Command("lastmatch"))
async def cmd_last_match(message: Message) -> None:
    """Handle /lastmatch command."""
    user = await storage.get_user(message.from_user.id)
    if not user or not user.faceit_player_id:
        await message.answer(
            "❌ Сначала привяжите свой FACEIT аккаунт командой /setplayer\n\nИли нажмите \"🔍 Найти игрока\" в меню.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu()
        )
        return
    
    await message.answer(
        "🔍 Получаю данные о последнем матче...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        matches = await faceit_api.get_player_matches(user.faceit_player_id, limit=1)
        if not matches:
            await message.answer(
                "❌ Матчи не найдены.",
                parse_mode=ParseMode.HTML
            )
            return
        
        match = matches[0]
        logger.info(f"Match status: '{match.status}' for match {match.match_id}")
        if match.status.upper() != "FINISHED":
            await message.answer(
                f"⏳ Последний матч еще не завершен (статус: {match.status}).",
                parse_mode=ParseMode.HTML
            )
            return
        
        stats = await faceit_api.get_match_stats(match.match_id)
        formatted_message = MessageFormatter.format_match_result(
            match, stats, user.faceit_player_id
        )
        
        await message.answer(formatted_message, parse_mode=ParseMode.HTML)
        logger.info(f"Sent last match info to user {message.from_user.id}")
        
    except FaceitAPIError as e:
        logger.error(f"FACEIT API error in last_match: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении данных матча.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Unexpected error in last_match: {e}")
        await message.answer(
            "❌ Произошла непредвиденная ошибка.",
            parse_mode=ParseMode.HTML
        )


@router.message(Command("matches"))
async def cmd_matches(message: Message) -> None:
    """Handle /matches command."""
    user = await storage.get_user(message.from_user.id)
    if not user or not user.faceit_player_id:
        await message.answer(
            "❌ Сначала привяжите свой FACEIT аккаунт командой /setplayer\n\nИли нажмите \"🔍 Найти игрока\" в меню.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu()
        )
        return
    
    # Parse limit from command
    limit = 5
    if message.text:
        args = message.text.split()[1:]
        if args and args[0].isdigit():
            limit = min(int(args[0]), 20)
    
    await message.answer(
        f"🔍 Получаю данные о последних {limit} матчах...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        matches = await faceit_api.get_player_matches(user.faceit_player_id, limit=limit)
        finished_matches = [match for match in matches if match.status.upper() == "FINISHED"]
        
        if not finished_matches:
            await message.answer(
                "❌ Завершенные матчи не найдены.",
                parse_mode=ParseMode.HTML
            )
            return
        
        formatted_message = MessageFormatter.format_matches_list(
            finished_matches, user.faceit_player_id
        )
        
        await message.answer(formatted_message, parse_mode=ParseMode.HTML)
        logger.info(f"Sent matches list to user {message.from_user.id}")
        
    except FaceitAPIError as e:
        logger.error(f"FACEIT API error in matches: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении данных матчей.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Unexpected error in matches: {e}")
        await message.answer(
            "❌ Произошла непредвиденная ошибка.",
            parse_mode=ParseMode.HTML
        )


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    """Handle /profile command."""
    user = await storage.get_user(message.from_user.id)
    if not user or not user.faceit_player_id:
        await message.answer(
            "❌ Сначала привяжите свой FACEIT аккаунт командой /setplayer\n\nИли нажмите \"🔍 Найти игрока\" в меню.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu()
        )
        return
    
    await message.answer(
        "🔍 Получаю информацию о профиле...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        player = await faceit_api.get_player_by_id(user.faceit_player_id)
        if not player:
            await message.answer(
                "❌ Не удалось получить информацию о профиле.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Get player statistics and recent matches for streaks calculation
        player_stats = await faceit_api.get_player_stats(user.faceit_player_id)
        recent_matches = await faceit_api.get_player_matches(user.faceit_player_id, limit=100)
        
        formatted_message = MessageFormatter.format_player_info(player, player_stats, recent_matches)
        await message.answer(formatted_message, parse_mode=ParseMode.HTML)
        logger.info(f"Sent profile info to user {message.from_user.id}")
        
    except FaceitAPIError as e:
        logger.error(f"FACEIT API error in profile: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении информации о профиле.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Unexpected error in profile: {e}")
        await message.answer(
            "❌ Произошла непредвиденная ошибка.",
            parse_mode=ParseMode.HTML
        )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Handle /stats command - show statistics menu."""
    user = await storage.get_user(message.from_user.id)
    if not user or not user.faceit_player_id:
        await message.answer(
            "❌ <b>Для просмотра статистики нужно привязать аккаунт</b>\n\n"
            "Используйте команду /setplayer или нажмите \"🔍 Найти игрока\"",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu()
        )
        return
    
    await message.answer(
        f"📊 <b>Статистика игрока {user.faceit_nickname}</b>\n\n"
        "Выберите тип статистики:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_stats_menu()
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command."""
    help_text = """
<b>🎮 FACEIT Stats Bot - Справка</b>

<b>📋 Основные команды:</b>

/start - начать работу с ботом
/setplayer &lt;nickname&gt; - привязать FACEIT аккаунт  
/profile - информация о профиле + базовая статистика
/stats - детальная статистика игрока
/lastmatch - последний матч с подробностями
/matches [число] - список последних матчей (макс. 20)
/analyze &lt;ссылка&gt; - анализ матча перед игрой
/today - быстрый обзор за последние матчи
/my_tasks - показать активные задачи анализа
/cancel_task &lt;id&gt; - отменить задачу
/version - версия бота и информация о системе
/help - показать эту справку

<b>💎 Подписки и лимиты:</b>

<b>🆓 FREE (бесплатно):</b>
• 10 запросов в день
• История до 20 матчей
• Базовая аналитика
• Уведомления

<b>⭐ PREMIUM (199 ⭐/мес):</b>
• 100 запросов в день
• История до 50 матчей
• Продвинутая аналитика
• API доступ

<b>🚀 PRO (299 ⭐/мес):</b>
• Неограниченные запросы
• История до 200 матчей
• Полная аналитика
• Приоритетная поддержка

<b>⚡ Возможности бота:</b>
• Анализ статистики игроков CS2
• Предматчевый анализ противников
• Анализ карт и стиля игры
• Отслеживание формы и прогресса
• Фоновая обработка запросов

<b>💡 Примеры использования:</b>
<code>/setplayer s1mple</code>
<code>/stats</code> - полная статистика
<code>/matches 10</code> - последние 10 матчей
<code>/analyze https://faceit.com/en/cs2/room/1-abc-def</code>

Также можете просто написать никнейм игрока или вставить ссылку на матч FACEIT для автоматического анализа.

<b>🔧 Управление задачами:</b>
• /my_tasks - активные задачи анализа
• Кнопки отмены в сообщениях прогресса
• /cancel_task &lt;id&gt; - отменить конкретную задачу

<b>🆘 Поддержка:</b> Если есть вопросы, обратитесь к разработчику.
"""
    
    # Create help keyboard with back button
    help_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к главному меню", callback_data="back_to_menu")]
        ]
    )
    
    await message.answer(help_text, parse_mode=ParseMode.HTML, reply_markup=help_keyboard)


@router.message(Command("version"))
async def cmd_version(message: Message) -> None:
    """Handle /version command."""
    build_info = get_build_info()
    version = get_version()
    
    version_text = f"""
<b>🤖 {build_info['name']}</b>

<b>📦 Версия:</b> <code>{version}</code>
<b>📝 Описание:</b> {build_info['description']}
<b>👨‍💻 Автор:</b> {build_info['author']}

<b>🔧 Техническая информация:</b>
• <b>Python:</b> {build_info['python_version']}
• <b>Docker:</b> {'✅ Поддерживается' if build_info['docker_ready'] else '❌ Не поддерживается'}
• <b>Архитектура:</b> Микросервисная
• <b>API:</b> FACEIT Data API v4

<b>⚡ Возможности:</b>
• Анализ статистики игроков CS2
• Предматчевый анализ
• Автоматический мониторинг матчей
• Полностью бесплатные функции

<b>🏗️ Компоненты:</b>
• Bot Engine: aiogram 3.x
• Cache System: Multi-level caching
• Analytics: HLTV 2.1 Rating
• Performance: 4x faster analysis

<i>🚀 Готов к продакшену!</i>
"""
    
    await message.answer(version_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())




@router.message(Command("analyze"))
async def cmd_analyze(message: Message) -> None:
    """Handle /analyze command."""
    if not message.text:
        await message.answer(
            "⚔️ <b>Анализ матча</b>\n\n"
            "Укажите ссылку на матч FACEIT:\n"
            "<code>/analyze https://www.faceit.com/en/cs2/room/1-abc-def-ghi</code>",
            parse_mode=ParseMode.HTML
        )
        return
        
    args = message.text.split()[1:]
    if not args:
        await message.answer(
            "⚔️ <b>Анализ матча</b>\n\n"
            "Укажите ссылку на матч FACEIT:\n"
            "<code>/analyze https://www.faceit.com/en/cs2/room/1-abc-def-ghi</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    match_url = args[0]
    await analyze_match_from_url(message, match_url)


async def analyze_match_from_url(message: Message, match_url: str) -> None:
    """Analyze match from URL."""
    await message.answer(
        "🔍 <b>Анализирую матч...</b>\n\n"
        "⏳ Получаю данные игроков и статистику...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Analyze the match
        analysis_result = await match_analyzer.analyze_match(match_url)
        
        # Format and send result
        formatted_message = format_match_analysis(analysis_result)
        
        # Split long message if needed
        if len(formatted_message) > 4096:
            # Split into multiple messages
            parts = []
            current_part = ""
            lines = formatted_message.split('\n')
            
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
            
            # Send all parts
            for i, part in enumerate(parts):
                if i == 0:
                    await message.answer(part, parse_mode=ParseMode.HTML)
                else:
                    await message.answer(
                        f"<b>Продолжение анализа...</b>\n\n{part}",
                        parse_mode=ParseMode.HTML
                    )
        else:
            await message.answer(formatted_message, parse_mode=ParseMode.HTML)
        
        logger.info(f"Match analysis completed for user {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error in match analysis: {e}")
        await message.answer(
            "❌ <b>Ошибка при анализе матча</b>\n\n"
            "Возможные причины:\n"
            "• Неверная ссылка на матч\n"
            "• Матч уже завершён\n"
            "• Временные проблемы с API FACEIT\n\n"
            "Попробуйте ещё раз или обратитесь в поддержку.",
            parse_mode=ParseMode.HTML
        )


@router.message(Command("today"))
async def cmd_today(message: Message) -> None:
    """Handle /today command for quick daily overview."""
    user = await storage.get_user(message.from_user.id)
    if not user or not user.faceit_player_id:
        await message.answer(
            "❌ Сначала привяжите свой FACEIT аккаунт командой /setplayer\n\nИли нажмите \"🔍 Найти игрока\" в меню.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu()
        )
        return
    
    await message.answer(
        "⚡ Получаю быстрый обзор за сегодня...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        player = await faceit_api.get_player_by_id(user.faceit_player_id)
        
        # Get recent matches (last 20 for quick overview)
        matches = await faceit_api.get_player_matches(user.faceit_player_id, limit=50)
        finished_matches = [m for m in matches if m.status.upper() == "FINISHED"]
        
        if not finished_matches:
            await message.answer(
                "📊 Завершенных матчей за последнее время не найдено.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Quick stats calculation
        wins = len([m for m in finished_matches if MessageFormatter._get_player_faction(m, player.player_id) == m.results.winner])
        total = len(finished_matches)
        win_rate = round((wins / total) * 100, 1) if total > 0 else 0
        
        # Recent form
        recent_results = []
        for match in finished_matches:
            is_win = MessageFormatter._get_player_faction(match, player.player_id) == match.results.winner
            recent_results.append("🟢" if is_win else "🔴")
        
        message_text = f"⚡ <b>Быстрый обзор: {player.nickname}</b>\n\n"
        message_text += f"🎮 <b>Последние {total} матчей:</b>\n"
        message_text += f"🏆 <b>Винрейт:</b> {win_rate}% ({wins}/{total})\n"
        message_text += f"📊 <b>Форма:</b> {' '.join(recent_results)}\n\n"
        message_text += f"💡 Используйте меню для детального анализа"
        
        await message.answer(message_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())
        logger.info(f"Sent today overview to user {message.from_user.id}")
        
    except FaceitAPIError as e:
        logger.error(f"FACEIT API error in today: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении данных.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Unexpected error in today: {e}")
        await message.answer(
            "❌ Произошла непредвиденная ошибка.",
            parse_mode=ParseMode.HTML
        )


# Task management callback handlers
@router.callback_query(F.data.startswith("task_status:"))
async def handle_task_status_callback(callback: CallbackQuery) -> None:
    """Handle task status check callback."""
    from bot.queue_handlers import handle_task_status_check
    await handle_task_status_check(callback)


@router.callback_query(F.data.startswith("task_cancel:"))
async def handle_task_cancel_callback(callback: CallbackQuery) -> None:
    """Handle task cancellation callback."""
    from bot.queue_handlers import handle_task_cancellation
    await handle_task_cancellation(callback)


# Handle callback queries from inline buttons
@router.callback_query(F.data.startswith("analysis_"))
async def handle_analysis_callback(callback: CallbackQuery) -> None:
    """Handle analysis period callback."""
    await callback.answer()
    
    user = await storage.get_user(callback.from_user.id)
    if not user or not user.faceit_player_id:
        await callback.message.edit_text(
            "❌ Сначала привяжите свой FACEIT аккаунт командой /setplayer",
            parse_mode=ParseMode.HTML
        )
        return
    
    period = callback.data.split("_")[1]
    
    if period == "all":
        await callback.message.edit_text("🔍 Получаю полный анализ формы...", parse_mode=ParseMode.HTML)
        
        try:
            player = await faceit_api.get_player_by_id(user.faceit_player_id)
            matches_10 = await faceit_api.get_player_matches(user.faceit_player_id, limit=100)
            matches_30 = await faceit_api.get_player_matches(user.faceit_player_id, limit=200) 
            matches_60 = await faceit_api.get_player_matches(user.faceit_player_id, limit=300)
            
            # Используем новый анализ с клатч статистикой для первого периода
            formatted_message = await MessageFormatter.format_period_analysis_with_api(
                player, faceit_api, 50  # Показываем анализ за 50 матчей с клатч статистикой
            )
            await callback.message.edit_text(formatted_message, parse_mode=ParseMode.HTML)
            
        except Exception as e:
            logger.error(f"Error in analysis callback: {e}")
            await callback.message.edit_text("❌ Произошла ошибка при получении анализа.", parse_mode=ParseMode.HTML)
    else:
        limit = int(period)
        # Увеличиваем лимит для получения большей истории
        actual_limit = min(limit * 2, 100)  # Загружаем в 2 раза больше, но не более 100
        await callback.message.edit_text(f"🔍 Загружаю статистику за последние {actual_limit} матчей...", parse_mode=ParseMode.HTML)
        
        try:
            player = await faceit_api.get_player_by_id(user.faceit_player_id)
            
            # Use new API-based analysis with real HLTV rating calculation
            formatted_message = await MessageFormatter.format_period_analysis_with_api(
                player, faceit_api, actual_limit
            )
            
            await callback.message.edit_text(formatted_message, parse_mode=ParseMode.HTML)
            
        except Exception as e:
            logger.error(f"Error in analysis callback: {e}")
            await callback.message.edit_text(f"❌ Произошла ошибка при получении анализа: {str(e)}", parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "maps_analysis")
async def handle_maps_analysis(callback: CallbackQuery) -> None:
    """Handle maps analysis callback."""
    await callback.answer()
    
    user = await storage.get_user(callback.from_user.id)
    if not user or not user.faceit_player_id:
        await callback.message.edit_text(
            "❌ Сначала привяжите свой FACEIT аккаунт командой /setplayer",
            parse_mode=ParseMode.HTML
        )
        return
    
    await callback.message.edit_text("🗺 Анализирую ваши карты...", parse_mode=ParseMode.HTML)
    
    try:
        player = await faceit_api.get_player_by_id(user.faceit_player_id)
        
        formatted_message = await MessageFormatter.format_map_analysis(
            player, faceit_api, limit=200
        )
        
        # Добавляем кнопку назад
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к анализу", callback_data="analysis_menu")]
        ])
        
        await callback.message.edit_text(formatted_message, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
        
    except Exception as e:
        logger.error(f"Error in maps analysis callback: {e}")
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к анализу", callback_data="analysis_menu")]
        ])
        await callback.message.edit_text(
            f"❌ Произошла ошибка при анализе карт: {str(e)}", 
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard
        )


@router.callback_query(F.data == "today_summary")
async def handle_today_summary(callback: CallbackQuery) -> None:
    """Handle today summary callback."""
    await callback.answer()
    
    user = await storage.get_user(callback.from_user.id)
    if not user or not user.faceit_player_id:
        await callback.message.edit_text(
            "❌ Сначала привяжите свой FACEIT аккаунт командой /setplayer",
            parse_mode=ParseMode.HTML
        )
        return
    
    await callback.message.edit_text("⚡ Получаю быстрый обзор...", parse_mode=ParseMode.HTML)
    
    try:
        player = await faceit_api.get_player_by_id(user.faceit_player_id)
        
        # Get recent matches for summary
        matches_with_stats = await faceit_api.get_matches_with_stats(user.faceit_player_id, limit=100)
        
        if not matches_with_stats:
            await callback.message.edit_text("❌ Матчи не найдены", parse_mode=ParseMode.HTML)
            return
        
        # Calculate summary stats
        current_stats = MessageFormatter._calculate_match_stats_from_api(matches_with_stats, user.faceit_player_id)
        
        if not current_stats:
            await callback.message.edit_text("❌ Не удалось рассчитать статистику", parse_mode=ParseMode.HTML)
            return
        
        # Recent form
        finished_matches = [m for m, s in matches_with_stats if m.status.upper() == "FINISHED"]
        recent_results = []
        for match in finished_matches[:5]:
            is_win = MessageFormatter._get_player_faction(match, player.player_id) == match.results.winner
            recent_results.append("🟢" if is_win else "🔴")
        
        message_text = f"⚡ <b>Быстрый обзор: {player.nickname}</b>\n\n"
        message_text += f"🎮 <b>Последние {current_stats['matches']} матчей:</b>\n"
        message_text += f"🏆 <b>Винрейт:</b> {current_stats['win_rate']}% ({current_stats['wins']}/{current_stats['matches']})\n"
        message_text += f"⚔️ <b>K/D:</b> {current_stats['kd_ratio']}\n"
        message_text += f"💥 <b>ADR:</b> {current_stats['adr']}\n"
        message_text += f"📈 <b>HLTV Rating:</b> {current_stats['hltv_rating']}\n"
        message_text += f"🎪 <b>KAST:</b> {current_stats['kast']}%\n"
        message_text += f"🔥 <b>Clutch:</b> {current_stats['clutch_success']}% ({current_stats['clutch_attempts']})\n"
        message_text += f"📊 <b>Форма:</b> {' '.join(recent_results)}\n"
        
        # Добавляем кнопку назад
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к анализу", callback_data="analysis_menu")]
        ])
        
        await callback.message.edit_text(message_text, parse_mode=ParseMode.HTML, reply_markup=back_keyboard)
        
    except Exception as e:
        logger.error(f"Error in today summary callback: {e}")
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к анализу", callback_data="analysis_menu")]
        ])
        await callback.message.edit_text(
            f"❌ Произошла ошибка: {str(e)}", 
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard
        )


@router.callback_query(F.data == "sessions_analysis")
async def handle_sessions_analysis(callback: CallbackQuery) -> None:
    """Handle sessions analysis callback."""
    await callback.answer()
    
    user = await storage.get_user(callback.from_user.id)
    if not user or not user.faceit_player_id:
        await callback.message.edit_text(
            "❌ Сначала привяжите свой FACEIT аккаунт командой /setplayer",
            parse_mode=ParseMode.HTML
        )
        return
    
    await callback.message.edit_text("🎮 Анализирую ваши игровые сессии...", parse_mode=ParseMode.HTML)
    
    try:
        player = await faceit_api.get_player_by_id(user.faceit_player_id)
        
        formatted_message = await MessageFormatter.format_sessions_analysis(
            player, faceit_api, limit=200
        )
        
        # Создаем клавиатуру с кнопкой "Назад"
        back_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад к анализу", callback_data="analysis_menu")]
            ]
        )
        
        await callback.message.edit_text(
            formatted_message, 
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard
        )
        
    except Exception as e:
        logger.error(f"Error in sessions analysis callback: {e}")
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад к анализу", callback_data="analysis_menu")]
        ])
        await callback.message.edit_text(
            f"❌ Произошла ошибка при анализе сессий: {str(e)}", 
            parse_mode=ParseMode.HTML,
            reply_markup=back_keyboard
        )


@router.callback_query(F.data == "analysis_menu")
async def handle_analysis_menu(callback: CallbackQuery) -> None:
    """Handle analysis menu callback."""
    await callback.answer()
    await callback.message.edit_text(
        "📊 <b>Меню анализа</b>\n\nВыберите тип анализа:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_analysis_menu()
    )

@router.callback_query(F.data == "back_to_menu")
async def handle_back_to_menu(callback: CallbackQuery) -> None:
    """Handle back to menu callback."""
    await callback.answer()
    await callback.message.delete()
    await callback.message.answer(
        "Используйте меню для навигации:",
        reply_markup=get_main_menu()
    )


@router.callback_query(F.data == "back_to_main")
async def handle_back_to_main(callback: CallbackQuery) -> None:
    """Handle back to main stats menu callback."""
    await callback.answer()
    await callback.message.edit_text(
        "📊 <b>Статистика</b>\n\nВыберите раздел:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_stats_menu()
    )




# Administrative commands
@router.message(Command("admin_stats"))
async def cmd_admin_stats(message: Message) -> None:
    """Admin command: Get system statistics."""
    if not AdminManager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав доступа")
        return
    
    try:
        stats = await AdminManager.get_system_stats()
        stats_message = AdminManager.format_stats_message(stats)
        await message.answer(stats_message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error getting admin stats: {e}")
        await message.answer("❌ Ошибка при получении статистики")




@router.message(Command("admin_user"))
async def cmd_admin_user(message: Message) -> None:
    """Admin command: Get user information."""
    if not AdminManager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав доступа")
        return
    
    if not message.text:
        return
    
    args = message.text.split()[1:]
    if len(args) < 1:
        await message.answer(
            "Использование: /admin_user <user_id>\n"
            "Пример: /admin_user 123456789",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        user_id = int(args[0])
        user_info = await AdminManager.get_user_info(user_id)
        info_message = AdminManager.format_user_info(user_info)
        await message.answer(info_message, parse_mode=ParseMode.HTML)
        
    except ValueError:
        await message.answer("❌ Неверный формат user_id")
    except Exception as e:
        logger.error(f"Error getting user info: {e}")
        await message.answer("❌ Ошибка при получении информации о пользователе")




@router.message(Command("admin_cache"))
async def cmd_admin_cache(message: Message) -> None:
    """Admin command: Get cache statistics."""
    if not AdminManager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав доступа")
        return
    
    try:
        cache_stats = await get_cache_stats()
        
        stats_message = "📊 <b>Статистика кэша</b>\n\n"
        
        # Player cache
        player_cache = cache_stats["player_cache"]
        stats_message += f"👤 <b>Player Cache:</b>\n"
        stats_message += f"• Размер: {player_cache['memory_usage']}\n"
        stats_message += f"• Hit Rate: {player_cache['hit_rate']}%\n"
        stats_message += f"• Hits/Misses: {player_cache['hits']}/{player_cache['misses']}\n\n"
        
        # Match cache
        match_cache = cache_stats["match_cache"]
        stats_message += f"⚔️ <b>Match Cache:</b>\n"
        stats_message += f"• Размер: {match_cache['memory_usage']}\n"
        stats_message += f"• Hit Rate: {match_cache['hit_rate']}%\n"
        stats_message += f"• Hits/Misses: {match_cache['hits']}/{match_cache['misses']}\n\n"
        
        # Stats cache
        stats_cache = cache_stats["stats_cache"]
        stats_message += f"📈 <b>Stats Cache:</b>\n"
        stats_message += f"• Размер: {stats_cache['memory_usage']}\n"
        stats_message += f"• Hit Rate: {stats_cache['hit_rate']}%\n"
        stats_message += f"• Hits/Misses: {stats_cache['hits']}/{stats_cache['misses']}\n\n"
        
        stats_message += f"💾 <b>Общий размер:</b> {cache_stats['total_entries']} записей"
        
        await message.answer(stats_message, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        await message.answer("❌ Ошибка при получении статистики кэша")


@router.message(Command("admin_cache_clear"))
async def cmd_admin_cache_clear(message: Message) -> None:
    """Admin command: Clear all caches."""
    if not AdminManager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав доступа")
        return
    
    try:
        await clear_all_caches()
        await message.answer("✅ Все кэши очищены")
        logger.info(f"Admin {message.from_user.id} cleared all caches")
        
    except Exception as e:
        logger.error(f"Error clearing caches: {e}")
        await message.answer("❌ Ошибка при очистке кэшей")


@router.message(Command("my_tasks"))
async def cmd_my_tasks(message: Message) -> None:
    """Show user's active tasks."""
    try:
        from bot.queue_handlers import get_user_active_tasks
        
        active_tasks = await get_user_active_tasks(message.from_user.id)
        
        if not active_tasks:
            await message.answer(
                "📋 <b>Ваши задачи</b>\n\n"
                "📭 У вас нет активных задач",
                parse_mode=ParseMode.HTML
            )
            return
        
        tasks_message = "📋 <b>Ваши активные задачи:</b>\n\n"
        
        for task_info in active_tasks:
            task_id = task_info["task_id"]
            status = task_info["status"]
            
            task_status = status.get("status", "unknown")
            
            # Status emoji
            status_emoji = {
                "queued": "⏳",
                "started": "🔄",
                "finished": "✅",
                "failed": "❌",
                "cancelled": "🚫"
            }.get(task_status, "❓")
            
            tasks_message += f"{status_emoji} <code>{task_id[:12]}...</code>\n"
            tasks_message += f"📊 Статус: {task_status}\n"
            
            # Add progress if available
            progress = status.get("progress", {})
            if progress:
                current_step = progress.get("current_step", 0)
                total_steps = progress.get("total_steps", 0)
                if total_steps > 0:
                    progress_pct = round((current_step / total_steps) * 100, 1)
                    tasks_message += f"📈 Прогресс: {progress_pct}%\n"
                    
                current_operation = progress.get("current_operation")
                if current_operation:
                    tasks_message += f"⚙️ {current_operation}\n"
            
            tasks_message += "\n"
        
        await message.answer(tasks_message, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error getting user tasks: {e}")
        await message.answer(
            "❌ Ошибка при получении списка задач",
            parse_mode=ParseMode.HTML
        )


@router.message(Command("cancel_task"))
async def cmd_cancel_task(message: Message) -> None:
    """Cancel a user's task."""
    if not message.text:
        return
    
    args = message.text.split()[1:]
    if not args:
        await message.answer(
            "Использование: /cancel_task <task_id>\n"
            "Используйте /my_tasks чтобы увидеть свои задачи",
            parse_mode=ParseMode.HTML
        )
        return
    
    task_id = args[0]
    user_id = message.from_user.id
    
    try:
        from bot.queue_handlers import user_active_tasks
        
        # Check if task belongs to user
        user_tasks = user_active_tasks.get(user_id, [])
        if task_id not in user_tasks:
            await message.answer(
                "❌ Задача не найдена среди ваших активных задач\n\n"
                "Используйте /my_tasks для просмотра ваших задач",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Cancel the task
        success = task_manager.cancel_task(task_id)
        
        if success:
            # Remove from user's active tasks
            user_active_tasks[user_id].remove(task_id)
            if not user_active_tasks[user_id]:
                del user_active_tasks[user_id]
            
            await message.answer(
                f"✅ <b>Задача отменена</b>\n\n"
                f"🆔 ID: <code>{task_id}</code>",
                parse_mode=ParseMode.HTML
            )
        else:
            await message.answer(
                f"❌ <b>Не удалось отменить задачу</b>\n\n"
                f"🆔 ID: <code>{task_id}</code>\n"
                f"💡 Возможно, задача уже завершена",
                parse_mode=ParseMode.HTML
            )
        
    except Exception as e:
        logger.error(f"Error cancelling task {task_id}: {e}")
        await message.answer(
            f"❌ Ошибка при отмене задачи\n\n"
            f"🆔 ID: <code>{task_id}</code>",
            parse_mode=ParseMode.HTML
        )




async def _fallback_analyze_match(message: Message, match_url: str) -> None:
    """Fallback synchronous match analysis when queue system fails."""
    await message.answer(
        "🔍 <b>Анализирую матч...</b>\n\n"
        "⏳ Получаю данные игроков и статистику...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Analyze the match
        analysis_result = await match_analyzer.analyze_match(match_url)
        
        # Format and send result
        formatted_message = format_match_analysis(analysis_result)
        
        # Split long message if needed
        if len(formatted_message) > 4096:
            # Split into multiple messages
            parts = []
            current_part = ""
            lines = formatted_message.split('\n')
            
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
            
            # Send all parts
            for i, part in enumerate(parts):
                if i == 0:
                    await message.answer(part, parse_mode=ParseMode.HTML)
                else:
                    await message.answer(
                        f"<b>Продолжение анализа...</b>\n\n{part}",
                        parse_mode=ParseMode.HTML
                    )
        else:
            await message.answer(formatted_message, parse_mode=ParseMode.HTML)
        
        logger.info(f"Match analysis completed for user {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error in match analysis: {e}")
        await message.answer(
            "❌ <b>Ошибка при анализе матча</b>\n\n"
            "Возможные причины:\n"
            "• Неверная ссылка на матч\n"
            "• Матч уже завершён\n"
            "• Временные проблемы с API FACEIT\n\n"
            "Попробуйте ещё раз или обратитесь в поддержку.",
            parse_mode=ParseMode.HTML
        )




# Handle any other text
@router.message(F.text)
async def handle_text(message: Message) -> None:
    """Handle any other text input."""
    user = await storage.get_user(message.from_user.id)
    
    # Check if message contains FACEIT match URL
    if message.text and 'faceit.com' in message.text.lower() and '/room/' in message.text.lower():
        await analyze_match_from_url(message, message.text.strip())
        return
    
    # Check if user is waiting for nickname
    if user and user.waiting_for_nickname:
        nickname = message.text.strip()
        
        # Check if it looks like a valid nickname
        if len(nickname) < 3 or len(nickname) > 25:
            await message.answer(
                "❌ Никнейм должен содержать от 3 до 25 символов.\n"
                "Попробуйте еще раз:",
                parse_mode=ParseMode.HTML
            )
            return
            
        await message.answer(f"🔍 Ищу игрока {nickname}...", parse_mode=ParseMode.HTML)
        
        try:
            player = await faceit_api.search_player(nickname)
            if not player:
                await message.answer(
                    f"❌ Игрок с никнеймом \"{nickname}\" не найден.\n\n"
                    f"Попробуйте:\n"
                    f"• Проверить написание\n"
                    f"• Написать полный никнейм как он отображается в FACEIT\n\n"
                    f"Напишите другой никнейм:",
                    parse_mode=ParseMode.HTML
                )
                return
            
            user.faceit_player_id = player.player_id
            user.faceit_nickname = player.nickname
            user.waiting_for_nickname = False
            await storage.save_user(user)
            
            player_info = MessageFormatter.format_player_info(player, None, None)
            success_text = f"✅ Игрок успешно привязан!\n\n{player_info}"
            
            await message.answer(success_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())
            logger.info(f"User {message.from_user.id} linked player {player.nickname}")
            
        except FaceitAPIError as e:
            logger.error(f"FACEIT API error in text handler: {e}")
            await message.answer(
                "❌ Произошла ошибка при поиске игрока. Попробуйте позже.\n"
                "Напишите никнейм еще раз:",
                parse_mode=ParseMode.HTML
            )
    elif not user or not user.faceit_player_id:
        await message.answer(
            "🤔 Не понимаю команду.\n\n"
            "Сначала привяжите FACEIT аккаунт командой /setplayer или нажмите /start.",
            parse_mode=ParseMode.HTML
        )
    else:
        await message.answer(
            "🤔 Не понимаю команду. Используйте меню ниже или /help для справки.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu()
        )


# ==================== STATISTICS CALLBACK HANDLERS ====================

@router.callback_query(F.data == "my_stats")
async def callback_my_stats(callback: CallbackQuery):
    """Handle my stats callback - show statistics menu."""
    await callback.answer()
    
    user = await storage.get_user(callback.from_user.id)
    if not user or not user.faceit_player_id:
        await callback.message.edit_text(
            "❌ <b>Для просмотра статистики нужно привязать аккаунт</b>\n\n"
            "Используйте команду /setplayer",
            parse_mode=ParseMode.HTML
        )
        return
    
    await callback.message.edit_text(
        f"📊 <b>Статистика игрока {user.faceit_nickname}</b>\n\n"
        "Выберите тип статистики:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_stats_menu()
    )

@router.callback_query(F.data == "stats_general")
async def callback_stats_general(callback: CallbackQuery):
    """Handle general statistics callback."""
    await callback.answer()
    
    user = await storage.get_user(callback.from_user.id)
    if not user or not user.faceit_player_id:
        await callback.message.edit_text(
            "❌ <b>Для просмотра статистики нужно привязать аккаунт</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        await callback.message.edit_text("📊 Получаю общую статистику...", parse_mode=ParseMode.HTML)
        
        player = await faceit_api.get_player_by_id(user.faceit_player_id)
        stats = await faceit_api.get_player_stats(user.faceit_player_id, "cs2")
        
        if not player or not stats:
            await callback.message.edit_text("❌ Статистика недоступна", parse_mode=ParseMode.HTML)
            return
        
        general_text = MessageFormatter.format_player_stats(player, stats)
        
        await callback.message.edit_text(
            general_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К статистике", callback_data="my_stats")]
            ])
        )
    except Exception as e:
        logger.error(f"Error showing general stats: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при загрузке общей статистики",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К статистике", callback_data="my_stats")]
            ])
        )

@router.callback_query(F.data == "stats_detailed")
async def callback_stats_detailed(callback: CallbackQuery):
    """Handle detailed statistics callback."""
    await callback.answer()
    
    user = await storage.get_user(callback.from_user.id)
    if not user or not user.faceit_player_id:
        await callback.message.edit_text(
            "❌ <b>Для просмотра статистики нужно привязать аккаунт</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        await callback.message.edit_text("📈 Получаю детальную статистику...", parse_mode=ParseMode.HTML)
        
        stats = await faceit_api.get_player_stats(user.faceit_player_id, "cs2")
        
        if not stats:
            await callback.message.edit_text("❌ Статистика недоступна", parse_mode=ParseMode.HTML)
            return
        
        # Get player info for advanced stats
        player = await faceit_api.get_player_by_id(user.faceit_player_id)
        if not player:
            await callback.message.edit_text("❌ Игрок не найден", parse_mode=ParseMode.HTML)
            return
            
        # Use advanced CS2 formatter
        detailed_text = format_cs2_advanced_stats(player, stats)
        
        await callback.message.edit_text(
            detailed_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К статистике", callback_data="my_stats")]
            ])
        )
    except Exception as e:
        logger.error(f"Error showing detailed stats: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при загрузке детальной статистики",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К статистике", callback_data="my_stats")]
            ])
        )

@router.callback_query(F.data == "stats_maps")
async def callback_stats_maps(callback: CallbackQuery):
    """Handle map statistics callback with real per-map analysis."""
    await callback.answer()
    
    user = await storage.get_user(callback.from_user.id)
    if not user or not user.faceit_player_id:
        await callback.message.edit_text(
            "❌ <b>Для просмотра статистики нужно привязать аккаунт</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        await callback.message.edit_text("🔍 Анализирую статистику по картам...", parse_mode=ParseMode.HTML)
        
        # Get player info for map analysis
        player = await faceit_api.get_player_by_id(user.faceit_player_id)
        if not player:
            await callback.message.edit_text("❌ Игрок не найден", parse_mode=ParseMode.HTML)
            return
            
        # Use proper map analysis from MessageFormatter with real match data
        maps_text = await MessageFormatter.format_map_analysis(
            player,
            faceit_api,
            limit=100  # Analyze last 100 matches for accurate map statistics
        )
        
        await callback.message.edit_text(
            maps_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К статистике", callback_data="my_stats")]
            ])
        )
    except Exception as e:
        logger.error(f"Error showing map stats: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при загрузке статистики карт",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К статистике", callback_data="my_stats")]
            ])
        )

@router.callback_query(F.data == "stats_sessions")
async def callback_stats_sessions(callback: CallbackQuery):
    """Handle session statistics callback with proper session analysis."""
    await callback.answer()
    
    user = await storage.get_user(callback.from_user.id)
    if not user or not user.faceit_player_id:
        await callback.message.edit_text(
            "❌ <b>Для просмотра статистики нужно привязать аккаунт</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        # Show loading message
        await callback.message.edit_text("🔍 Анализирую игровые сессии...", parse_mode=ParseMode.HTML)
        
        # Get player info for sessions analysis
        player = await faceit_api.get_player_by_id(user.faceit_player_id)
        if not player:
            await callback.message.edit_text("❌ Игрок не найден", parse_mode=ParseMode.HTML)
            return
            
        # Use proper sessions analysis from MessageFormatter with real match data  
        sessions_text = await MessageFormatter.format_sessions_analysis(
            player,
            faceit_api,
            limit=100  # Analyze last 100 matches for session grouping
        )
        
        await callback.message.edit_text(
            sessions_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К статистике", callback_data="my_stats")]
            ])
        )
    except Exception as e:
        logger.error(f"Error showing session stats: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при загрузке статистики сессий",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К статистике", callback_data="my_stats")]
            ])
        )

@router.callback_query(F.data == "stats_weapons")
async def callback_stats_weapons(callback: CallbackQuery):
    """Handle weapon statistics callback."""
    await callback.answer()
    
    user = await storage.get_user(callback.from_user.id)
    if not user or not user.faceit_player_id:
        await callback.message.edit_text(
            "❌ <b>Для просмотра статистики нужно привязать аккаунт</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        await callback.message.edit_text("🔍 Анализирую статистику по оружию...", parse_mode=ParseMode.HTML)
        
        # Get player stats for weapon analysis
        stats = await faceit_api.get_player_stats(user.faceit_player_id, "cs2")
        if not stats:
            await callback.message.edit_text("❌ Статистика недоступна", parse_mode=ParseMode.HTML)
            return
            
        # Use weapon stats formatter
        weapon_text = format_weapon_stats(stats)
        
        await callback.message.edit_text(
            weapon_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К статистике", callback_data="my_stats")]
            ])
        )
    
    except Exception as e:
        logger.error(f"Error showing weapon stats: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при загрузке статистики по оружию",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К статистике", callback_data="my_stats")]
            ])
        )

@router.callback_query(F.data.in_(["stats_10", "stats_30", "stats_60"]))
async def callback_stats_matches(callback: CallbackQuery):
    """Handle match statistics callback."""
    await callback.answer()
    
    user = await storage.get_user(callback.from_user.id)
    if not user or not user.faceit_player_id:
        await callback.message.edit_text(
            "❌ <b>Для просмотра статистики нужно привязать аккаунт</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Extract match count from callback data
    match_count = int(callback.data.split("_")[1])
    
    try:
        await callback.message.edit_text(
            f"📊 Получаю статистику за последние {match_count} матчей...", 
            parse_mode=ParseMode.HTML
        )
        
        player = await faceit_api.get_player_by_id(user.faceit_player_id)
        if not player:
            await callback.message.edit_text("❌ Игрок не найден", parse_mode=ParseMode.HTML)
            return
        
        # Get matches with statistics
        matches_text = await MessageFormatter.format_recent_matches_analysis(
            player, faceit_api, limit=match_count
        )
        
        await callback.message.edit_text(
            matches_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К статистике", callback_data="my_stats")]
            ])
        )
    except Exception as e:
        logger.error(f"Error getting match statistics: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при получении статистики матчей",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К статистике", callback_data="my_stats")]
            ])
        )

@router.callback_query(F.data == "stats_playstyle")
async def callback_stats_playstyle(callback: CallbackQuery):
    """Handle playstyle statistics callback."""
    await callback.answer()
    
    user = await storage.get_user(callback.from_user.id)
    if not user or not user.faceit_player_id:
        await callback.message.edit_text(
            "❌ <b>Для просмотра статистики нужно привязать аккаунт</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        await callback.message.edit_text("🔍 Анализирую стиль игры...", parse_mode=ParseMode.HTML)
        
        stats = await faceit_api.get_player_stats(user.faceit_player_id, "cs2")
        if not stats:
            await callback.message.edit_text("❌ Статистика недоступна", parse_mode=ParseMode.HTML)
            return
            
        playstyle_text = format_player_playstyle(stats)
        
        await callback.message.edit_text(
            playstyle_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К статистике", callback_data="my_stats")]
            ])
        )
    except Exception as e:
        logger.error(f"Error showing playstyle stats: {e}")
        await callback.message.edit_text(
            "❌ Ошибка при загрузке анализа стиля игры",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К статистике", callback_data="my_stats")]
            ])
        )