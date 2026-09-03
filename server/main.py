"""
main.py — FastAPI application entry point for sound-check-web server.

Startup:
  1. Connect to MongoDB and ensure indexes.
  2. Load ML models (shared from VoiceStack env via ml/ shim).

Routers:
  /auth/*      — OTP sign-up / verify
  /analysis/*  — JWT-protected voice analysis + engagement flags

Run:
  source venv/bin/activate
  uvicorn main:app --reload --port 8001
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import log
from db.mongo import connect, disconnect
from auth.router import router as auth_router
from analysis.router import router as analysis_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    connect()
    try:
        from ml.engine import ModelEngine
        ModelEngine.get_instance().load_all()
        log.info("[startup] ML models loaded")
    except Exception as exc:
        log.warning(f"[startup] ML model load skipped (running without VoiceStack env?): {exc}")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    disconnect()


app = FastAPI(
    title="Sound Check Web API",
    version="1.0.0",
    description="Voice stress analysis with email OTP auth.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(analysis_router)


@app.get("/", tags=["Health"])
def root():
    return {"service": "sound-check-web", "status": "ok"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
