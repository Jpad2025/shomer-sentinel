"""
Topología de red L2/L3 — multimarca, config por sitio (system_state).

Proveedores previstos:
  - SNMP genérico (IF-MIB) — cualquier switch con SNMP v2c
  - UniFi Controller API — cuando topology.unifi.* esté configurado
  - MikroTik SSH/LLDP — futuro
  - Manual — panel / import CSV

No altera Guardian ni alertas por AP. Complementa status_events / Infra.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_api import get_current_user
from app.api.shomer_common import get_config, get_db, set_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["topology"])

CONFIG_PREFIX = "topology."


@dataclass
class NetworkLink:
    child_ip: str
    parent_ip: str
    parent_port: str = ""
    link_type: str = "unknown"  # poe | uplink | unknown
    source: str = "manual"  # manual | snmp | unifi | lldp
    child_name: str = ""
    parent_name: str = ""


@dataclass
class PortEvent:
    switch_ip: str
    port_name: str
    oper_status: str  # up | down
    ts: str = ""


def get_topology_config() -> Dict[str, Any]:
    raw = get_config(f"{CONFIG_PREFIX}enabled")
    enabled = bool(raw) if raw is not None else False
    return {
        "enabled": enabled,
        "poll_interval_sec": max(60, int(get_config(f"{CONFIG_PREFIX}poll_interval_sec") or 300)),
        "snmp_default_community": (get_config(f"{CONFIG_PREFIX}snmp.default_community") or "").strip(),
        "unifi_host": (get_config(f"{CONFIG_PREFIX}unifi.host") or "").strip(),
        "unifi_user": (get_config(f"{CONFIG_PREFIX}unifi.user") or "").strip(),
        "unifi_pass": (get_config(f"{CONFIG_PREFIX}unifi.pass") or "").strip(),
        "unifi_verify_ssl": bool(get_config(f"{CONFIG_PREFIX}unifi.verify_ssl") if get_config(f"{CONFIG_PREFIX}unifi.verify_ssl") is not None else False),
    }


_tables_ready = False


def _ensure_tables() -> None:
    # Guard de una sola vez evita CREATE TABLE repetido en el hilo único de Guardian por request.
    global _tables_ready
    if _tables_ready:
        return
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS network_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                child_ip TEXT NOT NULL,
                parent_ip TEXT NOT NULL,
                parent_port TEXT DEFAULT '',
                link_type TEXT DEFAULT 'unknown',
                source TEXT DEFAULT 'manual',
                child_name TEXT DEFAULT '',
                parent_name TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(child_ip, parent_ip, parent_port, source)
            );
            CREATE INDEX IF NOT EXISTS idx_network_links_child ON network_links (child_ip);
            CREATE INDEX IF NOT EXISTS idx_network_links_parent ON network_links (parent_ip);
        """)
        conn.commit()
    _tables_ready = True


class TopologyProvider(ABC):
    name: str = "base"

    @abstractmethod
    def discover_links(self) -> List[NetworkLink]:
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        ...


# LLDP-MIB (RFC 2922 / IEEE 802.1AB) — estándar, funciona igual en Cisco/HP/etc.
_OID_IFDESCR        = "1.3.6.1.2.1.2.2.1.2"       # ifIndex -> nombre de puerto local
_OID_LLDP_REM_SYSNAME = "1.0.8802.1.1.2.1.4.1.1.9"  # lldpRemSysName (nombre del vecino)
_OID_LLDP_REM_PORTID  = "1.0.8802.1.1.2.1.4.1.1.7"  # lldpRemPortId (MAC/puerto del vecino)


