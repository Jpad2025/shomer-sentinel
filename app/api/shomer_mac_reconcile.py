"""Reconciliación de IP por MAC — Sesión 72/73.

Si un equipo (AP de Guardian, o switch/impresora/cámara/datáfono de
Inframonitor) cambia de IP -- DHCP, reconfiguración -- el poller se queda
pingueando la IP vieja para siempre y genera una falsa alerta de caída
permanente, sin que nadie note que el equipo sigue vivo en otra dirección
(caso real encontrado 14 ago: AP LOBBY RECEPCION, .121 -> .137).

No depende de que alguien corra un escaneo de Tracker (esos son manuales,
pueden pasar semanas sin uno) -- hace su propio barrido liviano cada
MAC_RECONCILE_INTERVAL_SEC: pinguea el /24 en paralelo (no root, ~1-2s) y
lee la tabla ARP del kernel (`ip neigh`, tampoco necesita root -- a
diferencia de `nmap -sn`, que solo muestra MAC con privilegios y Guardian
corre como usb_admin, no root; probado: sin esto quedaba en 0 resultados
siempre, en silencio, sin que nadie lo notara). Solo actualiza la IP
configurada de equipos que estén offline ahora mismo -- si un equipo está
online no hay nada que reconciliar. No toca Redis/estado en memoria de
Guardian: el próximo ciclo de poll reconstruye ese estado solo, ya con la
IP correcta.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import sqlite3
import subprocess

from app.api.shomer_common import get_db

logger = logging.getLogger(__name__)

MAC_RECONCILE_INTERVAL_SEC = int(os.environ.get("MAC_RECONCILE_INTERVAL_SEC", "1800"))
MAC_RECONCILE_SUBNET = os.environ.get("MAC_RECONCILE_SUBNET", "192.168.0.0/24")


def _ping_sweep(subnet: str) -> None:
    """Pinguea cada IP del /24 en paralelo (no bloqueante, sin root) para
    refrescar la tabla ARP del kernel con lo que está vivo ahora mismo."""
    hosts = [str(ip) for ip in ipaddress.ip_network(subnet, strict=False).hosts()]
    procs = []
    for ip in hosts:
        try:
            procs.append(subprocess.Popen(
                ["ping", "-c", "1", "-W", "1", ip],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ))
        except Exception:
            pass
    for p in procs:
        try:
            p.wait(timeout=2)
        except Exception:
            pass


def _scan_mac_ip() -> dict[str, str]:
    """Barrido propio -> {MAC: IP} visto ahora mismo en la LAN, vía tabla ARP."""
    try:
        _ping_sweep(MAC_RECONCILE_SUBNET)
        out = subprocess.run(
            ["ip", "-j", "neigh", "show"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        entries = json.loads(out or "[]")
    except Exception as e:
        logger.warning("mac_reconcile: barrido falló: %s", e)
        return {}

    result: dict[str, str] = {}
    for e in entries:
        mac = e.get("lladdr")
        ip = e.get("dst")
        states = e.get("state") or []
        if mac and ip and "FAILED" not in states and "INCOMPLETE" not in states:
            result[mac.upper()] = ip
    return result


def _ensure_log_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mac_reconcile_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT (datetime('now')),
            fuente TEXT NOT NULL,
            name TEXT NOT NULL,
            mac TEXT NOT NULL,
            ip_vieja TEXT NOT NULL,
            ip_nueva TEXT NOT NULL
        )
        """
    )


