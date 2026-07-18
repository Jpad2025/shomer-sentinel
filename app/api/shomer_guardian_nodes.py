"""Guardian — nodos, heartbeat, reboot, logs, health."""
import asyncio
import json
import logging
import os
import subprocess
import time as _time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.auth_api import get_current_user
from app.api.shomer_common import (
    REDIS_AVAILABLE,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PORT,
    _prune_old_logs,
    get_config,
    get_db,
    get_redis,
)
from app.api.shomer_guardian_health_checks import (
    DEGRADED_NOTIFY_KEY_PREFIX,
    DEGRADED_STREAK_KEY_PREFIX,
    OFFLINE_STREAK_KEY_PREFIX,
    _get_health_config,
    _ping_metrics,
    _snmp_health_probes,
    _ssh_health_probes,
    classify_health,
    classify_snmp_health,
)
from app.api.shomer_guardian_lib import (
    ALLOWED_IP_PATTERN,
    FAILURES_KEY_PREFIX,
    LAST_REBOOT_KEY_PREFIX,
    MAINTENANCE_KEY,
    NODE_MAINTENANCE_PREFIX,
    MONITOR_RECENT_SEC,
    NODE_DATA_PREFIX,
    log_event,
    send_telegram_safe,
    _get_guardian_thresholds,
    _normalize_success,
    _redis_bool,
    _run_ssh_reboot,
    _save_node_data_redis,
)
from app.api.shomer_status_events import _context_snapshots, record_status_event
from app.api.shomer_network_blip import evaluate_host_network_blip_async, metrics_to_status

try:
    import redis as redis_lib
except ImportError:
    redis_lib = None  # type: ignore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Shomer Guardian"])

_POLL_INTERVAL_SEC = int(os.environ.get("SHOMER_POLL_INTERVAL_SEC", "10"))
GUARDIAN_POLL_INTERVAL_SEC = _POLL_INTERVAL_SEC
_poller_task = None

# Límites de concurrencia — evitan saturar el pool de hilos y la red del sitio.
SSH_SEM = asyncio.Semaphore(4)
HC_SEM = asyncio.Semaphore(8)
SNMP_SEM = asyncio.Semaphore(4)


def _get_devices_for_poll() -> List[Dict]:
    """Devuelve lista de dispositivos activos con credenciales SSH y SNMP."""
    try:
        with get_db() as conn:
            cur = conn.execute(
                "SELECT ip_address, name, device_type, reboot_method, "
                "ssh_user, ssh_password, ssh_port, snmp_community "
                "FROM devices WHERE is_active=1"
            )
            return [dict(row) for row in cur.fetchall()]
    except Exception:
        return []


def _update_infra_nodes(results: List[Dict[str, Any]]) -> None:
    """Upsert en tabla `infra_nodes` y elimina IPs fuera del ciclo activo.

    Migrado desde `app/scripts/monitor.py` (Sesión 15). Mantiene la tabla
    alineada con el ciclo del poller para que las vistas del panel siempre
    reflejen el inventario real.
    """
    if not results:
        return
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    active_ips = [r["ip"] for r in results]
    import sqlite3
    import time as _time

    for attempt in range(4):
        try:
            with get_db() as conn:
                for rr in results:
                    conn.execute(
                        "INSERT OR REPLACE INTO infra_nodes "
                        "(ip_address, status, last_heartbeat, latency_ms) VALUES (?, ?, ?, ?)",
                        (rr["ip"], rr["status"], now, rr.get("latency_ms")),
                    )
                placeholders = ",".join("?" * len(active_ips))
                conn.execute(
                    f"DELETE FROM infra_nodes WHERE ip_address NOT IN ({placeholders})",
                    active_ips,
                )
                conn.commit()
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < 3:
                _time.sleep(0.15 * (attempt + 1))
                continue
            logger.warning("update_infra_nodes: %s", e)
            return
        except Exception as e:
            logger.warning("update_infra_nodes: %s", e)
            return


def _sync_devices_status_from_infra_nodes() -> None:
    """Refleja infra_nodes → devices.status para APs (inventario Guardian, no el poller)."""
    import sqlite3
    import time as _time

    for attempt in range(4):
        try:
            with get_db() as conn:
                rows = conn.execute(
                    """
                    SELECT n.ip_address, n.status, n.latency_ms
                    FROM infra_nodes n
                    INNER JOIN devices d ON d.ip_address = n.ip_address
                        AND d.is_active = 1 AND d.device_type = 'access_point'
                    """
                ).fetchall()
                for r in rows:
                    lat = r["latency_ms"]
                    conn.execute(
                        "UPDATE devices SET status = ?, latency_ms = ?, "
                        "updated_at = datetime('now') WHERE ip_address = ? "
                        "AND device_type = 'access_point'",
                        (
                            r["status"] or "unknown",
                            int(round(lat)) if lat is not None else None,
                            r["ip_address"],
                        ),
                    )
                conn.commit()
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < 3:
                _time.sleep(0.15 * (attempt + 1))
                continue
            logger.warning("sync_devices_status_from_infra_nodes: %s", e)
            return
        except Exception as e:
            logger.warning("sync_devices_status_from_infra_nodes: %s", e)
            return


def _get_redis_guardian_client():
    """Cliente Redis para el poller Guardian (timeouts acotados)."""
    if not REDIS_AVAILABLE or redis_lib is None:
        return None
    try:
        r = redis_lib.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        r.ping()
        return r
    except Exception:
        return None


