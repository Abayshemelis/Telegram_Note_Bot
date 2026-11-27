#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=========================================================="
echo "   Installing CyberLearn 24/7 Autostart Service           "
echo "=========================================================="

echo "[1/3] Enabling PostgreSQL on system boot..."
sudo systemctl enable --now postgresql

echo "[2/3] Installing CyberLearn systemd service..."
sudo cp "$DIR/cyberlearn.service" /etc/systemd/system/cyberlearn.service
sudo systemctl daemon-reload

echo "[3/3] Enabling and starting CyberLearn service..."
sudo systemctl enable --now cyberlearn.service

echo ""
echo "=========================================================="
echo "   [✓] SUCCESS: CyberLearn is now running 24/7!           "
echo "=========================================================="
echo "The bot, studio, and database will now start automatically"
echo "every time your computer boots up."
echo ""
echo "Useful commands:"
echo "  Check status:  sudo systemctl status cyberlearn"
echo "  Restart:       sudo systemctl restart cyberlearn"
echo "  Stop:          sudo systemctl stop cyberlearn"
echo "  View logs:     journalctl -u cyberlearn -f"

