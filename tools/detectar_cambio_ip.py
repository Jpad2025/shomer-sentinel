#!/usr/bin/env python3
"""detectar_cambio_ip.py — compara la MAC guardada de cada equipo (Guardian +
Inframonitor) contra el último escaneo de Tracker (inventory.db, tabla
assets). Si la misma MAC aparece en Tracker con una IP distinta a la
configurada, es candidato real a "el equipo cambió de IP" -- Guardian/
Inframonitor se quedan pingueando la IP vieja para siempre y generan una
falsa alerta de caída permanente sin que nadie se dé cuenta de que el
equipo está vivo, solo que en otra dirección.

Solo lectura, no cambia nada -- avisa, no mueve la configuración solo (ver
CLAUDE.md § Mapa de decisión de alertas: mismo criterio de "avisar, no
actuar solo" que ya usan node_maintenance y los botones de ack).

Uso:
  python3 tools/detectar_cambio_ip.py                  # todos los equipos con MAC conocida
  python3 tools/detectar_cambio_ip.py --solo-offline    # solo los que están offline ahora mismo
"""
from __future__ import annotations

import argparse
import sqlite3

NETWORK_DB = "/storage/db/network_monitor.db"
INVENTORY_DB = "/storage/db/inventory.db"


def _ro(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _norm_mac(mac: str) -> str:
    return (mac or "").strip().upper()


def equipos_monitoreados() -> list[dict]:
    """(mac, ip_configurada, name, fuente, status) de Guardian + Inframonitor."""
    out: list[dict] = []
    conn = _ro(NETWORK_DB)

    for r in conn.execute(
        "SELECT mac_address mac, ip_address ip, name, status FROM devices "
        "WHERE is_active=1 AND mac_address IS NOT NULL AND mac_address != ''"
    ):
        out.append({
            "mac": _norm_mac(r["mac"]), "ip": r["ip"], "name": r["name"],
            "fuente": "Guardian", "status": r["status"],
        })

    for r in conn.execute(
        """
        SELECT s.mac mac, d.ip ip, d.name name, s.status status
        FROM infra_devices d JOIN infra_status s ON s.ip = d.ip
        WHERE d.active=1 AND s.mac IS NOT NULL AND s.mac != ''
        """
    ):
        out.append({
            "mac": _norm_mac(r["mac"]), "ip": r["ip"], "name": r["name"],
            "fuente": "Inframonitor", "status": r["status"],
        })

    conn.close()
    return out


def mac_vista_por_tracker() -> dict[str, tuple[str, str]]:
    """mac -> (ip_vista_ahora, last_seen), del escaneo más reciente de Tracker."""
    conn = _ro(INVENTORY_DB)
    out: dict[str, tuple[str, str]] = {}
    for r in conn.execute("SELECT mac, ip, last_seen FROM assets WHERE mac IS NOT NULL AND mac != ''"):
        mac = _norm_mac(r["mac"])
        prev = out.get(mac)
        if prev is None or r["last_seen"] > prev[1]:
            out[mac] = (r["ip"], r["last_seen"])
    conn.close()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--solo-offline", action="store_true")
    args = ap.parse_args()

    monitoreados = equipos_monitoreados()
    vistos = mac_vista_por_tracker()

    if not vistos:
        print(f"No se pudo leer ningún escaneo de Tracker en {INVENTORY_DB} -- ¿corriste un escaneo?")
        return

    candidatos = []
    for eq in monitoreados:
        if args.solo_offline and eq["status"] not in ("offline", "unknown", None):
            continue
        visto = vistos.get(eq["mac"])
        if visto is None:
            continue
        ip_vista, last_seen = visto
        if ip_vista != eq["ip"]:
            candidatos.append({**eq, "ip_vista": ip_vista, "last_seen": last_seen})

    print(f"Equipos monitoreados con MAC conocida: {len(monitoreados)}")
    print(f"MACs vistas por Tracker (último escaneo): {len(vistos)}")
    print()

    if not candidatos:
        print("Sin discrepancias -- ninguna MAC monitoreada aparece en Tracker con una IP distinta.")
        return

    print(f"── {len(candidatos)} equipo(s) que podrían haber cambiado de IP ──\n")
    for c in candidatos:
        print(f"  {c['fuente']:<13} {c['name']}")
        print(f"    Configurado en: {c['ip']}  (estado actual: {c['status']})")
        print(f"    Tracker lo vio en: {c['ip_vista']}  (último escaneo: {c['last_seen']})")
        print(f"    MAC: {c['mac']}")
        print()

    print("Esto NO se corrigió solo -- revisar y actualizar la IP manualmente si aplica.")


if __name__ == "__main__":
    main()
