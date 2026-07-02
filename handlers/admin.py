"""
Admin commands for SeriesBot.

/addseries <Title>          — Start a series upload session
/done                       — Finalise the session and save to DB
/cancel                     — Abort the session
/delseries <Title>          — Delete a series
/listall                    — List all stored series titles
/botstats                   — Show stats
"""
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import ADMIN_IDS, PAGE_SIZE
from utils.database import (
    save_series,
    delete_series,
    get_all_series_titles,
    count_series,
)

# In-memory session per admin: { admin_id: { "title": str, "files": [] } }
_sessions: dict[int, dict] = {}


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


# ─── File upload handler (during session) ────────────────────────────────────

async def upload_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receives files from admin during an active session."""
    user = update.effective_user
    if not is_admin(user.id):
        return

    session = _sessions.get(user.id)
    if not session:
        return

    message = update.message

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

    await update.message.reply_text(
        f"📊 *SeriesBot Stats*\n\n"
        f"📺 Total series: `{total}`\n\n"
        f"{session_line}"
        f"*Admin Commands:*\n"
        f"`/addseries <Title>` — Start upload session\n"
        f"`/done` — Save & finish\n"
        f"`/cancel` — Abort session\n"
        f"`/delseries <Title>` — Delete a series\n"
        f"`/listall` — List all series\n"
        f"`/botstats` — This panel",
        parse_mode=ParseMode.MARKDOWN,
    )
