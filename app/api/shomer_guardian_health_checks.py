"""Guardian — health checks extendidos (DNS, HTTP 204, métricas ping).

Todas las funciones de esta módulo son **síncronas y bloqueantes** (subprocess,
SSH, SNMP). El poller Guardian las invoca exclusivamente vía
``asyncio.to_thread()`` con semáforos (``HC_SEM`` / ``SSH_SEM`` / ``SNMP_SEM``)
para no bloquear el event loop ni ``/health``.

Cumple §0: todos los umbrales y toggles se leen de `system_state` vía
`get_config(...)`; los defaults vienen de variables de entorno, nunca
literales de red.

Expuesto:
    - `_get_health_config()`          → dict con toggles y umbrales
    - `_ping_metrics(ip)`             → (ok, loss_pct, rtt_avg)
    - `_ssh_health_probes(...)`       → dict con ping/dns/http/connected
    - `_snmp_health_probes(...)`      → dict con snmp_ok/radio_24/radio_5/connected
    - `classify_health(...)`          → "online" | "degraded" | "no-internet" | "offline"
    - `classify_snmp_health(...)`     → igual, para dispositivos SNMP-only
    - `DEGRADED_NOTIFY_KEY_PREFIX`    → clave Redis para anti-spam Telegram
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import Any, Dict, Optional, Tuple

from app.api.shomer_common import get_config

logger = logging.getLogger(__name__)

DEGRADED_NOTIFY_KEY_PREFIX = "degraded_notified:"
DEGRADED_STREAK_KEY_PREFIX = "degraded_streak:"

_PING_COUNT_DEFAULT = int(os.environ.get("SHOMER_PING_COUNT", "3"))
_PING_LOSS_DEGRADED_PCT = int(os.environ.get("SHOMER_PING_LOSS_DEGRADED_PCT", "60"))
_PING_RTT_DEGRADED_MS = int(os.environ.get("SHOMER_PING_RTT_DEGRADED_MS", "400"))
_DEGRADED_PERSIST_TICKS = int(os.environ.get("SHOMER_DEGRADED_PERSIST_TICKS", "3"))
_DEGRADED_ALERT_COOLDOWN_SEC = int(os.environ.get("SHOMER_DEGRADED_ALERT_COOLDOWN_SEC", "1800"))
_HTTP_PROBE_URL = os.environ.get(
    "SHOMER_HTTP_PROBE_URL", "http://connectivitycheck.gstatic.com/generate_204"
)
_HTTP_PROBE_EXPECT = os.environ.get("SHOMER_HTTP_PROBE_EXPECT", "204")
_DNS_PROBE_HOST = os.environ.get("SHOMER_DNS_PROBE_HOST", "google.com")
_DNS_PROBE_SERVER = os.environ.get("SHOMER_DNS_PROBE_SERVER", "8.8.8.8")

_LOSS_RE = re.compile(r"(\d+(?:\.\d+)?)%\s*packet loss", re.IGNORECASE)
_RTT_RE = re.compile(r"=\s*[\d.]+/([\d.]+)/")


def _get_health_config() -> Dict[str, Any]:
    """Lee toggles y umbrales desde BD con fallback a env/constantes."""
    def _cfg_bool(key: str, default: bool) -> bool:
        v = get_config(key)
        if v is None or v == "":
            return default
        return v in (True, 1, "1", "true", "True", "yes")

    def _cfg_int(key: str, default: int) -> int:
        try:
            v = get_config(key)
            if v is None or v == "":
                return default
            return int(v)
        except Exception:
            return default

    def _cfg_str(key: str, default: str) -> str:
        v = get_config(key)
        if not v:
            return default
        return str(v)

    return {
        "check_dns": _cfg_bool("guardian.check_dns_enabled", True),
        "check_http": _cfg_bool("guardian.check_http_enabled", True),
        "check_latency": _cfg_bool("guardian.check_latency_enabled", True),
        "ping_count": _cfg_int("guardian.ping_count", _PING_COUNT_DEFAULT),
        "loss_degraded_pct": _cfg_int(
            "guardian.ping_loss_degraded_pct", _PING_LOSS_DEGRADED_PCT
        ),
        "rtt_degraded_ms": _cfg_int(
            "guardian.ping_rtt_degraded_ms", _PING_RTT_DEGRADED_MS
        ),
            "degraded_persist_ticks": _cfg_int(
                "guardian.degraded_persist_ticks", _DEGRADED_PERSIST_TICKS
            ),
            "degraded_alert_cooldown_sec": _cfg_int(
                "guardian.degraded_alert_cooldown_sec", _DEGRADED_ALERT_COOLDOWN_SEC
            ),
        "http_probe_url": _cfg_str("guardian.http_probe_url", _HTTP_PROBE_URL),
        "http_probe_expect": _cfg_str("guardian.http_probe_expect", _HTTP_PROBE_EXPECT),
        "dns_probe_host": _cfg_str("guardian.dns_probe_host", _DNS_PROBE_HOST),
        "dns_probe_server": _cfg_str("guardian.dns_probe_server", _DNS_PROBE_SERVER),
    }


def _ping_metrics(ip: str, count: int = 3) -> Tuple[bool, float, Optional[float]]:
    """Ping con N paquetes. Devuelve (ok, loss_pct, rtt_avg_ms).

    - `ok`: al menos un paquete recibido (no 100% loss).
    - `loss_pct`: porcentaje de pérdida [0-100]. 100.0 si subprocess falla.
    - `rtt_avg_ms`: rtt medio; None si no hay métricas.
    """
    timeout = max(count * 2 + 2, 5)
    try:
        r = subprocess.run(
            ["ping", "-c", str(count), "-W", "2", "-i", "0.3", ip],
            capture_output=True, text=True, timeout=timeout,
        )
        out = (r.stdout or "") + (r.stderr or "")
        m_loss = _LOSS_RE.search(out)
        loss = float(m_loss.group(1)) if m_loss else 100.0
        m_rtt = _RTT_RE.search(out)
        rtt = float(m_rtt.group(1)) if m_rtt else None
        return (loss < 100.0, loss, rtt)
    except Exception:
        return (False, 100.0, None)


def _ssh_cmd_base(
    ssh_user: str, ssh_port: int, ip: str, ssh_password: str, payload: str
) -> Optional[subprocess.CompletedProcess]:
    """Ejecuta un comando por SSH (llave primero, password fallback)."""
    from app.api.shomer_guardian_lib import SSH_KEY_PATH

    cmd_suffix = [
        "-o", "ConnectTimeout=5",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "HostKeyAlgorithms=+ssh-rsa,ssh-dss,ecdsa-sha2-nistp256,ssh-ed25519",
        "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa,ssh-dss",
        "-o", "KexAlgorithms=+diffie-hellman-group14-sha1,diffie-hellman-group14-sha256,diffie-hellman-group1-sha1",
        "-p", str(ssh_port),
        f"{ssh_user}@{ip}",
        payload,
    ]
    if os.path.isfile(SSH_KEY_PATH):
        try:
            r = subprocess.run(
                ["/usr/bin/ssh", "-i", SSH_KEY_PATH, "-o", "BatchMode=yes"] + cmd_suffix,
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode in (0, 1):
                return r
        except Exception:
            pass
    sshpass = subprocess.run(
        ["which", "sshpass"], capture_output=True, text=True
    ).stdout.strip()
    if sshpass and ssh_password:
        try:
            r = subprocess.run(
                [sshpass, "-p", ssh_password, "/usr/bin/ssh"] + cmd_suffix,
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode in (0, 1):
                return r
        except Exception:
            pass
    return None


def _ssh_health_probes(
    ip: str, ssh_user: str, ssh_port: int, ssh_password: str, cfg: Dict[str, Any]
) -> Dict[str, Optional[bool]]:
    """Ejecuta ping/DNS/HTTP dentro del AP vía **una sola** sesión SSH.

    Devuelve:
        {
            "connected": bool,  # si logramos ejecutar algo por SSH
            "ping":      True/False/None,
            "dns":       True/False/None,   # None si disabled
            "http":      True/False/None,   # None si disabled
        }
    """
    parts = [
        "P=$(ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1 && echo 1 || echo 0)",
    ]
    if cfg["check_dns"]:
        parts.append(
            "D=$(nslookup {host} {srv} 2>/dev/null | grep -E '^Address.*:.*\\.' "
            "| grep -v '#' >/dev/null && echo 1 || echo 0)".format(
                host=cfg["dns_probe_host"], srv=cfg["dns_probe_server"]
            )
        )
    else:
        parts.append("D=-")
    if cfg["check_http"]:
        parts.append(
            "H=$(curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 '{url}' "
            "2>/dev/null | grep -q '^{code}$' && echo 1 || echo 0)".format(
                url=cfg["http_probe_url"], code=cfg["http_probe_expect"]
            )
        )
    else:
        parts.append("H=-")
    parts.append("echo \"ping=$P dns=$D http=$H\"")
    payload = "; ".join(parts)

    r = _ssh_cmd_base(ssh_user, ssh_port, ip, ssh_password, payload)
    if r is None:
        return {"connected": False, "ping": None, "dns": None, "http": None}

    out = (r.stdout or "").strip()
    kv: Dict[str, str] = {}
    for tok in out.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            kv[k] = v

    def _tri(v: Optional[str]) -> Optional[bool]:
        if v == "1":
            return True
        if v == "0":
            return False
        return None

    return {
        "connected": True,
        "ping": _tri(kv.get("ping")),
        "dns": _tri(kv.get("dns")) if cfg["check_dns"] else None,
        "http": _tri(kv.get("http")) if cfg["check_http"] else None,
    }


def classify_health(
    lan_ok: bool,
    lan_loss_pct: float,
    lan_rtt_ms: Optional[float],
    is_router: bool,
    ssh_result: Optional[Dict[str, Optional[bool]]],
    cfg: Dict[str, Any],
) -> Tuple[str, str]:
    """Deriva status_label y razón humana.

    Reglas de prioridad:
      1. LAN down total (100% loss)                 → offline   [reboot]
      2. Router SSH conectado + ping 8.8.8.8 falla  → no-internet [reboot]
      3. DNS o HTTP fallan, o pérdida/latencia alta → degraded  [sólo avisa]
      4. Resto                                      → online
    """
    if not lan_ok:
        return "offline", "sin respuesta LAN"

    if is_router and ssh_result is not None and ssh_result.get("connected"):
        if ssh_result.get("ping") is False:
            return "no-internet", "ping 8.8.8.8 desde el AP falla"

        bad_signals = []
        if cfg["check_dns"] and ssh_result.get("dns") is False:
            bad_signals.append(f"DNS ({cfg['dns_probe_host']}) no resuelve")
        if cfg["check_http"] and ssh_result.get("http") is False:
            bad_signals.append(
                f"HTTP probe ({cfg['http_probe_expect']}) falla"
            )
        if cfg["check_latency"]:
            if lan_loss_pct >= cfg["loss_degraded_pct"]:
                bad_signals.append(f"pérdida LAN {lan_loss_pct:.0f}%")
            if (
                lan_rtt_ms is not None
                and lan_rtt_ms >= cfg["rtt_degraded_ms"]
            ):
                bad_signals.append(f"rtt LAN {lan_rtt_ms:.0f}ms")

        if bad_signals:
            return "degraded", ", ".join(bad_signals)

        return "online", "ok"

    if cfg["check_latency"]:
        if lan_loss_pct >= cfg["loss_degraded_pct"]:
            return "degraded", f"pérdida LAN {lan_loss_pct:.0f}%"
        if lan_rtt_ms is not None and lan_rtt_ms >= cfg["rtt_degraded_ms"]:
            return "degraded", f"rtt LAN {lan_rtt_ms:.0f}ms"

    return "online", "ok"


def _snmp_health_probes(ip: str, community: str, timeout: int = 8) -> Dict[str, Any]:
    """Probe SNMP para APs sin permisos SSH (EAP, Omada, etc.).

    Chequea:
      1. Conectividad SNMP via uptime OID — detecta AP colgado
      2. Estado radios wifi (ifOperStatus) — detecta radio crasheado

    Retorna:
        connected  : bool  — SNMP respondió
        snmp_ok    : bool  — uptime OID válido
        radio_24   : bool|None — radio 2.4GHz up (None si no detectado)
        radio_5    : bool|None — radio 5GHz up (None si no detectado)
    """
    import shutil
    snmpget_bin = shutil.which("snmpget")
    snmpwalk_bin = shutil.which("snmpwalk")

    if not snmpget_bin:
        return {"connected": False, "snmp_ok": False, "radio_24": None, "radio_5": None}

    # 1. Uptime — test básico de conectividad SNMP
    try:
        r = subprocess.run(
            [snmpget_bin, "-v2c", "-c", community, "-t", str(timeout), "-r", "1",
             ip, "1.3.6.1.2.1.1.3.0"],
            capture_output=True, text=True, timeout=timeout + 3,
        )
        snmp_ok = r.returncode == 0 and "Timeticks" in r.stdout
    except Exception:
        snmp_ok = False

    if not snmp_ok:
        return {"connected": False, "snmp_ok": False, "radio_24": None, "radio_5": None}

    # 2. Estado radios via ifDescr + ifOperStatus
    radio_24: Optional[bool] = None
    radio_5: Optional[bool] = None

    if snmpwalk_bin:
        try:
            r_descr = subprocess.run(
                [snmpwalk_bin, "-v2c", "-c", community, "-t", str(timeout), "-r", "1",
                 ip, "1.3.6.1.2.1.2.2.1.2"],
                capture_output=True, text=True, timeout=timeout + 5,
            )
            r_oper = subprocess.run(
                [snmpwalk_bin, "-v2c", "-c", community, "-t", str(timeout), "-r", "1",
                 ip, "1.3.6.1.2.1.2.2.1.8"],
                capture_output=True, text=True, timeout=timeout + 5,
            )
            # idx → nombre de interfaz
            idx_name: Dict[str, str] = {}
            for line in r_descr.stdout.splitlines():
                if "STRING:" in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        idx = parts[0].rsplit(".", 1)[-1]
                        idx_name[idx] = parts[-1].strip('"').lower()

            # idx → ifOperStatus (1=up, 2=down)
            idx_status: Dict[str, str] = {}
            for line in r_oper.stdout.splitlines():
                if "INTEGER:" in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        idx = parts[0].rsplit(".", 1)[-1]
                        idx_status[idx] = parts[-1]

            _24_names = {"wifi0", "wlan0", "ath0", "radio0", "wl0", "ra0"}
            _5_names  = {"wifi1", "wlan1", "ath1", "ath10", "radio1", "wl1", "rax0", "rai0"}
            for idx, name in idx_name.items():
                st = idx_status.get(idx)
                if name in _24_names and radio_24 is None:
                    radio_24 = (st == "1")
                elif name in _5_names and radio_5 is None:
                    radio_5 = (st == "1")
        except Exception:
            pass

    return {"connected": True, "snmp_ok": True, "radio_24": radio_24, "radio_5": radio_5}


def classify_snmp_health(
    lan_ok: bool,
    lan_loss_pct: float,
    lan_rtt_ms: Optional[float],
    snmp_result: Optional[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> Tuple[str, str]:
    """Clasifica estado para dispositivos SNMP-only (EAP, Omada, etc.).

    Mapeo a estados Guardian estándar:
      offline      — ICMP falla (AP sin LAN)
      no-internet  — SNMP sin respuesta (AP colgado) O radio caído
      online       — todo ok
    Radio caído se mapea a no-internet (no degraded) para que el failsafe
    pueda reiniciar tras threshold — un radio crasheado necesita reboot.
    """
    if not lan_ok:
        return "offline", "sin respuesta LAN"

    if snmp_result is None:
        return "online", "solo ICMP (SNMP no configurado)"

    if not snmp_result.get("connected"):
        return "no-internet", "SNMP sin respuesta — AP posiblemente colgado"

    bad: list = []
    if snmp_result.get("radio_24") is False:
        bad.append("radio 2.4GHz caído")
    if snmp_result.get("radio_5") is False:
        bad.append("radio 5GHz caído")
    if bad:
        return "no-internet", ", ".join(bad)

    if cfg.get("check_latency"):
        if lan_loss_pct >= cfg["loss_degraded_pct"]:
            return "degraded", f"pérdida LAN {lan_loss_pct:.0f}%"
        if lan_rtt_ms is not None and lan_rtt_ms >= cfg["rtt_degraded_ms"]:
            return "degraded", f"rtt LAN {lan_rtt_ms:.0f}ms"

    return "online", "ok"
