"""
analysis/router.py — HTTP layer for voice analysis endpoints.

POST  /analysis/voice             — JWT-protected, rate-limited voice analysis
PATCH /analysis/{event_id}/viewed     — mark result as viewed
PATCH /analysis/{event_id}/downloaded — mark result as downloaded
"""
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from auth.deps import get_current_user
from analysis.service import AnalysisError, run_voice_analysis
from analysis.repository import insert_event, mark_viewed, mark_downloaded
from rate_limit.service import enforce, record_usage
from config import log

router = APIRouter(prefix="/analysis", tags=["Analysis"])


# ─── POST /analysis/voice ─────────────────────────────────────────────────────

@router.post("/voice", summary="Submit voice recording for stress analysis")
async def voice_analysis(
    request:         Request,
    background_tasks: BackgroundTasks,
    audio_file:      UploadFile = File(...),
    sleep_3d_avg:    float      = Form(0.0),
    user:            dict       = Depends(get_current_user),
):
    """
    Accepts a voice recording (any ffmpeg-supported format) and an optional
    3-day sleep average.  Returns the full analysis result immediately;
    DB logging and rate-limit counter increments happen in the background.

    Rate limits:
      - 3 requests per email per 48 hours
      - 3 requests per IP   per 48 hours
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
            "success": False,
            "error": {"code": "INVALID_FILE", "message": "Could not read the uploaded audio file."},
        })

    # ── ML pipeline (synchronous — heavy CPU work) ───────────────────────────
    try:
        result = run_voice_analysis(audio_bytes, audio_file.filename or "audio.wav", sleep_3d_avg)
    except AnalysisError as exc:
        parts = str(exc).split("|", 1)
        code  = parts[0] if len(parts) == 2 else "PROCESSING_ERROR"
        msg   = parts[1] if len(parts) == 2 else str(exc)
        status_code = 422 if code in ("INSUFFICIENT_SPEECH", "NO_SEGMENTS") else 500
        return JSONResponse(status_code=status_code, content={
            "success": False,
            "error": {"code": code, "message": msg},
        })

    # ── Background: log to DB + bump rate-limit counters ────────────────────
    background_tasks.add_task(
        _persist_and_rate_limit, user_id, email, ip, result
    )

    return result


def _persist_and_rate_limit(user_id: str, email: str, ip: str, result: dict) -> None:
    """Fire-and-forget: save the event to MongoDB and increment counters."""
    try:
        event_id = insert_event(user_id, email, ip, result)
        log.info(f"[analysis] Event saved — id={event_id}")
    except Exception as exc:
        log.error(f"[analysis] Failed to persist event: {exc}")
    try:
        record_usage(email, ip)
    except Exception as exc:
        log.error(f"[analysis] Failed to record usage: {exc}")


# ─── PATCH /analysis/{event_id}/viewed ───────────────────────────────────────

@router.patch("/{event_id}/viewed", summary="Mark analysis result as viewed")
def mark_as_viewed(
    event_id: str,
    user: dict = Depends(get_current_user),
):
    ok = mark_viewed(event_id, user["user_id"])
    if not ok:
        return JSONResponse(status_code=404, content={
            "success": False, "error": "Event not found or does not belong to you."
        })
    return {"success": True, "has_viewed_result": True}


# ─── PATCH /analysis/{event_id}/downloaded ───────────────────────────────────

@router.patch("/{event_id}/downloaded", summary="Mark analysis result as downloaded")
def mark_as_downloaded(
    event_id: str,
    user: dict = Depends(get_current_user),
):
    ok = mark_downloaded(event_id, user["user_id"])
    if not ok:
        return JSONResponse(status_code=404, content={
            "success": False, "error": "Event not found or does not belong to you."
        })
    return {"success": True, "has_clicked_download": True}
