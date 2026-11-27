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

echo "=========================================================="
echo "   CyberLearn Studio & Telegram Bot - All-in-One Launcher "
echo "=========================================================="

# Guard against duplicate runs when systemd service is active or another instance is running
if systemctl is-active --quiet cyberlearn 2>/dev/null; then
  SERVICE_PID=$(systemctl show -p MainPID --value cyberlearn 2>/dev/null || true)
  if [ "$$" != "$SERVICE_PID" ] && ! pgrep -P "$SERVICE_PID" 2>/dev/null | grep -q "^$$\$"; then
    echo "=========================================================="
    echo "   CyberLearn is ALREADY running 24/7 via systemd!        "
    echo "=========================================================="
    LIVE_URL=$(cat .tunnel_ready 2>/dev/null || grep -E "^MINI_APP_URL=" .env 2>/dev/null | cut -d'=' -f2-)
    echo "  - Web Studio: http://127.0.0.1:8000"
    echo "  - Tunnel URL: $LIVE_URL"
    echo "  - Bot Status: Active (managed by systemd)"
    echo "=========================================================="
    echo "Streaming live logs below (Press Ctrl+C to exit log view):"
    exec journalctl -u cyberlearn -f
  fi
elif pgrep -f "notes_bot.main" >/dev/null; then
  echo "[!] An instance of CyberLearn bot is already running (PID: $(pgrep -f 'notes_bot.main' | tr '\n' ' '))."
  echo "[!] Running duplicate instances causes Telegram Conflict errors."
  echo "[*] If you want to restart, run: ./service_manager.sh restart"
  exit 1
fi

WEB_PID=""
TUNNEL_PID=""

cleanup() {
  echo ""
  echo "[*] Stopping background services..."
  if [ -n "$WEB_PID" ]; then
    kill "$WEB_PID" 2>/dev/null || true
  fi
  if [ -n "$TUNNEL_PID" ]; then
    kill "$TUNNEL_PID" 2>/dev/null || true
  fi
  pkill -P $$ 2>/dev/null || true
  rm -f .tunnel_ready
  echo "[✓] All services stopped."
  exit 0
}
trap cleanup SIGINT SIGTERM

# 1. Virtual Environment check
if [ ! -d ".venv" ]; then
  echo "[!] .venv not found. Creating virtualenv..."
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
source .venv/bin/activate

# 2. Check PostgreSQL
if ! pg_isready -q 2>/dev/null; then
  echo "[*] Attempting to start PostgreSQL service..."
  if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
    sudo systemctl start postgresql 2>/dev/null || true
  elif [ -d "/var/lib/postgres/data" ]; then
    sudo -u postgres pg_ctl -D /var/lib/postgres/data -l /var/lib/postgres/data/logfile start 2>/dev/null || true
  fi
  sleep 1
fi
if pg_isready -q 2>/dev/null; then
  echo "[✓] PostgreSQL is online."
else
  echo "[!] Warning: PostgreSQL is inactive. If connection fails, run: sudo systemctl start postgresql"
fi

# 3. Start Web API server in background (auto-restarting supervisor)
echo "[*] Launching Studio Web Server on http://127.0.0.1:8000..."
(
  while true; do
    PYTHONPATH=. python -m notes_bot.web >> web.log 2>&1 || true
    sleep 2
  done
) &
WEB_PID=$!

# Wait for web server to start
sleep 1

# 4. Start HTTPS Tunnel in background & wait for live URL
echo "[*] Launching HTTPS Tunnel..."
rm -f .tunnel_ready
python tunnel_runner.py > tunnel.log 2>&1 &
TUNNEL_PID=$!

echo "[*] Connecting tunnel to Cloudflare and obtaining fresh HTTPS URL..."
FRESH_URL=""
for i in {1..60}; do
  if [ -s ".tunnel_ready" ]; then
    FRESH_URL=$(cat .tunnel_ready | tr -d '\r\n')
    break
  fi
  sleep 1
done

if [ -n "$FRESH_URL" ]; then
  echo "[✓] Fresh HTTPS Tunnel: $FRESH_URL"
  export MINI_APP_URL="$FRESH_URL"
else
  FRESH_URL=$(grep -E "^MINI_APP_URL=https://" .env 2>/dev/null | cut -d'=' -f2- | tr -d '\r' || true)
  echo "[*] Using tunnel URL: $FRESH_URL"
fi

# 5. Start Telegram Bot in foreground
echo ""
echo "=========================================================="
echo "   All Systems Online!                                    "
echo "   - Web Studio: http://127.0.0.1:8000                    "
echo "   - Tunnel URL: ${FRESH_URL:-$CURRENT_URL}               "
echo "   - Telegram Bot: Polling active                         "
echo "=========================================================="
echo "Press Ctrl+C at any time to stop all services."
echo "----------------------------------------------------------"

while true; do
  PYTHONPATH=. python -m notes_bot.main || {
    echo "[!] Telegram bot exited. Reconnecting in 5 seconds..."
    sleep 5
  }
done

