"""
Indexing for the source channel where files already live.

Two ways an entry gets indexed — both now save the ACTUAL FILE into the
main series collection (same one /addseries uses), not just a pointer to
the channel post. This means delivery never depends on the channel again.

  1. Automatically — every new post in the channel is indexed using its
     caption or filename as the title.
  2. Manually, one at a time — admin forwards an old channel post into
     their private chat with the bot, then replies to it with:
       /indexchannel <Title>

For bulk back-indexing many old files at once, see /startindex and
/stopindex in handlers/admin.py — that lets you just forward a whole
batch of files and each gets saved under its own title automatically.
"""
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import ADMIN_IDS, CHANNEL_ID
from utils.database import add_series_file
from utils.indexing import derive_title_and_entry


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ─── Auto-index new channel posts ──────────────────────────────────────────

async def auto_index_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = update.channel_post
    if not post or post.chat_id != CHANNEL_ID:
        return

    title, entry = derive_title_and_entry(post)
    if not title:
        return  # nothing usable to index it by

    await add_series_file(title, entry)


# ─── Manual /indexchannel command (index one specific old post) ───────────

async def indexchannel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    message = update.message

    if not context.args:
        await message.reply_text(
            "⚠️ Usage: forward a post from the channel here, then *reply* to it with:\n"
            "`/indexchannel <Title>`\n\n"
            "Tip: for indexing many old files at once, use /startindex instead.",
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

    _, entry = derive_title_and_entry(fwd)
    if not entry:
        await message.reply_text("⚠️ That message doesn't contain a supported file, video, photo, or link.")
        return

    title = " ".join(context.args)
    await add_series_file(title, entry)

    await message.reply_text(
        f"✅ Indexed *{title}* — file saved and searchable now.",
        parse_mode=ParseMode.MARKDOWN,
    )
