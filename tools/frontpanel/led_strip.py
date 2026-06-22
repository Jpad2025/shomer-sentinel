#!/usr/bin/env python3
"""Tira RGB AceMagic S1 (CH340 /dev/ttyUSB0) — protocolo s1panel."""
from __future__ import annotations

import logging
import os
import time

LOG = logging.getLogger("shomer-led-strip")

DEVICE = os.environ.get("SHOMER_LED_DEVICE", "/dev/ttyUSB0")
THEME = int(os.environ.get("SHOMER_LED_THEME", "1"))  # 1 = arcoíris
INTENSITY = int(os.environ.get("SHOMER_LED_INTENSITY", "3"))
SPEED = int(os.environ.get("SHOMER_LED_SPEED", "3"))
RETRY_SEC = float(os.environ.get("SHOMER_LED_RETRY_SEC", "5"))
REFRESH_SEC = float(os.environ.get("SHOMER_LED_REFRESH_SEC", "120"))


def _fix_value(n: int) -> int:
    return min(5, max(1, 6 - n))


def _frame(theme: int, intensity: int, speed: int) -> bytes:
    buf = [0xFA, theme & 0xFF, _fix_value(intensity), _fix_value(speed)]
    buf.append(sum(buf[:4]) & 0xFF)
    return bytes(buf)


def apply_led() -> None:
    import serial

    payload = _frame(THEME, INTENSITY, SPEED)
    with serial.Serial(DEVICE, 10000, timeout=2) as ser:
        for byte in payload:
            ser.write(bytes([byte]))
            time.sleep(0.005)
    LOG.info("LED tema=%s device=%s", THEME, DEVICE)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    LOG.info("shomer-led-strip iniciado device=%s tema=%s", DEVICE, THEME)
    while True:
        try:
            apply_led()
            time.sleep(REFRESH_SEC)
        except Exception as e:
            LOG.warning("LED no aplicado (%s) — reintento en %ss", e, RETRY_SEC)
            time.sleep(RETRY_SEC)


if __name__ == "__main__":
    main()
