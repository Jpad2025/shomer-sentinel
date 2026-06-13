"""SSH firewall para bloqueo Hunter — soporta OpenWrt/Linux (iptables) y MikroTik RouterOS."""
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


# ── MikroTik RouterOS (address-list) ──────────────────────────────────────────
# Requiere que exista en el MikroTik una regla DROP sobre la lista "shomer-blocked":
#   /ip firewall filter add chain=forward src-address-list=shomer-blocked action=drop place-before=0 comment="Shomer-Hunter"

_ROS_LIST = "shomer-blocked"


async def _connect_routeros(creds: dict):
    """Contexto asyncssh con opciones compatibles con RouterOS."""
    return asyncssh.connect(
        creds["ip"],
        port=creds["port"],
        username=creds["user"],
        password=creds["pass"],
        known_hosts=None,
        connect_timeout=creds["timeout"],
        # RouterOS puede requerir algoritmos legacy de host key;
        # encryption/mac usan los defaults modernos de asyncssh (no existen
        # asyncssh.encryption_algs / mac_algs como atributos del módulo)
        server_host_key_algs=["ssh-rsa", "ecdsa-sha2-nistp256", "ssh-ed25519"],
    )


async def _routeros_block(ip: str) -> tuple[bool, str]:
    creds = _get_firewall_creds()
    if not creds["ip"]:
        return False, "IP del firewall no configurada"
    if not creds["user"]:
        return False, "Usuario del firewall no configurado (hunter.firewall_user)"
    if _cb_is_open():
        return False, "Firewall unreachable — circuito abierto"
    run_timeout = max(2, creds["timeout"] - 2)
    cmd = f'/ip firewall address-list add address={ip} list={_ROS_LIST} comment="Shomer-Hunter"'
    try:
        async with await _connect_routeros(creds) as conn:
            result = await conn.run(cmd, timeout=run_timeout)
            # RouterOS devuelve exit 0 en éxito; en duplicado devuelve error en stderr
            stderr = (result.stderr or "").strip()
            if result.exit_status != 0 and "already" not in stderr.lower():
                opened = _cb_record_failure()
                msg = f"RouterOS error (exit {result.exit_status}): {stderr}"
                if opened:
                    msg += " — CIRCUITO ABIERTO"
                return False, msg
        _cb_record_success()
        return True, f"{ip} bloqueada en MikroTik RouterOS (address-list {_ROS_LIST})"
    except Exception as e:
        opened = _cb_record_failure()
        msg = str(e)
        if opened:
            msg += " — CIRCUITO ABIERTO"
        return False, msg


async def _routeros_sync_block(ip: str) -> tuple[bool, str]:
    """Aplica bloqueo solo si la IP no está ya en la lista — evita duplicados en sync."""
    creds = _get_firewall_creds()
    if not creds["ip"]:
        return False, "IP del firewall no configurada"
    if not creds["user"]:
        return False, "Usuario del firewall no configurado"
    if _cb_is_open():
        return False, "Firewall unreachable — circuito abierto"
    run_timeout = max(2, creds["timeout"] - 2)
    check_cmd = f'/ip firewall address-list print count-only where address="{ip}" list={_ROS_LIST}'
    add_cmd = f'/ip firewall address-list add address={ip} list={_ROS_LIST} comment="Shomer-Hunter"'
    try:
        async with await _connect_routeros(creds) as conn:
            check = await conn.run(check_cmd, timeout=run_timeout)
            count = (check.stdout or "").strip()
            if count == "0" or count == "":
                result = await conn.run(add_cmd, timeout=run_timeout)
                if result.exit_status != 0:
                    err = (result.stderr or "").strip()
                    opened = _cb_record_failure()
                    msg = f"RouterOS sync error: {err}"
                    if opened:
                        msg += " — CIRCUITO ABIERTO"
                    return False, msg
        _cb_record_success()
        return True, f"{ip} sincronizada en MikroTik RouterOS"
    except Exception as e:
        opened = _cb_record_failure()
        msg = str(e)
        if opened:
            msg += " — CIRCUITO ABIERTO"
        return False, msg


async def _routeros_unblock(ip: str) -> tuple[bool, str]:
    creds = _get_firewall_creds()
    if not creds["ip"]:
        return False, "IP del firewall no configurada"
    if not creds["user"]:
        return False, "Usuario del firewall no configurado (hunter.firewall_user)"
    if _cb_is_open():
        return False, "Firewall unreachable — circuito abierto; desbloqueo no aplicado"
    run_timeout = max(2, creds["timeout"] - 2)
    cmd = f'/ip firewall address-list remove [find where address="{ip}" and list={_ROS_LIST}]'
    try:
        async with await _connect_routeros(creds) as conn:
            result = await conn.run(cmd, timeout=run_timeout)
            if result.exit_status != 0:
                err = (result.stderr or "").strip()
                return False, f"RouterOS unblock error (exit {result.exit_status}): {err}"
        _cb_record_success()
        return True, f"{ip} desbloqueada en MikroTik RouterOS"
    except Exception as e:
        _cb_record_failure()
        return False, str(e)


