#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PID_FILE="$DIR/.services.pid"

start_services() {
  if [ -f "$PID_FILE" ]; then
    echo "[!] Services are already marked as running in $PID_FILE."
    echo "[*] Run './service_manager.sh status' or './service_manager.sh stop' first."
    exit 1
  fi

  echo "=========================================================="
  echo "   Starting CyberLearn Studio & Bot in Background         "
  echo "=========================================================="

  # 1. Check PostgreSQL
  if ! pg_isready -q 2>/dev/null; then
    echo "[*] Starting PostgreSQL service..."
    sudo systemctl start postgresql 2>/dev/null || true
    sleep 1
    if ! pg_isready -q 2>/dev/null; then
      echo "[!] Error: PostgreSQL is offline. Please run:"
      echo "    sudo systemctl enable --now postgresql"
      exit 1
    fi
  fi
  echo "[✓] PostgreSQL is active."

  source .venv/bin/activate

  # 2. Start Web Server
  echo "[*] Starting Studio Web Server..."
  PYTHONPATH=. nohup python -m notes_bot.web > web.log 2>&1 &
  WEB_PID=$!

  # 3. Start Tunnel
  echo "[*] Starting HTTPS Tunnel..."
  rm -f .tunnel_ready
  nohup python tunnel_runner.py > tunnel.log 2>&1 &
  TUNNEL_PID=$!

  # Wait briefly for tunnel URL
  echo "[*] Establishing tunnel connection..."
  for i in {1..30}; do
    if [ -s ".tunnel_ready" ]; then
      break
    fi
    sleep 1
  done

  # 4. Start Telegram Bot
  echo "[*] Starting Telegram Bot..."
  PYTHONPATH=. nohup python -m notes_bot.main > bot.log 2>&1 &
  BOT_PID=$!

  echo "$WEB_PID $TUNNEL_PID $BOT_PID" > "$PID_FILE"

  LIVE_URL=$(cat .tunnel_ready 2>/dev/null || grep -E "^MINI_APP_URL=" .env | cut -d'=' -f2-)
  echo ""
  echo "=========================================================="
  echo "   [✓] All Services Are Now Running in Background!        "
  echo "   - Web Studio: http://127.0.0.1:8000                    "
  echo "   - Live URL:   ${LIVE_URL:-Establishing...}             "
  echo "   - Logs:       bot.log, web.log, tunnel.log             "
  echo "=========================================================="
  echo "To check status: ./service_manager.sh status"
  echo "To stop:         ./service_manager.sh stop"
}

stop_services() {
  echo "[*] Stopping services..."
  if [ -f "$PID_FILE" ]; then
    read -r WEB_PID TUNNEL_PID BOT_PID < "$PID_FILE" || true
    [ -n "$BOT_PID" ] && kill "$BOT_PID" 2>/dev/null || true
    [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null || true
    [ -n "$WEB_PID" ] && kill "$WEB_PID" 2>/dev/null || true
    rm -f "$PID_FILE"
  fi
  pkill -f "notes_bot.main" 2>/dev/null || true
  pkill -f "notes_bot.web" 2>/dev/null || true
  pkill -f "tunnel_runner.py" 2>/dev/null || true
  rm -f .tunnel_ready
  echo "[✓] All services stopped."
}

status_services() {
  echo "=========================================================="
  echo "   CyberLearn Service Status                              "
  echo "=========================================================="
  if pg_isready -q 2>/dev/null; then
    echo "  [✓] PostgreSQL:  ONLINE"
  else
    echo "  [✗] PostgreSQL:  OFFLINE (run: sudo systemctl enable --now postgresql)"
  fi

  if pgrep -f "notes_bot.web" >/dev/null; then
    echo "  [✓] Web Server:  RUNNING (http://127.0.0.1:8000)"
  else
    echo "  [✗] Web Server:  STOPPED"
  fi

  if pgrep -f "tunnel_runner.py" >/dev/null; then
    LIVE_URL=$(cat .tunnel_ready 2>/dev/null || grep -E "^MINI_APP_URL=" .env | cut -d'=' -f2-)
    echo "  [✓] Tunnel:      ONLINE ($LIVE_URL)"
  else
    echo "  [✗] Tunnel:      STOPPED"
  fi

  if pgrep -f "notes_bot.main" >/dev/null; then
    echo "  [✓] Telegram Bot: RUNNING (polling active)"
  else
    echo "  [✗] Telegram Bot: STOPPED"
  fi
  echo "=========================================================="
}

case "${1:-status}" in
  start)
    start_services
    ;;
  stop)
    stop_services
    ;;
  restart)
    stop_services
    sleep 1
    start_services
    ;;
  status)
    status_services
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac

