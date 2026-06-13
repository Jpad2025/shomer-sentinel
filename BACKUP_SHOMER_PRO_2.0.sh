#!/bin/bash
# Backup SHOMER PRO 2.0 - Servidor 192.168.1.205
# Excluye venv, .git, logs pesados. Incluye código, config, frontend, DB.

set -e
BACKUP_ROOT="${BACKUP_ROOT:-/home/usb_admin/backups}"
STAMP=$(date +%Y%m%d_%H%M%S)
DIR="$BACKUP_ROOT/shomer_pro_2.0_$STAMP"
mkdir -p "$DIR"

echo "Backup SHOMER PRO 2.0 -> $DIR"

# Proyecto (excluir venv, .git, logs grandes)
rsync -a --exclude='venv' --exclude='.git' --exclude='*.log' --exclude='__pycache__' \
  /opt/network_monitor/ "$DIR/opt_network_monitor/" 2>/dev/null || \
  cp -r /opt/network_monitor "$DIR/opt_network_monitor" 2>/dev/null && \
  (rm -rf "$DIR/opt_network_monitor/venv" "$DIR/opt_network_monitor/.git" 2>/dev/null; true)

# Panel servido por Nginx
mkdir -p "$DIR/var_www_html"
cp -r /var/www/html/index.html "$DIR/var_www_html/" 2>/dev/null || true

# Persistencia /storage/db (copiar si existe)
mkdir -p "$DIR/storage_db"
cp /storage/db/network_monitor.db "$DIR/storage_db/" 2>/dev/null || true
cp /storage/db/inventory.db "$DIR/storage_db/" 2>/dev/null || true
cp /storage/db/remedies.json "$DIR/storage_db/" 2>/dev/null || true

# Info de sistema
crontab -l > "$DIR/crontab_usb_admin.txt" 2>/dev/null || true
systemctl list-units --type=service 2>/dev/null | head -30 > "$DIR/services_list.txt" 2>/dev/null || true
nginx -t 2>&1 > "$DIR/nginx_test.txt" 2>/dev/null || true

# Resumen
echo "Backup completado: $DIR" > "$DIR/README.txt"
echo "Fecha: $(date)" >> "$DIR/README.txt"
echo "Contenido: opt_network_monitor, var_www_html, storage_db (/storage/db), crontab, services" >> "$DIR/README.txt"

echo "OK: $DIR"
ls -la "$DIR"
