"""
Tracker - Capa de red: Nmap, ARP, detección de presencia.
Motor de identificación heurística: vendor por OUI (IEEE oui.txt o API con caché).
"""
import os
import re
import socket
import subprocess
import sys
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# Importación del logger (evitar circular)
def _log():
    from . import get_logger
    return get_logger("tracker.discovery")

DEFAULT_TARGETS = None  # Detectado dinámicamente por get_network_context()
HOST_TIMEOUT_SEC = 5

_REPORT_PREFIX = "Nmap scan report for "
_MAC_PREFIX = "MAC Address: "
_IP_RE = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
_MAC_RE = re.compile(r"([0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2})")

# Motor OUI: lista de rutas donde buscar oui.txt (IEEE); la primera existente se usa.
# Ruta canónica desde app.backend.db (partición p10)
try:
    import sys as _sys
    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if _root not in _sys.path:
        _sys.path.insert(0, _root)
    from app.backend.db import OUI_PATH as _STORAGE_OUI
except Exception:
    _STORAGE_OUI = "/storage/db/oui.txt"
OUI_FILE_PATHS = [
    os.environ.get("OUI_FILE"),
    _STORAGE_OUI,
    "/opt/network_monitor/data/oui.txt",
    "/usr/share/ieee-data/oui.txt",
]
OUI_DOWNLOAD_URL = "https://standards-oui.ieee.org/oui.txt"
_OUI_CACHE: Optional[Dict[str, str]] = None
_OUI_CACHE_PATH = _STORAGE_OUI


def _load_oui_from_file(path: str) -> Dict[str, str]:
    """Parsea oui.txt (formato IEEE: '00-0C-29 (hex)\\tVendor Name')."""
    out: Dict[str, str] = {}
    # Líneas: 28-6F-B9 (hex) Nokia Shanghai Bell Co., Ltd.
    line_re = re.compile(r"^([0-9A-Fa-f]{2})-([0-9A-Fa-f]{2})-([0-9A-Fa-f]{2})\s+\(hex\)\s+(.+)$")
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                m = line_re.match(line)
                if m:
                    oui = (m.group(1) + m.group(2) + m.group(3)).upper()
                    vendor = (m.group(4) or "").strip()[:120]
                    if oui and vendor:
                        out[oui] = vendor
    except OSError:
        pass
    return out


