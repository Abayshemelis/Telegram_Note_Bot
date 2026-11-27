#!/usr/bin/env bash
set -e

# Resolve directory even if invoked via symlink
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
cd "$DIR"

echo "============================================="
echo "   CyberLearn Studio - Startup Helper        "
echo "============================================="

# Ensure .venv is used
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
else
  echo "[!] .venv not found in $DIR. Please initialize virtualenv first."
  exit 1
fi

# 1. Start PostgreSQL if inactive
if ! pg_isready -q 2>/dev/null; then
  echo "[*] PostgreSQL is not running. Attempting to start service..."
  if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
    sudo systemctl start postgresql || true
  elif [ -d "/var/lib/postgres/data" ]; then
    sudo -u postgres pg_ctl -D /var/lib/postgres/data -l /var/lib/postgres/data/logfile start || true
  fi
  sleep 1
  if ! pg_isready -q 2>/dev/null; then
    echo "[!] Notice: PostgreSQL is still inactive."
    echo "[!] Please run: sudo systemctl start postgresql (or: sudo -u postgres pg_ctl -D /var/lib/postgres/data start)"
  else
    echo "[✓] PostgreSQL is online."
  fi
fi

# 2. Rebuild frontend bundle
echo "[*] Verifying Mini App production build..."
cd miniapp
if [ -f "/home/amazi1075/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node" ]; then
  /home/amazi1075/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node ./node_modules/vite/bin/vite.js build
else
  npx vite build 2>/dev/null || npm run build 2>/dev/null || true
fi
cd "$DIR"

echo ""
echo "[✓] Frontend is ready in miniapp/dist."
echo "[*] Launching API server on http://127.0.0.1:8000..."
echo "---------------------------------------------"
echo "Press Ctrl+C to stop the web server."
echo "---------------------------------------------"

PYTHONPATH=. python -m notes_bot.web
