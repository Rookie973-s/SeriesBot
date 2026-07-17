"""
Shared helper for auto-deleting files the bot sends, and for building the
"save this now" warning appended to captions.

Requires the JobQueue extra:
    pip install "python-telegram-bot[job-queue]"
Without it, context.job_queue is None and scheduling is skipped (logged
as a warning) - files will simply never auto-delete.
"""
import logging
from telegram.ext import ContextTypes
from config import AUTO_DELETE_SECONDS

logger = logging.getLogger(__name__)


def autodelete_notice() -> str:
    """Short warning line to append to a file's caption."""
    hours = AUTO_DELETE_SECONDS / 3600
    hours_str = f"{hours:.0f}" if hours == int(hours) else f"{hours:.1f}"
    return f"\n\n⏳ *Auto-deletes in {hours_str}h — save it to your device now!*"


async def _delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    try:
        await context.bot.delete_message(chat_id=data["chat_id"], message_id=data["message_id"])
    except Exception:
        # Already deleted, chat cleared, bot lost delete rights, etc - not fatal.
        logger.debug(
            "Auto-delete: couldn't remove message %s in chat %s (probably already gone).",
            data["message_id"], data["chat_id"],
        )


def schedule_autodelete(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    """Schedule a message the bot just sent for deletion AUTO_DELETE_SECONDS from now."""
    if not context.job_queue:
        logger.warning(
            "job_queue unavailable - auto-delete skipped for message %s in chat %s. "
            "Install with: pip install \"python-telegram-bot[job-queue]\"",
            message_id, chat_id,
        )
        return

    context.job_queue.run_once(
        _delete_message_job,
        when=AUTO_DELETE_SECONDS,
        data={"chat_id": chat_id, "message_id": message_id},
        name=f"autodel_{chat_id}_{message_id}",
    )
