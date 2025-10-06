# Multi-stage production Dockerfile for Splittchen

# Build stage - includes build tools and dependencies
FROM python:3.13.7-slim AS builder

# Set environment variables for build stage
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Production stage - minimal runtime image
FROM python:3.13.7-slim AS production

# OCI Labels for proper package metadata
LABEL org.opencontainers.image.title="Splittchen"
LABEL org.opencontainers.image.description="Privacy-first expense splitting app"
LABEL org.opencontainers.image.url="https://github.com/splittchen/splittchen"
LABEL org.opencontainers.image.source="https://github.com/splittchen/splittchen"
LABEL org.opencontainers.image.documentation="https://github.com/splittchen/splittchen/blob/main/README.md"
LABEL org.opencontainers.image.licenses="MIT"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Install only runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd -r splittchen && useradd -r -g splittchen splittchen

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Set work directory
WORKDIR /app

# Copy application code
COPY . .

# Set permissions
RUN chown -R splittchen:splittchen /app

# Switch to non-root user
USER splittchen

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Set Flask app for CLI commands (uses flask_cli.py which does monkey patching)
ENV FLASK_APP=flask_cli.py

# Production command using Gunicorn with gevent workers for SocketIO support
# Using gevent worker class for WebSocket compatibility (better Python 3.13 support)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "gevent", "--workers", "1", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "wsgi:application"]