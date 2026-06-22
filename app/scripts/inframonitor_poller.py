"""
Inframonitor standalone poller — proceso independiente controlado por systemd.
Importa la lógica de shomer_inframonitor sin levantar FastAPI.
Permite separar el ciclo de polling de los workers uvicorn.
"""
import asyncio
import logging
import signal
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("inframonitor-poller")

_stop_event: asyncio.Event | None = None


def _handle_signal(sig, _frame):
    logger.info("Señal %s recibida — deteniendo poller", sig)
    if _stop_event:
        _stop_event.set()


async def main() -> None:
    global _stop_event
    _stop_event = asyncio.Event()

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGTERM, _handle_signal, signal.SIGTERM, None)
    loop.add_signal_handler(signal.SIGINT,  _handle_signal, signal.SIGINT,  None)

    from app.api.shomer_inframonitor import (
        _init_tables,
        _poll_once,
        _sync_guardian_aps,
        POLL_INTERVAL_SEC,
    )

    logger.info("Inframonitor standalone poller arrancando (intervalo %ss)", POLL_INTERVAL_SEC)
    _init_tables()

    while not _stop_event.is_set():
        t0 = loop.time()
        try:
            _sync_guardian_aps()
            await _poll_once()
        except Exception as exc:
            logger.error("Error en ciclo de poll: %s", exc)
        elapsed = loop.time() - t0
        wait = max(0.1, POLL_INTERVAL_SEC - elapsed)
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=wait)
        except asyncio.TimeoutError:
            pass

    logger.info("Inframonitor standalone poller detenido")


if __name__ == "__main__":
    asyncio.run(main())