def _snmpwalk_qn(snmpwalk_bin: str, ip: str, community: str, oid: str, timeout: int = 5) -> Dict[str, str]:
    """Ejecuta snmpwalk -Oqn (OID numérico, valor limpio) y devuelve {oid_completo: valor}.
    Mismo patrón (subprocess + binario CLI) que _snmp_health_probes en
    shomer_guardian_health_checks.py -- consistente con el resto del proyecto."""
    import subprocess
    try:
        r = subprocess.run(
            [snmpwalk_bin, "-v2c", "-c", community, "-t", str(timeout), "-r", "1",
             "-Oqn", ip, oid],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if r.returncode != 0:
            return {}
        out: Dict[str, str] = {}
        for line in r.stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            full_oid = parts[0].lstrip(".")
            value = parts[1].strip().strip('"')
            # Errores SNMP reales (agente sin ese sub-árbol MIB, ej. LLDP deshabilitado
            # o switch que no lo soporta) vienen como texto plano, no como OID walkeado
            # -- detectado en producción el 6 sep 2026 contra SW Piso 7 (192.168.0.118).
            if not full_oid.startswith(oid) or value.lower().startswith(
                ("no such object", "no such instance", "end of mib", "timeout")
            ):
                continue
            out[full_oid] = value
        return out
    except Exception as e:
        logger.debug("topology snmpwalk %s oid=%s: %s", ip, oid, e)
        return {}


def _lldp_neighbors(snmpwalk_bin: str, ip: str, community: str) -> List[tuple[str, str, str]]:
    """Consulta LLDP-MIB real vía SNMP. Devuelve [(puerto_local, nombre_vecino, id_puerto_vecino)].
    Verificado contra switch real (Cisco Sx220, 192.168.0.146) el 6 sep 2026 --
    responde nombres de vecino reales (ej. 'P1OFCCONTABILIDAD'), no simulado."""
    ifdescr  = _snmpwalk_qn(snmpwalk_bin, ip, community, _OID_IFDESCR)
    sysnames = _snmpwalk_qn(snmpwalk_bin, ip, community, _OID_LLDP_REM_SYSNAME)
    portids  = _snmpwalk_qn(snmpwalk_bin, ip, community, _OID_LLDP_REM_PORTID)

    results: List[tuple[str, str, str]] = []
    for full_oid, sysname in sysnames.items():
        if not sysname:
            continue
        # full_oid = "1.0.8802.1.1.2.1.4.1.1.9.<timemark>.<localport>.<index>"
        parts = full_oid.split(".")
        if len(parts) < 2:
            continue
        local_port_num = parts[-2]
        local_port_name = ifdescr.get(f"{_OID_IFDESCR}.{local_port_num}", f"if{local_port_num}")
        remote_port_id = portids.get(full_oid.replace(_OID_LLDP_REM_SYSNAME, _OID_LLDP_REM_PORTID, 1), "")
        results.append((local_port_name, sysname, remote_port_id))
    return results


class SnmpSwitchProvider(TopologyProvider):
    """Descubrimiento real de topología vía LLDP-MIB (SNMP), usando los switches
    activos de infra_devices y su snmp_community individual."""

    name = "snmp"

    def is_configured(self) -> bool:
        _ensure_tables()
        with get_db() as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM infra_devices WHERE active=1 AND device_type='switch'"
            ).fetchone()[0]
        return n > 0

    def discover_links(self) -> List[NetworkLink]:
        """Descubrimiento real: consulta LLDP por SNMP a cada switch activo y
        resuelve el nombre del vecino contra infra_devices cuando coincide
        (revela enlaces switch-switch/AP reales, no solo lo cargado a mano)."""
        import shutil
        _ensure_tables()
        snmpwalk_bin = shutil.which("snmpwalk")
        if not snmpwalk_bin:
            logger.warning("topology: snmpwalk no disponible en el sistema -- sin descubrimiento SNMP")
            return []

        with get_db() as conn:
            switches = conn.execute(
                "SELECT ip, name, snmp_community FROM infra_devices "
                "WHERE active=1 AND device_type='switch'"
            ).fetchall()
            known_by_name = {
                (r["name"] or "").strip().lower(): r["ip"]
                for r in conn.execute(
                    "SELECT ip, name FROM infra_devices WHERE active=1 AND name IS NOT NULL"
                ).fetchall()
            }

        # Cada switch es una consulta de red independiente -- en paralelo evita que
        # un switch sin LLDP (agota su timeout) alargue serialmente todo el ciclo.
        # Medido en producción el 6 sep 2026: 8 switches en serie con 1-2 caídos
        # de LLDP se acercaba a 2 minutos; en paralelo baja a ~10s.
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _query(sw) -> tuple[str, str, list]:
            ip = sw["ip"]
            name = sw["name"] or ip
            community = (sw["snmp_community"] or "public").strip() or "public"
            try:
                return ip, name, _lldp_neighbors(snmpwalk_bin, ip, community)
            except Exception as e:
                logger.debug("topology: descubrimiento LLDP falló para %s: %s", ip, e)
                return ip, name, []

        links: List[NetworkLink] = []
        seen: set[tuple[str, str, str]] = set()  # (parent_ip, parent_port, child_name)
        with ThreadPoolExecutor(max_workers=max(1, len(switches))) as pool:
            futures = [pool.submit(_query, sw) for sw in switches]
            for fut in as_completed(futures):
                ip, name, neighbors = fut.result()
                for local_port, remote_name, remote_port_id in neighbors:
                    # Un mismo puerto puede reportar el mismo vecino varias veces
                    # (entradas LLDP acumuladas sin limpiar en el propio switch --
                    # visto en producción el 6 sep 2026, 4x "MK-OPERA" en un puerto).
                    dedup_key = (ip, local_port, remote_name)
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    child_ip = known_by_name.get(remote_name.strip().lower(), "")
                    links.append(NetworkLink(
                        child_ip=child_ip,
                        parent_ip=ip,
                        parent_port=local_port,
                        link_type="lldp",
                        source="snmp",
                        child_name=remote_name,
                        parent_name=name,
                    ))
        return links


