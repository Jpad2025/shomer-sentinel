"""Guardian — salud del propio Shomer (WAN quorum, métricas, heartbeat report).

Migración Sesión 15 de funciones únicas que antes vivían en
`app/scripts/monitor.py` (servicio `network-monitor.service` legacy).

Cumple §0: umbrales, IPs WAN, horas de heartbeat y RAM alert se leen de
`system_state` vía `get_config(...)`; defaults por variables de entorno.

Tareas expuestas (ciclos independientes, arrancan en `lifespan`):
    - `server_health_loop()`       — cada `health_interval_sec`:
          - WAN quorum (N IPs públicas configurables)
          - escribe `shomer:wan_status` en Redis
          - escribe métricas cpu/ram/temp en `server_metrics` (SQLite)
          - dispara Telegram 🚨 si RAM >= ram_alert_threshold
          - dispara failsafe Shomer: 🔴 si WAN cae > wan_fail_sec
                                     🟢 recuperación si sube tras caída
    - `heartbeat_report_loop()`    — cada 10 min:
          - si hora actual ∈ heartbeat_hours y no se mandó en la hora → ✅ SALUD DE NODOS

Endpoint público:
    - GET /api/server-metrics     — últimas 20 muestras cpu/ram/temp
    - GET /api/wan-status         — estado WAN actual + timestamp
"""
from __future__ import annotations

import asyncio
import datetime
import logging
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends

from app.api.auth_api import get_current_user
from app.api.shomer_common import get_config, get_db, get_redis
from app.api.shomer_guardian_lib import send_telegram_safe

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Shomer Server Health"])

_HEALTH_INTERVAL_DEFAULT = int(os.environ.get("SHOMER_HEALTH_INTERVAL_SEC", "30"))
_WAN_IPS_DEFAULT = os.environ.get(
    "SHOMER_WAN_CHECK_IPS", "8.8.8.8,1.1.1.1,208.67.222.222"
)
_WAN_MIN_FAIL_DEFAULT = int(os.environ.get("SHOMER_WAN_MIN_FAIL", "2"))
_WAN_FAIL_SEC_DEFAULT = int(os.environ.get("SHOMER_WAN_FAIL_SEC", "120"))
_WAN_COOLDOWN_SEC_DEFAULT = int(os.environ.get("SHOMER_WAN_COOLDOWN_SEC", "1800"))
_RAM_ALERT_DEFAULT = int(os.environ.get("SHOMER_RAM_ALERT_PCT", "90"))
_HEARTBEAT_HOURS_DEFAULT = os.environ.get("SHOMER_HEARTBEAT_HOURS", "0,8,16")
_STARTUP_TELEGRAM = os.environ.get("SHOMER_STARTUP_TELEGRAM", "1") in ("1", "true", "yes")

WAN_STATUS_KEY = "shomer:wan_status"
WAN_FAIL_START_KEY = "shomer:wan_fail_start"
WAN_LAST_ALERT_KEY = "shomer:wan_last_alert"
HEARTBEAT_REPORT_KEY = "shomer:heartbeat_last_hour"
STARTUP_SENT_KEY = "shomer:startup_sent"

_server_health_task: Optional[asyncio.Task] = None
_heartbeat_report_task: Optional[asyncio.Task] = None


def _failsafe_state_get(key: str) -> Optional[str]:
    """Lee clave persistente de tabla SQLite `failsafe_state` (sobrevive reinicios Redis)."""
    try:
        with get_db() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS failsafe_state (key TEXT PRIMARY KEY, value TEXT)"
            )
            cur = conn.execute("SELECT value FROM failsafe_state WHERE key = ?", (key,))
            row = cur.fetchone()
            if row is None:
                return None
            return row["value"] if hasattr(row, "keys") else row[0]
    except Exception as e:
        logger.debug("failsafe_state_get(%s): %s", key, e)
        return None