def _redis_scan_keys(r, pattern: str) -> List[str]:
    """SCAN en lugar de KEYS — no bloquea Redis en producción."""
    keys: List[str] = []
    cursor = 0
    while True:
        cursor, batch = r.scan(cursor=cursor, match=pattern, count=200)
        keys.extend(batch)
        if cursor == 0:
            break
    return keys


def _cleanup_orphan_guardian_keys(r, all_ips: set) -> None:
    """Elimina claves Redis de nodos ya borrados de `devices` (sync, en hilo)."""
    try:
        for key in _redis_scan_keys(r, "status:*"):
            ip = key.replace("status:", "", 1)
            if ip not in all_ips:
                for prefix in (
                    "status:", "failures:", "last_reboot:", "node_maintenance:",
                    "degraded_notified:", "degraded_streak:", "offline_streak:",
                ):
                    r.delete(f"{prefix}{ip}")
    except Exception:
        pass


def _batch_read_redis_state(r, ips: List[str]) -> Dict[str, Any]:
    """Lee estado Redis de todos los nodos en un solo pipeline."""
    if not ips:
        return {"global_maintenance": False, "per_ip": {}}
    pipe = r.pipeline()
    for ip in ips:
        pipe.get(f"status:{ip}")
        pipe.get(f"{FAILURES_KEY_PREFIX}{ip}")
        pipe.get(f"{DEGRADED_STREAK_KEY_PREFIX}{ip}")
        pipe.get(f"{OFFLINE_STREAK_KEY_PREFIX}{ip}")
        pipe.get(f"{DEGRADED_NOTIFY_KEY_PREFIX}{ip}")
        pipe.get(f"{NODE_MAINTENANCE_PREFIX}{ip}")
        pipe.get(f"{LAST_REBOOT_KEY_PREFIX}{ip}")
    pipe.get(MAINTENANCE_KEY)
    raw = pipe.execute()
    per_ip: Dict[str, Dict[str, Any]] = {}
    idx = 0
    for ip in ips:
        per_ip[ip] = {
            "status": raw[idx] or "unknown",
            "failures": int(raw[idx + 1] or 0),
            "streak": int(raw[idx + 2] or 0),
            "offline_streak": int(raw[idx + 3] or 0),
            "notify": raw[idx + 4],
            "node_maint": raw[idx + 5] == "1",
            "last_reboot": raw[idx + 6],
        }
        idx += 7
    return {"global_maintenance": raw[idx] == "1", "per_ip": per_ip}


def _load_guardian_poll_read() -> Optional[Dict[str, Any]]:
    """Fase lectura del ciclo Guardian (sync — asyncio.to_thread)."""
    devices = _get_devices_for_poll()
    with get_db() as conn:
        all_ips = {row[0] for row in conn.execute("SELECT ip_address FROM devices").fetchall()}
    threshold, cooldown = _get_guardian_thresholds()
    health_cfg = _get_health_config()
    wan_snapshot, maintenance = _context_snapshots()
    r = _get_redis_guardian_client()
    if r is None:
        return None
    _cleanup_orphan_guardian_keys(r, all_ips)
    ips = [d["ip_address"] for d in devices]
    redis_state = _batch_read_redis_state(r, ips)
    gateway_ip = (get_config("base.gateway") or "").strip()
    return {
        "devices": devices,
        "all_ips": all_ips,
        "threshold": threshold,
        "cooldown": cooldown,
        "health_cfg": health_cfg,
        "wan_snapshot": wan_snapshot,
        "maintenance": maintenance,
        "redis": r,
        "redis_state": redis_state,
        "gateway_ip": gateway_ip,
    }


def _apply_redis_op(pipe, op: Tuple) -> None:
    kind = op[0]
    if kind == "set":
        _, key, val = op
        pipe.set(key, val)
    elif kind == "setex":
        _, key, val, ttl = op
        pipe.setex(key, ttl, val)
    elif kind == "delete":
        _, key = op
        pipe.delete(key)
    elif kind == "expire":
        _, key, ttl = op
        pipe.expire(key, ttl)


