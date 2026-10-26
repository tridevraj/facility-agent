import re
from datetime import datetime, timezone


def utcnow():
    """Naive UTC timestamp (works the same on SQLite and MySQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def norm(text):
    """Lower-case and strip punctuation so 'Block C - Room 204' == 'block c room 204'."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def has_phrase(normalised_text, phrase):
    """Whole-word match with optional plural, on already-normalised text."""
    p = norm(phrase)
    if not p:
        return False
    return re.search(r"\b" + re.escape(p) + r"(s|es)?\b", normalised_text) is not None
