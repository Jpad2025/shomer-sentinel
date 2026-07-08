"""
Inframonitor — monitoreo ICMP (+TCP opcional) de cualquier equipo de red.
Switches, servidores, NAS, cámaras, impresoras — cualquier IP que responda ping.
Sin lógica de reboot ni failsafe. Solo registro de estado para NOC y panel.
Alertas Telegram en transiciones de estado (online↔offline).
"""
import asyncio
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import time as _time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.api.auth_api import get_current_user
from app.api.shomer_common import (
    REDIS_AVAILABLE,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PORT,
    get_db,
    get_redis,
    get_config,
)
from app.api.shomer_status_events import _context_snapshots, record_status_event
from app.api.shomer_network_blip import evaluate_host_network_blip_async
from app.api.shomer_pulse_correlate import read_last_blip, read_poll_context, write_poll_context
from app.api.shomer_infra_pulse import (
    ensure_pulse_table,
    mark_pulse_alerted,
    pulse_alert_due,
    pulse_config,
    pulse_enabled,
    update_pulse,
)
from app.api.infra_monitor_profiles import (
    derive_liveness,
    enrich_device_row,
    ping_count_for_profile,
    resolve_monitor_profile,
)

try:
    import redis as redis_lib
except ImportError:
    redis_lib = None  # type: ignore

_security = HTTPBearer(auto_error=False)


def _optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> Optional[dict]:
    from app.api.auth_api import verify_token
    token = (credentials.credentials if credentials and credentials.credentials else None) \
            or request.cookies.get("access_token")
    if not token:
        return None
    payload = verify_token(token)
    if not payload:
        return None
    return {"username": payload.get("username") or payload.get("sub"), "role": payload.get("role", "operator")}


logger = logging.getLogger(__name__)
router = APIRouter(tags=["inframonitor"])

FAST_POLL_INTERVAL_SEC = int(os.environ.get("INFRA_FAST_POLL_INTERVAL_SEC", "30"))
SNMP_POLL_INTERVAL_SEC = int(os.environ.get("INFRA_SNMP_POLL_INTERVAL_SEC", "300"))
POLL_INTERVAL_SEC = FAST_POLL_INTERVAL_SEC  # compat TTL / logs
_poller_running = False
_executor_configured = False
_fast_executor: Optional[ThreadPoolExecutor] = None
_snmp_executor: Optional[ThreadPoolExecutor] = None
# Pools separados: ping/tcp/mac (fast) vs SNMP (lento). El default de asyncio
# (min(32, CPUs+4) ≈ 8 hilos) hacía cola y falsos offline.
ALERT_COOLDOWN_SEC = 300  # no repetir alerta del mismo equipo por 5 min
_sync_ap_cache: Optional[frozenset] = None  # evita writes en BD si los APs Guardian no cambiaron

DEVICE_ICONS = {
    "generic":    "📡",
    "ap":         "📶",
    "router":     "🌐",
    "switch":     "🔀",
    "server":     "🖥️",
    "nas":        "💾",
    "camera":     "📷",
    "printer":    "🖨️",
    "pos":        "🏧",
    "reader":     "💳",
    "controller": "🎛️",
    "pc":         "🖱️",
    "phone":      "📞",
    "ups":        "🔋",
}


# ──────────────────────────────────────────────
# DB init + migrations
# ──────────────────────────────────────────────

def _infra_device_counts() -> Tuple[int, int]:
    """Equipos activos (sin APs Guardian) y con SNMP — para dimensionar pools."""
    try:
        with get_db() as conn:
            n = int(conn.execute(
                "SELECT COUNT(*) FROM infra_devices "
                "WHERE active = 1 AND device_type != 'ap'"
            ).fetchone()[0])
            n_snmp = int(conn.execute(
                "SELECT COUNT(*) FROM infra_devices WHERE active = 1 "
                "AND device_type != 'ap' "
                "AND snmp_community IS NOT NULL AND trim(snmp_community) != ''"
            ).fetchone()[0])
        return n, n_snmp
    except Exception:
        return 0, 0


def _scaled_fast_workers(n_devices: int) -> int:
    auto = min(128, max(32, n_devices * 2)) if n_devices > 0 else 32
    override = os.environ.get("INFRA_THREAD_WORKERS", "").strip()
    manual = os.environ.get("INFRA_AUTO_SCALE_WORKERS", "1").strip().lower() in (
        "0", "false", "no",
    )
    if override and manual:
        return max(8, int(override))
    if override:
        return max(auto, int(override))
    return auto


def _scaled_snmp_workers(n_snmp: int) -> int:
    auto = min(32, max(8, n_snmp * 2)) if n_snmp > 0 else 8
    override = os.environ.get("INFRA_SNMP_THREAD_WORKERS", "").strip()
    manual = os.environ.get("INFRA_AUTO_SCALE_WORKERS", "1").strip().lower() in (
        "0", "false", "no",
    )
    if override and manual:
        return max(4, int(override))
    if override:
        return max(auto, int(override))
    return auto


def _ensure_executors():
    """Pools fast (ping/tcp/mac) y snmp separados; tamaño según inventario activo."""
    global _executor_configured, _fast_executor, _snmp_executor
    if _executor_configured:
        return
    n_dev, n_snmp = _infra_device_counts()
    fast_w = _scaled_fast_workers(n_dev)
    snmp_w = _scaled_snmp_workers(n_snmp)
    _fast_executor = ThreadPoolExecutor(
        max_workers=fast_w, thread_name_prefix="infra-fast",
    )
    _snmp_executor = ThreadPoolExecutor(
        max_workers=snmp_w, thread_name_prefix="infra-snmp",
    )
    try:
        loop = asyncio.get_event_loop()
        loop.set_default_executor(_fast_executor)
        _executor_configured = True
        logger.info(
            "Inframonitor: pools fast=%d snmp=%d workers (equipos=%d con_snmp=%d)",
            fast_w, snmp_w, n_dev, n_snmp,
        )
    except Exception as e:
        logger.warning("Inframonitor: no se pudo configurar executors: %s", e)


async def _run_in_snmp_executor(fn, /, *args, **kwargs):
    _ensure_executors()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_snmp_executor, partial(fn, *args, **kwargs))


_tables_ready = False


def _init_tables():
    # Esta función hacía CREATE/ALTER TABLE en CADA request (list_devices, get_status,
    # add_device, etc.) -- DDL real contra SQLite en el único hilo de Guardian, en cada
    # llamada, no solo la primera. Bajo contención con otro escritor (poller, Hunter,
    # backups) eso puede bloquear el event loop entero. Guard de una sola vez por proceso.
    global _tables_ready
    if _tables_ready:
        return
    _ensure_executors()
    with get_db() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS infra_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                device_type TEXT DEFAULT 'generic',
                location TEXT DEFAULT '',
                tcp_port INTEGER DEFAULT NULL,
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS infra_status (
                ip TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                latency_ms REAL,
                tcp_ok INTEGER DEFAULT NULL,
                mac TEXT DEFAULT NULL,
                last_state_change TEXT,
                checked_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS infra_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                event TEXT NOT NULL,
                ts TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_infra_events_ip_ts ON infra_events (ip, ts);
        """)
        # Migrations for existing installs
        for col, tbl, defn in [
            ("tcp_port",         "infra_devices", "INTEGER DEFAULT NULL"),
            ("snmp_community",         "infra_devices", "TEXT DEFAULT 'public'"),
            ("snmp_community_write",   "infra_devices", "TEXT DEFAULT ''"),
            ("pc_server_ip",     "infra_devices", "TEXT DEFAULT NULL"),
            ("tcp_ok",           "infra_status",  "INTEGER DEFAULT NULL"),
            ("loss_pct",         "infra_status",  "REAL DEFAULT NULL"),
            ("mac",              "infra_status",  "TEXT DEFAULT NULL"),
            ("last_state_change","infra_status",  "TEXT"),
            ("snmp_data",        "infra_status",  "TEXT"),
            ("snmp_ok",          "infra_status",  "INTEGER DEFAULT NULL"),
            ("monitor_profile",  "infra_devices", "TEXT DEFAULT ''"),
        ]:
            try:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {defn}")
            except Exception:
                pass
        conn.commit()
        _backfill_monitor_profiles(conn)
        ensure_pulse_table(conn)
        conn.commit()
    _tables_ready = True


def _backfill_monitor_profiles(conn) -> None:
    """Asigna monitor_profile inferido a equipos sin perfil explícito."""
    try:
        rows = conn.execute(
            "SELECT ip, device_type, tcp_port, snmp_community, monitor_profile "
            "FROM infra_devices WHERE active = 1"
        ).fetchall()
        for r in rows:
            desired = resolve_monitor_profile(
                r["device_type"] or "generic",
                r["tcp_port"],
                r["snmp_community"],
                r["monitor_profile"],
            )
            current = (r["monitor_profile"] or "").strip()
            if current != desired:
                conn.execute(
                    "UPDATE infra_devices SET monitor_profile = ? WHERE ip = ?",
                    (desired, r["ip"]),
                )
        conn.commit()
    except Exception as e:
        logger.warning("backfill monitor_profile: %s", e)


def _sync_guardian_aps() -> int:
    """Guardian access_point → infra_devices (tipo ap). Los APs viven en devices; Infra los refleja."""
    global _sync_ap_cache
    n = 0
    try:
        with get_db() as conn:
            try:
                ap_rows = conn.execute(
                    "SELECT ip_address, name, location FROM devices "
                    "WHERE is_active=1 AND device_type='access_point'"
                ).fetchall()
            except Exception:
                return 0
            # Solo escribir en BD si el conjunto de APs cambió
            ap_snapshot = frozenset(
                (r["ip_address"], r["name"] or "", r["location"] or "")
                for r in ap_rows if r["ip_address"]
            )
            if ap_snapshot == _sync_ap_cache:
                return 0
            _sync_ap_cache = ap_snapshot
            for row in ap_rows:
                ip = row["ip_address"]
                if not ip:
                    continue
                conn.execute(
                    "INSERT INTO infra_devices "
                    "(ip, name, device_type, location, active, tcp_port, snmp_community, monitor_profile) "
                    "VALUES (?, ?, 'ap', ?, 1, NULL, '', 'ap_guardian') "
                    "ON CONFLICT(ip) DO UPDATE SET "
                    "name=excluded.name, location=excluded.location, "
                    "device_type='ap', active=1, monitor_profile='ap_guardian'",
                    (ip, row["name"] or ip, row["location"] or ""),
                )
                n += 1
            # APs dados de baja en Guardian → ocultar en Infra
            if ap_rows:
                ips = [r["ip_address"] for r in ap_rows if r["ip_address"]]
                ph = ",".join("?" * len(ips))
                conn.execute(
                    f"UPDATE infra_devices SET active=0 WHERE device_type='ap' "
                    f"AND ip NOT IN ({ph})",
                    ips,
                )
            conn.commit()
            if n:
                logger.info("Inframonitor: %d APs Guardian sincronizados a infra_devices", n)
    except Exception as e:
        logger.warning("sync guardian APs → infra: %s", e)
    return n


def _map_guardian_status_to_infra(g_st: str) -> str:
    """Traduce estado Guardian/infra_nodes al vocabulario de infra_status."""
    s = (g_st or "unknown").strip().lower()
    if s in ("online", "ok"):
        return "online"
    if s == "degraded":
        return "degraded"
    if s in ("offline", "down", "no-internet"):
        return "offline"
    return "unknown"


def _sync_ap_status_from_guardian() -> int:
    """Espeja estado Guardian (infra_nodes) → infra_status para APs (sin ping Infra)."""
    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    try:
        with get_db() as conn:
            # devices.status queda en 'unknown' (inventario); el poller Guardian escribe en infra_nodes.
            rows = conn.execute(
                """
                SELECT n.ip_address, n.status, n.latency_ms
                FROM infra_nodes n
                INNER JOIN infra_devices i ON i.ip = n.ip_address
                    AND i.device_type = 'ap' AND i.active = 1
                """
            ).fetchall()
            for r in rows:
                ip = r["ip_address"]
                if not ip:
                    continue
                status = _map_guardian_status_to_infra(r["status"])
                raw_lat = r["latency_ms"]
                latency = int(round(raw_lat)) if raw_lat is not None else None
                prev = conn.execute(
                    "SELECT status, last_state_change FROM infra_status WHERE ip = ?",
                    (ip,),
                ).fetchone()
                prev_status = prev["status"] if prev else None
                last_change = now
                if prev and prev_status == status and prev["last_state_change"]:
                    last_change = prev["last_state_change"]
                conn.execute(
                    """
                    INSERT INTO infra_status (ip, status, latency_ms, checked_at, last_state_change)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(ip) DO UPDATE SET
                        status = excluded.status,
                        latency_ms = excluded.latency_ms,
                        checked_at = excluded.checked_at,
                        last_state_change = CASE
                            WHEN infra_status.status != excluded.status THEN excluded.last_state_change
                            ELSE infra_status.last_state_change
                        END
                    """,
                    (ip, status, latency, now, last_change),
                )
                updated += 1
            conn.commit()
    except Exception as e:
        logger.warning("sync ap status from guardian: %s", e)
    return updated


# ──────────────────────────────────────────────
# Network helpers (blocking, run in thread)
# ──────────────────────────────────────────────

_LOSS_RE = re.compile(r"(\d+(?:\.\d+)?)%\s*packet loss", re.IGNORECASE)
PING_COUNT = int(os.environ.get("INFRA_PING_COUNT", "3"))
PING_LOSS_DEGRADED_PCT = int(os.environ.get("INFRA_PING_LOSS_DEGRADED_PCT", "60"))
INFRA_BLIP_MIN_DEVICES = int(os.environ.get("INFRA_BLIP_MIN_DEVICES", "8"))

# SNMP — semáforo async, cache ifTable y walk cada 60 s (poll cada 30 s).
SNMP_SEM = asyncio.Semaphore(int(os.environ.get("INFRA_SNMP_SEM", "8")))
SNMP_IFCACHE_SEC = int(os.environ.get("INFRA_SNMP_IFCACHE_SEC", "90"))
SNMP_WALK_INTERVAL_SEC = int(os.environ.get("INFRA_SNMP_WALK_INTERVAL_SEC", "60"))
# Equipos que solo hablan v1 (EdgeSwitch/UniFi/impresoras) pagaban el timeout
# completo de v2c en cada ciclo antes de caer a v1 -- ahora se recuerda la
# versión que funcionó (_snmp_ver en snmp_data) y se prueba esa primero.
SNMP_FAIL_BACKOFF_THRESHOLD = int(os.environ.get("INFRA_SNMP_FAIL_BACKOFF_THRESHOLD", "3"))
SNMP_FAIL_BACKOFF_SEC = int(os.environ.get("INFRA_SNMP_FAIL_BACKOFF_SEC", "300"))
_snmp_iftable_cache: Dict[str, Dict[str, Any]] = {}
_PRINTER_DESCR_MARKERS = ("HP", "BROTHER", "CANON", "EPSON")


def _ping(ip: str, count: Optional[int] = None) -> tuple[str, Optional[float], float]:
    """Paquetes ICMP — offline solo si se pierden TODOS; degraded si pérdida alta."""
    ping_n = count if count is not None else PING_COUNT
    try:
        result = subprocess.run(
            ["ping", "-c", str(ping_n), "-W", "2", "-i", "0.3", ip],
            capture_output=True, text=True, timeout=ping_n * 2 + 3,
        )
        out = result.stdout or ""
        m_loss = _LOSS_RE.search(out)
        loss = float(m_loss.group(1)) if m_loss else 100.0
        latency = None
        for line in out.splitlines():
            if "time=" in line:
                try:
                    latency = float(line.split("time=")[1].split()[0])
                    break
                except Exception:
                    pass
        if loss >= 100.0:
            return "offline", None, loss
        if loss >= PING_LOSS_DEGRADED_PCT:
            return "degraded", latency, loss
        return "online", latency, loss
    except Exception:
        return "offline", None, 100.0


def _tcp_check(ip: str, port: int) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=3):
            return True
    except Exception:
        return False


def _get_mac(ip: str) -> Optional[str]:
    """Read MAC from kernel ARP table. Works after a successful ping."""
    try:
        result = subprocess.run(
            ["ip", "neigh", "show", ip],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if "lladdr" in parts:
                idx = parts.index("lladdr")
                return parts[idx + 1].upper()
    except Exception:
        pass
    return None


def _parse_iftable(output: str, prev_snmp: Optional[dict]) -> tuple:
    """Parse snmpwalk 1.3.6.1.2.1.2.2.1 output → (interfaces list, raw_octets dict)."""
    COL_BY_NUM = {
        "2": "descr", "5": "speed", "7": "admin", "8": "oper",
        "10": "in_oct", "14": "in_err", "16": "out_oct", "20": "out_err",
    }
    COL_BY_NAME = {
        "ifdescr": "descr", "ifspeed": "speed", "ifadminstatus": "admin",
        "ifoperstatus": "oper", "ifinoctets": "in_oct", "ifinerrors": "in_err",
        "ifoutoctets": "out_oct", "ifouterrors": "out_err",
    }
    rows: dict = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        try:
            lhs, rhs = line.split("=", 1)
            lhs, rhs = lhs.strip(), rhs.strip()
            col = idx = None
            if "::" in lhs:
                name_part = lhs.split("::", 1)[1]
                if "." in name_part:
                    cname, idx = name_part.rsplit(".", 1)
                    col = COL_BY_NAME.get(cname.lower())
            else:
                parts = lhs.lstrip(".").split(".")
                if len(parts) >= 2:
                    col = COL_BY_NUM.get(parts[-2])
                    idx = parts[-1]
            if not col or not idx:
                continue
            if "STRING:" in rhs:
                val = rhs.split("STRING:", 1)[1].strip().strip('"')
            elif "INTEGER:" in rhs:
                val = rhs.split("INTEGER:", 1)[1].strip()
                if "(" in val:
                    val = val[val.index("(")+1:val.index(")")]
            elif any(t in rhs for t in ("Gauge32:", "Counter32:", "Counter64:")):
                val = rhs.split(":", 1)[1].strip()
            else:
                val = rhs
            rows.setdefault(idx, {})[col] = val.strip()
        except Exception:
            pass

    prev_raw = (prev_snmp or {}).get("_raw_octets", {})
    prev_ts  = (prev_snmp or {}).get("_raw_ts", 0)
    dt = _time.time() - prev_ts if prev_ts else 0

    interfaces = []
    raw_octets: dict = {}
    for idx, data in sorted(rows.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
        name = data.get("descr", f"if{idx}")
        if name.lower() in ("lo", "loopback") or name.lower().startswith("lo:"):
            continue
        oper_raw = data.get("oper", "")
        oper = "up" if oper_raw == "1" else ("down" if oper_raw == "2" else "unknown")
        try:
            speed_mbps = int(data.get("speed", 0) or 0) // 1_000_000 or None
        except Exception:
            speed_mbps = None
        try:
            in_oct  = int(data.get("in_oct",  0) or 0)
            out_oct = int(data.get("out_oct", 0) or 0)
        except Exception:
            in_oct, out_oct = 0, 0
        raw_octets[idx] = {"in": in_oct, "out": out_oct}
        rx_mbps = tx_mbps = None
        if dt > 0 and idx in prev_raw:
            p_in, p_out = prev_raw[idx].get("in", 0), prev_raw[idx].get("out", 0)
            d_in  = in_oct  - p_in  if in_oct  >= p_in  else (4294967295 - p_in  + in_oct)
            d_out = out_oct - p_out if out_oct >= p_out else (4294967295 - p_out + out_oct)
            rx_mbps = round(d_in  * 8 / dt / 1_000_000, 3)
            tx_mbps = round(d_out * 8 / dt / 1_000_000, 3)
        try:
            in_err  = int(data.get("in_err",  0) or 0)
            out_err = int(data.get("out_err", 0) or 0)
        except Exception:
            in_err, out_err = 0, 0
        interfaces.append({
            "idx": idx, "name": name, "oper": oper,
            "speed_mbps": speed_mbps,
            "rx_mbps": rx_mbps, "tx_mbps": tx_mbps,
            "in_errors": in_err, "out_errors": out_err,
        })
    return interfaces, raw_octets


_PRINTER_STATUS_LABELS = {1: "otro", 2: "desconocido", 3: "lista", 4: "imprimiendo", 5: "calentando"}
_OID_INPUT_CURRENT = "1.3.6.1.2.1.43.8.2.1.10"
_OID_INPUT_MAX = "1.3.6.1.2.1.43.8.2.1.9"


def _parse_snmp_walk_indexed(stdout: str, table_oid: str) -> dict[str, int]:
    """Parsea snmpwalk de tablas prtInput* — clave = sufijo índice (ej. '1.1', '1.2')."""
    tail = table_oid.rsplit(".", 1)[-1]
    pattern = re.compile(rf"\.43\.8\.2\.1\.{re.escape(tail)}\.(.+)$")
    out: dict[str, int] = {}
    for line in (stdout or "").splitlines():
        if "=" not in line:
            continue
        lhs, rhs = line.split("=", 1)
        m = pattern.search(lhs.strip())
        if not m:
            continue
        val_str = rhs.strip().split(":")[-1].strip()
        try:
            out[m.group(1)] = int(val_str)
        except ValueError:
            continue
    return out


def _tray_paper_state(current: int, max_cap: int) -> str:
    """RFC 3805 prtInputCurrentLevel — -3/-4 = con papel; 0 = vacía."""
    if current in (-3, -4):
        return "ok"
    if current in (-2, -1):
        return "unknown"
    if current == 0:
        return "empty" if max_cap > 0 else "unknown"
    if current > 0:
        if max_cap > 0 and current <= max(10, int(max_cap * 0.08)):
            return "low"
        return "ok"
    return "unknown"


def _summarize_printer_paper(levels: dict[str, int], maxs: dict[str, int]) -> dict:
    """Agrega todas las bandejas — alerta solo si ninguna tiene papel."""
    trays: list = []
    has_paper = False
    has_definite_empty = False
    best_current: Optional[int] = None
    best_max: Optional[int] = None
    worst_empty_current: Optional[int] = None
    worst_empty_max: Optional[int] = None

    def _idx_key(k: str) -> tuple:
        try:
            return tuple(int(p) for p in k.split("."))
        except ValueError:
            return (999, 999)

    for idx in sorted(set(levels) | set(maxs), key=_idx_key):
        cur = levels.get(idx)
        if cur is None:
            continue
        mx = maxs.get(idx, 0)
        state = _tray_paper_state(cur, mx)
        trays.append({
            "index": idx,
            "current": cur if cur >= 0 else None,
            "max": mx if mx > 0 else None,
            "level_raw": cur,
            "state": state,
        })
        if state in ("ok", "low"):
            has_paper = True
            if cur >= 0 and (best_current is None or cur > best_current):
                best_current = cur
                best_max = mx if mx > 0 else None
        elif state == "empty":
            has_definite_empty = True
            if worst_empty_current is None:
                worst_empty_current = 0
                worst_empty_max = mx if mx > 0 else None

    paper_low = bool(trays) and not has_paper and has_definite_empty
    if best_current is not None:
        paper_current, paper_max = best_current, best_max
    elif worst_empty_current is not None:
        paper_current, paper_max = worst_empty_current, worst_empty_max
    else:
        paper_current = paper_max = None

    return {
        "paper_trays": trays,
        "paper_ok": has_paper,
        "paper_low": paper_low,
        "paper_current": paper_current,
        "paper_max": paper_max,
        "paper_tray_count": len(trays),
    }


def _poll_printer_snmp(
    snmpget: str,
    snmpwalk: Optional[str],
    base: list,
    ip: str,
    timeout: int,
) -> Optional[dict]:
    """Estado impresora: tóner + todas las bandejas de papel (prtInput table)."""
    try:
        r_p = subprocess.run(
            [snmpget] + base + [ip,
                "1.3.6.1.2.1.25.3.5.1.1.1",
                "1.3.6.1.2.1.43.11.1.1.9.1.1",
            ],
            capture_output=True, text=True, timeout=timeout + 2,
        )
        if r_p.returncode != 0 or not r_p.stdout.strip():
            return None
        pr_status = pr_toner = None
        for line in r_p.stdout.splitlines():
            if "=" not in line:
                continue
            lhs, rhs = line.split("=", 1)
            lhs_s = lhs.strip()
            val_str = rhs.strip().split(":")[-1].strip()
            try:
                val = int(val_str)
            except ValueError:
                continue
            if "25.3.5.1.1.1" in lhs_s:
                pr_status = _PRINTER_STATUS_LABELS.get(val, f"código {val}")
            elif "43.11.1.1.9.1.1" in lhs_s:
                pr_toner = None if val < 0 else val

        levels: dict[str, int] = {}
        maxs: dict[str, int] = {}
        if snmpwalk:
            walk_to = timeout + 6
            for oid, dest in ((_OID_INPUT_CURRENT, levels), (_OID_INPUT_MAX, maxs)):
                try:
                    r_w = subprocess.run(
                        [snmpwalk] + base + [ip, oid],
                        capture_output=True, text=True, timeout=walk_to,
                    )
                    if r_w.returncode == 0 and r_w.stdout.strip():
                        dest.update(_parse_snmp_walk_indexed(r_w.stdout, oid))
                except Exception:
                    pass
        if not levels and not maxs:
            r_fb = subprocess.run(
                [snmpget] + base + [ip, f"{_OID_INPUT_CURRENT}.1.1", f"{_OID_INPUT_MAX}.1.1"],
                capture_output=True, text=True, timeout=timeout + 2,
            )
            if r_fb.returncode == 0:
                for line in r_fb.stdout.splitlines():
                    if "=" not in line:
                        continue
                    lhs, rhs = line.split("=", 1)
                    lhs_s = lhs.strip()
                    val_str = rhs.strip().split(":")[-1].strip()
                    try:
                        val = int(val_str)
                    except ValueError:
                        continue
                    if "43.8.2.1.10.1.1" in lhs_s:
                        levels["1.1"] = val
                    elif "43.8.2.1.9.1.1" in lhs_s:
                        maxs["1.1"] = val

        paper = _summarize_printer_paper(levels, maxs)
        return {
            "status": pr_status,
            "toner_pct": pr_toner,
            **paper,
        }
    except Exception:
        return None


def _parse_snmp_string(rhs: str) -> str:
    if "STRING:" in rhs:
        return rhs.split("STRING:", 1)[1].strip().strip('"')
    return ""


def _snmp_cmd_base(community: str, timeout: int, version: str) -> list:
    return ["-v" + version, "-c", community, "-t", str(timeout), "-r", "0"]


def _snmp_probe_version(
    snmpget: str, ip: str, community: str, timeout: int,
    known_version: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Prueba v2c primero; fallback v1 (EdgeSwitch / UniFi adoptados).

    Si known_version viene seteado (la versión que respondió la última vez
    para este equipo), se prueba primero -- evita pagar el timeout completo
    de v2c en cada ciclo para equipos que solo hablan v1.
    """
    sys_oids = ["1.3.6.1.2.1.1.1.0", "1.3.6.1.2.1.1.3.0", "1.3.6.1.2.1.1.5.0"]
    versions = ("2c", "1")
    if known_version in versions:
        versions = (known_version,) + tuple(v for v in versions if v != known_version)
    for ver in versions:
        try:
            r = subprocess.run(
                [snmpget] + _snmp_cmd_base(community, timeout, ver) + [ip] + sys_oids,
                capture_output=True, text=True, timeout=timeout + 2,
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout, ver
        except Exception:
            continue
    return None, None


def _is_printer_sysdescr(sys_descr: str) -> bool:
    u = (sys_descr or "").upper()
    return any(m in u for m in _PRINTER_DESCR_MARKERS)


def _uptime_ticks(sys_uptime: str) -> Optional[str]:
    """Clave estable de uptime SNMP para invalidar cache."""
    if not sys_uptime:
        return None
    return sys_uptime.strip()


def _snmp_poll(
    ip: str,
    community: str,
    prev_snmp: Optional[dict],
    device_type: str = "generic",
    *,
    do_walk: bool = True,
) -> dict:
    """Blocking: collect SNMP system info + interface table (+ printer OIDs si aplica)."""
    snmpget  = shutil.which("snmpget")
    snmpwalk = shutil.which("snmpwalk")
    if not snmpget:
        return {"ok": False, "error": "snmpget no disponible"}

    TIMEOUT = 4
    known_version = (prev_snmp or {}).get("_snmp_ver")
    sys_out, snmp_ver = _snmp_probe_version(snmpget, ip, community, TIMEOUT, known_version)
    if not sys_out or not snmp_ver:
        return {
            "ok": False,
            "error": "SNMP no responde (timeout o comunidad incorrecta)",
            "_snmp_ver": known_version,
        }
    BASE = _snmp_cmd_base(community, TIMEOUT, snmp_ver)

    sys_descr = sys_uptime = sys_name = ""
    for line in sys_out.splitlines():
        if "=" not in line:
            continue
        lhs, rhs = line.split("=", 1)
        lhs_s = lhs.strip()
        lhs_l = lhs_s.lower()
        rhs = rhs.strip()
        # Soporta nombres simbólicos (SNMPv2-MIB::sysDescr.0) y numéricos (iso.3.6.1.2.1.1.1.0)
        if "sysdescr" in lhs_l or lhs_s.endswith(".2.1.1.1.0"):
            sys_descr = _parse_snmp_string(rhs)[:150]
        elif "sysuptime" in lhs_l or lhs_s.endswith(".2.1.1.3.0"):
            m = re.search(r'\)\s+(.+)$', rhs)
            sys_uptime = m.group(1).strip() if m else rhs
        elif "sysname" in lhs_l or lhs_s.endswith(".2.1.1.5.0"):
            sys_name = _parse_snmp_string(rhs)

    is_printer = device_type in ("printer", "pos") or _is_printer_sysdescr(sys_descr)
    uptime_key = _uptime_ticks(sys_uptime)
    cached = _snmp_iftable_cache.get(ip) or {}
    cache_fresh = (
        cached
        and (_time.time() - cached.get("ts", 0)) < SNMP_IFCACHE_SEC
        and cached.get("uptime_key") == uptime_key
        and uptime_key is not None
    )

    # Interface table — impresoras: sin walk; switches: walk solo si do_walk o cache inválida
    interfaces: list = []
    raw_octets: dict = {}
    skip_walk = is_printer or (not do_walk and cache_fresh)

    if skip_walk and cache_fresh:
        interfaces = list(cached.get("interfaces") or [])
        raw_octets = dict(cached.get("raw_octets") or {})
    elif skip_walk and prev_snmp and prev_snmp.get("interfaces"):
        interfaces = prev_snmp.get("interfaces") or []
        raw_octets = prev_snmp.get("_raw_octets") or {}
    elif snmpwalk and do_walk and not is_printer:
        walk_timeout = TIMEOUT + (20 if snmp_ver == "1" else 10)
        try:
            r_if = subprocess.run(
                [snmpwalk] + BASE + [ip, "1.3.6.1.2.1.2.2.1"],
                capture_output=True, text=True, timeout=walk_timeout,
            )
            if r_if.returncode == 0 and r_if.stdout.strip():
                interfaces, raw_octets = _parse_iftable(r_if.stdout, prev_snmp)
        except Exception:
            pass
    # Walk incompleto: conservar tabla anterior (evita flapping falso en bot/panel)
    if not interfaces and prev_snmp and prev_snmp.get("interfaces"):
        interfaces = prev_snmp.get("interfaces") or []
        raw_octets = prev_snmp.get("_raw_octets") or {}

    if interfaces and uptime_key:
        _snmp_iftable_cache[ip] = {
            "ts": _time.time(),
            "uptime_key": uptime_key,
            "num_interfaces": len(interfaces),
            "interfaces": interfaces,
            "raw_octets": raw_octets,
        }
        prev_num = (prev_snmp or {}).get("_num_interfaces")
        if (
            prev_num is not None
            and prev_num != len(interfaces)
            and cache_fresh
        ):
            pass  # num_interfaces cambió — ya guardamos cache nueva arriba

    result = {
        "ok": True,
        "sys_descr": sys_descr,
        "sys_uptime": sys_uptime,
        "sys_name": sys_name,
        "_snmp_ver": snmp_ver,
        "interfaces": interfaces,
        "_raw_octets": raw_octets,
        "_num_interfaces": len(interfaces),
        "_last_walk_at": _time.time() if (do_walk and not is_printer and interfaces) else (
            (prev_snmp or {}).get("_last_walk_at")
        ),
        "_raw_ts": _time.time(),
        "polled_at": datetime.now(timezone.utc).isoformat(),
    }

    # Impresora: tóner + walk de todas las bandejas (prtInput)
    if is_printer and snmpget:
        pr_data = _poll_printer_snmp(snmpget, snmpwalk, BASE, ip, TIMEOUT)
        if pr_data:
            result["printer"] = pr_data

    return result


async def _noop() -> None:
    return None


# ──────────────────────────────────────────────
# Telegram alert
# ──────────────────────────────────────────────

async def _send_infra_alert(
    name: str, ip: str, status: str, prev_status: str,
    duration_sec: Optional[float], device_type: str = "generic",
):
    redis = get_redis()
    ck = f"infra_alert_cooldown:{ip}"
    if redis and redis.get(ck):
        return

    is_printer = device_type in ("printer", "pos")

    try:
        from app.scripts.alerts import send_telegram_alert
        if status == "offline":
            if is_printer:
                msg = (
                    f"🖨️ <b>IMPRESORA FUERA DE LÍNEA</b>\n"
                    f"Equipo: <b>{name}</b>\n"
                    f"IP: <code>{ip}</code>\n"
                    f"⚠️ Verificar: alimentación, cable de red, papel."
                )
            else:
                msg = (
                    f"🔴 <b>INFRA — DISPOSITIVO CAÍDO</b>\n"
                    f"Equipo: <b>{name}</b>\n"
                    f"IP: <code>{ip}</code>"
                )
        else:
            dur = ""
            if duration_sec and duration_sec > 0:
                m, s = int(duration_sec // 60), int(duration_sec % 60)
                dur = f"\nEstuvo offline: {m}m {s}s" if m else f"\nEstuvo offline: {s}s"
            if is_printer:
                msg = (
                    f"🖨️ <b>IMPRESORA RECUPERADA</b>\n"
                    f"Equipo: <b>{name}</b>\n"
                    f"IP: <code>{ip}</code>{dur}"
                )
            else:
                msg = (
                    f"🟢 <b>INFRA — DISPOSITIVO RECUPERADO</b>\n"
                    f"Equipo: <b>{name}</b>\n"
                    f"IP: <code>{ip}</code>{dur}"
                )
        sent = await asyncio.to_thread(send_telegram_alert, msg)
        if sent and redis:
            redis.setex(ck, ALERT_COOLDOWN_SEC, "1")
    except Exception as e:
        logger.error("infra alert error: %s", e)


# ──────────────────────────────────────────────
# Uptime 24h calculation
# ──────────────────────────────────────────────

def _calc_uptime_24h_batch(conn, ips: list, status_map: dict) -> dict:
    """2 queries para todos los IPs; devuelve {ip: uptime_pct}. Evita N×2 queries en /infra/devices."""
    if not ips:
        return {}
    ph = ",".join("?" * len(ips))
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=24)
    rows_in = conn.execute(
        f"SELECT ip, event, ts FROM infra_events WHERE ip IN ({ph}) "
        f"AND ts >= datetime('now','-24 hours') ORDER BY ip, ts",
        ips,
    ).fetchall()
    prev_rows = conn.execute(
        f"""SELECT ip, event FROM infra_events ie
            WHERE ip IN ({ph})
              AND ts = (SELECT max(ts) FROM infra_events WHERE ip=ie.ip
                        AND ts < datetime('now','-24 hours'))""",
        ips,
    ).fetchall()
    events_by_ip: dict = {}
    for r in rows_in:
        events_by_ip.setdefault(r["ip"], []).append(r)
    prev_by_ip = {r["ip"]: r["event"] for r in prev_rows}
    result: dict = {}
    for ip in ips:
        current_status = (status_map.get(ip) or {}).get("status", "unknown")
        events = events_by_ip.get(ip, [])
        if not events:
            result[ip] = 100.0 if current_status == "online" else 0.0
            continue
        initial = prev_by_ip.get(ip) or ("offline" if events[0]["event"] == "online" else "online")
        online_secs = 0.0
        cur_st = initial
        cur_time = window_start
        for row in events:
            try:
                ts = datetime.fromisoformat(row["ts"]).replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if cur_st == "online":
                online_secs += (ts - cur_time).total_seconds()
            cur_time = ts
            cur_st = row["event"]
        if cur_st == "online":
            online_secs += (now - cur_time).total_seconds()
        total = (now - window_start).total_seconds()
        result[ip] = round(min(100.0, online_secs / total * 100), 1) if total > 0 else None
    return result


def _calc_uptime_24h(conn, ip: str, current_status: str) -> Optional[float]:
    rows = conn.execute(
        "SELECT event, ts FROM infra_events WHERE ip=? AND ts >= datetime('now','-24 hours') ORDER BY ts",
        (ip,)
    ).fetchall()

    if not rows:
        # No events → device has been in current state the whole time
        return 100.0 if current_status == "online" else 0.0

    prev = conn.execute(
        "SELECT event FROM infra_events WHERE ip=? AND ts < datetime('now','-24 hours') ORDER BY ts DESC LIMIT 1",
        (ip,)
    ).fetchone()

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=24)

    # Determine state at window start
    if prev:
        initial = prev["event"]
    else:
        # Infer: first event in window is a transition TO that state, so before = opposite
        initial = "offline" if rows[0]["event"] == "online" else "online"

    online_secs = 0.0
    cur_status = initial
    cur_time = window_start

    for row in rows:
        try:
            ts = datetime.fromisoformat(row["ts"]).replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if cur_status == "online":
            online_secs += (ts - cur_time).total_seconds()
        cur_time = ts
        cur_status = row["event"]

    if cur_status == "online":
        online_secs += (now - cur_time).total_seconds()

    total = (now - window_start).total_seconds()
    return round(min(100.0, online_secs / total * 100), 1) if total > 0 else None


# ──────────────────────────────────────────────
# Poller
# ──────────────────────────────────────────────

def _get_redis_poll_client():
    """Cliente Redis para el ciclo de persistencia (socket_timeout acotado)."""
    if not REDIS_AVAILABLE or redis_lib is None:
        return None
    try:
        r = redis_lib.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=3,
        )
        r.ping()
        return r
    except Exception:
        return None


