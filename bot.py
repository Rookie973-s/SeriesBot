import logging
from telegram import Update
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
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception while processing an update:", exc_info=context.error)

    # Best-effort ping to admins so you find out without digging through logs.
    # Wrapped in its own try/except so a failure here can't cause a loop.
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
