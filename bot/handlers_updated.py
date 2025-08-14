"""Updated Bot command handlers with service integration."""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, PreCheckoutQuery, SuccessfulPayment
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode

from faceit.api import FaceitAPI, FaceitAPIError
from utils.storage import UserData, SubscriptionTier
from utils.formatter import MessageFormatter
from utils.subscription import SubscriptionManager
from utils.admin import AdminManager
from utils.payments import PaymentManager
from utils.cache import get_cache_stats, clear_all_caches
from config.version import get_version, get_build_info
from adapters.bot_integration import BotIntegrationAdapter

logger = logging.getLogger(__name__)

router = Router()

# Global instances (will be initialized when bot starts)
bot_adapter: BotIntegrationAdapter = None
payment_manager: PaymentManager = None


def initialize_handlers(integration_adapter: BotIntegrationAdapter, payment_mgr: PaymentManager = None):
    """Initialize handlers with integration adapter."""
    global bot_adapter, payment_manager
    bot_adapter = integration_adapter
    payment_manager = payment_mgr
    logger.info("Handlers initialized with integration adapter")


def get_main_menu():
    """Get main menu keyboard."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Моя статистика"), KeyboardButton(text="🎮 Последний матч")],
            [KeyboardButton(text="📋 История матчей"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="📈 Анализ формы"), KeyboardButton(text="🔍 Найти игрока")],
            [KeyboardButton(text="⚔️ Анализ матча"), KeyboardButton(text="💎 Подписка")],
            [KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
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
    """Handle /start command with service integration."""
    if not bot_adapter:
        await message.answer("⚠️ Система временно недоступна, попробуйте позже.")
        return
    
    try:
        # Extract referral code if present
        referral_code = None
        if message.text and len(message.text.split()) > 1:
            referral_code = message.text.split()[1].strip()
        
        # Get or create user using integration adapter
        user = await bot_adapter.get_or_create_user(
            message.from_user.id,
            referral_code=referral_code
        )
        
        if not user:
            await message.answer(
                "❌ Ошибка при создании пользователя. Попробуйте позже.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Handle referral success message
        if referral_code:
            await message.answer(
                "🎉 <b>Добро пожаловать!</b>\n\n"
                "✅ Реферальный код обработан!\n"
                "🎁 Проверьте статус подписки в меню!\n\n"
                "Теперь привяжите свой FACEIT аккаунт:",
                parse_mode=ParseMode.HTML
            )
        
        # Check if user has FACEIT account linked
        if user.faceit_player_id:
            # User already linked, show main menu
            welcome_text = f"""
<b>🎮 Добро пожаловать обратно!</b>

Привязанный аккаунт: <b>{user.faceit_nickname}</b>

Используйте меню ниже для просмотра статистики и анализа матчей.
"""
            await message.answer(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())
        else:
            # New user or no FACEIT account, ask for nickname
            welcome_text = """
<b>🎮 Добро пожаловать в FACEIT Stats Bot!</b>

Этот бот поможет вам отслеживать статистику ваших матчей в CS2 на платформе FACEIT.