def _load_poll_context() -> Tuple[List[dict], Dict[str, dict]]:
    """Lectura SQLite inicial del ciclo (sync — invocar vía asyncio.to_thread)."""
    with get_db() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT ip, name, device_type, tcp_port, snmp_community, monitor_profile "
                "FROM infra_devices WHERE active = 1"
            ).fetchall()
        ]
        existing = {
            r["ip"]: dict(r)
            for r in conn.execute(
                "SELECT ip, status, last_state_change, snmp_data, checked_at "
                "FROM infra_status"
            ).fetchall()
        }
    return rows, existing


def _persist_poll_results(
    rows: List[dict],
    ping_results: list,
    tcp_ok_by_ip: Dict[str, Optional[int]],
    mac_res: Dict[str, Optional[str]],
    snmp_map: dict,
    existing: Dict[str, dict],
    host_network_blip: bool,
    newly_offline_ips: set,
    batch_id: str,
    now_utc: datetime,
) -> Dict[str, Any]:
    """Escritura SQLite + Redis del ciclo (sync — invocar vía asyncio.to_thread).

    Fase 1: calcula filas en memoria. Fase 2: una transacción SQLite + commit.
    Fase 3: pipeline Redis (después del commit).
    """
    wan_snapshot, maintenance = _context_snapshots()
    ttl = POLL_INTERVAL_SEC * 4
    checked_at = now_utc.isoformat()

    pending_rows: List[dict] = []
    telegram_alerts: List[dict] = []
    pulse_events: List[dict] = []
    pulse_cfg = pulse_config() if pulse_enabled() else None

    for row, ping_r in zip(rows, ping_results):
        ip = row["ip"]
        name = row["name"]
        profile = row.get("monitor_profile") or resolve_monitor_profile(
            row.get("device_type") or "generic",
            row.get("tcp_port"),
            row.get("snmp_community"),
            row.get("monitor_profile"),
        )

        if profile == "ap_guardian":
            continue

        if host_network_blip and ip in newly_offline_ips:
            continue

        tcp_ok = tcp_ok_by_ip.get(ip)
        prev = existing.get(ip)

        if ping_r is None:
            continue

        status, latency, loss_pct = derive_liveness(
            profile, ping_r, tcp_ok, prev,
        )

        mac = mac_res.get(ip)
        prev_status = prev.get("status") if prev else None
        last_change_str = prev.get("last_state_change") if prev else None

        snmp_res = snmp_map.get(ip)
        snmp_res = _merge_snmp_interfaces(snmp_res, existing, ip)
        snmp_data_json = json.dumps(snmp_res) if snmp_res is not None else None
        snmp_ok_val = (
            1 if (snmp_res and snmp_res.get("ok")) else (0 if snmp_res is not None else None)
        )

        duration_sec = None
        infra_event = None
        if prev_status is not None and prev_status != status:
            last_change = now_utc.isoformat()
            if last_change_str:
                try:
                    prev_ts = datetime.fromisoformat(last_change_str).replace(tzinfo=timezone.utc)
                    duration_sec = (now_utc - prev_ts).total_seconds()
                except Exception:
                    pass

            device_type = row.get("device_type") or "generic"
            infra_event = {"ip": ip, "event": status, "record_status": None}
            if device_type != "ap":
                lat_int = int(round(latency)) if latency is not None else None
                if status == "offline":
                    if profile == "endpoint_tcp":
                        infra_reason = "puerto TCP sin respuesta"
                    elif profile == "network_gear":
                        infra_reason = "sin respuesta (ping/SNMP)"
                    else:
                        infra_reason = "sin respuesta ping (100% pérdida)"
                elif status == "degraded":
                    infra_reason = f"pérdida de paquetes {loss_pct:.0f}%"
                elif profile == "network_gear":
                    infra_reason = "SNMP OK"
                elif profile == "endpoint_tcp":
                    infra_reason = "puerto TCP OK"
                else:
                    infra_reason = "ping OK"
                infra_event["record_status"] = {
                    "source": "infra",
                    "ip": ip,
                    "name": name,
                    "device_type": device_type,
                    "prev_status": prev_status,
                    "status": status,
                    "reason": infra_reason,
                    "latency_ms": lat_int,
                    "loss_pct": loss_pct,
                    "batch_id": batch_id,
                    "wan_snapshot": wan_snapshot,
                    "maintenance": maintenance,
                }
                is_real_outage_edge = status == "offline" or prev_status == "offline"
                if is_real_outage_edge and os.environ.get("INFRA_TELEGRAM_PANEL", "0").strip() == "1":
                    telegram_alerts.append({
                        "name": name,
                        "ip": ip,
                        "status": status,
                        "prev_status": prev_status,
                        "duration_sec": duration_sec,
                        "device_type": device_type,
                    })
        else:
            last_change = last_change_str or now_utc.isoformat()

        pending_rows.append({
            "ip": ip,
            "name": name,
            "status": status,
            "latency": latency,
            "loss_pct": loss_pct,
            "tcp_ok": tcp_ok,
            "mac": mac,
            "last_change": last_change,
            "snmp_data_json": snmp_data_json,
            "snmp_ok_val": snmp_ok_val,
            "infra_event": infra_event,
            "redis_payload": {
                "status": status,
                "latency_ms": latency,
                "loss_pct": loss_pct,
                "tcp_ok": tcp_ok,
                "mac": mac,
                "snmp_ok": snmp_ok_val,
                "checked_at": checked_at,
            },
        })

    devices_written = 0
    with get_db() as conn:
        ensure_pulse_table(conn)
        for pr in pending_rows:
            if pulse_cfg:
                skip_blip = host_network_blip and pr["ip"] in newly_offline_ips
                pulse_snap = update_pulse(
                    conn,
                    ip=pr["ip"],
                    name=pr.get("name") or pr["ip"],
                    latency_ms=pr["latency"],
                    loss_pct=float(pr["loss_pct"] or 0),
                    status=pr["status"],
                    host_network_blip=skip_blip,
                    now_iso=checked_at,
                    cfg=pulse_cfg,
                )
                pr["pulse"] = pulse_snap
                if pulse_snap.get("transition") == "enter_degrading":
                    pulse_events.append(pulse_snap)
                    conn.execute(
                        "INSERT INTO infra_events (ip, event) VALUES (?, ?)",
                        (pr["ip"], "pulse_degrading"),
                    )
                elif pulse_snap.get("transition") == "exit_degrading":
                    conn.execute(
                        "INSERT INTO infra_events (ip, event) VALUES (?, ?)",
                        (pr["ip"], "pulse_recovered"),
                    )
            if pr.get("infra_event"):
                ev = pr["infra_event"]
                conn.execute(
                    "INSERT INTO infra_events (ip, event) VALUES (?,?)",
                    (ev["ip"], ev["event"]),
                )
                rs = ev.get("record_status")
                if rs:
                    record_status_event(conn=conn, **rs)
            conn.execute(
                """
                INSERT INTO infra_status
                    (ip, status, latency_ms, loss_pct, tcp_ok, mac, last_state_change,
                     snmp_data, snmp_ok, checked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(ip) DO UPDATE SET
                    status=excluded.status,
                    latency_ms=excluded.latency_ms,
                    loss_pct=excluded.loss_pct,
                    tcp_ok=excluded.tcp_ok,
                    mac=COALESCE(excluded.mac, infra_status.mac),
                    last_state_change=excluded.last_state_change,
                    snmp_data=COALESCE(excluded.snmp_data, infra_status.snmp_data),
                    snmp_ok=COALESCE(excluded.snmp_ok, infra_status.snmp_ok),
                    checked_at=excluded.checked_at
                """,
                (
                    pr["ip"], pr["status"], pr["latency"], pr["loss_pct"], pr["tcp_ok"],
                    pr["mac"], pr["last_change"], pr["snmp_data_json"], pr["snmp_ok_val"],
                ),
            )
            devices_written += 1
        conn.commit()

    redis = _get_redis_poll_client()
    if redis and pending_rows:
        try:
            pipe = redis.pipeline()
            for pr in pending_rows:
                ip = pr["ip"]
                pipe.setex(f"infra:{ip}:status", ttl, pr["status"])
                if pr["latency"] is not None:
                    pipe.setex(f"infra:{ip}:latency", ttl, str(pr["latency"]))
                pr["redis_payload"]["pulse"] = pr.get("pulse") or {}
                pipe.setex(
                    f"infra:{ip}:data", ttl, json.dumps(pr["redis_payload"]),
                )
                pulse_st = pr.get("pulse") or {}
                if pulse_st.get("enabled"):
                    pipe.setex(f"infra:{ip}:pulse", ttl, json.dumps(pulse_st))
            pipe.execute()
            try:
                redis.setex("infra:poller:last_ok", ttl, checked_at)
            except Exception:
                pass
        except Exception as e:
            logger.error(
                "infra poll: Redis pipeline failed batch_id=%s devices=%d: %s",
                batch_id, devices_written, e,
            )

    return {"telegram_alerts": telegram_alerts, "devices_written": devices_written}


