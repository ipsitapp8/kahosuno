# KahoSuno backend. Build from the repo root or from backend/:
#   docker build -t kahosuno-backend backend
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so this layer is cached until pyproject.toml changes.
COPY pyproject.toml ./
COPY app ./app
RUN pip install .

# Run as a normal user, with one folder it may write to (the SQLite call records).
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown appuser /data
USER appuser

ENV DATABASE_URL=sqlite+aiosqlite:////data/calls.db \
    APP_ENV=production \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=4)"

# --ws-max-size: uvicorn's default allows 16 MB websocket messages; audio frames are ~3 KB.
# --proxy-headers: behind Render/nginx the real client IP comes from X-Forwarded-For. Only
# trusted when the sender is listed in FORWARDED_ALLOW_IPS (default: localhost only).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --ws-max-size 65536 --proxy-headers"]