def _build_node_outcome(
    dev: Dict[str, Any],
    probe: Dict[str, Any],
    *,
    threshold: int,
    cooldown: int,
    health_cfg: Dict[str, Any],
    redis_snap: Dict[str, Any],
    global_maint: bool,
    batch_id: str,
    wan_snapshot: str,
    maintenance: int,
    host_network_blip: bool = False,
) -> Dict[str, Any]:
    """Calcula estado, eventos y operaciones Redis en memoria (sin I/O)."""
    ip = dev["ip_address"]
    dev_name = dev.get("name") or ip
    dev_type = dev.get("device_type") or "generic"
    prev_redis = redis_snap.get("status") or "unknown"

    lan_ok = probe["lan_ok"]
    lan_loss = probe["lan_loss"]
    lan_rtt = probe["lan_rtt"]
    ssh_result = probe.get("ssh_result")
    snmp_result = probe.get("snmp_result")
    is_snmp_device = dev.get("reboot_method") == "snmp"
    is_router = not is_snmp_device and dev.get("device_type") in ("router", "gateway")

    if is_snmp_device:
        status_label, reason = classify_snmp_health(
            lan_ok=lan_ok,
            lan_loss_pct=lan_loss,
            lan_rtt_ms=lan_rtt,
            snmp_result=snmp_result,
            cfg=health_cfg,
        )
    else:
        status_label, reason = classify_health(
            lan_ok=lan_ok,
            lan_loss_pct=lan_loss,
            lan_rtt_ms=lan_rtt,
            is_router=is_router,
            ssh_result=ssh_result,
            cfg=health_cfg,
        )

    lat_ms = int(round(lan_rtt)) if lan_rtt is not None else None
    outcome: Dict[str, Any] = {
        "ip": ip,
        "status_events": [],
        "redis_ops": [],
        "telegrams": [],
        "log_events": [],
        "reboot": None,
        "poller_log": None,
        "tick_result": None,
    }

    def _event(prev: str, status: str, reason_txt: str) -> None:
        if host_network_blip:
            return
        outcome["status_events"].append({
            "source": "guardian",
            "ip": ip,
            "name": dev_name,
            "device_type": dev_type,
            "prev_status": prev,
            "status": status,
            "reason": reason_txt,
            "latency_ms": lat_ms,
            "loss_pct": lan_loss,
            "batch_id": batch_id,
            "wan_snapshot": wan_snapshot,
            "maintenance": maintenance,
        })

    fail_key = f"{FAILURES_KEY_PREFIX}{ip}"
    streak_key = f"{DEGRADED_STREAK_KEY_PREFIX}{ip}"
    offline_streak_key = f"{OFFLINE_STREAK_KEY_PREFIX}{ip}"
    status_key = f"status:{ip}"

    if status_label == "online":
        if prev_redis != "online":
            _event(prev_redis, "online", "ping OK")
        outcome["redis_ops"].extend([
            ("set", status_key, "online"),
            ("delete", fail_key),
            ("delete", streak_key),
            ("delete", offline_streak_key),
        ])
        outcome["tick_result"] = {"ip": ip, "status": "online", "latency_ms": lat_ms}
        return outcome

    if status_label == "degraded":
        outcome["redis_ops"].append(("delete", fail_key))
        new_streak = int(redis_snap.get("streak") or 0) + 1
        outcome["redis_ops"].append(("set", streak_key, str(new_streak)))
        outcome["redis_ops"].append(("expire", streak_key, max(cooldown, 60)))
        persist = int(health_cfg.get("degraded_persist_ticks") or 3)
        if new_streak < persist:
            prev = redis_snap.get("status") or "online"
            outcome["tick_result"] = {"ip": ip, "status": prev, "latency_ms": lat_ms}
            return outcome
        if prev_redis != "degraded":
            _event(prev_redis, "degraded", reason)
        outcome["redis_ops"].append(("set", status_key, "degraded"))
        notify_key = f"{DEGRADED_NOTIFY_KEY_PREFIX}{ip}"
        if not host_network_blip and not redis_snap.get("notify"):
            alert_cooldown = int(health_cfg.get("degraded_alert_cooldown_sec") or 1800)
            outcome["redis_ops"].append(("setex", notify_key, "1", alert_cooldown))
            outcome["telegrams"].append(
                f"🟡 <b>CALIDAD DEGRADADA</b> SHOMER: Nodo {ip} — {reason} "
                f"({new_streak} ticks sostenidos)"
            )
            outcome["log_events"].append(("warning", "DEGRADED", f"Nodo {ip} degradado: {reason}"))
        outcome["tick_result"] = {"ip": ip, "status": "degraded", "latency_ms": lat_ms}
        return outcome

    if status_label == "offline":
        new_offline_streak = int(redis_snap.get("offline_streak") or 0) + 1
        outcome["redis_ops"].append(("set", offline_streak_key, str(new_offline_streak)))
        outcome["redis_ops"].append(("expire", offline_streak_key, max(cooldown, 60)))
        offline_persist = int(health_cfg.get("offline_persist_ticks") or 3)
        if new_offline_streak < offline_persist:
            prev = redis_snap.get("status") or "online"
            outcome["redis_ops"].append(("delete", streak_key))
            outcome["tick_result"] = {"ip": ip, "status": prev, "latency_ms": lat_ms}
        else:
            if prev_redis != "offline":
                _event(prev_redis, "offline", reason)
            outcome["redis_ops"].extend([
                ("set", status_key, "offline"),
                ("delete", streak_key),
            ])
            outcome["tick_result"] = {"ip": ip, "status": "offline", "latency_ms": lat_ms}
    else:
        if prev_redis != status_label:
            _event(prev_redis, status_label, reason)
        outcome["redis_ops"].extend([
            ("set", status_key, status_label),
            ("delete", streak_key),
            ("delete", offline_streak_key),
        ])
        outcome["tick_result"] = {"ip": ip, "status": status_label, "latency_ms": lat_ms}

    if global_maint or redis_snap.get("node_maint") or host_network_blip:
        return outcome

    new_failures = int(redis_snap.get("failures") or 0) + 1
    outcome["redis_ops"].append(("set", fail_key, str(new_failures)))
    outcome["poller_log"] = (ip, status_label, new_failures, threshold, reason)

    if new_failures < threshold:
        return outcome

    now_ts = int(datetime.utcnow().timestamp())
    lr_key = f"{LAST_REBOOT_KEY_PREFIX}{ip}"
    last_raw = redis_snap.get("last_reboot")
    if last_raw:
        try:
            if now_ts - int(last_raw) < cooldown:
                return outcome
        except Exception:
            pass

    reboot_via = "SNMP" if dev.get("reboot_method") == "snmp" else "SSH"
    outcome["reboot"] = {
        "ip": ip,
        "dev_name": dev_name,
        "reason": reason,
        "count": new_failures,
        "reboot_via": reboot_via,
        "lr_key": lr_key,
        "now_ts": now_ts,
    }
    return outcome


