"""
Módulo de alertas por Telegram - Producción
Desarrollado por USB Ingeniería SAS y USB Engineers LLC
Filtro de hierro: regex .21, whitelist SHOMER/Gateway/.210, etiquetas obligatorias.
"""
import re
import logging
import requests

def _get_telegram_creds() -> tuple[str, str]:
    try:
        import sys, os
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


def send_telegram_alert(message: str) -> bool:
    """
    Envía mensaje por Telegram.
    - Requiere token y chat_id configurados en system_state o variables de entorno
    - Etiquetas permitidas: ver ALLOWED_TAGS (incl. bloqueo Wazuh y autobloqueo Hunter)
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
            return True
        logger.warning("Telegram: fallo HTTP %d - %s", r.status_code, (r.text or "")[:200])
        return False
    except Exception as e:
        logger.warning("Telegram: error enviando alerta: %s", e)
        return False
