#!/bin/bash
# Makes Pi Self-Learning AI start automatically whenever the Pi boots,
# and restart by itself if it ever crashes. The math AI picks up where it left off.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3)"

sudo tee /etc/systemd/system/selflearning.service > /dev/null << SERVICE
[Unit]
Description=Pi Self-Learning AI
After=network.target

[Service]
User=$USER
WorkingDirectory=$DIR
ExecStart=$PY $DIR/server.py
Restart=always
RestartSec=10
TimeoutStopSec=20
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable selflearning
sudo systemctl restart selflearning
echo
echo "Done! Pi Self-Learning AI is running in the background and starts on boot."
echo "Open:          http://$(hostname).local:8100"
echo "    (or use the Pi's IP address:  http://YOUR-PI-IP:8100  - find it with: hostname -I)"
echo "See its log:   journalctl -u selflearning -f"
echo "Stop it:       sudo systemctl stop selflearning"
