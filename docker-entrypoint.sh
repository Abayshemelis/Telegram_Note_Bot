#!/usr/bin/env bash
set -e

# Wait for PostgreSQL to become reachable
if [ -n "$DATABASE_URL" ]; then
  echo "[*] Waiting for PostgreSQL to be ready..."
  python3 -c '
import os, time, psycopg
url = os.environ.get("DATABASE_URL")
for i in range(30):
    try:
        with psycopg.connect(url, connect_timeout=3) as conn:
            print("[✓] Connected to PostgreSQL successfully.")
            break
    except Exception as e:
        time.sleep(1)
else:
    print("[!] Database connection wait timed out, continuing...")
'
fi

# Trap signals for graceful shutdown
cleanup() {
  echo "[*] Shutting down services..."
  if [ -n "$WEB_PID" ]; then
    kill -TERM "$WEB_PID" 2>/dev/null || true
  fi
  wait
  exit 0
}
trap cleanup SIGTERM SIGINT

# Start Web Server (FastAPI + Mini App static files)
echo "[*] Starting CyberLearn Web Studio on port 8000..."
python3 -m notes_bot.web &
WEB_PID=$!

# Start Telegram Bot polling in foreground
echo "[*] Starting Telegram Bot polling..."
python3 -m notes_bot.main &
BOT_PID=$!

# Wait for any process to exit
wait -n $WEB_PID $BOT_PID
cleanup

