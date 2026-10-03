"""
TMDB-backed verification for "is this text actually a movie/series title?"

Replaces guesswork (word blacklists) with a real check: we ask TMDB's
multi-search endpoint whether the text matches a known movie or TV show.

  - No match on TMDB   -> almost certainly chit-chat, stay quiet.
  - Match on TMDB       -> it's a real title, worth forwarding to admins
                           even if it's not in our own DB yet.

Requires TMDB_API_KEY in config.py / your .env.
Get a free key at https://www.themoviedb.org/settings/api
"""
import httpx
from config import TMDB_API_KEY

_TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"

# Small in-memory cache so the same repeated phrase doesn't hit the API
# every time (helps with spammy groups). Cleared on restart - that's fine.
_cache: dict[str, dict | None] = {}
_CACHE_MAX = 500


async def tmdb_lookup(query: str) -> dict | None:
    """
    Returns a dict describing the best TMDB match, or None if nothing
    relevant was found (or the API key isn't configured / call failed).

    Result shape: {"title": str, "media_type": "movie"|"tv", "popularity": float}
    """
    q = query.strip()
    if not TMDB_API_KEY or not q:
        return None

    key = q.lower()
    if key in _cache:
        return _cache[key]

    params = {
        "api_key": TMDB_API_KEY,
        "query": q,
        "include_adult": "false",
    }

    result = None
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(_TMDB_SEARCH_URL, params=params)
            if resp.status_code == 200:
                data = resp.json()
                candidates = [
                    r for r in data.get("results", [])
                    if r.get("media_type") in ("tv", "movie")
                ]
                if candidates:
                    # Results already come back popularity-sorted-ish;
                    # take the top hit.
                    top = candidates[0]
                    result = {
                        "title": top.get("title") or top.get("name"),
                        "media_type": top.get("media_type"),
                        "popularity": top.get("popularity", 0),
                    }
    except Exception:
        # Network hiccup, bad key, timeout, etc. Fail safe -> treat as
        # "couldn't verify", caller decides what to do with None.
        result = None

    if len(_cache) >= _CACHE_MAX:
        _cache.clear()
    _cache[key] = result

    return result