def _persist_guardian_tick(
    outcomes: List[Dict[str, Any]],
    tick_results: List[Dict[str, Any]],
    r,
) -> None:
    """SQLite corto + pipeline Redis + reboots (sync — asyncio.to_thread)."""
    with get_db() as conn:
        for oc in outcomes:
            for ev in oc.get("status_events", []):
                record_status_event(conn=conn, **ev)
        conn.commit()

    _update_infra_nodes(tick_results)
    _sync_devices_status_from_infra_nodes()

    pipe = r.pipeline()
    for oc in outcomes:
        for op in oc.get("redis_ops", []):
            _apply_redis_op(pipe, op)
    pipe.execute()

    for oc in outcomes:
        pl = oc.get("poller_log")
        if pl:
            logger.info(
                "[POLLER] %s → %s | fallos: %d/%d | %s",
                pl[0], pl[1], pl[2], pl[3], pl[4],
            )
        for msg in oc.get("telegrams", []):
            send_telegram_safe(msg)
        for lev, src, msg in oc.get("log_events", []):
            log_event(r, lev, src, msg)

        reboot = oc.get("reboot")
        if not reboot:
            continue
        ok, msg = _run_ssh_reboot(reboot["ip"])
        r.set(reboot["lr_key"], str(reboot["now_ts"]))
        if ok:
            send_telegram_safe(
                f"⚡ <b>REINICIO EN PROGRESO</b> SHOMER\n"
                f"<b>Equipo:</b> {reboot['dev_name']} ({reboot['ip']})\n"
                f"<b>Motivo:</b> {reboot['reason']}\n"
                f"<b>Fallos:</b> {reboot['count']} consecutivos\n"
                f"<b>Vía:</b> {reboot['reboot_via']} — {msg}"
            )
            log_event(
                r, "warning", "AUTO-REBOOT",
                f"{reboot['dev_name']} ({reboot['ip']}) reiniciado — "
                f"motivo: {reboot['reason']}, {reboot['count']} fallos",
            )
        else:
            send_telegram_safe(
                f"🚨 <b>PÉRDIDA DE SERVICIO</b> SHOMER\n"
                f"<b>Equipo:</b> {reboot['dev_name']} ({reboot['ip']})\n"
                f"<b>Error al reiniciar:</b> {msg}\n"
                f"<b>Motivo:</b> {reboot['reason']} — {reboot['count']} fallos consecutivos"
            )
            log_event(
                r, "error", "AUTO-REBOOT",
                f"Fallo al reiniciar {reboot['dev_name']} ({reboot['ip']}): {msg}",
            )

    try:
        r.setex(
            "guardian:poller:last_ok",
            GUARDIAN_POLL_INTERVAL_SEC * 4,
            datetime.utcnow().isoformat(),
        )
    except Exception:
        pass


async def _probe_guardian_ping(
    dev: Dict[str, Any],
    health_cfg: Dict[str, Any],
) -> Tuple[Tuple[bool, float, Optional[float]], int]:
    """Solo ICMP — fase 1 del ciclo Guardian."""
    ip = dev["ip_address"]
    t0 = _time.monotonic()
    async with HC_SEM:
        lan_ok, lan_loss, lan_rtt = await asyncio.to_thread(
            _ping_metrics, ip, health_cfg["ping_count"],
        )
    return (lan_ok, lan_loss, lan_rtt), int((_time.monotonic() - t0) * 1000)


async def _probe_guardian_extended(
    dev: Dict[str, Any],
    health_cfg: Dict[str, Any],
    lan_ok: bool,
    lan_loss: float,
    lan_rtt: Optional[float],
) -> Tuple[Dict[str, Any], int, int]:
    """SSH/SNMP tras ping OK — no se llama durante host_network_blip."""
    ip = dev["ip_address"]
    ssh_ms = 0
    snmp_ms = 0
    ssh_result: Any = None
    snmp_result: Any = None
    is_snmp_device = dev.get("reboot_method") == "snmp"
    is_router = not is_snmp_device and dev.get("device_type") in ("router", "gateway")

    if lan_ok and is_router:
        t0 = _time.monotonic()
        async with SSH_SEM:
            ssh_user = dev.get("ssh_user") or "root"
            ssh_port = int(dev.get("ssh_port") or 22)
            ssh_pwd = dev.get("ssh_password") or ""
            ssh_result = await asyncio.to_thread(
                _ssh_health_probes, ip, ssh_user, ssh_port, ssh_pwd, health_cfg,
            )
        ssh_ms = int((_time.monotonic() - t0) * 1000)
    elif lan_ok and is_snmp_device:
        t0 = _time.monotonic()
        async with SNMP_SEM:
            snmp_community = dev.get("snmp_community") or "public"
            snmp_result = await asyncio.to_thread(_snmp_health_probes, ip, snmp_community)
        snmp_ms = int((_time.monotonic() - t0) * 1000)

    return {
        "lan_ok": lan_ok,
        "lan_loss": lan_loss,
        "lan_rtt": lan_rtt,
        "ssh_result": ssh_result,
        "snmp_result": snmp_result,
    }, ssh_ms, snmp_ms


async def _probe_guardian_device(
    dev: Dict[str, Any],
    health_cfg: Dict[str, Any],
) -> Tuple[Dict[str, Any], int, int, int]:
    """Ping + SSH/SNMP (ruta completa cuando no hay blip)."""
    (lan_ok, lan_loss, lan_rtt), ping_ms = await _probe_guardian_ping(dev, health_cfg)
    probe, ssh_ms, snmp_ms = await _probe_guardian_extended(
        dev, health_cfg, lan_ok, lan_loss, lan_rtt,
    )
    return probe, ping_ms, ssh_ms, snmp_ms


