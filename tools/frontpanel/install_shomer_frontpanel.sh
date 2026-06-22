#!/usr/bin/env bash
# Pantalla frontal AceMagic S1 (Holtek 04d9:fd01, 320×170) — tema Shomer via s1panel snap.
# Uso en lab (mini PC): bash tools/frontpanel/install_shomer_frontpanel.sh [hostname_label]
set -euo pipefail

LABEL="${1:-$(hostname -s)}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WALL_SRC="${REPO_ROOT}/app/static/img/shomer-eyes.png"
USB_SRC="${REPO_ROOT}/app/static/img/logo-usb.png"
TMP="/tmp/shomer-frontpanel-$$"
SNAP_DATA="/root/snap/s1panel/current"
PYTHON="${REPO_ROOT}/venv/bin/python3"
if [[ ! -x "$PYTHON" ]] || ! "$PYTHON" -c "import PIL" 2>/dev/null; then
  PYTHON="python3"
fi

if [[ ! -f "$WALL_SRC" ]]; then
  echo "No se encontró $WALL_SRC" >&2
  exit 1
fi
if [[ ! -f "$USB_SRC" ]]; then
  echo "No se encontró $USB_SRC" >&2
  exit 1
fi

mkdir -p "$TMP"
export PYTHONPATH="${REPO_ROOT}"
"$PYTHON" -c "
from pathlib import Path
from tools.frontpanel.render import render_logo_portrait
render_logo_portrait(
    Path('$USB_SRC'), Path('$WALL_SRC'), Path('$TMP/logo-portrait.png'),
    show_status=False,
)
print('logo-portrait', '$TMP/logo-portrait.png')
"

if ! snap list s1panel &>/dev/null; then
  echo "Instalando s1panel (canal edge)..."
  sudo snap install --edge s1panel
  sudo snap connect s1panel:raw-usb
  sudo snap connect s1panel:hardware-observe
  sudo snap connect s1panel:mount-observe
  sudo snap connect s1panel:removable-media
  sudo snap connect s1panel:block-devices
fi

sudo snap stop s1panel

# Tema Shomer
sudo mkdir -p "${SNAP_DATA}/themes/shomer"
sudo cp "$TMP/logo-portrait.png" "${SNAP_DATA}/themes/shomer/logo-portrait.png"

sudo tee "${SNAP_DATA}/themes/shomer/shomer.json" >/dev/null <<JSON
{
   "orientation": "portrait",
   "refresh": "update",
   "screens": [
      {
         "id": 1,
         "name": "Shomer Sentinel",
         "background": "#0d1a2a",
         "duration": 0,
         "led_config": { "theme": 6, "intensity": 3, "speed": 3 },
         "widgets": [
            {
               "id": 0, "group": 1, "name": "image",
               "rect": { "x": 0, "y": 18, "width": 170, "height": 280 },
               "sensor": false,
               "value": "${SNAP_DATA}/themes/shomer/logo-portrait.png",
               "refresh": 0, "debug_frame": false
            },
            {
               "id": 1, "group": 1, "name": "text",
               "rect": { "x": 0, "y": 0, "width": 85, "height": 16 },
               "sensor": true, "value": "clock", "format": "{1} {3}", "refresh": 1000,
               "font": "12px Arial", "color": "#0d6e6e", "align": "left", "debug_frame": false
            },
            {
               "id": 2, "group": 1, "name": "text",
               "rect": { "x": 85, "y": 0, "width": 85, "height": 16 },
               "sensor": true, "value": "calendar", "format": "{9}/{2}/{10}", "refresh": 1000,
               "font": "12px Arial", "color": "#0d6e6e", "align": "right", "debug_frame": false
            },
            {
               "id": 3, "group": 1, "name": "text",
               "rect": { "x": 0, "y": 302, "width": 55, "height": 18 },
               "sensor": true, "value": "cpu_usage", "format": "CPU {0}%", "refresh": 2000,
               "font": "11px Arial", "color": "#47b320", "align": "left", "debug_frame": false
            },
            {
               "id": 4, "group": 1, "name": "text",
               "rect": { "x": 55, "y": 302, "width": 60, "height": 18 },
               "sensor": false, "value": "${LABEL}", "format": "", "refresh": 0,
               "font": "11px Arial", "color": "#0d6e6e", "align": "center", "debug_frame": false
            },
            {
               "id": 5, "group": 1, "name": "text",
               "rect": { "x": 115, "y": 302, "width": 55, "height": 18 },
               "sensor": true, "value": "cpu_temp", "format": "{0}{2}", "refresh": 2000,
               "font": "11px Arial", "color": "#47b320", "align": "right", "debug_frame": false
            }
         ]
      }
   ]
}
JSON

