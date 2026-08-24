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
import sqlite3

_TELEGRAM_ENVIADOS_DB = "/storage/shomer-agent/data/telegram_enviados.db"


def _registrar_envio_real(origen: str, resumen: str) -> None:
    """Contador de verdad -- registra CADA mensaje que de verdad salió a
    Telegram, sin importar qué camino lo mandó. Motivado por la Sesión del
    23 ago: reconstruir el conteo desde memoria_alertas (bot) tenía un
    hueco real -- este canal directo de Guardian nunca quedaba ahí. Archivo
    compartido en /storage/shomer-agent/data/ (escribible desde el host Y
    desde el contenedor del bot; /storage/db es solo-lectura para el bot)."""
    try:
        conn = sqlite3.connect(_TELEGRAM_ENVIADOS_DB, timeout=5)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS enviados ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "ts TEXT DEFAULT (datetime('now')), "
            "origen TEXT, resumen TEXT)"
        )
        conn.execute(
            "INSERT INTO enviados (origen, resumen) VALUES (?, ?)",
            (origen, (resumen or "")[:80]),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


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
    "SEGURIDAD —",
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
    if "SEGURIDAD" in m:
        return "Seguridad"
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


def _encolar_para_bot(msg: str) -> bool:
    """Encola el mensaje para que el bot lo relea y lo mande por su canal
    (con formato consistente, y por el mismo camino que ya audita todo).
    Si el bot no lo releva en 60s (caído/lento), watch_pending_fallback lo
    manda directo como respaldo -- no depende de que el bot esté sano.
    Tabla compartida en /storage/shomer-agent/data/ (escribible desde el
    host y desde el contenedor; /storage/db es solo-lectura para el bot)."""
    try:
        conn = sqlite3.connect(_TELEGRAM_ENVIADOS_DB, timeout=5)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS notificaciones_pendientes ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "ts TEXT DEFAULT (datetime('now')), "
            "mensaje TEXT NOT NULL, "
            "estado TEXT DEFAULT 'pendiente', "
            "procesado_at TEXT)"
        )
        conn.execute(
            "INSERT INTO notificaciones_pendientes (mensaje) VALUES (?)", (msg,),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.warning("Telegram: no se pudo encolar para el bot: %s", e)
        return False


def _enviar_directo(msg: str) -> bool:
    """Envío real a la API de Telegram -- usado por el respaldo de
    emergencia (watch_pending_fallback) si el bot no releva a tiempo."""
    _token, _chat_id = _get_telegram_creds()
    if not _token or not _chat_id:
        return False
    url = f"https://api.telegram.org/bot{_token}/sendMessage"
    payload = {"chat_id": _chat_id, "text": msg, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            logger.info("Telegram: alerta enviada (respaldo directo)")
            _registrar_envio_real("guardian_directo_fallback", msg)
            mirror_telegram_to_noc(msg)
            return True
        logger.warning("Telegram: fallo HTTP %d - %s", r.status_code, (r.text or "")[:200])
        return False
    except Exception as e:
        logger.warning("Telegram: error enviando alerta directa: %s", e)
        return False


def send_telegram_alert(message: str) -> bool:
    """
    Punto de entrada único de Guardian hacia Telegram -- Opción 2 (24 ago):
    ya NO manda directo. Encola para que el bot lo releve con formato
    consistente; si el bot no confirma en 60s, watch_pending_fallback lo
    manda directo como respaldo. Callers no cambian, misma firma/semántica.
    - Requiere token y chat_id configurados en system_state o variables de entorno
    - Etiquetas permitidas: ver ALLOWED_TAGS
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

    return _encolar_para_bot(msg)
