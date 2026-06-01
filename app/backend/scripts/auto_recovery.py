#!/usr/bin/env python3
"""
Auto-recovery: revisa cada minuto la BD y reinicia dispositivos OFFLINE
cuyo último reinicio fue hace más de 10 minutos.
Dispara reboot_glinet.py para el reinicio y registra eventos en events_log.
Optimizado para consumir menos del 2% de CPU (dormir 60 s entre ciclos).
"""
import logging
import os
import sys
import time
from datetime import datetime, timedelta

# Añadir backend y scripts al path para importar db y reboot_glinet
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPTS_DIR)
for _p in (_BACKEND_DIR, _SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from db import get_connection
from reboot_glinet import reboot_glinet

# Configuración
CHECK_INTERVAL_SEC = 60
REBOOT_COOLDOWN_MIN = 10
LOG_DIR = "/var/log/shomer"
LOG_FILE = os.path.join(LOG_DIR, "auto_recovery.log")

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger("auto_recovery")


def _now_utc() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _log_event(device_id: int, event_type: str, description: str, severity: str = "info") -> None:
    """Registra un evento en events_log para que el Dashboard lo muestre."""
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO events_log (device_id, event_type, description, severity, created_at) VALUES (?, ?, ?, ?, ?)",
                (device_id, event_type, description, severity, _now_utc()),
            )
            conn.commit()
    except Exception as e:
        logger.warning("No se pudo escribir en events_log: %s", e)


def _get_offline_devices_eligible_for_reboot() -> list:
    """
    Devuelve dispositivos activos cuyo último estado es OFFLINE
    y last_reboot_at es NULL o hace más de REBOOT_COOLDOWN_MIN minutos.
    """
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            # Último estado por dispositivo (mismo criterio que el API)
            cur.execute("""
                SELECT d.id, d.name, d.last_reboot_at
                FROM devices d
                JOIN (
                    SELECT device_id, MAX(last_check) AS last_check
                    FROM device_status
                    GROUP BY device_id
                ) m ON d.id = m.device_id
                JOIN device_status ds ON ds.device_id = m.device_id AND ds.last_check = m.last_check
                WHERE d.is_active = 1
                  AND LOWER(TRIM(ds.status)) = 'offline'
            """)
            rows = cur.fetchall()
            out = []
            cutoff = (datetime.utcnow() - timedelta(minutes=REBOOT_COOLDOWN_MIN)).strftime("%Y-%m-%d %H:%M:%S")
            for row in rows:
                r = dict(row)
                last_reboot = r.get("last_reboot_at")
                if last_reboot is None or (str(last_reboot).strip() or "0000-00-00") < cutoff:
                    out.append({"id": r["id"], "name": r.get("name") or f"Device-{r['id']}"})
            return out
    except Exception as e:
        logger.exception("Error leyendo dispositivos offline: %s", e)
        return []


def _run_cycle() -> None:
    """Un ciclo: buscar offline elegibles y disparar reinicio vía reboot_glinet."""
    devices = _get_offline_devices_eligible_for_reboot()
    if not devices:
        return
    for d in devices:
        device_id = d["id"]
        name = d["name"]
        _log_event(device_id, "auto_recovery", f"Auto-recovery: intentando reinicio de {name} (ID {device_id})", "info")
        logger.info("Auto-recovery: reiniciando %s (ID %s)", name, device_id)
        try:
            ok, info = reboot_glinet(device_id=device_id)
            if ok:
                _log_event(device_id, "auto_recovery", f"Auto-recovery: reinicio solicitado para {name}", "info")
                logger.info("Auto-recovery: reinicio solicitado para %s: %s", name, info)
            else:
                _log_event(device_id, "auto_recovery", f"Auto-recovery: fallo reinicio {name} - {info}", "warning")
                logger.warning("Auto-recovery: fallo %s - %s", name, info)
        except Exception as e:
            _log_event(device_id, "auto_recovery", f"Auto-recovery: error reinicio {name} - {e}", "error")
            logger.exception("Auto-recovery: error reiniciando %s: %s", name, e)
        # Un solo reinicio por ciclo para no saturar
        break


def main() -> int:
    logger.info("Auto-recovery iniciado (intervalo=%ds, cooldown=%d min)", CHECK_INTERVAL_SEC, REBOOT_COOLDOWN_MIN)
    try:
        while True:
            _run_cycle()
            time.sleep(CHECK_INTERVAL_SEC)
    except KeyboardInterrupt:
        logger.info("Auto-recovery detenido por el usuario")
        return 0
    except Exception as e:
        logger.exception("Auto-recovery error fatal: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
