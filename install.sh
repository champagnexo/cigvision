#!/usr/bin/env bash
# Peuken Stembus installer for a Raspberry Pi 5 running Raspberry Pi OS (Bookworm or Trixie).
# Usage: ./install.sh [--service]
#   --service  also start the program at boot (sets headless: True in config.yaml)
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
WITH_SERVICE=0
[ "${1:-}" = "--service" ] && WITH_SERVICE=1

if [ "$(id -u)" -eq 0 ]; then
  echo "Run this as your normal user, not root. It uses sudo where needed."
  exit 1
fi
grep -q "Raspberry Pi 5" /proc/device-tree/model 2>/dev/null || echo "WARNING: this does not look like a Raspberry Pi 5."

echo "== 1/6 System packages"
sudo apt update
sudo apt install -y python3-venv python3-pip python3-numpy python3-opencv \
  python3-gpiozero python3-lgpio python3-rpi-lgpio
sudo apt install -y --no-install-recommends python3-picamera2

echo "== 2/6 Folders"
mkdir -p Data Debug Dataset Images/Originals/butt Images/Originals/not_butt

echo "== 3/6 Python environment (venv with access to the system picamera2)"
python3 -m venv --system-site-packages venv
# shellcheck disable=SC1091
. venv/bin/activate
python -m pip install --upgrade pip
# keep numpy compatible with the system packages (picamera2, OpenCV)
if [ "$(python -c 'import numpy; print(numpy.__version__.split(".")[0])')" = "1" ]; then
  echo "numpy<2" > venv/constraints.txt
else
  : > venv/constraints.txt
fi
pip install -r requirements.txt -c venv/constraints.txt

echo "== 4/6 Permissions for the NeoPixel ring (PIO) and GPIO"
echo 'SUBSYSTEM=="*-pio", GROUP="gpio", MODE="0660"' | sudo tee /etc/udev/rules.d/99-pio.rules >/dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger
sudo usermod -aG gpio,video "$USER"
if [ ! -e /dev/pio0 ]; then
  echo "NOTE: /dev/pio0 not found. Update the firmware, then reboot:"
  echo "      sudo apt full-upgrade -y && sudo rpi-eeprom-update -a && sudo reboot"
fi

echo "== 5/6 Autostart"
if [ "$WITH_SERVICE" -eq 1 ]; then
  sed -i 's/^headless:.*/headless: True/' src_runtime/config.yaml
  sudo tee /etc/systemd/system/peuken.service >/dev/null <<EOF
[Unit]
Description=Peuken Stembus
After=network-online.target
Wants=network-online.target
ConditionPathExists=$ROOT/Data/butt_cls.pt

[Service]
User=$USER
WorkingDirectory=$ROOT/src_runtime
ExecStart=$ROOT/venv/bin/python runtime.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable peuken.service
  echo "Service enabled. It starts at boot once Data/butt_cls.pt exists."
else
  echo "Skipped (run ./install.sh --service to start at boot)."
fi

echo "== 6/6 Check"
python src_runtime/check_install.py || true

cat <<MSG

Done. Next steps:
  1. Reboot once so the new group permissions apply:  sudo reboot
  2. Train the model and put it at Data/butt_cls.pt (see README.md)
  3. Run:  cd $ROOT/src_runtime && ../venv/bin/python runtime.py
MSG