def _failsafe_state_set(key: str, value: str) -> None:
    try:
        with get_db() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS failsafe_state (key TEXT PRIMARY KEY, value TEXT)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO failsafe_state (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()
    except Exception as e:
        logger.debug("failsafe_state_set(%s): %s", key, e)


def _failsafe_state_delete(key: str) -> None:
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM failsafe_state WHERE key = ?", (key,))
            conn.commit()
    except Exception as e:
        logger.debug("failsafe_state_delete(%s): %s", key, e)




def _get_server_health_config() -> Dict[str, Any]:
    """Lee parámetros de health desde BD con fallback a env/constantes."""
    def _cfg_int(key: str, default: int) -> int:
        try:
            v = get_config(key)
            if v is None or v == "":
                return default
            return int(v)
        except Exception:
            return default

    def _cfg_str(key: str, default: str) -> str:
        v = get_config(key)
        if not v:
            return default
        return str(v)

    def _parse_list(s: str) -> List[str]:
        return [x.strip() for x in s.split(",") if x.strip()]

    def _parse_int_list(s: str) -> List[int]:
        out = []
        for x in s.split(","):
            x = x.strip()
            if not x:
                continue
            try:
                out.append(int(x))
            except Exception:
                pass
        return out

    return {
        "health_interval_sec": _cfg_int(
            "guardian.health_interval_sec", _HEALTH_INTERVAL_DEFAULT
        ),
        "wan_check_ips": _parse_list(
            _cfg_str("guardian.wan_check_ips", _WAN_IPS_DEFAULT)
        ),
        "wan_min_fail": _cfg_int("guardian.wan_min_fail", _WAN_MIN_FAIL_DEFAULT),
        "wan_fail_sec": _cfg_int("guardian.wan_fail_sec", _WAN_FAIL_SEC_DEFAULT),
        "wan_cooldown_sec": _cfg_int(
            "guardian.wan_cooldown_sec", _WAN_COOLDOWN_SEC_DEFAULT
        ),
        "ram_alert_pct": _cfg_int("guardian.ram_alert_pct", _RAM_ALERT_DEFAULT),
        "heartbeat_hours": _parse_int_list(
            _cfg_str("guardian.heartbeat_hours", _HEARTBEAT_HOURS_DEFAULT)
        ),
    }


def _ping_ok(ip: str, timeout_sec: int = 2) -> bool:
    try:
        r = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout_sec), ip],
            capture_output=True, text=True, timeout=timeout_sec + 2,
        )
        return r.returncode == 0
    except Exception:
        return False


def _check_wan_quorum(cfg: Dict[str, Any]) -> Tuple[bool, Dict[str, bool]]:
    """Prueba las IPs WAN desde el propio Shomer. Devuelve (down, detalle)."""
    results: Dict[str, bool] = {}
    for ip in cfg["wan_check_ips"]:
        results[ip] = _ping_ok(ip)
    fails = sum(1 for ok in results.values() if not ok)
    down = fails >= cfg["wan_min_fail"]
    return down, results


def _get_server_metrics() -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """CPU%, RAM%, Temp desde /proc y /sys — sólo lectura local."""
    cpu_pct: Optional[float] = None
    ram_pct: Optional[float] = None
    temp_c: Optional[float] = None
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
    return cpu_pct, ram_pct, temp_c


