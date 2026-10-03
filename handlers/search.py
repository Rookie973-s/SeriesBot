"""
User-facing search and paginated delivery.

Flow:
  1. Admins are skipped entirely - their plain text is never treated as a
     search query (avoids the bot replying to the admin's own comments).
  2. Non-admin user must have joined the required channel(s), same gate
     as /start. If not joined, they're prompted to join instead of being
     searched.
  3. User types any text in group -> bot searches series DB (this
     includes anything indexed from the channel too, since indexing
     saves the actual file straight into this same collection).
  4. First PAGE_SIZE files sent immediately.
  5. If more files exist -> "Continue?" button shown, locked to the
     original requester.
  6. If nothing is found in our DB, we no longer rely on a word
     blacklist to guess whether it's a real request. Instead we ask
     TMDB whether the text matches a real movie/show title:
       - No TMDB match  -> it's chit-chat, bot stays silent.
       - TMDB match     -> forwarded to every admin's private chat.
     Whatever the admin replies with (file/video/photo/link) is
     delivered straight to the user who asked.
"""
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TimedOut, NetworkError

from config import PAGE_SIZE, ADMIN_IDS, AUTO_DELETE_SECONDS
from utils.database import search_series
from utils.pending import add_pending
from utils.membership import check_membership
from utils.tmdb import tmdb_lookup
from utils.autodelete import autodelete_notice, schedule_autodelete

logger = logging.getLogger(__name__)

# Minimum gap between consecutive sends to the same chat. Telegram enforces
# roughly 20 messages/minute to a single group - 1.5s keeps us comfortably
# under that even with the header + files + continue button all counted.
_SEND_DELAY_SECONDS = 1.5


async def _call_with_retry(coro_func, *args, max_retries: int = 3, **kwargs):
    """
    Calls a telegram bot method, automatically waiting out flood control
    (RetryAfter) or brief network hiccups (TimedOut/NetworkError) instead
    of letting them abort the whole batch. Re-raises after max_retries so
    a genuinely broken file still gets caught by the caller's try/except.
    """
    last_exc = None
    for attempt in range(max_retries):
        try:
            return await coro_func(*args, **kwargs)
        except RetryAfter as e:
            wait = e.retry_after + 1
            logger.warning(
                "Flood control hit - waiting %.1fs before retry (attempt %d/%d)",
                wait, attempt + 1, max_retries,
            )
            await asyncio.sleep(wait)
            last_exc = e
        except (TimedOut, NetworkError) as e:
            logger.warning(
                "Transient network error - retrying in 2s (attempt %d/%d): %s",
                attempt + 1, max_retries, e,
            )
            await asyncio.sleep(2)
            last_exc = e
    raise last_exc


# Telegram's system account used when a group admin/owner sends "anonymously"
# (posting as the group itself). In that mode, update.effective_user is this
# bot account, NOT the admin's real user ID - so an ADMIN_IDS check alone
# will never catch it.
GROUP_ANONYMOUS_BOT_ID = 1087968824


# ─── Cheap pre-filter (kept only to avoid pointless TMDB calls) ────────────
# This is NOT the gate that decides "reply or not" anymore - TMDB is.
# It just skips obviously-not-a-title text (long sentences, punctuation-
# heavy chatter) before bothering to hit the API at all.
_STRIP_CHARS = ".,!?🙏😂😍❤️👍🔥💯🙌😊👌✅🎉"


