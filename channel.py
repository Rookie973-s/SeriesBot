"""
Indexing for the source channel where files already live.

Two ways an entry gets indexed:
  1. Automatically — every new post in the channel is indexed using its
     caption/text as the title.
  2. Manually — admin forwards an existing OLD channel post into their
     private chat with the bot, then replies to it with
     /indexchannel <Title>
     This is how you back-index everything already posted before the bot
     existed.
"""
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import ADMIN_IDS, CHANNEL_ID
from utils.database import save_channel_entry


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ─── Auto-index new channel posts ──────────────────────────────────────────

async def auto_index_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = update.channel_post
    if not post or post.chat_id != CHANNEL_ID:
        return

    title = (post.caption or post.text or "").strip()
    if not title:
        return  # nothing to index it by — e.g. a bare video with no caption

    if "|" in title:
        title = title.split("|", 1)[0].strip()

    await save_channel_entry(title, post.message_id)


# ─── Manual /indexchannel command (for back-indexing old posts) ───────────

async def indexchannel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    message = update.message

    if not context.args:
        await message.reply_text(
            "⚠️ Usage: forward a post from the channel here, then *reply* to it with:\n"
            "`/indexchannel <Title>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not message.reply_to_message:
        await message.reply_text(
            "⚠️ Reply to a message that was forwarded from the channel.\n"
            "1. Forward the post from the channel into this chat.\n"
            "2. Reply to it with `/indexchannel <Title>`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    fwd = message.reply_to_message
    origin_chat_id = None
    origin_message_id = None

    # PTB v20+ / Bot API 7+
    if getattr(fwd, "forward_origin", None) and hasattr(fwd.forward_origin, "chat"):
        origin_chat_id = fwd.forward_origin.chat.id
        origin_message_id = fwd.forward_origin.message_id
    # Older Bot API fallback
    elif getattr(fwd, "forward_from_chat", None):
        origin_chat_id = fwd.forward_from_chat.id
        origin_message_id = fwd.forward_from_message_id

    if origin_chat_id != CHANNEL_ID or not origin_message_id:
        await message.reply_text(
            "⚠️ That message doesn't look like it was forwarded from your source channel."
        )
        return

    title = " ".join(context.args)
    await save_channel_entry(title, origin_message_id)

    await message.reply_text(
        f"✅ Indexed *{title}* → channel message `{origin_message_id}`.",
        parse_mode=ParseMode.MARKDOWN,
    )
