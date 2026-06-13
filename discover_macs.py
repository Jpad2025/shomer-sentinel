"""
import sys
import os
import subprocess
import sqlite3
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# BD desde app.backend.db (/storage/db/network_monitor.db)
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from app.backend.db import get_connection as _get_connection

def get_mac_address(ip):
    """Obtener dirección MAC de una IP"""
    try:
        # Primero hacer ping para asegurar que está en la tabla ARP
        subprocess.run(
            f"ping -c 1 -W 1 {ip}",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        # Obtener MAC de la tabla ARP
        result = subprocess.run(
            f"arp -n {ip} | grep -v Address | awk '{{print $3}}'",
            shell=True,
            capture_output=True,
            text=True
        )
        mac = result.stdout.strip()
        
        if mac and mac != "(incomplete)":
            return mac
        
        return None
    except Exception as e:
        logger.error(f"Error obteniendo MAC para {ip}: {str(e)}")
        return None

def main():
    """Función principal"""
    logger.info("Iniciando descubrimiento de direcciones MAC")
    with _get_connection() as conn:
        devices = conn.execute("SELECT id, name, ip_address FROM devices WHERE is_active = 1").fetchall()
        for device in devices:
            device_id = device["id"]
            name = device["name"]
            ip = device["ip_address"]
            logger.info(f"Procesando {name} ({ip})")
            mac = get_mac_address(ip)
            if mac:
                logger.info(f"MAC encontrada para {name}: {mac}")
                conn.execute("UPDATE devices SET mac_address = ? WHERE id = ?", (mac, device_id))
                conn.commit()
            else:
                logger.warning(f"No se pudo obtener MAC para {name}")
    logger.info("Proceso completado")

if __name__ == "__main__":
    main()
