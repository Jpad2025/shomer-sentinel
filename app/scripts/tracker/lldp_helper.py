"""
Tracker — Helper de vecinos LLDP/CDP/EDP/FDP/SONMP.

Lee la salida JSON de `lldpcli show neighbors -f json0` y normaliza cada
vecino a un dict homogéneo indexable por IP y/o MAC. Uso típico:

    neighbors = get_lldp_neighbors()
    info = neighbors.by_ip.get("192.168.1.88") or neighbors.by_mac.get("54:05:db:d1:a2:ad")

Mapeo de capacidades LLDP -> asset_type del Tracker:
    Router enabled     -> "Router"
    Bridge + Wlan      -> "AP"
    Bridge only        -> "Switch"
    Wlan only          -> "AP"
    Telephone          -> "Telefonía IP"
    Station only       -> "PC/Endpoint"

Protocolos soportados (cuando `configure` apropiado en /etc/lldpd.d/):
    LLDP, CDP (Cisco), EDP (Extreme), FDP (Foundry), SONMP (Nortel/Avaya).

Seguro frente a fallos: si `lldpcli` no está instalado, el servicio no
corre o la salida es inesperada, devuelve un LLDPIndex vacío sin
excepción.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _log():
    from . import get_logger
    return get_logger("tracker.lldp")


@dataclass
class LLDPNeighbor:
    """Un vecino detectado por LLDP/CDP/etc., normalizado."""
    local_iface: str = ""        # Interfaz de Shomer por donde se le oyó
    via: str = ""                # Protocolo: LLDP/CDP/EDP/FDP/SONMP
    mac: str = ""                # chassis.id type=mac
    name: str = ""               # chassis.name (hostname)
    descr: str = ""              # chassis.descr (modelo/SO)
    mgmt_ips: List[str] = field(default_factory=list)
    capabilities: Dict[str, bool] = field(default_factory=dict)
    port_mac: str = ""           # port.id type=mac
    port_descr: str = ""         # port.descr (nombre de puerto remoto)

    def asset_type(self) -> str:
        """Deriva asset_type a partir de las capabilities LLDP."""
        caps = self.capabilities or {}
        is_router = caps.get("Router", False)
        is_bridge = caps.get("Bridge", False)
        is_wlan = caps.get("Wlan", False)
        is_phone = caps.get("Telephone", False)
        if is_phone:
            return "Telefonía IP"
        if is_router:
            return "Router"
        if is_bridge and is_wlan:
            return "AP"
        if is_wlan:
            return "AP"
        if is_bridge:
            return "Switch"
        return ""

    def to_merge_dict(self) -> Dict[str, str]:
        """Devuelve sólo los campos no-vacíos listos para extractor.merge_asset."""
        out: Dict[str, str] = {}
        if self.name:
            out["hostname"] = self.name[:200]
        if self.descr:
            out["os_detected"] = self.descr[:400]
        at = self.asset_type()
        if at:
            out["asset_type"] = at
        out["lldp_via"] = self.via
        if self.port_descr:
            out["lldp_port"] = self.port_descr[:80]
        return out


@dataclass
class LLDPIndex:
    """Índice de vecinos LLDP. Vacío si lldpd no está disponible."""
    by_ip: Dict[str, LLDPNeighbor] = field(default_factory=dict)
    by_mac: Dict[str, LLDPNeighbor] = field(default_factory=dict)
    all: List[LLDPNeighbor] = field(default_factory=list)

    def lookup(self, ip: str = "", mac: str = "") -> Optional[LLDPNeighbor]:
        """Busca por IP primero, luego por MAC normalizada."""
        if ip and ip in self.by_ip:
            return self.by_ip[ip]
        if mac:
            key = mac.lower().replace("-", ":")
            if key in self.by_mac:
                return self.by_mac[key]
        return None


def _first_value(lst: Optional[List[Dict]]) -> str:
    """Extrae el primer 'value' de una lista tipo [{'value': '...'}] de lldpcli."""
    if not lst:
        return ""
    it = lst[0] if isinstance(lst, list) else lst
    if isinstance(it, dict):
        return str(it.get("value") or "").strip()
    return str(it).strip()


def _parse_capabilities(cap_list) -> Dict[str, bool]:
    """lldpcli devuelve: [{'type':'Bridge','enabled':true}, ...]"""
    out: Dict[str, bool] = {}
    if not cap_list:
        return out
    if isinstance(cap_list, dict):
        cap_list = [cap_list]
    for cap in cap_list:
        if not isinstance(cap, dict):
            continue
        t = str(cap.get("type") or "").strip()
        e = bool(cap.get("enabled", False))
        if t:
            out[t] = e
    return out


def _parse_chassis_id_mac(id_obj) -> str:
    """Extrae la MAC de un chassis.id o port.id (type='mac')."""
    if not id_obj:
        return ""
    if isinstance(id_obj, dict):
        id_obj = [id_obj]
    for el in id_obj:
        if isinstance(el, dict) and (el.get("type") or "").lower() == "mac":
            return str(el.get("value") or "").lower()
    return ""


def _parse_chassis_id_local(id_obj) -> str:
    """Extrae el hostname de un chassis.id type='local' (Windows anuncia así)."""
    if not id_obj:
        return ""
    if isinstance(id_obj, dict):
        id_obj = [id_obj]
    for el in id_obj:
        if isinstance(el, dict) and (el.get("type") or "").lower() == "local":
            return str(el.get("value") or "").strip()
    return ""


def _parse_interface(iface_entry: Dict) -> Optional[LLDPNeighbor]:
    """Parsea un objeto 'interface' del JSON de lldpcli."""
    if not isinstance(iface_entry, dict):
        return None
    n = LLDPNeighbor()
    n.local_iface = str(iface_entry.get("name") or "")
    n.via = str(iface_entry.get("via") or "")

    chassis_list = iface_entry.get("chassis") or []
    if isinstance(chassis_list, dict):
        chassis_list = [chassis_list]
    if not chassis_list:
        return None
    ch = chassis_list[0] if isinstance(chassis_list, list) else chassis_list
    if not isinstance(ch, dict):
        return None

    # MAC puede estar en chassis.id (type=mac) o en port.id (Windows
    # anuncia chassis.id como 'local'=hostname y la MAC va en port.id).
    n.mac = _parse_chassis_id_mac(ch.get("id"))
    n.name = _first_value(ch.get("name"))
    # Fallback de hostname: chassis.id type=local (caso Windows nativo)
    if not n.name:
        n.name = _parse_chassis_id_local(ch.get("id"))
    n.descr = _first_value(ch.get("descr"))
    n.capabilities = _parse_capabilities(ch.get("capability"))

    mgmt = ch.get("mgmt-ip") or []
    if isinstance(mgmt, dict):
        mgmt = [mgmt]
    for m in mgmt:
        if isinstance(m, dict):
            v = str(m.get("value") or "").strip()
            if v and ":" not in v[:5]:  # IPv4 simple, descarta IPv6 link-local
                n.mgmt_ips.append(v)

    port_list = iface_entry.get("port") or []
    if isinstance(port_list, dict):
        port_list = [port_list]
    if port_list:
        p = port_list[0] if isinstance(port_list, list) else port_list
        if isinstance(p, dict):
            n.port_mac = _parse_chassis_id_mac(p.get("id"))
            n.port_descr = _first_value(p.get("descr"))

    # Si chassis no trajo MAC pero port sí (caso Windows), usar esa
    if not n.mac and n.port_mac:
        n.mac = n.port_mac
    return n


def get_lldp_neighbors(exclude_self: bool = True) -> LLDPIndex:
    """
    Ejecuta `lldpcli show neighbors -f json0` y devuelve un LLDPIndex.

    Si `exclude_self` es True, filtra los vecinos cuyo SysName/MAC
    coincide con la propia máquina (Shomer tiene 2 NICs y se ve a sí
    mismo entre enp2s0 y enp4s0 cuando las dos están en el mismo switch).
    """
    log = _log()
    idx = LLDPIndex()
    try:
        proc = subprocess.run(
            ["/usr/sbin/lldpcli", "show", "neighbors", "-f", "json0"],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.debug("lldpcli no disponible o timeout: %s", e)
        return idx
    if proc.returncode != 0:
        log.debug("lldpcli exit=%s stderr=%s", proc.returncode, (proc.stderr or "")[:120])
        return idx

    raw = (proc.stdout or "").strip()
    if not raw:
        return idx
    try:
        data = json.loads(raw)
    except Exception as e:
        log.debug("lldpcli parse error: %s", e)
        return idx

    self_macs = _get_local_macs() if exclude_self else set()
    self_hostname = _get_local_hostname() if exclude_self else ""

    lldp_list = data.get("lldp") or []
    if isinstance(lldp_list, dict):
        lldp_list = [lldp_list]

    for entry in lldp_list:
        if not isinstance(entry, dict):
            continue
        ifaces = entry.get("interface") or []
        if isinstance(ifaces, dict):
            ifaces = [ifaces]
        for iface_entry in ifaces:
            n = _parse_interface(iface_entry)
            if not n:
                continue
            if exclude_self:
                if n.mac and n.mac in self_macs:
                    continue
                if self_hostname and n.name and n.name.lower() == self_hostname.lower():
                    continue
            idx.all.append(n)
            if n.mac:
                idx.by_mac[n.mac] = n
            for ip in n.mgmt_ips:
                idx.by_ip[ip] = n

    log.info("LLDP: %d vecinos útiles (tras filtrar self)", len(idx.all))
    return idx


def _get_local_macs() -> set:
    """MACs de las interfaces locales, normalizadas a lowercase con dos puntos."""
    macs = set()
    try:
        proc = subprocess.run(
            ["ip", "-o", "link", "show"], capture_output=True, text=True, timeout=4
        )
        for line in (proc.stdout or "").splitlines():
            parts = line.split("link/ether")
            if len(parts) >= 2:
                tail = parts[1].strip().split()[0]
                if len(tail) == 17:
                    macs.add(tail.lower())
    except Exception:
        pass
    return macs


def _get_local_hostname() -> str:
    try:
        import socket as _s
        return _s.gethostname()
    except Exception:
        return ""
