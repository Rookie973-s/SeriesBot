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
    Insert or update a series entry.
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
