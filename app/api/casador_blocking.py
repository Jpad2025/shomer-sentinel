"""Casador — bloqueo firewall, lista blocked_ips, circuit breaker."""
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

_log = logging.getLogger("shomer.casador")

from fastapi import APIRouter, Body, Depends, Header, HTTPException

from app.api.auth_api import get_current_user

from app.api.casador_support import (
    _cb_record_success,
    _get_config,
    _get_redis,
    _is_blocked,
    _is_external_ip,
    _mikrotik_block,
    _mikrotik_sync_block,
    _mikrotik_unblock,
    _require_hunter,
    _CB_FAIL_KEY,
    _CB_STATUS_KEY,
    _CB_THRESHOLD,
)
from app.api.casador_support_hunter_recurrence import (
    hunter_high_recurrence_warn_telegram,
    hunter_recurrence_bump,
)
from app.backend.db import get_connection

router = APIRouter()


def _to_int(v: Any, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _auto_block_policy() -> Dict[str, Any]:
    """
    Política de autobloqueo configurable desde system_state.
    Defaults prudentes para producción:
    - enabled: true
    - min_severity: 2 (critical/high)
    - only_external: true
    - exceptions: [] (IPs o subredes en CIDR)
    """
    return {
        "enabled": bool(_get_config("hunter.auto_block_enabled", False)),
        "min_severity": _to_int(_get_config("hunter.auto_block_min_severity", 2), 2),
        "only_external": bool(_get_config("hunter.auto_block_only_external", True)),
        "exceptions": _get_config("hunter.auto_block_exceptions", []) or [],
        # ALTA: N eventos en ventana (Suricata → panel); 1 = sin requisito extra. CRITICAL (1) no usa esto.
        "high_recurrence_min": _to_int(_get_config("hunter.high_recurrence_min", 3), 3),
        "high_recurrence_window_sec": _to_int(
            _get_config("hunter.high_recurrence_window_sec", 600), 600
        ),
        "high_recurrence_warn_at": _to_int(
            _get_config("hunter.high_recurrence_warn_at", 2), 2
        ),
    }


def _ip_in_exceptions(ip: str, exceptions: Any) -> bool:
    import ipaddress

    if not isinstance(exceptions, list):
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except Exception:
        return False
    for item in exceptions:
        raw = str(item or "").strip()
        if not raw:
            continue
        try:
            if "/" in raw:
                if addr in ipaddress.ip_network(raw, strict=False):
                    return True
            elif raw == ip:
                return True
        except Exception:
            continue
    return False


def _wazuh_integration_key_configured() -> bool:
    if (os.environ.get("SHOMER_WAZUH_INTEGRATION_KEY") or "").strip():
        return True
    v = _get_config("hunter.integration_key", "")
    return bool((str(v) if v is not None else "").strip())


def _wazuh_integration_key_match(provided: Optional[str]) -> bool:
    p = (provided or "").strip()
    if not p:
        return False
    env_k = (os.environ.get("SHOMER_WAZUH_INTEGRATION_KEY") or "").strip()
    if env_k and p == env_k:
        return True
    cfg = (str(_get_config("hunter.integration_key", "") or "")).strip()
    if cfg and p == cfg:
        return True
    return False


@router.post("/block")
async def block_ip(
    body: Dict[str, Any] = Body(...),
    x_shomer_integration_key: Optional[str] = Header(default=None, alias="X-Shomer-Integration-Key"),
):
    """
    Bloquea una IP en el firewall y la registra en BD.
    Wazuh → Shomer: `blocked_by: "wazuh"` + cabecera `X-Shomer-Integration-Key` (misma clave que
    `hunter.integration_key` en BD o variable `SHOMER_WAZUH_INTEGRATION_KEY`).
    """
    _require_hunter()
    ip = (body.get("ip") or "").strip()
    blocked_by = (body.get("blocked_by") or "manual").strip().lower()
    if blocked_by not in ("manual", "auto", "wazuh"):
        blocked_by = "manual"
    alert_sid = body.get("alert_sid")
    alert_signature = body.get("alert_signature", "")
    severity = body.get("severity", 3)

    if not ip:
        raise HTTPException(status_code=400, detail="IP requerida")
    try:
        import ipaddress as _ipa; _ipa.ip_address(ip)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Formato de IP inválido: {ip}")

    # Cadena Wazuh → Shomer: filtrado/escalado en Wazuh; aquí solo confianza + excepciones globales.
    if blocked_by == "wazuh":
        if not _wazuh_integration_key_configured():
            raise HTTPException(
                status_code=503,
                detail="Integración Wazuh: configure SHOMER_WAZUH_INTEGRATION_KEY o hunter.integration_key en Shomer",
            )
        if not _wazuh_integration_key_match(x_shomer_integration_key):
            raise HTTPException(status_code=401, detail="X-Shomer-Integration-Key inválida o ausente")
        policy = _auto_block_policy()
        if _ip_in_exceptions(ip, policy["exceptions"]):
            return {
                "success": False,
                "skipped": True,
                "detail": "IP en lista de excepciones (hunter.auto_block_exceptions)",
            }

    # Defensa en backend: el autobloqueo NO depende solo del frontend.
    if blocked_by == "auto":
        policy = _auto_block_policy()
        if not policy["enabled"]:
            return {
                "success": False,
                "skipped": True,
                "detail": "Autobloqueo deshabilitado por política",
            }
        sev_i = _to_int(severity, 3)
        if sev_i > int(policy["min_severity"]):
            return {
                "success": False,
                "skipped": True,
                "detail": f"Severidad fuera de política (min <= {policy['min_severity']})",
            }
        # Solo externas, excepto crítico (1): en interna solo autobloquea CRITICAL.
        if policy["only_external"] and not _is_external_ip(ip) and sev_i != 1:
            return {
                "success": False,
                "skipped": True,
                "detail": "IP interna; autobloqueo automático no aplica a esta severidad (use manual o ajuste política)",
            }
        if _ip_in_exceptions(ip, policy["exceptions"]):
            return {
                "success": False,
                "skipped": True,
                "detail": "IP en lista de excepciones de autobloqueo",
            }
        # ALTA (2): requiere N eventos en ventana (recurrencia = ataque sostenido). CRITICAL/otras: sin esto.
        hmin = max(1, int(policy.get("high_recurrence_min") or 1))
        wsec = max(30, int(policy.get("high_recurrence_window_sec") or 600))
        warn_at = int(policy.get("high_recurrence_warn_at") or 0)
        if sev_i == 2 and hmin > 1:
            cnt = hunter_recurrence_bump(
                ip, alert_sid, str(alert_signature or ""), wsec
            )
            if cnt is None:
                return {
                    "success": False,
                    "skipped": True,
                    "detail": "Redis requerido para contar recurrencia de alertas ALTA (autobloqueo)",
                }
            if warn_at > 0:
                hunter_high_recurrence_warn_telegram(
                    ip, alert_sid, str(alert_signature or ""),
                    cnt, warn_at, wsec,
                )
            if cnt < hmin:
                return {
                    "success": False,
                    "skipped": True,
                    "detail": f"ALTA: recurrencia {cnt}/{hmin} en {wsec}s (misma IP/regla) — requisito de política",
                }

    if _is_blocked(ip):
        if blocked_by == "wazuh":
            _log.warning(
                "Bloqueo Wazuh: %s ya estaba en lista — no se envía Telegram (evento atendido, sin re-notificar)",
                ip,
            )
        return {"success": True, "message": f"{ip} ya estaba bloqueada", "already_blocked": True}

    ok, msg = await _mikrotik_block(ip)
    if not ok:
        firewall_not_configured = "no configurada" in msg or "no configurado" in msg
        if not firewall_not_configured:
            _log.error(
                "Firewall block FAILED para %s — BD no actualizada, IP NO bloqueada en firewall. Causa: %s",
                ip, msg,
            )
            return {
                "success": False,
                "firewall_ok": False,
                "ip": ip,
                "message": msg,
                "detail": "Bloqueo en firewall falló — IP no registrada en BD",
            }
        # Firewall no configurado: modo solo-BD (monitoreo sin firewall)
        _log.warning("Firewall no configurado — %s solo se registrará en BD sin bloqueo real en red", ip)

    try:
        with get_connection(timeout=10) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO blocked_ips (ip, blocked_at, blocked_by, alert_sid, alert_signature, severity, firewall_blocked) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    ip,
                    datetime.now(timezone.utc).isoformat(),
                    blocked_by,
                    alert_sid,
                    alert_signature,
                    severity,
                    1 if ok else 0,
                ),
            )
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    telegram_sent: Optional[bool] = None
    if blocked_by in ("auto", "wazuh"):
        try:
            from app.scripts.alerts import send_telegram_alert

            sev_label = {1: "🔴 CRÍTICA", 2: "🟠 ALTA", 3: "🟡 MEDIA"}.get(int(severity or 3), "⚪ BAJA")
            sig_text = f"\n📋 Regla: {alert_signature}" if alert_signature else ""
            fw_text = "✅ Firewall bloqueado" if ok else "⚠️ Firewall no disponible — solo registrado en BD"
            if blocked_by == "wazuh":
                title = "🛡️ <b>BLOQUEO (Wazuh → Shomer)</b>"
            else:
                title = "🚨 <b>BLOQUEO AUTOMÁTICO</b>"
            telegram_sent = bool(
                send_telegram_alert(
                    f"{title}\n"
                    f"🌐 IP: <code>{ip}</code>\n"
                    f"⚡ Severidad: {sev_label}{sig_text}\n"
                    f"{fw_text}"
                )
            )
            if not telegram_sent:
                _log.warning("Telegram: no se envió aviso de bloqueo (token/chat, filtro o API Telegram). blocked_by=%s", blocked_by)
        except Exception as ex:
            _log.warning("Telegram: excepción al enviar: %s", ex)
            telegram_sent = False

    try:
        from app.api.shomer_incidents import create_incident
        create_incident(ip, alert_signature or "", int(severity or 3), blocked_by, ok)
    except Exception:
        pass

    out: Dict[str, Any] = {"success": True, "message": msg, "ip": ip, "firewall_ok": ok}
    if telegram_sent is not None:
        out["telegram_sent"] = telegram_sent
    return out