<b>Напишите ваш никнейм в FACEIT:</b>
"""
            await message.answer(welcome_text, parse_mode=ParseMode.HTML)
        
        # Track command usage
        await bot_adapter.track_command_usage(message.from_user.id, "start", success=True)
    
    except Exception as e:
        logger.error(f"Error in cmd_start: {e}")
        await message.answer(
            "❌ Произошла ошибка при обработке команды.",
            parse_mode=ParseMode.HTML
        )
        
        if bot_adapter:
            await bot_adapter.track_command_usage(message.from_user.id, "start", success=False)


@router.message(F.text == "🔍 Найти игрока")
async def menu_find_player(message: Message) -> None:
    """Handle find player menu with service integration."""
    if not bot_adapter:
        await message.answer("⚠️ Система временно недоступна, попробуйте позже.")
        return
    
    try:
        # Update user activity
        await bot_adapter.update_user_activity(message.from_user.id, "find_player")
        
        await message.answer(
            "🔍 <b>Поиск игрока</b>\n\nВведите никнейм игрока в FACEIT для привязки к вашему аккаунту:\n\nПример: <code>s1mple</code>",
            parse_mode=ParseMode.HTML
        )
        
        await bot_adapter.track_command_usage(message.from_user.id, "find_player", success=True)
    
    except Exception as e:
        logger.error(f"Error in menu_find_player: {e}")
        await message.answer("❌ Произошла ошибка при обработке команды.")


@router.message(F.text == "👤 Профиль")
async def menu_profile(message: Message) -> None:
    """Handle profile menu with service integration."""
    await cmd_profile(message)


@router.message(F.text == "📊 Моя статистика")
async def menu_stats(message: Message) -> None:
    """Handle stats menu with service integration."""
    await cmd_stats(message)


@router.message(F.text == "💎 Подписка")
async def menu_subscription(message: Message) -> None:
    """Handle subscription menu with service integration."""
    if not bot_adapter:
        await message.answer("⚠️ Система временно недоступна, попробуйте позже.")
        return
    
    try:
        # Get subscription status using integration adapter
        status_message = await bot_adapter.format_subscription_status(message.from_user.id)
        
        # Create inline keyboard for subscription actions
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⭐ Купить Premium", callback_data="buy_premium"),
                    InlineKeyboardButton(text="💎 Купить Pro", callback_data="buy_pro")
                ],
                [
                    InlineKeyboardButton(text="🎁 Реферальный код", callback_data="referral_menu"),
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_subscription")
                ],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
            ]
        )
        
        await message.answer(status_message, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        
        await bot_adapter.track_command_usage(message.from_user.id, "subscription", success=True)
    
    except Exception as e:
        logger.error(f"Error in menu_subscription: {e}")
        await message.answer("❌ Произошла ошибка при получении статуса подписки.")


@router.message(F.text == "⚔️ Анализ матча")
async def menu_match_analysis(message: Message) -> None:
    """Handle match analysis menu with service integration."""
    if not bot_adapter:
        await message.answer("⚠️ Система временно недоступна, попробуйте позже.")
        return
    
    try:
        # Check rate limits
        can_request, reason = await bot_adapter.check_rate_limit(message.from_user.id)
        if not can_request:
            await message.answer(f"❌ {reason}")
            return
        
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
        
        await bot_adapter.track_command_usage(message.from_user.id, "match_analysis_menu", success=True)
    
    except Exception as e:
        logger.error(f"Error in menu_match_analysis: {e}")
        await message.answer("❌ Произошла ошибка при обработке команды.")


@router.message(Command("setplayer"))
async def cmd_set_player(message: Message) -> None:
    """Handle /setplayer command with service integration."""
    if not bot_adapter:
        await message.answer("⚠️ Система временно недоступна, попробуйте позже.")
        return
    
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
    
    try:
        await message.answer(f"🔍 Ищу игрока {nickname}...", parse_mode=ParseMode.HTML)
        
        # Link FACEIT account using integration adapter
        success, error_message = await bot_adapter.link_faceit_account(
            message.from_user.id, nickname
        )
        
        if success:
            # Get updated user data for display
            user = await bot_adapter.storage.get_user(message.from_user.id)
            
            success_text = f"✅ Игрок успешно привязан!\n\n"
            success_text += f"🎮 <b>Никнейм:</b> {user.faceit_nickname}\n"
            success_text += f"🆔 <b>ID:</b> {user.faceit_player_id}\n"
            success_text += f"🌍 <b>Язык:</b> {user.language}\n"
            
            await message.answer(success_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())
            
            await bot_adapter.track_command_usage(message.from_user.id, "setplayer", success=True)
            logger.info(f"User {message.from_user.id} linked player {nickname}")
        else:
            await message.answer(
                f"❌ {error_message}",
                parse_mode=ParseMode.HTML
            )
            await bot_adapter.track_command_usage(message.from_user.id, "setplayer", success=False)
    
    except Exception as e:
        logger.error(f"Error in cmd_set_player: {e}")
        await message.answer(
            "❌ Произошла непредвиденная ошибка при поиске игрока.",
            parse_mode=ParseMode.HTML
        )


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    """Handle /profile command with service integration."""
    if not bot_adapter:
        await message.answer("⚠️ Система временно недоступна, попробуйте позже.")
        return
    
    try:
        # Check rate limits
        can_request, reason = await bot_adapter.check_rate_limit(message.from_user.id)
        if not can_request:
            await message.answer(f"❌ {reason}")
            return
        
        user = await bot_adapter.storage.get_user(message.from_user.id)
        if not user or not user.faceit_player_id:
            await message.answer(
                "❌ Сначала привяжите свой FACEIT аккаунт командой /setplayer\n\nИли нажмите \"🔍 Найти игрока\" в меню.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu()
            )
            return
        
        await message.answer("🔍 Получаю информацию о профиле...", parse_mode=ParseMode.HTML)
        
        # Get user statistics with FACEIT data
        stats = await bot_adapter.get_user_statistics(message.from_user.id, include_faceit_stats=True)
        
        if stats:
            profile_text = f"👤 <b>Профиль: {user.faceit_nickname}</b>\n\n"
            profile_text += f"🆔 <b>ID:</b> <code>{user.faceit_player_id}</code>\n"
            profile_text += f"📅 <b>Зарегистрирован:</b> {user.created_at.strftime('%d.%m.%Y') if user.created_at else 'Неизвестно'}\n"
            profile_text += f"⏰ <b>Последняя активность:</b> {user.last_active_at.strftime('%d.%m.%Y %H:%M') if user.last_active_at else 'Неизвестно'}\n"
            profile_text += f"📊 <b>Всего запросов:</b> {user.total_requests}\n"
            
            # Add FACEIT stats if available
            faceit_stats = stats.get("faceit_stats")
            if faceit_stats:
                profile_text += f"\n🎮 <b>FACEIT Статистика:</b>\n"
                profile_text += f"⭐ <b>Уровень:</b> {faceit_stats.get('skill_level', 'N/A')}\n"
                profile_text += f"🏆 <b>ELO:</b> {faceit_stats.get('faceit_elo', 'N/A')}\n"
                profile_text += f"🌍 <b>Регион:</b> {faceit_stats.get('region', 'N/A')}\n"
            
            await message.answer(profile_text, parse_mode=ParseMode.HTML)
            
            await bot_adapter.track_command_usage(message.from_user.id, "profile", success=True)
        else:
            await message.answer(
                "❌ Не удалось получить информацию о профиле.",
                parse_mode=ParseMode.HTML
            )
    
    except Exception as e:
        logger.error(f"Error in cmd_profile: {e}")
        await message.answer("❌ Произошла ошибка при получении профиля.")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Handle /stats command with service integration."""
    if not bot_adapter:
        await message.answer("⚠️ Система временно недоступна, попробуйте позже.")
        return
    
    try:
        # Check rate limits
        can_request, reason = await bot_adapter.check_rate_limit(message.from_user.id)
        if not can_request:
            await message.answer(f"❌ {reason}")
            return
        
        user = await bot_adapter.storage.get_user(message.from_user.id)
        if not user or not user.faceit_player_id:
            await message.answer(
                "❌ Сначала привяжите свой FACEIT аккаунт командой /setplayer\n\nИли нажмите \"🔍 Найти игрока\" в меню.",
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu()
            )
            return
        
        await message.answer("🔍 Получаю детальную статистику...", parse_mode=ParseMode.HTML)
        
        # Use existing FACEIT API integration for detailed stats
        from faceit.api import FaceitAPI
        faceit_api = FaceitAPI()
        
        try:
            player = await faceit_api.get_player_by_id(user.faceit_player_id)
            player_stats = await faceit_api.get_player_stats(user.faceit_player_id)
            recent_matches = await faceit_api.get_player_matches(user.faceit_player_id, limit=50)
            
            if player:
                formatted_message = MessageFormatter.format_detailed_stats(player, player_stats, recent_matches)
                await message.answer(formatted_message, parse_mode=ParseMode.HTML)
                
                await bot_adapter.track_command_usage(message.from_user.id, "stats", success=True)
            else:
                await message.answer("❌ Не удалось получить статистику игрока.")
        
        except FaceitAPIError as e:
            logger.error(f"FACEIT API error in stats: {e}")
            await message.answer("❌ Произошла ошибка при получении статистики.")
    
    except Exception as e:
        logger.error(f"Error in cmd_stats: {e}")
        await message.answer("❌ Произошла ошибка при получении статистики.")


