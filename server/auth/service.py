"""
auth/service.py — Business logic for OTP generation and JWT issuance.

Keeps all auth business rules here. The router calls these functions;
the repository handles all DB I/O.
"""
import secrets
import string
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRES_DAYS, log
from auth.repository import (
    find_user_by_email,
    upsert_otp,
    mark_verified_and_clear_otp,
)

OTP_LENGTH    = 6
OTP_TTL_MINS  = 15


# ─── OTP helpers ────────────────────────────────────────────────────────────

def _generate_otp() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(OTP_LENGTH))


def _hash_otp(otp: str) -> str:
    return bcrypt.hashpw(otp.encode(), bcrypt.gensalt()).decode()


def _verify_otp(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ─── JWT ────────────────────────────────────────────────────────────────────

def _issue_jwt(user_id: str, email: str) -> str:
    payload = {
        "sub":   user_id,
        "email": email,
        "exp":   datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRES_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ─── Public service calls ────────────────────────────────────────────────────

def create_and_store_otp(email: str) -> str:
    """
    Generate a fresh OTP, hash+store it, and return the plain OTP
    so the caller (router) can send it via email.
    """
    otp     = _generate_otp()
    hashed  = _hash_otp(otp)
    expires = datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINS)
    upsert_otp(email, hashed, expires)
    log.info(f"[auth] OTP created for {email}, expires {expires.isoformat()}")
    return otp


class OTPError(Exception):
    """Raised for any OTP verification failure."""


def verify_otp_and_issue_token(email: str, otp: str) -> str:
    """
    Validate the OTP and return a signed JWT on success.
    Raises OTPError with a safe message on any failure.
    """
    user = find_user_by_email(email)
    if not user:
        raise OTPError("No account found for this email.")

    otp_hash    = user.get("otp_hash")
    otp_expires = user.get("otp_expires_at")

    if not otp_hash:
        raise OTPError("No OTP pending for this account. Please request a new one.")

    now = datetime.now(timezone.utc)
    if otp_expires is None or (otp_expires.tzinfo is None and otp_expires.replace(tzinfo=timezone.utc) < now) or (otp_expires.tzinfo is not None and otp_expires < now):
        raise OTPError("OTP has expired. Please request a new one.")

    if not _verify_otp(otp, otp_hash):
        raise OTPError("Incorrect OTP.")

    # Consume the OTP — mark user verified
    mark_verified_and_clear_otp(user["_id"])
    token = _issue_jwt(str(user["_id"]), user["email"])
    log.info(f"[auth] JWT issued for {email}")
    return token