@router.post("/unblock")
async def unblock_ip(body: Dict[str, Any] = Body(...)):
    ip = (body.get("ip") or "").strip()
    if not ip:
        raise HTTPException(status_code=400, detail="IP requerida")
    try:
        import ipaddress as _ipa; _ipa.ip_address(ip)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Formato de IP inválido: {ip}")

    ok, msg = await _mikrotik_unblock(ip)

    try:
        with get_connection(timeout=10) as conn:
            conn.execute(
                "UPDATE blocked_ips SET unblocked_at = ? WHERE ip = ? AND unblocked_at IS NULL",
                (datetime.now(timezone.utc).isoformat(), ip),
            )
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, "message": msg, "ip": ip, "firewall_ok": ok}


@router.get("/blocked")
async def list_blocked(user=Depends(get_current_user)):
    try:
        with get_connection(timeout=10) as conn:
            rows = conn.execute(
                "SELECT ip, blocked_at, blocked_by, alert_signature, severity, firewall_blocked FROM blocked_ips WHERE unblocked_at IS NULL ORDER BY blocked_at DESC"
            ).fetchall()
        return {"success": True, "blocked": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def list_history(limit: int = 200, user=Depends(get_current_user)):
    """Historial de IPs que ya fueron desbloqueadas (unblocked_at IS NOT NULL)."""
    try:
        with get_connection(timeout=10) as conn:
            rows = conn.execute(
                "SELECT ip, blocked_at, unblocked_at, blocked_by, alert_signature, severity, firewall_blocked "
                "FROM blocked_ips WHERE unblocked_at IS NOT NULL ORDER BY unblocked_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return {"success": True, "history": [dict(r) for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/csv")
async def export_history_csv(user=Depends(get_current_user)):
    """Descarga historial de bloqueos desbloqueados como CSV."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    try:
        with get_connection(timeout=10) as conn:
            rows = conn.execute(
                "SELECT ip, blocked_at, unblocked_at, blocked_by, alert_signature, severity, firewall_blocked "
                "FROM blocked_ips WHERE unblocked_at IS NOT NULL ORDER BY unblocked_at DESC"
            ).fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ip", "bloqueada_en", "desbloqueada_en", "origen", "firma_alerta", "severidad", "bloqueado_en_firewall"])
    for r in rows:
        writer.writerow([
            r["ip"],
            r["blocked_at"],
            r["unblocked_at"],
            r["blocked_by"],
            r["alert_signature"] or "",
            r["severity"] or "",
            "si" if r["firewall_blocked"] else "no",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=hunter_historial_bloqueos.csv"},
    )


@router.get("/is_blocked/{ip}")
async def check_blocked(ip: str, user=Depends(get_current_user)):
    from app.api.casador_support import _is_external_ip

    return {"success": True, "ip": ip, "blocked": _is_blocked(ip), "external": _is_external_ip(ip)}


@router.get("/firewall/status")
async def firewall_circuit_status(user=Depends(get_current_user)):
    r = _get_redis()
    fail_count = 0
    is_open = False
    if r:
        try:
            fail_count = int(r.get(_CB_FAIL_KEY) or 0)
            is_open = bool(r.get(_CB_STATUS_KEY))
        except Exception:
            pass
    return {
        "success": True,
        "circuit_open": is_open,
        "fail_count": fail_count,
        "threshold": _CB_THRESHOLD,
        "message": "Firewall unreachable — bloqueo automático desactivado"
        if is_open
        else "Firewall operativo",
    }


@router.post("/firewall/reset")
async def firewall_circuit_reset(user=Depends(get_current_user)):
    _cb_record_success()
    return {"success": True, "message": "Circuit breaker reseteado — firewall habilitado"}


@router.post("/firewall/sync")
async def firewall_sync(user=Depends(get_current_user)):
    """
    Re-aplica en el firewall todas las IPs activas en BD (unblocked_at IS NULL).
    Usa check-then-insert (iptables -C) para evitar duplicados.
    Útil tras reboot del router — las reglas iptables son volátiles.
    Actualiza firewall_blocked en BD según resultado de cada IP.
    """
    _require_hunter()
    try:
        with get_connection(timeout=10) as conn:
            rows = conn.execute(
                "SELECT ip FROM blocked_ips WHERE unblocked_at IS NULL ORDER BY blocked_at ASC"
            ).fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not rows:
        return {"success": True, "message": "No hay IPs activas en BD — nada que sincronizar", "synced": 0, "failed": 0, "total": 0}

    synced, failed, skipped = 0, 0, 0
    errors: list = []

    for row in rows:
        ip = row["ip"]
        ok, msg = await _mikrotik_sync_block(ip)
        if ok:
            synced += 1
        elif "circuito abierto" in msg.lower() or "unreachable" in msg.lower():
            skipped += 1
            errors.append({"ip": ip, "error": msg})
            break  # CB abierto — no seguir intentando el resto
        else:
            failed += 1
            errors.append({"ip": ip, "error": msg})

        try:
            with get_connection(timeout=10) as conn:
                conn.execute(
                    "UPDATE blocked_ips SET firewall_blocked = ? WHERE ip = ? AND unblocked_at IS NULL",
                    (1 if ok else 0, ip),
                )
                conn.commit()
        except Exception:
            pass

    total = len(rows)
    cb_open = skipped > 0
    return {
        "success": not cb_open and failed == 0,
        "total": total,
        "synced": synced,
        "failed": failed,
        "skipped_cb_open": skipped,
        "circuit_open": cb_open,
        "errors": errors,
        "message": (
            f"Sync completo: {synced}/{total} IPs aplicadas al firewall"
            if not cb_open and failed == 0
            else f"Sync parcial: {synced} OK, {failed} fallos, {skipped} omitidas (circuit breaker)"
        ),
    }


@router.get("/stats")
async def hunter_stats(user=Depends(get_current_user)):
    """Contadores resumen para el panel: alertas hoy, bloqueadas activas, por origen."""
    from datetime import date

    today_str = date.today().isoformat()

    # Bloqueadas activas
    active_blocks = 0
    by_origin: Dict[str, int] = {"manual": 0, "auto": 0, "wazuh": 0}
    try:
        with get_connection(timeout=10) as conn:
            rows = conn.execute(
                "SELECT blocked_by FROM blocked_ips WHERE unblocked_at IS NULL"
            ).fetchall()
            active_blocks = len(rows)
            for r in rows:
                k = (r["blocked_by"] or "manual").strip().lower()
                by_origin[k] = by_origin.get(k, 0) + 1
    except Exception:
        pass

    # Alertas hoy desde EVE
    alerts_today = 0
    try:
        from app.api.casador_support_suricata import _read_suricata_recent_alerts
        events, _ = _read_suricata_recent_alerts(limit=2000)
        alerts_today = sum(
            1 for e in events
            if (e.get("timestamp") or "").startswith(today_str)
        )
    except Exception:
        pass

    # Alta recurrencia activa (claves hunter:rec:* en Redis)
    high_rec_ips = 0
    try:
        r = _get_redis()
        if r:
            keys = r.keys("hunter:rec:*.*.*.*:*")
            high_rec_ips = len(keys) if keys else 0
    except Exception:
        pass

    return {
        "success": True,
        "alerts_today": alerts_today,
        "active_blocks": active_blocks,
        "blocks_by_origin": by_origin,
        "high_recurrence_ips": high_rec_ips,
    }
