FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg build-essential cmake libgomp1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY server/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY server/ /app/

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

EXPOSE 8001
CMD ["gunicorn", "--preload", "-k", "uvicorn.workers.UvicornWorker", "-w", "6", "--timeout", "300", "-b", "0.0.0.0:8001", "main:app"]
