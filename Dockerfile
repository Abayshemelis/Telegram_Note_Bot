# syntax=docker/dockerfile:1

# Stage 1: Build the React Mini App
FROM node:20-alpine AS frontend-builder
WORKDIR /app/miniapp
COPY miniapp/package*.json ./
RUN npm ci
COPY miniapp/ ./
RUN npm run build

# Stage 2: Python Backend & Bot
FROM python:3.11-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY notes_bot/ ./notes_bot/
COPY schema.sql .
COPY migrations/ ./migrations/
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

# Copy built frontend assets
COPY --from=frontend-builder /app/miniapp/dist ./miniapp/dist

EXPOSE 8000

CMD ["./docker-entrypoint.sh"]

