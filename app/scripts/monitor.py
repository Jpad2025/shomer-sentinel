#!/usr/bin/env python3
"""
Script de monitoreo de dispositivos
Desarrollado por USB Ingeniería SAS y USB Engineers LLC
"""
import os
import re
import sys
import time
import logging
import socket
import sqlite3
import subprocess
import datetime
import json
import requests
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler

try:
    from alerts import send_telegram_alert, MSG_INICIO
except ImportError:
    send_telegram_alert = lambda msg: False
    MSG_INICIO = "🛡️ SHOMER: Sistema activo. Red del Hotel El Buen Descanso. Monitoreo de 30 routers iniciado."

# Logs: rotación 10MB, máximo 5 archivos de respaldo (evitar crecimiento indefinido)
LOG_MONITOR = "/opt/network_monitor/logs/monitoring/monitor.log"
os.makedirs(os.path.dirname(LOG_MONITOR), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(LOG_MONITOR, maxBytes=10 * 1024 * 1024, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("monitor")

# Conexión a la base de datos (timeout y WAL para evitar "database is locked")
DB_PATH = "/opt/network_monitor/database/network_monitor.db"
CONNECT_TIMEOUT = 30

# Intervalo de ping: 10 s entre ciclos (estabilidad del router con carga de clientes)
CYCLE_INTERVAL_SEC = 10
PAUSE_BETWEEN_DEVICES_SEC = 1
PING_TIMEOUT_SEC = 2
PORT_CHECK_TIMEOUT_SEC = 2
# Ruta absoluta de ping (el proceso puede ejecutarse con PATH mínimo, p. ej. como servicio)
PING_CMD = "/usr/bin/ping"
# Puertos de gestión por si el router bloquea ICMP (ping): 80 (HTTP), 22 (SSH), 443 (HTTPS)
PORT_CHECK_PORTS = [80, 22, 443]

# Huéspedes (LAN del GL): reintentos de ping y refresco SSH al router antes de comprobar
GUEST_PING_RETRIES = 3
GUEST_PING_INTERVAL_SEC = 1.0
GL_ROUTER_DEVICE_ID = 5
SSH_REFRESH_BROADCAST = "192.168.1.255"
SSHPASS_PATH = "/usr/bin/sshpass"
SSH_PATH = "/usr/bin/ssh"
SSH_TIMEOUT_SEC = 10

# Failsafe: reinicio si (locales .20 y .27 offline) O (DNS + ping externo fallan) > 5 min
FAILSAFE_OBJECTIVE_IPS = ["192.168.1.20", "192.168.1.27"]  # Laptop, MacBook
FAILSAFE_INTERNET_IP = "8.8.8.8"
FAILSAFE_DNS_HOST = "www.google.com"
FAILSAFE_BOTH_OFFLINE_SEC = 300  # 5 minutos
FAILSAFE_STATE_DIR = "/opt/network_monitor/state"
FAILSAFE_STATE_FILE = os.path.join(FAILSAFE_STATE_DIR, "failsafe_both_offline_since.txt")
FAILSAFE_DNS_PING_FILE = os.path.join(FAILSAFE_STATE_DIR, "failsafe_dns_ping_fail_since.txt")
REBOOT_SSH_TIMEOUT_SEC = 25
REBOOT_SSH_RETRIES = 3
REBOOT_SSH_RETRY_DELAY_SEC = 5
# Umbral de latencia: si ping > 400 ms, estado ADVERTENCIA (warning) en el panel
LATENCY_WARNING_MS = 400
GATEWAY_IP = "192.168.1.210"

@contextmanager
def _get_connection():
    """Abre conexión con timeout y modo WAL. Cierra al salir del 'with'."""
    conn = sqlite3.connect(DB_PATH, timeout=CONNECT_TIMEOUT)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def get_active_devices():
    """Solo dispositivos con is_active = 1 (p. ej. GL-AX6000 debe tener is_active = 1 para monitorearse)."""
    with _get_connection() as conn:
        return conn.execute("SELECT * FROM devices WHERE is_active = 1").fetchall()


def _get_router_for_ssh():
    """Obtiene credenciales del router GL (device_id = GL_ROUTER_DEVICE_ID) para refresco SSH."""
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT id, ip_address, ssh_user, ssh_password, ssh_port FROM devices WHERE id = ?",
            (GL_ROUTER_DEVICE_ID,),
        ).fetchone()
    if not row:
        return None
    port = row["ssh_port"] if row["ssh_port"] is not None else 22
    if not row["ip_address"] or not row["ssh_user"] or not row["ssh_password"]:
        return None
    return {
        "ip": row["ip_address"],
        "user": row["ssh_user"],
        "password": row["ssh_password"],
        "port": port,
    }


def refresh_gl_neighbors_ssh():
    """
    Conexión SSH rápida al GL para refrescar tabla de vecinos (ARP/ruta).
    Ejecuta un ping broadcast en el router para que actualice la caché antes de comprobar huéspedes.
    """
    router = _get_router_for_ssh()
    if not router:
        logger.warning("No se encontró router GL (id=%s) con credenciales SSH; se omite refresco de caché.", GL_ROUTER_DEVICE_ID)
        return False
    cmd = [
        SSHPASS_PATH, "-p", router["password"],
        SSH_PATH,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=5",
        "-o", "BatchMode=no",
        "-p", str(router["port"]),
        f"{router['user']}@{router['ip']}",
        f"ping -c 1 -W 2 {SSH_REFRESH_BROADCAST}",
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=SSH_TIMEOUT_SEC)
        logger.info("Refresco de tabla de vecinos en GL (SSH) ejecutado")
        return True
    except subprocess.TimeoutExpired:
        logger.warning("SSH al GL para refresco de vecinos: timeout")
        return False
    except FileNotFoundError:
        logger.warning("sshpass o ssh no encontrado; se omite refresco SSH al GL")
        return False
    except Exception as e:
        logger.warning("Error en refresco SSH al GL: %s", e)
        return False


def ping_device(ip, log_ping=False):
    """Ping simple: ping -c 1 -W 1 <ip>; True si código de salida 0. No loguea por defecto (evitar duplicados)."""
    ok, _ = ping_device_with_latency(ip)
    return ok


def ping_device_with_latency(ip):
    """Ping y devuelve (éxito, latencia_ms). Extrae el valor numérico en ms. None si falla."""
    try:
        result = subprocess.run(
            [PING_CMD, "-c", "1", "-W", "2", ip],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False, None
        output = result.stdout or ""
        # 1) time=12.3 ms o time=12.3 (línea de respuesta)
        for line in output.splitlines():
            if "time=" in line or "time =" in line:
                m = re.search(r"time[=\s]+([\d.]+)\s*ms?", line, re.I)
                if m:
                    return True, float(m.group(1))
        # 2) Fallback: rtt min/avg/max/mdev = 1.34/1.34/1.34/0.00 ms
        m = re.search(r"rtt\s+min/avg/max[^=]*=\s*([\d.]+)/", output, re.I)
        if m:
            return True, float(m.group(1))
        return True, None
    except Exception:
        return False, None


def check_port(ip, port, timeout_sec=PORT_CHECK_TIMEOUT_SEC):
    """Comprueba si un puerto TCP está abierto (p. ej. 80 o 22). Útil si el router bloquea ICMP."""
    try:
        with socket.create_connection((ip, port), timeout=timeout_sec):
            return True
    except (socket.timeout, socket.error, OSError):
        return False

def update_device_status(device_id, status, latency_ms=None):
    """Actualizar el estado en device_status (historial), devices.status y devices.latency_ms."""
    try:
        now = datetime.datetime.utcnow()
        with _get_connection() as conn:
            conn.execute(
                "INSERT INTO device_status (device_id, status, last_check) VALUES (?, ?, ?)",
                (device_id, status, now)
            )
            if latency_ms is not None:
                conn.execute(
                    "UPDATE devices SET status = ?, latency_ms = ? WHERE id = ?",
                    (status, int(round(latency_ms)), device_id)
                )
            else:
                conn.execute(
                    "UPDATE devices SET status = ?, latency_ms = NULL WHERE id = ?",
                    (status, device_id)
                )
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error al actualizar estado del dispositivo {device_id}: {str(e)}")
        return False

def log_event(device_id, event_type, description, severity="info"):
    """Registrar un evento en la base de datos"""
    try:
        with _get_connection() as conn:
            conn.execute(
                "INSERT INTO events_log (device_id, event_type, description, severity, created_at) VALUES (?, ?, ?, ?, ?)",
                (device_id, event_type, description, severity, datetime.datetime.utcnow())
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error al registrar evento para dispositivo {device_id}: {str(e)}")
        return False


def _failsafe_read_both_offline_since():
    """Lee la marca de tiempo desde la que ambos objetivos están offline (o None)."""
    try:
        if os.path.isfile(FAILSAFE_STATE_FILE):
            with open(FAILSAFE_STATE_FILE, "r") as f:
                s = f.read().strip()
            if s:
                return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return None


def _failsafe_write_both_offline_since(ts):
    """Escribe la marca de tiempo (ambos objetivos offline desde ts)."""
    try:
        os.makedirs(FAILSAFE_STATE_DIR, exist_ok=True)
        with open(FAILSAFE_STATE_FILE, "w") as f:
            f.write(ts.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception as e:
        logger.warning("No se pudo escribir estado failsafe: %s", e)


def _failsafe_clear_state():
    """Borra el estado failsafe (condición de reinicio dejó de cumplirse)."""
    for path in (FAILSAFE_STATE_FILE, FAILSAFE_DNS_PING_FILE):
        try:
            if os.path.isfile(path):
                os.remove(path)
        except Exception:
            pass


def _check_dns() -> bool:
    """Resuelve FAILSAFE_DNS_HOST (www.google.com). True si hay resolución."""
    try:
        socket.getaddrinfo(FAILSAFE_DNS_HOST, None, socket.AF_INET)
        return True
    except (socket.gaierror, socket.error, OSError):
        return False


def _log_dns_fail_if_ping_ok(internet_ok, dns_ok):
    """Si el ping a 8.8.8.8 fue OK pero la resolución DNS falla, registra una línea en el log."""
    if internet_ok and not dns_ok:
        logger.warning("[SHOMER] Fallo de resolución DNS detectado")


def _device_id_by_ip(ip):
    """Devuelve device_id para la IP dada, o None si no existe."""
    with _get_connection() as conn:
        row = conn.execute("SELECT id FROM devices WHERE ip_address = ? AND is_active = 1", (ip,)).fetchone()
    return row["id"] if row else None


def _run_router_reboot_ssh():
    """
    Reinicio del router vía SSH. Reintenta hasta REBOOT_SSH_RETRIES veces antes de marcar error crítico.
    """
    router = _get_router_for_ssh()
    if not router:
        logger.error("Failsafe: no hay credenciales del router para reinicio SSH")
        return False
    cmd = [
        SSHPASS_PATH, "-p", router["password"],
        SSH_PATH,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=8",
        "-p", str(router["port"]),
        f"{router['user']}@{router['ip']}",
        "/sbin/reboot",
    ]
    last_error = None
    for attempt in range(1, REBOOT_SSH_RETRIES + 1):
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=REBOOT_SSH_TIMEOUT_SEC)
            logger.warning("Failsafe: comando de reinicio SSH enviado al router (intento %d/%d)", attempt, REBOOT_SSH_RETRIES)
            log_event(GL_ROUTER_DEVICE_ID, "failsafe_reboot", "Reinicio automático: Internet + locales offline > 5 min", "warning")
            return True
        except subprocess.TimeoutExpired:
            logger.warning("Failsafe: timeout SSH reinicio, intento %d/%d (el router puede estar reiniciando)", attempt, REBOOT_SSH_RETRIES)
            log_event(GL_ROUTER_DEVICE_ID, "failsafe_reboot", "Reinicio SSH enviado (timeout esperado)", "info")
            return True
        except FileNotFoundError:
            logger.error("Failsafe: sshpass o ssh no encontrado")
            return False
        except Exception as e:
            last_error = e
            logger.warning("Failsafe: error en reinicio SSH intento %d/%d: %s", attempt, REBOOT_SSH_RETRIES, e)
            if attempt < REBOOT_SSH_RETRIES:
                time.sleep(REBOOT_SSH_RETRY_DELAY_SEC)
    logger.error("Failsafe: reinicio SSH falló tras %d intentos: %s", REBOOT_SSH_RETRIES, last_error)
    log_event(GL_ROUTER_DEVICE_ID, "failsafe_reboot_failed", f"Falló tras {REBOOT_SSH_RETRIES} intentos: {last_error}", "error")
    return False


def _check_internet():
    """Test de Internet: ping a 8.8.8.8. Devuelve (éxito, latencia_ms). Actualiza dispositivo 8.8.8.8 si existe."""
    ok, latency_ms = ping_device_with_latency(FAILSAFE_INTERNET_IP)
    device_id = _device_id_by_ip(FAILSAFE_INTERNET_IP)
    if device_id is not None:
        if ok:
            status = "warning" if (latency_ms is not None and latency_ms > LATENCY_WARNING_MS) else "online"
            update_device_status(device_id, status, latency_ms)
            if status == "warning" and latency_ms is not None:
                logger.warning("[SHOMER] Latencia alta: Internet %.0f ms", latency_ms)
                send_telegram_alert(
                    f"⚠️ <b>SHOMER: Latencia alta</b> (red Hotel El Buen Descanso)\n"
                    f"Internet (8.8.8.8): {latency_ms:.0f} ms"
                )
        else:
            update_device_status(device_id, "offline", None)
    return ok


def _failsafe_read_dns_ping_since():
    """Lee la marca de tiempo desde la que DNS y ping externo fallan (o None)."""
    try:
        if os.path.isfile(FAILSAFE_DNS_PING_FILE):
            with open(FAILSAFE_DNS_PING_FILE, "r") as f:
                s = f.read().strip()
            if s:
                return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return None


def _failsafe_write_dns_ping_since(ts):
    try:
        os.makedirs(FAILSAFE_STATE_DIR, exist_ok=True)
        with open(FAILSAFE_DNS_PING_FILE, "w") as f:
            f.write(ts.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception:
        pass


def _failsafe_check_and_act():
    """
    Reinicio automático si (Laptop .20 Y MacBook .27 offline > 5 min) O (DNS Y ping 8.8.8.8 fallan > 5 min).
    Test DNS: si ping 8.8.8.8 OK pero resolución DNS falla, se registra en log una vez por ciclo.
    """
    try:
        internet_ok = _check_internet()
        dns_ok = _check_dns()
        _log_dns_fail_if_ping_ok(internet_ok, dns_ok)
        with _get_connection() as conn:
            cur = conn.execute(
                "SELECT ip_address, status FROM devices WHERE ip_address IN (?, ?)",
                (FAILSAFE_OBJECTIVE_IPS[0], FAILSAFE_OBJECTIVE_IPS[1]),
            )
            rows = {r["ip_address"]: r["status"] for r in cur.fetchall()}
        status_20 = (rows.get(FAILSAFE_OBJECTIVE_IPS[0]) or "").lower()
        status_27 = (rows.get(FAILSAFE_OBJECTIVE_IPS[1]) or "").lower()
        both_locals_offline = status_20 == "offline" and status_27 == "offline"
        dns_and_ping_fail = (not dns_ok) and (not internet_ok)
        now = datetime.datetime.utcnow()

        if both_locals_offline:
            since = _failsafe_read_both_offline_since()
            if since is None:
                _failsafe_write_both_offline_since(now)
                logger.info("Failsafe: objetivos locales (.20 y .27) caídos; ventana 5 min")
            else:
                elapsed = (now - since).total_seconds()
                if elapsed >= FAILSAFE_BOTH_OFFLINE_SEC:
                    logger.warning("Failsafe: locales caídos > 5 min; reinicio Gateway (.210)")
                    send_telegram_alert(
                        "🚨 <b>SHOMER: Failsafe activado</b> (red Hotel El Buen Descanso)\n"
                        "Laptop (.20) y MacBook (.27) offline > 5 min.\n"
                        "Reiniciando Gateway..."
                    )
                    _run_router_reboot_ssh()
                    _failsafe_clear_state()
        else:
            try:
                if os.path.isfile(FAILSAFE_STATE_FILE):
                    os.remove(FAILSAFE_STATE_FILE)
            except Exception:
                pass

        if dns_and_ping_fail:
            since = _failsafe_read_dns_ping_since()
            if since is None:
                _failsafe_write_dns_ping_since(now)
                logger.info("[SHOMER] DNS y ping externo caídos; ventana 5 min")
            else:
                elapsed = (now - since).total_seconds()
                if elapsed >= FAILSAFE_BOTH_OFFLINE_SEC:
                    logger.warning("Failsafe: DNS + ping externo caídos > 5 min; reinicio Gateway (.210)")
                    send_telegram_alert(
                        "🚨 <b>SHOMER: Failsafe activado</b> (red Hotel El Buen Descanso)\n"
                        "DNS y ping externo caídos > 5 min.\n"
                        "Reiniciando Gateway..."
                    )
                    _run_router_reboot_ssh()
                    _failsafe_clear_state()
        else:
            try:
                if os.path.isfile(FAILSAFE_DNS_PING_FILE):
                    os.remove(FAILSAFE_DNS_PING_FILE)
            except Exception:
                pass
    except Exception as e:
        logger.warning("Failsafe: %s", e)
        _failsafe_clear_state()

def _is_guest(device):
    """True si el dispositivo está marcado como huésped (LAN del GL)."""
    try:
        return bool(device.get("is_guest"))
    except (TypeError, AttributeError):
        return False


def check_device(device):
    """
    Ping como verdad única; actualiza BD. Gateway (.210) e Internet (8.8.8.8): si latencia > 400 ms -> warning.
    Un solo log por dispositivo por ciclo (evitar duplicados).
    """
    try:
        device_id = device['id']
        name = device['name']
        ip = device['ip_address']
    except (KeyError, TypeError):
        logger.warning("Dispositivo sin id/name/ip_address, se omite")
        return False

    is_guest_device = _is_guest(device)
    is_gateway = ip == GATEWAY_IP
    is_online = False
    latency_ms = None
    try:
        if is_guest_device:
            for attempt in range(1, GUEST_PING_RETRIES + 1):
                ok, lat = ping_device_with_latency(ip)
                if ok:
                    is_online = True
                    latency_ms = lat  # Captura latencia del ping (ms)
                    break
                if attempt < GUEST_PING_RETRIES:
                    time.sleep(GUEST_PING_INTERVAL_SEC)
        else:
            ok, latency_ms = ping_device_with_latency(ip)  # Extrae valor numérico del ping (ms)
            is_online = ok
        if not is_online:
            for port in PORT_CHECK_PORTS:
                try:
                    if check_port(ip, port):
                        is_online = True
                        break
                except Exception:
                    pass
    except Exception as e:
        logger.warning("Verificación %s (%s) falló: %s", name, ip, e)

    # Lógica de advertencia: si latency_ms > 400ms, estado 'warning' aunque responda al ping
    if is_online and latency_ms is not None and latency_ms > LATENCY_WARNING_MS:
        status = "warning"
        if is_gateway:
            logger.warning("[SHOMER] Latencia alta: Gateway %.0f ms", latency_ms)
            send_telegram_alert(
                f"⚠️ <b>SHOMER: Latencia alta</b> (red Hotel El Buen Descanso)\n"
                f"Gateway ({ip}): {latency_ms:.0f} ms"
            )
        else:
            logger.warning("[SHOMER] Latencia alta: %s %.0f ms", name, latency_ms)
            send_telegram_alert(
                f"⚠️ <b>SHOMER: Latencia alta</b> (red Hotel El Buen Descanso)\n"
                f"{name} ({ip}): {latency_ms:.0f} ms"
            )
    else:
        status = "online" if is_online else "offline"
    try:
        update_device_status(device_id, status, latency_ms)
    except Exception as e:
        logger.error("Error actualizando estado de %s: %s", name, e)

    logger.info("%s (%s): %s", name, ip, status)
    if not is_online:
        try:
            log_event(device_id, "status_change", f"Dispositivo {name} está offline", "warning")
        except Exception:
            pass
    return is_online

def main():
    """Función principal"""
    logger.info("Iniciando sistema de monitoreo...")
    send_telegram_alert(MSG_INICIO)
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS device_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                last_check TIMESTAMP NOT NULL,
                FOREIGN KEY (device_id) REFERENCES devices (id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER,
                event_type TEXT NOT NULL,
                description TEXT NOT NULL,
                severity TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                FOREIGN KEY (device_id) REFERENCES devices (id)
            )
        """)
        conn.commit()
    try:
        while True:
            devices = get_active_devices()
            logger.info("Ciclo: %d dispositivos", len(devices))
            if devices and any(_is_guest(d) for d in devices):
                refresh_gl_neighbors_ssh()
            for device in devices:
                try:
                    check_device(device)
                except Exception as e:
                    logger.warning("check_device falló para %s: %s", device.get("id") or device.get("ip_address"), e)
                time.sleep(PAUSE_BETWEEN_DEVICES_SEC)

            try:
                _failsafe_check_and_act()
            except Exception as e:
                logger.warning("Failsafe: %s", e)

            logger.info("Ciclo listo; próximo en %d s", CYCLE_INTERVAL_SEC)
            time.sleep(CYCLE_INTERVAL_SEC)
    except KeyboardInterrupt:
        logger.info("Sistema de monitoreo detenido por el usuario")
    except Exception as e:
        logger.error(f"Error en el sistema de monitoreo: {str(e)}")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
