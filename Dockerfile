# Multi-stage build for production-ready, secure and optimized container
# Base stage for shared environment variables and packages
FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    API_PORT=8080 \
    API_HOST=0.0.0.0 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies needed for compiling certain python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Final production stage
FROM python:3.11-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    API_PORT=8080 \
    API_HOST=0.0.0.0 \
    PYTHONPATH=/app

WORKDIR /app

# Install runtime system dependencies (e.g. libpq for pgsql client)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed python dependencies from build base stage
COPY --from=base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=base /usr/local/bin /usr/local/bin

# Create a non-privileged system user for running the application securely
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /sbin/nologin -c "Application User" appuser

# Copy application source code and web files
COPY src/ /app/src/
COPY web_ui.py /app/
COPY VERSION /app/
# Copy other metadata/documentation files if necessary
COPY docs/ /app/docs/

# Set ownership of the app directory to the non-root user
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Expose the default Cloud Run port
EXPOSE 8080

# Health check to ensure API is responsive
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/stats', timeout=2)" || exit 1

# Start the API server in module mode
CMD ["python3", "-m", "src.api_server"]
