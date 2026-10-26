# ==============================================================================
# INTAKE AI — Production Docker Container
# ==============================================================================
FROM python:3.12-slim AS base

# Install system dependencies for OCR rasterization and PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Environment Defaults
ENV HOST=0.0.0.0
ENV PORT=8001
ENV ENVIRONMENT=production
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["python", "run.py"]