async def _poller_tick() -> None:
    t_total = _time.monotonic()
    batch_id = f"g-{int(datetime.utcnow().timestamp())}"

    try:
        ctx = await asyncio.to_thread(_load_guardian_poll_read)
    except Exception as e:
        logger.error("guardian poll: read error: %s", e, exc_info=True)
        return

    if ctx is None:
        return

    devices = ctx["devices"]
    read_ms = int((_time.monotonic() - t_total) * 1000)
    if not devices:
        return

    r = ctx["redis"]
    threshold = ctx["threshold"]
    cooldown = ctx["cooldown"]
    health_cfg = ctx["health_cfg"]
    wan_snapshot = ctx["wan_snapshot"]
    maintenance = ctx["maintenance"]
    redis_state = ctx["redis_state"]
    global_maint = redis_state["global_maintenance"]
    per_ip = redis_state["per_ip"]
    gateway_ip = ctx.get("gateway_ip") or ""

    # Fase 1 — ping paralelo a todos los nodos
    ping_tasks = [_probe_guardian_ping(dev, health_cfg) for dev in devices]
    ping_out = await asyncio.gather(*ping_tasks, return_exceptions=True)

    checks_ms = 0
    ping_by_ip: Dict[str, Tuple[bool, float, Optional[float]]] = {}
    cycle_status: Dict[str, str] = {}
    existing_status: Dict[str, str] = {}

    for dev, pr in zip(devices, ping_out):
        ip = dev["ip_address"]
        if isinstance(pr, Exception):
            ping_by_ip[ip] = (False, 100.0, None)
            cycle_status[ip] = "offline"
        else:
            (lan_ok, lan_loss, lan_rtt), p_ms = pr
            checks_ms += p_ms
            ping_by_ip[ip] = (lan_ok, lan_loss, lan_rtt)
            cycle_status[ip] = metrics_to_status(
                lan_ok, lan_loss, lan_rtt,
                loss_degraded_pct=float(health_cfg.get("loss_degraded_pct") or 60),
            )
        existing_status[ip] = per_ip.get(ip, {}).get("status") or "unknown"

    loss_deg = float(health_cfg.get("loss_degraded_pct") or 60)

    async def _gw_ping_triplet():
        if not gateway_ip:
            return "online", 0.0, None
        ok, loss, rtt = await asyncio.to_thread(
            _ping_metrics, gateway_ip, health_cfg["ping_count"],
        )
        return metrics_to_status(ok, loss, rtt, loss_degraded_pct=loss_deg), loss, rtt

    host_network_blip, blip_skip_ips = await evaluate_host_network_blip_async(
        gateway_ip,
        _gw_ping_triplet,
        cycle_status,
        existing_status,
        len(devices),
        log_prefix="guardian poll",
    )

    ssh_ms = 0
    snmp_ms = 0
    outcomes: List[Dict[str, Any]] = []
    tick_results: List[Dict[str, Any]] = []

    for dev in devices:
        ip = dev["ip_address"]
        lan_ok, lan_loss, lan_rtt = ping_by_ip.get(ip, (False, 100.0, None))

        if host_network_blip and ip in blip_skip_ips:
            prev = existing_status.get(ip) or "unknown"
            lat_ms = int(round(lan_rtt)) if lan_rtt is not None else None
            tick_results.append({"ip": ip, "status": prev, "latency_ms": lat_ms})
            continue

        try:
            if host_network_blip:
                probe = {
                    "lan_ok": lan_ok,
                    "lan_loss": lan_loss,
                    "lan_rtt": lan_rtt,
                    "ssh_result": None,
                    "snmp_result": None,
                }
            else:
                probe, s_ms, n_ms = await _probe_guardian_extended(
                    dev, health_cfg, lan_ok, lan_loss, lan_rtt,
                )
                ssh_ms += s_ms
                snmp_ms += n_ms

            oc = _build_node_outcome(
                dev,
                probe,
                threshold=threshold,
                cooldown=cooldown,
                health_cfg=health_cfg,
                redis_snap=per_ip.get(ip, {}),
                global_maint=global_maint,
                batch_id=batch_id,
                wan_snapshot=wan_snapshot,
                maintenance=maintenance,
                host_network_blip=host_network_blip,
            )
            outcomes.append(oc)
            if oc.get("tick_result"):
                tick_results.append(oc["tick_result"])
        except Exception as e:
            logger.warning("Poller outcome error en %s: %s", ip, e)
            tick_results.append({"ip": ip, "status": "unknown", "latency_ms": None})

    t_write = _time.monotonic()
    try:
        await asyncio.to_thread(_persist_guardian_tick, outcomes, tick_results, r)
    except Exception as e:
        logger.error(
            "guardian poll: persist failed batch_id=%s nodes=%d: %s",
            batch_id, len(devices), e,
            exc_info=True,
        )
        try:
            r.setex(
                "guardian:poller:last_error",
                300,
                json.dumps({
                    "ts": datetime.utcnow().isoformat(),
                    "batch_id": batch_id,
                    "error": str(e)[:500],
                }),
            )
        except Exception:
            pass
        write_ms = int((_time.monotonic() - t_write) * 1000)
        total_ms = int((_time.monotonic() - t_total) * 1000)
        logger.info(
            "guardian poll: read=%dms checks=%dms ssh=%dms snmp=%dms write=%dms "
            "total=%dms nodes=%d (persist error)",
            read_ms, checks_ms, ssh_ms, snmp_ms, write_ms, total_ms, len(devices),
        )
        return

    write_ms = int((_time.monotonic() - t_write) * 1000)
    total_ms = int((_time.monotonic() - t_total) * 1000)
    logger.info(
        "guardian poll: read=%dms checks=%dms ssh=%dms snmp=%dms write=%dms "
        "total=%dms nodes=%d",
        read_ms, checks_ms, ssh_ms, snmp_ms, write_ms, total_ms, len(devices),
    )
    if total_ms > GUARDIAN_POLL_INTERVAL_SEC * 1000:
        logger.warning(
            "guardian poll: ciclo lento read=%dms checks=%dms ssh=%dms snmp=%dms "
            "write=%dms total=%dms nodes=%d (umbral %ds)",
            read_ms, checks_ms, ssh_ms, snmp_ms, write_ms, total_ms,
            len(devices), GUARDIAN_POLL_INTERVAL_SEC,
        )


