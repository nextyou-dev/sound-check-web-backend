"""
auth/repository.py — All DB operations for the users collection.

Follows the Repository pattern: raw pymongo calls are isolated here
so that the service layer never touches the DB directly.
"""
from datetime import datetime, timezone
from bson import ObjectId

from db.mongo import get_db


def find_user_by_email(email: str) -> dict | None:
    return get_db()["users"].find_one({"email": email.lower()})


def upsert_otp(email: str, otp_hash: str, otp_expires_at: datetime) -> dict:
    """
    Create or update a user record with a fresh OTP hash.
    Returns the updated document.
    """
    now = datetime.now(timezone.utc)
    result = get_db()["users"].find_one_and_update(
        {"email": email.lower()},
        {
            "$set": {
                "otp_hash":      otp_hash,
                "otp_expires_at": otp_expires_at,
                "updated_at":    now,
            },
            "$setOnInsert": {
                "email":       email.lower(),
                "is_verified": False,
                "created_at":  now,
            },
        },
        upsert=True,
        return_document=True,   # return updated doc
    )
    return result


def mark_verified_and_clear_otp(user_id: ObjectId) -> None:
    """Mark the user as verified and remove the consumed OTP."""
    get_db()["users"].update_one(
        {"_id": user_id},
        {
            "$set": {
                "is_verified": True,
                "otp_hash":    None,
                "updated_at":  datetime.now(timezone.utc),
            }
        },
    )