def _worth_checking_tmdb(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False

    words = stripped.split()

    # Titles are almost never longer than ~6 words
    if len(words) > 6:
        return False

    # Sentence-like punctuation strongly suggests chit-chat, not a title
    if any(p in stripped for p in ("!", "?", "...", "..")):
        return False
    if stripped.count(".") > 1:
        return False

    return True


async def _gate_on_membership(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Returns True if the user is allowed to proceed (has joined required
    channels). If not, sends a join-prompt (same style as /start) and
    returns False so the caller can stop processing.
    """
    user = update.effective_user
    not_joined = await check_membership(context.bot, user.id)
    if not not_joined:
        return True

    buttons = [
        [InlineKeyboardButton(f"📢 Join {ch['name']}", url=ch["url"])]
        for ch in not_joined
    ]
    await update.message.reply_text(
        "🔒 Please join our channel(s) first to search for series:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return False


async def text_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered on any plain text message - searches for a matching series."""
    message = update.message
    if not message or not message.text:
        return

    user = update.effective_user

    # ── Never treat admin chatter as a search request ──────────────────
    # Covers both a normal admin account AND an admin posting anonymously
    # "as the group" (message.sender_chat is set, and/or the sender shows
    # up as Telegram's GroupAnonymousBot).
    if message.sender_chat is not None:
        return
    if user.id in ADMIN_IDS or user.id == GROUP_ANONYMOUS_BOT_ID:
        return

    query = message.text.strip()

    # Ignore commands
    if query.startswith("/"):
        return

    # ── Must have joined required channel(s) before we respond at all ──
    if not await _gate_on_membership(update, context):
        return

    series = await search_series(query)

    if not series:
        # Cheap pre-filter first (saves an API call on obvious chit-chat)
        if not _worth_checking_tmdb(query):
            return

        # Real gate: does TMDB recognize this as an actual title?
        match = await tmdb_lookup(query)
        if not match:
            return  # not a recognizable title -> stay quiet

        await message.reply_text(
            f"🔍 *{query}* isn't available for instant response.\n"
            f"Our admins are reviewing your request. Please wait a moment, it'll be posted.",
            parse_mode=ParseMode.MARKDOWN,
        )

        # ── Forward the request to every admin's private chat ──────────
        requester = f"@{user.username}" if user.username else user.full_name
        chat_title = message.chat.title or "Private chat"

        for admin_id in ADMIN_IDS:
            try:
                sent = await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"📩 *New request*\n\n"
                        f"👤 {requester}\n"
                        f"💬 From: {chat_title}\n"
                        f"🔎 Query: `{query}`\n"
                        f"🎬 TMDB match: *{match['title']}* ({match['media_type']})\n\n"
                        f"↩️ Reply to *this* message with the file, video, photo, "
                        f"or a link (`Label | URL`) to send it straight to the user."
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                )
                add_pending(
                    admin_message_id=sent.message_id,
                    user_id=user.id,
                    chat_id=message.chat_id,
                    message_id=message.message_id,
                    query=query,
                )
            except Exception:
                # Admin may not have DM'd the bot yet - skip silently
                continue

        return

    files = series.get("files", [])
    title = series["title"]

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

    hours = AUTO_DELETE_SECONDS / 3600
    hours_str = f"{hours:.0f}" if hours == int(hours) else f"{hours:.1f}"

    # ── Header message ────────────────────────────────────────
    header = (
        f"📺 *{title}*\n"
        f"Sending {len(chunk)} file{'s' if len(chunk) != 1 else ''} "
        f"(Part {page + 1}/{pages})...\n"
        f"⏳ Files auto-delete after {hours_str}h — save them to your device!"
    )
    kwargs = {"chat_id": chat_id, "text": header, "parse_mode": ParseMode.MARKDOWN}
    if reply_to:
        kwargs["reply_to_message_id"] = reply_to

    await _call_with_retry(context.bot.send_message, **kwargs)

    # ── Send files ────────────────────────────────────────────
    failed = []
    for i, f in enumerate(chunk):
        file_id   = f["file_id"]
        file_type = f.get("file_type", "document")
        base_caption = f.get("caption", f"🎬 *{title}*")
        # No real "file" to save for a plain link/button - skip the warning there.
        caption = base_caption + (autodelete_notice() if file_type != "text" else "")

        try:
            sent_msg = await _send_file(context, chat_id, file_id, file_type, caption, extra=f)
            if sent_msg is not None:
                schedule_autodelete(context, chat_id, sent_msg.message_id)
        except Exception:
            failed.append(f.get("name") or base_caption or f"file #{start + i + 1}")
            logger.exception(
                "Failed to send file for series '%s' (index %d in DB list)",
                title, start + i,
            )

        if i < len(chunk) - 1:
            await asyncio.sleep(_SEND_DELAY_SECONDS)

    if failed:
        await _call_with_retry(
            context.bot.send_message,
            chat_id=chat_id,
            text=(
                "⚠️ Couldn't send " + str(len(failed)) + " file(s) in this batch "
                "(likely an expired or broken file). Skipped so the rest could "
                "still go through:\n" + "\n".join(f"• {name}" for name in failed)
            ),
        )


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
        try:
            await _call_with_retry(
                context.bot.send_message,
                chat_id=chat_id,
                text=f"✅ Part {page + 1} sent! Tap to get the next batch.",
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            logger.exception(
                "Failed to send Continue button for '%s' page %d (callback_data=%r)",
                title, page + 1, callback_data,
            )
            await _call_with_retry(
                context.bot.send_message,
                chat_id=chat_id,
                text=(
                    f"✅ Part {page + 1} sent, but I couldn't build the Continue "
                    f"button ({remaining} file{'s' if remaining != 1 else ''} left). "
                    f"Type the series name again to get more."
                ),
            )
    else:
        await _call_with_retry(
            context.bot.send_message,
            chat_id=chat_id,
            text=f"✅ All {total} file{'s' if total != 1 else ''} for *{title}* sent!",
            parse_mode=ParseMode.MARKDOWN,
        )


async def _send_file(context, chat_id: int, file_id: str, file_type: str, caption: str, extra: dict = None):
    """Sends the file/link and returns the resulting Message (or None)."""
    bot = context.bot
    kwargs = dict(chat_id=chat_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
    if file_type == "document":
        return await _call_with_retry(bot.send_document, document=file_id, **kwargs)
    elif file_type == "video":
        return await _call_with_retry(bot.send_video, video=file_id, **kwargs)
    elif file_type == "photo":
        return await _call_with_retry(bot.send_photo, photo=file_id, **kwargs)
    elif file_type == "text":
        url = (extra or {}).get("text", "")
        if url.startswith("http://") or url.startswith("https://"):
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton(caption.strip("🎬 *_") or "Open", url=url)]]
            )
            return await _call_with_retry(
                bot.send_message, chat_id=chat_id, text=caption,
                parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard,
            )
        else:
            return await _call_with_retry(
                bot.send_message, chat_id=chat_id, text=f"{caption}\n\n{url}",
                parse_mode=ParseMode.MARKDOWN,
            )
    return None
