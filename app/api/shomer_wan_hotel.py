"""Estado del internet REAL del hotel, medido desde el gateway.

Distinto de `watch_wan_outage` (que reacciona cuando caen grupos de equipos) y
de la WAN del propio servidor: acá se mide lo que usan los huéspedes.

La distinción importa y costó aprenderla: que el servidor Shomer navegue NO
prueba que el hotel navegue. Shomer vive en la LAN de gestión, mientras que los
huéspedes salen por otras VLAN y por el hotspot, y la regla de bloqueo de Hunter
actúa sobre `chain=forward`, o sea justo sobre el tráfico de ellos. Shomer puede
navegar perfecto con el hotel caído.

Se mide desde el router, que es por donde sale todo el sitio:
  1. WAN física arriba y con dirección asignada.
  2. Salida real a internet desde el gateway (pérdida de paquetes).
  3. Uso real: sesiones NAT y clientes del hotspot. Un desplome acá es la señal
     más honesta de que la gente se quedó sin servicio, incluso cuando todo lo
     demás "responde".

Genérico (norma B.1): interfaz WAN y destinos salen de `system_state`; los
valores por defecto sirven en cualquier sitio y no hay nada de un cliente
concreto en el código.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.api.auth_api import get_current_user
from app.api.shomer_common import get_config, get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["wan-hotel"])

DESTINOS_DEFECTO = ["8.8.8.8", "1.1.1.1"]
# Caída de uso, respecto de la medición anterior, que se considera sospechosa.
CAIDA_USO_PCT = 80


def _cfg_router() -> Dict[str, str]:
    with get_db() as c:
        return {
            r[0].replace("hunter.firewall_", ""): r[1]
            for r in c.execute(
                "SELECT key,value FROM system_state WHERE key LIKE 'hunter.firewall_%'"
            )
        }


def wan_interface() -> str:
    return (get_config("base.wan_interface") or "ether3").strip()


def destinos_prueba() -> list:
    cfg = get_config("base.wan_test_ips")
    if cfg:
        try:
            datos = json.loads(cfg) if isinstance(cfg, str) else cfg
            if isinstance(datos, list) and datos:
                return datos
        except Exception:
            pass
    return DESTINOS_DEFECTO


def _guardar_uso(clave: str, valor: int):
    """Guarda la medición y devuelve la anterior, para comparar tendencia."""
    try:
        with get_db() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS wan_uso_historial ("
                "clave TEXT PRIMARY KEY, valor INTEGER, ts TEXT)"
            )
            row = con.execute(
                "SELECT valor FROM wan_uso_historial WHERE clave=?", (clave,)
            ).fetchone()
            anterior = row[0] if row else None
            con.execute(
                "INSERT INTO wan_uso_historial (clave, valor, ts) "
                "VALUES (?,?,datetime('now')) "
                "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor, ts=excluded.ts",
                (clave, valor),
            )
            con.commit()
            return anterior
    except Exception as e:
        logger.debug("wan hotel: historial de uso: %s", e)
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


async def medir_wan_hotel() -> Dict[str, Any]:
    """Consulta el gateway y devuelve el estado del internet del hotel."""
    import asyncssh

    cfg = _cfg_router()
    iface = wan_interface()
    datos: Dict[str, Any] = {"interfaz": iface, "ok": False, "problemas": []}

    try:
        async with asyncssh.connect(
            cfg["ip"], port=int(cfg.get("port", 22)), username=cfg["user"],
            password=cfg["pass"], known_hosts=None, connect_timeout=15,
        ) as con:
            r = await con.run(f'/interface print where name="{iface}"', timeout=20)
            datos["wan_arriba"] = bool(re.search(r"^\s*\d+\s+R\s", r.stdout or "", re.M))

            r = await con.run(f"/ip address print where interface={iface}", timeout=20)
            m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3}/\d+)", r.stdout or "")
            datos["wan_ip"] = m.group(1) if m else ""

            datos["perdida"] = {}
            for destino in destinos_prueba():
                r = await con.run(f"/ping {destino} count=3", timeout=30)
                m = re.search(r"packet-loss=(\d+)%", r.stdout or "")
                datos["perdida"][destino] = int(m.group(1)) if m else 100

            r = await con.run("/ip firewall connection print count-only", timeout=25)
            datos["sesiones"] = int((r.stdout or "0").strip() or 0)

            try:
                r = await con.run("/ip hotspot active print count-only", timeout=20)
                datos["hotspot"] = int((r.stdout or "0").strip() or 0)
            except Exception:
                datos["hotspot"] = -1  # el sitio puede no usar hotspot
    except Exception as e:
        datos["problemas"].append(
            f"no se pudo consultar el gateway ({type(e).__name__}): sin acceso al "
            "router no se puede afirmar nada del internet del hotel"
        )
        return datos

    datos["sesiones_antes"] = _guardar_uso("sesiones_nat", datos["sesiones"])
    if datos.get("hotspot", -1) >= 0:
        datos["hotspot_antes"] = _guardar_uso("hotspot_activos", datos["hotspot"])

    peor = max(datos["perdida"].values()) if datos["perdida"] else 100
    datos["perdida_max"] = peor

    if not datos.get("wan_arriba"):
        datos["problemas"].append(f"la interfaz WAN ({iface}) está caída")
    if not datos.get("wan_ip"):
        datos["problemas"].append("la WAN no tiene dirección asignada")
    if peor >= 100:
        datos["problemas"].append("el router no llega a internet (100% de pérdida)")
    elif peor >= 50:
        datos["problemas"].append(f"pérdida de paquetes alta hacia internet ({peor}%)")

    for etiqueta, actual, antes in (
        ("las sesiones de tráfico", datos.get("sesiones", -1), datos.get("sesiones_antes")),
        ("los huéspedes conectados", datos.get("hotspot", -1), datos.get("hotspot_antes")),
    ):
        if antes and antes > 20 and actual >= 0 and actual < antes * (1 - CAIDA_USO_PCT / 100):
            datos["problemas"].append(
                f"{etiqueta} cayeron de {antes} a {actual}: el hotel pudo quedarse sin servicio"
            )

    esenciales = [ip for ip in destinos_prueba() if ip in _ips_bloqueadas()]
    if esenciales:
        datos["problemas"].append(
            f"Shomer está bloqueando destinos esenciales: {', '.join(esenciales)}"
        )

    datos["ok"] = not datos["problemas"]
    return datos


@router.get("/api/wan-hotel")
async def api_wan_hotel(user=Depends(get_current_user)):
    """Estado del internet del hotel visto desde el gateway."""
    return {"success": True, **(await medir_wan_hotel())}