def _merge_snmp_interfaces(snmp_res: Optional[dict], existing: Dict[str, dict], ip: str) -> Optional[dict]:
    """Conserva ifTable cacheado si un poll get-only no trajo interfaces."""
    if not snmp_res or not snmp_res.get("ok"):
        return snmp_res
    if snmp_res.get("interfaces"):
        return snmp_res
    prev_row = existing.get(ip) or {}
    if not prev_row.get("snmp_data"):
        return snmp_res
    try:
        prev_snmp = json.loads(prev_row["snmp_data"])
        if prev_snmp.get("interfaces"):
            return {
                **snmp_res,
                "interfaces": prev_snmp["interfaces"],
                "_raw_octets": prev_snmp.get("_raw_octets", {}),
            }
    except Exception:
        pass
    return snmp_res


def _persist_snmp_results(snmp_map: dict, existing: Dict[str, dict]) -> int:
    """Actualiza solo columnas SNMP (sync — invocar vía asyncio.to_thread)."""
    if not snmp_map:
        return 0
    checked_at = datetime.now(timezone.utc).isoformat()
    ttl = FAST_POLL_INTERVAL_SEC * 4
    updates: List[tuple] = []

    for ip, snmp_res in snmp_map.items():
        snmp_res = _merge_snmp_interfaces(snmp_res, existing, ip)
        snmp_data_json = json.dumps(snmp_res) if snmp_res is not None else None
        snmp_ok_val = (
            1 if (snmp_res and snmp_res.get("ok")) else (0 if snmp_res is not None else None)
        )
        updates.append((snmp_data_json, snmp_ok_val, ip))

    with get_db() as conn:
        for snmp_data_json, snmp_ok_val, ip in updates:
            conn.execute(
                """
                UPDATE infra_status
                SET snmp_data=?, snmp_ok=?, checked_at=datetime('now')
                WHERE ip=?
                """,
                (snmp_data_json, snmp_ok_val, ip),
            )
        conn.commit()

    written = len(updates)

    redis = _get_redis_poll_client()
    if redis:
        try:
            pipe = redis.pipeline()
            for snmp_data_json, snmp_ok_val, ip in updates:
                key = f"infra:{ip}:data"
                raw = redis.get(key)
                payload: dict = {}
                if raw:
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        payload = {}
                payload["snmp_ok"] = snmp_ok_val
                payload["checked_at"] = checked_at
                pipe.setex(key, ttl, json.dumps(payload))
            pipe.execute()
            redis.setex("infra:poller:last_snmp_ok", ttl, checked_at)
        except Exception as e:
            logger.error("infra poll snmp: Redis pipeline failed: %s", e)

    return len(updates)


