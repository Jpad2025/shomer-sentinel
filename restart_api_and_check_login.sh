#!/bin/bash
# Reinicia la API SHOMER y comprueba que /login y /api/login respondan.
# Uso: ./restart_api_and_check_login.sh

cd /opt/network_monitor
export PYTHONPATH="/opt/network_monitor:$PYTHONPATH"

echo "=== Deteniendo uvicorn (si está en ejecución) ==="
pkill -f "uvicorn app.api.main:app" 2>/dev/null || true
sleep 2

echo "=== Iniciando API en segundo plano (puerto 8000) ==="
nohup /usr/bin/python3 -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000 >> /var/log/shomer/api.log 2>&1 &
API_PID=$!
echo "PID: $API_PID"
sleep 3

echo "=== Comprobando rutas de login ==="
echo -n "GET http://127.0.0.1:8000/login/ok -> "
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/login/ok
echo ""
echo -n "GET http://127.0.0.1:8000/login -> "
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/login
echo ""
echo -n "GET http://127.0.0.1:8000/api/login -> "
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/login
echo ""

echo "=== Si ves 200 en las tres líneas, las rutas están activas. Abre en el navegador: ==="
echo "  http://TU_IP:8000/login   o   http://TU_IP:8000/api/login"
