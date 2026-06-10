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
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.api.auth_api import get_current_user
from app.api.shomer_common import get_db, get_redis

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

POLL_INTERVAL_SEC = 30
_poller_running = False
ALERT_COOLDOWN_SEC = 300  # no repetir alerta del mismo equipo por 5 min

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

def _init_tables():
    with get_db() as conn:
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
            ("snmp_community",   "infra_devices", "TEXT DEFAULT 'public'"),
            ("pc_server_ip",     "infra_devices", "TEXT DEFAULT NULL"),
            ("tcp_ok",           "infra_status",  "INTEGER DEFAULT NULL"),
            ("mac",              "infra_status",  "TEXT DEFAULT NULL"),
            ("last_state_change","infra_status",  "TEXT"),
            ("snmp_data",        "infra_status",  "TEXT"),
            ("snmp_ok",          "infra_status",  "INTEGER DEFAULT NULL"),
        ]:
            try:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {defn}")
            except Exception:
                pass
        conn.commit()


# ──────────────────────────────────────────────
# Network helpers (blocking, run in thread)
# ──────────────────────────────────────────────

def _ping(ip: str) -> tuple[str, Optional[float]]:
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", ip],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "time=" in line:
                    try:
                        ms = float(line.split("time=")[1].split()[0])
                        return "online", ms
                    except Exception:
                        pass
            return "online", None
        return "offline", None
    except Exception:
        return "offline", None


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


def _parse_snmp_string(rhs: str) -> str:
    if "STRING:" in rhs:
        return rhs.split("STRING:", 1)[1].strip().strip('"')
    return ""


def _snmp_poll(ip: str, community: str, prev_snmp: Optional[dict], device_type: str = "generic") -> dict:
    """Blocking: collect SNMP system info + interface table (+ printer OIDs si aplica)."""
    snmpget  = shutil.which("snmpget")
    snmpwalk = shutil.which("snmpwalk")
    if not snmpget:
        return {"ok": False, "error": "snmpget no disponible"}

    TIMEOUT = 4
    BASE = ["-v2c", "-c", community, "-t", str(TIMEOUT), "-r", "0"]

    # System info: sysDescr + sysUpTime + sysName
    try:
        r = subprocess.run(
            [snmpget] + BASE + [ip,
                "1.3.6.1.2.1.1.1.0",
                "1.3.6.1.2.1.1.3.0",
                "1.3.6.1.2.1.1.5.0",
            ],
            capture_output=True, text=True, timeout=TIMEOUT + 2,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return {"ok": False, "error": "SNMP no responde (timeout o comunidad incorrecta)"}
        sys_out = r.stdout
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}

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

    # Interface table
    interfaces: list = []
    raw_octets: dict = {}
    if snmpwalk:
        try:
            r_if = subprocess.run(
                [snmpwalk] + BASE + [ip, "1.3.6.1.2.1.2.2.1"],
                capture_output=True, text=True, timeout=TIMEOUT + 10,
            )
            if r_if.returncode == 0 and r_if.stdout.strip():
                interfaces, raw_octets = _parse_iftable(r_if.stdout, prev_snmp)
        except Exception:
            pass

    result = {
        "ok": True,
        "sys_descr": sys_descr,
        "sys_uptime": sys_uptime,
        "sys_name": sys_name,
        "interfaces": interfaces,
        "_raw_octets": raw_octets,
        "_raw_ts": _time.time(),
        "polled_at": datetime.now(timezone.utc).isoformat(),
    }

    # OIDs específicos de impresora (printer MIB RFC 3805)
    if device_type in ("printer", "pos") and snmpget:
        try:
            r_p = subprocess.run(
                [snmpget] + BASE + [ip,
                    "1.3.6.1.2.1.25.3.5.1.1.1",    # hrPrinterStatus
                    "1.3.6.1.2.1.43.11.1.1.9.1.1",  # prtMarkerSuppliesLevel (tóner)
                    "1.3.6.1.2.1.43.8.2.1.10.1.1",  # prtInputCurrentLevel (papel actual)
                    "1.3.6.1.2.1.43.8.2.1.9.1.1",   # prtInputMaxCapacity (papel máx)
                ],
                capture_output=True, text=True, timeout=TIMEOUT + 2,
            )
            if r_p.returncode == 0 and r_p.stdout.strip():
                pr_status = pr_toner = pr_paper = pr_paper_max = None
                for line in r_p.stdout.splitlines():
                    if "=" not in line:
                        continue
                    lhs, rhs = line.split("=", 1)
                    lhs_s = lhs.strip()
                    rhs = rhs.strip()
                    val_str = rhs.split(":")[-1].strip() if ":" in rhs else rhs
                    try:
                        val = int(val_str)
                    except ValueError:
                        continue
                    if "25.3.5.1.1.1" in lhs_s:
                        pr_status = _PRINTER_STATUS_LABELS.get(val, f"código {val}")
                    elif "43.11.1.1.9.1.1" in lhs_s:
                        # -3=lleno, -2=desconocido, -1=otro, ≥0 = porcentaje/unidades
                        pr_toner = None if val < 0 else val
                    elif "43.8.2.1.10.1.1" in lhs_s:
                        pr_paper = None if val < 0 else val
                    elif "43.8.2.1.9.1.1" in lhs_s:
                        pr_paper_max = None if val <= 0 else val
                result["printer"] = {
                    "status": pr_status,
                    "toner_pct": pr_toner,
                    "paper_current": pr_paper,
                    "paper_max": pr_paper_max,
                }
        except Exception:
            pass

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

