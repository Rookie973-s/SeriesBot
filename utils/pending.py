"""
In-memory store correlating a request forwarded to an admin with the
original user who asked, so that whatever the admin replies with gets
routed back to exactly the right person.

Key   = message_id of the request as it appears in the admin's private
        chat with the bot.
Value = {
    "user_id":    int,   # who asked
    "chat_id":    int,   # chat where they asked (group or DM)
    "message_id": int,   # their original message_id, so we can reply to it
    "query":      str,   # what they typed
}
"""

_pending: dict[int, dict] = {}


def add_pending(admin_message_id: int, user_id: int, chat_id: int, message_id: int, query: str):
    _pending[admin_message_id] = {
        "user_id": user_id,
        "chat_id": chat_id,
        "message_id": message_id,
        "query": query,
    }


def get_pending(admin_message_id: int) -> dict | None:
    return _pending.get(admin_message_id)


def pop_pending(admin_message_id: int) -> dict | None:
    return _pending.pop(admin_message_id, None)
