"""
Auditoría de Red — Shomer Sentinel 2.0
Escaneo nmap -sV sobre activos del Tracker → hallazgos clasificados por severidad.
Estados de hallazgo: pendiente / en_revision / terminado.
"""
import asyncio
import json
import logging
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

import asyncssh

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_api import get_current_user, require_admin
from app.api.shomer_common import get_db
from app.backend.db import connect_inventory
from app.scripts.tracker.extractor import (
    _PS_PENDING_PATCHES,
    _REMOTE_PATCH_SMB,
    wmi_powershell_json,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["audit_network"])

# Solo un escaneo a la vez
_scan_running = False

# ── Reglas de riesgo por puerto ───────────────────────────────────────────────
# (puerto, severidad, titulo, categoria, descripcion, recomendacion)
_PORT_RULES: list[tuple] = [
    (23,    "critico",  "Telnet expuesto",             "acceso_inseguro",
     "Telnet transmite credenciales en texto plano. Cualquier equipo en la red puede capturar contraseñas.",
     "Deshabilitar Telnet. Usar SSH para administración remota."),
    (512,   "critico",  "rexec expuesto",              "acceso_inseguro",
     "Servicio rexec legacy sin autenticación segura.",
     "Deshabilitar rexec. Usar SSH."),
    (513,   "critico",  "rlogin expuesto",             "acceso_inseguro",
     "Servicio rlogin legacy sin cifrado.",
     "Deshabilitar rlogin. Usar SSH."),
    (514,   "critico",  "rsh expuesto",                "acceso_inseguro",
     "Servicio rsh sin cifrado ni autenticación fuerte.",
     "Deshabilitar rsh. Usar SSH."),
    (6379,  "critico",  "Redis expuesto en red",       "base_de_datos",
     "Redis accesible en la red sin autenticación por defecto. Puede usarse para ejecución remota de comandos.",
     "Restringir Redis a localhost. Agregar requirepass en redis.conf."),
    (21,    "alto",     "FTP sin cifrado",             "acceso_inseguro",
     "FTP transmite credenciales y datos en texto plano.",
     "Migrar a SFTP (SSH) o FTPS. Deshabilitar FTP si no es necesario."),
    (3389,  "alto",     "RDP expuesto",                "acceso_remoto",
     "Escritorio remoto accesible en la red. Objetivo frecuente de fuerza bruta.",
     "Restringir RDP a IPs administrativas o túnel VPN. Activar NLA."),
    (3306,  "alto",     "MySQL expuesto en red",       "base_de_datos",
     "Base de datos MySQL accesible desde la red.",
     "Restringir MySQL a localhost o IP del servidor de aplicación."),
    (5432,  "alto",     "PostgreSQL expuesto en red",  "base_de_datos",
     "Base de datos PostgreSQL accesible desde la red.",
     "Configurar pg_hba.conf para aceptar solo localhost o IPs confiables."),
    (1433,  "alto",     "MSSQL expuesto en red",       "base_de_datos",
     "SQL Server accesible desde la red.",
     "Restringir MSSQL a localhost o IPs del servidor de aplicación."),
    (5900,  "alto",     "VNC expuesto",                "acceso_remoto",
     "VNC accesible en la red. Puede tener autenticación débil.",
     "Proteger VNC con túnel SSH o VPN. Usar contraseña fuerte."),
    (27017, "alto",     "MongoDB expuesto en red",     "base_de_datos",
     "MongoDB puede estar accesible sin autenticación.",
     "Habilitar autenticación en MongoDB y restringir a localhost."),
    (11211, "alto",     "Memcached expuesto",          "base_de_datos",
     "Memcached sin autenticación puede usarse para amplificación DDoS.",
     "Restringir Memcached a localhost."),
    (445,   "medio",    "SMB activo",                  "compartidos",
     "Puerto SMB activo. Verificar que solo comparte recursos necesarios con autenticación.",
     "Auditar shares compartidos. Deshabilitar acceso anónimo."),
    (139,   "medio",    "NetBIOS activo",              "compartidos",
     "NetBIOS expone información del equipo en la red.",
     "Deshabilitar NetBIOS si no es requerido por aplicaciones legacy."),
    (161,   "medio",    "SNMP activo",                 "monitoreo",
     "Verificar que la comunidad SNMP no sea 'public' o 'private'. Acceso de lectura puede exponer configuración.",
     "Cambiar comunidad SNMP a valor personalizado. Restringir a IPs del servidor Shomer."),
    (162,   "medio",    "SNMP Trap activo",            "monitoreo",
     "SNMP Trap activo. Verificar restricción de destinos.",
     "Restringir traps a IPs autorizadas."),
    (80,    "medio",    "HTTP sin cifrado",            "web",
     "Panel de administración o servicio web usando HTTP. Las credenciales viajan en texto plano.",
     "Habilitar HTTPS (TLS). Redirigir HTTP → HTTPS."),
    (2049,  "medio",    "NFS expuesto",                "compartidos",
     "NFS activo en la red. Los exports pueden ser montados por cualquier equipo.",
     "Restringir exports NFS a IPs específicas. Revisar /etc/exports."),
    (8080,  "bajo",     "HTTP alternativo activo",     "web",
     "Puerto HTTP alternativo activo. Puede ser un panel de administración sin cifrado.",
     "Verificar si requiere HTTPS. Deshabilitar si no es necesario."),
    (8008,  "bajo",     "HTTP alternativo activo",     "web",
     "Puerto HTTP alternativo.",
     "Verificar uso y habilitar HTTPS si aplica."),
    (2222,  "bajo",     "SSH en puerto alternativo",   "acceso_remoto",
     "SSH corriendo en puerto no estándar.",
     "Verificar que es SSH legítimo. Mantener fail2ban activo."),
    (8888,  "bajo",     "Puerto de administración",    "web",
     "Puerto de administración o Jupyter Notebook detectado.",
     "Verificar acceso y proteger con autenticación."),
]

