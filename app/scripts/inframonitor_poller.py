"""
Inframonitor standalone poller — proceso independiente controlado por systemd.
Importa la lógica de shomer_inframonitor sin levantar FastAPI.
Capa rápida (ping/tcp/mac) cada INFRA_FAST_POLL_INTERVAL_SEC;
SNMP en proceso paralelo cada INFRA_SNMP_POLL_INTERVAL_SEC.
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
        _poll_fast_once,
        _poll_snmp_once,
        _sync_guardian_aps,
        FAST_POLL_INTERVAL_SEC,
        SNMP_POLL_INTERVAL_SEC,
    )

    logger.info(
        "Inframonitor standalone poller arrancando (fast=%ss snmp=%ss)",
        FAST_POLL_INTERVAL_SEC, SNMP_POLL_INTERVAL_SEC,
    )
    _init_tables()

    async def _fast_loop():
        while not _stop_event.is_set():
            t0 = loop.time()
            try:
                _sync_guardian_aps()
                await _poll_fast_once()
            except Exception as exc:
                logger.error("Error en ciclo fast: %s", exc)
            elapsed = loop.time() - t0
            wait = max(0.1, FAST_POLL_INTERVAL_SEC - elapsed)
            try:
                await asyncio.wait_for(_stop_event.wait(), timeout=wait)
            except asyncio.TimeoutError:
                pass

    async def _snmp_loop():
        while not _stop_event.is_set():
            try:
                await _poll_snmp_once()
            except Exception as exc:
                logger.error("Error en ciclo snmp: %s", exc)
            try:
                await asyncio.wait_for(_stop_event.wait(), timeout=SNMP_POLL_INTERVAL_SEC)
            except asyncio.TimeoutError:
                pass

    fast_task = asyncio.create_task(_fast_loop())
    snmp_task = asyncio.create_task(_snmp_loop())
    await _stop_event.wait()
    fast_task.cancel()
    snmp_task.cancel()
    for t in (fast_task, snmp_task):
        try:
            await t
        except asyncio.CancelledError:
            pass

    logger.info("Inframonitor standalone poller detenido")


if __name__ == "__main__":
    asyncio.run(main())
