"""Respaldo de emergencia para notificaciones de Guardian — Opción 2 (24 ago).

Guardian ya no manda a Telegram directo (ver app/scripts/alerts.py
`send_telegram_alert`) -- encola en `notificaciones_pendientes` para que el
bot (shomer-agent) lo releve con formato consistente y por el mismo canal
auditado que usa para todo lo demás. Este módulo es la red de seguridad:
si el bot no confirma en `PENDING_FALLBACK_TIMEOUT_SEC` (no está sano, o
está lento), lo manda directo él mismo -- para que un backup fallando o un
bloqueo de seguridad nunca se quede sin avisar solo porque el bot esté
caído en ese momento exacto.
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3

logger = logging.getLogger(__name__)

_TELEGRAM_ENVIADOS_DB = "/storage/shomer-agent/data/telegram_enviados.db"
PENDING_FALLBACK_TIMEOUT_SEC = 60
PENDING_SWEEP_INTERVAL_SEC = 20


def _procesar_pendientes_vencidas() -> int:
    from app.scripts.alerts import _enviar_directo

    enviados = 0
    try:
        conn = sqlite3.connect(_TELEGRAM_ENVIADOS_DB, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE IF NOT EXISTS notificaciones_pendientes ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "ts TEXT DEFAULT (datetime('now')), "
            "mensaje TEXT NOT NULL, "
            "estado TEXT DEFAULT 'pendiente', "
            "procesado_at TEXT)"
        )
        rows = conn.execute(
            "SELECT id, mensaje FROM notificaciones_pendientes "
            "WHERE estado='pendiente' "
            "AND (julianday('now') - julianday(ts)) * 86400 >= ?",
            (PENDING_FALLBACK_TIMEOUT_SEC,),
        ).fetchall()
        for row in rows:
            ok = _enviar_directo(row["mensaje"])
            conn.execute(
                "UPDATE notificaciones_pendientes SET estado=?, procesado_at=datetime('now') "
                "WHERE id=?",
                ("enviado_directo_fallback" if ok else "fallo_fallback", row["id"]),
            )
            conn.commit()
            if ok:
                enviados += 1
                logger.warning(
                    "telegram_relay: el bot no relevó a tiempo (>%ds) -- "
                    "enviado directo como respaldo, id=%d",
                    PENDING_FALLBACK_TIMEOUT_SEC, row["id"],
                )
        conn.close()
    except Exception as e:
        logger.warning("telegram_relay: fallback falló: %s", e)
    return enviados


async def watch_pending_fallback_loop() -> None:
    await asyncio.sleep(30)
    while True:
        try:
            await asyncio.to_thread(_procesar_pendientes_vencidas)
        except Exception as e:
            logger.warning("telegram_relay loop error: %s", e)
        await asyncio.sleep(PENDING_SWEEP_INTERVAL_SEC)


def start_telegram_relay_fallback() -> None:
    loop = asyncio.get_event_loop()
    loop.create_task(watch_pending_fallback_loop())
    logger.info(
        "telegram_relay: respaldo de emergencia activo (tope %ds, revisa cada %ds)",
        PENDING_FALLBACK_TIMEOUT_SEC, PENDING_SWEEP_INTERVAL_SEC,
    )