@router.message(Command("analyze"))
async def cmd_analyze(message: Message) -> None:
    """Handle /analyze command with service integration."""
    if not bot_adapter:
        await message.answer("⚠️ Система временно недоступна, попробуйте позже.")
        return
    
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
    
    try:
        # Check rate limits
        can_request, reason = await bot_adapter.check_rate_limit(message.from_user.id)
        if not can_request:
            await message.answer(f"❌ {reason}")
            return
        
        await message.answer(
            "🔍 <b>Анализирую матч...</b>\n\n"
            "⏳ Получаю данные игроков и статистику...",
            parse_mode=ParseMode.HTML
        )
        
        # Analyze match using integration adapter
        success, error_message, analysis_data = await bot_adapter.analyze_match(
            match_url, message.from_user.id
        )
        
        if success and analysis_data:
            # Format analysis result
            from utils.match_analyzer import format_match_analysis
            formatted_message = format_match_analysis(analysis_data)
            
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
            
            await bot_adapter.track_command_usage(message.from_user.id, "analyze", success=True)
        else:
            await message.answer(
                f"❌ <b>Ошибка при анализе матча</b>\n\n"
                f"{error_message or 'Неизвестная ошибка'}\n\n"
                "Возможные причины:\n"
                "• Неверная ссылка на матч\n"
                "• Матч уже завершён\n"
                "• Временные проблемы с API FACEIT",
                parse_mode=ParseMode.HTML
            )
            
            await bot_adapter.track_command_usage(message.from_user.id, "analyze", success=False)
    
    except Exception as e:
        logger.error(f"Error in cmd_analyze: {e}")
        await message.answer(
            "❌ Произошла ошибка при анализе матча. Попробуйте позже.",
            parse_mode=ParseMode.HTML
        )


