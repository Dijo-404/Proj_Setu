# Setu QR Tally Bridge — single-server LAN deployment image.
# Verified runtime: Python 3.11.9 (see docs/plans/2026-06-23-features-plan.md Phase 0).
FROM python:3.11-slim

# Keep Python predictable in containers.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install pinned dependencies first for better layer caching.
# All pins ship manylinux wheels for cp311 (fastapi, uvicorn[standard],
# sqlalchemy, jinja2, python-multipart, qrcode[pil]/pillow, reportlab,
# openpyxl, pytest, httpx) — no compiler/apt build deps are required on slim.
COPY requirements.txt ./
RUN pip install --only-binary=:all: -r requirements.txt

# Copy application code (see .dockerignore for what stays out of the image).
COPY app ./app

# Create the SQLite data directory and a non-root user that owns the app tree.
# The DB lives at /app/data/setu.db (DATABASE_URL default sqlite:///./data/setu.db).
RUN mkdir -p /app/data \
    && useradd --create-home --uid 10001 setu \
    && chown -R setu:setu /app

USER setu

# Persist the SQLite database (incl. WAL/SHM sidecar files) outside the image layer.
VOLUME ["/app/data"]

EXPOSE 8000

# slim has no curl; probe /health with the stdlib instead.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
