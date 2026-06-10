"""
Tracker - Capa de detalle (fingerprinting): SNMP, WMI, SSH, banner web, remedies.
Credenciales las recibe el orquestador (get_credentials + get_overrides_by_ip) y las pasa por host.
Timeouts estrictos: 12s SSH/WMI; 3s web. Un host 'zombie' no bloquea el inventario.
"""
import csv
import io
import json
import os
import re
import ssl
import subprocess
import sys
import time
import base64
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import http.client

# Ruta de remedies desde app.backend.db
def _get_remedies_path():
    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from app.backend.db import REMEDIES_JSON_PATH
    return REMEDIES_JSON_PATH

REMEDIES_JSON_PATH = _get_remedies_path()

PYTHON_VENV = "/opt/network_monitor/venv/bin/python3"
WMI_EXEC_PATH = os.environ.get("WMIEXEC_PATH", "/opt/network_monitor/venv/bin/wmiexec.py")
EXTRACTOR_SSH_WMI_TIMEOUT = 90
EXTRACTOR_WEB_TIMEOUT = 3

try:
    from pysnmp.hlapi import (
        getCmd,
        SnmpEngine,
        CommunityData,
        UdpTransportTarget,
        ContextData,
        ObjectType,
        ObjectIdentity,
    )
    PYSNMP_AVAILABLE = True
except ImportError:
    PYSNMP_AVAILABLE = False

try:
    import paramiko
    from paramiko.ssh_exception import IncompatiblePeer as _IncompatiblePeer
    PARAMIKO_AVAILABLE = True
except ImportError:
    paramiko = None  # type: ignore[assignment, misc]
    _IncompatiblePeer = None
    PARAMIKO_AVAILABLE = False

from .discovery import _port_open, _vendor_from_mac


def _log():
    from . import get_logger
    return get_logger("tracker.extractor")


_REMEDIES_CACHE: Optional[Dict[str, Any]] = None


def _load_remedies() -> Dict[str, Any]:
    """Carga /storage/db/remedies.json. Si no existe, no crashea: retorna {} y loguea error."""
    global _REMEDIES_CACHE
    if _REMEDIES_CACHE is not None:
        return _REMEDIES_CACHE
    path = REMEDIES_JSON_PATH
    if not path or not os.path.isfile(path):
        _log().error("remedies file not found: %s", path or "(empty path)")
        _REMEDIES_CACHE = {}
        return _REMEDIES_CACHE
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        _log().error("remedies load failed: %s", e)
        _REMEDIES_CACHE = {}
        return _REMEDIES_CACHE
    if not isinstance(data, dict):
        _REMEDIES_CACHE = {}
        return _REMEDIES_CACHE
    _REMEDIES_CACHE = data
    return data


# Regex de identidad por banner (capa aplicación): tipo de activo desde Server/título
# Se evalúan en orden: Firewall primero (más específico), luego Router/AP,
# luego Cámara/Impresora. La primera coincidencia gana.
_RE_FIREWALL = re.compile(
    r"(?i)("
    r"fortigate|fortinet|fortimanager|fortianalyzer|"
    r"palo\s*alto|panos|globalprotect|"
    r"sonicwall|sonicos|"
    r"watchguard|"
    r"sophos\s*(utm|xg|sfos|firewall)|"
    r"check\s*point|checkpoint\s*gaia|"
    r"barracuda|"
    r"pfsense|opnsense|"
    r"fireware|"
    r"cisco\s*(asa|firepower|ftd)|"
    r"meraki\s*mx|"
    r"untangle"
    r")"
)
_RE_ROUTER_AP = re.compile(
    r"(?i)("
    r"mikrotik|routeros|webfig|winbox|"
    r"openwrt|luci|"
    r"gl\.inet|gl-inet|"
    r"tp-link|tplink|tether|"
    r"d-link|dir-\d|"
    r"netgear|nighthawk|"
    r"asus\s*(router|wireless)|asuswrt|"
    r"linksys|"
    r"ubiquiti|unifi|edgeos|edgerouter|airos|"
    r"aruba\s*(instant|controller|ap)|"
    r"ruckus|zonedirector|"
    r"meraki"
    r")"
)
_RE_CAMARA = re.compile(
    r"(?i)(hikvision|dahua|axis|camera|vivotek|foscam|reolink|hanwha|mobotix|geovision|dvr)"
)
_RE_IMPRESORA = re.compile(
    r"(?i)(jetdirect|laserjet|officejet|designjet|brother\s|epson\s|canon\s|lexmark|xerox|ricoh|kyocera|zebra\s|hp-chai|cups)"
)


def _oui_vendor_suggests_network_cpe(v: str) -> bool:
    """
    OUI/MAC vendor apunta a router, AP o switch (CPE). Si además el HTTP
    parece impresora, es a menudo un título genérico, proxy o sesión equivocada.
    """
    s = (v or "").lower()
    return any(
        x in s
        for x in (
            "tp-link",
            "tplink",
            "mikrotik",
            "routerboard",
            "d-link",
            "netgear",
            "linksys",
            "asustek",
            "asus",
            "tenda",
            "gl technologies",
            "gl-inet",
            "cisco",
            "huawei",
            "zte",
            "fiberhome",
            "mercury",  # Mercury/TP-Link SOHO
            "zbt",  # OEM
        )
    )


def get_web_banner(
    ip: str,
    use_https: bool,
    timeout: float = 3.0,
    mac_vendor: str = "",
) -> Dict[str, str]:
    """
    Banner grabbing HTTP/HTTPS: cabecera Server y <title>.
    Aplica regex de identidad: Cámara (Hikvision, Dahua, Axis...) o Impresora (HP, Brother...).
    Devuelve dict con keys: server, title, asset_type (si aplica).
    """
    out: Dict[str, str] = {}
    t = min(float(timeout), EXTRACTOR_WEB_TIMEOUT) if timeout else EXTRACTOR_WEB_TIMEOUT
    try:
        if use_https:
            ctx = ssl._create_unverified_context()
            conn = http.client.HTTPSConnection(ip, 443, timeout=t, context=ctx)
        else:
            conn = http.client.HTTPConnection(ip, 80, timeout=t)
        conn.request("GET", "/", headers={"Host": ip, "User-Agent": "ShomerScanner/1.0"})
        resp = conn.getresponse()
        server = (resp.getheader("Server") or "").strip()[:200]
        if server:
            out["server"] = server
        if resp.status >= 400:
            conn.close()
            return out
        body = resp.read(8192).decode("utf-8", errors="ignore")
        conn.close()
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return out
    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
    title = ""
    if m:
        title = m.group(1).strip()
        title = re.sub(r"\s+", " ", title)[:200]
        out["title"] = title
    # Identidad por banner. Orden importa: más específico primero.
    # Firewall > Router/AP > Cámara > Impresora. Si ya había asset_type
    # puesto por otra fase (p.ej. OUI/SNMP), NO lo pisamos a menos que
    # el banner sea más específico (firewall/cámara/impresora ganan
    # sobre el hint OUI genérico "Router").
    banner_text = (server + " " + title).lower()
    prev = (out.get("asset_type") or "").strip()
    if _RE_FIREWALL.search(banner_text):
        out["asset_type"] = "Firewall"
    elif _RE_CAMARA.search(banner_text):
        out["asset_type"] = "Cámara"
    elif _RE_IMPRESORA.search(banner_text):
        if _oui_vendor_suggests_network_cpe(mac_vendor):
            # No forzar Impresora: el título (p. ej. "Canon…") choca con OUI CPE.
            out["identity_note"] = (
                "Título HTTP parece impresora; OUI indica equipo de red (CPE). "
                "Validar con gestión o firmware; el inventario no asume impresora."
            )[:300]
        else:
            out["asset_type"] = "Impresora"
    elif _RE_ROUTER_AP.search(banner_text) and not prev:
        # Sólo marcamos Router si no había nada antes, el banner de
        # routers es menos concluyente que OUI.
        out["asset_type"] = "Router"
    return out