# Conservar canvas/device/led del config embebido del snap; solo cambiar tema y sensores básicos.
BASE="${SNAP_DATA}/config.json"
if [[ ! -f "$BASE" ]]; then
  sudo cp /snap/s1panel/current/s1panel/config.json "$BASE" 2>/dev/null || true
fi

"$PYTHON" <<PY
import json, pathlib
base = pathlib.Path("${SNAP_DATA}/config.json")
cfg = json.loads(base.read_text()) if base.exists() else json.loads(pathlib.Path("/snap/s1panel/current/s1panel/config.json").read_text())
cfg["theme"] = "themes/shomer/shomer.json"
cfg["portrait"] = True
cfg["theme_list"] = [
    {"name": "Shomer Sentinel (portrait)", "config": "themes/shomer/shomer.json"},
    {"name": "Demo portrait (original)", "config": "themes/simple_demo/portrait_simple.json"},
]
cfg["sensors"] = [
    {"module": "sensors/clock.js"},
    {"module": "sensors/calendar.js"},
    {"module": "sensors/cpu_usage.js", "config": {"max_points": 300}},
    {"module": "sensors/cpu_temp.js", "config": {"max_points": 300, "fahrenheit": True}},
    {"module": "sensors/network.js", "config": {"interface": "enp4s0", "max_points": 300}},
    {"module": "sensors/memory.js", "config": {"max_points": 300}},
    {"module": "sensors/space.js", "config": {"name": "root", "mount_point": "/", "max_points": 300}},
]
if "led_config" in cfg:
    # Tema 6 = s1panel no toca /dev/ttyUSB0; lo maneja shomer-led-strip.service
    cfg["led_config"]["theme"] = 6
    cfg["led_config"]["intensity"] = 3
    cfg["led_config"]["speed"] = 3
base.write_text(json.dumps(cfg, indent=3) + "\n")
print("config actualizado", base)
PY

LED_PY="${REPO_ROOT}/venv/bin/python3"
if ! "$LED_PY" -c "import serial" 2>/dev/null; then
  echo "Instalando pyserial en venv..."
  sudo -H "$LED_PY" -m pip install -q pyserial
fi

sudo snap start s1panel
sleep 3
if curl -sf -o /dev/null http://127.0.0.1:8686/; then
  echo "OK — GUI http://$(hostname -I | awk '{print $1}'):8686"
  echo "Pantalla: logo Shomer portrait + hora + CPU. LED arcoíris (shomer-led-strip). Etiqueta: ${LABEL}"
else
  echo "Revisar: sudo snap logs s1panel -n=30" >&2
  exit 1
fi

if [[ -f "${REPO_ROOT}/etc/shomer-led-strip.service" ]]; then
  sudo cp "${REPO_ROOT}/etc/shomer-led-strip.service" /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now shomer-led-strip.service
  echo "Servicio shomer-led-strip activo (arcoíris vía /dev/ttyUSB0)"
fi

# Opción 2 — servicio que actualiza WAN/APs en la imagen
if [[ -f "${REPO_ROOT}/etc/shomer-frontpanel.service" ]]; then
  sudo cp "${REPO_ROOT}/etc/shomer-frontpanel.service" /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now shomer-frontpanel.service
  echo "Servicio shomer-frontpanel activo (estado WAN/AP cada ${FRONTPANEL_POLL_SEC:-30}s)"
fi

rm -rf "$TMP"