class UniFiControllerProvider(TopologyProvider):
    """UniFi Network Application — requiere topology.unifi.host + credenciales."""

    name = "unifi"

    def __init__(self, cfg: Dict[str, Any]):
        self._cfg = cfg

    def is_configured(self) -> bool:
        return bool(self._cfg.get("unifi_host") and self._cfg.get("unifi_user"))

    def discover_links(self) -> List[NetworkLink]:
        if not self.is_configured():
            return []
        # TODO: login API local / cloud, mapear AP mac → switch port
        logger.debug("UniFi topology: pendiente credenciales/host en %s", self._cfg.get("unifi_host"))
        return []


def get_providers() -> List[TopologyProvider]:
    cfg = get_topology_config()
    providers: List[TopologyProvider] = [SnmpSwitchProvider()]
    if cfg.get("unifi_host"):
        providers.append(UniFiControllerProvider(cfg))
    return providers


def correlate_outage_to_switches(child_ips: List[str]) -> Dict[str, Any]:
    """
    Dado un conjunto de IPs caídas, agrupa por switch padre (network_links).
    Usado por status_events post-oleada cuando topology.enabled=true.
    """
    _ensure_tables()
    if not child_ips:
        return {"groups": [], "unmapped": []}

    with get_db() as conn:
        placeholders = ",".join("?" * len(child_ips))
        rows = conn.execute(
            f"SELECT child_ip, parent_ip, parent_port, parent_name, child_name "
            f"FROM network_links WHERE child_ip IN ({placeholders})",
            child_ips,
        ).fetchall()

    by_parent: Dict[str, Dict[str, Any]] = {}
    mapped = set()
    for r in rows:
        mapped.add(r["child_ip"])
        pid = r["parent_ip"]
        if pid not in by_parent:
            by_parent[pid] = {
                "parent_ip": pid,
                "parent_name": r["parent_name"] or pid,
                "ports": set(),
                "children": [],
            }
        by_parent[pid]["children"].append({"ip": r["child_ip"], "name": r["child_name"] or r["child_ip"]})
        if r["parent_port"]:
            by_parent[pid]["ports"].add(r["parent_port"])

    groups = []
    for g in by_parent.values():
        g["ports"] = sorted(g["ports"])
        g["count"] = len(g["children"])
        groups.append(g)
    groups.sort(key=lambda x: -x["count"])

    unmapped = [ip for ip in child_ips if ip not in mapped]
    return {"groups": groups, "unmapped": unmapped}