# Handle text that looks like a nickname (for when user just types nickname)
@router.message(F.text.regexp(r'^[a-zA-Z0-9_-]{3,25}$'))
async def handle_nickname_input(message: Message) -> None:
    """Handle nickname input without command with service integration."""
    if not bot_adapter:
        await message.answer("⚠️ Система временно недоступна, попробуйте позже.")
        return
    
    try:
        user = await bot_adapter.storage.get_user(message.from_user.id)
        
        # Check if user needs to link account or is waiting for nickname
        if not user or not user.faceit_player_id:
            nickname = message.text.strip()
            await message.answer(f"🔍 Ищу игрока {nickname}...", parse_mode=ParseMode.HTML)
            
            # Link FACEIT account using integration adapter
            success, error_message = await bot_adapter.link_faceit_account(
                message.from_user.id, nickname
            )
            
            if success:
                updated_user = await bot_adapter.storage.get_user(message.from_user.id)
                success_text = f"✅ Игрок успешно привязан!\n\n"
                success_text += f"🎮 <b>Никнейм:</b> {updated_user.faceit_nickname}\n"
                
                await message.answer(success_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())
                
                await bot_adapter.track_command_usage(message.from_user.id, "nickname_input", success=True)
                logger.info(f"User {message.from_user.id} linked player {nickname}")
            else:
                await message.answer(
                    f"❌ {error_message}\n\n"
                    f"Попробуйте:\n"
                    f"• Проверить написание\n"
                    f"• Использовать команду: <code>/setplayer {nickname}</code>",
                    parse_mode=ParseMode.HTML
                )
    
    except Exception as e:
        logger.error(f"Error in handle_nickname_input: {e}")
        await message.answer("❌ Произошла ошибка при поиске игрока.")