async def _poller_loop() -> None:
    await asyncio.sleep(5)
    loop = asyncio.get_event_loop()
    while True:
        t0 = loop.time()
        try:
            await _poller_tick()
        except Exception as e:
            logger.warning("Poller loop error: %s", e)
        elapsed = loop.time() - t0
        await asyncio.sleep(max(0.1, GUARDIAN_POLL_INTERVAL_SEC - elapsed))


def start_node_poller() -> None:
    global _poller_task
    loop = asyncio.get_event_loop()
    _poller_task = loop.create_task(_poller_loop())
    logger.info("Guardian node poller iniciado (intervalo: %ds, umbral: threshold desde BD)", _POLL_INTERVAL_SEC)


@router.get("/nodes")
async def get_nodes(user=Depends(get_current_user)):
    """
    Lee directamente de Redis. Devuelve JSON con IP, estado (online/offline) y latencia.
    Estado desde Redis (tiempo real). Latencia desde infra_nodes (SQLite).
    """
    r = get_redis()
    nodes: List[Dict[str, Any]] = []

    if r is not None:
        try:
            keys = r.keys("status:*")
            for key in keys:
                ip = key.replace("status:", "")
                status = r.get(key) or "unknown"
                nodes.append({"ip": ip, "status": status, "latency_ms": None})
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Redis error: {e}")

    if not nodes:
        try:
            with get_db() as conn:
                cur = conn.execute(
                    "SELECT ip_address, status, latency_ms FROM infra_nodes ORDER BY last_heartbeat DESC LIMIT 50"
                )
                for row in cur.fetchall():
                    nodes.append(
                        {
                            "ip": row["ip_address"],
                            "status": row["status"] or "unknown",
                            "latency_ms": row["latency_ms"],
                        }
                    )
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"SQLite error: {e}")

    try:
        with get_db() as conn:
            cur = conn.execute("SELECT ip_address, latency_ms FROM infra_nodes")
            latency_map = {row["ip_address"]: row["latency_ms"] for row in cur.fetchall()}
        for n in nodes:
            n["latency_ms"] = latency_map.get(n["ip"])
    except Exception as e:
        logger.warning("Error leyendo latencias de BD: %s", e)

    if r is not None:
        try:
            for n in nodes:
                key = f"{FAILURES_KEY_PREFIX}{n['ip']}"
                n["failures"] = int(r.get(key) or 0)
                lr_raw = r.get(f"{LAST_REBOOT_KEY_PREFIX}{n['ip']}")
                n["last_reboot"] = int(lr_raw) if lr_raw else None
                data_key = f"{NODE_DATA_PREFIX}{n['ip']}"
                data = r.hgetall(data_key) or {}
                n["clients"] = int(data["clients"]) if data.get("clients") not in (None, "") else None
                n["uptime"] = int(data["uptime"]) if data.get("uptime") not in (None, "") else None
                n["point_a"] = _redis_bool(data.get("point_a"))
                n["point_b"] = _redis_bool(data.get("point_b"))
                n["point_c"] = _redis_bool(data.get("point_c"))
                nm_val = r.get(f"{NODE_MAINTENANCE_PREFIX}{n['ip']}")
                n["node_maintenance"] = nm_val == "1"
                nm_ttl = r.ttl(f"{NODE_MAINTENANCE_PREFIX}{n['ip']}") if nm_val else -1
                n["node_maintenance_ttl"] = nm_ttl if nm_ttl > 0 else None
        except Exception:
            for n in nodes:
                n["failures"] = n.get("failures", 0)
                n.setdefault("clients", None)
                n.setdefault("uptime", None)
                n.setdefault("point_a", None)
                n.setdefault("point_b", None)
                n.setdefault("point_c", None)
                n.setdefault("node_maintenance", False)
                n.setdefault("node_maintenance_ttl", None)
    else:
        for n in nodes:
            n["failures"] = n.get("failures", 0)
            n.setdefault("clients", None)
            n.setdefault("uptime", None)
            n.setdefault("point_a", None)
            n.setdefault("point_b", None)
            n.setdefault("point_c", None)
            n.setdefault("node_maintenance", False)
            n.setdefault("node_maintenance_ttl", None)

    try:
        with get_db() as conn:
            cur = conn.execute("SELECT ip_address, name FROM devices WHERE is_active=1")
            name_map = {row["ip_address"]: row["name"] for row in cur.fetchall()}
        for n in nodes:
            n["name"] = name_map.get(n["ip"]) or ""
    except Exception as e:
        logger.warning("Error leyendo nombres de dispositivos: %s", e)
        for n in nodes:
            n.setdefault("name", "")

    return {"success": True, "count": len(nodes), "nodes": nodes}


