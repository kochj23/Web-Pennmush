# Web-Pennmush server image (Nova Games: novagames-mush)
# Non-root (uid 10001), read-only rootfs friendly, no LLM libraries.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    DATA_DIR=/data \
    COOKIE_SECURE=true \
    COOKIE_PATH=/mush/ \
    REGISTRATION_MODE=approval

RUN groupadd -g 10001 app && useradd -u 10001 -g 10001 -M -d /app -s /usr/sbin/nologin app

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-compile -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
RUN python -m compileall -q backend && mkdir -p /data && chown 10001:10001 /data

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--ws-max-size", "16384", "--no-server-header", "--timeout-keep-alive", "15", \
     "--limit-concurrency", "400"]