# Handle any other text
@router.message(F.text)
async def handle_text(message: Message) -> None:
    """Handle any other text input with service integration."""
    if not bot_adapter:
        await message.answer("⚠️ Система временно недоступна, попробуйте позже.")
        return
    
    try:
        # Check if message contains FACEIT match URL
        if message.text and 'faceit.com' in message.text.lower() and '/room/' in message.text.lower():
            # Extract URL and analyze match
            match_url = message.text.strip()
            
            # Check rate limits
            can_request, reason = await bot_adapter.check_rate_limit(message.from_user.id)
            if not can_request:
                await message.answer(f"❌ {reason}")
                return
            
            await message.answer(
                "🔍 <b>Обнаружена ссылка на матч! Анализирую...</b>\n\n"
                "⏳ Получаю данные игроков и статистику...",
                parse_mode=ParseMode.HTML
            )
            
            # Analyze match using integration adapter
            success, error_message, analysis_data = await bot_adapter.analyze_match(
                match_url, message.from_user.id
            )
            
            if success and analysis_data:
                from utils.match_analyzer import format_match_analysis
                formatted_message = format_match_analysis(analysis_data)
                await message.answer(formatted_message, parse_mode=ParseMode.HTML)
            else:
                await message.answer(f"❌ Ошибка при анализе матча: {error_message}")
            
            return
        
        # Check if user is waiting for nickname or doesn't have FACEIT account
        user = await bot_adapter.storage.get_user(message.from_user.id)
        
        if not user or not user.faceit_player_id:
            # Try to link as FACEIT nickname
            nickname = message.text.strip()
            
            if len(nickname) >= 3 and len(nickname) <= 25:
                success, error_message = await bot_adapter.link_faceit_account(
                    message.from_user.id, nickname
                )
                
                if success:
                    updated_user = await bot_adapter.storage.get_user(message.from_user.id)
                    success_text = f"✅ Игрок успешно привязан!\n\n"
                    success_text += f"🎮 <b>Никнейм:</b> {updated_user.faceit_nickname}\n"
                    
                    await message.answer(success_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())
                    return
                else:
                    await message.answer(
                        f"❌ {error_message}\n\n"
                        "Попробуйте еще раз или используйте команду /setplayer",
                        parse_mode=ParseMode.HTML
                    )
                    return
            else:
                await message.answer(
                    "❌ Никнейм должен содержать от 3 до 25 символов.\n"
                    "Попробуйте еще раз:",
                    parse_mode=ParseMode.HTML
                )
                return
        
        # Default response for unrecognized text
        await message.answer(
            "🤔 Не понимаю команду. Используйте меню ниже или /help для справки.",
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu()
        )
    
    except Exception as e:
        logger.error(f"Error in handle_text: {e}")
        await message.answer("❌ Произошла ошибка при обработке сообщения.")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command."""
    help_text = """
<b>🎮 FACEIT Stats Bot - Справка</b>

<b>📋 Доступные команды:</b>

/start - начать работу с ботом
/setplayer &lt;nickname&gt; - привязать FACEIT аккаунт  
/profile - информация о профиле + базовая статистика
/stats - детальная статистика игрока
/analyze &lt;ссылка&gt; - анализ матча перед игрой
/subscription - управление подпиской
/help - показать эту справку

<b>💎 Подписки:</b>
• <b>Free:</b> 10 запросов/день, базовые функции
• <b>Premium:</b> 1000 запросов/день, расширенная аналитика
• <b>Pro:</b> Безлимит, API доступ, командные функции

