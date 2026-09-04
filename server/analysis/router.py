"""
analysis/router.py — HTTP layer for voice analysis endpoints.

POST  /analysis/voice        — JWT-protected, rate-limited voice analysis
PATCH /analysis/viewed       — mark result as viewed   (JWT + session_id in body)
PATCH /analysis/downloaded   — mark result as downloaded (JWT + session_id in body)
GET   /analysis/quota        — return remaining quota info for the authenticated user
"""
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth.deps import get_current_user
from analysis.service import AnalysisError, run_voice_analysis
from analysis.repository import insert_event, mark_viewed, mark_downloaded
from rate_limit.service import enforce, record_usage, get_quota
from config import log

router = APIRouter(prefix="/analysis", tags=["Analysis"])


# ─── Request schemas ──────────────────────────────────────────────────────────

class EngagementRequest(BaseModel):
    """Body accepted by the /viewed and /downloaded endpoints."""
    session_id: str


# ─── POST /analysis/voice ─────────────────────────────────────────────────────

@router.post("/voice", summary="Submit voice recording for stress analysis")
async def voice_analysis(
    request:          Request,
    background_tasks: BackgroundTasks,
    audio_file:       UploadFile = File(...),
    sleep_3d_avg:     float      = Form(0.0),
    session_id:       str        = Form(...),   # required — frontend session identifier
    user:             dict       = Depends(get_current_user),
):
    """
    Accepts a voice recording (any ffmpeg-supported format), a 3-day sleep
    average, and a session_id from the frontend.  Returns the full analysis
    result immediately; DB logging and rate-limit counter increments happen
    in the background.

    Rate limits:
      - N requests per email per 48 hours  (N = MAX_TRIES env var)
    """
    user_id = user["user_id"]
    email   = user["email"]
    ip      = request.client.host or "unknown"

    # ── Guard: rate limits ───────────────────────────────────────────────────
    enforce(email, ip)

    # ── Read upload ──────────────────────────────────────────────────────────
    try:
        audio_bytes = await audio_file.read()
    except Exception as exc:
        log.error(f"[analysis] Failed to read upload: {exc}")
        return JSONResponse(status_code=400, content={
            "detail": f"INVALID_FILE|Could not read the uploaded audio file.",
        })

    # ── ML pipeline (synchronous — heavy CPU work) ───────────────────────────
    try:
        result = run_voice_analysis(audio_bytes, audio_file.filename or "audio.wav", sleep_3d_avg)
    except AnalysisError as exc:
        parts       = str(exc).split("|", 1)
        code        = parts[0] if len(parts) == 2 else "PROCESSING_ERROR"
        msg         = parts[1] if len(parts) == 2 else str(exc)
        status_code = 422 if code in ("INSUFFICIENT_SPEECH", "NO_SEGMENTS") else 500
        return JSONResponse(status_code=status_code, content={
            "detail": f"{code}|{msg}",
        })

    # ── Background: log to DB + bump rate-limit counters ────────────────────
    background_tasks.add_task(
        _persist_and_rate_limit, user_id, email, ip, session_id, result
    )

    return result


def _persist_and_rate_limit(
    user_id: str, email: str, ip: str, session_id: str, result: dict
) -> None:
    """Fire-and-forget: save the event to MongoDB and increment counters."""
    try:
        event_id = insert_event(user_id, email, ip, session_id, result)
        log.info(f"[analysis] Event saved — id={event_id}, session={session_id}")
    except Exception as exc:
        log.error(f"[analysis] Failed to persist event: {exc}")
    try:
        record_usage(email, ip)
    except Exception as exc:
        log.error(f"[analysis] Failed to record usage: {exc}")


# ─── PATCH /analysis/viewed ───────────────────────────────────────────────────

@router.patch("/viewed", summary="Mark analysis result as viewed")
def mark_as_viewed(
    body: EngagementRequest,
    user: dict = Depends(get_current_user),
):
    """
    Idempotently marks the analysis result associated with `session_id` as
    viewed.  The session must belong to the authenticated user.
    """
    ok = mark_viewed(body.session_id, user["user_id"])
    if not ok:
        return JSONResponse(status_code=404, content={
            "detail": "Session not found or does not belong to you."
        })
    return {"success": True, "has_viewed_result": True}


# ─── PATCH /analysis/downloaded ──────────────────────────────────────────────

@router.patch("/downloaded", summary="Mark analysis result as downloaded")
def mark_as_downloaded(
    body: EngagementRequest,
    user: dict = Depends(get_current_user),
):
    """
    Idempotently marks the analysis result associated with `session_id` as
    downloaded.  The session must belong to the authenticated user.
    """
    ok = mark_downloaded(body.session_id, user["user_id"])
    if not ok:
        return JSONResponse(status_code=404, content={
            "detail": "Session not found or does not belong to you."
        })
    return {"success": True, "has_clicked_download": True}


# ─── GET /analysis/quota ──────────────────────────────────────────────────────

@router.get("/quota", summary="Get remaining analysis quota for the authenticated user")
def get_analysis_quota(user: dict = Depends(get_current_user)):
    """
    Returns:
      - remaining:       how many analyses the user can still run in this window
      - max:             the maximum analyses allowed per window (MAX_TRIES)
      - hours_remaining: hours until the rate-limit window resets (0 if no usage yet)
    """
    quota = get_quota(user["email"])
    return quota
