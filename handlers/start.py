from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from utils.database import save_user
from utils.membership import check_membership
from config import BOT_NAME


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user.id, user.username, user.full_name)

    not_joined = await check_membership(context.bot, user.id)

    if not_joined:
        buttons = []
        for ch in not_joined:
            buttons.append([InlineKeyboardButton(f"📢 Join {ch['name']}", url=ch["url"])])
        buttons.append([InlineKeyboardButton("✅ Done — Let Me In", callback_data="verify_start")])

        await update.message.reply_text(
            f"👋 Welcome to *{BOT_NAME}*!\n\n"
            f"To access the series library, please join our channel(s) first:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    await update.message.reply_text(
        f"🎬 Welcome to *{BOT_NAME}*!\n\n"
        f"Simply type the name of any series and I'll send you the files.\n\n"
        f"Example: _Stranger Things_, _Breaking Bad_, _Money Heist_\n\n"
        f"📢 Join our channel to stay updated with new additions!",
        parse_mode=ParseMode.MARKDOWN,
    )