async def _poll_once():
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT ip, name, device_type, tcp_port, snmp_community FROM infra_devices WHERE active = 1"
            ).fetchall()
            existing = {
                r["ip"]: dict(r)
                for r in conn.execute(
                    "SELECT ip, status, last_state_change, snmp_data FROM infra_status"
                ).fetchall()
            }

    except Exception as e:
        logger.error("infra poll: DB error: %s", e)
        return

    if not rows:
        return

    redis = get_redis()
    now_utc = datetime.now(timezone.utc)

    ping_tasks = [asyncio.to_thread(_ping, r["ip"]) for r in rows]
    tcp_tasks = [
        asyncio.to_thread(_tcp_check, r["ip"], r["tcp_port"]) if r["tcp_port"] else _noop()
        for r in rows
    ]

    ping_results, tcp_results = await asyncio.gather(
        asyncio.gather(*ping_tasks, return_exceptions=True),
        asyncio.gather(*tcp_tasks, return_exceptions=True),
    )

    # MAC lookups only for online devices (ARP cache populated right after ping)
    mac_ips = [r["ip"] for r, pr in zip(rows, ping_results)
               if not isinstance(pr, Exception) and pr[0] == "online"]
    mac_res = {}
    if mac_ips:
        mac_vals = await asyncio.gather(
            *[asyncio.to_thread(_get_mac, ip) for ip in mac_ips],
            return_exceptions=True
        )
        mac_res = {ip: (v if not isinstance(v, Exception) else None)
                   for ip, v in zip(mac_ips, mac_vals)}

    # SNMP — parallel for all devices with non-empty community
    snmp_map: dict = {}
    snmp_tasks_list = []
    snmp_ips_list = []
    for row in rows:
        community = (row["snmp_community"] or "").strip()
        if not community:
            continue
        prev_snmp = None
        prev = existing.get(row["ip"])
        if prev and prev.get("snmp_data"):
            try:
                prev_snmp = json.loads(prev["snmp_data"])
            except Exception:
                pass
        snmp_tasks_list.append(asyncio.to_thread(_snmp_poll, row["ip"], community, prev_snmp, row["device_type"] or "generic"))
        snmp_ips_list.append(row["ip"])
    if snmp_tasks_list:
        snmp_vals = await asyncio.gather(*snmp_tasks_list, return_exceptions=True)
        for sip, sval in zip(snmp_ips_list, snmp_vals):
            snmp_map[sip] = sval if not isinstance(sval, Exception) else {"ok": False, "error": str(sval)}

    with get_db() as conn:
        for row, ping_r, tcp_r in zip(rows, ping_results, tcp_results):
            ip = row["ip"]
            name = row["name"]

            status, latency = ("offline", None) if isinstance(ping_r, Exception) else ping_r
            tcp_ok = None if (isinstance(tcp_r, Exception) or tcp_r is None) else (1 if tcp_r else 0)
            mac = mac_res.get(ip)

            prev = existing.get(ip)
            prev_status = prev["status"] if prev else None
            last_change_str = prev["last_state_change"] if prev else None

            if prev_status is not None and prev_status != status:
                conn.execute("INSERT INTO infra_events (ip, event) VALUES (?,?)", (ip, status))
                last_change = now_utc.isoformat()

                duration_sec = None
                if last_change_str:
                    try:
                        prev_ts = datetime.fromisoformat(last_change_str).replace(tzinfo=timezone.utc)
                        duration_sec = (now_utc - prev_ts).total_seconds()
                    except Exception:
                        pass

                # Telegram vía agente (watch_infra). Panel solo si INFRA_TELEGRAM_PANEL=1.
                if os.environ.get("INFRA_TELEGRAM_PANEL", "0").strip() == "1":
                    asyncio.create_task(
                        _send_infra_alert(name, ip, status, prev_status, duration_sec,
                                          device_type=(row["device_type"] or "generic"))
                    )
            else:
                last_change = last_change_str or now_utc.isoformat()

            snmp_res = snmp_map.get(ip)
            snmp_data_json = json.dumps(snmp_res) if snmp_res is not None else None
            snmp_ok_val = 1 if (snmp_res and snmp_res.get("ok")) else (0 if snmp_res is not None else None)

            conn.execute("""
                INSERT INTO infra_status
                    (ip, status, latency_ms, tcp_ok, mac, last_state_change, snmp_data, snmp_ok, checked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(ip) DO UPDATE SET
                    status=excluded.status,
                    latency_ms=excluded.latency_ms,
                    tcp_ok=excluded.tcp_ok,
                    mac=COALESCE(excluded.mac, infra_status.mac),
                    last_state_change=excluded.last_state_change,
                    snmp_data=COALESCE(excluded.snmp_data, infra_status.snmp_data),
                    snmp_ok=COALESCE(excluded.snmp_ok, infra_status.snmp_ok),
                    checked_at=excluded.checked_at
            """, (ip, status, latency, tcp_ok, mac, last_change, snmp_data_json, snmp_ok_val))

            if redis:
                redis.setex(f"infra:{ip}:status", POLL_INTERVAL_SEC * 4, status)
                if latency is not None:
                    redis.setex(f"infra:{ip}:latency", POLL_INTERVAL_SEC * 4, str(latency))
        conn.commit()


