from fastapi import APIRouter, HTTPException, Body, BackgroundTasks
from datetime import datetime, timedelta
import sys
import os
import subprocess

# Asegurar que backend y scripts estén en el path para encontrar reboot_glinet.py
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.join(_BACKEND_DIR, "scripts")
for _p in (_SCRIPTS_DIR, _BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from reboot_glinet import reboot_glinet
from reboot_playwright import reboot_tplink, reboot_netgear
from app.backend.db import get_connection

SSHPASS_PATH = "/usr/bin/sshpass"
SSH_PATH = "/usr/bin/ssh"
TEST_ROUTE_TIMEOUT_SEC = 15

router = APIRouter(prefix="/api/devices", tags=["reboot"])

def now(): return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def log_event(cur, device_id: int, etype: str, desc: str, severity: str = "info"):
    cur.execute(
        "INSERT INTO events_log (device_id, event_type, description, severity, created_at) VALUES (?, ?, ?, ?, ?)",
        (device_id, etype, desc, severity, now())
    )

@router.patch("/{device_id}/credentials")
async def set_credentials(device_id: int, payload: dict = Body(...)):
    allowed = {"ssh_user","ssh_password","ssh_port","reboot_method","reboot_command","reboot_cooldown_seconds"}
    fields = {k: v for k, v in (payload or {}).items() if k in allowed}
    if not fields:
        raise HTTPException(status_code=400, detail="No hay campos válidos")
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM devices WHERE id=?", (device_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
        sets = ", ".join([f"{k}=?" for k in fields.keys()])
        cur.execute(f"UPDATE devices SET {sets} WHERE id=?", (*fields.values(), device_id))
        conn.commit()
    return {"success": True, "updated": list(fields.keys())}

def do_reboot_job(device_id: int) -> None:
    print(f"[do_reboot_job] Inicio para device_id={device_id}")
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT id,name,ip_address,ssh_user,ssh_password,
                                  reboot_method,reboot_cooldown_seconds,last_reboot_at
                           FROM devices WHERE id=?""", (device_id,))
            d = cur.fetchone()

            method_check = (d["reboot_method"] or "").lower() if d else ""
            if method_check == "ssh_glinet":
                print(f"[do_reboot_job] method=ssh_glinet: llamando a reboot_glinet(device_id={device_id})")
                log_event(cur, device_id, "device_reboot_requested", "Reinicio GL.iNet vía SSH", "info")
                try:
                    ok, info = reboot_glinet(device_id=device_id)
                    print(f"[do_reboot_job] reboot_glinet() -> ok={ok}, info={info!r}")
                    if ok:
                        cur.execute("UPDATE devices SET last_reboot_at=? WHERE id=?", (now(), device_id))
                        log_event(cur, device_id, "device_reboot_success", f"OK: {info}", "info")
                    else:
                        log_event(cur, device_id, "device_reboot_failed", f"Error: {info}", "error")
                except Exception as e:
                    error_msg = str(e) if e else "Error desconocido en reboot_glinet"
                    log_event(cur, device_id, "device_reboot_failed", f"Excepción: {error_msg}", "error")
                conn.commit()
                return

            if not d:
                return

            name = d["name"] or f"Device-{device_id}"
            ip = d["ip_address"]
            user = d["ssh_user"]
            pwd = d["ssh_password"]
            method = (d["reboot_method"] or "").lower()
            cooldown = d["reboot_cooldown_seconds"] or 300

            if d["last_reboot_at"]:
                try:
                    last = datetime.strptime(d["last_reboot_at"], "%Y-%m-%d %H:%M:%S")
                    if datetime.utcnow() - last < timedelta(seconds=cooldown):
                        log_event(cur, device_id, "device_reboot_denied", f"Cooldown {cooldown}s para {name}", "warning")
                        conn.commit()
                        return
                except Exception:
                    pass

            if not (ip and user and pwd):
                log_event(cur, device_id, "device_reboot_denied", f"Faltan credenciales para {name}", "warning")
                conn.commit()
                return

            log_event(cur, device_id, "device_reboot_requested", f"Reinicio {name} ({ip}) vía {method}", "info")

            ok, info = False, "unknown_method"
            try:
                if method == "http_tplink":
                    ok, info = reboot_tplink(ip, user, pwd)
                elif method == "http_netgear":
                    ok, info = reboot_netgear(ip, user, pwd)
                else:
                    log_event(cur, device_id, "device_reboot_denied", f"Método no soportado: {method}", "warning")
                    conn.commit()
                    return
            except Exception as e:
                error_msg = str(e) if e else "Error desconocido en método de reinicio"
                log_event(cur, device_id, "device_reboot_failed", f"Excepción: {error_msg}", "error")
                conn.commit()
                return

            if ok:
                cur.execute("UPDATE devices SET last_reboot_at=? WHERE id=?", (now(), device_id))
                log_event(cur, device_id, "device_reboot_success", f"Reinicio OK: {info}", "info")
            else:
                log_event(cur, device_id, "device_reboot_failed", f"Fallo: {info}", "error")
            conn.commit()
    except Exception as e:
        print(f"[do_reboot_job] Error crítico: {e}")

def _run_ping_from_gl(target_ip: str) -> tuple[bool, str]:
    """SSH al router principal y ejecuta ping -c 1 -W 2 <target_ip>. Devuelve (éxito, mensaje)."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT ip_address, ssh_user, ssh_password, ssh_port FROM devices "
            "WHERE is_active=1 AND ssh_user IS NOT NULL ORDER BY id LIMIT 1"
        )
        row = cur.fetchone()
    if not row or not row["ip_address"] or not row["ssh_user"] or not row["ssh_password"]:
        return False, "GL no encontrado o sin credenciales SSH en la BD"
    host = row["ip_address"]
    user = row["ssh_user"]
    pwd = row["ssh_password"]
    port = row["ssh_port"] if row["ssh_port"] is not None else 22
    cmd = [
        SSHPASS_PATH, "-p", pwd,
        SSH_PATH,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=5",
        "-p", str(port),
        f"{user}@{host}",
        f"ping -c 1 -W 2 {target_ip}",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TEST_ROUTE_TIMEOUT_SEC)
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode == 0:
            return True, f"El GL (.210) llega a {target_ip}. Salida: {out or 'OK'}"
        return False, f"El GL no respondió ping a {target_ip}. Código: {proc.returncode}. {err or out}"
    except subprocess.TimeoutExpired:
        return False, "Timeout en la conexión SSH al GL"
    except FileNotFoundError:
        return False, "sshpass o ssh no encontrado en el servidor"
    except Exception as e:
        return False, str(e)


@router.post("/{device_id}/test-route")
async def test_route(device_id: int, payload: dict = Body(default=None)):
    """Ejecuta un ping desde el router principal hacia target_ip. Útil si el Mini PC no llega pero el router sí."""
    # Verificar que el device_id corresponde a un dispositivo con SSH habilitado
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM devices WHERE id=? AND ssh_user IS NOT NULL", (device_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail="Testear ruta requiere un dispositivo con SSH configurado")
    target_ip = (payload or {}).get("target_ip") or ""
    target_ip = target_ip.strip()
    if not target_ip:
        raise HTTPException(status_code=400, detail="Falta target_ip (ej: 192.168.1.20)")
    ok, msg = _run_ping_from_gl(target_ip)
    return {"success": ok, "message": msg, "target_ip": target_ip}


@router.post("/{device_id}/reboot")
async def reboot_device(device_id: int, bg: BackgroundTasks):
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM devices WHERE id=?", (device_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
        bg.add_task(do_reboot_job, device_id)
        return {
            "success": True,
            "message": "Reinicio solicitado",
            "device_id": device_id
        }
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e) if e else "Error desconocido"
        raise HTTPException(
            status_code=500,
            detail=f"Error al programar el reinicio: {error_msg}"
        )
