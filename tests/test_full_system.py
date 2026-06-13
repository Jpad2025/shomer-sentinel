"""
Script manual legacy (no suite pytest moderna).
Importaba módulos eliminados (router_http_manager, advanced_recovery).
Las funciones se llamaban test_* por histórico; renombradas para no confundir pytest.
Desarrollado por USB Ingeniería SAS y USB Engineers LLC
"""
import sys
import os
import time
import subprocess
import logging
import sqlite3
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Añadir rutas para importaciones
sys.path.insert(0, '/opt/network_monitor')
sys.path.insert(0, '/opt/network_monitor/app/backend')
sys.path.insert(0, '/opt/network_monitor/app/scripts')

# Importar módulos
try:
    from router_http_manager import RouterHTTPManager
    from advanced_recovery import advanced_recovery
    MODULES_AVAILABLE = True
except ImportError as e:
    logger.error(f"Error importando módulos: {str(e)}")
    MODULES_AVAILABLE = False

def print_header(title):
    """Imprimir encabezado de sección"""
    print("\n" + "="*60)
    print(title)
    print("="*60)

def ping_device(ip, count=1):
    """Verificar si un dispositivo responde a ping"""
    try:
        result = subprocess.run(
            f"ping -c {count} -W 2 {ip}",
            shell=True,
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False

def get_devices_from_db():
    """Obtener dispositivos de la base de datos (/storage/db/ desde app.backend.db)"""
    try:
        from app.backend.db import connect
        conn = connect()
        conn.row_factory = sqlite3.Row
        devices = conn.execute("SELECT * FROM devices WHERE is_active = 1").fetchall()
        conn.close()
        return [dict(d) for d in devices]
    except Exception as e:
        logger.error(f"Error obteniendo dispositivos: {str(e)}")
        return []

def run_system_status_check():
    """Probar estado general del sistema"""
    print_header("ESTADO DEL SISTEMA")
    
    # Verificar servicios
    services = ["network-api", "network-monitor", "network-recovery"]
    for service in services:
        status = subprocess.run(
            f"systemctl is-active {service}.service",
            shell=True,
            capture_output=True,
            text=True
        ).stdout.strip()
        
        print(f"Servicio {service}: {'✅ ACTIVO' if status == 'active' else '❌ INACTIVO'}")
    
    # Verificar API
    api_status = subprocess.run(
        "curl -s http://localhost:8000/api > /dev/null && echo OK || echo FAIL",
        shell=True,
        capture_output=True,
        text=True
    ).stdout.strip()
    
    print(f"API: {'✅ OK' if api_status == 'OK' else '❌ FAIL'}")
    
    # Verificar base de datos
    try:
        from app.backend.db import connect
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM devices")
        device_count = cursor.fetchone()[0]
        conn.close()
        print(f"Base de datos: ✅ OK ({device_count} dispositivos)")
    except Exception as e:
        print(f"Base de datos: ❌ ERROR ({str(e)})")

def run_device_connectivity_check():
    """Probar conectividad con dispositivos"""
    print_header("CONECTIVIDAD CON DISPOSITIVOS")
    
    devices = get_devices_from_db()
    if not devices:
        print("No se encontraron dispositivos en la base de datos")
        return
    
    for device in devices:
        ip = device['ip_address']
        name = device['name']
        
        is_online = ping_device(ip, count=3)
        status = "✅ ONLINE" if is_online else "❌ OFFLINE"
        
        print(f"{name} ({ip}): {status}")

def run_recovery_methods_check():
    """Probar métodos de recuperación"""
    print_header("MÉTODOS DE RECUPERACIÓN")
    
    if not MODULES_AVAILABLE:
        print("❌ Módulos de recuperación no disponibles")
        return
    
    # Probar gestor HTTP
    http_manager = RouterHTTPManager(timeout=5)
    print("✅ Gestor HTTP inicializado correctamente")
    
    # Listar métodos disponibles
    methods = [m for m in dir(http_manager) if not m.startswith('_') and callable(getattr(http_manager, m))]
    print("\nMétodos HTTP disponibles:")
    for method in methods:
        print(f"  - {method}")
    
    # Probar recuperación avanzada
    print("\nMétodos de recuperación avanzada disponibles:")
    adv_methods = [m for m in dir(advanced_recovery) if not m.startswith('_') and callable(getattr(advanced_recovery, m))]
    for method in adv_methods:
        print(f"  - {method}")

def main():
    """Función principal"""
    print_header("PRUEBA COMPLETA DEL SISTEMA NETWORK MONITOR")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Desarrollado por USB Ingeniería SAS y USB Engineers LLC")
    
    # Probar estado del sistema
    run_system_status_check()
    
    # Probar conectividad con dispositivos
    run_device_connectivity_check()
    
    # Probar métodos de recuperación
    run_recovery_methods_check()
    
    print_header("PRUEBA COMPLETADA")

if __name__ == "__main__":
    main()