_ROS_DROP_COUNT_CMD = (
    f'/ip firewall filter print count-only where chain=forward action=drop '
    f'src-address-list={_ROS_LIST}'
)
_ROS_DROP_ADD_CMD = (
    f'/ip firewall filter add chain=forward action=drop '
    f'src-address-list={_ROS_LIST} place-before=0 comment="Shomer-Hunter"'
)
_ROS_LIST_COUNT_CMD = f'/ip firewall address-list print count-only where list={_ROS_LIST}'


def _ros_count(stdout: str) -> int:
    raw = (stdout or "").strip()
    if not raw:
        return 0
    try:
        return int(raw.splitlines()[-1].strip())
    except ValueError:
        return 0


async def _routeros_verify_setup() -> dict:
    """
    Comprueba regla DROP en forward y entradas en address-list shomer-blocked.
    La lista sola no bloquea tráfico — hace falta la regla filter.
    """
    creds = _get_firewall_creds()
    if creds.get("type") != "routeros":
        return {
            "success": False,
            "firewall_type": creds.get("type", "openwrt"),
            "message": "Verificación solo aplica con hunter.firewall_type=routeros",
        }
    if not creds["ip"]:
        return {"success": False, "message": "IP del firewall no configurada"}
    if not creds["user"]:
        return {"success": False, "message": "Usuario del firewall no configurado"}
    if _cb_is_open():
        return {"success": False, "circuit_open": True, "message": "Circuit breaker abierto — firewall inalcanzable"}

    run_timeout = max(2, creds["timeout"] - 2)
    try:
        async with await _connect_routeros(creds) as conn:
            drop_r = await conn.run(_ROS_DROP_COUNT_CMD, timeout=run_timeout)
            list_r = await conn.run(_ROS_LIST_COUNT_CMD, timeout=run_timeout)
        drop_count = _ros_count(drop_r.stdout)
        list_count = _ros_count(list_r.stdout)
        drop_ok = drop_count >= 1
        _cb_record_success()
        if drop_ok:
            msg = f"Regla DROP activa ({drop_count}). Lista {_ROS_LIST}: {list_count} IP(s)."
        elif list_count > 0:
            msg = (
                f"Hay {list_count} IP(s) en lista {_ROS_LIST} pero "
                "falta la regla DROP en chain=forward — el bloqueo no es efectivo."
            )
        else:
            msg = f"Lista {_ROS_LIST} vacía y sin regla DROP (normal antes del primer bloqueo)."
        return {
            "success": True,
            "drop_rule_count": drop_count,
            "drop_rule_ok": drop_ok,
            "blocked_list_count": list_count,
            "address_list": _ROS_LIST,
            "message": msg,
        }
    except Exception as e:
        _cb_record_failure()
        return {"success": False, "message": str(e)}


async def _routeros_ensure_drop_rule() -> tuple[bool, str]:
    """Crea la regla DROP idempotente si no existe (place-before=0 en forward)."""
    creds = _get_firewall_creds()
    if creds.get("type") != "routeros":
        return False, "Solo aplica con firewall MikroTik RouterOS"
    if not creds["ip"]:
        return False, "IP del firewall no configurada"
    if not creds["user"]:
        return False, "Usuario del firewall no configurado"
    if _cb_is_open():
        return False, "Firewall unreachable — circuito abierto"

    run_timeout = max(2, creds["timeout"] - 2)
    try:
        async with await _connect_routeros(creds) as conn:
            check = await conn.run(_ROS_DROP_COUNT_CMD, timeout=run_timeout)
            if _ros_count(check.stdout) >= 1:
                _cb_record_success()
                return True, "Regla DROP ya existe en forward — no se modificó nada"
            result = await conn.run(_ROS_DROP_ADD_CMD, timeout=run_timeout)
            if result.exit_status != 0:
                err = (result.stderr or "").strip()
                opened = _cb_record_failure()
                msg = f"RouterOS no pudo crear regla DROP: {err}"
                if opened:
                    msg += " — CIRCUITO ABIERTO"
                return False, msg
        _cb_record_success()
        return True, "Regla DROP creada en forward (src-address-list=shomer-blocked)"
    except Exception as e:
        opened = _cb_record_failure()
        msg = str(e)
        if opened:
            msg += " — CIRCUITO ABIERTO"
        return False, msg
