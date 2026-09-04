#!/usr/bin/env bash
# start.sh — Production startup for the Sound Check FastAPI backend.
#
# Usage:
#   ./start.sh                           # 2 workers on port 8001
#   WEB_CONCURRENCY=1 ./start.sh         # 1 worker (low-RAM machine)
#   PORT=9000 LOG_LEVEL=debug ./start.sh # custom port and log level
#
# Prerequisites:
#   - Python venv activated: source venv/bin/activate
#   - .env file populated from .env.example

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "▶  Starting Sound Check API (Gunicorn + UvicornWorker)"
echo "   Workers : ${WEB_CONCURRENCY:-2}"
echo "   Port    : ${PORT:-8001}"
echo "   Log lvl : ${LOG_LEVEL:-info}"
echo ""

exec gunicorn main:app -c gunicorn.conf.py
