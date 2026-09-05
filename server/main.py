"""
main.py — FastAPI application entry point for sound-check-web server.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import log
from db.mongo import connect, disconnect
from auth.router import router as auth_router
from analysis.router import router as analysis_router

# PRELOAD MODELS GLOBALLY SO GUNICORN WORKERS SHARE RAM
try:
    from ml.engine import ModelEngine
    ModelEngine.get_instance().load_all()
    log.info("[startup] ML models globally preloaded into RAM")
except Exception as exc:
    log.warning(f"[startup] Global ML model load failed: {exc}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    connect()
    yield
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

app.include_router(auth_router)
app.include_router(analysis_router)

@app.get("/", tags=["Health"])
def root():
    return {"service": "sound-check-web", "status": "ok"}

@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