async def _collect_snmp_map(rows: List[dict], existing: Dict[str, dict]) -> tuple[dict, int]:
    """Ejecuta polls SNMP en paralelo; retorna (snmp_map, snmp_ms)."""
    t_snmp = _time.monotonic()
    snmp_map: dict = {}
    snmp_tasks_list = []
    snmp_ips_list = []
    now_ts = _time.time()

    async def _snmp_with_sem(ip: str, community: str, prev_snmp, device_type: str) -> dict:
        prev_snmp = prev_snmp or {}
        fail_streak = prev_snmp.get("_snmp_fail_streak") or 0
        last_attempt = prev_snmp.get("_snmp_last_attempt_at") or 0
        if (
            fail_streak >= SNMP_FAIL_BACKOFF_THRESHOLD
            and (now_ts - last_attempt) < SNMP_FAIL_BACKOFF_SEC
        ):
            return prev_snmp

        last_walk = prev_snmp.get("_last_walk_at") or 0
        do_walk = (now_ts - last_walk) >= SNMP_WALK_INTERVAL_SEC
        async with SNMP_SEM:
            result = await _run_in_snmp_executor(
                _snmp_poll, ip, community, prev_snmp, device_type, do_walk=do_walk,
            )
        result["_snmp_last_attempt_at"] = now_ts
        result["_snmp_fail_streak"] = 0 if result.get("ok") else fail_streak + 1
        return result

    for row in rows:
        community = (row.get("snmp_community") or "").strip()
        if not community:
            continue
        prev_snmp = None
        prev = existing.get(row["ip"])
        if prev and prev.get("snmp_data"):
            try:
                prev_snmp = json.loads(prev["snmp_data"])
            except Exception:
                pass
        dt = row.get("device_type") or "generic"
        snmp_tasks_list.append(
            _snmp_with_sem(row["ip"], community, prev_snmp, dt)
        )
        snmp_ips_list.append(row["ip"])
    if snmp_tasks_list:
        snmp_vals = await asyncio.gather(*snmp_tasks_list, return_exceptions=True)
        for sip, sval in zip(snmp_ips_list, snmp_vals):
            snmp_map[sip] = (
                sval if not isinstance(sval, Exception) else {"ok": False, "error": str(sval)}
            )
    snmp_ms = int((_time.monotonic() - t_snmp) * 1000)
    return snmp_map, snmp_ms


