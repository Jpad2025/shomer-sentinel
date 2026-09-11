#!/usr/bin/env python3
"""Vigila el internet REAL del hotel — el de los huéspedes, no el del servidor.

Esta distinción importa y costó aprenderla: verificar que el servidor Shomer
navega NO prueba que el hotel navega. Shomer está en la LAN de gestión, mientras
que los huéspedes salen por otras VLAN y por el hotspot, y la regla de bloqueo
de Hunter actúa sobre `chain=forward`, o sea justo sobre el tráfico que
atraviesa el router: el de ellos. Shomer puede navegar perfecto con el hotel
caído.

Por eso se mide **desde el router**, que es por donde sale todo el hotel:

  1. WAN física arriba y con dirección asignada (si no, no hay internet).
  2. Salida real a internet desde el router (pérdida de paquetes y latencia).
  3. Uso real: sesiones NAT y clientes del hotspot. Un desplome aquí es la
     señal más honesta de que la gente se quedó sin servicio, incluso cuando
     todo lo demás "responde".
  4. Si además hay servicio esencial en la lista de bloqueo de Hunter, se avisa
     como causa propia — que fue lo que pasó el 8 sep 2026 con los DNS de Google.

Genérico (norma B.1): la interfaz WAN y los destinos salen de system_state; los
valores por defecto sirven en cualquier sitio y no hay nada de Ópera en el código.

Uso:
    python3 tools/vigilar_internet_hotel.py
    python3 tools/vigilar_internet_hotel.py --silencioso
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/opt/network_monitor")

import asyncssh  # noqa: E402

from app.api.shomer_common import get_config, get_db  # noqa: E402

ESTADO_DB = "/storage/db/network_monitor.db"
DESTINOS_DEFECTO = ["8.8.8.8", "1.1.1.1"]
# Caída de uso que se considera sospechosa respecto de la medición anterior.
CAIDA_USO_PCT = 80


def _cfg_router() -> dict:
    with get_db() as c:
        return {
            r[0].replace("hunter.firewall_", ""): r[1]
            for r in c.execute(
                "SELECT key,value FROM system_state WHERE key LIKE 'hunter.firewall_%'"
            )
        }


def _wan_iface() -> str:
    return (get_config("base.wan_interface") or "ether3").strip()


def _destinos() -> list:
    cfg = get_config("base.wan_test_ips")
    if cfg:
        try:
            datos = json.loads(cfg) if isinstance(cfg, str) else cfg
            if isinstance(datos, list) and datos:
                return datos
        except Exception:
            pass
    return DESTINOS_DEFECTO


def _guardar_estado(clave: str, valor: int) -> int | None:
    """Guarda la medición y devuelve la anterior, para comparar tendencia."""
    try:
        con = sqlite3.connect(ESTADO_DB, timeout=5)
        con.execute(
            "CREATE TABLE IF NOT EXISTS wan_uso_historial ("
            "clave TEXT PRIMARY KEY, valor INTEGER, ts TEXT)"
        )
        row = con.execute(
            "SELECT valor FROM wan_uso_historial WHERE clave=?", (clave,)
        ).fetchone()
        anterior = row[0] if row else None
        con.execute(
            "INSERT INTO wan_uso_historial (clave, valor, ts) VALUES (?,?,datetime('now')) "
            "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor, ts=excluded.ts",
            (clave, valor),
        )
        con.commit()
        con.close()
        return anterior
    except Exception:
        return None


def _ips_bloqueadas() -> set:
    try:
        with get_db() as conn:
            return {
                r[0] for r in conn.execute(
                    "SELECT ip FROM blocked_ips WHERE unblocked_at IS NULL"
                )
            }
    except Exception:
        return set()


async def _medir(cfg: dict) -> dict:
    iface = _wan_iface()
    datos: dict = {"iface": iface}
    async with asyncssh.connect(
        cfg["ip"], port=int(cfg.get("port", 22)), username=cfg["user"],
        password=cfg["pass"], known_hosts=None, connect_timeout=15,
    ) as con:
        r = await con.run(f'/interface print where name="{iface}"', timeout=20)
        datos["wan_running"] = " R " in (r.stdout or "") or "R " in (r.stdout or "")

        r = await con.run(f"/ip address print where interface={iface}", timeout=20)
        m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3}/\d+)", r.stdout or "")
        datos["wan_ip"] = m.group(1) if m else ""

        datos["pings"] = {}
        for destino in _destinos():
            r = await con.run(f"/ping {destino} count=3", timeout=30)
            m = re.search(r"packet-loss=(\d+)%", r.stdout or "")
            datos["pings"][destino] = int(m.group(1)) if m else 100

        r = await con.run("/ip firewall connection print count-only", timeout=25)
        try:
            datos["sesiones"] = int((r.stdout or "0").strip())
        except ValueError:
            datos["sesiones"] = -1

        try:
            r = await con.run("/ip hotspot active print count-only", timeout=20)
            datos["hotspot"] = int((r.stdout or "0").strip())
        except Exception:
            datos["hotspot"] = -1  # el sitio puede no usar hotspot
    return datos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--silencioso", action="store_true")
    args = ap.parse_args()
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        datos = asyncio.run(_medir(_cfg_router()))
    except Exception as e:
        print(f"[{ahora}] NO SE PUDO CONSULTAR EL ROUTER: {type(e).__name__}: {e}")
        print("  Sin acceso al gateway no se puede afirmar nada del internet del hotel.")
        return 1

    perdida = datos["pings"]
    peor = max(perdida.values()) if perdida else 100
    sesiones, hotspot = datos["sesiones"], datos["hotspot"]
    ses_antes = _guardar_estado("sesiones_nat", sesiones) if sesiones >= 0 else None
    hs_antes = _guardar_estado("hotspot_activos", hotspot) if hotspot >= 0 else None

    lineas = [
        f"  WAN {datos['iface']:8} {'arriba' if datos['wan_running'] else 'CAIDA'}"
        f"  ip={datos['wan_ip'] or 'SIN DIRECCION'}",
    ]
    for d, p in perdida.items():
        lineas.append(f"  ping {d:12} pérdida {p}%")
    lineas.append(f"  sesiones NAT     {sesiones}" + (f"  (antes {ses_antes})" if ses_antes else ""))
    if hotspot >= 0:
        lineas.append(f"  hotspot activos  {hotspot}" + (f"  (antes {hs_antes})" if hs_antes else ""))

    problemas = []
    if not datos["wan_running"]:
        problemas.append(f"la interfaz WAN ({datos['iface']}) está caída")
    if not datos["wan_ip"]:
        problemas.append("la WAN no tiene dirección asignada")
    if peor >= 100:
        problemas.append("el router no llega a internet (100% de pérdida)")
    elif peor >= 50:
        problemas.append(f"pérdida de paquetes alta hacia internet ({peor}%)")

    # Desplome de uso: la señal más honesta de que la gente se quedó sin servicio.
    for etiqueta, actual, antes in (
        ("sesiones NAT", sesiones, ses_antes),
        ("clientes del hotspot", hotspot, hs_antes),
    ):
        if antes and antes > 20 and actual >= 0 and actual < antes * (1 - CAIDA_USO_PCT / 100):
            problemas.append(
                f"{etiqueta} se desplomó de {antes} a {actual}: el hotel pudo quedarse sin servicio"
            )

    # ¿Hay servicio esencial en nuestra lista de bloqueo?
    bloqueadas = _ips_bloqueadas()
    esenciales = [ip for ip in _destinos() if ip in bloqueadas]
    if esenciales:
        problemas.append(f"Shomer está bloqueando destinos esenciales: {esenciales}")

    if not args.silencioso or problemas:
        print(f"[{ahora}] internet del hotel (medido desde el router)")
        print("\n".join(lineas))

    if problemas:
        detalle = "; ".join(problemas)
        print(f"\n*** PROBLEMA: {detalle} ***")
        try:
            from app.scripts.alerts import send_telegram_alert
            send_telegram_alert(
                "🔴 <b>Internet del hotel — revisar</b>\n"
                f"{detalle}\n"
                f"WAN {datos['iface']}: {'arriba' if datos['wan_running'] else 'caída'} · "
                f"pérdida máx {peor}% · sesiones {sesiones}"
            )
        except Exception as e:
            print(f"  (no se pudo avisar por Telegram: {e})")
        return 2

    if not args.silencioso:
        print("\n  El hotel tiene internet y hay tráfico real pasando.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
