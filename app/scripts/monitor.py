#!/usr/bin/env python3
"""
SHOMER Monitor Pro v2.0 - Sistema de monitoreo industrial concurrente
Desarrollado por USB Ingeniería SAS y USB Engineers LLC
Características: SSH RSA, Redis, Threading, Failsafe 120s inmune
"""
import json
import os
import re
import sys
import time
import requests
import logging
import socket
import sqlite3
import subprocess
import datetime
import threading
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("redis no disponible; continuando sin Redis")

try:
    from alerts import send_telegram_alert
except ImportError:
    send_telegram_alert = lambda msg: False
MSG_INICIO = "🔄 <b>SISTEMA REINICIADO</b> | SHOMER Sentinel v2.0 activo y operativo."

LOG_MONITOR = "/var/log/shomer/monitoring/monitor.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3
os.makedirs(os.path.dirname(LOG_MONITOR), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(LOG_MONITOR, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("monitor")
if os.environ.get("SHOMER_LOG_DEBUG", "").lower() in ("1", "true", "yes"):
    logger.setLevel(logging.DEBUG)

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from app.backend import db as _db
DB_PATH = _db.DB_PATH
CONNECT_TIMEOUT = _db.CONNECT_TIMEOUT
NETWORK_TIMEOUT_SEC = 3
CYCLE_INTERVAL_SEC = 10
PING_CMD = "/usr/bin/ping"
PORT_CHECK_PORTS = [80, 22, 443]
GUEST_PING_RETRIES = 3
GUEST_PING_INTERVAL_SEC = 1.0

SSH_KEY_PATH = os.path.expanduser("~/.ssh/id_rsa_shomer")
SSH_BIN = "/usr/bin/ssh"
SSH_REBOOT_CONNECT_TIMEOUT = 5
SSH_TIMEOUT_SEC = 5

REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_TTL_SEC = 60

CONFIG_DIR = "/opt/network_monitor/config"
NODOS_GL_PATH = os.path.join(CONFIG_DIR, "nodos_gl.json")

try:
    from network_context import get_network_context
except ImportError:
    def get_network_context():
        return {"subnet": None, "interface": None, "gateway": None, "base_ip": None}


def _get_monitor_ips() -> tuple[list[str], str]:
    """IPs a monitorear: exclusivamente desde nodos_gl.json. Sin fallback automático."""
    ctx = get_network_context()
    gateway = ctx.get("gateway") or ""
    try:
        if os.path.isfile(NODOS_GL_PATH):
            with open(NODOS_GL_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                ips = []
                for n in data:
                    if not isinstance(n, dict):
                        continue
                    ip = (n.get("ip") or "").strip()
                    if not ip:
                        continue
                    activo = n.get("activo", True)
                    if activo in (False, "0", 0, "false", "False", "no"):
                        continue
                    ips.append(ip)
                if ips:
                    return (ips, gateway)
    except (json.JSONDecodeError, OSError):
        pass
    # Sin nodos configurados: monitorear solo el servidor local (IP dinámica)
    import socket as _socket
    try:
        local_ip = _socket.gethostbyname(_socket.gethostname())
    except Exception:
        local_ip = "127.0.0.1"
    logger.warning("nodos_gl.json vacío — monitoreando solo servidor local (%s)", local_ip)
    return ([local_ip], gateway)


MAX_WORKERS = 25

WAN_CHECK_IPS = ["8.8.8.8", "1.1.1.1", "208.67.222.222"]
WAN_MIN_SOURCES_FAIL = 2
FAILSAFE_INTERNET_IP = "8.8.8.8"
FAILSAFE_INTERNET_DOWN_SEC = 120
FAILSAFE_STATE_DIR = "/opt/network_monitor/state"
FAILSAFE_START_FILE = os.path.join(FAILSAFE_STATE_DIR, "failsafe_start.txt")
FAILSAFE_REBOOT_COOLDOWN_SEC = 1800
HEARTBEAT_REPORT_HOURS = [0, 8, 16]
VALIDATION_TIMEOUT_SEC = 2
LATENCY_WARNING_MS = 400
# Gateway: actualizado dinámicamente en cada ciclo desde get_network_context()
GATEWAY_IP = ""
RAM_ALERT_THRESHOLD_PCT = 90

redis_client = None
if REDIS_AVAILABLE:
    try:
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=3,
        )
        redis_client.ping()
        logger.info("Redis conectado en %s:%d", REDIS_HOST, REDIS_PORT)
    except Exception as e:
        logger.warning("Redis no disponible al inicio: %s", e)
        redis_client = None


@contextmanager
def _get_connection():
    conn = _db.connect(timeout=CONNECT_TIMEOUT)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Crea tablas si no existen. Ejecutar al arranque. Incluye infra_nodes con status y latency_ms."""
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS infra_nodes (
                ip_address TEXT PRIMARY KEY,
                status TEXT,
                last_heartbeat TIMESTAMP,
                latency_ms REAL
            )
        """)
        conn.execute("CREATE TABLE IF NOT EXISTS event_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ip_address TEXT, event_type TEXT, description TEXT, created_at TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS system_state (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS server_metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, cpu_usage REAL, ram_usage REAL, temperature REAL, recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE IF NOT EXISTS failsafe_state (key TEXT PRIMARY KEY, value TEXT)")
        conn.commit()
    logger.info("Base de datos inicializada: infra_nodes (status, latency_ms), event_log, system_state, server_metrics, failsafe_state")


def ssh_run(ip: str, command: str, timeout: int = 5) -> tuple[bool, str]:
    """SSH estricto con llave RSA. Comando: ssh -i ~/.ssh/id_rsa_shomer -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=5 root@{ip} {command}. Sin sshpass."""
    if not os.path.isfile(SSH_KEY_PATH):
        return False, f"Llave SSH no encontrada: {SSH_KEY_PATH}"
    cmd = [
        SSH_BIN,
        "-i", SSH_KEY_PATH,
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={timeout}",
        f"root@{ip}",
        command,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 2)
        if proc.returncode == 0:
            return True, proc.stdout.strip()
        return False, proc.stderr.strip() or proc.stdout.strip() or f"código {proc.returncode}"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except FileNotFoundError:
        return False, "ssh no encontrado"
    except Exception as e:
        return False, str(e)


def save_status_redis(ip: str, status: str) -> None:
    """Guarda estado en Redis: r.set(f\"status:{ip}\", status, ex=60). Instancia global redis_client."""
    if redis_client is None:
        logger.debug("Redis no disponible, omitiendo escritura para %s", ip)
        return
    try:
        redis_client.set(f"status:{ip}", status, ex=60)
        logger.debug("Redis actualizado para %s", ip)
    except Exception as e:
        logger.warning("Redis error para %s: %s", ip, e)


def ping_device_with_latency(ip: str) -> tuple[bool, float | None]:
    """Ping con latencia. Retorna (online, latency_ms)."""
    try:
        r = subprocess.run([PING_CMD, "-c", "1", "-W", str(NETWORK_TIMEOUT_SEC), ip], capture_output=True, text=True, timeout=NETWORK_TIMEOUT_SEC)
        if r.returncode != 0:
            return False, None
        out = r.stdout or ""
        m = re.search(r"time[=\s]+([\d.]+)\s*ms?", out, re.I)
        if m:
            return True, float(m.group(1))
        m = re.search(r"rtt\s+min/avg/max[^=]*=\s*([\d.]+)/", out, re.I)
        return (True, float(m.group(1))) if m else (True, None)
    except Exception:
        return False, None


def check_port(ip: str, port: int, timeout_sec: int = None) -> bool:
    """Verifica puerto TCP."""
    t = timeout_sec if timeout_sec is not None else NETWORK_TIMEOUT_SEC
    try:
        with socket.create_connection((ip, port), timeout=t):
            return True
    except (socket.timeout, socket.error, OSError):
        return False


def check_infra_node(ip: str) -> dict:
    """Verifica un nodo de infraestructura. Guarda en Redis. Concurrencia real por hilo."""
    logger.info("[DEBUG] Iniciando monitoreo de %s", ip)
    online, latency_ms = ping_device_with_latency(ip)
    if not online:
        for port in PORT_CHECK_PORTS:
            if check_port(ip, port):
                online = True
                break
    status = "online" if online else "offline"
    save_status_redis(ip, status)
    return {"ip": ip, "status": status, "latency_ms": latency_ms}


def update_infra_nodes(results: list[dict]) -> None:
    """Actualiza tabla infra_nodes con resultados concurrentes. Borra IPs que ya no están en el ciclo."""
    if not results:
        logger.warning("update_infra_nodes: sin resultados")
        return
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    active_ips = [r["ip"] for r in results]
    try:
        with _get_connection() as conn:
            for r in results:
                conn.execute(
                    "INSERT OR REPLACE INTO infra_nodes (ip_address, status, last_heartbeat, latency_ms) VALUES (?, ?, ?, ?)",
                    (r["ip"], r["status"], now, r.get("latency_ms")),
                )
            # Borrar IPs que ya no forman parte del ciclo activo
            placeholders = ",".join("?" * len(active_ips))
            conn.execute(f"DELETE FROM infra_nodes WHERE ip_address NOT IN ({placeholders})", active_ips)
            conn.commit()
        logger.info("infra_nodes actualizada: %d nodos activos", len(results))
    except Exception as e:
        logger.error("Error actualizando infra_nodes: %s", e)


def log_event(ip_address: str, event_type: str, description: str) -> None:
    """Registra evento en event_log."""
    try:
        now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        with _get_connection() as conn:
            conn.execute(
                "INSERT INTO event_log (ip_address, event_type, description, created_at) VALUES (?, ?, ?, ?)",
                (ip_address, event_type, description, now),
            )
            conn.commit()
    except Exception as e:
        logger.error("Error log_event: %s", e)


def _check_wan_quorum() -> tuple[bool, bool]:
    """Quórum WAN: 2 de 3 fallan -> internet_down."""
    results = []
    for ip in WAN_CHECK_IPS:
        ok, _ = ping_device_with_latency(ip)
        results.append(ok)
    fail_count = sum(1 for ok in results if not ok)
    internet_down = fail_count >= WAN_MIN_SOURCES_FAIL
    internet_ok = any(results)
    # [DEBUG-TEMP] Log detallado de quórum WAN
    labels = [f"{ip}={'OK' if ok else 'FAIL'}" for ip, ok in zip(WAN_CHECK_IPS, results)]
    logger.info("[WAN-QUORUM] %s → %d/3 fallos → internet_down=%s", " | ".join(labels), fail_count, internet_down)
    return internet_ok, internet_down


def read_failsafe_start() -> datetime.datetime | None:
    """Lee timestamp de inicio de failsafe."""
    if not os.path.isfile(FAILSAFE_START_FILE):
        return None
    try:
        with open(FAILSAFE_START_FILE) as f:
            s = f.read().strip()
        if s:
            return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return None


def write_failsafe_start(ts: datetime.datetime) -> None:
    """Escribe timestamp de inicio de failsafe."""
    try:
        os.makedirs(FAILSAFE_STATE_DIR, exist_ok=True)
        with open(FAILSAFE_START_FILE, "w") as f:
            f.write(ts.strftime("%Y-%m-%d %H:%M:%S"))
    except Exception as e:
        logger.warning("No se pudo escribir failsafe: %s", e)


def update_system_state(key: str, value: str) -> None:
    """Actualiza system_state."""
    try:
        with _get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO system_state (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
    except Exception:
        pass


def validate_layer7_before_reboot() -> None:
    """Validación Capa 7 no bloqueante (2s timeout)."""
    try:
        try:
            with socket.create_connection(("127.0.0.1", 80), timeout=VALIDATION_TIMEOUT_SEC):
                logger.info("[INFO] Capa7: localhost:80 OK")
        except Exception as e:
            logger.info("[INFO] Capa7: localhost:80 falló (%s)", type(e).__name__)
        try:
            r = requests.get("https://www.google.com", timeout=VALIDATION_TIMEOUT_SEC)
            logger.info("[INFO] Capa7: Google HTTP %d", r.status_code)
        except Exception as e:
            logger.info("[INFO] Capa7: Google falló (%s)", type(e).__name__)
    except Exception:
        pass


def do_reboot_failover() -> None:
    """Ejecuta reboot vía SSH usando identidad RSA."""
    logger.warning("INTERNET_DOWN > 120s: ejecutando reboot Gateway (.210) vía SSH RSA")
    ok, msg = ssh_run(GATEWAY_IP, "/sbin/reboot", timeout=SSH_REBOOT_CONNECT_TIMEOUT)
    if ok:
        logger.info("Reboot SSH enviado al Gateway (.210)")
        log_event(GATEWAY_IP, "reboot", "Reinicio automático: Internet caído > 120s")
        send_telegram_alert("⚡ <b>REINICIO EN PROGRESO</b> SHOMER: Reboot enviado al Gateway (.210) vía SSH RSA")
    else:
        logger.error("[CRITICAL] Falla de autenticación o conexión SSH al .210: %s", msg)
        log_event(GATEWAY_IP, "reboot_failed", f"Error SSH: {msg}")
        send_telegram_alert("🚨 <b>PÉRDIDA DE SERVICIO</b> SHOMER: Fallo crítico en reboot SSH al Gateway (.210)")


def failsafe_check_and_act(internet_down: bool) -> None:
    """Failsafe inmune: cronómetro 120s que persiste tras reinicios."""
    now = datetime.datetime.utcnow()
    logger.info("Estado WAN: %s", "INTERNET_DOWN" if internet_down else "WAN_OK")

    if not internet_down:
        try:
            if os.path.isfile(FAILSAFE_START_FILE):
                os.remove(FAILSAFE_START_FILE)
        except Exception:
            pass
        update_system_state("status", "healthy")
        logger.info("[FAILSAFE] WAN OK — sin acción")
        return

    start = read_failsafe_start()
    if start is None:
        write_failsafe_start(now)
        update_system_state("status", "recovering")
        update_system_state("start_time", now.strftime("%Y-%m-%d %H:%M:%S"))
        logger.warning("[FAILSAFE] INTERNET_DOWN detectado — cronómetro 120s INICIADO")
        return

    elapsed = (now - start).total_seconds()
    if elapsed < FAILSAFE_INTERNET_DOWN_SEC:
        logger.warning("[FAILSAFE] INTERNET_DOWN: %.0fs / 120s — esperando umbral", elapsed)
        return

    if _failsafe_reboot_alert_already_sent():
        logger.info("Cooldown activo: reboot ya enviado recientemente")
        try:
            if os.path.isfile(FAILSAFE_START_FILE):
                os.remove(FAILSAFE_START_FILE)
        except Exception:
            pass
        return

    logger.info("Ejecutando comando SSH de reboot ahora...")
    validate_layer7_before_reboot()
    send_telegram_alert("🔴 <b>PÉRDIDA DE SERVICIO</b> SHOMER: Internet Caído\n<b>REINICIO EN PROGRESO</b> Ejecutando reinicio del Gateway (.210) vía SSH RSA")
    _failsafe_mark_reboot_alert_sent()
    do_reboot_failover()
    try:
        if os.path.isfile(FAILSAFE_START_FILE):
            os.remove(FAILSAFE_START_FILE)
    except Exception:
        pass


def _failsafe_reboot_alert_already_sent() -> bool:
    """Verifica cooldown de reboot."""
    try:
        with _get_connection() as conn:
            row = conn.execute("SELECT value FROM failsafe_state WHERE key = 'last_reboot_alert_at'").fetchone()
        if not row or not row["value"]:
            return False
        ts = datetime.datetime.strptime(row["value"], "%Y-%m-%d %H:%M:%S")
        return (datetime.datetime.utcnow() - ts).total_seconds() < FAILSAFE_REBOOT_COOLDOWN_SEC
    except Exception:
        return False


def _failsafe_mark_reboot_alert_sent() -> None:
    """Marca reboot alert enviado."""
    try:
        with _get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO failsafe_state (key, value) VALUES ('last_reboot_alert_at', ?)",
                (datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),),
            )
            conn.commit()
    except Exception:
        pass