def _download_oui_to(path: str) -> bool:
    """Descarga oui.txt de la IEEE y lo guarda en path."""
    try:
        req = urllib.request.Request(OUI_DOWNLOAD_URL, headers={"User-Agent": "ShomerTracker/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        dirpath = os.path.dirname(path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        _log().warning("OUI download failed: %s", e)
        return False


def _get_oui_cache() -> Dict[str, str]:
    """Carga OUI desde archivo local o descarga; caché en memoria."""
    global _OUI_CACHE
    if _OUI_CACHE is not None:
        return _OUI_CACHE
    for path in OUI_FILE_PATHS:
        if not path or not os.path.isfile(path):
            continue
        _OUI_CACHE = _load_oui_from_file(path)
        if _OUI_CACHE:
            _log().info("OUI loaded from %s (%d entries)", path, len(_OUI_CACHE))
            return _OUI_CACHE
    if os.path.isdir(os.path.dirname(_OUI_CACHE_PATH) or "."):
        if _download_oui_to(_OUI_CACHE_PATH):
            _OUI_CACHE = _load_oui_from_file(_OUI_CACHE_PATH)
            if _OUI_CACHE:
                return _OUI_CACHE
    _OUI_CACHE = {}
    return _OUI_CACHE


def _vendor_from_mac(mac: str) -> str:
    """
    Vendor desde OUI: oui.txt local (IEEE) o descarga con caché.
    MAC 00:0c:29 -> OUI 000C29 -> VMware, etc.
    """
    mac = (mac or "").replace(":", "").replace("-", "").upper()
    if len(mac) < 6:
        return ""
    oui = mac[:6]
    return _get_oui_cache().get(oui, "")


# Heurística vendor -> asset_type. Permite clasificar infraestructura
# (routers/APs/firewalls/impresoras/cámaras) incluso cuando SNMP está
# apagado y WMI/SSH no aplican — escenario típico en redes SOHO/hotel
# reales. El substring se busca case-insensitive. El orden importa:
# especificidad descendente (matches más específicos primero).
_VENDOR_ASSET_TYPE_RULES: List[Tuple[str, str]] = [
    # Firewalls dedicados
    ("fortinet", "Firewall"),
    ("palo alto", "Firewall"),
    ("sonicwall", "Firewall"),
    ("watchguard", "Firewall"),
    ("sophos", "Firewall"),
    ("check point", "Firewall"),
    ("barracuda", "Firewall"),
    ("juniper", "Firewall"),
    # Routers / APs / switches
    ("mikrotik", "Router"),
    ("routerboard", "Router"),
    ("tp-link", "Router"),
    ("tplink", "Router"),
    ("ubiquiti", "AP"),
    ("ruckus", "AP"),
    ("aruba", "AP"),
    ("meraki", "AP"),
    ("gl technologies", "Router"),
    ("gl-inet", "Router"),
    ("asustek", "Router"),
    ("d-link", "Router"),
    ("netgear", "Router"),
    ("linksys", "Router"),
    ("huawei technologies", "Router"),
    ("tenda", "Router"),
    ("openwrt", "Router"),
    ("cisco-linksys", "Router"),
    ("cisco systems", "Switch"),
    ("cisco", "Switch"),
    ("hewlett packard enterprise", "Switch"),
    ("brocade", "Switch"),
    ("extreme networks", "Switch"),
    # PCs OEM (antes que reglas de impresora genéricas)
    ("lcfc", "laptop"),
    ("compal", "laptop"),
    # Impresoras
    ("hewlett-packard printer", "Printer"),
    # HP Inc. en OUI es la división de PCs; impresoras suelen usar otro string OUI.
    ("hp inc", "laptop"),
    ("epson", "Printer"),
    ("canon", "Printer"),
    ("brother industries", "Printer"),
    ("kyocera", "Printer"),
    ("ricoh", "Printer"),
    ("lexmark", "Printer"),
    ("xerox", "Printer"),
    ("zebra technologies", "Printer"),
    # Cámaras IP
    ("hikvision", "Cámara"),
    ("dahua", "Cámara"),
    ("axis communications", "Cámara"),
    ("foscam", "Cámara"),
    ("hanwha", "Cámara"),
    ("mobotix", "Cámara"),
    ("reolink", "Cámara"),
    ("vivotek", "Cámara"),
    # VoIP
    ("grandstream", "Telefonía IP"),
    ("yealink", "Telefonía IP"),
    ("polycom", "Telefonía IP"),
    ("snom", "Telefonía IP"),
    # Hints débiles (al final)
    ("apple", "Dispositivo Apple"),
    ("raspberry pi", "SBC/Embedded"),
]


def guess_asset_type_from_vendor(vendor: str) -> str:
    """Adivina asset_type a partir del vendor OUI. "" si no hay match.

    Fallback usado cuando SNMP no responde (router con SNMP apagado,
    caso mayoritario en hoteles) y WMI/SSH no aplican. El valor es un
    "best guess" y NO debe sobrescribir información más fuerte
    (SNMP sysObjectID, WMI Chassis, banner web). La consolidación de
    prioridades se hace en scanner.consolidate_identity.
    """
    v = (vendor or "").lower()
    if not v:
        return ""
    for substr, atype in _VENDOR_ASSET_TYPE_RULES:
        if substr in v:
            return atype
    return ""


def get_targets() -> List[str]:
    import os
    raw = os.environ.get("INVENTORY_SCAN_TARGETS", "")
    parts = [p.strip() for p in raw.split() if p.strip()]
    if parts:
        return parts
    # Detectar subred dinámicamente
    try:
        from app.scripts.network_context import get_network_context
        ctx = get_network_context()
        if ctx.get("subnet"):
            return [ctx["subnet"]]
    except Exception:
        pass
    return []


def _ip_in_targets(ip: str, targets: List[str]) -> bool:
    """True si ip pertenece a alguno de los targets (IP suelta o CIDR).

    Usado para restringir el enriquecimiento ARP al scope del scan.
    """
    try:
        import ipaddress
        ip_obj = ipaddress.ip_address(ip)
    except (ValueError, TypeError):
        return False
    for t in targets or []:
        t = (t or "").strip()
        if not t:
            continue
        try:
            if "/" in t:
                if ip_obj in ipaddress.ip_network(t, strict=False):
                    return True
            else:
                if str(ip_obj) == t:
                    return True
        except (ValueError, TypeError):
            continue
    return False


def _port_open(ip: str, port: int, timeout: float = 2.0) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        r = s.connect_ex((ip, port))
        s.close()
        return r == 0
    except Exception:
        return False


def get_arp_table() -> Dict[str, str]:
    """Ejecuta ip neigh show (y opcionalmente arp -a) y devuelve dict IP -> MAC."""
    ip_to_mac: Dict[str, str] = {}
    mac_re = re.compile(r"([0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2})")
    ip_re = re.compile(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b")
    for _binary, cmd in [(False, ["ip", "neigh", "show"]), (False, ["arp", "-a"])]:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            out = (proc.stdout or "") + (proc.stderr or "")
            for line in out.splitlines():
                ips = ip_re.findall(line)
                macs = mac_re.findall(line)
                if ips and macs and macs[0] != "00:00:00:00:00:00":
                    ip_to_mac[ips[0]] = macs[0]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return ip_to_mac


def _is_real_mac(mac: str) -> bool:
    """True si es una MAC válida (XX:XX:XX:XX:XX:XX). NUNCA true para prefijo ip-."""
    if not mac or (mac or "").strip().startswith("ip-"):
        return False
    s = (mac or "").strip().replace("-", ":")
    return bool(_MAC_RE.fullmatch(s)) and s != "00:00:00:00:00:00"


def _empty_host(ip: str, mac: str, vendor: str = "", hostname: str = "") -> Dict[str, Any]:
    return {
        "ip": ip,
        "mac": mac,
        "vendor": vendor,
        "hostname": hostname,
        "ports_open": "",
        "asset_type": "",
        "os_family": "",
        "os_version": "",
        "cpu": "",
        "ram": "",
        "storage_cap": "",
        "serial_number": "",
        "firmware_version": "",
        "os_detected": "",
        "software_list": "",
        "software_updates": "",
    }


def _parse_nmap_plain_text(raw_out: str, arp_table: Dict[str, str]) -> List[Dict[str, Any]]:
    """Parser texto plano nmap -sn. Extrae IP, MAC y vendor por host."""
    hosts: List[Dict[str, Any]] = []
    current_ip = ""
    current_hostname = ""
    current_mac = ""
    current_vendor = ""
    for line in raw_out.splitlines():
        line = line.strip()
        if line.startswith(_REPORT_PREFIX):
            if current_ip:
                mac = current_mac if _is_real_mac(current_mac) else (arp_table.get(current_ip, "") or "")
                if not _is_real_mac(mac):
                    mac = "ip-%s" % current_ip
                hosts.append(_empty_host(current_ip, mac, current_vendor, current_hostname))
            rest = line[len(_REPORT_PREFIX):].strip()
            ips = _IP_RE.findall(rest)
            current_ip = ips[0] if ips else ""
            current_hostname = ""
            if current_ip and rest != current_ip:
                current_hostname = rest.replace("(" + current_ip + ")", "").strip()
            current_mac = ""
            current_vendor = ""
        elif line.startswith(_MAC_PREFIX):
            rest = line[len(_MAC_PREFIX):].strip()
            macs = _MAC_RE.findall(rest)
            if macs:
                current_mac = macs[0]
                m = re.search(r"\(([^)]+)\)", rest)
                if m:
                    current_vendor = m.group(1).strip()[:200]
    if current_ip:
        mac = current_mac if _is_real_mac(current_mac) else (arp_table.get(current_ip, "") or "")
        if not _is_real_mac(mac):
            mac = "ip-%s" % current_ip
        hosts.append(_empty_host(current_ip, mac, current_vendor, current_hostname))
    return hosts


def discovery_nmap(targets: List[str], use_pn: bool = False) -> List[Dict[str, Any]]:
    """
    Discovery con sudo nmap -sn en texto plano. Cruce con ip neighbor para MACs.
    """
    log = _log()
    log.info("[INFO] Discovery started (targets=%s)", len(targets))
    hosts: List[Dict[str, Any]] = []
    if not targets:
        log.info("[INFO] Discovery finished: 0 hosts (no targets)")
        return hosts
    arp_table = get_arp_table()
    if arp_table:
        log.info("ARP/neigh: %d entries", len(arp_table))
    cmd = [
        "sudo", "-n",
        "/usr/bin/nmap", "-sn", "-R",
        "--host-timeout", "%ds" % max(HOST_TIMEOUT_SEC, 6),
    ]
    if use_pn:
        cmd.append("-Pn")
    cmd.extend(targets)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.warning("Nmap error: %s", e)
        log.info("[INFO] Discovery finished: 0 hosts (nmap failed)")
        return hosts
    raw_out = proc.stdout or ""
    if proc.returncode not in (0, 1):
        log.info("[INFO] Discovery finished: 0 hosts (nmap exit %s)", proc.returncode)
        return hosts
    hosts = _parse_nmap_plain_text(raw_out, arp_table)

    # Enriquecimiento ARP: hay hosts (p.ej. Linux en swap/sleep) que no responden
    # a tiempo al nmap -sn pero tienen entrada ARP reciente porque se han visto
    # en el switch hace poco. Los agregamos aquí para que el scan no los pierda.
    ips_found = {h.get("ip", "") for h in hosts if h.get("ip")}
    for arp_ip, arp_mac in arp_table.items():
        if arp_ip in ips_found or not arp_ip:
            continue
        # Filtrar a las subredes objetivo para no meter vecinos fuera de scope
        if not _ip_in_targets(arp_ip, targets):
            continue
        log.info("Discovery: agregando %s (sólo ARP, nmap no lo detectó)", arp_ip)
        hosts.append(_empty_host(arp_ip, arp_mac, "", ""))

    for h in hosts:
        ip = h.get("ip", "")
        if ip and not (h.get("hostname") or "").strip():
            try:
                fqdn = socket.getfqdn(ip)
                if fqdn and fqdn != ip:
                    h["hostname"] = fqdn[:200]
            except Exception:
                pass
    log.info("[INFO] Discovery finished: %d hosts found", len(hosts))
    return hosts


def os_detection_aggressive(ip_list: List[str]) -> Dict[str, Dict[str, str]]:
    """nmap -sS -A -T4 por IP; retorna dict ip -> {os_detected, asset_model, ...}."""
    log = _log()
    result: Dict[str, Dict[str, str]] = {}
    if not ip_list:
        return result
    log.info("[INFO] OS detection (aggressive) started: %d IPs", len(ip_list[:200]))
    cmd = [
        "sudo", "-n",
        "/usr/bin/nmap", "-sS", "-A", "-T4", "-oX", "-",
        "--host-timeout", "45",
    ] + ip_list[:200]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        log.warning("OS detection nmap timeout or not found")
        log.info("[INFO] OS detection finished: 0 results")
        return result
    if proc.returncode not in (0, 1):
        log.info("[INFO] OS detection finished: 0 results (exit %s)", proc.returncode)
        return result
    raw = proc.stdout or ""
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(raw)
    except Exception:
        log.info("[INFO] OS detection finished: 0 results (parse error)")
        return result
    for host in root.findall("host"):
        ip = ""
        for addr in host.findall("address"):
            if addr.get("addrtype") == "ipv4":
                ip = addr.get("addr", "")
                break
        if not ip:
            continue
        result[ip] = {}
        os_el = host.find("os")
        if os_el is not None:
            for match in os_el.findall("osmatch"):
                name = (match.get("name") or "").strip()
                if name:
                    result[ip]["os_detected"] = name[:400]
                    break
        for port in host.findall("ports/port"):
            svc = port.find("service")
            if svc is None:
                continue
            product = (svc.get("product") or "").strip()
            version = (svc.get("version") or "").strip()
            if product and ip in result and "asset_model" not in result[ip]:
                val = (product + " " + version).strip()[:150]
                if val.lower() != "microsoft windows rpc":
                    result[ip]["asset_model"] = val
    log.info("[INFO] OS detection finished: %d IPs with data", len(result))
    return result


def scan_ports_per_host(ip: str, ports: str = "22,80,135,161,443,445,8080") -> List[str]:
    """Escaneo de puertos por host. Timeout 15s."""
    open_ports: List[str] = []
    try:
        proc = subprocess.run(
            ["/usr/bin/nmap", "-sT", "-p", ports, "--open", "-oX", "-", "--host-timeout", "8", ip],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return open_ports
    if proc.returncode not in (0, 1):
        return open_ports
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(proc.stdout or "")
        for host in root.findall("host"):
            for port_el in host.findall("ports/port"):
                if port_el.find("state") is not None and port_el.find("state").get("state") == "open":
                    portid = port_el.get("portid", "")
                    svc = port_el.find("service")
                    name = (svc.get("name", "") if svc is not None else "") or ""
                    open_ports.append("%s/%s" % (portid, name) if name else portid)
    except Exception:
        pass
    return open_ports
