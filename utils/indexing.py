"""
Shared logic for turning a Telegram message (document/video/photo/text link)
into a (title, file_entry) pair ready to store in the series collection.

Used by:
  - handlers/channel.py  → auto-indexing new channel posts
  - handlers/channel.py  → manual /indexchannel command
  - handlers/admin.py    → bulk indexing mode (forward many files at once)
"""
import os


def derive_title_and_entry(message):
    """
    Given a telegram Message, extract a title and a storable file entry.

    Title priority:
      1. The message's caption (if present)
      2. The filename, with its extension stripped (for documents/videos)
      3. For plain text/link messages, "Label" from "Label | URL" format

    Returns (title, entry) or (None, None) if nothing usable was found.
    """
    file_id = None
    file_type = None
    name = None
    text_content = None

    if message.document:
        file_id   = message.document.file_id
        file_type = "document"
        name      = message.document.file_name or "File"
    elif message.video:
        file_id   = message.video.file_id
        file_type = "video"
        name      = message.video.file_name or "Video"
    elif message.photo:
        file_id   = message.photo[-1].file_id
        file_type = "photo"
        name      = "Photo"
    elif message.text:
        file_type = "text"
        raw = message.text.strip()
        if "|" in raw:
            label, _, url = raw.partition("|")
            name = label.strip()
            text_content = url.strip()
        else:
            name = "Link"
            text_content = raw
    else:
        return None, None

    # ── Determine the title ─────────────────────────────────────────────
    title = (message.caption or "").strip()

    if not title:
        if file_type == "text":
            title = name
        elif name:
            title = os.path.splitext(name)[0].strip()

    if not title:
        return None, None

    if "|" in title:
        title = title.split("|", 1)[0].strip()

    caption = message.caption or f"🎬 *{title}*"

    entry = {
        "file_id":   file_id,
        "file_type": file_type,
        "caption":   caption,
        "name":      name,
    }
    if text_content is not None:
        entry["text"] = text_content

    return title, entry