# Puertos informativos (no generan alerta pero se registran)
_INFO_PORTS = {22, 443, 8443, 53, 67, 68, 123}

_PORT_RULE_MAP = {r[0]: r for r in _PORT_RULES}


# ──────────────────────────────────────────────
# DB init
# ──────────────────────────────────────────────

_tables_ready = False


def _init_tables():
    # Llamado en CADA endpoint de este módulo -- guard de una sola vez evita CREATE/ALTER
    # repetido contra SQLite en el hilo único de Guardian por request.
    global _tables_ready
    if _tables_ready:
        return
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS network_audit_scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT DEFAULT 'running',
                total_hosts INTEGER DEFAULT 0,
                findings_count INTEGER DEFAULT 0,
                triggered_by TEXT DEFAULT 'manual',
                error_msg TEXT
            );
            CREATE TABLE IF NOT EXISTS network_audit_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id INTEGER REFERENCES network_audit_scans(id),
                ip TEXT NOT NULL,
                hostname TEXT,
                port INTEGER,
                protocol TEXT DEFAULT 'tcp',
                service TEXT,
                version TEXT,
                severity TEXT NOT NULL,
                category TEXT,
                title TEXT NOT NULL,
                description TEXT,
                recommendation TEXT,
                finding_status TEXT DEFAULT 'pendiente',
                notes TEXT,
                found_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_naf_ip ON network_audit_findings(ip);
            CREATE INDEX IF NOT EXISTS idx_naf_severity ON network_audit_findings(severity);
            CREATE INDEX IF NOT EXISTS idx_naf_status ON network_audit_findings(finding_status);
        """)
        conn.commit()
    _tables_ready = True


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _get_asset_ip_map() -> dict[str, str]:
    """IP → hostname desde inventory.db."""
    mapping: dict[str, str] = {}
    try:
        conn = connect_inventory()
        try:
            rows = conn.execute(
                "SELECT ip, hostname FROM assets WHERE ip IS NOT NULL AND ip != ''"
            ).fetchall()
            for ip, hostname in rows:
                ip = (ip or "").strip()
                hn = (hostname or "").strip()
                if ip and hn:
                    mapping[ip] = hn
        finally:
            conn.close()
    except Exception as e:
        logger.warning("No se pudo leer hostnames de inventory.db: %s", e)
    return mapping


def _get_asset_ips() -> list[str]:
    """Lee IPs únicas de inventory.db (Tracker assets)."""
    try:
        conn = connect_inventory()
        try:
            rows = conn.execute(
                "SELECT DISTINCT ip FROM assets WHERE ip IS NOT NULL AND ip != '' ORDER BY ip"
            ).fetchall()
            return [r[0] for r in rows if r[0]]
        finally:
            conn.close()
    except Exception as e:
        logger.warning("No se pudo leer inventory.db: %s", e)
        return []


def _run_nmap(ips: list[str]) -> Optional[str]:
    """Ejecuta nmap -sV -T3 --open -oX sobre la lista de IPs. Retorna XML string o None."""
    if not ips:
        return None
    cmd = [
        "nmap", "-sV", "--version-intensity", "2",
        "-T3", "--open", "-oX", "-",
        "--host-timeout", "45s",
    ] + ips
    nmap_timeout = min(900, max(300, len(ips) * 10))
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=nmap_timeout,
        )
        if result.returncode != 0:
            logger.warning("nmap exit=%s stderr=%s", result.returncode, result.stderr[:200])
        return result.stdout if result.stdout.strip() else None
    except subprocess.TimeoutExpired:
        logger.error("nmap timeout después de 300s")
        return None
    except Exception as e:
        logger.error("nmap error: %s", e)
        return None


def _parse_nmap_xml(xml_str: str) -> list[dict]:
    """
    Parsea XML de nmap y retorna lista de hallazgos.
    Cada hallazgo: {ip, hostname, port, protocol, service, version, severity, category, title, description, recommendation}
    """
    findings = []
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        logger.error("Error parsing nmap XML: %s", e)
        return findings

    for host in root.findall("host"):
        # IP
        addr_el = host.find("address[@addrtype='ipv4']")
        if addr_el is None:
            continue
        ip = addr_el.get("addr", "")

        # Hostname
        hostnames_el = host.find("hostnames")
        hostname = ""
        if hostnames_el is not None:
            hn = hostnames_el.find("hostname[@type='user']")
            if hn is None:
                hn = hostnames_el.find("hostname")
            if hn is not None:
                hostname = hn.get("name", "")

        # Ports
        ports_el = host.find("ports")
        if ports_el is None:
            continue

        for port_el in ports_el.findall("port"):
            state_el = port_el.find("state")
            if state_el is None or state_el.get("state") != "open":
                continue

            portnum = int(port_el.get("portid", 0))
            protocol = port_el.get("protocol", "tcp")

            service_el = port_el.find("service")
            service_name = ""
            version_str = ""
            if service_el is not None:
                service_name = service_el.get("name", "")
                product = service_el.get("product", "")
                version = service_el.get("version", "")
                extrainfo = service_el.get("extrainfo", "")
                parts = [p for p in [product, version, extrainfo] if p]
                version_str = " ".join(parts)

            # Skip purely informational ports (no finding)
            if portnum in _INFO_PORTS:
                continue

            # Check rule
            if portnum in _PORT_RULE_MAP:
                _, severity, title, category, description, recommendation = _PORT_RULE_MAP[portnum]
            else:
                # Unknown open port — severity depends on protocol
                severity = "info"
                title = f"Puerto abierto: {portnum}/{protocol}"
                category = "puerto_abierto"
                service_display = f" ({service_name})" if service_name else ""
                description = f"Puerto {portnum}/{protocol}{service_display} abierto. Verificar si el servicio es necesario."
                recommendation = "Si el servicio no es requerido, cerrar el puerto en el firewall del equipo."

            findings.append({
                "ip": ip,
                "hostname": hostname,
                "port": portnum,
                "protocol": protocol,
                "service": service_name,
                "version": version_str,
                "severity": severity,
                "category": category,
                "title": title,
                "description": description,
                "recommendation": recommendation,
            })

    return findings


def _save_findings(scan_id: int, findings: list[dict], hostname_map: Optional[dict] = None) -> int:
    """Guarda hallazgos en BD. Evita duplicados por (ip, port, protocol) — actualiza si existe."""
    hostname_map = hostname_map or {}
    count = 0
    with get_db() as conn:
        for f in findings:
            if not f.get("hostname") and f.get("ip") in hostname_map:
                f["hostname"] = hostname_map[f["ip"]]
            # Check if finding already exists for this ip+port+protocol (any previous scan)
            existing = conn.execute(
                "SELECT id, finding_status FROM network_audit_findings WHERE ip=? AND port=? AND protocol=? ORDER BY id DESC LIMIT 1",
                (f["ip"], f["port"], f["protocol"])
            ).fetchone()
            if existing:
                # If marked terminado but port is still open → reset to pendiente
                new_status = existing["finding_status"]
                if new_status == "terminado":
                    new_status = "pendiente"
                conn.execute(
                    """UPDATE network_audit_findings SET
                       scan_id=?, hostname=?, service=?, version=?, severity=?,
                       category=?, title=?, description=?, recommendation=?,
                       finding_status=?, updated_at=datetime('now')
                       WHERE id=?""",
                    (scan_id, f["hostname"], f["service"], f["version"], f["severity"],
                     f["category"], f["title"], f["description"], f["recommendation"],
                     new_status, existing["id"])
                )
            else:
                conn.execute(
                    """INSERT INTO network_audit_findings
                       (scan_id, ip, hostname, port, protocol, service, version,
                        severity, category, title, description, recommendation,
                        finding_status, found_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'pendiente',datetime('now'),datetime('now'))""",
                    (scan_id, f["ip"], f["hostname"], f["port"], f["protocol"],
                     f["service"], f["version"], f["severity"], f["category"],
                     f["title"], f["description"], f["recommendation"])
                )
                count += 1
        conn.commit()
    return count


# ──────────────────────────────────────────────
# Auditoría de parches — SSH/WMI por equipo
# ──────────────────────────────────────────────

def _get_patchable_assets(live_ips: set) -> list[dict]:
    """
    Lee inventory.db y retorna los activos que:
    - Respondieron al nmap (están en live_ips)
    - Son Linux, macOS o Windows
    - Tienen credenciales (global o por equipo)
    Lógica: override_user/override_pass del asset primero; si vacío, cae a network_credentials global.
    """
    try:
        conn = connect_inventory()
        try:
            # Credenciales globales (fallback)
            global_row = conn.execute(
                "SELECT user, password, domain FROM network_credentials ORDER BY id LIMIT 1"
            ).fetchone()
            global_user = (global_row[0] or "").strip() if global_row else ""
            global_pass = (global_row[1] or "").strip() if global_row else ""
            global_domain = (global_row[2] or "").strip() if global_row else ""

            rows = conn.execute(
                "SELECT ip, hostname, os_family, override_user, override_pass FROM assets "
                "WHERE ip IS NOT NULL AND ip != ''"
            ).fetchall()
        finally:
            conn.close()
    except Exception as e:
        logger.warning("_get_patchable_assets: no se pudo leer inventory.db: %s", e)
        return []

    result = []
    for row in rows:
        ip        = (row[0] or "").strip()
        hostname  = (row[1] or "").strip()
        os_family = (row[2] or "").lower().strip()
        ov_user   = (row[3] or "").strip()
        ov_pass   = (row[4] or "").strip()

        if ip not in live_ips:
            continue

        # Solo equipos con OS compatible para auditoría de parches
        if not any(k in os_family for k in ("linux", "darwin", "windows")):
            continue

        user     = ov_user  if ov_user  else global_user
        password = ov_pass  if ov_pass  else global_pass

        if not user:
            continue  # sin credenciales → saltar silenciosamente

        result.append({
            "ip":        ip,
            "hostname":  hostname,
            "os_family": os_family,
            "user":      user,
            "password":  password,
            "domain":    global_domain,
        })

    return result


def _patch_check_wmi(ip: str, user: str, password: str, domain: str = "", hostname: str = "") -> Optional[dict]:
    """
    Windows: actualizaciones pendientes vía Windows Update API (PowerShell remoto).
    Retorna hallazgo o None si el equipo está al día.
    """
    data = wmi_powershell_json(
        ip, user, password, domain,
        _PS_PENDING_PATCHES,
        _REMOTE_PATCH_SMB,
        wait_sec=20.0,
    )
    if not isinstance(data, dict):
        return None

    try:
        count = int(data.get("count") or 0)
    except (TypeError, ValueError):
        count = 0

    if count <= 0:
        return None

    titles = data.get("titles") or []
    if isinstance(titles, str):
        titles = [titles]
    sample = "\n".join("- " + str(t)[:120] for t in titles[:8])
    has_kernel = any("kernel" in str(t).lower() or "security" in str(t).lower() for t in titles)
    severity = "critico" if has_kernel and count > 5 else ("alto" if count > 15 else ("medio" if count > 5 else "bajo"))

    return {
        "ip":             ip,
        "hostname":       hostname,
        "port":           0,
        "protocol":       "wmi",
        "service":        "windows-update",
        "version":        "",
        "severity":       severity,
        "category":       "parches",
        "title":          f"{count} actualización{'es' if count > 1 else ''} pendiente{'s' if count > 1 else ''} (Windows)",
        "description":    f"Windows Update reporta {count} actualizaciones sin instalar.\n{sample}",
        "recommendation": "Abrir Configuración → Windows Update → Instalar actualizaciones. "
                           "En AD/WSUS, verificar que el equipo reciba las políticas de parches.",
    }


async def _patch_check_single(asset: dict) -> Optional[dict]:
    """
    Conecta por SSH al equipo y verifica actualizaciones pendientes.
    Retorna un dict de hallazgo o None si el equipo está al día.
    Windows: marcado como pendiente (impacket no instalado).
    """
    ip        = asset["ip"]
    os_family = asset["os_family"]
    user      = asset["user"]
    password  = asset["password"]
    hostname  = asset.get("hostname") or ""

    # Windows → WMI + PowerShell (actualizaciones pendientes)
    if "windows" in os_family:
        return await asyncio.to_thread(
            _patch_check_wmi,
            ip,
            asset["user"],
            asset["password"],
            asset.get("domain", ""),
            hostname,
        )

    # Linux / macOS → SSH
    try:
        async with asyncssh.connect(
            ip,
            username=user,
            password=password,
            known_hosts=None,
            connect_timeout=8,
            login_timeout=10,
        ) as conn:
            if "darwin" in os_family:
                result = await asyncio.wait_for(
                    conn.run("softwareupdate -l 2>&1", check=False), timeout=20
                )
                output = result.stdout or ""
                updates = [l for l in output.splitlines() if l.strip().startswith("-")]
                n = len(updates)
                if n == 0:
                    return None
                sample = "\n".join(updates[:5])
                return {
                    "ip":             ip,
                    "hostname":       hostname,
                    "port":           22,
                    "protocol":       "ssh",
                    "service":        "macos-update",
                    "version":        "",
                    "severity":       "medio" if n > 3 else "bajo",
                    "category":       "parches",
                    "title":          f"{n} actualización{'es' if n>1 else ''} pendiente{'s' if n>1 else ''} (macOS)",
                    "description":    f"Hay {n} actualizaciones de software disponibles:\n{sample}",
                    "recommendation": "Ejecutar: sudo softwareupdate -ia",
                }

            else:  # Linux
                # Intentar apt primero
                apt_result = await asyncio.wait_for(
                    conn.run("apt list --upgradable 2>/dev/null | grep -v 'Listing'", check=False),
                    timeout=20
                )
                apt_out = (apt_result.stdout or "").strip()

                if apt_out:
                    lines = [l for l in apt_out.splitlines() if l.strip()]
                    n = len(lines)
                    has_kernel = any("linux-image" in l or "linux-headers" in l for l in lines)
                    severity = "critico" if has_kernel else ("medio" if n > 10 else "bajo")
                    sample = "\n".join(lines[:5])
                    title_extra = " (incluye kernel)" if has_kernel else ""
                    return {
                        "ip":             ip,
                        "hostname":       hostname,
                        "port":           22,
                        "protocol":       "ssh",
                        "service":        "apt",
                        "version":        "",
                        "severity":       severity,
                        "category":       "parches",
                        "title":          f"{n} actualización{'es' if n>1 else ''} pendiente{'s' if n>1 else ''} (Linux){title_extra}",
                        "description":    f"Paquetes con actualizaciones disponibles:\n{sample}" + ("\n..." if n > 5 else ""),
                        "recommendation": "Ejecutar: sudo apt update && sudo apt upgrade -y",
                    }

                # Intentar yum/dnf como fallback
                yum_result = await asyncio.wait_for(
                    conn.run("yum check-update -q 2>/dev/null | wc -l", check=False),
                    timeout=20
                )
                try:
                    n = int((yum_result.stdout or "0").strip())
                except ValueError:
                    n = 0

                if n > 0:
                    return {
                        "ip":             ip,
                        "hostname":       hostname,
                        "port":           22,
                        "protocol":       "ssh",
                        "service":        "yum",
                        "version":        "",
                        "severity":       "medio" if n > 10 else "bajo",
                        "category":       "parches",
                        "title":          f"{n} actualización{'es' if n>1 else ''} pendiente{'s' if n>1 else ''} (Linux/yum)",
                        "description":    f"{n} paquetes con actualizaciones disponibles vía yum/dnf.",
                        "recommendation": "Ejecutar: sudo yum update -y",
                    }

                return None  # al día

    except asyncssh.DisconnectError:
        return None  # equipo rechazó la conexión — no es un hallazgo accionable
    except (asyncssh.PermissionDenied, asyncssh.BadHostKeyError):
        return {
            "ip":             ip,
            "hostname":       hostname,
            "port":           22,
            "protocol":       "ssh",
            "service":        "ssh",
            "version":        "",
            "severity":       "info",
            "category":       "parches",
            "title":          "Credenciales SSH no válidas",
            "description":    f"No se pudo conectar a {ip} con las credenciales configuradas.",
            "recommendation": "Verificar usuario y contraseña en Tracker → Credenciales.",
        }
    except (OSError, asyncio.TimeoutError, asyncssh.Error):
        return None  # equipo apagado u offline — sin hallazgo


async def _run_patch_audit(live_ips: set, scan_id: int) -> list[dict]:
    """
    Corre auditoría de parches en paralelo (máx 5 simultáneos).
    Retorna lista de hallazgos.
    """
    assets = await asyncio.to_thread(_get_patchable_assets, live_ips)
    if not assets:
        logger.info("Auditoría de parches: sin activos con credenciales para auditar")
        return []

    logger.info("Auditoría de parches: %d equipos a verificar", len(assets))
    sem = asyncio.Semaphore(5)

    async def _bounded(asset):
        async with sem:
            try:
                return await _patch_check_single(asset)
            except Exception as e:
                logger.debug("_patch_check_single %s error: %s", asset["ip"], e)
                return None

    results = await asyncio.gather(*[_bounded(a) for a in assets])
    findings = [r for r in results if r is not None]
    logger.info("Auditoría de parches: %d hallazgos encontrados", len(findings))
    return findings


def _extract_live_ips(xml_str: str) -> set:
    """Extrae el conjunto de IPs que respondieron en el XML de nmap."""
    ips = set()
    try:
        root = ET.fromstring(xml_str)
        for host in root.findall("host"):
            addr_el = host.find("address[@addrtype='ipv4']")
            if addr_el is not None:
                ip = addr_el.get("addr", "")
                if ip:
                    ips.add(ip)
    except Exception:
        pass
    return ips


# ──────────────────────────────────────────────
# Background scan task
# ──────────────────────────────────────────────

async def _do_scan(scan_id: int, triggered_by: str = "manual"):
    global _scan_running
    _scan_running = True
    started = datetime.now(timezone.utc).isoformat()
    try:
        ips = await asyncio.to_thread(_get_asset_ips)
        if not ips:
            with get_db() as conn:
                conn.execute(
                    "UPDATE network_audit_scans SET status='completed', finished_at=datetime('now'), "
                    "total_hosts=0, findings_count=0, error_msg='No hay activos en Tracker' WHERE id=?",
                    (scan_id,)
                )
                conn.commit()
            return

        logger.info("Auditoría de red: escaneo de %d hosts (scan_id=%d)", len(ips), scan_id)
        hostname_map = await asyncio.to_thread(_get_asset_ip_map)
        xml_out = await asyncio.to_thread(_run_nmap, ips)

        if not xml_out:
            with get_db() as conn:
                conn.execute(
                    "UPDATE network_audit_scans SET status='failed', finished_at=datetime('now'), "
                    "error_msg='nmap no retornó resultados' WHERE id=?",
                    (scan_id,)
                )
                conn.commit()
            return

        # 1. Hallazgos nmap (puertos abiertos / servicios inseguros)
        findings = await asyncio.to_thread(_parse_nmap_xml, xml_out)
        await asyncio.to_thread(_save_findings, scan_id, findings, hostname_map)

        # 2. Auditoría de parches SSH/WMI — solo en equipos que respondieron al nmap
        live_ips = await asyncio.to_thread(_extract_live_ips, xml_out)
        patch_findings = await _run_patch_audit(live_ips, scan_id)
        if patch_findings:
            await asyncio.to_thread(_save_findings, scan_id, patch_findings, hostname_map)

        total_findings = len(findings) + len(patch_findings)

        with get_db() as conn:
            conn.execute(
                "UPDATE network_audit_scans SET status='completed', finished_at=datetime('now'), "
                "total_hosts=?, findings_count=? WHERE id=?",
                (len(ips), total_findings, scan_id)
            )
            conn.commit()

        logger.info(
            "Auditoría completada: %d hallazgos nmap + %d parches en %d hosts (%d vivos)",
            len(findings), len(patch_findings), len(ips), len(live_ips)
        )

    except Exception as e:
        logger.error("Error en scan_id=%d: %s", scan_id, e)
        with get_db() as conn:
            conn.execute(
                "UPDATE network_audit_scans SET status='failed', finished_at=datetime('now'), "
                "error_msg=? WHERE id=?",
                (str(e)[:500], scan_id)
            )
            conn.commit()
    finally:
        _scan_running = False


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.post("/audit/network/scan")
async def start_network_scan(user=Depends(get_current_user)):
    """Inicia escaneo nmap sobre activos del Tracker (background). Solo uno a la vez."""
    global _scan_running
    _init_tables()

    if _scan_running:
        # Return current scan status
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, status, started_at FROM network_audit_scans WHERE status='running' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return {"success": False, "error": "Ya hay un escaneo en progreso", "scan_id": row["id"] if row else None}

    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO network_audit_scans (started_at, status, triggered_by) VALUES (datetime('now'),'running',?)",
            (user.get("username", "manual"),)
        )
        scan_id = cur.lastrowid
        conn.commit()

    asyncio.create_task(_do_scan(scan_id, user.get("username", "manual")))
    return {"success": True, "scan_id": scan_id, "message": "Escaneo iniciado"}


@router.get("/audit/network/status")
async def get_scan_status(user=Depends(get_current_user)):
    """Estado del escaneo más reciente."""
    _init_tables()
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, started_at, finished_at, status, total_hosts, findings_count, error_msg "
            "FROM network_audit_scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return {"success": True, "scan": None, "running": False}
    return {
        "success": True,
        "running": _scan_running,
        "scan": dict(row),
    }


@router.get("/audit/network/findings")
async def get_findings(
    severity: Optional[str] = None,
    finding_status: Optional[str] = None,
    ip: Optional[str] = None,
    user=Depends(get_current_user),
):
    """Lista de hallazgos con filtros opcionales."""
    _init_tables()
    filters = []
    params = []
    if severity:
        filters.append("severity = ?")
        params.append(severity)
    if finding_status:
        filters.append("finding_status = ?")
        params.append(finding_status)
    if ip:
        filters.append("ip = ?")
        params.append(ip)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM network_audit_findings {where} ORDER BY "
            "CASE severity WHEN 'critico' THEN 1 WHEN 'alto' THEN 2 WHEN 'medio' THEN 3 "
            "WHEN 'bajo' THEN 4 ELSE 5 END, ip, port",
            params
        ).fetchall()
    return {"success": True, "count": len(rows), "findings": [dict(r) for r in rows]}


@router.patch("/audit/network/findings/{finding_id}")
async def update_finding(finding_id: int, body: dict, user=Depends(get_current_user)):
    """Actualiza estado y/o notas de un hallazgo."""
    _init_tables()
    allowed_statuses = {"pendiente", "en_revision", "terminado"}
    updates = []
    params = []

    new_status = body.get("finding_status")
    if new_status:
        if new_status not in allowed_statuses:
            raise HTTPException(400, f"Estado inválido. Usar: {allowed_statuses}")
        updates.append("finding_status = ?")
        params.append(new_status)

    notes = body.get("notes")
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes[:1000])

    if not updates:
        raise HTTPException(400, "Nada que actualizar")

    updates.append("updated_at = datetime('now')")
    params.append(finding_id)

    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE network_audit_findings SET {', '.join(updates)} WHERE id = ?", params
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Hallazgo no encontrado")

    return {"success": True}


@router.delete("/audit/network/findings/{finding_id}")
async def delete_finding(finding_id: int, user=Depends(require_admin)):
    """Elimina un hallazgo (solo admin)."""
    _init_tables()
    with get_db() as conn:
        conn.execute("DELETE FROM network_audit_findings WHERE id = ?", (finding_id,))
        conn.commit()
    return {"success": True}


@router.get("/audit/network/summary")
async def get_summary(user=Depends(get_current_user)):
    """Resumen de hallazgos activos (para badges en Inframonitor y Hunter)."""
    _init_tables()
    with get_db() as conn:
        # Por severidad (no terminados)
        by_severity = conn.execute(
            "SELECT severity, COUNT(*) as cnt FROM network_audit_findings "
            "WHERE finding_status != 'terminado' GROUP BY severity"
        ).fetchall()
        # Por estado
        by_status = conn.execute(
            "SELECT finding_status, COUNT(*) as cnt FROM network_audit_findings GROUP BY finding_status"
        ).fetchall()
        # Por IP (para badges en Inframonitor)
        by_ip = conn.execute(
            "SELECT ip, severity, COUNT(*) as cnt FROM network_audit_findings "
            "WHERE finding_status != 'terminado' GROUP BY ip, severity"
        ).fetchall()
        # Último escaneo
        last_scan = conn.execute(
            "SELECT started_at, status, findings_count FROM network_audit_scans ORDER BY id DESC LIMIT 1"
        ).fetchone()

    severity_counts = {r["severity"]: r["cnt"] for r in by_severity}
    status_counts = {r["finding_status"]: r["cnt"] for r in by_status}

    # Build per-IP summary: {ip: {critico:N, alto:N, medio:N, bajo:N, info:N, total:N}}
    ip_summary: dict = {}
    for r in by_ip:
        ip = r["ip"]
        if ip not in ip_summary:
            ip_summary[ip] = {"critico": 0, "alto": 0, "medio": 0, "bajo": 0, "info": 0, "total": 0}
        ip_summary[ip][r["severity"]] = ip_summary[ip].get(r["severity"], 0) + r["cnt"]
        ip_summary[ip]["total"] += r["cnt"]

    return {
        "success": True,
        "by_severity": severity_counts,
        "by_status": status_counts,
        "by_ip": ip_summary,
        "last_scan": dict(last_scan) if last_scan else None,
        "total_active": sum(severity_counts.values()),
    }
