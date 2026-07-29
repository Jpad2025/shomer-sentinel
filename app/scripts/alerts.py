"""
Módulo de alertas por Telegram - Producción
Desarrollado por USB Ingeniería SAS y USB Engineers LLC
Filtro de hierro: regex .21, whitelist SHOMER/Gateway/.210, etiquetas obligatorias.
Espejo NOC: lo enviado a Telegram también se registra en Redis noc:ia_log (sin spam extra).
"""
import re
import logging
import requests
import os


def _get_telegram_creds() -> tuple[str, str]:
    try:
        import sys
        _root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from app.api.shomer import get_config as _gc
        token   = _gc("guardian.telegram_token",   "") or ""
        chat_id = _gc("guardian.telegram_chat_id", "") or ""
        if token and chat_id:
            return token, chat_id
    except Exception:
        pass
    return (
        os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        os.environ.get("TELEGRAM_CHAT_ID",   ""),
    )

TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID = _get_telegram_creds()

ALLOWED_TAGS = (
    "PÉRDIDA DE SERVICIO",
    "REINICIO EN PROGRESO",
    "SALUD DE NODOS",
    "MANTENIMIENTO",
    "BLOQUEO AUTOMÁTICO",
    "BLOQUEO (Wazuh",
    "Hunter — ALTA recurrente",
    "CALIDAD DEGRADADA",
    "Protector — copia local OK",
    "Protector — copia local FALLÓ",
    "Protector — sync B2 OK",
    "Protector — sync B2 FALLÓ",
    "INFRA — DISPOSITIVO CAÍDO",
    "INFRA — DISPOSITIVO RECUPERADO",
)

logger = logging.getLogger("alerts")


def _plain_telegram(message: str) -> str:
    """Quita HTML de Telegram para el ticker del NOC."""
    t = re.sub(r"<[^>]+>", " ", message or "")
    t = t.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", t).strip()


def _engine_from_message(message: str) -> str:
    m = message or ""
    if "BLOQUEO" in m or "Hunter" in m or "Wazuh" in m:
        return "Hunter"
    if "INFRA" in m or "IMPRESORA" in m:
        return "Infra"
    if "Protector" in m:
        return "Protector"
    if "PÉRDIDA" in m or "REINICIO" in m or "CALIDAD" in m or "SALUD DE NODOS" in m or "MANTENIMIENTO" in m:
        return "Guardian"
    return "Telegram"


def mirror_telegram_to_noc(message: str, engine=None) -> None:
    """Copia un aviso ya enviado al feed del NOC. No envía Telegram."""
    try:
        import json
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("America/Bogota"))
        except Exception:
            now = datetime.utcnow()
        import redis as _redis
        plain = _plain_telegram(message)
        if not plain:
            return
        eng = engine or _engine_from_message(message)
        r = _redis.Redis(host="127.0.0.1", port=6379, decode_responses=True, socket_timeout=1)
        entry = json.dumps({
            "at": now.strftime("%H:%M:%S"),
            "engine": eng,
            "msg": plain[:140],
            "type": "telegram",
        }, ensure_ascii=False)
        r.lpush("noc:ia_log", entry)
        r.ltrim("noc:ia_log", 0, 24)
    except Exception:
        pass


def send_telegram_alert(message: str) -> bool:
    """
    Envía mensaje por Telegram.
    - Requiere token y chat_id configurados en system_state o variables de entorno
    - Etiquetas permitidas: ver ALLOWED_TAGS
    - Si se envía OK → espejo en NOC (noc:ia_log); no genera mensajes extra
    """
    _token, _chat_id = _get_telegram_creds()
    if not _token or _token == "YOUR_BOT_TOKEN":
        logger.debug("Telegram: TOKEN no configurado, alerta omitida")
        return False
    if not _chat_id or _chat_id == "YOUR_CHAT_ID":
        logger.debug("Telegram: CHAT_ID no configurado, alerta omitida")
        return False
    msg = message or ""
    if not any(tag in msg for tag in ALLOWED_TAGS):
        logger.debug("Telegram: bloqueado (falta etiqueta permitida)")
        return False

    url = f"https://api.telegram.org/bot{_token}/sendMessage"
    payload = {"chat_id": _chat_id, "text": msg, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            logger.info("Telegram: alerta enviada")
            mirror_telegram_to_noc(msg)
            return True
        logger.warning("Telegram: fallo HTTP %d - %s", r.status_code, (r.text or "")[:200])
        return False
    except Exception as e:
        logger.warning("Telegram: error enviando alerta: %s", e)
        return False
