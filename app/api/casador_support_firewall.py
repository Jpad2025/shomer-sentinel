"""SSH OpenWrt / iptables para bloqueo Hunter."""
import asyncssh

from app.api.casador_support_redis_cb import _cb_is_open, _cb_record_failure, _cb_record_success
from app.api.casador_support_state import _get_firewall_creds


async def _mikrotik_block(ip: str) -> tuple[bool, str]:
    creds = _get_firewall_creds()
    if not creds["ip"]:
        return False, "IP del firewall no configurada"
    if not creds["user"]:
        return False, "Usuario del firewall no configurado en system_state (hunter.firewall_user)"
    if _cb_is_open():
        return False, (
            "Firewall unreachable — circuito abierto (3 fallos consecutivos). "
            "Resetear con POST /remedies/firewall/reset"
        )
    connect_timeout = creds["timeout"]
    run_timeout = max(2, connect_timeout - 2)
    try:
        async with asyncssh.connect(
            creds["ip"],
            port=creds["port"],
            username=creds["user"],
            password=creds["pass"],
            known_hosts=None,
            connect_timeout=connect_timeout,
        ) as conn:
            result = await conn.run(f"iptables -I FORWARD -s {ip} -j DROP", timeout=run_timeout)
            if result.exit_status != 0:
                err = (result.stderr or "").strip()
                opened = _cb_record_failure()
                msg = f"iptables error (exit {result.exit_status}): {err}"
                if opened:
                    msg += " — CIRCUITO ABIERTO: firewall marcado unreachable"
                return False, msg
        _cb_record_success()
        return True, f"{ip} bloqueada en OpenWrt (iptables DROP)"
    except Exception as e:
        opened = _cb_record_failure()
        msg = str(e)
        if opened:
            msg += " — CIRCUITO ABIERTO: firewall marcado unreachable"
        return False, msg


async def _mikrotik_sync_block(ip: str) -> tuple[bool, str]:
    """
    Aplica la regla iptables solo si no existe ya (check-then-insert).
    Usar para sync tras reboot del router — evita duplicados.
    """
    creds = _get_firewall_creds()
    if not creds["ip"]:
        return False, "IP del firewall no configurada"
    if not creds["user"]:
        return False, "Usuario del firewall no configurado"
    if _cb_is_open():
        return False, "Firewall unreachable — circuito abierto"
    connect_timeout = creds["timeout"]
    run_timeout = max(2, connect_timeout - 2)
    try:
        async with asyncssh.connect(
            creds["ip"],
            port=creds["port"],
            username=creds["user"],
            password=creds["pass"],
            known_hosts=None,
            connect_timeout=connect_timeout,
        ) as conn:
            # -C comprueba si la regla ya existe (exit 0) — solo inserta si no está
            cmd = f"iptables -C FORWARD -s {ip} -j DROP 2>/dev/null || iptables -I FORWARD -s {ip} -j DROP"
            result = await conn.run(cmd, timeout=run_timeout)
            if result.exit_status != 0:
                err = (result.stderr or "").strip()
                opened = _cb_record_failure()
                msg = f"iptables sync error (exit {result.exit_status}): {err}"
                if opened:
                    msg += " — CIRCUITO ABIERTO"
                return False, msg
        _cb_record_success()
        return True, f"{ip} sincronizada en OpenWrt (iptables)"
    except Exception as e:
        opened = _cb_record_failure()
        msg = str(e)
        if opened:
            msg += " — CIRCUITO ABIERTO"
        return False, msg


async def _mikrotik_unblock(ip: str) -> tuple[bool, str]:
    creds = _get_firewall_creds()
    if not creds["ip"]:
        return False, "IP del firewall no configurada"
    if not creds["user"]:
        return False, "Usuario del firewall no configurado en system_state (hunter.firewall_user)"
    if _cb_is_open():
        return False, "Firewall unreachable — circuito abierto; desbloqueo no aplicado en red"
    connect_timeout = creds["timeout"]
    run_timeout = max(2, connect_timeout - 2)
    try:
        async with asyncssh.connect(
            creds["ip"],
            port=creds["port"],
            username=creds["user"],
            password=creds["pass"],
            known_hosts=None,
            connect_timeout=connect_timeout,
        ) as conn:
            result = await conn.run(f"iptables -D FORWARD -s {ip} -j DROP", timeout=run_timeout)
            if result.exit_status != 0:
                err = (result.stderr or "").strip()
                return False, f"iptables error (exit {result.exit_status}): {err}"
        _cb_record_success()
        return True, f"{ip} desbloqueada en OpenWrt"
    except Exception as e:
        _cb_record_failure()
        return False, str(e)