def _get_server_metrics() -> tuple[float | None, float | None, float | None]:
    """CPU%, RAM%, Temp desde /proc y /sys."""
    cpu_pct, ram_pct, temp_c = None, None, None
    try:
        with open("/proc/stat") as f:
            p1 = f.readline().split()
        time.sleep(0.1)
        with open("/proc/stat") as f:
            p2 = f.readline().split()
        if len(p1) >= 5 and len(p2) >= 5:
            t1, i1 = sum(int(x) for x in p1[1:5]), int(p1[4])
            t2, i2 = sum(int(x) for x in p2[1:5]), int(p2[4])
            if t2 > t1:
                cpu_pct = 100.0 * (1 - (i2 - i1) / (t2 - t1))
    except Exception:
        pass
    try:
        with open("/proc/meminfo") as f:
            d = f.read()
        m = re.search(r"MemTotal:\s+(\d+)", d)
        total = int(m.group(1)) if m else 0
        m = re.search(r"MemAvailable:\s+(\d+)", d)
        avail = int(m.group(1)) if m else None
        if avail is None:
            m = re.search(r"MemFree:\s+(\d+)", d)
            avail = int(m.group(1)) if m else 0
        if total > 0 and avail is not None:
            ram_pct = 100.0 * (1 - avail / total)
    except Exception:
        pass
    try:
        for name in os.listdir("/sys/class/thermal"):
            p = os.path.join("/sys/class/thermal", name, "temp")
            if os.path.isfile(p):
                with open(p) as f:
                    temp_c = int(f.read().strip()) / 1000.0
                break
        if temp_c is None and os.path.isdir("/sys/class/hwmon"):
            for d in os.listdir("/sys/class/hwmon"):
                p = os.path.join("/sys/class/hwmon", d, "temp1_input")
                if os.path.isfile(p):
                    with open(p) as f:
                        temp_c = int(f.read().strip()) / 1000.0
                    break
    except Exception:
        pass
    return (cpu_pct, ram_pct, temp_c)


def _maybe_send_heartbeat_report() -> None:
    """Reporte cada 8h: guarda métricas y alerta si RAM > 90%."""
    try:
        now = datetime.datetime.utcnow()
        if now.hour not in HEARTBEAT_REPORT_HOURS:
            return
        with _get_connection() as conn:
            row = conn.execute("SELECT value FROM failsafe_state WHERE key = 'last_heartbeat_report_hour'").fetchone()
            if row and row["value"] == str(now.hour):
                return
            conn.execute("INSERT OR REPLACE INTO failsafe_state (key, value) VALUES ('last_heartbeat_report_hour', ?)", (str(now.hour),))
            conn.commit()
        cpu, ram, temp = _get_server_metrics()
        with _get_connection() as conn:
            conn.execute(
                "INSERT INTO server_metrics (cpu_usage, ram_usage, temperature, recorded_at) VALUES (?, ?, ?, ?)",
                (cpu, ram, temp, now.strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
        parts = []
        if cpu is not None:
            parts.append(f"CPU {cpu:.0f}%")
        if ram is not None:
            parts.append(f"RAM {ram:.0f}%")
        if temp is not None:
            parts.append(f"Temp {temp:.0f}°C")
        suffix = " | " + ", ".join(parts) if parts else ""
        send_telegram_alert(f"✅ <b>SALUD DE NODOS</b> SHOMER Operativo - Todos los sistemas OK{suffix}")
        if ram is not None and ram >= RAM_ALERT_THRESHOLD_PCT:
            send_telegram_alert(f"🚨 <b>PÉRDIDA DE SERVICIO</b> Servidor en Peligro - RAM {ram:.0f}% (límite 90%)")
    except Exception as e:
        logger.warning("Heartbeat: %s", e)


def monitor_cycle_concurrent(cycle_count: int) -> None:
    """Ciclo de monitoreo concurrente usando ThreadPoolExecutor. IPs desde nodos_gl.json o fallback .205-.226."""
    global GATEWAY_IP
    infra_ips, gateway = _get_monitor_ips()
    GATEWAY_IP = gateway
    max_workers = min(25, max(1, len(infra_ips)))

    try:
        internet_ok, internet_down = _check_wan_quorum()
    except Exception as e:
        logger.warning("Chequeo WAN falló: %s", e)
        internet_ok, internet_down = False, True

    if internet_down:
        logger.info("[SHOMER] INTERNET_DOWN")

    _maybe_send_heartbeat_report()
    failsafe_check_and_act(internet_down)

    logger.info("Ciclo %d: monitoreando %d nodos infraestructura", cycle_count, len(infra_ips))

    futures = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for ip in infra_ips:
            futures[pool.submit(check_infra_node, ip)] = ip

        results = []
        for fut in as_completed(futures):
            ip = futures[fut]
            try:
                res = fut.result()
                results.append(res)
                logger.debug("%s: %s (latency: %s ms)", ip, res["status"], res["latency_ms"] or "N/A")
            except Exception as e:
                logger.warning("%s: error en hilo: %s", ip, e)
                results.append({"ip": ip, "status": "unknown", "latency_ms": None})

    update_infra_nodes(results)
    logger.info("Ciclo %d completado; próximo en %d s", cycle_count, CYCLE_INTERVAL_SEC)


def main():
    global GATEWAY_IP
    logger.info("Iniciando SHOMER Monitor Pro v2.0...")
    ips0, gw0 = _get_monitor_ips()
    GATEWAY_IP = gw0
    logger.info("Red: %d nodos a monitorear (nodos_gl o fallback .205-.226); gateway %s", len(ips0), gw0)

    if not os.path.isfile(SSH_KEY_PATH):
        logger.error("Llave SSH no encontrada: %s", SSH_KEY_PATH)
        logger.error("Crea la llave con: ssh-keygen -t rsa -f ~/.ssh/id_rsa_shomer -N ''")
        return 1

    init_db()

    if os.path.isfile(FAILSAFE_START_FILE):
        since = read_failsafe_start()
        if since:
            logger.info("Failsafe persistente: retomando cronómetro desde failsafe_start.txt (timestamp: %s). No se reinicia el contador.", since.strftime("%Y-%m-%d %H:%M:%S"))

    send_telegram_alert(MSG_INICIO)

    cycle_count = 0
    try:
        while True:
            cycle_count += 1
            monitor_cycle_concurrent(cycle_count)
            time.sleep(CYCLE_INTERVAL_SEC)
    except KeyboardInterrupt:
        logger.info("SHOMER detenido por el usuario")
        return 0
    except Exception as e:
        logger.exception("Error crítico: %s", e)
        try:
            send_telegram_alert(f"🚨 <b>PÉRDIDA DE SERVICIO</b> Error Crítico SHOMER\n{str(e)[:300]}")
        except Exception:
            pass
        try:
            os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:])
        except Exception as re:
            logger.error("No se pudo reiniciar: %s", re)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
