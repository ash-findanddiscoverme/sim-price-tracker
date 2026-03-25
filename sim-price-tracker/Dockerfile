FROM python:3.11-slim

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only to save space)
RUN playwright install chromium

# Copy application code
COPY backend/ ./backend/
COPY static/ ./static/
COPY local-scraper/ ./local-scraper/

# Create data directory for SQLite
RUN mkdir -p /app/backend/data

# Expose port
EXPOSE 8000

# Run from the backend directory so imports work
WORKDIR /app/backend

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
