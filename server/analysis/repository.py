"""
analysis/repository.py — DB operations for the analysis_events collection.

Each document stores a full voice analysis result plus two engagement flags:
  has_viewed_result    — flipped by PATCH /analysis/{id}/viewed
  has_clicked_download — flipped by PATCH /analysis/{id}/downloaded
"""
from datetime import datetime, timezone

from bson import ObjectId

from db.mongo import get_db


def insert_event(user_id: str, email: str, ip: str, payload: dict) -> str:
    """
    Persist a completed analysis result.
    Returns the new document's string _id.
    """
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": ObjectId(user_id),
        "email":   email,
        "ip":      ip,

        # ML output
        "overall":           payload.get("overall"),
        "segments":          payload.get("segments"),
        "speech_ratio":      payload.get("speech_ratio"),
        "audio_duration_sec": payload.get("audio_duration_sec"),
        "sleep_3d_avg":      payload.get("sleep_3d_avg"),
        "ml_version":        payload.get("ml_version"),

        # Engagement flags
        "has_viewed_result":    False,
        "has_clicked_download": False,
        "viewed_at":            None,
        "downloaded_at":        None,

        "created_at": now,
    }
    result = get_db()["analysis_events"].insert_one(doc)
    return str(result.inserted_id)


def find_event_for_user(event_id: str, user_id: str) -> dict | None:
    """Fetch an event only if it belongs to this user."""
    try:
        oid = ObjectId(event_id)
        uid = ObjectId(user_id)
    except Exception:
        return None
    return get_db()["analysis_events"].find_one({"_id": oid, "user_id": uid})


def mark_viewed(event_id: str, user_id: str) -> bool:
    """Idempotently set has_viewed_result=true. Returns False if not found."""
    try:
        oid = ObjectId(event_id)
        uid = ObjectId(user_id)
    except Exception:
        return False
    result = get_db()["analysis_events"].update_one(
        {"_id": oid, "user_id": uid},
        {
            "$set": {
                "has_viewed_result": True,
                "viewed_at": datetime.now(timezone.utc),
            }
        },
    )
    return result.matched_count > 0


def mark_downloaded(event_id: str, user_id: str) -> bool:
    """Idempotently set has_clicked_download=true. Returns False if not found."""
    try:
        oid = ObjectId(event_id)
        uid = ObjectId(user_id)
    except Exception:
        return False
    result = get_db()["analysis_events"].update_one(
        {"_id": oid, "user_id": uid},
        {
            "$set": {
                "has_clicked_download": True,
                "downloaded_at": datetime.now(timezone.utc),
            }
        },
    )
    return result.matched_count > 0
