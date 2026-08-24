"""Detección de seguridad Capa 1 — nativa del host (Sesión 75).

Reemplaza watch_security() de shomer-agent: esa versión corría dentro del
contenedor Docker del bot y nunca tuvo acceso real a auth.log, journalctl,
who ni /proc/mounts del *host* -- las 4 detecciones nunca dispararon una
sola alerta real, en silencio, desde que existían (verificado con
docker exec: auth.log no existe en el contenedor, who no ve sesiones del
host, journalctl no está instalado, /proc/mounts es el namespace propio
del contenedor). Este módulo corre en network_monitor (proceso host, igual
que Guardian/Hunter/Protector) con acceso genuino a lo que dice vigilar.

Cambios respecto al original además de la reubicación:
- Login inusual: en vez de `who` (solo ve sesiones interactivas activas EN
  el instante del poll -- una sesión breve se pierde entre polls), lee
  líneas "Accepted ... from" de auth.log -- no depende del timing del poll.
- Copia de archivos sensibles: en vez de journalctl -u ssh (sshd no
  registra el comando ejecutado en su unidad de systemd -- ese patrón
  nunca iba a matchear nada, ni siquiera corriendo en el host), escanea
  procesos scp/rsync/sftp/tar activos vía /proc -- ve la copia mientras
  ocurre de verdad.
- USB: /proc/mounts real del host.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import time
from datetime import datetime
from typing import List, Set

logger = logging.getLogger(__name__)

AUTH_LOG = "/var/log/auth.log"
POLL_INTERVAL_SEC = 120
BRUTE_FORCE_WINDOW_SEC = 600
BRUTE_FORCE_THRESHOLD = 5

_SENSITIVE_CMD_PATTERNS = (
    "/opt/network_monitor", "/etc/shomer", "network_monitor.db",
    "shomer-runtime.env", "/storage/shomer-agent", "/storage/db",
)
_COPY_BINARIES = ("scp", "rsync", "sftp", "tar")

_auth_log_offset = 0
_auth_fail_times: List[float] = []
_brute_warned_keys: Set[str] = set()
_login_warned_keys: Set[str] = set()
_copy_warned_keys: Set[str] = set()
_usb_warned: Set[str] = set()


def _wall(msg: str) -> None:
    try:
        subprocess.run(["wall", msg], timeout=5, capture_output=True)
    except Exception:
        pass


def _init_auth_log_offset() -> None:
    """Arranca al final del archivo -- no reprocesa el historial completo
    de auth.log (semanas/meses de fallos viejos) en cada arranque."""
    global _auth_log_offset
    try:
        _auth_log_offset = os.path.getsize(AUTH_LOG)
    except Exception:
        _auth_log_offset = 0


def _read_new_auth_lines() -> List[str]:
    global _auth_log_offset
    try:
        size = os.path.getsize(AUTH_LOG)
        if size < _auth_log_offset:
            _auth_log_offset = 0  # logrotate truncó/rotó el archivo
        with open(AUTH_LOG, "r", errors="ignore") as f:
            f.seek(_auth_log_offset)
            lines = f.readlines()
            _auth_log_offset = f.tell()
        return lines
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.debug("security_watch: no se pudo leer auth.log: %s", e)
        return []


def _check_brute_force(lines: List[str]) -> None:
    global _auth_fail_times
    from app.scripts.alerts import send_telegram_alert

    now_ts = time.time()
    cutoff = now_ts - BRUTE_FORCE_WINDOW_SEC
    _auth_fail_times = [t for t in _auth_fail_times if t > cutoff]

    fail_lines = [l for l in lines if "Failed password" in l or "Invalid user" in l]
    for _ in fail_lines:
        _auth_fail_times.append(now_ts)

    if len(_auth_fail_times) >= BRUTE_FORCE_THRESHOLD:
        key = f"brute_{int(now_ts / BRUTE_FORCE_WINDOW_SEC)}"
        if key in _brute_warned_keys:
            return
        _brute_warned_keys.add(key)
        ips: Set[str] = set()
        for line in fail_lines[-20:]:
            m = re.search(r"from (\d+\.\d+\.\d+\.\d+)", line)
            if m:
                ips.add(m.group(1))
        ips_txt = ", ".join(list(ips)[:5]) or "desconocidas"
        _wall(
            "AVISO DE SEGURIDAD: se detectaron múltiples intentos de acceso "
            "fallidos al servidor. Este sistema está siendo monitoreado."
        )
        send_telegram_alert(
            f"🔐 SEGURIDAD — Intentos SSH fallidos\n"
            f"{len(_auth_fail_times)} en {BRUTE_FORCE_WINDOW_SEC // 60} min — {ips_txt}"
        )


def _check_unusual_login(lines: List[str]) -> None:
    from app.scripts.alerts import send_telegram_alert

    now = datetime.now()
    if not (0 <= now.hour < 6):
        return
    for line in lines:
        m = re.search(r"Accepted (\S+) for (\S+) from (\d+\.\d+\.\d+\.\d+)", line)
        if not m:
            continue
        _metodo, user, ip = m.groups()
        key = f"login_{user}_{ip}_{now.date()}_{now.hour}"
        if key in _login_warned_keys:
            continue
        _login_warned_keys.add(key)
        _wall(
            f"AVISO: acceso SSH detectado en horario inusual ({now.strftime('%H:%M')}). "
            f"Este acceso ha sido registrado."
        )
        send_telegram_alert(
            f"🔐 SEGURIDAD — Acceso SSH en horario inusual\n"
            f"{user} desde {ip} — {now.strftime('%H:%M')}"
        )


def _check_sensitive_copy() -> None:
    from app.scripts.alerts import send_telegram_alert

    try:
        pids = os.listdir("/proc")
    except Exception as e:
        logger.debug("security_watch: /proc no accesible: %s", e)
        return

    for pid in pids:
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                raw = f.read()
        except Exception:
            continue
        cmdline = raw.replace(b"\x00", b" ").decode(errors="ignore").strip()
        if not cmdline:
            continue
        parts = cmdline.split()
        cmd0 = parts[0].split("/")[-1]
        if cmd0 not in _COPY_BINARIES:
            continue
        if not any(pat in cmdline for pat in _SENSITIVE_CMD_PATTERNS):
            continue
        key = f"copy_{pid}_{hash(cmdline)}"
        if key in _copy_warned_keys:
            continue
        _copy_warned_keys.add(key)
        _wall(
            "AVISO DE SEGURIDAD: se detectó una operación de transferencia de "
            "archivos del sistema. Este acceso ha sido registrado y reportado."
        )
        send_telegram_alert(
            f"🔐 SEGURIDAD — Posible copia de archivos sensibles\n"
            f"<code>{cmd0}</code> — pid {pid}"
        )


def _check_usb() -> None:
    from app.scripts.alerts import send_telegram_alert

    try:
        with open("/proc/mounts", "r") as f:
            mounts = f.read()
    except Exception:
        return
    for line in mounts.splitlines():
        if "/media/" not in line and "/mnt/" not in line:
            continue
        device = line.split()[0]
        if device in _usb_warned or device.startswith("//"):
            continue
        _usb_warned.add(device)
        _wall(
            "AVISO: se detectó un dispositivo externo conectado al servidor. "
            "Este evento ha sido registrado."
        )
        send_telegram_alert(f"🔐 SEGURIDAD — USB conectado al servidor\n<code>{device}</code>")


async def watch_security_loop() -> None:
    await asyncio.sleep(180)
    await asyncio.to_thread(_init_auth_log_offset)
    while True:
        try:
            lines = await asyncio.to_thread(_read_new_auth_lines)
            if lines:
                await asyncio.to_thread(_check_brute_force, lines)
                await asyncio.to_thread(_check_unusual_login, lines)
            await asyncio.to_thread(_check_sensitive_copy)
            await asyncio.to_thread(_check_usb)
        except Exception as e:
            logger.warning("security_watch loop error: %s", e)
        await asyncio.sleep(POLL_INTERVAL_SEC)


def start_security_watch() -> None:
    loop = asyncio.get_event_loop()
    loop.create_task(watch_security_loop())
    logger.info(
        "security_watch: Capa 1 de seguridad activa (host nativo) -- "
        "fuerza bruta SSH, login inusual, copia sensible, USB"
    )
