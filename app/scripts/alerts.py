"""
Módulo de alertas por Telegram
Desarrollado por USB Ingeniería SAS y USB Engineers LLC
"""
import logging
import requests

TELEGRAM_BOT_TOKEN = "8581376385:AAF6YYJ0fteTekQIiedNXn-NDb2AgI8-05Y"
TELEGRAM_CHAT_ID = "6513540405"
# Red monitoreada (no confundir con el sistema: SHOMER)
RED_MONITOREDA = "Hotel El Buen Descanso"

MSG_INICIO = (
    "🛡️ SHOMER: Sistema activo. Red del Hotel El Buen Descanso. "
    "Monitoreo de 30 routers iniciado."
)

logger = logging.getLogger("alerts")


def send_telegram_alert(message: str) -> bool:
    """
    Envía un mensaje de alerta por Telegram mediante la API de Bot.
    Returns True si se envió correctamente, False en caso contrario.
    """
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN":
        logger.debug("Telegram: TOKEN no configurado, alerta omitida")
        return False
    if not TELEGRAM_CHAT_ID or TELEGRAM_CHAT_ID == "YOUR_CHAT_ID":
        logger.debug("Telegram: CHAT_ID no configurado, alerta omitida")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}

    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            logger.info("Telegram: alerta enviada")
            return True
        logger.warning("Telegram: fallo HTTP %d - %s", r.status_code, r.text[:200])
        return False
    except Exception as e:
        logger.warning("Telegram: error enviando alerta: %s", e)
        return False
