#!/bin/bash
# SHOMER API - Lanza la API FastAPI en el puerto 8000
# Uso: ./start_api.sh  o  bash start_api.sh

cd /opt/network_monitor
export PYTHONPATH="/opt/network_monitor:$PYTHONPATH"

exec /usr/bin/python3 -m uvicorn app.api.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload
