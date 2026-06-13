"""
Lógica compartida Guardian (Redis, SSH reboot, eventos) — sin rutas FastAPI.
"""
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from app.api.shomer_common import get_config

logger = logging.getLogger(__name__)

MONITOR_RECENT_SEC = 120
FAILURES_KEY_PREFIX = "failures:"
NODE_DATA_PREFIX = "node:"
LAST_REBOOT_KEY_PREFIX = "last_reboot:"
ALERT_THRESHOLD = int(os.environ.get("SHOMER_ALERT_THRESHOLD", "2"))
AUTO_REBOOT_COOLDOWN_SEC = int(os.environ.get("SHOMER_REBOOT_COOLDOWN_SEC", "360"))
# Override en instalación no estándar: export SHOMER_SSH_KEY_PATH=/ruta/id_rsa
SSH_KEY_PATH = (os.environ.get("SHOMER_SSH_KEY_PATH") or "").strip() or (
    "/home/usb_admin/.ssh/id_ed25519_shomer"
)
SSH_KNOWN_HOSTS = (os.environ.get("SHOMER_SSH_KNOWN_HOSTS") or "").strip() or (
    "/home/usb_admin/.ssh/known_hosts"
)
SSH_CONNECT_TIMEOUT = 5
SSH_FALLBACK_PASSWORD = os.environ.get("SSH_FALLBACK_PASSWORD", "")
ALLOWED_IP_PATTERN = re.compile(
    r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
    r"(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
)

MAINTENANCE_KEY = "shomer_maintenance"
NODE_MAINTENANCE_PREFIX = "node_maintenance:"  # clave por nodo: node_maintenance:{ip}
EVENTS_KEY = "shomer_events"
EVENTS_MAX = 200


def send_telegram_safe(msg: str) -> None:
    """Envía mensaje Telegram sin lanzar excepción si falla."""
    try:
        from app.scripts.alerts import send_telegram_alert
        send_telegram_alert(msg)
    except Exception:
        pass


def _get_guardian_thresholds() -> Tuple[int, int]:
    """Lee fail_threshold y cooldown_sec desde system_state. Fallback a constantes."""
    try:
        threshold = int(get_config("guardian.fail_threshold") or ALERT_THRESHOLD)
        cooldown = int(get_config("guardian.cooldown_sec") or AUTO_REBOOT_COOLDOWN_SEC)
        return threshold, cooldown
    except Exception:
        return ALERT_THRESHOLD, AUTO_REBOOT_COOLDOWN_SEC


def log_event(r, level: str, source: str, message: str) -> None:
    """Registra evento en Redis para el panel de logs en tiempo real."""
    if r is None:
        return
    try:
        import time

        entry = json.dumps(
            {
                "ts": int(time.time() * 1000),
                "level": level,
                "source": source,
                "msg": message,
            },
            ensure_ascii=False,
        )
        r.lpush(EVENTS_KEY, entry)
        r.ltrim(EVENTS_KEY, 0, EVENTS_MAX - 1)
    except Exception as e:
        logger.debug("log_event error: %s", e)


def _redis_bool(v: Any) -> Optional[bool]:
    if v is None or v == "":
        return None
    if v in (True, "1", 1, "true", "True", "yes"):
        return True
    if v in (False, "0", 0, "false", "False", "no"):
        return False
    return None


def _normalize_success(payload: Dict[str, Any]) -> bool:
    """Interpreta success del JSON: true/True/1/"true" -> True; resto -> False."""
    if "success" in payload:
        v = payload["success"]
        if v is True or v in (1, "true", "True", "1"):
            return True
        if v is False or v in (0, "false", "False", "0"):
            return False
    if isinstance(payload.get("connection_results"), dict):
        cr = payload["connection_results"]
        v = cr.get("success", cr.get("ok"))
        if v is True or v in (1, "true", "True", "1"):
            return True
        if v is False or v in (0, "false", "False", "0"):
            return False
    return False


_SNMP_REBOOT_OID = "1.3.6.1.4.1.11863.10.1.2.1.0"


def _get_device_ssh_credentials(
    node_ip: str,
) -> Tuple[Optional[str], Optional[str], int, str]:
    """User/password/port/reboot_command desde devices. reboot_command default: reboot."""
    try:
        from app.backend.db import connect
        conn = connect(timeout=5, check_same_thread=False)
        conn.row_factory = __import__("sqlite3").Row
        try:
            cur = conn.execute(
                "SELECT ssh_user, ssh_password, ssh_port, reboot_command "
                "FROM devices WHERE ip_address=? AND is_active=1 LIMIT 1",
                (node_ip,),
            )
            row = cur.fetchone()
            if row and row["ssh_user"] and row["ssh_password"]:
                port = int(row["ssh_port"] or 22)
                cmd = (row["reboot_command"] or "reboot").strip() or "reboot"
                return row["ssh_user"], row["ssh_password"], port, cmd
        finally:
            conn.close()
    except Exception:
        pass
    return None, None, 22, "reboot"


def _get_device_snmp_credentials(node_ip: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Devuelve (reboot_method, snmp_community_read, snmp_community_write) del dispositivo."""
    try:
        from app.backend.db import connect
        conn = connect(timeout=5, check_same_thread=False)
        conn.row_factory = __import__("sqlite3").Row
        try:
            cur = conn.execute(
                "SELECT reboot_method, snmp_community, snmp_community_write "
                "FROM devices WHERE ip_address=? AND is_active=1 LIMIT 1",
                (node_ip,)
            )
            row = cur.fetchone()
            if row:
                return row["reboot_method"], row["snmp_community"], row["snmp_community_write"]
        finally:
            conn.close()
    except Exception:
        pass
    return None, None, None


def _run_snmp_reboot(node_ip: str, community_write: str) -> Tuple[bool, str]:
    """Reinicia el dispositivo vía SNMP SET. Verificado en EAP225 y EAP610."""
    snmpset = shutil.which("snmpset")
    if not snmpset:
        return False, "snmpset no disponible en el sistema"

    # Pre-ping: confirmar que el device está en LAN antes de enviar el SET.
    # Si no responde a ping → verdaderamente inalcanzable → no tiene sentido
    # enviar SNMP y confundir el timeout con un reboot exitoso.
    try:
        ping_r = subprocess.run(
            ["ping", "-c", "1", "-W", "2", node_ip],
            capture_output=True, timeout=4,
        )
        if ping_r.returncode != 0:
            return False, f"Device inalcanzable (ping falló) — SNMP SET no enviado"
    except Exception:
        return False, "Error al hacer ping pre-SNMP — SNMP SET no enviado"

    try:
        r = subprocess.run(
            [snmpset, "-v2c", "-c", community_write, "-t", "8", "-r", "1",
             node_ip, _SNMP_REBOOT_OID, "i", "1"],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0:
            return True, f"Reboot SNMP enviado a {node_ip}"
        return False, (r.stderr or r.stdout or f"exit code {r.returncode}").strip()
    except subprocess.TimeoutExpired:
        # Device respondió al ping pero cortó la conexión SNMP → empezó a
        # reiniciarse antes de responder al SET. Éxito confirmado.
        return True, "Reboot SNMP enviado — device reiniciando (timeout esperado)"
    except Exception as e:
        return False, str(e)


def _run_ssh_reboot(node_ip: str) -> Tuple[bool, str]:
    """Ejecuta reboot. Prioridad: (1) SNMP si reboot_method=snmp, (2) SSH credenciales BD, (3) llave SSH, (4) fallback global, (5) SNMP fallback."""
    if not ALLOWED_IP_PATTERN.match(node_ip):
        return False, "IP no permitida"

    # 0) SNMP directo si el dispositivo lo tiene configurado como método principal
    reboot_method, _, snmp_write = _get_device_snmp_credentials(node_ip)
    if reboot_method == "snmp" and snmp_write:
        return _run_snmp_reboot(node_ip, snmp_write)

    sshpass_path = shutil.which("sshpass")

    # 1) Intentar con credenciales específicas del dispositivo (user+password de la BD)
    db_user, db_pwd, db_port, reboot_cmd = _get_device_ssh_credentials(node_ip)
    if db_user and db_pwd and sshpass_path:
        try:
            cmd_db = [
                sshpass_path, "-p", db_pwd,
                "/usr/bin/ssh",
                "-o", "ConnectTimeout=" + str(SSH_CONNECT_TIMEOUT),
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=" + SSH_KNOWN_HOSTS,
                "-o", "HostKeyAlgorithms=+ssh-rsa,ssh-dss,ecdsa-sha2-nistp256,ssh-ed25519",
                "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa,ssh-dss",
                "-o", "KexAlgorithms=+diffie-hellman-group14-sha1,diffie-hellman-group14-sha256,diffie-hellman-group1-sha1",
                "-p", str(db_port),
                f"{db_user}@{node_ip}",
                reboot_cmd,
            ]
            r = subprocess.run(cmd_db, capture_output=True, text=True, timeout=SSH_CONNECT_TIMEOUT + 5)
            if r.returncode == 0:
                return True, f"Reboot enviado vía credenciales BD (user={db_user})"
            err_msg = r.stderr or r.stdout or f"exit code {r.returncode}"
        except subprocess.TimeoutExpired:
            err_msg = "Timeout SSH (credenciales BD)"
        except Exception as e:
            err_msg = str(e)
        # Si falló con credenciales BD, continuar con llave SSH como fallback
    else:
        err_msg = "Sin credenciales en BD para este nodo"

    # 2) Intentar con llave SSH
    key = SSH_KEY_PATH
    if os.path.isfile(key):
        try:
            cmd_key = [
                "/usr/bin/ssh",
                "-i", key,
                "-o", "ConnectTimeout=" + str(SSH_CONNECT_TIMEOUT),
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "HostKeyAlgorithms=+ssh-rsa,ssh-dss,ecdsa-sha2-nistp256,ssh-ed25519",
                "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa,ssh-dss",
                "-o", "KexAlgorithms=+diffie-hellman-group14-sha1,diffie-hellman-group14-sha256,diffie-hellman-group1-sha1",
                "-o", "BatchMode=yes",
                "root@" + node_ip,
                "reboot",
            ]
            r = subprocess.run(cmd_key, capture_output=True, text=True, timeout=SSH_CONNECT_TIMEOUT + 5)
            if r.returncode == 0:
                return True, "Reboot enviado vía llave SSH"
            err_msg = r.stderr or r.stdout or f"exit code {r.returncode}"
        except subprocess.TimeoutExpired:
            err_msg = "Timeout SSH (llave)"
        except Exception as e:
            err_msg = str(e)

    # 3) Fallback con contraseña global SSH_FALLBACK_PASSWORD
    if sshpass_path and SSH_FALLBACK_PASSWORD:
        try:
            cmd_fb = [
                sshpass_path, "-p", SSH_FALLBACK_PASSWORD,
                "/usr/bin/ssh",
                "-o", "ConnectTimeout=" + str(SSH_CONNECT_TIMEOUT),
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa",
                "root@" + node_ip,
                "reboot",
            ]
            r2 = subprocess.run(cmd_fb, capture_output=True, text=True, timeout=SSH_CONNECT_TIMEOUT + 5)
            if r2.returncode == 0:
                return True, "Reboot enviado (fallback global)"
            return False, r2.stderr or r2.stdout or f"fallback exit code {r2.returncode}"
        except subprocess.TimeoutExpired:
            return False, "Timeout SSH (fallback global)"
        except Exception as e2:
            return False, f"Fallback error: {e2}"

    # 4) Fallback SNMP si SSH falló y el dispositivo tiene comunidad write
    if snmp_write:
        logger.info("SSH falló para %s — intentando reboot SNMP como fallback", node_ip)
        return _run_snmp_reboot(node_ip, snmp_write)

    return False, err_msg


def _save_node_data_redis(r, node_id: str, payload: Dict[str, Any]) -> None:
    """Persiste clients, uptime y estados de pings (point_a, point_b, point_c) en Redis hash."""
    key = f"{NODE_DATA_PREFIX}{node_id}"
    mapping: Dict[str, str] = {}
    if "clients" in payload and payload["clients"] is not None:
        mapping["clients"] = str(int(payload["clients"]))
    if "uptime" in payload and payload["uptime"] is not None:
        mapping["uptime"] = str(int(payload["uptime"]))
    for k in ("point_a", "point_b", "point_c"):
        if k in payload and payload[k] is not None:
            mapping[k] = "1" if payload[k] in (True, 1, "1", "true", "yes") else "0"
    if mapping:
        r.hset(key, mapping=mapping)
