"""
Inframonitor -- endpoints HTTP (`/infra/*`) para el panel: alta/baja/edicion
de equipos, estado en vivo, datos SNMP puntuales y acciones manuales.

El sondeo de red/SNMP y el ciclo del poller viven en
shomer_inframonitor_poller.py (separado el 12 sep 2026, particion calculada
con la clausura transitiva real de referencias, no a mano -- un primer
intento a mano se salto varias cosas: asyncio.to_thread(func) pasa `func`
como argumento, no es una "llamada" directa, y una clase (DeviceEdit) que
vivia entre dos endpoints tampoco aparecia en un primer barrido por
funciones). Solo 4 nombres cruzan la frontera, importados de alla:
_init_tables, _sync_guardian_aps, _ping y start_inframonitor_poller
(re-exportado para que main.py no cambie su import).
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.api.auth_api import get_current_user
from app.api.shomer_common import get_db, get_redis
from app.api.infra_monitor_profiles import resolve_monitor_profile
from app.api.shomer_infra_pulse import ensure_pulse_table, mark_pulse_alerted, pulse_enabled
from app.api.shomer_pulse_correlate import read_last_blip, read_poll_context
from app.api.shomer_inframonitor_poller import (
    _init_tables,
    _sync_guardian_aps,
    _ping,
    start_inframonitor_poller,  # noqa: F401 -- re-exportado, main.py lo importa de aca
)

logger = logging.getLogger(__name__)

_security = HTTPBearer(auto_error=False)
router = APIRouter(tags=["inframonitor"])


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


def _calc_uptime_24h_batch(conn, ips: list, status_map: dict) -> dict:
    """2 queries para todos los IPs; devuelve {ip: uptime_pct}. Evita N×2 queries en /infra/devices."""
    if not ips:
        return {}
    ph = ",".join("?" * len(ips))
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=24)
    # Solo online/offline representan un cambio real de alcanzabilidad -- eventos como
    # degraded/pulse_degrading/pulse_recovered no deben "atascar" el estado del cálculo
    # (bug detectado: dejaban el uptime en ~0% aunque el equipo siguiera online).
    rows_in = conn.execute(
        f"SELECT ip, event, ts FROM infra_events WHERE ip IN ({ph}) "
        f"AND event IN ('online','offline') "
        f"AND ts >= datetime('now','-24 hours') ORDER BY ip, ts",
        ips,
    ).fetchall()
    prev_rows = conn.execute(
        f"""SELECT ip, event FROM infra_events ie
            WHERE ip IN ({ph})
              AND event IN ('online','offline')
              AND ts = (SELECT max(ts) FROM infra_events WHERE ip=ie.ip
                        AND event IN ('online','offline')
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


class DeviceIn(BaseModel):
    ip: str
    name: str
    device_type: str = "generic"
    location: str = ""
    tcp_port: Optional[int] = None
    snmp_community: str = "public"
    pc_server_ip: Optional[str] = None
    # Cámaras/NVR: ruta RTSP del fabricante (sin hardcodear marca, norma B.1).
    rtsp_path: str = ""


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
        "rtsp_path": d["rtsp_path"] if "rtsp_path" in d.keys() else "",
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
        # Caídas REALES de las últimas 24h -> historial (infra_events), no el
        # estado actual. La versión anterior consultaba infra_status, que tiene
        # UNA fila por IP con el estado de AHORA y un checked_at reescrito en
        # cada ciclo (30s): la condición de 24h se cumplía siempre, así que el
        # número no era "caídas en 24h" sino "equipos caídos en este instante".
        # Medido en Ópera al detectarlo: mostraba 1 cuando en 24h hubo 11
        # caídas reales sobre 10 equipos distintos. Se cuenta por equipo
        # distinto para que cuadre con el badge por fila (mismo origen).
        row = conn.execute(
            "SELECT COUNT(DISTINCT ip) FROM infra_events "
            "WHERE event='offline' AND ts > datetime('now', '-24 hours')"
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
                "(ip, name, device_type, location, tcp_port, snmp_community, pc_server_ip, "
                "monitor_profile, rtsp_path) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (body.ip, body.name, body.device_type, body.location, body.tcp_port,
                 body.snmp_community or "public", body.pc_server_ip or None, profile,
                 (body.rtsp_path or "").strip())
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


class DeviceEdit(BaseModel):
    name: Optional[str] = None
    device_type: Optional[str] = None
    location: Optional[str] = None
    # Editables desde Sesión 82: sin esto, un campo que solo se podía fijar al
    # CREAR el equipo quedaba congelado para siempre. Caso real en Ópera: los 6
    # equipos printer/pos tenían pc_server_ip vacío, así que el botón "Cola"
    # (limpiar cola de impresión) no aparecía en ninguna fila y no había forma
    # de arreglarlo sin borrar y recrear el equipo (perdiendo su historial) o
    # editar la BD a mano.
    pc_server_ip: Optional[str] = None
    tcp_port: Optional[int] = None
    snmp_community: Optional[str] = None
    rtsp_path: Optional[str] = None


@router.patch("/infra/devices/{device_id}")
async def edit_device(device_id: int, body: DeviceEdit, user=Depends(get_current_user)):
    """Editar nombre/tipo/ubicación/PC de impresión/puerto TCP/comunidad SNMP de
    un equipo ya existente -- pedido Juan Pablo (3 sep 2026): antes solo se podía
    fijar el tipo al crear el equipo, sin forma de corregirlo después (necesario
    para marcar criticidad de negocio, Tarea pendiente 2 opción 4, sin depender
    de editar la BD a mano)."""
    if body.device_type is not None and body.device_type not in DEVICE_ICONS:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Opciones: {list(DEVICE_ICONS.keys())}")

    campos, valores = [], []
    if body.name is not None:
        nombre = body.name.strip()
        if not nombre:
            raise HTTPException(status_code=400, detail="Nombre no puede estar vacío")
        campos.append("name = ?"); valores.append(nombre)
    if body.device_type is not None:
        campos.append("device_type = ?"); valores.append(body.device_type)
    if body.location is not None:
        campos.append("location = ?"); valores.append(body.location.strip())
    if body.pc_server_ip is not None:
        pc_ip = body.pc_server_ip.strip()
        if pc_ip:
            import ipaddress
            try:
                ipaddress.ip_address(pc_ip)
            except ValueError:
                raise HTTPException(status_code=400, detail="IP del PC de impresión inválida")
        campos.append("pc_server_ip = ?"); valores.append(pc_ip or None)
    if body.tcp_port is not None:
        # 0 = limpiar el puerto (JSON no distingue "no enviado" de "borrar")
        if body.tcp_port == 0:
            campos.append("tcp_port = ?"); valores.append(None)
        elif not (1 <= body.tcp_port <= 65535):
            raise HTTPException(status_code=400, detail="Puerto TCP inválido (1-65535)")
        else:
            campos.append("tcp_port = ?"); valores.append(body.tcp_port)
    if body.snmp_community is not None:
        campos.append("snmp_community = ?"); valores.append(body.snmp_community.strip())
    if body.rtsp_path is not None:
        campos.append("rtsp_path = ?"); valores.append(body.rtsp_path.strip())
    if not campos:
        raise HTTPException(status_code=400, detail="Nada para actualizar")

    # monitor_profile se deriva de device_type/tcp_port/snmp_community: si
    # cambió alguno, hay que recalcularlo o el equipo sigue evaluándose con el
    # perfil viejo (ej. pasar un genérico a switch con SNMP y que igual se
    # decida su estado solo por ping).
    if any(f.startswith(("device_type", "tcp_port", "snmp_community")) for f in campos):
        campos.append("monitor_profile = ''")

    _init_tables()
    valores.append(device_id)
    with get_db() as conn:
        cur = conn.execute(f"UPDATE infra_devices SET {', '.join(campos)} WHERE id = ?", valores)
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Equipo no encontrado")
    return {"success": True, "message": "Equipo actualizado"}


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
    action=stream_url   → devuelve URL de stream RTSP de la cámara (usa rtsp_path del equipo)

    El reinicio por SNMP vive en Guardian (shomer_guardian_lib._run_snmp_reboot),
    no acá: duplicarlo para el mismo hardware solo daba dos caminos divergentes.
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

    # snmp_reboot eliminado (auditoría Sesión 82, decisión de Juan Pablo): era
    # inalcanzable -- sin botón en la UI, snmp_community_write vacío en los 51
    # equipos y no configurable, y su OID era específico de TP-Link EAP, pero
    # los APs TP-Link los reinicia Guardian con su propia ruta SNMP. Mantener
    # dos caminos de reinicio para el mismo hardware no aporta.

    # ── URL stream cámara ────────────────────────────────────────────────────
    elif action == "stream_url":
        if dtype != "camera":
            raise HTTPException(status_code=400, detail="Solo disponible para cámaras")
        # La ruta RTSP depende del fabricante (Hikvision usa
        # /Streaming/Channels/101, otros /stream1, /h264/ch1/main/av_stream...)
        # y del canal del NVR, así que se configura por equipo. Sin ruta no se
        # inventa una: se dice qué falta y dónde ponerla.
        rtsp_path = (dev.get("rtsp_path") or "").strip()
        if not rtsp_path:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Este equipo no tiene ruta RTSP configurada. Edítalo y agrega la "
                    "ruta de tu fabricante — Hikvision: /Streaming/Channels/101 · "
                    "Dahua: /cam/realmonitor?channel=1&subtype=0 · genérica: /stream1"
                ),
            )
        rtsp_url = f"rtsp://{ip}:554/{rtsp_path.lstrip('/')}"
        return {
            "success": True,
            "stream_url": rtsp_url,
            "message": f"Abre esta URL en VLC: {rtsp_url}",
            "note": "Si el equipo pide autenticación, usa rtsp://usuario:clave@" + ip + ":554/" + rtsp_path.lstrip("/"),
        }

    else:
        raise HTTPException(status_code=400, detail=f"Acción desconocida: {action}")

