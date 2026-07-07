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
