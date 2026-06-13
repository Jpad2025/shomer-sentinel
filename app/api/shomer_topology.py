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


def _ensure_tables() -> None:
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


class TopologyProvider(ABC):
    name: str = "base"

    @abstractmethod
    def discover_links(self) -> List[NetworkLink]:
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        ...


class SnmpSwitchProvider(TopologyProvider):
    """Usa equipos switch de infra_devices + poll SNMP existente en Inframonitor."""

    name = "snmp"

    def is_configured(self) -> bool:
        _ensure_tables()
        with get_db() as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM infra_devices WHERE active=1 AND device_type='switch'"
            ).fetchone()[0]
        return n > 0

    def discover_links(self) -> List[NetworkLink]:
        """Placeholder: enlaces manuales + futura correlación MAC/LLDP."""
        _ensure_tables()
        with get_db() as conn:
            rows = conn.execute(
                "SELECT child_ip, parent_ip, parent_port, link_type, source, child_name, parent_name "
                "FROM network_links WHERE source IN ('manual', 'snmp', 'unifi')"
            ).fetchall()
        return [
            NetworkLink(
                child_ip=r["child_ip"],
                parent_ip=r["parent_ip"],
                parent_port=r["parent_port"] or "",
                link_type=r["link_type"] or "unknown",
                source=r["source"] or "manual",
                child_name=r["child_name"] or "",
                parent_name=r["parent_name"] or "",
            )
            for r in rows
        ]


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