@router.post("/heartbeat")
async def heartbeat(request: Request, user=Depends(get_current_user)):
    """
    Recibe JSON con node_id, success, clients, uptime, point_a/b/c. Redis: contador de fallos y hash con datos.
    Si success es true -> reset contador. Si fallos llegan a ALERT_THRESHOLD -> reinicio automático por SSH.
    Requiere JWT (panel / integración autenticada). El poller interno no usa esta ruta.
    """
    try:
        try:
            payload = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Body debe ser JSON válido: {e}")
        if not isinstance(payload, dict):
            payload = {}
        raw_id = payload.get("node_id") or payload.get("ip") or payload.get("id")
        if not raw_id:
            raise HTTPException(status_code=400, detail="Se requiere node_id, ip o id")
        node_id = str(raw_id).strip()

        success = _normalize_success(payload)
        if not success:
            logger.info("[HEARTBEAT] %s success=false (fallo reportado)", node_id)
        r = get_redis()
        if r is None:
            raise HTTPException(status_code=503, detail="Redis no disponible")

        _save_node_data_redis(r, node_id, payload)

        key = f"{FAILURES_KEY_PREFIX}{node_id}"

        if success:
            r.delete(key)
            logger.debug("[HEARTBEAT] %s → success=True | fallos reseteados a 0", node_id)
            return {"success": True, "node_id": node_id, "failures": 0, "message": "Contador reseteado"}

        r.incr(key)
        count = int(r.get(key) or 1)
        _threshold, _cooldown = _get_guardian_thresholds()
        logger.debug("[HEARTBEAT] %s → success=False | fallos acumulados=%d / umbral=%d", node_id, count, _threshold)

        maintenance_on = False
        try:
            if r.get(MAINTENANCE_KEY) == "1":
                maintenance_on = True
            elif r.get(f"{NODE_MAINTENANCE_PREFIX}{node_id}") == "1":
                maintenance_on = True
        except Exception:
            pass
        if not maintenance_on and count >= _threshold:
            now_ts = int(datetime.utcnow().timestamp())
            lr_key = f"{LAST_REBOOT_KEY_PREFIX}{node_id}"
            last_ts_raw = r.get(lr_key)
            if last_ts_raw is not None:
                try:
                    last_ts = int(last_ts_raw)
                    delta = now_ts - last_ts
                    if delta < _cooldown:
                        msg_cooldown = f"Nodo {node_id}: {count} fallos, cooldown {delta}s/{_cooldown}s — no se reinicia"
                        logger.info("[COOLDOWN] %s", msg_cooldown)
                        log_event(r, "info", "COOLDOWN", msg_cooldown)
                        return {
                            "success": True,
                            "node_id": node_id,
                            "failures": count,
                            "message": "En cooldown, no se reinicia.",
                        }
                except Exception:
                    pass

            ok, msg = await asyncio.to_thread(_run_ssh_reboot, node_id)
            if ok:
                r.set(LAST_REBOOT_KEY_PREFIX + node_id, str(now_ts))
                logger.info("[AUTO-REBOOT] Nodo %s: %s", node_id, msg)
                send_telegram_safe(
                    f"⚡ <b>REINICIO EN PROGRESO</b> SHOMER: Nodo {node_id} reiniciado automáticamente — {count} fallos detectados"
                )
                log_event(
                    r,
                    "warning",
                    "AUTO-REBOOT",
                    f"Nodo {node_id} reiniciado automáticamente — {count} fallos detectados",
                )
                return {
                    "success": True,
                    "node_id": node_id,
                    "failures": count,
                    "message": "Reboot automático enviado",
                }
            logger.warning("[AUTO-REBOOT-ERROR] Nodo %s: %s", node_id, msg)
            send_telegram_safe(f"🚨 <b>PÉRDIDA DE SERVICIO</b> SHOMER: Fallo al reiniciar {node_id} — {msg}")
            log_event(r, "error", "AUTO-REBOOT", f"Fallo al reiniciar {node_id}: {msg}")
            return {
                "success": False,
                "node_id": node_id,
                "failures": count,
                "message": f"No se pudo reiniciar: {msg}",
            }
        elif maintenance_on and count >= _threshold:
            scope = "nodo" if r.get(f"{NODE_MAINTENANCE_PREFIX}{node_id}") == "1" else "global"
            msg_maint = f"Nodo {node_id}: {count} fallos — reinicio omitido (mantenimiento {scope} activo)"
            logger.info("[MANTENIMIENTO] %s", msg_maint)
            log_event(r, "info", "MANTENIMIENTO", msg_maint)
        return {"success": True, "node_id": node_id, "failures": count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset_failures/{ip}")
async def reset_failures(ip: str, user=Depends(get_current_user)):
    """Borra el contador de fallos del nodo en Redis."""
    ip = ip.strip()
    if not ALLOWED_IP_PATTERN.match(ip):
        raise HTTPException(status_code=400, detail="IP no válida")
    r = get_redis()
    if r is None:
        raise HTTPException(status_code=503, detail="Redis no disponible")
    key = f"{FAILURES_KEY_PREFIX}{ip}"
    r.delete(key)
    log_event(r, "info", "GUARDIAN", f"Fallos reseteados manualmente para {ip}")
    return {"success": True, "ip": ip, "failures": 0, "message": "Contador de fallos reseteado"}


@router.post("/reboot/{ip}")
async def reboot_node(ip: str, user=Depends(get_current_user)):
    """Reinicio manual del nodo por IP.

    Actualiza `last_reboot:{ip}` y resetea `failures:{ip}` para que el poller
    respete el cooldown y no dispare un AUTO-REBOOT redundante sobre un AP que
    aún está arrancando. Respeta `shomer_maintenance=1` (kill-switch).
    """
    ip = ip.strip()
    if not ALLOWED_IP_PATTERN.match(ip):
        raise HTTPException(status_code=400, detail="IP no válida")

    r = get_redis()
    if r is not None:
        try:
            if r.get(MAINTENANCE_KEY) == "1":
                raise HTTPException(
                    status_code=423,
                    detail="Modo mantenimiento activo — reboot manual rechazado",
                )
        except HTTPException:
            raise
        except Exception:
            pass

    ok, msg = await asyncio.to_thread(_run_ssh_reboot, ip)
    if not ok:
        if r is not None:
            log_event(r, "error", "MANUAL-REBOOT", f"Fallo al reiniciar manualmente {ip}: {msg}")
        send_telegram_safe(
            f"🚨 <b>PÉRDIDA DE SERVICIO</b> SHOMER: Fallo reboot manual {ip} — {msg}"
        )
        raise HTTPException(status_code=502, detail=msg)

    if r is not None:
        try:
            now_ts = int(datetime.utcnow().timestamp())
            r.set(f"{LAST_REBOOT_KEY_PREFIX}{ip}", str(now_ts))
            r.delete(f"{FAILURES_KEY_PREFIX}{ip}")
            log_event(r, "warning", "MANUAL-REBOOT", f"Reboot manual enviado a {ip}")
        except Exception as e:
            logger.debug("reboot_node bookkeeping: %s", e)

    send_telegram_safe(f"⚡ <b>REINICIO EN PROGRESO</b> SHOMER: Reboot manual enviado a {ip}")
    return {"success": True, "ip": ip, "message": msg}


@router.get("/logs")
async def get_logs(limit: int = 50, user=Depends(get_current_user)):
    """
    Últimos N registros de la tabla infra_nodes en SQLite.
    Por defecto 50. Ejecuta prune de event_log (>30 días) como máximo cada hora.
    """
    _prune_old_logs()
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT ip_address, status, latency_ms, last_heartbeat
                FROM infra_nodes
                ORDER BY last_heartbeat DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
        items = [dict(r) for r in rows]
        return {"success": True, "count": len(items), "logs": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


_infra_heartbeat_col_ready = False


def ensure_infra_nodes_heartbeat_column() -> None:
    """Migración de una sola vez (llamada desde lifespan, no desde /health).

    Instalaciones viejas crearon `infra_nodes` sin `shomer-monitor.service` activo
    -- esa tabla quedó con el esquema antiguo (`last_seen`, sin `last_heartbeat`).
    `_health_db_read()` asume que `last_heartbeat` existe; sin esta migración /health
    devuelve 503 permanente y el watchdog reinicia Guardian en loop sin resolver nada
    (encontrado en shomer245/shomer243, jun 2026 -- nunca habían corrido monitor.py).
    """
    global _infra_heartbeat_col_ready
    if _infra_heartbeat_col_ready:
        return
    try:
        from app.backend.db import connect as _connect
        conn = _connect(timeout=10)
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(infra_nodes)").fetchall()}
            if cols and "last_heartbeat" not in cols:
                conn.execute("ALTER TABLE infra_nodes ADD COLUMN last_heartbeat TIMESTAMP")
                if "last_seen" in cols:
                    conn.execute(
                        "UPDATE infra_nodes SET last_heartbeat = last_seen WHERE last_heartbeat IS NULL"
                    )
                conn.commit()
                logger.warning("infra_nodes: columna last_heartbeat agregada (esquema viejo detectado)")
        finally:
            conn.close()
    except Exception as e:
        logger.debug("ensure_infra_nodes_heartbeat_column: %s", e)
    _infra_heartbeat_col_ready = True


def _health_db_read() -> int:
    """Lectura rápida y aislada — busy_timeout corto para no colgar /health
    si otro proceso (Guardian/Hunter/Inframonitor) está escribiendo en network_monitor.db.
    La tabla infra_nodes ya se crea al arrancar (app/scripts/monitor.py) — no se
    recrea aquí en cada chequeo para mantener esta ruta 100% de solo lectura."""
    from app.backend.db import connect as _connect
    conn = _connect(timeout=2)
    try:
        cutoff = (datetime.utcnow() - timedelta(seconds=MONITOR_RECENT_SEC)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        row = conn.execute(
            "SELECT COUNT(*) FROM infra_nodes WHERE last_heartbeat >= ?",
            (cutoff,),
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


@router.get("/health")
async def health():
    """
    Comprueba que el monitor y Redis están respondiendo.
    Redis: ping. Monitor: verifica datos recientes en infra_nodes (últimos 2 min).
    Corre en thread aparte — si SQLite está ocupado, no congela el event loop
    ni el resto de la API mientras este chequeo espera.
    """
    r = get_redis()
    if r is None:
        raise HTTPException(status_code=503, detail="Redis no disponible")
    try:
        r.ping()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Redis ping error: {e}")

    try:
        recent = await asyncio.to_thread(_health_db_read)
        return {"success": True, "redis": "ok", "recent_nodes": recent}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"SQLite ocupado/error: {e}")
