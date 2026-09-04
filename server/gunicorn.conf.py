"""
gunicorn.conf.py — Gunicorn configuration for the Sound Check FastAPI server.

Architecture:
  - Gunicorn as the process manager (multi-worker)
  - Each worker is a UvicornWorker (ASGI) — required for FastAPI
  - FastAPI handles concurrent async I/O within each worker
  - Heavy ML models (SenseVoice, Wav2Vec2, etc.) are loaded ONCE per worker
    on startup via the FastAPI lifespan event

Worker count guidance:
  - CPU-only servers: 2 workers (each worker holds all models in RAM ~3-6 GB)
  - If OOM on low-RAM servers: reduce WEB_CONCURRENCY=1 and rely on async concurrency
  - GPU servers: 1 worker per GPU (torch CUDA context cannot be forked)

Environment variable overrides (set in .env or shell):
  WEB_CONCURRENCY — number of worker processes (default: 2)
  PORT            — listening port (default: 8001)
  LOG_LEVEL       — uvicorn log level: debug | info | warning | error (default: info)
"""
import os

# ─── Networking ──────────────────────────────────────────────────────────────
bind     = f"0.0.0.0:{os.getenv('PORT', '8001')}"
backlog  = 2048                  # max queued TCP connections

# ─── Workers ─────────────────────────────────────────────────────────────────
# UvicornWorker is REQUIRED for ASGI apps like FastAPI.
# Each worker is an independent OS process — models load once per worker.
worker_class       = "uvicorn.workers.UvicornWorker"
workers            = int(os.getenv("WEB_CONCURRENCY", "2"))
threads            = 1           # 1 thread per worker; async handles concurrency
worker_connections = 1000        # max simultaneous keep-alive connections per worker
timeout            = 900         # kill worker if it's silent for 5 min (ML is slow)
graceful_timeout   = 30          # wait 30s for in-flight requests on SIGTERM
keepalive          = 5           # seconds to keep idle connections alive

# ─── Logging ─────────────────────────────────────────────────────────────────
loglevel          = os.getenv("LOG_LEVEL", "info")
accesslog         = "-"          # stdout
errorlog          = "-"          # stderr
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(D)s us'

# ─── Process lifecycle ───────────────────────────────────────────────────────
# preload_app=False ensures each worker runs the FastAPI lifespan independently,
# which is the safest way to load torch models (avoids fork-after-CUDA issues).
preload_app         = False
max_requests        = 500        # restart worker after N requests (prevents memory creep)
max_requests_jitter = 50         # add jitter to prevent thundering-herd restarts