async def _poll_fast_once():
    t_total = _time.monotonic()

    try:
        rows, existing = await asyncio.to_thread(_load_poll_context)
    except Exception as e:
        logger.error("infra poll fast: DB read error: %s", e)
        return

    if not rows:
        return

    rows = [enrich_device_row(r) for r in rows]
    await asyncio.to_thread(_sync_ap_status_from_guardian)

    poll_rows = [r for r in rows if r.get("monitor_profile") != "ap_guardian"]
    ping_results_full: List[Any] = []
    ping_by_ip: Dict[str, Any] = {}

    read_ms = int((_time.monotonic() - t_total) * 1000)
    now_utc = datetime.now(timezone.utc)
    batch_id = f"i-{int(now_utc.timestamp())}"

    t_ping = _time.monotonic()
    if poll_rows:
        ping_tasks = [
            asyncio.to_thread(
                _ping,
                r["ip"],
                ping_count_for_profile(r["monitor_profile"], PING_COUNT),
            )
            for r in poll_rows
        ]
        ping_gathered = await asyncio.gather(*ping_tasks, return_exceptions=True)
        ping_by_ip = {r["ip"]: pr for r, pr in zip(poll_rows, ping_gathered)}

    for row in rows:
        if row.get("monitor_profile") == "ap_guardian":
            ping_results_full.append(None)
        else:
            ping_results_full.append(ping_by_ip.get(row["ip"], Exception("sin ping")))

    cycle_status = {
        row["ip"]: (
            "offline"
            if isinstance(ping_by_ip.get(row["ip"]), Exception)
            else ping_by_ip.get(row["ip"], ("unknown", None, 0.0))[0]
        )
        for row in poll_rows
    }
    existing_status = {
        ip: (existing.get(ip) or {}).get("status") or "unknown"
        for ip in cycle_status
    }
    gateway_ip = (await asyncio.to_thread(get_config, "base.gateway") or "").strip()

    async def _gw_ping():
        if not gateway_ip:
            return "online", 0.0, None
        # _ping() devuelve (status, latency_ms, loss_pct) -- el contrato compartido
        # de shomer_network_blip.py espera (status, loss_pct, rtt_ms), igual que
        # Guardian (_gw_ping_triplet). Reordenar aquí, no en el módulo compartido.
        status, latency_ms, loss_pct = await asyncio.to_thread(_ping, gateway_ip)
        return status, loss_pct, latency_ms

    host_network_blip, newly_offline_ips = await evaluate_host_network_blip_async(
        gateway_ip,
        _gw_ping,
        cycle_status,
        existing_status,
        len(poll_rows),
        log_prefix="infra poll",
        batch_id=batch_id,
    )

    tcp_ok_by_ip: Dict[str, Optional[int]] = {}
    tcp_jobs: List[tuple] = []
    for row in poll_rows:
        ip = row["ip"]
        port = row.get("tcp_port")
        if not port:
            continue
        profile = row.get("monitor_profile") or "generic"
        pr = ping_by_ip.get(ip)
        if profile == "endpoint_tcp":
            tcp_jobs.append((ip, asyncio.to_thread(_tcp_check, ip, port)))
        elif not isinstance(pr, Exception) and pr[0] in ("online", "degraded"):
            tcp_jobs.append((ip, asyncio.to_thread(_tcp_check, ip, port)))
    if tcp_jobs:
        tcp_vals = await asyncio.gather(
            *[job for _, job in tcp_jobs], return_exceptions=True,
        )
        for (ip, _), tcp_r in zip(tcp_jobs, tcp_vals):
            if isinstance(tcp_r, Exception):
                tcp_ok_by_ip[ip] = None
            else:
                tcp_ok_by_ip[ip] = 1 if tcp_r else 0

    ping_ms = int((_time.monotonic() - t_ping) * 1000)

    t_mac = _time.monotonic()
    mac_ips = [
        r["ip"] for r in poll_rows
        if not isinstance(ping_by_ip.get(r["ip"]), Exception)
        and ping_by_ip.get(r["ip"], ("offline",))[0] in ("online", "degraded")
    ]
    mac_res: Dict[str, Optional[str]] = {}
    if mac_ips:
        mac_vals = await asyncio.gather(
            *[asyncio.to_thread(_get_mac, ip) for ip in mac_ips],
            return_exceptions=True,
        )
        mac_res = {
            ip: (v if not isinstance(v, Exception) else None)
            for ip, v in zip(mac_ips, mac_vals)
        }
    mac_ms = int((_time.monotonic() - t_mac) * 1000)

    t_write = _time.monotonic()
    devices_written = 0
    try:
        persist_result = await asyncio.to_thread(
            _persist_poll_results,
            rows,
            ping_results_full,
            tcp_ok_by_ip,
            mac_res,
            {},  # SNMP en capa lenta (_poll_snmp_once)
            existing,
            host_network_blip,
            newly_offline_ips,
            batch_id,
            now_utc,
        )
        devices_written = persist_result.get("devices_written", 0)
        for alert in persist_result.get("telegram_alerts", []):
            asyncio.create_task(_send_infra_alert(**alert))
        try:
            rctx = _get_redis_poll_client()
            gw_st = cycle_status.get(gateway_ip, "unknown") if gateway_ip else ""
            write_poll_context(
                rctx,
                batch_id=batch_id,
                host_network_blip=host_network_blip,
                offline_count=sum(1 for s in cycle_status.values() if s == "offline"),
                total_devices=len(poll_rows),
                gateway_ip=gateway_ip,
                gateway_status=gw_st,
                blip_skip_count=len(newly_offline_ips),
                pulse_events=pulse_events,
            )
        except Exception as e:
            logger.debug("pulse correlate context: %s", e)
    except Exception as e:
        logger.error(
            "infra poll: persist failed batch_id=%s devices=%d: %s",
            batch_id, len(poll_rows), e,
            exc_info=True,
        )
        try:
            rerr = _get_redis_poll_client()
            if rerr:
                rerr.setex(
                    "infra:poller:last_error",
                    300,
                    json.dumps({
                        "ts": now_utc.isoformat(),
                        "batch_id": batch_id,
                        "error": str(e)[:500],
                    }),
                )
        except Exception:
            pass
        write_ms = int((_time.monotonic() - t_write) * 1000)
        total_ms = int((_time.monotonic() - t_total) * 1000)
        logger.info(
            "infra poll fast: read=%dms ping=%dms mac=%dms write=%dms "
            "total=%dms devices=%d (persist error)",
            read_ms, ping_ms, mac_ms, write_ms, total_ms, len(rows),
        )
        return

    write_ms = int((_time.monotonic() - t_write) * 1000)
    total_ms = int((_time.monotonic() - t_total) * 1000)
    logger.info(
        "infra poll fast: read=%dms ping=%dms mac=%dms write=%dms "
        "total=%dms devices=%d polled=%d",
        read_ms, ping_ms, mac_ms, write_ms, total_ms, devices_written, len(poll_rows),
    )
    if total_ms > FAST_POLL_INTERVAL_SEC * 1000:
        logger.warning(
            "infra poll fast: ciclo lento read=%dms ping=%dms mac=%dms "
            "write=%dms total=%dms devices=%d (umbral %ds)",
            read_ms, ping_ms, mac_ms, write_ms, total_ms,
            devices_written, FAST_POLL_INTERVAL_SEC,
        )


