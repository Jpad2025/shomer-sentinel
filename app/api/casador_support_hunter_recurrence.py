"""Recurrencia (Redis) para autobloqueo HIGH — misma IP + SID en ventana de tiempo."""
import random
import time
from typing import Any, Optional, Union

from app.api.casador_support_redis_cb import _get_redis


def _sid_key(sid: Any, signature: str) -> str:
    try:
        n = int(sid or 0)
        if n > 0:
            return str(n)
    except Exception:
        pass
    h = abs(hash((signature or "")[:240])) % (10**9)
    return f"h{h}"


def hunter_recurrence_bump(
    ip: str, sid: Any, signature: str, window_sec: int
) -> Optional[int]:
    """
    Suma un evento y devuelve el número de eventos en [now - window, now].
    None si Redis no está disponible.
    """
    r = _get_redis()
    if not r:
        return None
    sk = _sid_key(sid, signature)
    k = f"hunter:rec:{ip}:{sk}"
    now = time.time()
    member = f"{now:.6f}:{random.random():.8f}"
    try:
        r.zadd(k, {member: now})
        r.zremrangebyscore(k, "-inf", now - float(window_sec))
        n = int(r.zcard(k))
        ex = min(max(int(window_sec) + 120, 60), 86400)
        r.expire(k, ex)
        return n
    except Exception:
        return None


def hunter_high_recurrence_warn_telegram(
    ip: str,
    sid: Any,
    signature: str,
    count: int,
    warn_at: int,
    window_sec: int,
) -> bool:
    """
    Un solo Telegram por (ip, sid) en la ventana cuando count == warn_at.
    """
    if warn_at <= 0 or count != warn_at:
        return False
    r = _get_redis()
    if not r:
        return False
    sk = _sid_key(sid, signature)
    wk = f"hunter:rec:warn:{ip}:{sk}"
    try:
        if not r.set(wk, "1", nx=True, ex=min(max(int(window_sec), 60), 86400)):
            return False
    except Exception:
        return False
    try:
        from app.scripts.alerts import send_telegram_alert

        from app.api.hunter_signature_labels import humanize_hunter_signature

        h = humanize_hunter_signature(signature)
        send_telegram_alert(
            f"⚠️ <b>Hunter — alerta recurrente</b>\n"
            f"{h['risk_icon']} <b>{h['title']}</b>\n"
            f"🌐 <code>{ip}</code> — evento {count} en {int(window_sec)}s\n"
            f"📋 {h['detail']}\n"
            f"<i>Se requiere recurrencia completa para autobloqueo según política.</i>"
        )
        return True
    except Exception:
        return False
