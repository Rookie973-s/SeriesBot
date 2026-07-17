import logging
import time
from telegram import Update
from telegram.error import Conflict
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from config import BOT_TOKEN, ADMIN_IDS, CHANNEL_ID
from handlers.admin import (
    addseries_handler,
    upload_handler,
    done_handler,
    cancel_handler,
    delseries_handler,
    listall_handler,
    botstats_handler,
    startindex_handler,
    stopindex_handler,
)
from handlers.search import text_search_handler, pagination_callback
from handlers.channel import auto_index_channel_post, indexchannel_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─── Global error handler ──────────────────────────────────────────────────
# Catches anything unhandled anywhere in the bot so it gets logged (and
# optionally reported to admins) instead of failing silently.
_last_notified: dict[str, float] = {}
_NOTIFY_COOLDOWN_SECONDS = 600  # don't re-DM admins about the same error more than once per 10 min


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception while processing an update:", exc_info=context.error)

    # 409 Conflict happens when two pollers briefly overlap (e.g. during a
    # redeploy) and self-resolves once the old process stops - PTB already
    # retries automatically. If it keeps happening past a redeploy, it means
    # a second instance is genuinely still running somewhere; don't spam
    # admins for every retry attempt either way, log is enough for this one.
    if isinstance(context.error, Conflict):
        return

    # Cooldown: same error type+message won't re-notify within the window,
    # so a fast-repeating failure doesn't flood admin DMs.
    key = f"{type(context.error).__name__}:{str(context.error)[:100]}"
    now = time.monotonic()
    if now - _last_notified.get(key, 0) < _NOTIFY_COOLDOWN_SECONDS:
        return
    _last_notified[key] = now

    error_text = f"⚠️ Bot error:\n`{context.error}`"
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=error_text[:4000])
        except Exception:
            continue


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # ── Global error handler ───────────────────────────────────
    app.add_error_handler(error_handler)

    # ── Admin commands ─────────────────────────────────────────
    app.add_handler(CommandHandler("addseries", addseries_handler))
    app.add_handler(CommandHandler("done",       done_handler))
    app.add_handler(CommandHandler("cancel",     cancel_handler))
    app.add_handler(CommandHandler("delseries",  delseries_handler))
    app.add_handler(CommandHandler("listall",    listall_handler))
    app.add_handler(CommandHandler("botstats",   botstats_handler))
    app.add_handler(CommandHandler("indexchannel", indexchannel_handler))
    app.add_handler(CommandHandler("startindex", startindex_handler))
    app.add_handler(CommandHandler("stopindex",  stopindex_handler))

    # ── Auto-index new posts from the source channel ───────────
    app.add_handler(MessageHandler(filters.Chat(chat_id=CHANNEL_ID), auto_index_channel_post))

    # ── Admin file uploads (session, bulk-index, or fulfilling a request) ──
    app.add_handler(
        MessageHandler(
            filters.User(user_id=ADMIN_IDS) & (
                filters.Document.ALL | filters.VIDEO | filters.PHOTO | filters.TEXT
            ),
            upload_handler,
        )
    )

    # ── Pagination callback (user-locked) ─────────────────────
    app.add_handler(CallbackQueryHandler(pagination_callback, pattern=r"^series_page\|"))

    # ── User text search (must be last — catches all text) ────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_search_handler))

    if app.job_queue is None:
        logger.warning(
            "JobQueue is not available - auto-delete of sent files will NOT run. "
            "Install with: pip install \"python-telegram-bot[job-queue]\""
        )

    logger.info("SeriesBot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
