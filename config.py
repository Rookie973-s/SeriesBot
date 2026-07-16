import os
from dotenv import load_dotenv
load_dotenv()
# ── Bot token ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("SERIES_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("SERIES_BOT_TOKEN is not set in your .env / Railway Variables.")
# ── Admin IDs ──────────────────────────────────────────────────────────────────
_raw_admins = os.getenv("ADMIN_IDS", "")
try:
    ADMIN_IDS = [int(x.strip()) for x in _raw_admins.split(",") if x.strip()]
except ValueError:
    raise RuntimeError("ADMIN_IDS must be numbers separated by commas.")
# ── MongoDB ────────────────────────────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not set.")
DB_NAME = "wavemovies"          # same DB as WavemoviesBot
SERIES_COLLECTION = "series"    # new collection
# ── Pagination ─────────────────────────────────────────────────────────────────
PAGE_SIZE = 10  # files per page
_raw_channel = os.getenv("SOURCE_CHANNEL_ID")
if not _raw_channel:
    raise RuntimeError("SOURCE_CHANNEL_ID is not set.")
CHANNEL_ID = int(_raw_channel)
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
if not TMDB_API_KEY:
    raise RuntimeError("TMDB_API_KEY is not set.")

# ── Required channel membership ─────────────────────────────────────────────
# Users must join these before the bot will search/reply to them.
# For a PUBLIC channel: "username" = "@handle", "url" = "https://t.me/handle"
# For a PRIVATE channel: "username" = numeric chat ID (int, starts with -100),
#                         "url" = an invite link (Telegram > channel > Invite Links)
# The bot must be an ADMIN in every channel listed here.
REQUIRED_CHANNELS = [
    {"name": "Main Channel", "username": "@wavemovies_chn", "url": "https://t.me/wavemovies_chn"},
    {"name": "Movie Channel", "username": -1002247736269, "url": "https://t.me/+dK1IC0727Z43ZWI8"},
    {"name": "Backup Channel", "username": -1003879166875, "url": "https://t.me/+FTIhdtx-3nFIMzc0"},
]

BOT_NAME = os.getenv("BOT_NAME", "SeriesBot")
