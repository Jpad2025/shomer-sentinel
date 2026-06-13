#!/bin/bash
# Crea /var/log/shomer/ y asigna permisos para que los módulos SHOMER (Protector, etc.) puedan escribir.
# Ejecutar una vez con: sudo /opt/network_monitor/ensure_shomer_log_dir.sh
# O como root: mkdir -p /var/log/shomer && chown usb_admin:usb_admin /var/log/shomer

set -e
LOG_DIR="/var/log/shomer"
OWNER="${SHOMER_LOG_OWNER:-usb_admin}"

if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR"
    echo "Creado: $LOG_DIR"
fi

if [ "$(id -u)" = "0" ]; then
    chown "$OWNER:$OWNER" "$LOG_DIR"
    chmod 755 "$LOG_DIR"
    echo "Permisos asignados: $LOG_DIR -> $OWNER"
else
    if [ -w "$LOG_DIR" ]; then
        echo "OK: $LOG_DIR existe y es escribible por $(whoami)"
    else
        echo "AVISO: $LOG_DIR existe pero no tiene permisos de escritura para $(whoami)."
        echo "Ejecute: sudo $0"
        exit 1
    fi
fi
