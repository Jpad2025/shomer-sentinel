#!/bin/bash
# Configura Suricata en laboratorio (sin SPAN obligatorio).
# Uso: sudo bash tools/suricata_lab_setup.sh [NIC_ESPEJO]
# Ejemplo mini PC Utah: sudo MIRROR_IFACE=enp2s0 bash tools/suricata_lab_setup.sh
# Ejemplo lab .205:      sudo MIRROR_IFACE=enp4s0 bash tools/suricata_lab_setup.sh

set -euo pipefail

MIRROR_IFACE="${MIRROR_IFACE:-${1:-enp2s0}}"
REPO="${REPO:-/opt/network_monitor}"
RULES_SRC="$REPO/tools/suricata/shomer-local.rules"
RUNTIME="/etc/shomer/shomer-runtime.env"
DB="/storage/db/network_monitor.db"

log() { echo "[suricata-lab] $*"; }

if [[ $EUID -ne 0 ]]; then
  echo "Ejecutar como root: sudo bash $0 $*" >&2
  exit 1
fi

log "NIC espejo: $MIRROR_IFACE"

# 1. Ruleset ET
if [[ ! -s /var/lib/suricata/rules/suricata.rules ]]; then
  log "Descargando ruleset (suricata-update)..."
  suricata-update
fi

# 2. Reglas locales Shomer
install -d /etc/suricata/rules
if [[ -f "$RULES_SRC" ]]; then
  cp "$RULES_SRC" /etc/suricata/rules/shomer-local.rules
else
  log "AVISO: no existe $RULES_SRC"
fi
ln -sf /etc/suricata/rules/shomer-local.rules /var/lib/suricata/rules/shomer-local.rules

# 3. Plantilla suricata.yaml desde lab .205 si existe; si no, parchear stock
if [[ -f /etc/suricata/suricata.yaml.bak-shomer ]]; then
  cp /etc/suricata/suricata.yaml.bak-shomer /etc/suricata/suricata.yaml
elif [[ ! -f /etc/suricata/suricata.yaml.bak-install ]]; then
  cp /etc/suricata/suricata.yaml /etc/suricata/suricata.yaml.bak-install
fi

# Sustituir interfaces legacy por NIC espejo
sed -i "s/interface: eth0/interface: ${MIRROR_IFACE}/g" /etc/suricata/suricata.yaml
sed -i "s/interface: enp4s0/interface: ${MIRROR_IFACE}/g" /etc/suricata/suricata.yaml
sed -i "s/interface: enp2s0/interface: ${MIRROR_IFACE}/g" /etc/suricata/suricata.yaml

# default-rule-path → /var/lib (fix §AJ — suricata-update escribe ahí)
if grep -q '^default-rule-path:' /etc/suricata/suricata.yaml; then
  sed -i 's|^default-rule-path:.*|default-rule-path: /var/lib/suricata/rules|' /etc/suricata/suricata.yaml
else
  cat >> /etc/suricata/suricata.yaml <<'YAML'

default-rule-path: /var/lib/suricata/rules
rule-files:
  - suricata.rules
  - shomer-local.rules
YAML
fi
if ! grep -q 'shomer-local.rules' /etc/suricata/suricata.yaml; then
  sed -i '/^rule-files:/a\  - shomer-local.rules' /etc/suricata/suricata.yaml
fi

# eve-alerts.json para Wazuh/panel (si no existe bloque)
if ! grep -q 'eve-alerts.json' /etc/suricata/suricata.yaml; then
  python3 <<'PY'
from pathlib import Path
p = Path("/etc/suricata/suricata.yaml")
text = p.read_text()
needle = "outputs:"
block = """  - eve-log:
      enabled: yes
      filetype: regular
      filename: eve-alerts.json
      types:
        - alert

"""
if needle in text and "eve-alerts.json" not in text:
    text = text.replace(needle, needle + "\n" + block, 1)
    p.write_text(text)
PY
fi

install -d /var/log/suricata
touch /var/log/suricata/eve-alerts.json /var/log/suricata/eve.json
chown suricata:suricata /var/log/suricata/*.json 2>/dev/null || true

# 4. NIC espejo UP sin IP (lab sin cable SPAN)
ip link set "$MIRROR_IFACE" up 2>/dev/null || true

# 5. Modo lab — pipeline no falla sin tráfico espejo
if [[ -f "$RUNTIME" ]]; then
  if grep -q '^SHOMER_LAB_NO_SPAN=' "$RUNTIME"; then
    sed -i 's/^SHOMER_LAB_NO_SPAN=.*/SHOMER_LAB_NO_SPAN=1/' "$RUNTIME"
  else
    echo 'SHOMER_LAB_NO_SPAN=1' >> "$RUNTIME"
  fi
fi

# 6. BD hunter.interfaces (si existe BD)
if [[ -f "$DB" ]] && command -v sqlite3 >/dev/null; then
  sqlite3 "$DB" "INSERT OR REPLACE INTO system_state(key,value) VALUES('hunter.interfaces', '[\"${MIRROR_IFACE}\"]');"
  sqlite3 "$DB" "INSERT OR IGNORE INTO system_state(key,value) VALUES('hunter.enabled','true');"
fi

# 7. Validar y arrancar
log "Validando configuración..."
suricata -T -c /etc/suricata/suricata.yaml 2>&1 | tail -3
systemctl enable suricata
systemctl restart suricata
sleep 2
if systemctl is-active --quiet suricata; then
  log "OK — suricata active en $MIRROR_IFACE"
else
  log "ERROR — suricata no arrancó; ver journalctl -u suricata"
  exit 1
fi