async def _poll_snmp_once():
    t_total = _time.monotonic()
    try:
        rows, existing = await asyncio.to_thread(_load_poll_context)
    except Exception as e:
        logger.error("infra poll snmp: DB read error: %s", e)
        return

    snmp_rows = [r for r in rows if (r.get("snmp_community") or "").strip()]
    if not snmp_rows:
        return

    read_ms = int((_time.monotonic() - t_total) * 1000)
    snmp_map, snmp_ms = await _collect_snmp_map(snmp_rows, existing)

    t_write = _time.monotonic()
    try:
        devices_written = await asyncio.to_thread(_persist_snmp_results, snmp_map, existing)
    except Exception as e:
        logger.error("infra poll snmp: persist failed devices=%d: %s", len(snmp_map), e)
        write_ms = int((_time.monotonic() - t_write) * 1000)
        total_ms = int((_time.monotonic() - t_total) * 1000)
        logger.info(
            "infra poll snmp: read=%dms snmp=%dms write=%dms total=%dms devices=%d (persist error)",
            read_ms, snmp_ms, write_ms, total_ms, len(snmp_map),
        )
        return

    write_ms = int((_time.monotonic() - t_write) * 1000)
    total_ms = int((_time.monotonic() - t_total) * 1000)
    logger.info(
        "infra poll snmp: read=%dms snmp=%dms write=%dms total=%dms devices=%d",
        read_ms, snmp_ms, write_ms, total_ms, devices_written,
    )


async def _poll_once():
    """Compat: ciclo completo legacy = solo capa rápida (SNMP va en _poll_snmp_once)."""
    await _poll_fast_once()


async def _poller_loop():
    global _poller_running
    _init_tables()
    loop = asyncio.get_event_loop()
    stop = asyncio.Event()

    async def _fast_loop():
        while not stop.is_set():
            t0 = loop.time()
            try:
                _sync_guardian_aps()
                await _poll_fast_once()
            except Exception as e:
                logger.error("infra poller fast error: %s", e)
            elapsed = loop.time() - t0
            await asyncio.sleep(max(0.1, FAST_POLL_INTERVAL_SEC - elapsed))

    async def _snmp_loop():
        while not stop.is_set():
            try:
                await _poll_snmp_once()
            except Exception as e:
                logger.error("infra poller snmp error: %s", e)
            await asyncio.sleep(max(1.0, SNMP_POLL_INTERVAL_SEC))

    await asyncio.gather(_fast_loop(), _snmp_loop())


def start_inframonitor_poller():
    global _poller_running
    if _poller_running:
        return
    _poller_running = True
    asyncio.create_task(_poller_loop())
    logger.info(
        "Inframonitor poller iniciado (fast=%ss snmp=%ss)",
        FAST_POLL_INTERVAL_SEC, SNMP_POLL_INTERVAL_SEC,
    )


# ──────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────

class DeviceIn(BaseModel):
    ip: str
    name: str
    device_type: str = "generic"
    location: str = ""
    tcp_port: Optional[int] = None
    snmp_community: str = "public"
    pc_server_ip: Optional[str] = None


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _fmt_duration(last_change_str: Optional[str]) -> Optional[str]:
    if not last_change_str:
        return None
    try:
        ts = datetime.fromisoformat(last_change_str).replace(tzinfo=timezone.utc)
        secs = int((datetime.now(timezone.utc) - ts).total_seconds())
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60}m {secs % 60}s"
        h = secs // 3600
        m = (secs % 3600) // 60
        return f"{h}h {m}m"
    except Exception:
        return None


def _snmp_down_port_names(snmp_data_raw) -> list:
    """Puertos ifOperStatus=down desde snmp_data cacheado (sin poll extra)."""
    if not snmp_data_raw:
        return []
    try:
        snmp = json.loads(snmp_data_raw) if isinstance(snmp_data_raw, str) else snmp_data_raw
    except Exception:
        return []
    names = []
    for iface in snmp.get("interfaces", []):
        if iface.get("oper") != "down":
            continue
        name = (iface.get("name") or "").strip()
        if not name or name.lower() in ("lo", "loopback"):
            continue
        names.append(name)
    return names


def _snmp_up_port_names(snmp_data_raw) -> list:
    """Puertos ifOperStatus=up desde snmp_data cacheado."""
    if not snmp_data_raw:
        return []
    try:
        snmp = json.loads(snmp_data_raw) if isinstance(snmp_data_raw, str) else snmp_data_raw
    except Exception:
        return []
    names = []
    for iface in snmp.get("interfaces", []):
        if iface.get("oper") != "up":
            continue
        name = (iface.get("name") or "").strip()
        if not name or name.lower() in ("lo", "loopback"):
            continue
        names.append(name)
    return names


def _build_device_row(
    d, s, uptime: Optional[float], outages_today: int = 0,
    pulse: Optional[dict] = None,
) -> dict:
    row = {
        "id": d["id"],
        "ip": d["ip"],
        "name": d["name"],
        "device_type": d["device_type"],
        "icon": DEVICE_ICONS.get(d["device_type"], "📡"),
        "location": d["location"],
        "tcp_port": d["tcp_port"],
        "snmp_community": d["snmp_community"] if "snmp_community" in d.keys() else "public",
        "pc_server_ip": d["pc_server_ip"] if "pc_server_ip" in d.keys() else None,
        "status": s["status"] if s else "unknown",
        "latency_ms": s["latency_ms"] if s else None,
        "loss_pct": s["loss_pct"] if (s and "loss_pct" in s.keys()) else None,
        "tcp_ok": s["tcp_ok"] if s else None,
        "mac": s["mac"] if s else None,
        "snmp_ok": s["snmp_ok"] if s else None,
        "uptime_24h": uptime,
        "outages_today": outages_today,
        "state_duration": _fmt_duration(s["last_state_change"] if s else None),
        "checked_at": (s["checked_at"] if s else None),
        "created_at": d["created_at"],
    }
    mp = d["monitor_profile"] if "monitor_profile" in d.keys() else None
    row["monitor_profile"] = resolve_monitor_profile(
        d["device_type"],
        d["tcp_port"],
        d["snmp_community"] if "snmp_community" in d.keys() else None,
        mp,
    )
    # Para impresoras: incluir datos de tóner/papel/estado directamente en la fila
    if s and s.get("snmp_data"):
        try:
            snmp = json.loads(s["snmp_data"])
            if d["device_type"] in ("printer", "pos") and snmp.get("printer"):
                row["printer"] = snmp["printer"]
            if d["device_type"] in (
                "switch", "router", "server", "nas", "controller", "generic",
            ):
                down = _snmp_down_port_names(snmp)
                if down:
                    row["snmp_down_ports"] = down
                up = _snmp_up_port_names(snmp)
                if up:
                    row["snmp_up_ports"] = up
        except Exception:
            pass
    if pulse:
        row["pulse"] = {
            "state": pulse.get("pulse_state") or "stable",
            "ewma_latency_ms": pulse.get("ewma_latency_ms"),
            "ewma_loss_pct": pulse.get("ewma_loss_pct"),
            "baseline_latency_ms": pulse.get("baseline_latency_ms"),
            "degrade_ticks": pulse.get("degrade_ticks"),
            "updated_at": pulse.get("updated_at"),
        }
    return row


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.get("/infra/devices")
async def list_devices(user=Depends(get_current_user)):
    # _init_tables/_sync_guardian_aps escriben en SQLite (get_db timeout=10) -- si chocan con
    # otro escritor (poller, Hunter, backups) bloquean hasta 10s el event loop entero porque
    # antes corrían síncronos aquí mismo. to_thread() libera el loop mientras esperan el lock.
    await asyncio.to_thread(_init_tables)
    await asyncio.to_thread(_sync_guardian_aps)
    with get_db() as conn:
        devices = conn.execute(
            "SELECT * FROM infra_devices WHERE active = 1 ORDER BY name"
        ).fetchall()
        status_map = {
            r["ip"]: dict(r) for r in conn.execute("SELECT * FROM infra_status").fetchall()
        }
        ips = [d["ip"] for d in devices]
        uptime_map = _calc_uptime_24h_batch(conn, ips, status_map)
        outage_rows = conn.execute(
            "SELECT ip, COUNT(*) as cnt FROM infra_events "
            "WHERE event='offline' AND ts > datetime('now','-24 hours') GROUP BY ip"
        ).fetchall()
        outage_map = {r["ip"]: r["cnt"] for r in outage_rows}
        pulse_map: Dict[str, dict] = {}
        if pulse_enabled():
            pulse_map = {
                r["ip"]: dict(r)
                for r in conn.execute(
                    "SELECT ip, ewma_latency_ms, ewma_loss_pct, baseline_latency_ms, "
                    "degrade_ticks, pulse_state, last_alert_at, updated_at "
                    "FROM infra_pulse"
                ).fetchall()
            }
        result = [
            _build_device_row(
                d, status_map.get(d["ip"]), uptime_map.get(d["ip"]),
                outage_map.get(d["ip"], 0), pulse_map.get(d["ip"]),
            )
            for d in devices
        ]
        row = conn.execute(
            "SELECT COUNT(DISTINCT ip) FROM infra_status "
            "WHERE status='offline' AND checked_at > datetime('now', '-24 hours')"
        ).fetchone()
        outages_24h = row[0] if row else 0
    poll_context = {}
    last_blip = {}
    try:
        r = get_redis()
        if r:
            poll_context = read_poll_context(r)
            last_blip = read_last_blip(r)
    except Exception:
        pass
    return {
        "success": True,
        "devices": result,
        "outages_24h": outages_24h,
        "poll_context": poll_context,
        "last_blip": last_blip,
        "pulse_enabled": pulse_enabled(),
    }


