#!/usr/bin/env python3
"""
Opción 2 — actualiza la pantalla frontal S1 con estado Shomer (WAN, APs).

Lee Redis + system_state, regenera logo-portrait.png y reinicia s1panel solo si cambió.
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("/opt/network_monitor")
sys.path.insert(0, str(REPO))

from tools.frontpanel.render import render_logo_portrait

LOG = logging.getLogger("shomer-frontpanel")

USB_SRC = REPO / "app/static/img/logo-usb.png"
SHOMER_SRC = REPO / "app/static/img/shomer-eyes.png"
LOGO_OUT = Path("/root/snap/s1panel/current/themes/shomer/logo-portrait.png")

POLL_SEC = int(os.environ.get("FRONTPANEL_POLL_SEC", "30"))
ROTATE_SEC = int(os.environ.get("FRONTPANEL_ROTATE_SEC", "45"))


def _redis():
    try:
        import redis

        return redis.Redis(host="127.0.0.1", port=6379, db=0, socket_timeout=2)
    except Exception as e:
        LOG.warning("Redis no disponible: %s", e)
        return None


def _get_config(key: str, default: str = "") -> str:
    try:
        from app.backend.db import get_config

        v = get_config(key)
        return str(v).strip() if v is not None else default
    except Exception as e:
        LOG.debug("get_config %s: %s", key, e)
        return default


def _fetch_status() -> dict:
    wan = "unknown"
    online, total = 0, 0
    r = _redis()
    if r:
        try:
            raw = r.get("shomer:wan_status") or r.get("wan_status")
            if raw:
                wan = raw.decode() if isinstance(raw, bytes) else str(raw)
            keys = r.keys("status:*")
            total = len(keys)
            for key in keys:
                val = r.get(key)
                st = val.decode() if isinstance(val, bytes) else str(val or "")
                if st == "online":
                    online += 1
        except Exception as e:
            LOG.warning("Error leyendo Redis: %s", e)

    site = _get_config("base.site_name", "")
    mode = _get_config("frontpanel.mode", "status") or "status"
    label = _get_config("frontpanel.label", "")

    aps = f"AP {online}/{total}" if total else "AP —"
    return {
        "wan": wan,
        "aps": aps,
        "site": site,
        "mode": mode.lower(),
        "label": label,
    }


def _png_hash(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _render_to_tmp(status: dict, show_status: bool, tmp: Path) -> None:
    render_logo_portrait(
        USB_SRC,
        SHOMER_SRC,
        tmp,
        status_wan=status["wan"] if show_status else None,
        status_aps=status["aps"] if show_status else None,
        site_name=status["site"] if show_status and status["site"] else None,
        show_status=show_status,
    )


def _s1panel_active() -> bool:
    try:
        chk = subprocess.run(
            ["/usr/bin/snap", "services", "s1panel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in chk.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0] == "s1panel.s1panel":
                return parts[2] == "active"
    except Exception:
        pass
    return False


def _restart_s1panel() -> None:
    """stop + limpiar puerto 8686 + start (snap restart deja zombie node)."""
    try:
        subprocess.run(
            ["sh", "-c", "fuser -k 8686/tcp 2>/dev/null; pkill -9 -f 's1panel/main.js' 2>/dev/null; true"],
            timeout=15,
            check=False,
        )
        subprocess.run(
            ["/usr/bin/snap", "stop", "s1panel"],
            timeout=30,
            check=False,
            capture_output=True,
        )
        time.sleep(2)
        subprocess.run(
            ["sh", "-c", "fuser -k 8686/tcp 2>/dev/null; pkill -9 -f 's1panel/main.js' 2>/dev/null; true"],
            timeout=15,
            check=False,
        )
        time.sleep(1)
        subprocess.run(
            ["/usr/bin/snap", "start", "s1panel"],
            check=True,
            timeout=30,
            capture_output=True,
        )
        time.sleep(2)
        chk = subprocess.run(
            ["/usr/bin/snap", "services", "s1panel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if "inactive" in chk.stdout:
            LOG.error("s1panel inactive tras start — revisar: snap logs s1panel")
        else:
            LOG.info("s1panel reiniciado OK")
    except Exception as e:
        LOG.error("No se pudo reiniciar s1panel: %s", e)


def _ensure_s1panel_running() -> None:
    chk = subprocess.run(
        ["/usr/bin/snap", "services", "s1panel"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if "inactive" in chk.stdout:
        LOG.warning("s1panel caído al arrancar — recuperando")
        _restart_s1panel()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    if not USB_SRC.is_file() or not SHOMER_SRC.is_file():
        LOG.error("Faltan assets en %s", REPO / "app/static/img")
        sys.exit(1)

    last_hash = _png_hash(LOGO_OUT)
    rotate_show_status = True
    rotate_next = time.time()
    boot_skip_restart = _s1panel_active() and LOGO_OUT.is_file()

    LOG.info("shomer-frontpanel iniciado poll=%ss out=%s", POLL_SEC, LOGO_OUT)
    if not _s1panel_active():
        _ensure_s1panel_running()

    tick = 0
    while True:
        try:
            tick += 1
            if not _s1panel_active():
                LOG.warning("s1panel caído — recuperando")
                _restart_s1panel()
                time.sleep(POLL_SEC)
                continue

            status = _fetch_status()
            mode = status["mode"]
            show_status = True
            if mode == "logo":
                show_status = False
            elif mode == "rotate":
                now = time.time()
                if now >= rotate_next:
                    rotate_show_status = not rotate_show_status
                    rotate_next = now + ROTATE_SEC
                show_status = rotate_show_status

            tmp = LOGO_OUT.with_suffix(".tmp.png")
            _render_to_tmp(status, show_status, tmp)
            new_hash = hashlib.sha256(tmp.read_bytes()).hexdigest()
            if new_hash != last_hash:
                tmp.replace(LOGO_OUT)
                last_hash = new_hash
                LOG.info(
                    "PNG actualizado mode=%s wan=%s %s",
                    mode,
                    status["wan"],
                    status["aps"],
                )
                if boot_skip_restart:
                    boot_skip_restart = False
                    LOG.info("Omitido reinicio s1panel (arranque, ya activo)")
                else:
                    _restart_s1panel()
            else:
                tmp.unlink(missing_ok=True)
            if tick % 20 == 0:
                LOG.info(
                    "watchdog ok s1panel=%s mode=%s",
                    "active" if _s1panel_active() else "DOWN",
                    status.get("mode", "?"),
                )
        except Exception as e:
            LOG.exception("Tick falló: %s", e)

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
