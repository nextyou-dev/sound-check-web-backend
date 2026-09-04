"""
rate_limit/service.py — Business logic for per-user rate limiting.

Policy:
  - N voice analyses per unique email per 48-hour rolling window.
    N is controlled by the MAX_TRIES environment variable.
  - IP rate limiting is currently disabled (commented out).
  - Counters are incremented AFTER a successful response is committed (fire-and-forget).
"""
from datetime import datetime, timezone

from fastapi import HTTPException, status

from config import MAX_TRIES, RATE_LIMIT_WINDOW_H, EXEMPT_EMAILS, log
from rate_limit.repository import get_count, get_quota_doc, increment


def _email_key(email: str) -> str:
    return f"email:{email.lower()}"


def _ip_key(ip: str) -> str:
    return f"ip:{ip}"


def enforce(email: str, ip: str) -> None:
    """
    Check the email key against MAX_TRIES.
    Raises HTTP 429 if the per-account limit is exceeded.

    IP rate limiting is commented out but can be re-enabled by
    uncommenting the _ip_key check below.
    """
    if email.lower() in EXEMPT_EMAILS:
        log.info(f"[rate_limit] Bypassing rate limit for exempt email: {email}")
        return

    # Commented out IP rate limiting as requested by user
    # for key, label in ((_email_key(email), "email"), (_ip_key(ip), "IP")):
    for key, label in ((_email_key(email), "email"),):
        count = get_count(key)
        if count >= MAX_TRIES:
            log.warning(f"[rate_limit] {label} limit hit for {key} (count={count})")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"RATE_LIMIT_EXCEEDED|You have reached the limit of {MAX_TRIES} "
                    f"voice analyses per {RATE_LIMIT_WINDOW_H} hours. "
                    f"Please try again later."
                ),
            )


def record_usage(email: str, ip: str) -> None:
    """
    Increment the email counter after a successful analysis.
    Should be called as a fire-and-forget background task.
    """
    if email.lower() in EXEMPT_EMAILS:
        return
        
    increment(_email_key(email))
    # increment(_ip_key(ip))  # Commented out IP rate limiting
    log.info(f"[rate_limit] Usage recorded — email={email} (IP tracking disabled)")


def get_quota(email: str) -> dict:
    """
    Return remaining quota info for the given email.

    Response shape:
      remaining:       int   — how many analyses left in this window
      max:             int   — MAX_TRIES
      hours_remaining: float — hours until the window resets (0.0 if no usage yet)
    """
    if email.lower() in EXEMPT_EMAILS:
        return {
            "max":             9999,
            "used":            0,
            "remaining":       9999,
            "window_hours":    RATE_LIMIT_WINDOW_H,
            "hours_remaining": 0.0,
        }

    doc = get_quota_doc(_email_key(email))

    if doc is None:
        # User has never made a request — full quota, no active window
        return {
            "max":             MAX_TRIES,
            "used":            0,
            "remaining":       MAX_TRIES,
            "window_hours":    RATE_LIMIT_WINDOW_H,
            "hours_remaining": 0.0,
        }

    used      = doc.get("count", 0)
    remaining = max(0, MAX_TRIES - used)

    expires_at = doc.get("expires_at")
    if expires_at:
        now = datetime.now(timezone.utc)
        # expires_at from Mongo may be naive — make it timezone-aware if needed
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        delta_secs      = (expires_at - now).total_seconds()
        hours_remaining = round(max(0.0, delta_secs / 3600), 2)
    else:
        hours_remaining = 0.0

    return {
        "max":             MAX_TRIES,
        "used":            used,
        "remaining":       remaining,
        "window_hours":    RATE_LIMIT_WINDOW_H,
        "hours_remaining": hours_remaining,
    }
