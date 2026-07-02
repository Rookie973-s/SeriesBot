from telegram import Bot
from telegram.error import TelegramError
from config import REQUIRED_CHANNELS


async def check_membership(bot: Bot, user_id: int) -> list[dict]:
    """
    Returns list of channels the user has NOT joined.
    Empty list = all good.
    """
    not_joined = []
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(channel["username"], user_id)
            if member.status in ("left", "kicked"):
                not_joined.append(channel)
        except TelegramError:
            not_joined.append(channel)
    return not_joined
