#!/bin/bash
echo "🚀 Iniciando Network Monitor MVP Server..."

cd /opt/network_monitor
source venv/bin/activate
cd app/backend

# Matar instancias previas si existen
pkill -f "python main.py" || true
sleep 1

# Limpiar archivos .pyc para evitar problemas de caché
find . -name "*.pyc" -delete
find . -name "__pycache__" -delete

# Iniciar servidor en segundo plano
mkdir -p /var/log/shomer/application
nohup python main.py > /var/log/shomer/application/server.log 2>&1 &

# Verificar que está corriendo
sleep 2
if pgrep -f "python main.py" > /dev/null; then
    echo "✅ Servidor iniciado correctamente en puerto 8000"
    echo "📊 Dashboard: http://192.168.1.205:8000"
    echo "📚 API Docs: http://192.168.1.205:8000/api/docs"
    echo "📱 API Dispositivos: http://192.168.1.205:8000/api/devices/"
else
    echo "❌ Error al iniciar el servidor"
    echo "📋 Revisa los logs: cat /var/log/shomer/application/server.log"