<b>💡 Примеры использования:</b>
<code>/setplayer s1mple</code>
<code>/stats</code> - полная статистика
<code>/analyze https://faceit.com/en/cs2/room/1-abc-def</code> - анализ матча

Также можете просто написать никнейм игрока (например: <code>s1mple</code>) и бот автоматически найдет его.

<b>🆘 Поддержка:</b> Если есть вопросы или предложения, обратитесь к разработчику.
"""
    
    await message.answer(help_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())


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
• <b>Архитектура:</b> Микросервисная с ORM
• <b>API:</b> FACEIT Data API v4

<b>⚡ Возможности:</b>
• Анализ статистики игроков CS2
• Предматчевый анализ
• Система подписок с Telegram Stars
• Реферальная программа
• Автоматический мониторинг матчей

<b>🏗️ Компоненты:</b>
• Bot Engine: aiogram 3.x
• Cache System: Redis + Multi-level caching
• Database: PostgreSQL + JSON fallback
• Analytics: HLTV 2.1 Rating
• Performance: 4x faster analysis

<i>🚀 Готов к продакшену с PostgreSQL!</i>
"""
    
    await message.answer(version_text, parse_mode=ParseMode.HTML, reply_markup=get_main_menu())


# Admin commands with service integration
@router.message(Command("admin_health"))
async def cmd_admin_health(message: Message) -> None:
    """Admin command: Get system health with service integration."""
    if not AdminManager.is_admin(message.from_user.id):
        await message.answer("❌ Недостаточно прав доступа")
        return
    
    if not bot_adapter:
        await message.answer("⚠️ Система временно недоступна.")
        return
    
    try:
        # Get health check from integration adapter
        health = await bot_adapter.health_check()
        
        health_text = "🏥 <b>Состояние системы</b>\n\n"
        
        # Storage adapter health
        storage_health = health.get("storage_adapter", {})
        health_text += f"💾 <b>Storage:</b> {storage_health.get('backend', 'unknown')}\n"
        health_text += f"📄 JSON: {storage_health.get('json_status', 'unknown')}\n"
        health_text += f"🐘 PostgreSQL: {storage_health.get('postgresql_status', 'unknown')}\n\n"
        
        # Services health
        services = health.get("services", {})
        health_text += "🔧 <b>Сервисы:</b>\n"
        
        for service_name, service_data in services.items():
            if isinstance(service_data, dict):
                status = service_data.get("status", "unknown")
                health_text += f"• {service_name}: {status}\n"
            else:
                health_text += f"• {service_name}: {service_data}\n"
        
        health_text += f"\n⏰ <b>Время проверки:</b> {health.get('timestamp', 'unknown')}"
        
        await message.answer(health_text, parse_mode=ParseMode.HTML)
    
    except Exception as e:
        logger.error(f"Error in admin health check: {e}")
        await message.answer("❌ Ошибка при получении состояния системы")


# Payment handlers (existing implementation)
@router.pre_checkout_query()
async def handle_pre_checkout_query(pre_checkout_query: PreCheckoutQuery) -> None:
    """Handle pre-checkout query for payment validation."""
    if payment_manager is None:
        await pre_checkout_query.answer(
            ok=False,
            error_message="Платежная система временно недоступна"
        )
        return
    
    await payment_manager.handle_pre_checkout_query(pre_checkout_query)


@router.message(F.successful_payment)
async def handle_successful_payment(message: Message) -> None:
    """Handle successful payment and upgrade subscription."""
    if payment_manager is None:
        await message.answer("❌ Ошибка: платежная система недоступна")
        return
    
    success = await payment_manager.handle_successful_payment(
        message.from_user.id, 
        message.successful_payment
    )
    
    if not success:
        await message.answer(
            "❌ Произошла ошибка при активации подписки. "
            "Обратитесь в поддержку если проблема сохраняется."
        )


# Function to initialize payment manager
def init_payment_manager(bot):
    """Initialize payment manager with bot instance."""
    global payment_manager
    payment_manager = PaymentManager(bot)
    logger.info("Payment manager initialized")