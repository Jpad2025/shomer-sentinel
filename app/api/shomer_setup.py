"""
Wizard /setup/* — primera instalación, netplan, escaneo de IPs.
Extraído de shomer.py.
"""
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException

from app.api.auth_api import get_current_user, require_admin
from app.api.shomer_common import get_config, set_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Shomer Guardian"])


def _setup_list_ipv4_interfaces() -> Tuple[List[Dict[str, Any]], Optional[str], Optional[str]]:
    """
    Lista interfaces con IPv4 (ip -json). Defaults OEM desde env o primera/segunda NIC.
    """
    import json as _json
    from app.backend.db import SHOMER_MANAGEMENT_INTERFACE as _oem_m, SHOMER_MIRROR_INTERFACE as _oem_r

    rows: List[Dict[str, Any]] = []
    try:
        r = subprocess.run(
            ["ip", "-json", "addr", "show"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode != 0 or not r.stdout:
            return rows, _oem_m, _oem_r
        data = _json.loads(r.stdout)
        by_name: dict[str, dict] = {}
        for dev in data:
            name = dev.get("ifname") or ""
            if not name or name == "lo":
                continue
            for a in dev.get("addr_info") or []:
                if a.get("family") != "inet":
                    continue
                ip = a.get("local")
                plen = a.get("prefixlen", 24)
                if ip and name not in by_name:
                    by_name[name] = {"name": name, "ip": ip, "prefix": plen}
        rows = list(by_name.values())
    except Exception:
        return rows, _oem_m, _oem_r

    names = [x["name"] for x in rows]

    def _is_wired(n: str) -> bool:
        return n.startswith(("en", "eth")) and not n.startswith("wl")

    wired_names = [n for n in names if _is_wired(n)]
    if _oem_m and _oem_m in names:
        def_mgmt = _oem_m
    elif wired_names:
        def_mgmt = wired_names[0]
    else:
        def_mgmt = names[0] if names else None

    def_mir = None
    if _oem_r and _oem_r in names and _oem_r != def_mgmt:
        def_mir = _oem_r
    elif def_mgmt:
        wired_other = [n for n in wired_names if n != def_mgmt]
        if wired_other:
            def_mir = wired_other[0]
        else:
            def_mir = next((n for n in names if n != def_mgmt), None)
    return rows, def_mgmt, def_mir


@router.get("/setup/detect_nics")
async def setup_detect_nics(user=Depends(get_current_user)):
    """
    Lista NICs con IPv4 y sugerencias de gestión/mirror (OEM por env).
    Público — usado por el wizard de primera instalación.
    """
    rows, def_mgmt, def_mir = _setup_list_ipv4_interfaces()
    return {
        "success": True,
        "interfaces": rows,
        "default_management": def_mgmt,
        "default_mirror": def_mir,
    }


@router.get("/setup/status")
async def setup_status(user=Depends(get_current_user)):
    """
    Verifica si el sistema necesita configuración inicial.
    Retorna needs_setup=True si no hay base.subnet en system_state.
    Público (sin auth) para que /login pueda mostrar aviso de primera instalación.
    """
    subnet = get_config("base.subnet", None)
    try:
        from app.scripts.network_context import get_network_context

        ctx = get_network_context(None)
    except Exception:
        ctx = {}
    det_iface = ctx.get("interface")
    mgmt_oem = (os.environ.get("SHOMER_MANAGEMENT_INTERFACE") or "").strip()
    mir_oem = (os.environ.get("SHOMER_MIRROR_INTERFACE") or "").strip()
    return {
        "needs_setup": subnet is None,
        "configured": subnet is not None,
        "current": {
            "subnet": get_config("base.subnet", None),
            "gateway": get_config("base.gateway", None),
            "interface": get_config("base.interface", None) or det_iface,
            "server_ip": get_config("base.server_ip", None),
            "mirror_interface": get_config("base.mirror_interface", None),
            "mirror_ip": get_config("base.mirror_ip", None),
            "client_name":  get_config("base.client_name", None),
            "timezone":     get_config("base.timezone", "America/Denver"),
            "service_user": get_config("base.service_user", None),
        },
        "detected_interface": det_iface,
        # Despacho / campo: valores por defecto tras factory_reset_network (override con SHOMER_FACTORY_*)
        "factory": {
            "ip": (os.environ.get("SHOMER_FACTORY_IP") or "192.168.0.205").strip(),
            "subnet": (os.environ.get("SHOMER_FACTORY_SUBNET") or "192.168.0.0/24").strip(),
            "gateway": (os.environ.get("SHOMER_FACTORY_GW") or "192.168.0.1").strip(),
            "prefix": (os.environ.get("SHOMER_FACTORY_PREFIX") or "24").strip(),
            "setup_url_path": "/setup",
            "panel_port_hint": (os.environ.get("SHOMER_FACTORY_PANEL_PORT") or "8000").strip(),
            "management_interface_oem": mgmt_oem or None,
            "mirror_interface_oem": mir_oem or None,
        },
    }


@router.post("/setup/apply")
async def setup_apply(
    payload: Dict[str, Any] = Body(...),
    _admin: Dict[str, Any] = Depends(require_admin),
):
    """
    Aplica configuración de red (primera instalación o reconfiguración):
    1. Guarda en system_state
    2. Escribe /etc/netplan/01-network-config.yaml
    3. Ejecuta netplan apply
    Requiere sesión admin.

    Campos opcionales:
      wifi_ssid           — SSID WiFi (solo si internet via WiFi independiente)
      wifi_pass           — Password WiFi (NUNCA se persiste en ningún lado)
      use_client_internet — True = internet via gateway del cliente (Modo A)
                            False + wifi_ssid = internet via WiFi (Modo B)
    """
    import ipaddress as _ipaddress
    import re as _re

    ip_static = (payload.get("ip_static") or "").strip()
    subnet_payload = (payload.get("subnet") or "").strip()
    gateway = (payload.get("gateway") or "").strip()
    wifi_ssid = (payload.get("wifi_ssid") or "").strip()
    wifi_pass = (payload.get("wifi_pass") or "").strip()
    use_client_internet = bool(payload.get("use_client_internet", True))
    from app.backend.db import SHOMER_MANAGEMENT_INTERFACE
    from app.scripts.network_context import get_network_context as _gnc

    _ctx0 = _gnc(None)
    interface = (payload.get("interface") or "").strip() or (_ctx0.get("interface") or "") or (SHOMER_MANAGEMENT_INTERFACE or "")
    if not interface:
        raise HTTPException(
            status_code=400,
            detail="interface requerida (wizard) o variable de entorno SHOMER_MANAGEMENT_INTERFACE",
        )
    mirror_if = (payload.get("mirror_interface") or "").strip()
    mirror_ip_input = (payload.get("mirror_ip") or payload.get("mirror_ip_static") or "").strip()
    if mirror_ip_input and not mirror_if:
        raise HTTPException(
            status_code=400,
            detail="Indica el nombre de la interfaz mirror (NIC Hunter) para esa IP.",
        )

    if not ip_static:
        raise HTTPException(status_code=400, detail="ip_static requerida")

    try:
        _ipaddress.IPv4Address(ip_static)
        if subnet_payload:
            subnet_str = subnet_payload
        else:
            ctx = _gnc(interface_hint=interface)
            subnet_str = ctx.get("subnet") or f"{ip_static}/24"
        net = _ipaddress.IPv4Network(subnet_str, strict=False)
        prefix = net.prefixlen
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"IP o subnet inválida: {e}")

    if ip_static not in net:
        raise HTTPException(
            status_code=400,
            detail="La IP de gestión debe pertenecer a la subnet indicada",
        )

    mirror_cidr: str | None = None
    if mirror_if and mirror_ip_input:
        try:
            _ipaddress.IPv4Address(mirror_ip_input)
        except Exception:
            raise HTTPException(status_code=400, detail="mirror_ip con formato inválido")
        if mirror_ip_input not in net:
            raise HTTPException(
                status_code=400,
                detail="mirror_ip debe estar en la misma subnet que la red del cliente",
            )
        if mirror_ip_input == ip_static:
            raise HTTPException(
                status_code=400,
                detail="IP de gestión y IP del NIC mirror no pueden coincidir",
            )
        mirror_cidr = f"{mirror_ip_input}/{prefix}"
    elif mirror_if:
        try:
            with open("/etc/netplan/01-network-config.yaml", "r") as _f:
                _txt = _f.read()
            _m = _re.search(
                rf'{_re.escape(mirror_if)}:.*?addresses:\s*[\[\s]*-?\s*([\d.]+/\d+)',
                _txt,
                _re.DOTALL,
            )
            if _m:
                mirror_cidr = _m.group(1).strip()
        except Exception:
            pass

    if mirror_if and interface == mirror_if:
        raise HTTPException(
            status_code=400,
            detail="La interfaz de gestión y la de mirror (Hunter) deben ser distintas",
        )
    if mirror_if and not mirror_cidr:
        raise HTTPException(
            status_code=400,
            detail="Indica la IP del NIC mirror (misma subnet) o deja vacíos nombre e IP del mirror",
        )

    client_name  = (payload.get("client_name")  or "").strip()
    timezone     = (payload.get("timezone")     or "America/Denver").strip()
    service_user = (payload.get("service_user") or "").strip()
    service_pass = (payload.get("service_pass") or "").strip()
    if client_name:
        set_config("base.client_name", client_name)
    set_config("base.timezone", timezone)
    if service_user:
        set_config("base.service_user", service_user)
    if service_pass:
        set_config("base.service_password", service_pass)

    set_config("base.interface", interface)
    set_config("base.subnet", str(net))
    set_config("base.gateway", gateway)
    set_config("base.server_ip", ip_static)
    if mirror_if:
        set_config("base.mirror_interface", mirror_if)
        if mirror_ip_input:
            set_config("base.mirror_ip", mirror_ip_input)
        elif mirror_cidr:
            try:
                set_config("base.mirror_ip", mirror_cidr.split("/")[0])
            except Exception:
                pass
    else:
        set_config("base.mirror_interface", "")
        set_config("base.mirror_ip", "")
    set_config("guardian.subnets", [str(net)])
    set_config("tracker.subnets", [str(net)])
    hunter_ifaces = [interface] + ([mirror_if] if mirror_if else [])
    set_config("hunter.interfaces", hunter_ifaces)
    set_config("hunter.subnets", [str(net)])
    if wifi_ssid:
        set_config("wifi.ssid", wifi_ssid)

    mirror_block = ""
    if mirror_if and mirror_cidr:
        mirror_block = f"\n    {mirror_if}:\n      dhcp4: false\n      addresses: [{mirror_cidr}]"

    netplan_path = "/etc/netplan/01-network-config.yaml"
    netplan_ok = False

    if use_client_internet or not wifi_ssid:
        netplan_content = f"""network:
  version: 2
  ethernets:
    {interface}:
      dhcp4: false
      addresses: [{ip_static}/{prefix}]
      routes:
        - to: default
          via: {gateway}
      nameservers:
        addresses: [8.8.8.8, 1.1.1.1]{mirror_block}
"""
    else:
        netplan_content = f"""network:
  version: 2
  ethernets:
    {interface}:
      dhcp4: false
      addresses: [{ip_static}/{prefix}]
      nameservers:
        addresses: [8.8.8.8, 1.1.1.1]{mirror_block}
  wifis:
    wlp3s0:
      dhcp4: true
      access-points:
        "{wifi_ssid}":
          password: "{wifi_pass}"
"""

    try:
        proc = subprocess.run(
            ["sudo", "tee", netplan_path],
            input=netplan_content.encode(),
            capture_output=True,
            timeout=10,
        )
        if proc.returncode != 0:
            raise Exception(proc.stderr.decode())
        proc2 = subprocess.run(
            ["sudo", "netplan", "apply"],
            capture_output=True,
            timeout=15,
        )
        netplan_ok = proc2.returncode == 0
    except Exception as e:
        logger.error("Error aplicando netplan: %s", e)

    return {
        "success": True,
        "netplan_applied": netplan_ok,
        "new_ip": ip_static,
        "message": f"Conectate a http://{ip_static}:8000 para continuar",
    }


@router.post("/setup/scan_ips")
async def setup_scan_ips(
    payload: Optional[Dict[str, Any]] = Body(default=None),
    _admin: Dict[str, Any] = Depends(require_admin),
):
    """
    Escanea subnet (ping sweep). Si no viene subnet en el payload, detecta en vivo
    (skip_saved=True) para no usar solo BD ni la ruta por defecto equivocada (ej. WiFi).
    Acepta interface (NIC gestión) para forzar la subred cableada correcta.
    """
    import concurrent.futures
    import ipaddress as _ipaddress
    from app.scripts.network_context import get_network_context

    p = payload or {}
    subnet = (p.get("subnet") or "").strip()
    gateway = (p.get("gateway") or "").strip()
    iface_hint = (p.get("interface") or "").strip() or None

    if not subnet:
        try:
            ctx = get_network_context(interface_hint=iface_hint, skip_saved=True)
            subnet = ctx.get("subnet", "") or ""
            gateway = gateway or ctx.get("gateway", "") or ""
        except Exception:
            pass

    if not subnet:
        try:
            _rows, def_mgmt, _def_mir = _setup_list_ipv4_interfaces()
            if def_mgmt:
                ctx2 = get_network_context(interface_hint=def_mgmt, skip_saved=True)
                subnet = (ctx2.get("subnet") or "").strip()
                gateway = gateway or (ctx2.get("gateway") or "").strip()
        except Exception:
            pass

    if not subnet:
        raise HTTPException(
            status_code=400,
            detail="No se pudo detectar la subnet. Conecta el cable de gestión, rellena Subnet/Gateway a mano, o indica la interfaz de gestión (ej. enp2s0) y vuelve a escanear.",
        )

    try:
        _net_chk = _ipaddress.IPv4Network(subnet, strict=False)
        if gateway:
            try:
                _gw = _ipaddress.IPv4Address(gateway)
                if _gw not in _net_chk:
                    gateway = str(_net_chk.network_address + 1)
            except Exception:
                gateway = str(_net_chk.network_address + 1)
        else:
            gateway = str(_net_chk.network_address + 1)
    except Exception:
        pass

    try:
        net = _ipaddress.IPv4Network(subnet, strict=False)
    except Exception:
        raise HTTPException(status_code=400, detail="Subnet inválida")

    if net.num_addresses > 512:
        raise HTTPException(
            status_code=400,
            detail="Subnet muy grande — usar /24 o menor",
        )

    exclude = {str(net.network_address), str(net.broadcast_address), gateway}
    hosts = [h for h in net.hosts() if str(h) not in exclude]

    def ping_host(ip):
        try:
            r = subprocess.run(
                ["ping", "-c", "1", "-W", "1", str(ip)],
                capture_output=True,
                timeout=3,
            )
            return str(ip), r.returncode == 0
        except Exception:
            return str(ip), False

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(ping_host, hosts))

    occupied = [ip for ip, up in results if up]
    free = [ip for ip, up in results if not up]
    suggestions = free[-10:] if len(free) >= 10 else free

    return {
        "success": True,
        "subnet": subnet,
        "gateway": gateway,
        "total_hosts": len(hosts),
        "occupied": len(occupied),
        "free": len(free),
        "occupied_list": occupied,
        "suggestions": suggestions,
    }


