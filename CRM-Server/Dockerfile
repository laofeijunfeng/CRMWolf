# CRMWolf Backend Dockerfile
# Multi-stage build for optimized production image

# Build stage
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/install -r requirements.txt

# Production stage
FROM python:3.11-slim as production

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local/lib/python3.11/site-packages

# Copy application code
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY alembic.ini ./

# Create directories for logs and uploads
RUN mkdir -p logs uploads

# Copy entrypoint script
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh && head -1 entrypoint.sh | grep -q "^#!" || (echo "#!/bin/bash" | cat - entrypoint.sh > temp && mv temp entrypoint.sh && chmod +x entrypoint.sh)

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run entrypoint
ENTRYPOINT ["./entrypoint.sh"]