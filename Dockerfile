# ============================================================
# Backend Dockerfile — Django + DRF
# ============================================================
# Base image: Python 3.13 slim (matches requirements.txt)
# Exposes:   port 8000
# Entrypoint: manage.py runserver (development mode)
# ============================================================

FROM python:3.13-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies required by psycopg2-binary and other packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (Docker cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

EXPOSE 8000

# Production: run migrations then start gunicorn
# Railway injects $PORT; fallback to 8000 for local Docker runs
CMD ["sh", "-c", "python manage.py migrate && python manage.py ensure_admin && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2"]
