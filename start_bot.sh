#!/usr/bin/env bash
set -e

SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
cd "$DIR"

echo "============================================="
echo "   Telegram Note Bot - Startup Helper        "
echo "============================================="

# 1. Verify Virtual Environment
if [ ! -d ".venv" ]; then
  echo "[!] .venv not found. Creating virtual environment and installing requirements..."
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

# 2. Check PostgreSQL service
if ! pg_isready -q 2>/dev/null; then
  echo "[*] PostgreSQL is not running. Attempting to start service..."
  if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
    sudo systemctl start postgresql 2>/dev/null || true
  elif [ -d "/var/lib/postgres/data" ]; then
    sudo -u postgres pg_ctl -D /var/lib/postgres/data -l /var/lib/postgres/data/logfile start 2>/dev/null || true
  fi
  sleep 1
  if ! pg_isready -q 2>/dev/null; then
    echo "[!] Warning: PostgreSQL is inactive. The bot may fail to connect to the database."
    echo "[!] Run: sudo systemctl start postgresql"
  else
    echo "[✓] PostgreSQL is online."
  fi
else
  echo "[✓] PostgreSQL is online."
fi

echo ""
echo "[*] Starting Telegram Bot polling..."
echo "---------------------------------------------"
echo "Press Ctrl+C to stop the bot."
echo "---------------------------------------------"

PYTHONPATH=. .venv/bin/python -m notes_bot.main