@router.post("/setup/site-info")
async def setup_site_info(
    payload: Dict[str, Any] = Body(...),
    _admin: Dict[str, Any] = Depends(require_admin),
):
    """Actualiza nombre del sitio y timezone (editable post-setup sin reconfigurar red)."""
    import re as _re
    client_name  = (payload.get("client_name")  or "").strip()
    timezone     = (payload.get("timezone")     or "").strip()
    service_user = (payload.get("service_user") or "").strip()
    service_pass = (payload.get("service_pass") or "").strip()
    if client_name:
        set_config("base.client_name", client_name)
    if timezone:
        if not _re.match(r'^[A-Za-z_]+/[A-Za-z_]+$', timezone):
            raise HTTPException(status_code=400, detail="Timezone inválida (ej: America/Bogota)")
        set_config("base.timezone", timezone)
    if service_user:
        set_config("base.service_user", service_user)
    if service_pass:
        set_config("base.service_password", service_pass)
    return {
        "success":      True,
        "client_name":  get_config("base.client_name", ""),
        "timezone":     get_config("base.timezone", "America/Denver"),
        "service_user": get_config("base.service_user", ""),
    }


@router.post("/setup/test_wifi")
async def setup_test_wifi(payload: Dict[str, Any] = Body(...)):
    """Prueba conectividad a internet desde el Shomer."""
    try:
        r = subprocess.run(
            ["ping", "-c", "2", "-W", "2", "8.8.8.8"],
            capture_output=True,
            timeout=10,
        )
        has_internet = r.returncode == 0
    except Exception:
        has_internet = False
    return {
        "success": True,
        "has_internet": has_internet,
        "message": "Internet disponible" if has_internet else "Sin internet",
    }