def upsert_link(link: NetworkLink) -> None:
    _ensure_tables()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute(
            """INSERT INTO network_links
               (child_ip, parent_ip, parent_port, link_type, source, child_name, parent_name, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(child_ip, parent_ip, parent_port, source) DO UPDATE SET
                 link_type=excluded.link_type,
                 child_name=excluded.child_name,
                 parent_name=excluded.parent_name,
                 updated_at=excluded.updated_at""",
            (
                link.child_ip,
                link.parent_ip,
                link.parent_port or "",
                link.link_type,
                link.source,
                link.child_name,
                link.parent_name,
                now,
            ),
        )
        conn.commit()


def run_discovery() -> Dict[str, Any]:
    """Corre discover_links() de todos los proveedores configurados y persiste
    los resultados. Nada llamaba a esto antes del 6 sep 2026 -- discover_links()
    existía pero estaba completamente desconectado de cualquier flujo real."""
    _ensure_tables()
    results: Dict[str, int] = {}
    total = 0
    for provider in get_providers():
        if not provider.is_configured():
            results[provider.name] = 0
            continue
        try:
            links = provider.discover_links()
        except Exception as e:
            logger.warning("topology: proveedor %s falló: %s", provider.name, e)
            results[provider.name] = 0
            continue
        for link in links:
            upsert_link(link)
        results[provider.name] = len(links)
        total += len(links)
    return {"success": True, "total_links": total, "by_provider": results}


class LinkBody(BaseModel):
    child_ip: str
    parent_ip: str
    parent_port: str = ""
    link_type: str = "poe"
    source: str = "manual"
    child_name: str = ""
    parent_name: str = ""


@router.get("/api/topology/config")
async def api_topology_config(user=Depends(get_current_user)):
    _ensure_tables()
    return {"success": True, "config": get_topology_config()}


@router.post("/api/topology/discover")
async def api_topology_discover(user=Depends(get_current_user)):
    """Dispara el descubrimiento real (LLDP/SNMP + UniFi si está configurado)
    y persiste los enlaces encontrados. Antes del 6 sep 2026 no existía forma
    de invocar discover_links() -- quedaba código muerto sin conectar."""
    import asyncio
    return await asyncio.to_thread(run_discovery)


@router.get("/api/topology/links")
async def api_topology_links(user=Depends(get_current_user)):
    _ensure_tables()
    with get_db() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT child_ip, parent_ip, parent_port, link_type, source, "
                "child_name, parent_name, updated_at FROM network_links "
                "ORDER BY parent_ip, child_ip"
            ).fetchall()
        ]
    return {"success": True, "count": len(rows), "links": rows}


@router.post("/api/topology/links")
async def api_topology_upsert_link(body: LinkBody, user=Depends(get_current_user)):
    if not body.child_ip.strip() or not body.parent_ip.strip():
        raise HTTPException(status_code=400, detail="child_ip y parent_ip requeridos")
    upsert_link(
        NetworkLink(
            child_ip=body.child_ip.strip(),
            parent_ip=body.parent_ip.strip(),
            parent_port=body.parent_port.strip(),
            link_type=body.link_type or "unknown",
            source=body.source or "manual",
            child_name=body.child_name.strip(),
            parent_name=body.parent_name.strip(),
        )
    )
    return {"success": True}


@router.post("/api/topology/config")
async def api_topology_save_config(body: dict = Body(...), user=Depends(get_current_user)):
    if "enabled" in body:
        set_config(f"{CONFIG_PREFIX}enabled", bool(body["enabled"]))
    if "unifi_host" in body:
        set_config(f"{CONFIG_PREFIX}unifi.host", str(body["unifi_host"] or ""))
    if "unifi_user" in body:
        set_config(f"{CONFIG_PREFIX}unifi.user", str(body["unifi_user"] or ""))
    if "unifi_pass" in body:
        set_config(f"{CONFIG_PREFIX}unifi.pass", str(body["unifi_pass"] or ""))
    if "snmp_default_community" in body:
        set_config(f"{CONFIG_PREFIX}snmp.default_community", str(body["snmp_default_community"] or ""))
    return {"success": True, "config": get_topology_config()}
