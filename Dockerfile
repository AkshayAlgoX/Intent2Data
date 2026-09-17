FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered output for logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Create a dedicated non-root user and group for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Install dependencies first for layer caching
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application code
COPY backend/app /app/app

# Set proper ownership for non-root execution
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose container port
EXPOSE 8000

# Start FastAPI application using Uvicorn (production mode, binding to 0.0.0.0 without --reload)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