def reconcile_once() -> list[dict]:
    """Una pasada de reconciliación. Devuelve los cambios aplicados."""
    scan = _scan_mac_ip()
    if not scan:
        return []

    cambios: list[dict] = []
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        _ensure_log_table(conn)
        for r in conn.execute(
            "SELECT id, ip_address, mac_address, name FROM devices "
            "WHERE is_active=1 AND status='offline' "
            "AND mac_address IS NOT NULL AND mac_address != ''"
        ).fetchall():
            mac = (r["mac_address"] or "").upper()
            nueva_ip = scan.get(mac)
            if nueva_ip and nueva_ip != r["ip_address"]:
                vieja_ip = r["ip_address"]
                conn.execute(
                    "UPDATE devices SET ip_address=?, updated_at=datetime('now') WHERE id=?",
                    (nueva_ip, r["id"]),
                )
                cambios.append({
                    "fuente": "Guardian", "name": r["name"], "mac": mac,
                    "ip_vieja": vieja_ip, "ip_nueva": nueva_ip,
                })
                conn.execute(
                    "INSERT INTO mac_reconcile_log (fuente, name, mac, ip_vieja, ip_nueva) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("Guardian", r["name"], mac, vieja_ip, nueva_ip),
                )
                logger.warning(
                    "mac_reconcile: Guardian %s (MAC %s) IP %s -> %s "
                    "(misma MAC vista en otra IP por barrido propio)",
                    r["name"], mac, vieja_ip, nueva_ip,
                )

        for r in conn.execute(
            """
            SELECT d.id id, d.ip ip, d.name name, s.mac mac
            FROM infra_devices d JOIN infra_status s ON s.ip = d.ip
            WHERE d.active=1 AND s.status='offline'
              AND s.mac IS NOT NULL AND s.mac != ''
            """
        ).fetchall():
            mac = (r["mac"] or "").upper()
            nueva_ip = scan.get(mac)
            if nueva_ip and nueva_ip != r["ip"]:
                vieja_ip = r["ip"]
                conn.execute("UPDATE infra_devices SET ip=? WHERE id=?", (nueva_ip, r["id"]))
                cambios.append({
                    "fuente": "Inframonitor", "name": r["name"], "mac": mac,
                    "ip_vieja": vieja_ip, "ip_nueva": nueva_ip,
                })
                conn.execute(
                    "INSERT INTO mac_reconcile_log (fuente, name, mac, ip_vieja, ip_nueva) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("Inframonitor", r["name"], mac, vieja_ip, nueva_ip),
                )
                logger.warning(
                    "mac_reconcile: Inframonitor %s (MAC %s) IP %s -> %s "
                    "(misma MAC vista en otra IP por barrido propio)",
                    r["name"], mac, vieja_ip, nueva_ip,
                )

        conn.commit()

    return cambios


def cleanup_orphaned_infra_status() -> int:
    """Borra de `infra_status` las IPs que ya no corresponden a ningún equipo
    activo de `infra_devices` -- pasa cuando un equipo cambia de IP (la fila
    vieja se queda huérfana, no hay nada que la borre sola) o se desactiva
    (la última lectura "offline" se queda congelada para siempre). Solo
    limpia el estado actual -- el historial real vive en `status_events` y
    no se toca. 4 filas encontradas así el 15 ago (2 de IP cambiada/equipo
    desactivado, 1 de un equipo desactivado hace meses)."""
    try:
        with get_db() as conn:
            cur = conn.execute(
                "DELETE FROM infra_status WHERE ip NOT IN "
                "(SELECT ip FROM infra_devices WHERE active=1)"
            )
            conn.commit()
            borradas = cur.rowcount or 0
    except Exception as e:
        logger.warning("mac_reconcile: cleanup_orphaned_infra_status falló: %s", e)
        return 0
    if borradas:
        logger.warning(
            "mac_reconcile: %d fila(s) huérfana(s) de infra_status borradas "
            "(equipo cambió de IP o fue desactivado)", borradas,
        )
    return borradas


async def mac_reconcile_loop() -> None:
    await asyncio.sleep(120)
    while True:
        try:
            cambios = await asyncio.to_thread(reconcile_once)
            if cambios:
                logger.warning(
                    "mac_reconcile: %d equipo(s) reconciliado(s) este ciclo", len(cambios),
                )
            await asyncio.to_thread(cleanup_orphaned_infra_status)
        except Exception as e:
            logger.warning("mac_reconcile loop error: %s", e)
        await asyncio.sleep(MAC_RECONCILE_INTERVAL_SEC)


def start_mac_reconcile_loop() -> None:
    loop = asyncio.get_event_loop()
    loop.create_task(mac_reconcile_loop())
    logger.info(
        "mac_reconcile: reconciliación IP-por-MAC iniciada (cada %ds, subred %s)",
        MAC_RECONCILE_INTERVAL_SEC, MAC_RECONCILE_SUBNET,
    )
