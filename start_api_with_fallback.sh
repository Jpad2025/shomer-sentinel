#!/bin/bash
# SHOMER API - Arranque con fallback sshpass para reinicio SSH
# Usa SSH_FALLBACK_PASSWORD para conectar al router cuando la llave falla.
# Ejecutar: ./start_api_with_fallback.sh

cd /opt/network_monitor
export PYTHONPATH="/opt/network_monitor:$PYTHONPATH"
export SSH_FALLBACK_PASSWORD='Usbing08@2026'

nohup /usr/bin/python3 -m uvicorn app.api.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload >> /var/log/shomer/api.log 2>&1 &

echo "API arrancada en puerto 8000 (PID $!). Log: /var/log/shomer/api.log"
echo "Tools (inventario, backups, export): sudo systemctl start shomer-tools.service  (puerto 8001; ver CLAUDE.md)"