async def _poller_loop():
    global _poller_running
    _init_tables()
    while True:
        try:
            await _poll_once()
        except Exception as e:
            logger.error("infra poller error: %s", e)
        await asyncio.sleep(POLL_INTERVAL_SEC)


def start_inframonitor_poller():
    global _poller_running
    if _poller_running:
        return
    _poller_running = True
    asyncio.create_task(_poller_loop())
    logger.info("Inframonitor poller iniciado (intervalo %ss)", POLL_INTERVAL_SEC)


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


def _build_device_row(d, s, uptime: Optional[float]) -> dict:
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
        "tcp_ok": s["tcp_ok"] if s else None,
        "mac": s["mac"] if s else None,
        "snmp_ok": s["snmp_ok"] if s else None,
        "uptime_24h": uptime,
        "state_duration": _fmt_duration(s["last_state_change"] if s else None),
        "checked_at": (s["checked_at"] if s else None),
        "created_at": d["created_at"],
    }
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
        except Exception:
            pass
    return row


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.get("/infra/devices")
async def list_devices(user=Depends(get_current_user)):
    _init_tables()
    with get_db() as conn:
        devices = conn.execute(
            "SELECT * FROM infra_devices WHERE active = 1 ORDER BY name"
        ).fetchall()
        status_map = {
            r["ip"]: dict(r) for r in conn.execute("SELECT * FROM infra_status").fetchall()
        }
        result = [
            _build_device_row(d, status_map.get(d["ip"]),
                              _calc_uptime_24h(conn, d["ip"], (status_map.get(d["ip"]) or {}).get("status", "unknown")))
            for d in devices
        ]
        row = conn.execute(
            "SELECT COUNT(DISTINCT ip) FROM infra_status "
            "WHERE status='offline' AND checked_at > datetime('now', '-24 hours')"
        ).fetchone()
        outages_24h = row[0] if row else 0
    return {"success": True, "devices": result, "outages_24h": outages_24h}


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
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO infra_devices (ip, name, device_type, location, tcp_port, snmp_community, pc_server_ip) "
                "VALUES (?,?,?,?,?,?,?)",
                (body.ip, body.name, body.device_type, body.location, body.tcp_port,
                 body.snmp_community or "public", body.pc_server_ip or None)
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

    _init_tables()
    with get_db() as conn:
        devices = conn.execute(
            "SELECT d.*, s.status, s.latency_ms, s.tcp_ok, s.mac, s.last_state_change, s.checked_at "
            "FROM infra_devices d LEFT JOIN infra_status s ON d.ip = s.ip "
            "WHERE d.active = 1 ORDER BY d.name"
        ).fetchall()
        result = []
        for d in devices:
            st = d["status"] or "unknown"
            result.append({
                "ip": d["ip"],
                "name": d["name"],
                "device_type": d["device_type"],
                "icon": DEVICE_ICONS.get(d["device_type"], "📡"),
                "location": d["location"],
                "tcp_port": d["tcp_port"],
                "status": st,
                "latency_ms": d["latency_ms"],
                "tcp_ok": d["tcp_ok"],
                "mac": d["mac"],
                "uptime_24h": _calc_uptime_24h(conn, d["ip"], st),
                "state_duration": _fmt_duration(d["last_state_change"]),
                "checked_at": d["checked_at"],
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

    status, latency = await asyncio.to_thread(_ping, ip)
    return {"ip": ip, "status": status, "latency_ms": latency}


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
            "SELECT name, device_type, snmp_community FROM infra_devices WHERE ip=? AND active=1", (ip,)
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
                    "net stop spooler && del /Q /F /S \"%SystemRoot%\\System32\\spool\\PRINTERS\\*\" && net start spooler",
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
        community_write = (dev.get("snmp_community") or "public")
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
