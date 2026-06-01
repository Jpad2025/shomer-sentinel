#!/usr/bin/env python3
"""
Orquestador del motor de auditoría SHOMER.
Descubre hosts (tracker.discovery), extrae datos (tracker.extractor), persiste (tracker.persistence).
Integridad: 100% de hosts a BD; MAC local para localhost; estatus nunca vacíos.
"""
import concurrent.futures
import os
import sys
import time
from typing import Any, Dict, List, Set


def _get_local_ips() -> Set[str]:
    """IPs de esta máquina (para detectar localhost en el escaneo)."""
    ips: Set[str] = set()
    try:
        import subprocess
        proc = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if proc.returncode == 0 and proc.stdout:
            for part in (proc.stdout or "").split():
                part = part.strip()
                if part and part.replace(".", "").isdigit():
                    ips.add(part)
    except Exception:
        pass
    if not ips:
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
            s.close()
        except Exception:
            pass
    return ips


def _get_local_interface_mac() -> str:
    """MAC de la interfaz activa (eth0 o wlan0) para inventariar el equipo donde corre el script."""
    for iface in ("eth0", "wlan0", "enp0s3", "ens33"):
        path = "/sys/class/net/%s/address" % iface
        if os.path.isfile(path):
            try:
                with open(path, "r") as f:
                    mac = (f.read() or "").strip().upper()
                    if mac and len(mac) == 17:
                        return mac
            except OSError:
                pass
    try:
        import subprocess
        proc = subprocess.run(
            ["ip", "link", "show"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        import re
        for line in (proc.stdout or "").splitlines():
            if "link/ether" in line:
                m = re.search(r"link/ether\s+([0-9a-f:]{17})", line, re.I)
                if m:
                    return m.group(1).strip().upper()
    except Exception:
        pass
    return ""

# Ruta del proyecto para imports (app.backend.db desde root, tracker desde app/scripts)
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.abspath(os.path.join(_scripts_dir, "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from app.backend.db import get_connection_inventory

from tracker import discovery, extractor, persistence
from tracker import get_logger, ensure_tracker_log_dir
from tracker.lldp_helper import get_lldp_neighbors

# Credenciales por defecto desde .env (se pasan al extractor si no hay overrides)
_ENV_FILE = os.path.join(_root, ".env")
try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_FILE)
except ImportError:
    pass

WMI_DEFAULT_USER = os.environ.get("SHOMER_WMI_USER", "")
WMI_DEFAULT_PASSWORD = os.environ.get("SHOMER_WMI_PASSWORD", "")
SSH_DEFAULT_USER = os.environ.get("SHOMER_SSH_USER", "")
SSH_DEFAULT_PASSWORD = os.environ.get("SHOMER_SSH_PASSWORD", "")

HOST_TIMEOUT_SEC = 5
TIMEOUT_CRITICAL_SEC = 12


def _process_one_host(h: Dict[str, Any], idx: int, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Enriquece un host con SNMP/WMI/SSH/web y devuelve el dict base listo para persistir."""
    overrides_by_ip = ctx["overrides_by_ip"]
    snmp_community = ctx["snmp_community"]
    wmi_user = ctx["wmi_user"]
    wmi_pass = ctx["wmi_pass"]
    wmi_domain = ctx["wmi_domain"]
    lldp_index = ctx["lldp_index"]
    os_aggressive = ctx["os_aggressive"]
    local_ips = ctx["local_ips"]
    local_mac = ctx["local_mac"]

    ip = (h.get("ip") or "").strip()
    if not ip:
        ip = "unknown-%d" % idx
        h = dict(h)
        h["ip"] = ip
    base = dict(h)
    if base.get("ip") != ip:
        base["ip"] = ip
    mac_raw = (base.get("mac") or "").strip()
    if mac_raw.startswith("ip-") and ip in local_ips and local_mac:
        base["mac"] = local_mac
    ov = overrides_by_ip.get(ip, {}) or {}
    eff_snmp = ov.get("snmp") or snmp_community
    eff_user = ov.get("user") or wmi_user
    eff_pass = ov.get("password") or wmi_pass
    if ov:
        base["override_user"] = ov.get("user", "")
        base["override_pass"] = ov.get("password", "")
        base["override_snmp"] = ov.get("snmp", "")

    if not (base.get("asset_type") or "").strip():
        vendor_guess = discovery.guess_asset_type_from_vendor(base.get("vendor") or "")
        if vendor_guess:
            base["asset_type"] = vendor_guess

    lldp_match = lldp_index.lookup(ip=ip, mac=(base.get("mac") or ""))
    if lldp_match:
        lldp_data = lldp_match.to_merge_dict()
        if lldp_data.get("asset_type"):
            base["asset_type"] = lldp_data["asset_type"]
        if lldp_data.get("hostname") and not (base.get("hostname") or "").strip():
            base["hostname"] = lldp_data["hostname"]
        if lldp_data.get("os_detected") and not (base.get("os_detected") or "").strip():
            base["os_detected"] = lldp_data["os_detected"]
        base["lldp_via"] = lldp_data.get("lldp_via") or ""
        base["lldp_port"] = lldp_data.get("lldp_port") or ""

    try:
        ports_list = discovery.scan_ports_per_host(ip)
    except Exception as e:
        import logging
        logging.getLogger("tracker.scanner").debug("scan_ports %s: %s", ip, e)
        ports_list = []
    if ports_list:
        base["ports_open"] = ", ".join(ports_list)
    else:
        ports = []
        for port, name in [
            (161, "snmp"), (135, "msrpc"), (445, "smb"),
            (22, "ssh"), (80, "http"), (443, "https"),
        ]:
            if discovery._port_open(ip, port):
                ports.append("%s/%s" % (port, name))
        ports_list = ports
        base["ports_open"] = ", ".join(ports) or base.get("ports_open", "")

    def _has_port(p: int) -> bool:
        s = str(p)
        for item in (ports_list or []):
            if item == s or item.startswith(s + "/"):
                return True
        return False

    has_161 = _has_port(161)
    has_135 = _has_port(135)
    has_445 = _has_port(445)
    has_22 = _has_port(22)
    has_critical = has_161 or has_135 or has_22
    t_sec = float(TIMEOUT_CRITICAL_SEC) if has_critical else float(HOST_TIMEOUT_SEC)

    atype = (base.get("asset_type") or "").lower()
    os_family_raw = (base.get("os_family") or "").strip()
    os_detected_raw = (base.get("os_detected") or "").strip()
    ports_open_str = (base.get("ports_open") or "").lower()
    is_windows = (
        "windows" in os_family_raw.lower()
        or "windows" in os_detected_raw.lower()
        or has_445 or has_135
        or "microsoft windows rpc" in ports_open_str
        or "msrpc" in ports_open_str
    )
    is_linux = "linux" in (os_family_raw or "").lower()

    snmp_candidate = (
        atype in ("printer", "impresora", "switch", "ap") or not is_windows
    )
    wmi_candidate = (has_135 or has_445) and is_windows
    ssh_candidate = has_22

    try:
        snmp_data = (
            extractor.phase2_snmp(ip, eff_snmp, timeout=min(t_sec, 5.0))
            if snmp_candidate
            else {}
        )
        extractor.merge_asset(base, snmp_data)
    except Exception as e:
        import logging
        logging.getLogger("tracker.scanner").debug("SNMP %s: %s", ip, e)

    wmi_data = {}
    if wmi_candidate:
        try:
            wmi_data = extractor.phase3_wmi(
                ip, WMI_DEFAULT_USER, WMI_DEFAULT_PASSWORD, "", timeout_sec=t_sec
            )
            if not wmi_data.get("wmi_status") or wmi_data.get("wmi_status") != "OK" or (
                not wmi_data.get("cpu") and not wmi_data.get("ram")
            ):
                wmi_data = extractor.phase3_wmi(
                    ip, eff_user, eff_pass, wmi_domain, timeout_sec=t_sec
                )
        except Exception as e:
            import logging
            logging.getLogger("tracker.scanner").debug("WMI %s: %s", ip, e)
        extractor.merge_asset(base, wmi_data)
        for _k in (
            "asset_model", "ram", "cpu", "os_detected",
            "serial_number", "firmware_version", "storage_cap",
        ):
            if _k in wmi_data and (wmi_data.get(_k) or "").strip():
                base[_k] = (wmi_data.get(_k) or "").strip()

    ssh_user = (eff_user or "").strip() or SSH_DEFAULT_USER
    ssh_pass = (eff_pass or "").strip() or SSH_DEFAULT_PASSWORD
    if ssh_candidate:
        try:
            ssh_data = extractor.phase4_ssh(ip, ssh_user, ssh_pass, timeout_sec=t_sec)
            extractor.merge_asset(base, ssh_data)
        except Exception as e:
            import logging
            logging.getLogger("tracker.scanner").debug("SSH %s: %s", ip, e)

    web_title = ""
    try:
        if any((p == "80" or p.startswith("80/")) for p in (ports_list or [])):
            banner = extractor.get_web_banner(
                ip, use_https=False, timeout=3.0,
                mac_vendor=(base.get("vendor") or "").strip(),
            )
            extractor.merge_asset(base, banner)
            if banner.get("identity_note"):
                vn = (base.get("visual_details") or "").strip()
                extra = (vn + "\n" if vn else "") + (banner.get("identity_note") or "")
                base["visual_details"] = extra.strip()[:2000]
            base.pop("identity_note", None)
            web_title = banner.get("title", "")
        if not web_title and any(
            (p == "443" or p.startswith("443/")) for p in (ports_list or [])
        ):
            banner = extractor.get_web_banner(
                ip, use_https=True, timeout=3.0,
                mac_vendor=(base.get("vendor") or "").strip(),
            )
            extractor.merge_asset(base, banner)
            if banner.get("identity_note"):
                vn = (base.get("visual_details") or "").strip()
                extra = (vn + "\n" if vn else "") + (banner.get("identity_note") or "")
                base["visual_details"] = extra.strip()[:2000]
            base.pop("identity_note", None)
            web_title = banner.get("title", "")
        if web_title:
            if not base.get("asset_model"):
                base["asset_model"] = web_title[:200]
            elif not base.get("os_detected"):
                base["os_detected"] = web_title[:200]
    except Exception as e:
        import logging
        logging.getLogger("tracker.scanner").debug("Web banner %s: %s", ip, e)

    extractor.consolidate_identity(
        base,
        nmap_os=os_aggressive.get(ip, {}).get("os_detected") if ip in os_aggressive else None,
    )

    remedy_msg = ""
    remedy_cmd = ""
    for key, proto in (("wmi_status", "wmi"), ("ssh_status", "ssh"), ("snmp_status", "snmp")):
        status = (base.get(key) or "").strip()
        if not status:
            continue
        su = status.upper()
        if su.startswith("ERROR") or "SIN RESPUESTA" in su:
            remedy_msg, remedy_cmd = extractor.get_it_remedy(
                status, base.get("asset_type", "") or "", proto
            )
            if remedy_msg:
                break
    if not remedy_msg:
        if any((p == "80" or p.startswith("80/")) for p in (ports_list or [])) and not web_title:
            remedy_msg, remedy_cmd = extractor.get_it_remedy(
                "HTTP_NO_TITLE", base.get("asset_type", "") or "", "http"
            )
        if not remedy_msg and any(
            (p == "443" or p.startswith("443/")) for p in (ports_list or [])
        ) and not web_title:
            remedy_msg, remedy_cmd = extractor.get_it_remedy(
                "HTTP_BANNER_MISSING", base.get("asset_type", "") or "", "http"
            )
    if remedy_msg:
        base["it_remedy"] = remedy_msg
        if remedy_cmd:
            base["it_command"] = remedy_cmd

    if not (base.get("hostname") or "").strip() and (base.get("os_name") or "").strip():
        base["hostname"] = (base.get("os_name") or "").strip()[:100]
    if (base.get("vendor") or "").strip() == "Unknown":
        base["vendor"] = (discovery._vendor_from_mac(base.get("mac") or "") or "Unknown").strip()[:200]
    if not (base.get("asset_type") or "").strip():
        vg = discovery.guess_asset_type_from_vendor(base.get("vendor") or "")
        if vg:
            base["asset_type"] = vg
    if not (base.get("wmi_status") or "").strip():
        base["wmi_status"] = "FAILED" if (has_135 or has_445) else "NOT_ATTEMPTED"
    if not (base.get("snmp_status") or "").strip():
        base["snmp_status"] = "FAILED" if has_161 else "NOT_ATTEMPTED"
    if not (base.get("ssh_status") or "").strip():
        base["ssh_status"] = "FAILED" if has_22 else "NOT_ATTEMPTED"

    return base


def _dedupe_hosts_by_mac(hosts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fusiona filas del discovery con la misma MAC (case-insensitive). Evita dos
    pasadas (nmap + ARP) duplicando PK en SQLite con distinto casing."""
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for h in hosts:
        raw_mac = (h.get("mac") or "").strip()
        if raw_mac and discovery._is_real_mac(raw_mac):
            key = raw_mac.upper()
        else:
            ip = (h.get("ip") or "").strip()
            key = "ip:" + ip if ip else "orphan:%d" % len(merged)
        if key not in merged:
            nh = dict(h)
            if raw_mac and discovery._is_real_mac(raw_mac):
                nh["mac"] = raw_mac.upper()
            merged[key] = nh
            order.append(key)
            continue
        dst = merged[key]
        for k, v in h.items():
            if v is None or v == "":
                continue
            cur = dst.get(k)
            if cur is None or (isinstance(cur, str) and not cur.strip()):
                dst[k] = v
            elif k == "mac" and discovery._is_real_mac(str(v)):
                dst[k] = str(v).strip().upper()
    return [merged[k] for k in order]


def run_scan() -> int:
    ensure_tracker_log_dir()
    log = get_logger("tracker.scanner")

    with get_connection_inventory(timeout=30) as conn:
        persistence.ensure_schema(conn)
        creds = persistence.get_credentials(conn)
        overrides_by_ip = persistence.get_overrides_by_ip(conn)

    targets = discovery.get_targets()
    log.info("[INFO] Scan started (targets=%s)", len(targets))

    hosts = discovery.discovery_nmap(targets)
    if not hosts:
        log.warning("Discovery: no hosts found")
        return 0
    hosts = _dedupe_hosts_by_mac(hosts)
    log.info("[INFO] Discovery: %d hosts to process (tras dedupe MAC)", len(hosts))

    # LLDP/CDP: capturamos vecinos que se anunciaron al Shomer por L2. Es
    # pasivo (no emite) y agrega información que nmap/ARP no ven, en
    # especial: hostname + capabilities (Router/Bridge/Wlan) de switches
    # managed, IP phones, y Windows (que anuncia por default desde Win8+).
    try:
        lldp_index = get_lldp_neighbors(exclude_self=True)
        log.info("[INFO] LLDP: %d vecinos detectados", len(lldp_index.all))
    except Exception as e:
        log.debug("LLDP lookup failed: %s", e)
        from tracker.lldp_helper import LLDPIndex
        lldp_index = LLDPIndex()

    ip_list = [h.get("ip") for h in hosts if h.get("ip")]
    os_aggressive: Dict[str, Any] = {}
    if ip_list:
        os_aggressive = discovery.os_detection_aggressive(ip_list)
        for h in hosts:
            ip = h.get("ip", "")
            if ip and ip in os_aggressive:
                extractor.merge_asset(h, os_aggressive[ip])

    snmp_community = creds.get("snmp_community", "public")
    wmi_user = creds.get("user", "")
    wmi_pass = creds.get("password", "")
    wmi_domain = creds.get("domain", "")

    results: List[Dict[str, Any]] = []
    start_time = time.monotonic()
    local_ips = _get_local_ips()
    local_mac = _get_local_interface_mac()

    ctx: Dict[str, Any] = {
        "overrides_by_ip": overrides_by_ip,
        "snmp_community": snmp_community,
        "wmi_user": wmi_user,
        "wmi_pass": wmi_pass,
        "wmi_domain": wmi_domain,
        "lldp_index": lldp_index,
        "os_aggressive": os_aggressive,
        "local_ips": local_ips,
        "local_mac": local_mac,
    }

    # Guardado incremental: abre conexión única para toda la duración del scan.
    # Cada lote de SAVE_BATCH_SIZE hosts se persiste en SQLite aunque el proceso
    # se interrumpa antes de terminar — evita perder todo en redes de 200+ equipos.
    SAVE_BATCH_SIZE = 10
    MAX_WORKERS = 20

    with get_connection_inventory(timeout=60) as conn:
        persistence.ensure_schema(conn)
        pending: List[Dict[str, Any]] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            fmap = {
                executor.submit(_process_one_host, h, idx, ctx): idx
                for idx, h in enumerate(hosts)
            }
            for fut in concurrent.futures.as_completed(fmap):
                try:
                    base = fut.result()
                    results.append(base)
                    pending.append(base)
                except Exception as exc:
                    log.error("Host %d processing failed: %s", fmap[fut], exc)

                if len(pending) >= SAVE_BATCH_SIZE:
                    persistence.save_assets(pending, conn)
                    log.info(
                        "[INFO] Incremental save: %d/%d hosts stored",
                        len(results), len(hosts),
                    )
                    pending.clear()

        if pending:
            persistence.save_assets(pending, conn)
            log.info(
                "[INFO] Incremental save final: %d/%d hosts stored",
                len(results), len(hosts),
            )

        if os.environ.get("INVENTORY_SCAN_REPLACE") == "1":
            current_macs = [
                str((a.get("mac") or "").strip())
                for a in results
                if (a.get("mac") or "").strip()
            ]
            if current_macs:
                placeholders = ",".join(["?"] * len(current_macs))
                conn.execute(
                    "DELETE FROM assets WHERE mac NOT IN (%s)" % placeholders,
                    current_macs,
                )
                conn.commit()

    elapsed = time.monotonic() - start_time
    success_count = sum(
        1 for a in results
        if (a.get("wmi_status") or "").strip() == "OK"
        or (a.get("ssh_status") or "").strip() == "OK"
        or (a.get("snmp_status") or "").strip() == "OK"
    )
    log.info(
        "[INFO] Scan finished: total_time=%.1fs, assets_processed=%d, with_protocol_ok=%d",
        elapsed, len(results), success_count,
    )

    return 0


def run_quick_scan() -> int:
    """
    Escaneo rápido: ping sweep + MAC + vendor + hostname básico.
    Sin OS detection, sin WMI, sin SSH, sin SNMP.
    Resultado en ~15-30 segundos independientemente del número de hosts.
    """
    ensure_tracker_log_dir()
    log = get_logger("tracker.scanner")

    targets = discovery.get_targets()
    log.info("[INFO] Quick scan started (targets=%s)", len(targets))

    hosts = discovery.discovery_nmap(targets)
    if not hosts:
        log.warning("Quick scan: no hosts found")
        return 0
    hosts = _dedupe_hosts_by_mac(hosts)
    log.info("[INFO] Quick scan: %d hosts found (tras dedupe MAC)", len(hosts))

    start_time = time.monotonic()
    local_ips = _get_local_ips()
    local_mac = _get_local_interface_mac()

    results: List[Dict[str, Any]] = []
    for idx, h in enumerate(hosts):
        ip = (h.get("ip") or "").strip()
        if not ip:
            ip = "unknown-%d" % idx
        base = dict(h)
        base["ip"] = ip

        mac_raw = (base.get("mac") or "").strip()
        if mac_raw.startswith("ip-") and ip in local_ips and local_mac:
            base["mac"] = local_mac

        if (base.get("vendor") or "").strip() in ("", "Unknown"):
            base["vendor"] = (discovery._vendor_from_mac(base.get("mac") or "") or "Unknown").strip()[:200]

        # Inferir tipo desde vendor si no viene del nmap
        if not (base.get("asset_type") or "").strip():
            vg = discovery.guess_asset_type_from_vendor(base.get("vendor") or "")
            if vg:
                base["asset_type"] = vg

        results.append(base)

    elapsed = time.monotonic() - start_time
    log.info("[INFO] Quick scan finished: total_time=%.1fs, hosts=%d", elapsed, len(results))

    with get_connection_inventory(timeout=30) as conn:
        persistence.ensure_schema(conn)
        persistence.merge_quick_scan_assets(results, conn)

    return 0


if __name__ == "__main__":
    mode = os.environ.get("INVENTORY_SCAN_MODE", "deep")
    if mode == "quick":
        raise SystemExit(run_quick_scan())
    else:
        raise SystemExit(run_scan())
