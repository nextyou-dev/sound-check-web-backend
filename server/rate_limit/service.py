"""
rate_limit/service.py — Business logic for per-user / per-IP rate limiting.

Policy:
  - 3 voice analyses per unique email per 48-hour rolling window.
  - 3 voice analyses per unique IP per 48-hour rolling window.
  - Both guards must pass before the analysis is run.
  - Counters are incremented AFTER a successful response is committed (fire-and-forget).
"""
from fastapi import HTTPException, status

from config import RATE_LIMIT_MAX, log
from rate_limit.repository import get_count, increment


def _email_key(email: str) -> str:
    return f"email:{email.lower()}"


def _ip_key(ip: str) -> str:
    return f"ip:{ip}"


def enforce(email: str, ip: str) -> None:
    """
    Check both keys against RATE_LIMIT_MAX.
    Raises HTTP 429 if either limit is exceeded.
    """
    for key, label in ((_email_key(email), "email"), (_ip_key(ip), "IP")):
        count = get_count(key)
        if count >= RATE_LIMIT_MAX:
            log.warning(f"[rate_limit] {label} limit hit for {key} (count={count})")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"You have reached the limit of {RATE_LIMIT_MAX} voice analyses "
                    f"per 48 hours for this {label}. Please try again later."
                ),
            )


def record_usage(email: str, ip: str) -> None:
    """
    Increment both counters after a successful analysis.
    Should be called as a fire-and-forget background task.
    """
    increment(_email_key(email))
    increment(_ip_key(ip))
    log.info(f"[rate_limit] Usage recorded — email={email}, ip={ip}")
