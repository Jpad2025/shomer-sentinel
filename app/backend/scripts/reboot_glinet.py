#!/usr/bin/env python3
"""
Reinicio del GL-MT6000 (u otro dispositivo) vía SSH usando sshpass.
Credenciales por argumentos o desde la tabla devices (por device_id).
Actualiza device_status a REBOOTING y registra en events_log.
"""
import argparse
import logging
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Tuple

import os
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
from app.backend.db import connect, CONNECT_TIMEOUT

COMMAND = "/sbin/reboot"
SSHPASS_PATH = "/usr/bin/sshpass"
SSH_PATH = "/usr/bin/ssh"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("reboot_glinet")


@contextmanager
def _get_connection():
    conn = connect(timeout=CONNECT_TIMEOUT)
    try:
        yield conn
    finally:
        conn.close()


def get_credentials_from_db(device_id: int = None) -> Optional[Tuple[str, str, str]]:
    """Obtiene (ip_address, ssh_user, ssh_password) de la tabla devices.
    Si device_id es None, usa el primer dispositivo activo con SSH configurado."""
    try:
        with _get_connection() as conn:
            cur = conn.cursor()
            if device_id is not None:
                cur.execute(
                    "SELECT ip_address, ssh_user, ssh_password FROM devices WHERE id = ? AND is_active = 1",
                    (device_id,),
                )
            else:
                cur.execute(
                    "SELECT ip_address, ssh_user, ssh_password FROM devices "
                    "WHERE is_active = 1 AND ssh_user IS NOT NULL ORDER BY id LIMIT 1"
                )
            row = cur.fetchone()
            if not row or not row["ip_address"] or not row["ssh_user"] or not row["ssh_password"]:
                return None
            return (row["ip_address"], row["ssh_user"], row["ssh_password"])
    except Exception:
        return None


def update_status_rebooting(device_id: int) -> bool:
    """Inserta en device_status estado REBOOTING y registra en events_log 'Iniciado por el usuario'."""
    try:
        with _get_connection() as conn:
            cur = conn.cursor()
            now_ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                "INSERT INTO device_status (device_id, status, last_check) VALUES (?, ?, ?)",
                (device_id, "rebooting", now_ts),
            )
            cur.execute(
                "INSERT INTO events_log (device_id, event_type, description, severity, created_at) VALUES (?, ?, ?, ?, ?)",
                (device_id, "reboot_requested", "Iniciado por el usuario", "info", now_ts),
            )
            conn.commit()
        return True
    except Exception:
        return False


def reboot_glinet(
    device_id: int = None,
    ip: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Reinicia el dispositivo vía sshpass/ssh.

    Si se pasan ip, user y password se usan directamente.
    Si no, se leen de la tabla devices para el device_id dado.
    Si device_id es None, usa el primer dispositivo activo con SSH.

    Tras éxito: actualiza device_status a rebooting y registra en events_log.
    """
    if ip and user and password:
        host, login, pwd = ip, user, password
        effective_device_id = device_id
    else:
        creds = get_credentials_from_db(device_id)
        if not creds:
            return False, f"Dispositivo {device_id} no encontrado o sin credenciales en la BD"
        host, login, pwd = creds
        effective_device_id = device_id

    # Usar ruta absoluta de sshpass para que el script lo encuentre aunque PATH no lo incluya
    ssh_cmd = [
        SSHPASS_PATH,
        "-p",
        pwd,
        SSH_PATH,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "PreferredAuthentications=password",
        f"{login}@{host}",
        COMMAND,
    ]

    try:
        proc = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            err_msg = f"SSH reboot failed (code {proc.returncode}): {stderr}"
            logger.error("Comando reinicio falló: %s", err_msg)
            if stderr:
                logger.error("stderr: %s", stderr)
            if stdout:
                logger.error("stdout: %s", stdout)
            return False, err_msg

        # Éxito: feedback de estado y trazabilidad
        update_status_rebooting(effective_device_id)
        return True, "Reboot command executed successfully via sshpass/ssh"
    except subprocess.TimeoutExpired as e:
        logger.exception("Timeout ejecutando reinicio SSH: %s", e)
        return False, "SSH connection timed out while executing reboot"
    except FileNotFoundError as e:
        logger.error("sshpass/ssh no encontrado: %s (ruta usada: %s)", e, SSHPASS_PATH)
        return False, f"sshpass no encontrado (ruta esperada: {SSHPASS_PATH})"
    except Exception as e:
        logger.exception("Error inesperado en reinicio: %s", e)
        return False, f"Unexpected error: {e}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Reinicio GL-MT6000 (u otro) vía SSH")
    parser.add_argument("--device-id", type=int, default=5, help="ID del dispositivo en la BD (default: 5)")
    parser.add_argument("--ip", type=str, default=None, help="IP del dispositivo (opcional)")
    parser.add_argument("--user", type=str, default=None, help="Usuario SSH (opcional)")
    parser.add_argument("--password", type=str, default=None, help="Contraseña SSH (opcional)")
    args = parser.parse_args()

    if (args.ip or args.user or args.password) and not (args.ip and args.user and args.password):
        print("Si se usan credenciales por argumentos, hay que pasar --ip, --user y --password.")
        return 2

    ok, info = reboot_glinet(
        device_id=args.device_id,
        ip=args.ip,
        user=args.user,
        password=args.password,
    )
    print(info)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