def _persist_server_metrics(cpu: Optional[float], ram: Optional[float], temp: Optional[float]) -> None:
    """Inserta fila en tabla server_metrics (crea la tabla si falta)."""
    try:
        with get_db() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS server_metrics ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "cpu_usage REAL, ram_usage REAL, temperature REAL, "
                "recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.execute(
                "INSERT INTO server_metrics (cpu_usage, ram_usage, temperature, recorded_at) "
                "VALUES (?, ?, ?, ?)",
                (cpu, ram, temp, datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
    except Exception as e:
        logger.warning("persist_server_metrics: %s", e)


def _send_startup_message_once() -> None:
    """Envía 🔄 SISTEMA REINICIADO — sólo una vez por arranque (clave Redis con TTL 1h)."""
    if not _STARTUP_TELEGRAM:
        return
    r = get_redis()
    if r is None:
        return
    try:
        if r.get(STARTUP_SENT_KEY):
            return
        r.set(STARTUP_SENT_KEY, "1", ex=3600)
        send_telegram_safe(
            "🔄 <b>SALUD DE NODOS</b> SISTEMA REINICIADO — Shomer Sentinel activo y operativo"
        )
    except Exception:
        pass


async def _server_health_tick(cfg: Dict[str, Any]) -> None:
    r = get_redis()
    down, detail = await asyncio.to_thread(_check_wan_quorum, cfg)
    now_ts = int(time.time())

    if r is not None:
        try:
            r.set(
                WAN_STATUS_KEY,
                "down" if down else "ok",
                ex=max(cfg["health_interval_sec"] * 3, 60),
            )
        except Exception:
            pass

    cpu, ram, temp = await asyncio.to_thread(_get_server_metrics)

    await asyncio.to_thread(_persist_server_metrics, cpu, ram, temp)

    if ram is not None and ram >= cfg["ram_alert_pct"] and r is not None:
        ram_alert_key = "shomer:ram_alert_sent"
        try:
            if not r.get(ram_alert_key):
                r.set(ram_alert_key, "1", ex=3600)
                send_telegram_safe(
                    f"🚨 <b>PÉRDIDA DE SERVICIO</b> SHOMER Servidor en peligro — "
                    f"RAM {ram:.0f}% (umbral {cfg['ram_alert_pct']}%)"
                )
        except Exception:
            pass

    if r is None:
        return

    try:
        if down:
            fail_start_raw = r.get(WAN_FAIL_START_KEY) or _failsafe_state_get("wan_fail_start")
            if fail_start_raw is None:
                r.set(WAN_FAIL_START_KEY, str(now_ts))
                _failsafe_state_set("wan_fail_start", str(now_ts))
                logger.warning(
                    "[WAN-QUORUM] Shomer sin internet — cronómetro iniciado (%s)",
                    detail,
                )
                return
            elapsed = now_ts - int(fail_start_raw)
            if elapsed < cfg["wan_fail_sec"]:
                logger.warning(
                    "[WAN-QUORUM] Shomer sin internet: %ds / %ds — esperando umbral",
                    elapsed, cfg["wan_fail_sec"],
                )
                return
            last_alert = r.get(WAN_LAST_ALERT_KEY) or _failsafe_state_get("wan_last_alert")
            if last_alert and (now_ts - int(last_alert)) < cfg["wan_cooldown_sec"]:
                return
            r.set(WAN_LAST_ALERT_KEY, str(now_ts), ex=cfg["wan_cooldown_sec"])
            _failsafe_state_set("wan_last_alert", str(now_ts))
            detail_str = ", ".join(
                f"{ip}={'OK' if ok else 'FAIL'}" for ip, ok in detail.items()
            )
            send_telegram_safe(
                f"🔴 <b>PÉRDIDA DE SERVICIO</b> SHOMER Internet Caído (> {cfg['wan_fail_sec']}s)\n"
                f"Shomer no alcanza WAN: {detail_str}"
            )
            logger.error("[WAN-QUORUM] ALERTA enviada — Shomer sin internet > %ds", cfg["wan_fail_sec"])
        else:
            fail_start_raw = r.get(WAN_FAIL_START_KEY) or _failsafe_state_get("wan_fail_start")
            if fail_start_raw is not None:
                r.delete(WAN_FAIL_START_KEY)
                _failsafe_state_delete("wan_fail_start")
                last_alert = r.get(WAN_LAST_ALERT_KEY) or _failsafe_state_get("wan_last_alert")
                if last_alert:
                    send_telegram_safe(
                        "🟢 <b>SALUD DE NODOS</b> SHOMER Internet restaurado — "
                        "conectividad WAN recuperada"
                    )
                    r.delete(WAN_LAST_ALERT_KEY)
                    _failsafe_state_delete("wan_last_alert")
    except Exception as e:
        logger.warning("wan failsafe: %s", e)


async def _server_health_loop() -> None:
    _send_startup_message_once()
    await asyncio.sleep(5)
    while True:
        try:
            cfg = await asyncio.to_thread(_get_server_health_config)
            await _server_health_tick(cfg)
        except Exception as e:
            logger.warning("server_health_loop error: %s", e)
        try:
            interval = int(get_config("guardian.health_interval_sec") or _HEALTH_INTERVAL_DEFAULT)
        except Exception:
            interval = _HEALTH_INTERVAL_DEFAULT
        await asyncio.sleep(interval)


async def _heartbeat_report_tick(cfg: Dict[str, Any]) -> None:
    r = get_redis()
    if r is None:
        return
    now = datetime.datetime.utcnow()
    if now.hour not in cfg["heartbeat_hours"]:
        return
    try:
        last = r.get(HEARTBEAT_REPORT_KEY) or _failsafe_state_get("last_heartbeat_report_hour")
        if last == str(now.hour):
            return
        r.set(HEARTBEAT_REPORT_KEY, str(now.hour), ex=3700)
        _failsafe_state_set("last_heartbeat_report_hour", str(now.hour))
    except Exception:
        return
    cpu, ram, temp = await asyncio.to_thread(_get_server_metrics)
    parts = []
    if cpu is not None:
        parts.append(f"CPU {cpu:.0f}%")
    if ram is not None:
        parts.append(f"RAM {ram:.0f}%")
    if temp is not None:
        parts.append(f"Temp {temp:.0f}°C")
    wan = r.get(WAN_STATUS_KEY) or "unknown"
    parts.append(f"WAN {wan}")
    suffix = " | " + ", ".join(parts) if parts else ""
    send_telegram_safe(
        f"✅ <b>SALUD DE NODOS</b> SHOMER operativo — todos los sistemas OK{suffix}"
    )


async def _heartbeat_report_loop() -> None:
    await asyncio.sleep(20)
    while True:
        try:
            cfg = await asyncio.to_thread(_get_server_health_config)
            await _heartbeat_report_tick(cfg)
        except Exception as e:
            logger.warning("heartbeat_report_loop error: %s", e)
        await asyncio.sleep(600)


def start_server_health_tasks() -> None:
    """Arranca las dos loops como background tasks del event loop actual."""
    global _server_health_task, _heartbeat_report_task
    loop = asyncio.get_event_loop()
    _server_health_task = loop.create_task(_server_health_loop())
    _heartbeat_report_task = loop.create_task(_heartbeat_report_loop())
    logger.info("Guardian server health tasks iniciadas (WAN quorum + métricas + heartbeat report)")


@router.get("/api/server-metrics")
async def get_server_metrics(limit: int = 20):
    """Últimas N muestras de cpu/ram/temperatura + lectura en vivo."""
    try:
        cpu_now, ram_now, temp_now = _get_server_metrics()
        history: List[Dict[str, Any]] = []
        try:
            with get_db() as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS server_metrics ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "cpu_usage REAL, ram_usage REAL, temperature REAL, "
                    "recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
                )
                cur = conn.execute(
                    "SELECT cpu_usage, ram_usage, temperature, recorded_at "
                    "FROM server_metrics ORDER BY id DESC LIMIT ?",
                    (max(1, min(int(limit), 200)),),
                )
                for row in cur.fetchall():
                    history.append({
                        "cpu": row["cpu_usage"],
                        "ram": row["ram_usage"],
                        "temp": row["temperature"],
                        "ts": row["recorded_at"],
                    })
        except Exception as e:
            logger.warning("server-metrics db: %s", e)
        return {
            "success": True,
            "now": {"cpu": cpu_now, "ram": ram_now, "temp": temp_now},
            "history": history,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/disk-partitions")
async def get_disk_partitions(user=Depends(get_current_user)):
    """Uso de disco de todas las particiones relevantes del host."""
    import shutil
    PARTITIONS = [
        ("/",        "sistema"),
        ("/var",     "logs"),
        ("/opt",     "Shomer"),
        ("/home",    "home"),
        ("/storage", "agente/datos"),
        ("/srv",     "srv"),
    ]
    result = []
    for path, label in PARTITIONS:
        try:
            total, used, free = shutil.disk_usage(path)
            pct = round(used / total * 100, 1)
            result.append({
                "mount": path,
                "label": label,
                "total_gb": round(total / 1e9, 1),
                "used_gb":  round(used  / 1e9, 1),
                "free_gb":  round(free  / 1e9, 1),
                "pct":      pct,
            })
        except Exception:
            pass
    return {"success": True, "partitions": result}


@router.get("/api/wan-status")
async def get_wan_status(user=Depends(get_current_user)):
    """Estado actual del WAN quorum desde Redis."""
    r = get_redis()
    if r is None:
        return {"success": False, "error": "Redis no disponible"}
    try:
        status = r.get(WAN_STATUS_KEY) or "unknown"
        fail_start = r.get(WAN_FAIL_START_KEY)
        last_alert = r.get(WAN_LAST_ALERT_KEY)
        now_ts = int(time.time())
        return {
            "success": True,
            "status": status,
            "fail_elapsed_sec": (now_ts - int(fail_start)) if fail_start else None,
            "last_alert_age_sec": (now_ts - int(last_alert)) if last_alert else None,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
