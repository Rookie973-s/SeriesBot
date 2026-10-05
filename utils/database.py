from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, DB_NAME, SERIES_COLLECTION

_client = None
_db = None


def get_db():
    global _client, _db
    if _db is None:
        _client = AsyncIOMotorClient(MONGO_URI)
        _db = _client[DB_NAME]
    return _db


# ─── Series operations ────────────────────────────────────────────────────────

async def save_series(title: str, files: list[dict]) -> str:
    """
    Insert or update a series entry, REPLACING its file list.
    files = [ { file_id, file_type, caption } ... ]
    Returns the canonical title stored.
    """
    db = get_db()
    await db[SERIES_COLLECTION].update_one(
        {"title_lower": title.lower()},
        {
            "$set": {
                "title": title,
                "title_lower": title.lower(),
                "files": files,
            }
        },
        upsert=True,
    )
    return title


async def add_series_file(title: str, file_entry: dict) -> str:
    """
    Add a single file to a series, APPENDING to its existing file list
    (creating the series if it doesn't exist yet). Used when indexing
    files one at a time — e.g. from the channel, forwarded in bulk.
    """
    db = get_db()
    await db[SERIES_COLLECTION].update_one(
        {"title_lower": title.lower()},
        {
            "$set": {"title": title, "title_lower": title.lower()},
            "$push": {"files": file_entry},
        },
        upsert=True,
    )
    return title


async def search_series(query: str) -> dict | None:
    """
    Case-insensitive search for a series.
    1. Exact match (case-insensitive)
    2. Partial match (series title contains the query)
    Returns the first matching document or None.
    """
    db = get_db()
    q = query.strip().lower()

    # 1. Exact match
    record = await db[SERIES_COLLECTION].find_one({"title_lower": q})
    if record:
        return record

    # 2. Partial / contains match
    import re
    pattern = re.compile(re.escape(q), re.IGNORECASE)
    record = await db[SERIES_COLLECTION].find_one({"title_lower": pattern})
    return record


async def get_all_series_titles() -> list[str]:
    """Return all canonical series titles (for admin listing)."""
    db = get_db()
    cursor = db[SERIES_COLLECTION].find({}, {"title": 1}).sort("title_lower", 1)
    docs = await cursor.to_list(length=500)
    return [d["title"] for d in docs]


async def delete_series(title: str) -> bool:
    """Delete a series by title (case-insensitive). Returns True if deleted."""
    db = get_db()
    result = await db[SERIES_COLLECTION].delete_one({"title_lower": title.strip().lower()})
    return result.deleted_count > 0


async def count_series() -> int:
    db = get_db()
    return await db[SERIES_COLLECTION].count_documents({})


# ─── User tracking (for broadcasts) ────────────────────────────────────────

USERS_COLLECTION = "users"


async def save_user(user_id: int, username: str | None, full_name: str | None) -> None:
    """Record/update a user who has started the bot."""
    db = get_db()
    await db[USERS_COLLECTION].update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "username": username, "full_name": full_name}},
        upsert=True,
    )


async def get_all_user_ids() -> list[int]:
    db = get_db()
    cursor = db[USERS_COLLECTION].find({}, {"user_id": 1})
    docs = await cursor.to_list(length=None)
    return [d["user_id"] for d in docs]


async def remove_user(user_id: int) -> None:
    """Called when a broadcast finds a user has blocked the bot."""
    db = get_db()
    await db[USERS_COLLECTION].delete_one({"user_id": user_id})


async def count_users() -> int:
    db = get_db()
    return await db[USERS_COLLECTION].count_documents({})
