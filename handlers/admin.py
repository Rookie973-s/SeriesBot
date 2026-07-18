"""
Admin commands for SeriesBot.

/addseries <Title>          — Start a series upload session
/done                       — Finalise the session and save to DB
/cancel                     — Abort the session
/delseries <Title>          — Delete a series
/listall                    — List all stored series titles
/botstats                   — Show stats
/startindex                 — Start bulk-indexing mode (forward old channel
                               files here, one after another — each gets
                               saved under its own title automatically)
/stopindex                  — Stop bulk-indexing mode

Also handles: admin replying (in DM with the bot) to a forwarded user
request — that reply gets delivered straight to whoever asked.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import ADMIN_IDS, PAGE_SIZE
from utils.database import (
    save_series,
    add_series_file,
    delete_series,
    get_all_series_titles,
    count_series,
)
from utils.pending import get_pending, pop_pending
from utils.indexing import derive_title_and_entry
from utils.autodelete import autodelete_notice, schedule_autodelete

# In-memory session per admin: { admin_id: { "title": str, "files": [] } }
_sessions: dict[int, dict] = {}

# Admins currently in bulk-indexing mode (forwarding old channel files)
_index_sessions: set[int] = set()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ─── /addseries ───────────────────────────────────────────────────────────────

async def addseries_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Usage: `/addseries <Title>`\nExample: `/addseries Stranger Things`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    title = " ".join(context.args)
    _sessions[user.id] = {"title": title, "files": []}

    await update.message.reply_text(
        f"📺 *Series session started!*\n\n"
        f"Title: *{title}*\n\n"
        f"Now send me the files/videos one by one.\n"
        f"Type /done when finished, or /cancel to abort.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /startindex, /stopindex — bulk indexing mode ──────────────────────────

async def startindex_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    _index_sessions.add(user.id)
    await update.message.reply_text(
        "📥 *Bulk indexing mode ON.*\n\n"
        "Forward old files from the channel here now, one after another.\n"
        "Each file will be saved under its own title, taken from its "
        "caption (or filename if there's no caption).\n\n"
        "Type /stopindex when you're done.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def stopindex_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    _index_sessions.discard(user.id)
    await update.message.reply_text("✅ Bulk indexing mode OFF.")


# ─── File upload handler ───────────────────────────────────────────────────
# Handles three distinct situations, in this order:
#   1. Admin is replying to a forwarded user request → deliver to that user
#   2. Admin is in bulk-indexing mode → auto-save this file under its own title
#   3. Admin is inside an /addseries session → add file to that session

async def upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    message = update.message

    # ── Case 1: this is a reply fulfilling a forwarded user request ────────
    if message.reply_to_message:
        pending = get_pending(message.reply_to_message.message_id)
        if pending:
            await _fulfill_request(message, context, pending)
            return

    # ── Case 2: bulk indexing mode — save this file under its own title ────
    if user.id in _index_sessions:
        title, entry = derive_title_and_entry(message)
        if not title:
            await message.reply_text(
                "⚠️ Couldn't find a title for that (no caption or filename) — skipped."
            )
            return

        await add_series_file(title, entry)
        await message.reply_text(f"✅ Indexed *{title}*", parse_mode=ParseMode.MARKDOWN)
        return

    # ── Case 3: part of an active /addseries session ────────────────────────
    session = _sessions.get(user.id)
    if not session:
        return

    file_id = None
    file_type = None
    name = None
    text_content = None

    if message.document:
        file_id   = message.document.file_id
        file_type = "document"
        name      = message.document.file_name or "File"
    elif message.video:
        file_id   = message.video.file_id
        file_type = "video"
        name      = message.caption or f"Episode {len(session['files']) + 1}"
    elif message.photo:
        file_id   = message.photo[-1].file_id
        file_type = "photo"
        name      = message.caption or "Photo"
    elif message.text:
        # Plain link, or "Label | URL" for a labeled button
        file_type = "text"
        raw = message.text.strip()
        if "|" in raw:
            label, _, url = raw.partition("|")
            name = label.strip()
            text_content = url.strip()
        else:
            name = f"Link {len(session['files']) + 1}"
            text_content = raw
    else:
        return

    caption = message.caption or f"🎬 *{name}* — *{session['title']}*"

    entry = {
        "file_id":   file_id,
        "file_type": file_type,
        "caption":   caption,
        "name":      name,
    }
    if text_content is not None:
        entry["text"] = text_content

    session["files"].append(entry)

    count = len(session["files"])
    await message.reply_text(
        f"✅ Added *{name}* ({count} file{'s' if count != 1 else ''} so far).\n"
        f"Send more or type /done to finish.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── Fulfilling a forwarded user request ───────────────────────────────────────

async def _fulfill_request(message, context: ContextTypes.DEFAULT_TYPE, pending: dict):
    """Delivers the admin's reply (file/video/photo/link) to the original
    user who asked, as a reply to their original message."""
    target_chat_id    = pending["chat_id"]
    target_message_id = pending["message_id"]
    query              = pending["query"]

    caption_default = f"🎬 Result to your request: *{query}*"

    try:
        if message.document:
            caption = (message.caption or caption_default) + autodelete_notice()
            sent = await context.bot.send_document(
                chat_id=target_chat_id,
                document=message.document.file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=target_message_id,
            )
            schedule_autodelete(context, target_chat_id, sent.message_id)
        elif message.video:
            caption = (message.caption or caption_default) + autodelete_notice()
            sent = await context.bot.send_video(
                chat_id=target_chat_id,
                video=message.video.file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=target_message_id,
            )
            schedule_autodelete(context, target_chat_id, sent.message_id)
        elif message.photo:
            caption = (message.caption or caption_default) + autodelete_notice()
            sent = await context.bot.send_photo(
                chat_id=target_chat_id,
                photo=message.photo[-1].file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=target_message_id,
            )
            schedule_autodelete(context, target_chat_id, sent.message_id)
        elif message.text:
            raw = message.text.strip()
            if "|" in raw:
                label, _, url = raw.partition("|")
                label = label.strip()
                url   = url.strip()
            else:
                label = None
                url   = raw

            if url.startswith("http://") or url.startswith("https://"):
                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton(label or "Open", url=url)]]
                )
                await context.bot.send_message(
                    chat_id=target_chat_id,
                    text=caption_default,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard,
                    reply_to_message_id=target_message_id,
                )
                # Just a link/button, nothing to "save to device" - not auto-deleted.
            else:
                await context.bot.send_message(
                    chat_id=target_chat_id,
                    text=f"{caption_default}\n\n{raw}",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_to_message_id=target_message_id,
                )
        else:
            await message.reply_text(
                "⚠️ Unsupported content — send a document, video, photo, or link."
            )
            return

        pop_pending(message.reply_to_message.message_id)
        await message.reply_text("✅ Sent to the user!")

    except Exception as e:
        await message.reply_text(f"⚠️ Failed to deliver to user: {e}")


# ─── /done ────────────────────────────────────────────────────────────────────

async def done_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    session = _sessions.get(user.id)
    if not session:
        await update.message.reply_text("⚠️ No active session. Use /addseries first.")
        return

    files = session["files"]
    if not files:
        await update.message.reply_text("⚠️ No files added yet. Send some files first.")
        return

    title = session["title"]
    await save_series(title, files)
    del _sessions[user.id]

    pages = -(-len(files) // PAGE_SIZE)  # ceiling division
    await update.message.reply_text(
        f"✅ *{title}* saved!\n\n"
        f"📁 {len(files)} file{'s' if len(files) != 1 else ''} across {pages} page{'s' if pages != 1 else ''}.\n\n"
        f"Users can now find it by typing the series name.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /cancel ─────────────────────────────────────────────────────────────────

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    if user.id in _sessions:
        del _sessions[user.id]
        await update.message.reply_text("🚫 Session cancelled.")
    else:
        await update.message.reply_text("No active session.")


# ─── /delseries ───────────────────────────────────────────────────────────────

async def delseries_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Usage: `/delseries <Title>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    title = " ".join(context.args)
    deleted = await delete_series(title)

    if deleted:
        await update.message.reply_text(f"🗑️ *{title}* deleted.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(
            f"⚠️ No series found with title `{title}`.",
            parse_mode=ParseMode.MARKDOWN,
        )


# ─── /listall ─────────────────────────────────────────────────────────────────

async def listall_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    titles = await get_all_series_titles()
    if not titles:
        await update.message.reply_text("📭 No series stored yet.")
        return

    lines = ["📺 *All Series*\n"]
    for i, t in enumerate(titles, 1):
        lines.append(f"{i}. {t}")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
    )


# ─── /botstats ────────────────────────────────────────────────────────────────

async def botstats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return

    total = await count_series()
    active = _sessions.get(user.id)
    session_line = (
        f"🔄 Active session: *{active['title']}* ({len(active['files'])} files staged)\n"
        if active else ""
    )
    indexing_line = "📥 Bulk indexing mode: *ON*\n" if user.id in _index_sessions else ""

    await update.message.reply_text(
        f"📊 *SeriesBot Stats*\n\n"
        f"📺 Total series: `{total}`\n\n"
        f"{session_line}"
        f"{indexing_line}"
        f"*Admin Commands:*\n"
        f"`/addseries <Title>` — Start upload session\n"
        f"`/done` — Save & finish\n"
        f"`/cancel` — Abort session\n"
        f"`/delseries <Title>` — Delete a series\n"
        f"`/listall` — List all series\n"
        f"`/startindex` — Bulk-index forwarded channel files\n"
        f"`/stopindex` — Stop bulk indexing\n"
        f"`/botstats` — This panel",
        parse_mode=ParseMode.MARKDOWN,
    )