def get_web_title(ip: str, use_https: bool, timeout: float = 3.0) -> str:
    """
    Banner grabbing HTTP/HTTPS; extrae <title>. Timeout estricto (3s por defecto).
    """
    d = get_web_banner(ip, use_https, timeout)
    return d.get("title", "")


def _snmp_get(ip: str, community: str, oid: str, timeout: float = 2.0) -> str:
    if not PYSNMP_AVAILABLE:
        return ""
    try:
        transport = UdpTransportTarget((ip, 161), timeout=timeout, retries=1)
        auth = CommunityData(community)
        for err_ind, err_status, err_idx, var_binds in getCmd(
            SnmpEngine(), auth, transport, ContextData(),
            ObjectType(ObjectIdentity(oid)),
        ):
            if err_ind or err_status:
                return ""
            for oid, val in var_binds:
                return str(val)[:500]
    except Exception:
        pass
    return ""


# sysDescr: inferencia IoT/embebido (Linux 4.4, armv7l, SMP)
_RE_SNMP_EMBEDDED = re.compile(r"(?i)(linux\s+[\d\.]+.*#\d+\s+smp|armv7l|armv6l|mips|openwrt|lede)")


def phase2_snmp(ip: str, community: str, timeout: float = 2.0) -> Dict[str, str]:
    out: Dict[str, str] = {}
    # NOTA: no pre-checkeamos con _port_open(ip, 161) porque eso usa TCP
    # y SNMP es UDP. _snmp_get() tiene su propio timeout y falla limpio si
    # la comunidad es incorrecta o el host no responde por UDP.
    if not PYSNMP_AVAILABLE:
        return out
    try:
        descr = _snmp_get(ip, community, "1.3.6.1.2.1.1.1.0", timeout=timeout)
        if descr:
            out["os_detected"] = descr
            out["snmp_sysdescr"] = descr  # Para consolidate_identity (prioridad Nmap > WMI/SSH > SNMP)
            m = re.search(r"^([A-Za-z0-9\-\+]+)\s+([A-Za-z0-9\-\.\s]+?)(?:\s+Series|\s*$|,|;)", descr)
            if m:
                out["vendor"] = out.get("vendor") or m.group(1).strip()[:80]
                out["asset_model"] = out.get("asset_model") or m.group(2).strip()[:120]
            if _RE_SNMP_EMBEDDED.search(descr) and not out.get("asset_type"):
                out["asset_type"] = "IoT/Router"
        name = _snmp_get(ip, community, "1.3.6.1.2.1.1.5.0", timeout=timeout)
        if name:
            out["hostname"] = name
        loc = _snmp_get(ip, community, "1.3.6.1.2.1.1.6.0", timeout=timeout)
        if loc:
            out["location"] = loc[:200]
        oid_val = _snmp_get(ip, community, "1.3.6.1.2.1.1.2.0", timeout=timeout)
        if oid_val:
            oid_str = oid_val.lower()
            if "printer" in oid_str or "print" in oid_str or "hpprinter" in oid_str:
                out["asset_type"] = "Printer"
            elif "wireless" in oid_str or "ap" in oid_str or "accesspoint" in oid_str:
                out["asset_type"] = "AP"
            else:
                out["asset_type"] = "Switch"
        if out.get("asset_type") == "Printer":
            toner = _snmp_get(ip, community, "1.3.6.1.2.1.43.11.1.1.9.1.1", timeout=timeout)
            if toner and toner.isdigit():
                out["software_list"] = (out.get("software_list") or "") + ("; Tóner: " + toner + "%") if out.get("software_list") else "Tóner: " + toner + "%"
    except Exception:
        out["snmp_status"] = "ERROR: SNMP sin respuesta o comunidad incorrecta"
        return out
    if out and "snmp_status" not in out:
        out["snmp_status"] = "OK"
    elif not out:
        out["snmp_status"] = "ERROR: SNMP sin respuesta o comunidad incorrecta"
    return out


def get_it_remedy(error_msg: str, asset_type: str, protocol: str) -> Tuple[str, str]:
    """
    Dado error_msg, asset_type y protocol (wmi/ssh/snmp/http), consulta remedies.json
    y devuelve (mensaje_para_el_tecnico, comando_a_copiar).
    """
    if not error_msg:
        return "", ""
    remedies = _load_remedies()
    proto = (protocol or "").lower()
    rules = []
    if proto and proto in remedies:
        rules.extend(remedies.get(proto, []))
    rules.extend(remedies.get("any", []))

    if not rules:
        return "", ""

    e = error_msg.upper()
    a = (asset_type or "").lower()

    for rule in rules:
        patterns = [str(p).upper() for p in rule.get("match_contains", []) if p]
        if patterns and not any(p in e for p in patterns):
            continue
        allowed_types = [str(t).lower() for t in rule.get("asset_types", []) if t]
        if allowed_types:
            if not any(t in a for t in allowed_types):
                continue
        msg = str(rule.get("message", "")).strip()
        cmd = str(rule.get("command", "")).strip()
        if msg:
            return msg, cmd

    return "", ""


_CHASSIS_TYPE_MAP = {
    1: "Virtual",
    3: "Desktop",
    4: "Desktop",
    7: "Server",
    9: "Laptop",
    10: "Laptop",
}
_RE_HOSTNAME = re.compile(r"^[A-Za-z0-9\-]{2,15}$")
_RE_SERIAL = re.compile(r"^[A-Za-z0-9\-\.]{5,30}$")


