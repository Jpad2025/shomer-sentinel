# SCRIPT DE DISCOVERY AUTOMATIZADO DE RED
# Inventario pasivo: lee la tabla ARP del router vía SSH (sin pings masivos).
# Barrido ICMP en la subred detectada dinámicamente para encontrar hosts activos.
# Ubicación: /opt/network_monitor/app/backend/scripts/discovery.py

import os
import sys
import subprocess
import json
import sqlite3
import re
import ipaddress
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Set
import logging
from logging.handlers import RotatingFileHandler

# Configuración: BD desde app.backend.db (/storage/db/)
_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.abspath(os.path.join(_PARENT, ".."))
for _p in (_ROOT, _PARENT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from app.backend.db import connect, CONNECT_TIMEOUT

SSHPASS_PATH = "/usr/bin/sshpass"
SSH_PATH = "/usr/bin/ssh"
SSH_TIMEOUT_SEC = 15
# Broadcast y red: calculados dinámicamente desde get_network_context() al momento del scan
ARP_REFRESH_BROADCAST = None
PING_SWEEP_TIMEOUT = 1
MAX_SCAN_WORKERS = 10
PING_SWEEP_WORKERS = MAX_SCAN_WORKERS

# Auto-promote: URL de la API para promover hosts encontrados por ICMP al panel
API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
PROMOTE_ENDPOINT = f"{API_BASE_URL.rstrip('/')}/api/discovery/promote"
# Nombres por defecto: vacío — no hardcodear IPs de clientes
DEFAULT_NAMES: Dict[str, str] = {}

# Logs: rotación 10MB, máximo 5 archivos de respaldo
LOG_DISCOVERY = "/var/log/shomer/discovery.log"
os.makedirs(os.path.dirname(LOG_DISCOVERY), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(LOG_DISCOVERY, maxBytes=10 * 1024 * 1024, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@contextmanager
def get_conn():
    """Conexión SQLite con timeout y WAL (network_monitor.db en /storage)."""
    conn = connect(timeout=CONNECT_TIMEOUT)
    try:
        yield conn
    finally:
        conn.close()


def get_credentials_from_db() -> Optional[Tuple[str, str, str]]:
    """Obtiene (ip_address, ssh_user, ssh_password) del router activo para ARP vía SSH.
    Usa el primer dispositivo activo con SSH configurado — sin ID hardcodeado."""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT ip_address, ssh_user, ssh_password FROM devices "
                "WHERE is_active = 1 AND ssh_user IS NOT NULL AND ssh_password IS NOT NULL "
                "ORDER BY id LIMIT 1"
            )
            row = cur.fetchone()
            if not row or not row["ip_address"]:
                return None
            return (row["ip_address"], row["ssh_user"], row["ssh_password"])
    except Exception as e:
        logger.error("Error leyendo credenciales del router: %s", e)
        return None


def _get_subnet() -> Optional[str]:
    """Detecta la subred de la NIC de gestión.
    Prefiere interfaces cableadas (en*, eth*, eno*) sobre WiFi (wl*, wlan*).
    Fallback a get_network_context() si no hay wired, o None si falla todo."""
    try:
        # Intentar detectar NIC wired primero (NIC de gestión)
        result = subprocess.run(
            ["ip", "-o", "-f", "inet", "addr", "show"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            iface = parts[1]
            addr = parts[3]  # e.g. 192.168.1.205/24
            # Preferir interfaces cableadas, excluir loopback y WiFi
            if iface == "lo" or iface.startswith(("wl", "wlan")):
                continue
            if iface.startswith(("en", "eth", "eno", "ens", "enp")):
                try:
                    net = ipaddress.IPv4Network(addr, strict=False)
                    logger.debug("Subred detectada desde %s: %s", iface, net)
                    return str(net)
                except Exception:
                    continue
    except Exception as e:
        logger.warning("Error detectando NIC wired: %s", e)

    # Fallback a get_network_context()
    try:
        from app.scripts.network_context import get_network_context
        ctx = get_network_context()
        subnet = ctx.get("subnet")
        if subnet:
            logger.debug("Subred desde get_network_context(): %s", subnet)
            return subnet
    except Exception as e:
        logger.warning("No se pudo detectar subred automáticamente: %s", e)
    return None


def run_ssh_command(host: str, user: str, password: str, command: str, timeout: int = SSH_TIMEOUT_SEC) -> bool:
    """Ejecuta un comando en el router vía SSH. Devuelve True si salida 0."""
    cmd = [
        SSHPASS_PATH, "-p", password, SSH_PATH,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "PreferredAuthentications=password",
        f"{user}@{host}",
        command,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode == 0
    except Exception as e:
        logger.debug("SSH command failed: %s", e)
        return False


def run_local_ping_sweep(subnet: Optional[str] = None) -> None:
    """
    Barrido rápido de pings desde el Mini PC a la subred local.
    Pobla la tabla ARP del Mini PC y del router (tráfico pasa por el gateway).
    Usa fping si está disponible, si no un loop de pings en paralelo.
    La subred se detecta dinámicamente si no se proporciona.
    """
    if not subnet:
        subnet = _get_subnet()
    if not subnet:
        logger.warning("Barrido ARP: no se pudo determinar la subred — omitiendo ping sweep")
        return
    try:
        network = ipaddress.IPv4Network(subnet, strict=False)
        hosts = [str(h) for h in network.hosts()]
        net_str = str(network)
    except Exception as e:
        logger.warning("Subred inválida '%s': %s — omitiendo ping sweep", subnet, e)
        return

    try:
        proc = subprocess.run(
            ["which", "fping"], capture_output=True, text=True, timeout=2
        )
        if proc.returncode == 0 and proc.stdout.strip():
            cmd = ["fping", "-r", "1", "-t", str(PING_SWEEP_TIMEOUT * 1000), "-g", net_str]
            subprocess.run(cmd, capture_output=True, timeout=15)
            logger.info("Barrido ARP: fping %s ejecutado", net_str)
            return
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: pings en paralelo
    def ping_one(ip: str) -> bool:
        try:
            r = subprocess.run(
                ["ping", "-c", "1", "-W", str(PING_SWEEP_TIMEOUT), ip],
                capture_output=True, text=True, timeout=PING_SWEEP_TIMEOUT + 1,
            )
            return r.returncode == 0
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=PING_SWEEP_WORKERS) as ex:
        list(ex.map(ping_one, hosts))
    logger.info("Barrido ARP: %d pings ejecutados en %s", len(hosts), net_str)


def run_icmp_sweep_returns_live_ips(subnet: Optional[str] = None) -> List[str]:
    """
    Barrido ICMP (ping) en la subred local desde el Mini PC.
    La subred se detecta dinámicamente si no se proporciona.
    Devuelve la lista de IPs que respondieron.
    """
    if not subnet:
        subnet = _get_subnet()
    if not subnet:
        logger.warning("Barrido ICMP: no se pudo determinar la subred — omitiendo")
        return []
    try:
        network = ipaddress.IPv4Network(subnet, strict=False)
        hosts = [str(h) for h in network.hosts()]
        net_str = str(network)
    except Exception as e:
        logger.warning("Subred inválida '%s': %s — omitiendo barrido ICMP", subnet, e)
        return []

    def ping_one(ip: str) -> Optional[str]:
        try:
            r = subprocess.run(
                ["ping", "-c", "1", "-W", str(PING_SWEEP_TIMEOUT), ip],
                capture_output=True,
                text=True,
                timeout=PING_SWEEP_TIMEOUT + 1,
            )
            return ip if r.returncode == 0 else None
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=PING_SWEEP_WORKERS) as ex:
        results = list(ex.map(ping_one, hosts))
    live = [ip for ip in results if ip]
    logger.info("Barrido ICMP %s: %d hosts respondieron", net_str, len(live))
    return live


def run_router_ping_sweep(host: str, user: str, password: str, broadcast: Optional[str] = None) -> None:
    """
    Ejecuta ping broadcast desde el router (vía SSH) para refrescar su tabla ARP.
    El broadcast se calcula dinámicamente desde get_network_context().
    """
    if not broadcast:
        try:
            subnet = _get_subnet()
            if subnet:
                broadcast = str(ipaddress.IPv4Network(subnet, strict=False).broadcast_address)
        except Exception:
            pass
    if not broadcast:
        logger.warning("Refresco ARP: no se pudo determinar broadcast — omitiendo pings desde router")
        return
    cmd = f"ping -c 1 -W 2 {broadcast}"
    if run_ssh_command(host, user, password, cmd, timeout=8):
        logger.debug("Router ping a %s OK", broadcast)
    logger.info("Refresco ARP: ping broadcast desde el router ejecutado")


def get_devices_ip_set() -> Set[str]:
    """Devuelve el conjunto de IPs ya presentes en la tabla devices."""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT ip_address FROM devices WHERE ip_address IS NOT NULL AND ip_address != ''")
            return {r["ip_address"] for r in cur.fetchall()}
    except Exception as e:
        logger.warning("Error leyendo devices: %s", e)
        return set()


def promote_ip_to_panel(ip: str, name: str) -> bool:
    """Llama al endpoint POST /api/discovery/promote para que el host aparezca en el panel."""
    payload = json.dumps({
        "ip_address": ip,
        "name": name,
        "device_type": "workstation",
        "location": "",
        "brand": "",
        "model": "",
    }).encode("utf-8")
    req = urllib.request.Request(
        PROMOTE_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 201):
                body = resp.read().decode("utf-8", errors="replace")
                data = json.loads(body) if body else {}
                logger.info("Promovido al panel: %s (%s) -> device_id=%s", ip, name, data.get("device_id"))
                return True
            return False
    except urllib.error.HTTPError as e:
        try:
            msg = e.read().decode("utf-8", errors="replace")
            if "Ya existía" in msg or "already" in msg.lower():
                logger.debug("Ya en panel: %s", ip)
                return True
        except Exception:
            pass
        logger.debug("Promote HTTP %s para %s: %s", e.code, ip, e.reason)
        return False
    except Exception as e:
        logger.warning("Error al promover %s al panel: %s", ip, e)
        return False


def auto_promote_live_ips(live_ips: List[str]) -> int:
    """
    Para cada IP en live_ips que no está en devices, llama al endpoint de promote
    para que aparezca en el panel. Nombres: DEFAULT_NAMES o "Host-XX" (último octeto).
    """
    existing = get_devices_ip_set()
    promoted = 0
    for ip in live_ips:
        if ip in existing:
            continue
        name = DEFAULT_NAMES.get(ip)
        if not name:
            try:
                last = ip.split(".")[-1]
                name = f"Host-{last}"
            except Exception:
                name = f"Host-{ip.replace('.', '-')}"
        if promote_ip_to_panel(ip, name):
            promoted += 1
    return promoted


def refresh_arp_via_ssh(host: str, user: str, password: str) -> None:
    """Antes de leer ARP: ping broadcast en el router para despertar vecinos y refrescar la tabla.
    El broadcast se calcula dinámicamente desde get_network_context()."""
    broadcast = None
    try:
        subnet = _get_subnet()
        if subnet:
            broadcast = str(ipaddress.IPv4Network(subnet, strict=False).broadcast_address)
    except Exception:
        pass
    if not broadcast:
        logger.warning("Refresco ARP: no se pudo calcular broadcast — omitiendo ping broadcast")
        return
    cmd = f"ping -c 1 -W 2 {broadcast}"
    if run_ssh_command(host, user, password, cmd, timeout=10):
        logger.info("Refresco ARP: broadcast %s ejecutado en el router", broadcast)
    else:
        logger.warning("Refresco ARP: ping broadcast falló (seguimos con la tabla actual)")


def get_arp_via_ssh(host: str, user: str, password: str) -> List[Dict[str, str]]:
    """
    Lee la tabla ARP del router vía SSH (sin pings). Compatible con OpenWrt/GL-iNet.
    Antes ejecuta ping broadcast para refrescar ARP. Luego: cat /proc/net/arp.
    Returns: lista de {"ip": "x.x.x.x", "mac": "XX:XX:XX:XX:XX:XX"}
    """
    entries = []
    # /proc/net/arp: IP at column 0, HW address at column 3; skip header and 0.0.0.0
    cmd = [
        SSHPASS_PATH, "-p", password, SSH_PATH,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "PreferredAuthentications=password",
        f"{user}@{host}",
        "cat /proc/net/arp",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=SSH_TIMEOUT_SEC,
        )
        if proc.returncode != 0:
            logger.warning("ARP vía SSH falló (code %s): %s", proc.returncode, (proc.stderr or "").strip())
            return entries
        for line in proc.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            ip_addr = parts[0]
            if ip_addr == "IP" or ip_addr == "0.0.0.0":
                continue
            hw = parts[3]
            if hw == "00:00:00:00:00:00" or "*" in hw:
                continue
            mac = hw.upper().replace("-", ":")
            if re.match(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$", mac):
                entries.append({"ip": ip_addr, "mac": mac})
    except subprocess.TimeoutExpired:
        logger.error("Timeout leyendo ARP vía SSH")
    except FileNotFoundError:
        logger.error("sshpass/ssh no encontrado (ruta: %s)", SSHPASS_PATH)
    except Exception as e:
        logger.exception("Error leyendo ARP vía SSH: %s", e)
    return entries


def _ensure_mac_unique_index(conn):
    """Índice UNIQUE en mac_address para ON CONFLICT(mac_address)."""
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_discovered_devices_mac ON discovered_devices(mac_address)")
        conn.commit()
    except Exception as e:
        logger.warning("Índice mac_address (puede haber MACs duplicadas): %s", e)


def save_discovered_device(device_info: Dict) -> bool:
    """
    Guardar dispositivo descubierto. Validación: ip_address y mac_address no vacíos.
    hostname/vendor: '' o 'Unknown' si vienen vacíos. Upsert por mac_address.
    """
    ip_addr = (device_info.get("ip_address") or "").strip()
    mac = (device_info.get("mac_address") or "").strip()
    if not ip_addr or not mac:
        logger.debug("Registro descartado: ip_address o mac_address vacíos (ip=%r, mac=%r)", ip_addr or None, mac or None)
        return False

    hostname = (device_info.get("hostname") or "").strip() or "Unknown"
    vendor = (device_info.get("vendor") or "").strip() or "Unknown"
    last_seen = (device_info.get("last_seen") or "").strip() or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
    status = (device_info.get("status") or "").strip() or "online"

    try:
        with get_conn() as conn:
            _ensure_mac_unique_index(conn)
            cur = conn.cursor()
            try:
                cur.execute("""
                    INSERT INTO discovered_devices (ip_address, mac_address, hostname, vendor, last_seen, status, first_seen, source, open_ports, inferred_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'arp_ssh', '[]', 'unknown')
                    ON CONFLICT(mac_address) DO UPDATE SET
                        ip_address = excluded.ip_address,
                        last_seen = excluded.last_seen,
                        status = excluded.status
                """, (ip_addr, mac, hostname, vendor, last_seen, status, last_seen))
            except (sqlite3.IntegrityError, sqlite3.OperationalError):
                cur.execute("SELECT id FROM discovered_devices WHERE mac_address = ?", (mac,))
                row = cur.fetchone()
                if row:
                    cur.execute(
                        "UPDATE discovered_devices SET ip_address = ?, last_seen = ?, status = ? WHERE mac_address = ?",
                        (ip_addr, last_seen, status, mac),
                    )
                else:
                    cur.execute("""
                        INSERT INTO discovered_devices (ip_address, mac_address, hostname, vendor, last_seen, status, first_seen, source, open_ports, inferred_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'arp_ssh', '[]', 'unknown')
                    """, (ip_addr, mac, hostname, vendor, last_seen, status, last_seen))
            conn.commit()
        logger.info("Dispositivo descubierto: %s / %s", ip_addr, mac)
        return True
    except Exception as e:
        logger.error("Error en BD: %s", e)
        return False


def cleanup_old_discoveries():
    """Marcar dispositivos offline que no se han visto en X tiempo"""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cutoff = (datetime.utcnow() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S.%f")
            cur.execute(
                "UPDATE discovered_devices SET status = 'offline' WHERE last_seen < ? AND status = 'online'",
                (cutoff,)
            )
            if cur.rowcount > 0:
                logger.info(f"Marcados {cur.rowcount} dispositivos como offline")
            conn.commit()
    except Exception as e:
        logger.error(f"Error limpiando discoveries viejos: {str(e)}")


def ensure_assets_table(conn):
    """Crear tabla assets si no existe (inventario permanente)."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_address TEXT NOT NULL UNIQUE,
            ip_address TEXT,
            hostname TEXT,
            vendor TEXT,
            first_seen TEXT,
            last_seen TEXT,
            source TEXT
        )
    """)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_last_seen ON assets(last_seen)")
    except Exception:
        pass
    conn.commit()


def sync_arp_to_assets(arp_entries: List[Dict[str, str]], now: str) -> None:
    """Tras el discovery pasivo: guardar en assets para inventario permanente (huéspedes)."""
    valid = [e for e in (arp_entries or []) if (e.get("ip") or "").strip() and (e.get("mac") or "").strip()]
    if not valid:
        return
    try:
        with get_conn() as conn:
            ensure_assets_table(conn)
            cur = conn.cursor()
            for e in valid:
                mac, ip_addr = (e["mac"] or "").strip(), (e["ip"] or "").strip()
                if not mac or not ip_addr:
                    continue
                cur.execute("SELECT id FROM assets WHERE mac_address = ?", (mac,))
                if cur.fetchone():
                    cur.execute(
                        "UPDATE assets SET ip_address = ?, last_seen = ? WHERE mac_address = ?",
                        (ip_addr, now, mac),
                    )
                else:
                    cur.execute(
                        "INSERT INTO assets (mac_address, ip_address, hostname, vendor, first_seen, last_seen, source) VALUES (?, ?, NULL, NULL, ?, ?, 'arp_ssh')",
                        (mac, ip_addr, now, now),
                    )
            conn.commit()
        logger.info("Sincronizados %d activos a tabla assets", len(valid))
    except Exception as e:
        logger.warning("Error sincronizando a assets: %s", e)


def get_local_arp_entries() -> List[Dict[str, str]]:
    """
    Lee /proc/net/arp del propio servidor. Solo entradas con MAC válida (flags=0x2).
    Captura hosts que no pasan por el router GL (mismo segmento L2).
    """
    entries = []
    try:
        with open("/proc/net/arp", "r") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 4 or parts[0] == "IP":
                    continue
                ip_addr = parts[0]
                flags = parts[2]
                mac = parts[3].upper().replace("-", ":")
                if flags != "0x2":
                    continue
                if mac == "00:00:00:00:00:00" or "*" in mac:
                    continue
                if not re.match(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$", mac):
                    continue
                entries.append({"ip": ip_addr, "mac": mac})
    except Exception as e:
        logger.warning("Error leyendo ARP local: %s", e)
    logger.info("ARP local del servidor: %d entradas válidas", len(entries))
    return entries


def run_discovery(subnet: Optional[str] = None):
    """
    Inventario pasivo: lee ARP del router vía SSH + ARP local del servidor.
    Combina ambas fuentes para encontrar todos los hosts del segmento.
    La subred se detecta dinámicamente si no se proporciona.
    """
    logger.info("=" * 60)
    logger.info("Iniciando inventario pasivo (ARP router + ARP local)")
    logger.info("=" * 60)

    creds = get_credentials_from_db()
    run_local_ping_sweep(subnet=subnet)

    arp_router = []
    if not creds:
        logger.warning("No se encontraron credenciales SSH de router activo — usando solo ARP local.")
    else:
        host, user, password = creds
        refresh_arp_via_ssh(host, user, password)
        run_router_ping_sweep(host, user, password)
        arp_router = get_arp_via_ssh(host, user, password)
        logger.info("Entradas ARP leídas del router: %d", len(arp_router))

    # Combinar ARP router + ARP local (deduplicar por MAC)
    arp_local = get_local_arp_entries()
    seen_macs: Set[str] = set()
    arp_entries: List[Dict[str, str]] = []
    for e in arp_router + arp_local:
        mac = (e.get("mac") or "").strip()
        if mac and mac not in seen_macs:
            seen_macs.add(mac)
            arp_entries.append(e)
    logger.info("Total entradas ARP combinadas (router+local, sin duplicados): %d", len(arp_entries))

    # Barrido ICMP en la subred para detectar hosts activos (solo para poblar ARP local)
    run_icmp_sweep_returns_live_ips(subnet=subnet)

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")
    discovered_count = 0
    for e in arp_entries:
        ip_addr = (e.get("ip") or "").strip()
        mac = (e.get("mac") or "").strip()
        if not ip_addr or not mac:
            logger.debug("Entrada ARP descartada: ip o mac vacíos")
            continue
        device_info = {
            "ip_address": ip_addr,
            "mac_address": mac,
            "hostname": (e.get("hostname") or "").strip() or "",
            "vendor": (e.get("vendor") or "").strip() or "",
            "last_seen": now,
            "status": "online",
        }
        if save_discovered_device(device_info):
            discovered_count += 1

    cleanup_old_discoveries()
    sync_arp_to_assets(arp_entries, now)

    logger.info("=" * 60)
    logger.info("Inventario pasivo completado. Dispositivos actualizados: %d", discovered_count)
    logger.info("=" * 60)
    return discovered_count


def main():
    """Función principal"""
    try:
        run_discovery()
    except Exception as e:
        logger.error(f"Error fatal en discovery: {str(e)}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
