import logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from config import BOT_TOKEN, ADMIN_IDS
from handlers.admin import (
    addseries_handler,
    upload_handler,
    done_handler,
    cancel_handler,
    delseries_handler,
    listall_handler,
    botstats_handler,
)
from handlers.search import text_search_handler, pagination_callback

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # ── Admin commands ─────────────────────────────────────────
    app.add_handler(CommandHandler("addseries", addseries_handler))
    app.add_handler(CommandHandler("done",       done_handler))
    app.add_handler(CommandHandler("cancel",     cancel_handler))
    app.add_handler(CommandHandler("delseries",  delseries_handler))
    app.add_handler(CommandHandler("listall",    listall_handler))
    app.add_handler(CommandHandler("botstats",   botstats_handler))

    # ── Admin file uploads (during session) ───────────────────
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

    logger.info("SeriesBot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