@router.post("/infra/pulse/{ip}/alerted")
async def pulse_alert_ack(ip: str, user=Depends(get_current_user)):
    """Marca cooldown Telegram Pulse EWMA tras alerta enviada (multi-cliente)."""
    await asyncio.to_thread(_init_tables)
    with get_db() as conn:
        ensure_pulse_table(conn)
        mark_pulse_alerted(conn, ip)
        conn.commit()
    return {"success": True, "ip": ip}


@router.post("/infra/devices")
async def add_device(body: DeviceIn, user=Depends(get_current_user)):
    import ipaddress
    try:
        ipaddress.ip_address(body.ip)
    except ValueError:
        raise HTTPException(status_code=400, detail="IP inválida")

    if body.device_type not in DEVICE_ICONS:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Opciones: {list(DEVICE_ICONS.keys())}")

    if body.tcp_port is not None and not (1 <= body.tcp_port <= 65535):
        raise HTTPException(status_code=400, detail="Puerto TCP inválido (1-65535)")

    _init_tables()
    profile = resolve_monitor_profile(
        body.device_type,
        body.tcp_port,
        body.snmp_community or "public",
        None,
    )
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO infra_devices "
                "(ip, name, device_type, location, tcp_port, snmp_community, pc_server_ip, monitor_profile) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (body.ip, body.name, body.device_type, body.location, body.tcp_port,
                 body.snmp_community or "public", body.pc_server_ip or None, profile)
            )
            conn.commit()
        return {"success": True, "message": f"Equipo {body.ip} agregado"}
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail=f"IP {body.ip} ya registrada")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/infra/devices/{device_id}")
async def remove_device(device_id: int, user=Depends(get_current_user)):
    _init_tables()
    with get_db() as conn:
        cur = conn.execute("UPDATE infra_devices SET active = 0 WHERE id = ?", (device_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Equipo no encontrado")
    return {"success": True, "message": f"Equipo {device_id} eliminado"}


@router.get("/infra/status")
async def get_status(
    token: Optional[str] = None,
    user: Optional[dict] = Depends(_optional_user),
):
    from app.api.shomer_common import get_config
    if user is None and token is not None:
        noc_token = get_config("noc.display_token")
        if not noc_token or token != noc_token:
            raise HTTPException(status_code=403, detail="Token NOC inválido")
    elif user is None:
        raise HTTPException(status_code=401, detail="No autorizado")

    redis_conn = get_redis()
    _init_tables()
    with get_db() as conn:
        devices = conn.execute(
            "SELECT d.*, s.status, s.latency_ms, s.loss_pct, s.tcp_ok, s.mac, s.last_state_change, s.checked_at "
            "FROM infra_devices d LEFT JOIN infra_status s ON d.ip = s.ip "
            "WHERE d.active = 1 ORDER BY d.name"
        ).fetchall()
        result = []
        for d in devices:
            ip = d["ip"]
            # Redis-first: blob vivo (TTL=120s); fallback a fila SQLite del JOIN
            live = None
            if redis_conn:
                try:
                    raw = redis_conn.get(f"infra:{ip}:data")
                    if raw:
                        live = json.loads(raw)
                except Exception:
                    pass
            if live:
                st         = live.get("status", "unknown")
                latency_ms = live.get("latency_ms")
                loss_pct   = live.get("loss_pct")
                tcp_ok     = live.get("tcp_ok")
                mac        = live.get("mac")
                checked_at = live.get("checked_at")
            else:
                st         = d["status"] or "unknown"
                latency_ms = d["latency_ms"]
                loss_pct   = d["loss_pct"] if "loss_pct" in d.keys() else None
                tcp_ok     = d["tcp_ok"]
                mac        = d["mac"]
                checked_at = d["checked_at"]
            result.append({
                "ip": ip,
                "name": d["name"],
                "device_type": d["device_type"],
                "icon": DEVICE_ICONS.get(d["device_type"], "📡"),
                "location": d["location"],
                "tcp_port": d["tcp_port"],
                "status": st,
                "latency_ms": latency_ms,
                "loss_pct": loss_pct,
                "tcp_ok": tcp_ok,
                "mac": mac,
                "state_duration": _fmt_duration(d["last_state_change"]),
                "checked_at": checked_at,
            })

    online = sum(1 for d in result if d["status"] == "online")
    offline = sum(1 for d in result if d["status"] == "offline")
    return {
        "success": True,
        "summary": {"total": len(result), "online": online, "offline": offline},
        "devices": result,
    }


@router.post("/infra/ping/{ip}")
async def manual_ping(ip: str, user=Depends(get_current_user)):
    import ipaddress
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise HTTPException(status_code=400, detail="IP inválida")

    status, latency, loss_pct = await asyncio.to_thread(_ping, ip)
    return {"ip": ip, "status": status, "latency_ms": latency, "loss_pct": loss_pct}


@router.get("/infra/snmp/{ip}")
async def get_snmp_data(ip: str, user=Depends(get_current_user)):
    import ipaddress
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise HTTPException(status_code=400, detail="IP inválida")

    _init_tables()
    with get_db() as conn:
        row = conn.execute(
            "SELECT snmp_data, snmp_ok FROM infra_status WHERE ip=?", (ip,)
        ).fetchone()
        dev = conn.execute(
            "SELECT name, device_type, snmp_community, snmp_community_write FROM infra_devices WHERE ip=? AND active=1", (ip,)
        ).fetchone()

    if not row or row["snmp_data"] is None:
        raise HTTPException(status_code=404, detail="Sin datos SNMP — equipo aún no escaneado o sin comunidad SNMP configurada")

    try:
        data = json.loads(row["snmp_data"])
    except Exception:
        raise HTTPException(status_code=500, detail="Error al parsear datos SNMP")

    clean = {k: v for k, v in data.items() if not k.startswith("_")}
    return {
        "success": True,
        "ip": ip,
        "name": dev["name"] if dev else ip,
        "snmp_ok": row["snmp_ok"],
        "data": clean,
    }


@router.post("/infra/action/{device_id}")
async def device_action(device_id: int, payload: dict, user=Depends(get_current_user)):
    """Acciones remotas por tipo de equipo.

    action=clear_queue  → limpiar cola de impresión vía SSH al PC asociado (printer/pos)
    action=snmp_reboot  → reiniciar equipo vía SNMP SET (AP/switch con SNMP write)
    action=stream_url   → devuelve URL de stream RTSP de la cámara
    """
    action = (payload.get("action") or "").strip()
    if not action:
        raise HTTPException(status_code=400, detail="Falta campo 'action'")

    _init_tables()
    with get_db() as conn:
        dev = conn.execute(
            "SELECT * FROM infra_devices WHERE id=? AND active=1", (device_id,)
        ).fetchone()

    if not dev:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")

    dev = dict(dev)
    ip = dev["ip"]
    dtype = dev.get("device_type", "generic")

    # ── Limpiar cola de impresión ────────────────────────────────────────────
    if action == "clear_queue":
        if dtype not in ("printer", "pos"):
            raise HTTPException(status_code=400, detail="Solo disponible para impresoras")
        pc_ip = (dev.get("pc_server_ip") or "").strip()
        if not pc_ip:
            raise HTTPException(
                status_code=400,
                detail="PC asociado no configurado. Edita el equipo y agrega la IP del servidor de impresión.",
            )
        # Obtener credenciales del PC desde Tracker (base.service_user/password)
        with get_db() as conn:
            svc_user = (conn.execute(
                "SELECT value FROM system_state WHERE key='base.service_user'"
            ).fetchone() or {}).get("value", "") or "shomer"
            svc_pass = (conn.execute(
                "SELECT value FROM system_state WHERE key='base.service_password'"
            ).fetchone() or {}).get("value", "") or ""

        try:
            import asyncssh
            async with asyncssh.connect(
                pc_ip, username=svc_user, password=svc_pass,
                known_hosts=None, connect_timeout=10
            ) as conn_ssh:
                result = await conn_ssh.run(
                    "net stop spooler && del /Q /F /S \"C:\\Windows\\System32\\spool\\PRINTERS\\*\" && net start spooler",
                    timeout=30,
                )
            return {
                "success": True,
                "message": f"Cola de impresión limpiada en {pc_ip}",
                "output": (result.stdout or "")[:500],
            }
        except Exception as ex:
            logger.warning("clear_queue %s → %s: %s", ip, pc_ip, ex)
            raise HTTPException(status_code=502, detail=f"Error SSH a {pc_ip}: {ex}") from ex

    # ── Reinicio SNMP ────────────────────────────────────────────────────────
    elif action == "snmp_reboot":
        community_write = (dev.get("snmp_community_write") or "").strip() or (dev.get("snmp_community") or "public")
        # TP-Link EAP reboot OID
        reboot_oid = "1.3.6.1.4.1.11863.10.1.2.1.0"
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["snmpset", "-v2c", "-c", community_write, ip, reboot_oid, "i", "1"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return {"success": True, "message": f"Reinicio SNMP enviado a {ip}"}
            raise HTTPException(status_code=502, detail=f"snmpset error: {result.stderr[:200]}")
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Timeout enviando comando SNMP")
        except HTTPException:
            raise
        except Exception as ex:
            raise HTTPException(status_code=502, detail=str(ex)) from ex

    # ── URL stream cámara ────────────────────────────────────────────────────
    elif action == "stream_url":
        if dtype != "camera":
            raise HTTPException(status_code=400, detail="Solo disponible para cámaras")
        # Devuelve URL RTSP estándar — el técnico la abre en VLC
        rtsp_url = f"rtsp://{ip}:554/stream1"
        return {
            "success": True,
            "stream_url": rtsp_url,
            "message": f"Abre esta URL en VLC: {rtsp_url}",
        }

    else:
        raise HTTPException(status_code=400, detail=f"Acción desconocida: {action}")
