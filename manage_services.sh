#!/bin/bash
# Script de gestión de servicios Network Monitor MVP

SERVICES=("network-monitor" "network-recovery" "network-api")
LOG_DIR="/var/log/shomer"

show_status() {
    echo "🔍 Estado de los servicios Network Monitor:"
    echo "=============================================="
    for service in "${SERVICES[@]}"; do
        echo ""
        echo "📊 $service.service:"
        sudo systemctl status $service.service --no-pager -l
        echo ""
    done
}

start_all() {
    echo "🚀 Iniciando todos los servicios..."
    for service in "${SERVICES[@]}"; do
        echo "▶️ Iniciando $service.service..."
        sudo systemctl start $service.service
        if [ $? -eq 0 ]; then
            echo "✅ $service.service iniciado correctamente"
        else
            echo "❌ Error al iniciar $service.service"
        fi
    done
    echo ""
    show_status
}

stop_all() {
    echo "🛑 Deteniendo todos los servicios..."
    for service in "${SERVICES[@]}"; do
        echo "⏹️ Deteniendo $service.service..."
        sudo systemctl stop $service.service
        if [ $? -eq 0 ]; then
            echo "✅ $service.service detenido correctamente"
        else
            echo "❌ Error al detener $service.service"
        fi
    done
}

restart_all() {
    echo "🔄 Reiniciando todos los servicios..."
    stop_all
    sleep 2
    start_all
}

show_logs() {
    echo "📋 Logs de los servicios:"
    echo "========================"
    echo ""
    echo "🔍 Monitor logs:"
    tail -20 $LOG_DIR/monitoring/monitor.log 2>/dev/null || echo "No hay logs de monitor"
    echo ""
    echo "🔧 Recovery logs:"
    tail -20 $LOG_DIR/recovery/recovery.log 2>/dev/null || echo "No hay logs de recovery"
    echo ""
    echo "🌐 API logs (systemd):"
    sudo journalctl -u network-api.service --no-pager -n 20
}

test_api() {
    echo "🧪 Probando endpoints de la API..."
    echo "=================================="
    API_BASE="http://192.168.1.205:8000"
    
    echo "📊 Estado general:"
    curl -s "$API_BASE/" | python3 -m json.tool 2>/dev/null || echo "Error al conectar con la API"
    echo ""
    
    echo "📱 Dispositivos:"
    curl -s "$API_BASE/api/devices/" | python3 -m json.tool 2>/dev/null || echo "Error al obtener dispositivos"
    echo ""
    
    echo "📈 Estadísticas de monitoreo:"
    curl -s "$API_BASE/api/devices/monitoring/stats" | python3 -m json.tool 2>/dev/null || echo "Error al obtener estadísticas"
    echo ""
}

show_help() {
    echo "🛠️ Network Monitor MVP - Gestión de Servicios"
    echo "=============================================="
    echo ""
    echo "Uso: $0 [comando]"
    echo ""
    echo "Comandos disponibles:"
    echo "  status  - Mostrar estado de todos los servicios"
    echo "  start
Bash


    echo "  start   - Iniciar todos los servicios"
    echo "  stop    - Detener todos los servicios"
    echo "  restart - Reiniciar todos los servicios"
    echo "  logs    - Mostrar logs recientes"
    echo "  test    - Probar endpoints de la API"
    echo "  help    - Mostrar esta ayuda"
    echo ""
    echo "Ejemplos:"
    echo "  $0 status"
    echo "  $0 restart"
    echo "  $0 test"
    echo ""
}

case "$1" in
    status)
        show_status
        ;;
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        restart_all
        ;;
    logs)
        show_logs
        ;;
    test)
        test_api
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "❌ Comando no reconocido: $1"
        echo ""
        show_help
        exit 1
        ;;
esac
