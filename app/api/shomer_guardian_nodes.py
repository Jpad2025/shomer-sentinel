"""Guardian — nodos, heartbeat, reboot, logs, health."""
import asyncio
import logging
import os
import subprocess
from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.auth_api import get_current_user
from app.api.shomer_common import _prune_old_logs, get_db, get_redis
from app.api.shomer_guardian_health_checks import (
    DEGRADED_NOTIFY_KEY_PREFIX,
    DEGRADED_STREAK_KEY_PREFIX,
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
from app.api.shomer_status_events import record_status_event

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Shomer Guardian"])

_POLL_INTERVAL_SEC = int(os.environ.get("SHOMER_POLL_INTERVAL_SEC", "10"))
_poller_task = None


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


async def _poller_tick() -> None:
    r = get_redis()
    if r is None:
        return

    devices = await asyncio.to_thread(_get_devices_for_poll)

    # Limpiar claves Redis huérfanas (de dispositivos ya eliminados de `devices`)
    # en lugar de re-incluirlas en el sondeo: re-incluirlas regenera la propia
    # clave en cada ciclo y perpetúa el "fantasma" indefinidamente (bug Sesión 49).
    known_ips = {d["ip_address"] for d in devices}
    try:
        with get_db() as conn:
            all_ips = {row[0] for row in conn.execute("SELECT ip_address FROM devices").fetchall()}
        for key in r.keys("status:*"):
            ip = key.replace("status:", "")
            if ip not in all_ips:
                for prefix in ("status:", "failures:", "last_reboot:", "node_maintenance:",
                               "degraded_notified:", "degraded_streak:"):
                    r.delete(f"{prefix}{ip}")
    except Exception:
        pass

    if not devices:
        return

    threshold, cooldown = _get_guardian_thresholds()
    health_cfg = _get_health_config()
    tick_results: List[Dict[str, Any]] = []
    batch_id = f"g-{int(datetime.utcnow().timestamp())}"

    for dev in devices:
        ip = dev["ip_address"]
        dev_name = dev.get("name") or ip
        dev_type = dev.get("device_type") or "generic"
        try:
            prev_redis = r.get(f"status:{ip}") or "unknown"
            lan_ok, lan_loss, lan_rtt = await asyncio.to_thread(
                _ping_metrics, ip, health_cfg["ping_count"]
            )

            is_snmp_device = dev.get("reboot_method") == "snmp"
            # Solo routers/gateways reciben probes WAN (ping 8.8.8.8, DNS, HTTP) vía SSH.
            # APs con reboot_method=ssh NO son routers — probes WAN en UniFi generaban
            # falsos no-internet/degraded (Sesión Ópera jun 2026).
            is_router = not is_snmp_device and dev.get("device_type") in (
                "router", "gateway"
            )

            ssh_result: Any = None
            snmp_result: Any = None

            if lan_ok and is_router:
                ssh_user = dev.get("ssh_user") or "root"
                ssh_port = int(dev.get("ssh_port") or 22)
                ssh_pwd = dev.get("ssh_password") or ""
                ssh_result = await asyncio.to_thread(
                    _ssh_health_probes, ip, ssh_user, ssh_port, ssh_pwd, health_cfg,
                )
            elif lan_ok and is_snmp_device:
                snmp_community = dev.get("snmp_community") or "public"
                snmp_result = await asyncio.to_thread(
                    _snmp_health_probes, ip, snmp_community,
                )

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

            key = f"{FAILURES_KEY_PREFIX}{ip}"
            streak_key = f"{DEGRADED_STREAK_KEY_PREFIX}{ip}"

            lat_ms = int(round(lan_rtt)) if lan_rtt is not None else None

            if status_label == "online":
                if prev_redis != "online":
                    record_status_event(
                        source="guardian",
                        ip=ip,
                        name=dev_name,
                        device_type=dev_type,
                        prev_status=prev_redis,
                        status="online",
                        reason="ping OK",
                        latency_ms=lat_ms,
                        loss_pct=lan_loss,
                        batch_id=batch_id,
                    )
                r.set(f"status:{ip}", "online")
                r.delete(key)
                r.delete(streak_key)
                # NO borrar DEGRADED_NOTIFY_KEY_PREFIX: dejamos que expire por su TTL.
                # Así oscilaciones degraded↔online no spammean Telegram en cada rebote.
                tick_results.append({"ip": ip, "status": "online", "latency_ms": lat_ms})
                continue

            if status_label == "degraded":
                r.delete(key)
                streak = r.incr(streak_key)
                r.expire(streak_key, max(cooldown, 60))
                persist = int(health_cfg.get("degraded_persist_ticks") or 3)
                if streak < persist:
                    # condición transitoria — mantener estado anterior, no alertar aún
                    prev = r.get(f"status:{ip}") or "online"
                    tick_results.append({"ip": ip, "status": prev, "latency_ms": lat_ms})
                    continue
                if prev_redis != "degraded":
                    record_status_event(
                        source="guardian",
                        ip=ip,
                        name=dev_name,
                        device_type=dev_type,
                        prev_status=prev_redis,
                        status="degraded",
                        reason=reason,
                        latency_ms=lat_ms,
                        loss_pct=lan_loss,
                        batch_id=batch_id,
                    )
                r.set(f"status:{ip}", "degraded")
                notify_key = f"{DEGRADED_NOTIFY_KEY_PREFIX}{ip}"
                alert_cooldown = int(health_cfg.get("degraded_alert_cooldown_sec") or 1800)
                if not r.get(notify_key):
                    r.set(notify_key, "1", ex=alert_cooldown)
                    send_telegram_safe(
                        f"🟡 <b>CALIDAD DEGRADADA</b> SHOMER: Nodo {ip} — {reason} "
                        f"({streak} ticks sostenidos)"
                    )
                    log_event(r, "warning", "DEGRADED", f"Nodo {ip} degradado: {reason}")
                tick_results.append({"ip": ip, "status": "degraded", "latency_ms": lat_ms})
                continue

            if prev_redis != status_label:
                record_status_event(
                    source="guardian",
                    ip=ip,
                    name=dev_name,
                    device_type=dev_type,
                    prev_status=prev_redis,
                    status=status_label,
                    reason=reason,
                    latency_ms=lat_ms,
                    loss_pct=lan_loss,
                    batch_id=batch_id,
                )
            r.set(f"status:{ip}", status_label)
            r.delete(streak_key)
            tick_results.append({"ip": ip, "status": status_label, "latency_ms": lat_ms})

            if r.get(MAINTENANCE_KEY) == "1":
                continue
            if r.get(f"{NODE_MAINTENANCE_PREFIX}{ip}") == "1":
                continue

            r.incr(key)
            count = int(r.get(key) or 1)
            logger.info(
                "[POLLER] %s → %s | fallos: %d/%d | %s",
                ip, status_label, count, threshold, reason,
            )

            if count < threshold:
                continue

            now_ts = int(datetime.utcnow().timestamp())
            lr_key = f"{LAST_REBOOT_KEY_PREFIX}{ip}"
            last_raw = r.get(lr_key)
            if last_raw:
                try:
                    if now_ts - int(last_raw) < cooldown:
                        continue
                except Exception:
                    pass

            dev_name = dev.get("name") or ip
            reboot_via = "SNMP" if dev.get("reboot_method") == "snmp" else "SSH"
            ok, msg = _run_ssh_reboot(ip)
            r.set(lr_key, str(now_ts))  # siempre registrar intento para que cooldown arranque
            if ok:
                send_telegram_safe(
                    f"⚡ <b>REINICIO EN PROGRESO</b> SHOMER\n"
                    f"<b>Equipo:</b> {dev_name} ({ip})\n"
                    f"<b>Motivo:</b> {reason}\n"
                    f"<b>Fallos:</b> {count} consecutivos\n"
                    f"<b>Vía:</b> {reboot_via} — {msg}"
                )
                log_event(
                    r, "warning", "AUTO-REBOOT",
                    f"{dev_name} ({ip}) reiniciado — motivo: {reason}, {count} fallos",
                )
            else:
                send_telegram_safe(
                    f"🚨 <b>PÉRDIDA DE SERVICIO</b> SHOMER\n"
                    f"<b>Equipo:</b> {dev_name} ({ip})\n"
                    f"<b>Error al reiniciar:</b> {msg}\n"
                    f"<b>Motivo:</b> {reason} — {count} fallos consecutivos"
                )
                log_event(r, "error", "AUTO-REBOOT", f"Fallo al reiniciar {dev_name} ({ip}): {msg}")
        except Exception as e:
            logger.warning("Poller error en %s: %s", ip, e)
            tick_results.append({"ip": ip, "status": "unknown", "latency_ms": None})

    await asyncio.to_thread(_update_infra_nodes, tick_results)


async def _poller_loop() -> None:
    await asyncio.sleep(5)
    while True:
        try:
            await _poller_tick()
        except Exception as e:
            logger.warning("Poller loop error: %s", e)
        await asyncio.sleep(_POLL_INTERVAL_SEC)


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
async def heartbeat(request: Request):
    """
    Recibe JSON con node_id, success, clients, uptime, point_a/b/c. Redis: contador de fallos y hash con datos.
    Si success es true -> reset contador. Si fallos llegan a ALERT_THRESHOLD -> reinicio automático por SSH.
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

            ok, msg = _run_ssh_reboot(node_id)
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

    ok, msg = _run_ssh_reboot(ip)
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


@router.get("/health")
async def health():
    """
    Comprueba que el monitor y Redis están respondiendo.
    Redis: ping. Monitor: verifica datos recientes en infra_nodes (últimos 2 min).
    """
    r = get_redis()
    if r is None:
        raise HTTPException(status_code=503, detail="Redis no disponible")
    try:
        r.ping()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Redis ping error: {e}")

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS infra_nodes "
                "(ip_address TEXT PRIMARY KEY, status TEXT, last_heartbeat TIMESTAMP, latency_ms REAL)"
            )
            cutoff = (datetime.utcnow() - timedelta(seconds=MONITOR_RECENT_SEC)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            cur.execute(
                "SELECT COUNT(*) FROM infra_nodes WHERE last_heartbeat >= ?",
                (cutoff,),
            )
            row = cur.fetchone()
        return {"success": True, "redis": "ok", "recent_nodes": row[0] if row else 0}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQLite error: {e}")
