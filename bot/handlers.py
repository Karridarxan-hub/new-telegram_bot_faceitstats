"""Bot command handlers."""

import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode

from faceit.api import FaceitAPI, FaceitAPIError
from utils.storage import storage, UserData
from utils.formatter import MessageFormatter

logger = logging.getLogger(__name__)

router = Router()
faceit_api = FaceitAPI()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Handle /start command."""
    welcome_text = """
🎮 **Добро пожаловать в FACEIT Stats Bot!**

Этот бот поможет вам отслеживать статистику ваших матчей в CS2 на платформе FACEIT\\.

**Доступные команды:**
/setplayer <nickname> \\- привязать FACEIT аккаунт
/lastmatch \\- показать последний матч
/matches \\[количество\\] \\- показать последние матчи \\(по умолчанию 5\\)
/profile \\- показать информацию о профиле
/help \\- показать справку

**Для начала работы:**
1\\. Используйте команду /setplayer с вашим никнеймом в FACEIT
2\\. Бот автоматически будет уведомлять вас о новых матчах

Пример: `/setplayer YourNickname`
"""
    
    await message.answer(welcome_text, parse_mode=ParseMode.MARKDOWN_V2)


@router.message(Command("setplayer"))
async def cmd_set_player(message: Message) -> None:
    """Handle /setplayer command."""
    if not message.text:
        return
        
    args = message.text.split()[1:]
    if not args:
        await message.answer(
            "Укажите ваш никнеим в FACEIT\\.\n"
            "Пример: `/setplayer YourNickname`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    nickname = " ".join(args).strip()
    await message.answer("🔍 Ищу игрока\\.\\.\\.", parse_mode=ParseMode.MARKDOWN_V2)
    
    try:
        player = await faceit_api.search_player(nickname)
        if not player:
            await message.answer(
                f"❌ Игрок с никнеймом \"{nickname}\" не найден\\. "
                "Проверьте правильность написания\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        user_data = UserData(
            user_id=message.from_user.id,
            faceit_player_id=player.player_id,
            faceit_nickname=player.nickname
        )
        await storage.save_user(user_data)
        
        player_info = MessageFormatter.format_player_info(player)
        success_text = f"✅ Игрок успешно привязан\\!\\n\\n{player_info}"
        
        await message.answer(success_text, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"User {message.from_user.id} linked player {player.nickname}")
        
    except FaceitAPIError as e:
        logger.error(f"FACEIT API error in set_player: {e}")
        await message.answer(
            "❌ Произошла ошибка при поиске игрока\\. Попробуйте позже\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Unexpected error in set_player: {e}")
        await message.answer(
            "❌ Произошла непредвиденная ошибка\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )


@router.message(Command("lastmatch"))
async def cmd_last_match(message: Message) -> None:
    """Handle /lastmatch command."""
    user = await storage.get_user(message.from_user.id)
    if not user or not user.faceit_player_id:
        await message.answer(
            "❌ Сначала привяжите свой FACEIT аккаунт командой /setplayer",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    await message.answer(
        "🔍 Получаю данные о последнем матче\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    
    try:
        matches = await faceit_api.get_player_matches(user.faceit_player_id, limit=1)
        if not matches:
            await message.answer(
                "❌ Матчи не найдены\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        match = matches[0]
        if match.status != "FINISHED":
            await message.answer(
                "⏳ Последний матч еще не завершен\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        stats = await faceit_api.get_match_stats(match.match_id)
        formatted_message = MessageFormatter.format_match_result(
            match, stats, user.faceit_player_id
        )
        
        await message.answer(formatted_message, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Sent last match info to user {message.from_user.id}")
        
    except FaceitAPIError as e:
        logger.error(f"FACEIT API error in last_match: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении данных матча\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Unexpected error in last_match: {e}")
        await message.answer(
            "❌ Произошла непредвиденная ошибка\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )


@router.message(Command("matches"))
async def cmd_matches(message: Message) -> None:
    """Handle /matches command."""
    user = await storage.get_user(message.from_user.id)
    if not user or not user.faceit_player_id:
        await message.answer(
            "❌ Сначала привяжите свой FACEIT аккаунт командой /setplayer",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    # Parse limit from command
    limit = 5
    if message.text:
        args = message.text.split()[1:]
        if args and args[0].isdigit():
            limit = min(int(args[0]), 20)
    
    await message.answer(
        f"🔍 Получаю данные о последних {limit} матчах\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    
    try:
        matches = await faceit_api.get_player_matches(user.faceit_player_id, limit=limit)
        finished_matches = [match for match in matches if match.status == "FINISHED"]
        
        if not finished_matches:
            await message.answer(
                "❌ Завершенные матчи не найдены\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        formatted_message = MessageFormatter.format_matches_list(
            finished_matches, user.faceit_player_id
        )
        
        await message.answer(formatted_message, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Sent matches list to user {message.from_user.id}")
        
    except FaceitAPIError as e:
        logger.error(f"FACEIT API error in matches: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении данных матчей\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Unexpected error in matches: {e}")
        await message.answer(
            "❌ Произошла непредвиденная ошибка\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    """Handle /profile command."""
    user = await storage.get_user(message.from_user.id)
    if not user or not user.faceit_player_id:
        await message.answer(
            "❌ Сначала привяжите свой FACEIT аккаунт командой /setplayer",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    
    await message.answer(
        "🔍 Получаю информацию о профиле\\.\\.\\.",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    
    try:
        player = await faceit_api.get_player_by_id(user.faceit_player_id)
        if not player:
            await message.answer(
                "❌ Не удалось получить информацию о профиле\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return
        
        formatted_message = MessageFormatter.format_player_info(player)
        await message.answer(formatted_message, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"Sent profile info to user {message.from_user.id}")
        
    except FaceitAPIError as e:
        logger.error(f"FACEIT API error in profile: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении информации о профиле\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Unexpected error in profile: {e}")
        await message.answer(
            "❌ Произошла непредвиденная ошибка\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command."""
    help_text = """
**🎮 FACEIT Stats Bot \\- Справка**

**Доступные команды:**

/start \\- начать работу с ботом
/setplayer <nickname> \\- привязать FACEIT аккаунт
/lastmatch \\- показать последний завершенный матч с детальной статистикой
/matches \\[количество\\] \\- показать список последних матчей \\(максимум 20\\)
/profile \\- показать информацию о вашем FACEIT профиле
/help \\- показать эту справку

**Автоматические уведомления:**
Бот автоматически отправляет уведомления о завершенных матчах с детальной статистикой\\.

**Примеры использования:**
`/setplayer s1mple`
`/matches 10`
`/lastmatch`

**Поддержка:** Если у вас есть вопросы или предложения, обратитесь к разработчику\\.
"""
    
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN_V2)