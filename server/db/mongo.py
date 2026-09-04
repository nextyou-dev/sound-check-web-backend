"""
db/mongo.py — MongoDB client singleton.

Provides a single MongoClient shared across the entire app lifetime.
Call get_db() anywhere to obtain the database handle.
"""
from pymongo import MongoClient
from pymongo.database import Database

from config import MONGO_URI, MONGO_DB_NAME, log

_client: MongoClient | None = None


def connect() -> None:
    """Initialise the client. Called once on app startup."""
    global _client
    _client = MongoClient(MONGO_URI)
    # Ping to validate connection
    _client.admin.command("ping")
    log.info(f"[mongo] Connected to {MONGO_DB_NAME}")
    _ensure_indexes()


def disconnect() -> None:
    """Close the client. Called on app shutdown."""
    global _client
    if _client:
        _client.close()
        log.info("[mongo] Disconnected")


def get_db() -> Database:
    """Return the active database handle. Raises if not yet connected."""
    if _client is None:
        raise RuntimeError("MongoDB client not initialised — call connect() first.")
    return _client[MONGO_DB_NAME]


# ─── Index bootstrap ─────────────────────────────────────────────────────────

def _ensure_indexes() -> None:
    """Idempotent index creation run at startup."""
    db = get_db()

    # users: unique email lookup
    db["users"].create_index("email", unique=True)

    # analysis_events: lookup by user and by session_id (engagement tracking)
    db["analysis_events"].create_index("user_id")
    db["analysis_events"].create_index("session_id", unique=True, sparse=True)

    # rate_limits: key lookup + TTL auto-expiry after 48 h
    db["rate_limits"].create_index("key", unique=True)
    db["rate_limits"].create_index("expires_at", expireAfterSeconds=0)

    log.info("[mongo] Indexes ensured")
