"""
rate_limit/repository.py — DB operations for the rate_limits collection.

Each document tracks how many requests a key (email:<addr> or ip:<addr>)
has made inside the current 48-hour window.  A MongoDB TTL index on the
`expires_at` field automatically removes expired documents.
"""
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument

from db.mongo import get_db
from config import RATE_LIMIT_WINDOW_H


def get_count(key: str) -> int:
    """Return the current request count for this key (0 if no record exists)."""
    doc = get_db()["rate_limits"].find_one({"key": key}, {"count": 1})
    return doc["count"] if doc else 0


def get_quota_doc(key: str) -> dict | None:
    """
    Return the full rate-limit document for `key`, or None if the window
    hasn't started yet (i.e. user has never made a request).
    """
    return get_db()["rate_limits"].find_one(
        {"key": key}, {"count": 1, "expires_at": 1}
    )


def increment(key: str) -> int:
    """
    Atomically increment the count for `key`.
    Creates the document with a 48-hour TTL window on first use.
    Returns the new count.
    """
    now     = datetime.now(timezone.utc)
    expires = now + timedelta(hours=RATE_LIMIT_WINDOW_H)

    result = get_db()["rate_limits"].find_one_and_update(
        {"key": key},
        {
            "$inc": {"count": 1},
            "$setOnInsert": {
                "key":        key,
                "first_seen": now,
                "expires_at": expires,
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return result["count"]