def _parse_wmi_powershell_strict(raw: str) -> Optional[Dict[str, str]]:
    """Parser solo JSON. Mapea a columnas BD: asset_model, ram, cpu, storage_cap, os_detected, etc."""
    if not raw or not raw.strip():
        return None
    idx = raw.find("{")
    if idx < 0:
        return None
    json_str = raw[idx:].strip()
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    hw = data.get("Hardware") or data.get("hardware") or {}
    os_obj = data.get("OS") or data.get("os") or {}
    bios = data.get("BIOS") or data.get("bios") or {}
    discos = data.get("Discos") or data.get("discos") or []
    software = data.get("Software") or data.get("software") or []
    if not isinstance(hw, dict):
        hw = {}
    if not isinstance(os_obj, dict):
        os_obj = {}
    if not isinstance(bios, dict):
        bios = {}
    if not isinstance(discos, list):
        discos = []
    if not isinstance(software, list):
        software = []

    asset_model = (hw.get("Model") or hw.get("model") or "").strip() or ""
    # No descartar todo el JSON cuando el modelo es "Microsoft Windows RPC" (WMI remoto); usar el resto de datos
    if asset_model and asset_model.lower() != "microsoft windows rpc":
        result: Dict[str, str] = {"asset_model": asset_model[:200]}
    else:
        result = {}

    total_mem = hw.get("TotalPhysicalMemory") or hw.get("totalphysicalmemory")
    if total_mem is not None:
        try:
            num_bytes = int(total_mem)
            gb = num_bytes / float(1024 ** 3)
            if gb >= 1:
                result["ram"] = "%d GB" % round(gb)
            else:
                result["ram"] = "%d MB" % int(num_bytes / (1024 ** 2))
        except (TypeError, ValueError):
            pass

    manufacturer = (hw.get("Manufacturer") or hw.get("manufacturer") or "").strip()
    model_hw = (hw.get("Model") or hw.get("model") or "").strip()
    cpu_obj = data.get("CPU") or data.get("cpu") or {}
    cpu_name = ""
    if isinstance(cpu_obj, dict):
        cpu_name = (cpu_obj.get("Name") or cpu_obj.get("name") or "").strip()
    if cpu_name:
        result["cpu"] = cpu_name[:200]
    elif manufacturer or model_hw:
        result["cpu"] = ("%s %s" % (manufacturer, model_hw)).strip()[:200]

    parts = []
    for d in discos[:20]:
        if not isinstance(d, dict):
            continue
        m = (d.get("Model") or d.get("model") or "").strip()
        sz = d.get("Size") or d.get("size")
        if sz is not None:
            try:
                gb = int(sz) / float(1024 ** 3)
                parts.append("%s %d GB" % (m, round(gb)) if m else "%d GB" % round(gb))
            except (TypeError, ValueError):
                if m:
                    parts.append(m)
        elif m:
            parts.append(m)
    if parts:
        result["storage_cap"] = "; ".join(parts)[:500]

    caption = (os_obj.get("Caption") or os_obj.get("caption") or "").strip()
    version = (os_obj.get("Version") or os_obj.get("version") or "").strip()
    arch = (os_obj.get("OSArchitecture") or os_obj.get("osarchitecture") or "").strip()
    if caption or version:
        result["os_detected"] = ("%s %s %s" % (caption, version, arch)).strip()[:400]

    sw_list = []
    for s in software[:200]:
        if isinstance(s, dict):
            sw_list.append({
                "DisplayName": s.get("DisplayName") or s.get("displayname") or "",
                "DisplayVersion": s.get("DisplayVersion") or s.get("displayversion") or "",
            })
    result["software_list"] = json.dumps(_filter_software(sw_list), ensure_ascii=False)

    serial = (bios.get("SerialNumber") or bios.get("serialnumber") or "").strip()
    if serial and _RE_SERIAL.match(serial):
        result["serial_number"] = serial.upper()[:150]
    name = (hw.get("Name") or hw.get("name") or "").strip()
    if name and _RE_HOSTNAME.match(name):
        result["hostname"] = name[:100]

    if not result.get("asset_model") and (caption or version):
        result["asset_model"] = ("%s %s" % (caption, version)).strip()[:200]

    logged = (data.get("LoggedUser") or data.get("logged_user") or hw.get("UserName") or "").strip()
    if logged:
        result["logged_user"] = logged[:120]
        result["logged_user_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    monitors = data.get("Monitors") or data.get("monitors") or []
    if isinstance(monitors, list) and monitors:
        result["monitors_detected_json"] = json.dumps(monitors[:6], ensure_ascii=False)

    printers = data.get("Printers") or data.get("printers") or []
    if isinstance(printers, list) and printers:
        result["local_printers_json"] = json.dumps(printers[:20], ensure_ascii=False)

    usb = data.get("UsbDevices") or data.get("usb_devices") or []
    if isinstance(usb, list) and usb:
        result["peripherals_detected_json"] = json.dumps(usb[:40], ensure_ascii=False)

    return result


_DOCK_USB_KEYWORDS = (
    "dock", "docking", "hub", "displaylink", "thunderbolt", "usb-c",
    "lenovo", "dell wd", "hp usb", "kensington", "plugable", "caldigit",
    "thinkpad", "elitebook", "usb hub", "composite device",
)


def _decode_wmi_char_array(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip().strip("\x00")
    if isinstance(val, (bytes, bytearray)):
        try:
            return val.decode("utf-16-le", errors="ignore").strip("\x00").strip()
        except Exception:
            return ""
    if isinstance(val, list):
        chars: List[str] = []
        for item in val:
            try:
                n = int(item)
                if n == 0:
                    break
                if 32 <= n < 127:
                    chars.append(chr(n))
            except (TypeError, ValueError):
                continue
        return "".join(chars).strip()
    return str(val).strip()


def _is_interesting_usb(name: str, pnp_class: str, device_id: str) -> bool:
    blob = " ".join((name, pnp_class, device_id)).lower()
    if "usb" not in blob and "hub" not in blob and "dock" not in blob:
        return False
    return any(k in blob for k in _DOCK_USB_KEYWORDS) or "hub" in blob or "dock" in blob


_REMOTE_SW_FILE = r"C:\Windows\Temp\sho_sw.json"
_REMOTE_SW_SMB = "Windows\\Temp\\sho_sw.json"
_REMOTE_PATCH_FILE = r"C:\Windows\Temp\sho_patch.json"
_REMOTE_PATCH_SMB = "Windows\\Temp\\sho_patch.json"

_PS_SOFTWARE = (
    "$paths=@('HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
    "'HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*');"
    "$sw=@();foreach($p in $paths){Get-ItemProperty $p -EA SilentlyContinue|?{$_.DisplayName}|"
    "ForEach-Object{$sw+=@{DisplayName=[string]$_.DisplayName;"
    "DisplayVersion=[string]$_.DisplayVersion}}};"
    f"$sw|ConvertTo-Json -Compress|Out-File -FilePath '{_REMOTE_SW_FILE}' -Encoding utf8"
)

_PS_PENDING_PATCHES = (
    "$ErrorActionPreference='SilentlyContinue';$n=0;$t=@();"
    "try{$s=New-Object -ComObject Microsoft.Update.Session;"
    "$r=$s.CreateUpdateSearcher().Search(\"IsInstalled=0 and Type='Software'\");"
    "$n=$r.Updates.Count;"
    "for($i=0;$i -lt [Math]::Min(12,$n);$i++){$t+=[string]$r.Updates.Item($i).Title}}catch{};"
    f"@{{count=$n;titles=$t}}|ConvertTo-Json -Compress|Out-File -FilePath '{_REMOTE_PATCH_FILE}' -Encoding utf8"
)


def _wmi_start_powershell(iWbemServices, ps_script: str) -> bool:
    """Lanza PowerShell remoto via Win32_Process.Create (EncodedCommand)."""
    try:
        encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
        cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand " + encoded
        win32_process, _ = iWbemServices.GetObject("Win32_Process")
        win32_process.Create(cmd, "C:\\Windows\\Temp", None)
        return True
    except Exception as e:
        _log().debug("WMI Win32_Process.Create failed: %s", e)
        return False


def _smb_read_remote_file(
    ip: str, user: str, password: str, domain: str, rel_path: str
) -> Optional[str]:
    """Lee un archivo del admin share C$ vía SMB."""
    try:
        from impacket.smbconnection import SMBConnection

        smb = SMBConnection(ip, ip, sess_port=445)
        smb.login(user, password, domain or "")
        buf = BytesIO()
        smb.getFile("C$", rel_path.replace("/", "\\"), buf.write)
        try:
            smb.deleteFile("C$", rel_path.replace("/", "\\"))
        except Exception:
            pass
        smb.close()
        raw = buf.getvalue()
        if raw.startswith(b"\xff\xfe"):
            return raw.decode("utf-16-le", errors="replace").strip()
        return raw.decode("utf-8-sig", errors="replace").strip()
    except Exception as e:
        _log().debug("SMB read %s@%s failed: %s", rel_path, ip, e)
        return None


def wmi_powershell_json(
    ip: str,
    user: str,
    password: str,
    domain: str,
    ps_script: str,
    remote_smb_path: str,
    wait_sec: float = 15.0,
) -> Optional[Any]:
    """
    Ejecuta PowerShell remoto, lee JSON desde C$ y lo parsea.
    Usado por Tracker (software) y Auditoría de red (parches pendientes).
    """
    try:
        from impacket.dcerpc.v5.dcom.wmi import (
            CLSID_WbemLevel1Login,
            IID_IWbemLevel1Login,
            IWbemLevel1Login,
        )
        from impacket.dcerpc.v5.dtypes import NULL
        from impacket.dcerpc.v5.dcomrt import DCOMConnection
        import logging as _logging

        _logging.getLogger("impacket").setLevel(_logging.CRITICAL)
        dcom = DCOMConnection(
            ip, username=user, password=password, domain=domain or ".",
            lmhash="", nthash="", aesKey=None, oxidResolver=True, doKerberos=False,
        )
        try:
            iface = dcom.CoCreateInstanceEx(CLSID_WbemLevel1Login, IID_IWbemLevel1Login)
            login = IWbemLevel1Login(iface)
            svc = login.NTLMLogin("//./root/cimv2", NULL, NULL)
            if not _wmi_start_powershell(svc, ps_script):
                return None
            time.sleep(max(8.0, wait_sec))
            raw = _smb_read_remote_file(ip, user, password, domain, remote_smb_path)
            if not raw:
                return None
            return json.loads(raw)
        finally:
            try:
                dcom.disconnect()
            except Exception:
                pass
    except Exception as e:
        _log().debug("wmi_powershell_json %s: %s", ip, e)
        return None


def _parse_software_json_payload(data: Any) -> List[Dict[str, str]]:
    software: List[Dict[str, str]] = []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return software
    for item in data:
        if not isinstance(item, dict):
            continue
        dn = str(item.get("DisplayName") or item.get("displayName") or "").strip()
        if not dn:
            continue
        dv = str(item.get("DisplayVersion") or item.get("displayVersion") or "").strip()
        software.append({"DisplayName": dn, "DisplayVersion": dv})
    return software


_PS_CONSOLIDATED_SCRIPT = (
    "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \""
    "$cs = Get-CimInstance Win32_ComputerSystem; "
    "$os = Get-CimInstance Win32_OperatingSystem | Select-Object -First 1; "
    "$bios = Get-CimInstance Win32_BIOS; "
    "$discos = Get-CimInstance Win32_DiskDrive | Select-Object Model, Size; "
    "$sw = Get-ItemProperty 'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*' -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName } | Select-Object DisplayName, DisplayVersion; "
    "$result = @{ Hardware=@{ Model=$cs.Model; Manufacturer=$cs.Manufacturer; TotalPhysicalMemory=$cs.TotalPhysicalMemory; Name=$cs.Name }; "
    "OS=@{ Caption=$os.Caption; Version=$os.Version; OSArchitecture=$os.OSArchitecture }; "
    "BIOS=@{ SerialNumber=$bios.SerialNumber }; "
    "Discos=@($discos | ForEach-Object { @{ Model=$_.Model; Size=$_.Size } }); "
    "Software=@($sw | ForEach-Object { @{ DisplayName=$_.DisplayName; DisplayVersion=$_.DisplayVersion } }) }; "
    "$result | ConvertTo-Json -Compress -Depth 5\""
)


def _extract_consolidated_wmi_json(stdout: str) -> Optional[Dict[str, Any]]:
    """Busca JSON en stdout (descartando banners Impacket), parsea y devuelve dict o None."""
    if not stdout or not stdout.strip():
        return None
    idx = stdout.find("{")
    if idx < 0:
        return None
    json_str = stdout[idx:].strip()
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def _apply_consolidated_validations(data: Dict[str, Any]) -> Dict[str, Any]:
    """Aplica filtros: Hostname, SerialNumber, Chassis → asset_type, Software."""
    result: Dict[str, Any] = {}
    hostname = (data.get("Hostname") or data.get("hostname") or "").strip()
    result["hostname"] = hostname if _RE_HOSTNAME.match(hostname) else "DESCONOCIDO"

    serial_raw = (data.get("SerialNumber") or data.get("serialnumber") or "").strip()
    if not serial_raw or not _RE_SERIAL.match(serial_raw):
        result["serial_number"] = "ERROR_SERIAL"
    else:
        result["serial_number"] = serial_raw.upper()[:150]

    chassis = data.get("Chassis") or data.get("chassis")
    if chassis is not None:
        try:
            c = int(chassis)
            result["asset_type"] = _CHASSIS_TYPE_MAP.get(c, "Otro")
        except (TypeError, ValueError):
            result["asset_type"] = "Otro"
    else:
        result["asset_type"] = "Otro"

    software = data.get("Software") or data.get("software") or []
    if not isinstance(software, list):
        software = [software] if software else []
    software_list_of_dicts = []
    for item in software:
        if isinstance(item, dict):
            software_list_of_dicts.append(item)
        else:
            software_list_of_dicts.append({"DisplayName": str(item), "DisplayVersion": ""})
    result["software_list"] = software_list_of_dicts
    return result


def phase3_wmi(ip: str, user: str, password: str, domain: str, timeout_sec: Optional[float] = None) -> Dict[str, str]:
    """
    WMI directo via DCOM (impacket). No usa wmiexec.py ni archivo temporal ADMIN$.
    El proceso WMI-spawned no tiene credenciales de red para escribir en \\127.0.0.1\ADMIN$
    (mecanismo de wmiexec), por eso usamos consultas DCOM directas que retornan datos via RPC.
    """
    out: Dict[str, str] = {}
    user = (user or "").strip()
    password = (password or "").strip()
    domain = (domain or "").strip()

    if not _port_open(ip, 135) and not _port_open(ip, 445):
        return out
    if not (user or "").replace(".\\", "").strip() or not password:
        return out

    if timeout_sec is not None:
        t = max(45, min(int(float(timeout_sec)), EXTRACTOR_SSH_WMI_TIMEOUT))
    else:
        t = EXTRACTOR_SSH_WMI_TIMEOUT

    try:
        import concurrent.futures as _cf
        def _do_wmi_dcom():
            from impacket.dcerpc.v5.dcom.wmi import (
                CLSID_WbemLevel1Login, IID_IWbemLevel1Login,
                IWbemLevel1Login, IEnumWbemClassObject,
            )
            from impacket.dcerpc.v5.dtypes import NULL
            from impacket.dcerpc.v5.dcomrt import DCOMConnection
            import logging as _logging
            _logging.getLogger("impacket").setLevel(_logging.CRITICAL)

            dcom = DCOMConnection(
                ip, username=user, password=password, domain=domain,
                lmhash="", nthash="", aesKey=None,
                oxidResolver=True, doKerberos=False,
            )
            try:
                iInterface = dcom.CoCreateInstanceEx(CLSID_WbemLevel1Login, IID_IWbemLevel1Login)
                iWbemLevel1Login = IWbemLevel1Login(iInterface)
                iWbemServices = iWbemLevel1Login.NTLMLogin("//./root/cimv2", NULL, NULL)

                def _query_svc(svc, wql):
                    iface = svc.ExecQuery(wql)
                    enum = IEnumWbemClassObject(iface)
                    rows = []
                    while True:
                        try:
                            objs = enum.Next(0xFFFF, 1)
                            if not objs:
                                break
                            rows.append(objs[0])
                        except Exception:
                            break
                    return rows

                def _query(wql):
                    return _query_svc(iWbemServices, wql)

                def _val_raw(obj, name):
                    try:
                        p = obj.getProperties().get(name)
                        if p is None:
                            return None
                        return p.get("value") if isinstance(p, dict) else getattr(p, "value", None)
                    except Exception:
                        return None

                def _val(obj, name):
                    v = _val_raw(obj, name)
                    return None if v is None else str(v).strip()

                hw = {}
                logged_user = ""
                cs = _query(
                    "SELECT Name, Model, Manufacturer, TotalPhysicalMemory, UserName "
                    "FROM Win32_ComputerSystem"
                )
                if cs:
                    o = cs[0]
                    hw["Name"] = _val(o, "Name")
                    hw["Model"] = _val(o, "Model")
                    hw["Manufacturer"] = _val(o, "Manufacturer")
                    hw["TotalPhysicalMemory"] = _val(o, "TotalPhysicalMemory")
                    logged_user = (_val(o, "UserName") or "").strip()

                os_d = {}
                oss = _query("SELECT Caption, Version, OSArchitecture FROM Win32_OperatingSystem")
                if oss:
                    o = oss[0]
                    os_d["Caption"] = _val(o, "Caption")
                    os_d["Version"] = _val(o, "Version")
                    os_d["OSArchitecture"] = _val(o, "OSArchitecture")

                bios_d = {}
                bioss = _query("SELECT SerialNumber FROM Win32_BIOS")
                if bioss:
                    bios_d["SerialNumber"] = _val(bioss[0], "SerialNumber")

                discos = []
                for d in _query("SELECT Model, Size FROM Win32_DiskDrive")[:8]:
                    discos.append({"Model": _val(d, "Model"), "Size": _val(d, "Size")})

                cpus = _query("SELECT Name FROM Win32_Processor")
                cpu_d = {"Name": _val(cpus[0], "Name")} if cpus else {}

                software: List[Dict[str, str]] = []
                ps_sw_started = _wmi_start_powershell(iWbemServices, _PS_SOFTWARE)

                monitors: List[Dict[str, str]] = []
                try:
                    iWbemWmi = iWbemLevel1Login.NTLMLogin("//./root/wmi", NULL, NULL)
                    for mobj in _query_svc(iWbemWmi, "SELECT * FROM WmiMonitorID")[:6]:
                        mfg = _decode_wmi_char_array(_val_raw(mobj, "ManufacturerName"))
                        prod = _decode_wmi_char_array(_val_raw(mobj, "UserFriendlyName")) or _decode_wmi_char_array(
                            _val_raw(mobj, "ProductCodeID")
                        )
                        serial = _decode_wmi_char_array(_val_raw(mobj, "SerialNumberID"))
                        if mfg or prod or serial:
                            monitors.append({
                                "manufacturer": mfg[:80],
                                "model": prod[:120],
                                "serial": serial[:80],
                            })
                except Exception:
                    pass
                if not monitors:
                    for dm in _query("SELECT Name, MonitorManufacturer, MonitorType FROM Win32_DesktopMonitor")[:6]:
                        name = _val(dm, "Name") or ""
                        mfg = _val(dm, "MonitorManufacturer") or ""
                        if name or mfg:
                            monitors.append({
                                "manufacturer": (mfg or "")[:80],
                                "model": (name or "")[:120],
                                "serial": "",
                            })

                _virtual_printer_names = (
                    "microsoft print to pdf", "xps document", "onenote", "fax",
                    "send to", "redirected", "pdf", "snagit",
                )
                printers: List[Dict[str, str]] = []
                for pr in _query(
                    "SELECT Name, PortName, Local, Default, DriverName FROM Win32_Printer"
                )[:40]:
                    name = _val(pr, "Name") or ""
                    port = (_val(pr, "PortName") or "").strip()
                    port_u = port.upper()
                    name_l = name.lower()
                    local_raw = (_val(pr, "Local") or "").strip().lower()
                    if not name:
                        continue
                    if any(v in name_l for v in _virtual_printer_names):
                        continue
                    if port_u in ("NUL:", "PORTPROMPT:", "PORTPROMPT") or port_u.startswith("PORTPROMPT"):
                        continue
                    if port_u.startswith(("IP_", "WSD", "HTTP", "TCP", "LPR", "IPP")) or "." in port:
                        continue
                    is_usb = port_u.startswith("USB") or "USB" in port_u
                    is_local = local_raw in ("true", "1") or port_u.startswith(
                        ("USB", "LPT", "COM", "FILE", "DOT4")
                    )
                    if not is_usb and not is_local:
                        continue
                    printers.append({
                        "name": name[:120],
                        "port": port[:60],
                        "driver": (_val(pr, "DriverName") or "")[:80],
                        "default": (_val(pr, "Default") or "").strip().lower() in ("true", "1"),
                    })

                usb_devices: List[Dict[str, str]] = []
                for dev in _query(
                    "SELECT Name, DeviceID, Manufacturer, PNPClass FROM Win32_PnPEntity"
                )[:200]:
                    name = _val(dev, "Name") or ""
                    device_id = _val(dev, "DeviceID") or ""
                    pnp_class = _val(dev, "PNPClass") or ""
                    if not _is_interesting_usb(name, pnp_class, device_id):
                        continue
                    usb_devices.append({
                        "name": name[:140],
                        "manufacturer": (_val(dev, "Manufacturer") or "")[:80],
                        "class": pnp_class[:40],
                        "device_id": device_id[:120],
                    })
                    if len(usb_devices) >= 25:
                        break

                if ps_sw_started:
                    time.sleep(10)
                    sw_raw = _smb_read_remote_file(ip, user, password, domain, _REMOTE_SW_SMB)
                    if sw_raw:
                        try:
                            software = _parse_software_json_payload(json.loads(sw_raw))
                        except json.JSONDecodeError:
                            pass

                try:
                    iWbemLevel1Login.RemRelease()
                except Exception:
                    pass

                return {
                    "Hardware": hw,
                    "CPU": cpu_d,
                    "OS": os_d,
                    "BIOS": bios_d,
                    "Discos": discos,
                    "Software": software,
                    "LoggedUser": logged_user,
                    "Monitors": monitors,
                    "Printers": printers,
                    "UsbDevices": usb_devices,
                }
            finally:
                try:
                    dcom.disconnect()
                except Exception:
                    pass

        with _cf.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_do_wmi_dcom)
            try:
                data = fut.result(timeout=t)
            except _cf.TimeoutError:
                _log().warning("[WARNING] Host %s timeout in Extractor (WMI DCOM)", ip)
                out["wmi_status"] = "ERROR: timeout (%ds)" % t
                return out

        parsed = _parse_wmi_powershell_strict(json.dumps(data))
        if parsed:
            for k, v in parsed.items():
                if v is not None and v != "":
                    out[k] = v
            out["wmi_status"] = "OK"
        else:
            out["wmi_status"] = "SIN RESPUESTA"

    except Exception as e:
        err = str(e)
        _log().warning("[WARNING] Host %s WMI DCOM error: %s", ip, err)
        out["wmi_status"] = ("ERROR: " + err)[:200]

    return out



_SW_EXCLUDE_KEYWORDS = (
    # Python components
    "python 3", "python 2", "tcl/tk", "pip bootstrap", "test suite",
    "core interpreter", "executables (64", "add to path", "freethreaded",
    "utility scripts", "documentation (64",
    # Visual Studio components
    "vs_", "vsix", "icecap", "diagnosticshub", "intellitrace",
    "vs script", "minshell", "devenv", "graphics_singleton",
    "application verifier", "universal crt", "windows app certification",
    # Parches y updates Windows
    "kb", "hotfix", "cumulative update", "security update",
    "visual c++", "vcredist", "redistributable",
    ".net framework", "directx", "windows sdk",
    # Drivers y sistema
    "driver", "chipset", "intel(r)", "amd ",
    # Librerías sistema Linux
    "lib", "python3-", "perl-", "ruby-", "fonts-",
    "linux-image", "linux-headers", "linux-modules",
    "gcc-", "g++-", "binutils", "libc-", "libx",
    "grub", "initramfs", "udev", "dbus",
    # Apps sistema Mac irrelevantes
    "automator", "chess", "dvd player", "dashboard",
    "launchpad", "mission control", "siri", "stickies",
    "font book", "image capture", "time machine",
    "classlink", "calculator", "calendar", "contacts",
    "dictionary", "facetime", "mail", "maps", "messages",
    "notes", "photo booth", "photos", "preview", "reminders",
    "safari", "system preferences", "textedit", "utilities",
    "ibooks", "itunes", "app store", "macos", "finder",
    "airdrop", "handoff", "continuity",
)

_SW_INCLUDE_KEYWORDS = (
    # Ofimática
    "office", "word", "excel", "powerpoint", "libreoffice",
    "openoffice", "outlook", "teams", "zoom", "slack",
    # Browsers
    "chrome", "firefox", "edge", "safari", "opera",
    # Seguridad
    "antivirus", "kaspersky", "norton", "avast", "eset",
    "malwarebytes", "defender", "symantec", "mcafee",
    "cleanmymac", "ccleaner",
    # Acceso remoto
    "anydesk", "teamviewer", "vnc", "putty", "rdp",
    # Compresión y utilidades
    "winrar", "7-zip", "winzip",
    # Multimedia
    "vlc", "acrobat", "adobe", "quicktime",
    # Desarrollo relevante
    "docker", "git", "virtualbox", "sql server",
    "visual studio", "vscode",
    # Sistemas contables
    "quickbooks", "sage", "contpaq", "aspel", "sap",
    # Comunicación
    "skype", "whatsapp", "telegram",
    # Windows Subsystem
    "windows subsystem",
)

def _filter_software(sw_list: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Filtra software para inventario de activos fijos.
    Prioriza software relevante para el negocio, descarta componentes de sistema.
    """
    if not sw_list:
        return []

    filtered = []
    for item in sw_list:
        name = (item.get("DisplayName") or "").lower().strip()
        if not name:
            continue

        # Siempre incluir software relevante
        if any(kw in name for kw in _SW_INCLUDE_KEYWORDS):
            filtered.append(item)
            continue

        # Descartar componentes de sistema/parches/librerías
        if any(name.startswith(kw) or kw in name for kw in _SW_EXCLUDE_KEYWORDS):
            continue

        # Para listas cortas incluir todo lo que quede
        filtered.append(item)

    return filtered[:50]


def _get_software_list_ssh(run_ssh_cmd, uname: str) -> List[Dict[str, str]]:
    """
    Obtiene lista de software vía SSH para Linux. Mismo formato que WMI: [{"DisplayName", "DisplayVersion"}].
    Orden: OpenWrt (opkg) -> Debian/Ubuntu (dpkg) -> RHEL/Fedora (rpm). Máximo 200 entradas.
    """
    sw_list: List[Dict[str, str]] = []
    uname_lower = (uname or "").lower()
    # Detección OpenWrt: uname contiene "openwrt" o existe opkg / etc/openwrt_release
    is_openwrt = (
        "openwrt" in uname_lower
        or bool((run_ssh_cmd("which opkg 2>/dev/null") or "").strip())
        or bool((run_ssh_cmd("test -f /etc/openwrt_release && echo 1") or "").strip())
    )
    if is_openwrt:
        raw = run_ssh_cmd("opkg list-installed 2>/dev/null") or ""
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            # Formato OpenWrt: "packagename - version" (separador " - ")
            if " - " in line:
                name, _, ver = line.partition(" - ")
                name, ver = name.strip()[:200], ver.strip()[:100]
            else:
                parts = line.split(None, 1)
                name = (parts[0] or "").strip()[:200]
                ver = (parts[1] or "").strip()[:100] if len(parts) > 1 else ""
            if name:
                sw_list.append({"DisplayName": name, "DisplayVersion": ver})
            if len(sw_list) >= 200:
                break
        return _filter_software(sw_list)
    is_darwin = "darwin" in uname_lower
    if is_darwin:
        raw = run_ssh_cmd("ls -1 /Applications 2>/dev/null; ls -1 /System/Applications 2>/dev/null") or ""
        for line in raw.splitlines():
            name = line.strip().replace(".app", "").strip()[:200]
            if name:
                sw_list.append({"DisplayName": name, "DisplayVersion": ""})
            if len(sw_list) >= 200:
                break
        return _filter_software(sw_list)
    # Debian/Ubuntu: dpkg -l (líneas ii  package  version ...)
    raw = run_ssh_cmd("dpkg -l 2>/dev/null | awk '/^ii/ {print $2 \"\t\" $3}'") or ""
    if raw.strip():
        for line in raw.splitlines():
            parts = line.split("\t", 1)
            name = (parts[0] or "").strip()[:200]
            ver = (parts[1] or "").strip()[:100] if len(parts) > 1 else ""
            if name:
                sw_list.append({"DisplayName": name, "DisplayVersion": ver})
            if len(sw_list) >= 200:
                break
        return _filter_software(sw_list)
    # RHEL/Fedora: rpm -qa
    raw = run_ssh_cmd("rpm -qa --qf '%{NAME}\t%{VERSION}-%{RELEASE}\n' 2>/dev/null") or ""
    if raw.strip():
        for line in raw.splitlines():
            parts = line.split("\t", 1)
            name = (parts[0] or "").strip()[:200]
            ver = (parts[1] or "").strip()[:100] if len(parts) > 1 else ""
            if name:
                sw_list.append({"DisplayName": name, "DisplayVersion": ver})
            if len(sw_list) >= 200:
                break
    return _filter_software(sw_list)


def _collect_ssh_session_extras(
    out: Dict[str, str],
    run_ssh,
    uname: str,
    is_darwin: bool,
) -> None:
    """Usuario logueado, monitores, USB/docks e impresoras locales vía SSH (si el SO lo permite)."""
    uname_l = (uname or "").lower()
    if any(x in uname_l for x in ("openwrt", "lede", "mips", "armv6l", "armv7l", "ubnt")):
        return

    who_out = run_ssh("who 2>/dev/null | head -5") or run_ssh("w -h 2>/dev/null | head -5")
    for line in (who_out or "").splitlines():
        parts = line.split()
        if parts and parts[0] not in ("(", "reboot"):
            user = parts[0].strip()
            if user and user != "system":
                out["logged_user"] = user[:120]
                out["logged_user_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                break

    monitors: List[Dict[str, str]] = []
    usb_devices: List[Dict[str, str]] = []
    printers: List[Dict[str, str]] = []

    if is_darwin:
        disp = run_ssh("system_profiler SPDisplaysDataType 2>/dev/null", cmd_timeout=20) or ""
        cur_name = ""
        for line in disp.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.endswith(":") and "display" in line.lower():
                cur_name = line.rstrip(":").strip()
            elif "resolution" in line.lower() and ":" in line:
                res = line.split(":", 1)[1].strip()
                if cur_name or res:
                    monitors.append({"manufacturer": "", "model": (cur_name or "Display")[:120], "serial": res[:80]})
        usb_raw = run_ssh("system_profiler SPUSBDataType 2>/dev/null", cmd_timeout=20) or ""
        for line in usb_raw.splitlines():
            s = line.strip()
            if not s.endswith(":") or s.count(":") != 1:
                continue
            name = s.rstrip(":").strip()
            if _is_interesting_usb(name, "USB", name):
                usb_devices.append({"name": name[:140], "manufacturer": "", "class": "USB", "device_id": ""})
        lp = run_ssh("lpstat -p 2>/dev/null") or ""
        for line in lp.splitlines():
            if line.startswith("printer "):
                pname = line.split()[1] if len(line.split()) > 1 else ""
                if pname:
                    printers.append({"name": pname[:120], "port": "local", "driver": "", "default": False})
    else:
        for line in (run_ssh("xrandr --query 2>/dev/null | grep ' connected'") or "").splitlines():
            name = line.split()[0] if line.split() else ""
            if name:
                monitors.append({"manufacturer": "", "model": name[:120], "serial": ""})
        for line in (run_ssh("lsusb 2>/dev/null") or "").splitlines():
            if not line.strip():
                continue
            if _is_interesting_usb(line, "USB", line):
                usb_devices.append({
                    "name": line.strip()[:140],
                    "manufacturer": "",
                    "class": "USB",
                    "device_id": line.strip()[:120],
                })
        for line in (run_ssh("lpstat -p 2>/dev/null") or "").splitlines():
            if line.startswith("printer "):
                pname = line.split()[1] if len(line.split()) > 1 else ""
                if pname:
                    printers.append({"name": pname[:120], "port": "local", "driver": "", "default": False})

    if monitors:
        out["monitors_detected_json"] = json.dumps(monitors[:6], ensure_ascii=False)
    if usb_devices:
        out["peripherals_detected_json"] = json.dumps(usb_devices[:25], ensure_ascii=False)
    if printers:
        out["local_printers_json"] = json.dumps(printers[:20], ensure_ascii=False)


def phase4_ssh(ip: str, user: str, password: str, timeout_sec: Optional[float] = None) -> Dict[str, str]:
    """
    SSH (paramiko). Timeout global 12s. Si el host no responde, se loguea [WARNING] y se retorna out.
    """
    out: Dict[str, str] = {}
    if not PARAMIKO_AVAILABLE or not _port_open(ip, 22):
        return out
    t = min(float(timeout_sec), EXTRACTOR_SSH_WMI_TIMEOUT) if timeout_sec is not None else EXTRACTOR_SSH_WMI_TIMEOUT
    t = max(1, min(int(t), EXTRACTOR_SSH_WMI_TIMEOUT))

    def run_ssh(client: paramiko.SSHClient, cmd: str, cmd_timeout: Optional[int] = None) -> str:
        try:
            to = cmd_timeout if cmd_timeout is not None else t
            stdin, stdout, stderr = client.exec_command(cmd, timeout=to)
            return (stdout.read() or b"").decode("utf-8", errors="ignore").strip()
        except Exception:
            return ""

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.WarningPolicy())
        client.connect(
            ip,
            username=user or "root",
            password=password or "",
            timeout=t,
            banner_timeout=min(t, 10),
            look_for_keys=False,
            allow_agent=False,
        )
    except Exception as e:
        if _IncompatiblePeer and isinstance(e, _IncompatiblePeer):
            out["ssh_status"] = (
                "ERROR: SSH no negociable (KEX o clave de host heredada no soportada, "
                "p. ej. solo DSA) — el inventario no conecta por SSH a este aparato."
            )[:200]
            return out
        err_str = str(e).lower()
        if "incompatible" in err_str and "host key" in err_str:
            out["ssh_status"] = (
                "ERROR: clave u algoritmos SSH del host no soportados por el conector. "
            )[:200]
            return out
        if "timeout" in err_str or "timed out" in err_str:
            _log().warning("[WARNING] Host %s timeout in Extractor (SSH connect)", ip)
            out["ssh_status"] = "TIMEOUT"
        elif "authentication" in err_str or "auth failed" in err_str or "permission denied" in err_str:
            out["ssh_status"] = "SSH_AUTH_FAILED"
        else:
            out["ssh_status"] = ("ERROR: " + str(e))[:200]
        return out

    try:
        uname = run_ssh(client, "uname -a")
        if uname:
            out["os_detected"] = uname[:400]
        is_darwin = "darwin" in (uname or "").lower()
        if is_darwin:
            hn = run_ssh(client, "hostname 2>/dev/null")
            if hn and not out.get("hostname"):
                out["hostname"] = hn[:100]
            sp = run_ssh(client, "system_profiler SPHardwareDataType 2>/dev/null", cmd_timeout=min(25, int(t) + 10))
            if sp:
                for line in sp.splitlines():
                    line = line.strip()
                    if ":" not in line:
                        continue
                    key, _, val = line.partition(":")
                    key, val = key.strip().lower(), val.strip()[:200]
                    if "model name" in key:
                        out["asset_model"] = val
                        if not out.get("cpu"):
                            out["cpu"] = val
                    elif "chip" in key or "processor name" in key:
                        out["cpu"] = val
                    elif "memory" in key and "gb" in val.lower():
                        out["ram"] = (val.split()[0] + " GB") if val.split() else val
                    elif "memory" in key and val.replace(" ", "").replace("gb", "").isdigit():
                        out["ram"] = val + " GB" if not val.lower().endswith("gb") else val
                    elif "serial number" in key:
                        out["serial_number"] = val
                if not out.get("ram"):
                    mem_bytes = run_ssh(client, "sysctl -n hw.memsize 2>/dev/null")
                    if mem_bytes and mem_bytes.isdigit():
                        gb = int(mem_bytes) // (1024**3)
                        out["ram"] = "%d GB" % gb if gb > 0 else ""
                if not out.get("serial_number"):
                    ioreg_out = run_ssh(client, "ioreg -c IOPlatformExpertDevice -d 2 2>/dev/null | grep IOPlatformSerialNumber")
                    if ioreg_out:
                        m = re.search(r'"([^"]+)"', ioreg_out)
                        if m:
                            out["serial_number"] = m.group(1)[:150]
                if not out.get("cpu"):
                    out["cpu"] = (run_ssh(client, "sysctl -n hw.model 2>/dev/null") or "Apple")[:200]
            out["os_family"] = "macOS"
            pv = run_ssh(client, "sw_vers -productVersion 2>/dev/null")
            if pv:
                out["os_version"] = pv[:80]
            df_out = run_ssh(client, "df -h / 2>/dev/null | tail -1")
            if df_out:
                parts = df_out.split()
                if len(parts) >= 2:
                    out["storage_cap"] = parts[1][:30]
            try:
                sw_list = _get_software_list_ssh(lambda cmd: run_ssh(client, cmd), uname or "")
                if sw_list:
                    out["software_list"] = json.dumps(sw_list, ensure_ascii=False)
            except Exception:
                pass
            try:
                _collect_ssh_session_extras(
                    out,
                    lambda cmd, cmd_timeout=None: run_ssh(client, cmd, cmd_timeout=cmd_timeout),
                    uname or "",
                    True,
                )
            except Exception:
                pass
        else:
            cpu_line = run_ssh(
                client,
                "grep -m1 'model name' /proc/cpuinfo 2>/dev/null || grep -m1 Model /proc/cpuinfo 2>/dev/null",
            )
            if cpu_line:
                out["cpu"] = (
                    cpu_line.replace("model name", "")
                    .replace("Model", "")
                    .replace(":", "")
                    .strip()[:200]
                )
            mem_line = run_ssh(client, "grep MemTotal /proc/meminfo 2>/dev/null")
            if mem_line:
                m = re.search(r"(\d+)\s*kB", mem_line)
                if m:
                    gb = int(m.group(1)) // (1024 * 1024)
                    out["ram"] = "%d GB" % gb if gb > 0 else "%d MB" % (int(m.group(1)) // 1024)
            hn = run_ssh(client, "hostname 2>/dev/null")
            if hn and not out.get("hostname"):
                out["hostname"] = hn[:100]
            for dmi_cmd, key in [
                ("dmidecode -s system-manufacturer 2>/dev/null", "vendor"),
                ("dmidecode -s system-product-name 2>/dev/null", "asset_model"),
                ("dmidecode -s system-serial-number 2>/dev/null", "serial_number"),
            ]:
                val = run_ssh(client, dmi_cmd)
                if val and not val.startswith("/dev"):
                    out[key] = val[:150]
            osr = run_ssh(
                client,
                "cat /etc/os-release 2>/dev/null | grep -E '^(NAME|VERSION)=' | head -2",
            )
            if osr:
                for line in osr.splitlines():
                    if "NAME=" in line:
                        out["os_family"] = line.split("=", 1)[1].strip(' "')[:80]
                    elif "VERSION=" in line:
                        out["os_version"] = line.split("=", 1)[1].strip(' "')[:80]
            df_out = run_ssh(
                client,
                "df -h / 2>/dev/null | tail -1 | awk '{print $2}'",
            )
            if df_out and df_out[0].isdigit():
                out["storage_cap"] = df_out[:30]
    
            # Lista de software (Linux: dpkg/rpm; OpenWrt: opkg). Fallback sin tocar extracción de hardware.
            try:
                sw_list = _get_software_list_ssh(lambda cmd: run_ssh(client, cmd), uname or "")
                if sw_list:
                    out["software_list"] = json.dumps(sw_list, ensure_ascii=False)
            except Exception:
                pass
            try:
                _collect_ssh_session_extras(
                    out,
                    lambda cmd, cmd_timeout=None: run_ssh(client, cmd, cmd_timeout=cmd_timeout),
                    uname or "",
                    False,
                )
            except Exception:
                pass
    except Exception as e:
        if "timeout" in str(e).lower() or "timed out" in str(e).lower():
            _log().warning("[WARNING] Host %s timeout in Extractor (SSH exec)", ip)
        out["ssh_status"] = ("ERROR: " + str(e))[:200]
    finally:
        try:
            client.close()
        except Exception:
            pass

    if out and "ssh_status" not in out:
        out["ssh_status"] = "OK"
    return out


def consolidate_identity(data_dict: Dict[str, Any], nmap_os: Optional[str] = None) -> None:
    """
    Jerarquiza identidad según evidencia de protocolos (motor heurístico).
    Prioridad: 1) Nmap OS  2) WMI/SSH  3) SNMP sysDescr  4) HTTP Banner / MAC Vendor.
    Rellena os_name y vendor en data_dict; no devuelve nada (mutación in-place).
    """
    os_candidates = [
        (nmap_os or "").strip(),
        (data_dict.get("os_detected") or "").strip(),
        (data_dict.get("os_name") or "").strip(),
        (data_dict.get("snmp_sysdescr") or "").strip(),
        (data_dict.get("server") or "").strip(),
        (data_dict.get("title") or "").strip(),
    ]
    for val in os_candidates:
        if val:
            data_dict["os_name"] = val[:400]
            break
    else:
        data_dict["os_name"] = data_dict.get("os_name") or ""

    vendor = (data_dict.get("vendor") or "").strip()
    if not vendor:
        vendor = _vendor_from_mac(data_dict.get("mac") or "").strip()
    if vendor:
        data_dict["vendor"] = vendor[:200]


def merge_asset(base: Dict[str, Any], *updates: Dict[str, str]) -> Dict[str, Any]:
    """Fusiona dicts: solo claves con valor no vacío sobrescriben base."""
    _skip_empty_json = frozenset({
        "software_list", "local_printers_json",
        "monitors_detected_json", "peripherals_detected_json",
    })
    for u in updates:
        for k, v in u.items():
            if v is None or v == "":
                continue
            if k in _skip_empty_json and str(v).strip() in ("[]", "{}"):
                continue
            base[k] = v
    return base
