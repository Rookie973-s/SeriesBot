"""
User-facing search and paginated delivery.

Flow:
  1. User types any text in group → bot searches series DB
  2. First PAGE_SIZE files sent immediately
  3. If more files exist → "Continue?" button shown
  4. Button callback is locked to the original requester
"""
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import PAGE_SIZE
from utils.database import search_series


async def text_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered on any plain text message — searches for a matching series."""
    message = update.message
    if not message or not message.text:
        return

    query = message.text.strip()

    # Ignore commands
    if query.startswith("/"):
        return

    series = await search_series(query)

    if not series:
        # Don't spam the group with "not found" for every message
        # Only reply if it looks intentional (3+ chars, no spaces before short words)
       await message.reply_text(
                f"🔍 *{query}* isn't available for instant response.\n"
                f"Our admins are reviewing your request. Please wait a moment, it'll be posted.",
                parse_mode=ParseMode.MARKDOWN,
            )
  
        return

    files = series.get("files", [])
    title = series["title"]
    user  = update.effective_user

    await _send_page(
        context=context,
        chat_id=message.chat_id,
        reply_to=message.message_id,
        user_id=user.id,
        title=title,
        files=files,
        page=0,
    )


async def pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Callback data format:  series_page|<user_id>|<title_lower>|<page>
    Only the original requester can trigger this.
    """
    query = update.callback_query
    await query.answer()

    data = query.data  # "series_page|123456789|stranger things|1"
    parts = data.split("|")

    if len(parts) != 4:
        return

    _, owner_id_str, title_lower, page_str = parts
    owner_id = int(owner_id_str)
    page     = int(page_str)

    # ── Lock check ────────────────────────────────────────────
    caller_id = update.effective_user.id
    if caller_id != owner_id:
        await query.answer(
            "⛔ This is not your request.",
            show_alert=True,   # pops up as an alert, not just a toast
        )
        return

    # ── Fetch series ──────────────────────────────────────────
    series = await search_series(title_lower)
    if not series:
        await query.edit_message_text("⚠️ This series no longer exists.")
        return

    files = series.get("files", [])
    title = series["title"]

    # Remove the "Continue?" button from the previous message
    await query.edit_message_reply_markup(reply_markup=None)

    await _send_page(
        context=context,
        chat_id=update.effective_chat.id,
        reply_to=None,
        user_id=owner_id,
        title=title,
        files=files,
        page=page,
    )

# ─── Core delivery ────────────────────────────────────────────────────────────

async def _send_page(
    context,
    chat_id: int,
    reply_to: int | None,
    user_id: int,
    title: str,
    files: list,
    page: int,
):
    """Send one page of files. Appends a Continue button if more pages exist."""
    start = page * PAGE_SIZE
    end   = start + PAGE_SIZE
    chunk = files[start:end]
    total = len(files)
    pages = -(-total // PAGE_SIZE)  # ceiling division

    # ── Header message ────────────────────────────────────────
    header = (
        f"📺 *{title}*\n"
        f"Sending {len(chunk)} file{'s' if len(chunk) != 1 else ''} "
        f"(Part {page + 1}/{pages})..."
    )
    kwargs = {"chat_id": chat_id, "text": header, "parse_mode": ParseMode.MARKDOWN}
    if reply_to:
        kwargs["reply_to_message_id"] = reply_to

    await context.bot.send_message(**kwargs)

    # ── Send files ────────────────────────────────────────────
    for i, f in enumerate(chunk):
        file_id   = f["file_id"]
        file_type = f.get("file_type", "document")
        caption   = f.get("caption", f"🎬 *{title}*")

        await _send_file(context.bot, chat_id, file_id, file_type, caption, extra=f)


        if i < len(chunk) - 1:
            await asyncio.sleep(0.4)

    # ── Continue button if more pages ─────────────────────────
    if end < total:
        remaining = total - end
        callback_data = f"series_page|{user_id}|{title.lower()}|{page + 1}"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"▶️ Continue sending? ({remaining} file{'s' if remaining != 1 else ''} left)",
                callback_data=callback_data,
            )]
        ])
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Part {page + 1} sent! Tap to get the next batch.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ All {total} file{'s' if total != 1 else ''} for *{title}* sent!",
            parse_mode=ParseMode.MARKDOWN,
        )


async def _send_file(bot, chat_id: int, file_id: str, file_type: str, caption: str, extra: dict = None):
    kwargs = dict(chat_id=chat_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
    if file_type == "document":
        await bot.send_document(document=file_id, **kwargs)
    elif file_type == "video":
        await bot.send_video(video=file_id, **kwargs)
    elif file_type == "photo":
        await bot.send_photo(photo=file_id, **kwargs)
    elif file_type == "text":
        url = (extra or {}).get("text", "")
        if url.startswith("http://") or url.startswith("https://"):
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton(caption.strip("🎬 *_") or "Open", url=url)]]
            )
            await bot.send_message(chat_id=chat_id, text=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        else:
            await bot.send_message(chat_id=chat_id, text=f"{caption}\n\n{url}", parse_mode=ParseMode.MARKDOWN)
