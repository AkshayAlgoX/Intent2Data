FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered output for logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Create a dedicated non-root user and group for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Install runtime dependencies first for layer caching (test deps live in requirements-dev.txt)
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application code
COPY backend/app /app/app

# Runtime index artifact (≈7 MB, built from the 261 MB metadata by
# `python backend/scripts/build_index.py`). The raw metadata is never baked in.
# The build FAILS here if the artifact is missing — build the index first.
# To provision it externally instead (volume/object store), mount it at the path
# given by INTENT2DATA_INDEX_CACHE and drop this COPY.
COPY backend/.cache/runtime_index.json.gz /app/.cache/runtime_index.json.gz

# Deployment configuration:
#  - the container has no metadata file, so the index MUST come from the cache;
#  - REQUIRE_INDEX makes a missing/corrupt artifact a fatal startup error
#    (clear log line + non-zero exit) instead of a silently degraded API;
#  - CORS defaults to "*" for the demo; set INTENT2DATA_CORS_ORIGINS to restrict.
ENV INTENT2DATA_INDEX_CACHE=/app/.cache/runtime_index.json.gz \
    INTENT2DATA_METADATA_PATH=/nonexistent/metadata.jsonl \
    INTENT2DATA_REQUIRE_INDEX=1

# Set proper ownership for non-root execution
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose container port
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys,urllib.request,json; b=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)); sys.exit(0 if b.get('ready') else 1)"

# Start FastAPI application using Uvicorn (production mode, binding to 0.0.0.0 without --reload)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
