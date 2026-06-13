#!/bin/bash
# factory_reset_network.sh — IP de fábrica en la NIC de gestión antes de ir a un cliente nuevo.
#
# Hardware de referencia del Mini PC Shomer (este equipo): gestión = enp2s0, mirror (SPAN/Hunter) = enp4s0.
# Otro modelo en el futuro: export SHOMER_MANAGEMENT_INTERFACE=… SHOMER_MIRROR_INTERFACE=…
#
# Flujo técnico en cliente (resumen): colocar Shomer + Mikrotik + APs en red → /setup (escaneo, fijar IPs
# de gestión y mirror en la subred del cliente) → Guardian (APs), Hunter (mirror ya cableada),
# Protector (backups programados), Tracker cuando pidan inventario/auditoría → Telegram.
#
# Variables opcionales (p. ej. /etc/shomer/shomer-runtime.env):
#   SHOMER_MANAGEMENT_INTERFACE — default enp2s0
#   SHOMER_MIRROR_INTERFACE     — default enp4s0 (si su bloque existe en netplan actual, se preserva)
#   SHOMER_FACTORY_IP / PREFIX / GW — defaults 192.168.0.205 / 24 / 192.168.0.1
#
# Uso: sudo bash /opt/network_monitor/tools/factory_reset_network.sh
#
set -e

FACTORY_IP="${SHOMER_FACTORY_IP:-192.168.0.205}"
FACTORY_PREFIX="${SHOMER_FACTORY_PREFIX:-24}"
FACTORY_GW="${SHOMER_FACTORY_GW:-192.168.0.1}"
NETPLAN_FILE="${SHOMER_NETPLAN_FILE:-/etc/netplan/01-network-config.yaml}"

# Mini PC referencia USB: enp2s0 = panel/API/SSH; otra generación → SHOMER_MANAGEMENT_INTERFACE
INTERFACE="${SHOMER_MANAGEMENT_INTERFACE:-enp2s0}"
MIRROR_IF="${SHOMER_MIRROR_INTERFACE:-enp4s0}"

MIRROR_BLOCK=""
if [ -n "$MIRROR_IF" ] && [ -f "$NETPLAN_FILE" ] && grep -q "${MIRROR_IF}:" "$NETPLAN_FILE" 2>/dev/null; then
  MIR_ADDR=$(grep -A8 "${MIRROR_IF}:" "$NETPLAN_FILE" | grep "addresses:" | grep -oE '[0-9.]+/[0-9]+' | head -1 || true)
  if [ -n "$MIR_ADDR" ]; then
    MIRROR_BLOCK="
    ${MIRROR_IF}:
      dhcp4: false
      addresses: [$MIR_ADDR]"
    echo "Preservando $MIRROR_IF: $MIR_ADDR"
  fi
fi

echo "=== Shomer Sentinel — Factory Reset Network ==="
echo "Interfaz gestión : $INTERFACE  (mirror referencia: $MIRROR_IF)"
echo "IP fábrica       : $FACTORY_IP/$FACTORY_PREFIX  gateway $FACTORY_GW"
echo ""

umask 022
mkdir -p "$(dirname "$NETPLAN_FILE")"

cat > "$NETPLAN_FILE" << YAML
network:
  version: 2
  renderer: networkd
  ethernets:
    $INTERFACE:
      dhcp4: false
      addresses: [$FACTORY_IP/$FACTORY_PREFIX]
      routes:
        - to: default
          via: $FACTORY_GW
      nameservers:
        addresses: [8.8.8.8, 1.1.1.1]$MIRROR_BLOCK
YAML

echo "Netplan escrito: $NETPLAN_FILE"
netplan apply
echo "Netplan aplicado."
echo ""
echo "=== Listo ==="
echo "Asistente: http://$FACTORY_IP:8000/setup"
