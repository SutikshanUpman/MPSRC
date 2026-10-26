# Trial of the Nine Realms: the console and the trial engine. Standard library only: no pip install.
# The Runemark pack is not in the image: mount it read-only at /app/dev_pack_E5 (or use Dockerfile.with-pack).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    DATA_DIR=/data

RUN useradd --create-home --uid 10001 realms && mkdir -p /data && chown realms /data
WORKDIR /app
COPY server.py ./
COPY backend ./backend
COPY config ./config
COPY prompts ./prompts
COPY scripts ./scripts
COPY web ./web

USER realms
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT','8000'),timeout=4)"

# Refuses to start on 0.0.0.0 without CONSOLE_PASSWORD. Set secrets at run time, never in the image.
CMD ["python", "server.py"]
