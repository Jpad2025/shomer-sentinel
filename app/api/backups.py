"""
Protector - Módulo Backups. Endpoints en puerto 8000.
Lista snapshots Restic, salud del repositorio, backup local y sincronización a nube.
Cero imports de inventory (8001). Usa solo app.backend.protector.
"""
import asyncio
import os
import zipfile
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.auth_api import require_admin
from app.backend.protector import (
    list_snapshots, repository_health, run_backup_and_prune, get_restic_password,
    RESTIC_REPOSITORY as _PROTO_REPO,
    RESTIC_BINARY as _PROTO_BIN,
)

router = APIRouter(prefix="/backups", tags=["Protector - Backups"])


@router.get("/snapshots")
async def get_snapshots(
    limit: int = 50,
    _admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Lista los últimos snapshots del repositorio Restic con nombre de equipo y stats."""
    snaps = list_snapshots(limit=min(limit, 100))
    # Cruzar tags device_N con nombre real y stats del último backup
    try:
        with _get_db() as conn:
            dev_rows = conn.execute(
                "SELECT id, name, last_files_count, last_size_mb, last_duration_sec, last_snapshot_id, "
                "schedule_enabled, schedule_time "
                "FROM backup_devices"
            ).fetchall()
        dev_map = {str(r["id"]): dict(r) for r in dev_rows}
    except Exception:
        dev_map = {}
    for s in snaps:
        tags = s.get("tags") or []
        s["device_name"] = ""
        s["device_id"]   = None
        s["schedule_enabled"] = False
        s["schedule_time"] = None
        s["last_files"]  = None
        s["last_size_mb"]= None
        s["last_duration_sec"] = None
        for tag in tags:
            if tag.startswith("device_"):
                dev = dev_map.get(tag[7:], {})
                s["device_name"]     = dev.get("name", "")
                s["device_id"]       = dev.get("id")
                s["schedule_enabled"] = bool(dev.get("schedule_enabled"))
                s["schedule_time"]   = dev.get("schedule_time")
                # Solo mostramos stats si este es el último snapshot del equipo
                if s.get("short_id") == dev.get("last_snapshot_id"):
                    s["last_files"]        = dev.get("last_files_count")
                    s["last_size_mb"]      = dev.get("last_size_mb")
                    s["last_duration_sec"] = dev.get("last_duration_sec")
                break
    return {"success": True, "snapshots": snaps, "count": len(snaps)}


@router.get("/health")
async def get_health(_admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    """Estado del repositorio Restic (accesible o error)."""
    h = repository_health()
    return {"success": True, "status": h["status"], "message": h["message"]}


def _run_backup_sync() -> None:
    """Ejecuta backup + prune en segundo plano. No lanza excepciones."""
    try:
        run_backup_and_prune()
    except Exception as e:
        # Evita silencios en fallos del job de background.
        print(f"[protector][run_backup_sync] error: {e}")


@router.post("/run")
async def run_manual_backup(
    background_tasks: BackgroundTasks,
    _admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Dispara un backup manual (Restic) en segundo plano. Responde de inmediato."""
    background_tasks.add_task(_run_backup_sync)
    return {
        "success": True,
        "message": "Backup iniciado en segundo plano. Actualice la tabla de snapshots en 1-2 min.",
    }


@router.post("/run_local")
async def run_local_backup(
    background_tasks: BackgroundTasks,
    _admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Ejecuta el backup local (Restic) en segundo plano. Responde rápido."""
    background_tasks.add_task(_run_backup_sync)
    return {
        "success": True,
        "message": "Backup local iniciado en segundo plano. La tabla se actualizará al terminar.",
    }


@router.post("/sync_cloud")
async def sync_to_cloud_endpoint(
    _admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Sincroniza snapshots al repositorio B2 configurado (restic copy)."""
    cfg        = _get_b2_config()
    account_id  = cfg.get("b2_account_id", "")
    app_key     = cfg.get("b2_app_key", "")
    bucket      = cfg.get("b2_bucket", "")
    b2_password = cfg.get("b2_password") or get_restic_password()
    b2_path     = _effective_b2_path()
    if not (account_id and app_key and bucket):
        return {
            "success": False,
            "message": "Configura B2 primero: bucket, Account ID y Application Key requeridos",
        }
    try:
        result = await asyncio.to_thread(
            _b2_sync_blocking, account_id, app_key, bucket, b2_path, b2_password
        )
        return result
    except Exception as e:
        return {"success": False, "message": "Error en sincronización: %s" % str(e)}


# ── Backup Devices ─────────────────────────────────────────────────────────────

import os
import subprocess
import sqlite3
import tempfile
import base64
import hashlib
import hmac
from datetime import datetime as _dt
from app.backend.db import DB_PATH


def _get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


_ENC_FERNET_PREFIX = "ENCF:"
_ENC_XOR_PREFIX = "ENCX:"

try:
    from cryptography.fernet import Fernet, InvalidToken  # type: ignore
    _HAS_FERNET = True
except Exception:
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore
    _HAS_FERNET = False


def _enc_key_material() -> bytes:
    """
    Clave de cifrado para credenciales de backup.
    Prioridad: BACKUP_CRED_SECRET -> JWT_SECRET -> fallback local.
    """
    secret = (
        os.environ.get("BACKUP_CRED_SECRET", "").strip()
        or os.environ.get("JWT_SECRET", "").strip()
        or "shomer-backup-cred-default-change-me"
    )
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _looks_encrypted(val: str) -> bool:
    return isinstance(val, str) and (val.startswith(_ENC_FERNET_PREFIX) or val.startswith(_ENC_XOR_PREFIX))


def _xor_stream(data: bytes, key: bytes, nonce: bytes) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < len(data):
        block = hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(a ^ b for a, b in zip(data, out[: len(data)]))


def _encrypt_device_password(raw: str) -> str:
    if not raw:
        return ""
    key = _enc_key_material()
    if _HAS_FERNET and Fernet is not None:
        f = Fernet(base64.urlsafe_b64encode(key))
        token = f.encrypt(raw.encode("utf-8")).decode("utf-8")
        return _ENC_FERNET_PREFIX + token
    # Fallback sin dependencia externa: cifrado XOR + HMAC (mejor que texto plano).
    nonce = os.urandom(16)
    cipher = _xor_stream(raw.encode("utf-8"), key, nonce)
    mac = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    payload = base64.urlsafe_b64encode(nonce + mac + cipher).decode("ascii")
    return _ENC_XOR_PREFIX + payload


def _decrypt_device_password(stored: str) -> str:
    if not stored:
        return ""
    if stored.startswith(_ENC_FERNET_PREFIX):
        token = stored[len(_ENC_FERNET_PREFIX) :]
        key = _enc_key_material()
        if not (_HAS_FERNET and Fernet is not None):
            raise ValueError("Credencial cifrada con Fernet, pero cryptography no está disponible")
        try:
            f = Fernet(base64.urlsafe_b64encode(key))
            return f.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as e:
            raise ValueError("No se pudo descifrar contraseña (clave inválida)") from e
    if stored.startswith(_ENC_XOR_PREFIX):
        payload = stored[len(_ENC_XOR_PREFIX) :]
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        if len(raw) < 48:
            raise ValueError("Formato de credencial inválido")
        nonce, mac, cipher = raw[:16], raw[16:48], raw[48:]
        key = _enc_key_material()
        exp = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, exp):
            raise ValueError("No se pudo verificar integridad de credencial")
        return _xor_stream(cipher, key, nonce).decode("utf-8")
    # Legacy: texto plano previo al hardening.
    return stored


def _ensure_backup_devices_table():
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS backup_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                ip TEXT NOT NULL,
                device_type TEXT DEFAULT 'windows',
                username TEXT,
                password TEXT,
                source_path TEXT,
                is_active INTEGER DEFAULT 1,
                schedule_enabled INTEGER DEFAULT 0,
                schedule_time TEXT DEFAULT NULL,
                last_backup_at TEXT,
                last_status TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        # Migración lazy: agregar columnas de scheduler si no existen.
        for col, definition in [
            ("schedule_enabled",    "INTEGER DEFAULT 0"),
            ("schedule_time",       "TEXT DEFAULT NULL"),
            ("schedule_b2_enabled", "INTEGER DEFAULT 0"),
            ("last_files_count",    "INTEGER DEFAULT NULL"),
            ("last_size_mb",        "REAL DEFAULT NULL"),
            ("last_duration_sec",   "INTEGER DEFAULT NULL"),
            ("last_snapshot_id",    "TEXT DEFAULT NULL"),
            ("include_pattern",     "TEXT DEFAULT NULL"),
        ]:
            try:
                conn.execute(f"ALTER TABLE backup_devices ADD COLUMN {col} {definition}")
            except Exception:
                pass
        # Migración lazy: convertir contraseñas legacy en texto plano a cifradas.
        rows = conn.execute(
            "SELECT id, password FROM backup_devices WHERE password IS NOT NULL AND TRIM(password) <> ''"
        ).fetchall()
        for r in rows:
            current = r["password"] or ""
            if _looks_encrypted(current):
                continue
            try:
                enc = _encrypt_device_password(current)
                conn.execute(
                    "UPDATE backup_devices SET password = ? WHERE id = ?",
                    (enc, r["id"]),
                )
            except Exception:
                # No bloquea arranque del módulo por una fila corrupta.
                continue
        conn.commit()


_ensure_backup_devices_table()


@router.get("/devices")
async def list_backup_devices(_admin: Dict[str, Any] = Depends(require_admin)):
    """Lista equipos configurados para backup."""
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, ip, device_type, username, source_path, include_pattern, is_active, "
            "schedule_enabled, schedule_time, schedule_b2_enabled, "
            "last_backup_at, last_status, last_files_count, last_size_mb, last_duration_sec, last_snapshot_id "
            "FROM backup_devices ORDER BY name"
        ).fetchall()
    return {"success": True, "devices": [dict(r) for r in rows]}


@router.get("/devices/{device_id}")
async def get_backup_device(device_id: int, _admin: Dict[str, Any] = Depends(require_admin)):
    """Detalle de un equipo (sin contraseña en claro)."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT id, name, ip, device_type, username, password, source_path, include_pattern, is_active, "
            "schedule_enabled, schedule_time, schedule_b2_enabled, "
            "last_backup_at, last_status, last_files_count, last_size_mb, last_duration_sec, last_snapshot_id "
            "FROM backup_devices WHERE id = ?",
            (device_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    d = dict(row)
    d["has_password"] = bool(d.get("password"))
    del d["password"]
    return {"success": True, "device": d}


def _parse_schedule_time(val) -> str | None:
    """Valida y normaliza HH:MM (hora local del sitio). Devuelve None si está vacío o inválido."""
    if not val:
        return None
    s = str(val).strip()
    import re
    if re.match(r"^\d{1,2}:\d{2}$", s):
        h, m = s.split(":")
        if 0 <= int(h) <= 23 and 0 <= int(m) <= 59:
            return f"{int(h):02d}:{int(m):02d}"
    return None


@router.post("/devices")
async def save_backup_device(
    body: Dict[str, Any] = Body(default={}),
    _admin: Dict[str, Any] = Depends(require_admin),
):
    """Guarda un equipo a respaldar."""
    name             = (body.get("name") or "").strip()
    ip               = (body.get("ip") or "").strip()
    device_type      = body.get("device_type", "windows")
    username         = (body.get("username") or "").strip()
    password         = (body.get("password") or "").strip()
    source_path      = (body.get("source_path") or "").strip()
    include_pattern  = (body.get("include_pattern") or "").strip() or None
    schedule_enabled    = 1 if body.get("schedule_enabled") else 0
    schedule_time       = _parse_schedule_time(body.get("schedule_time"))
    schedule_b2_enabled = 1 if body.get("schedule_b2_enabled") else 0
    if not name or not ip:
        raise HTTPException(status_code=400, detail="nombre e IP requeridos")
    with _get_db() as conn:
        conn.execute(
            "INSERT INTO backup_devices (name, ip, device_type, username, password, source_path, "
            "include_pattern, schedule_enabled, schedule_time, schedule_b2_enabled) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, ip, device_type, username, _encrypt_device_password(password), source_path,
             include_pattern, schedule_enabled, schedule_time, schedule_b2_enabled)
        )
        conn.commit()
    return {"success": True, "message": f"Equipo {name} guardado"}


@router.patch("/devices/{device_id}")
async def update_backup_device(
    device_id: int,
    body: Dict[str, Any] = Body(default={}),
    _admin: Dict[str, Any] = Depends(require_admin),
):
    """Actualiza equipo (ruta, credenciales, etc.). Contraseña vacía o '***' conserva la guardada.

    El SELECT debe traer schedule_enabled/schedule_time/schedule_b2_enabled -- si faltan,
    cualquier PATCH parcial (ej. el botón Activar/Pausar auto, que solo envía
    schedule_enabled) los resetea a 0/NULL porque cur.get(...) cae al default."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT id, name, ip, device_type, username, password, source_path, include_pattern, "
            "schedule_enabled, schedule_time, schedule_b2_enabled FROM backup_devices WHERE id = ?",
            (device_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    cur = dict(row)
    name        = (body.get("name") if body.get("name") is not None else cur["name"]) or ""
    name        = name.strip()
    ip          = (body.get("ip") if body.get("ip") is not None else cur["ip"]) or ""
    ip          = ip.strip()
    device_type = (body.get("device_type") if body.get("device_type") is not None else cur["device_type"]) or "windows"
    username    = (body.get("username") if body.get("username") is not None else cur["username"]) or ""
    username    = username.strip()
    source_path = (body.get("source_path") if body.get("source_path") is not None else cur["source_path"]) or ""
    source_path = source_path.strip()
    if "include_pattern" in body:
        include_pattern = (body.get("include_pattern") or "").strip() or None
    else:
        include_pattern = cur.get("include_pattern")
    pwd_in      = body.get("password")
    if pwd_in is None or (isinstance(pwd_in, str) and (not pwd_in.strip() or pwd_in.strip() == "***")):
        password_val = cur["password"]
    else:
        password_val = _encrypt_device_password(str(pwd_in).strip())
    schedule_enabled = 1 if body.get("schedule_enabled") else (cur.get("schedule_enabled") or 0)
    if "schedule_enabled" in body:
        schedule_enabled = 1 if body["schedule_enabled"] else 0
    if "schedule_time" in body:
        schedule_time = _parse_schedule_time(body["schedule_time"])
    else:
        schedule_time = cur.get("schedule_time")
    if "schedule_b2_enabled" in body:
        schedule_b2_enabled = 1 if body["schedule_b2_enabled"] else 0
    else:
        schedule_b2_enabled = cur.get("schedule_b2_enabled") or 0
    if not name or not ip:
        raise HTTPException(status_code=400, detail="nombre e IP requeridos")
    with _get_db() as conn:
        conn.execute(
            "UPDATE backup_devices SET name=?, ip=?, device_type=?, username=?, password=?, source_path=?, "
            "include_pattern=?, schedule_enabled=?, schedule_time=?, schedule_b2_enabled=? WHERE id=?",
            (name, ip, device_type, username, password_val, source_path, include_pattern,
             schedule_enabled, schedule_time, schedule_b2_enabled, device_id),
        )
        conn.commit()
    return {"success": True, "message": f"Equipo {name} actualizado"}


@router.post("/devices/test")
async def test_backup_device(
    body: Dict[str, Any] = Body(default={}),
    _admin: Dict[str, Any] = Depends(require_admin),
):
    """Prueba conexión a un equipo (SMB o SSH).

    Si la contraseña viene vacía o '***' (el panel no vuelve a mostrarla en
    claro tras guardarla) y se pasa device_id, se usa la contraseña cifrada
    ya guardada en BD para ese equipo en vez de probar con el literal '***'.
    """
    device_id   = body.get("device_id")
    ip          = (body.get("ip") or "").strip()
    device_type = body.get("device_type", "windows")
    username    = (body.get("username") or "").strip()
    password    = (body.get("password") or "").strip()
    source_path = (body.get("source_path") or "").strip()
    if (not password or password == "***") and device_id:
        with _get_db() as conn:
            row = conn.execute(
                "SELECT password FROM backup_devices WHERE id = ?", (device_id,)
            ).fetchone()
        if row and row["password"]:
            try:
                password = _decrypt_device_password(row["password"])
            except ValueError as e:
                return {
                    "success": False,
                    "message": f"No se pudo leer la contraseña guardada ({e}) — "
                                f"vuelve a escribirla, guarda el equipo y prueba de nuevo.",
                }
    if not ip:
        raise HTTPException(status_code=400, detail="IP requerida")
    try:
        if device_type in ("linux", "macos"):
            import asyncssh
            async with asyncssh.connect(
                ip, username=username, password=password,
                known_hosts=None, connect_timeout=10,
                preferred_auth='password',
            ) as conn:
                result = await conn.run(f'ls "{source_path}"' if source_path else 'echo ok')
            return {"success": True, "message": f"SSH OK — {ip} accesible"}
        else:
            share, subpath = _parse_smb_source_path(source_path)
            if not share:
                return {"success": False, "message": "source_path requerido (share o share/subcarpeta)"}
            include_pattern = (body.get("include_pattern") or "").strip() or None
            mount_point = tempfile.mkdtemp(prefix="shomer_smb_test_")
            try:
                _smb_mount_readonly(ip, share, username, password, mount_point)
                if subpath:
                    target = _smb_resolve_backup_target(mount_point, subpath)
                    msg = f"SMB OK — {ip} — subcarpeta accesible: {subpath}"
                    if include_pattern:
                        import glob as _glob
                        total = 0
                        for raw in include_pattern.split(","):
                            pat = _expand_include_pattern(raw.strip())
                            if pat:
                                total += len(_glob.glob(os.path.join(target, pat)))
                        msg += f" — {total} archivo(s) coinciden con filtro hoy"
                else:
                    msg = f"SMB OK — {ip} — share {share} montado"
                return {"success": True, "message": msg}
            except Exception as e:
                return {"success": False, "message": f"SMB FALLO — {ip}: {str(e)[:200]}"}
            finally:
                subprocess.run(["sudo", "/usr/bin/umount", "-l", mount_point],
                               capture_output=True, timeout=15)
                try:
                    os.rmdir(mount_point)
                except OSError:
                    pass
    except Exception as e:
        return {"success": False, "message": f"Error: {str(e)[:150]}"}


@router.delete("/devices/{device_id}")
async def delete_backup_device(device_id: int, _admin: Dict[str, Any] = Depends(require_admin)):
    """Elimina un equipo de la lista de backups."""
    with _get_db() as conn:
        conn.execute("DELETE FROM backup_devices WHERE id = ?", (device_id,))
        conn.commit()
    return {"success": True, "message": "Equipo eliminado"}


# ── Backup Now (SSH / SMB → Restic) ────────────────────────────────────────────

RESTIC_REPO    = _PROTO_REPO
RESTIC_BIN     = _PROTO_BIN
SMB_MOUNT_BASE = "/mnt/shomer_smb"


def _update_device_status(
    device_id: int, status: str,
    files: int = None, size_mb: float = None,
    duration_sec: int = None, snapshot_id: str = None,
) -> None:
    with _get_db() as conn:
        conn.execute(
            "UPDATE backup_devices SET last_backup_at=?, last_status=?, "
            "last_files_count=?, last_size_mb=?, last_duration_sec=?, last_snapshot_id=? WHERE id=?",
            (_dt.now().strftime("%Y-%m-%d %H:%M:%S"), status,
             files, size_mb, duration_sec, snapshot_id, device_id),
        )
        conn.commit()


def _telegram(msg: str) -> None:
    try:
        from app.scripts.alerts import send_telegram_alert
        result = send_telegram_alert(msg)
        if not result:
            print(f"[protector][telegram] mensaje bloqueado o falló: {msg[:80]}")
    except Exception as e:
        print(f"[protector][telegram] error: {e}")


def _parse_smb_source_path(source_path: str) -> tuple[str, str]:
    """
    Parsea source_path SMB: 'share' o 'share/sub/carpeta'.
    Acepta barras Windows o Unix. Ej: C$/back_bases/Copias Diarias

    Corrige el error común de escribir la letra de unidad con ':' (C:) en vez
    de '$' (C$) -- "C:" no existe como nombre de share administrativo SMB,
    solo "C$" -- de lo contrario el mount falla como si fuera credencial mala.
    """
    import re as _re_local
    normalized = (source_path or "").strip().replace("\\", "/").strip("/")
    if not normalized:
        return "", ""
    if "/" not in normalized:
        share, sub = normalized, ""
    else:
        share, _, sub = normalized.partition("/")
    if _re_local.match(r"^[A-Za-z]:$", share):
        share = share[0].upper() + "$"
    return share, sub


def _expand_include_pattern(pattern: str) -> str:
    """Reemplaza {today} y {today_compact} según hora local del sitio (base.timezone)."""
    try:
        from zoneinfo import ZoneInfo
        tz_name = (
            _get_system_state("base.timezone")
            or _get_system_state("protector.timezone")
            or "America/Denver"
        )
        today = _dt.now(ZoneInfo(tz_name)).date()
    except Exception:
        today = _dt.utcnow().date()
    return (
        pattern.replace("{today}", today.strftime("%Y_%m_%d"))
        .replace("{today_compact}", today.strftime("%Y%m%d"))
    )


def _cifs_credentials_content(username: str, password: str) -> str:
    """
    Genera el contenido del archivo de credenciales para mount.cifs.

    Si username viene como 'DOMINIO\\usuario' o '.\\usuario' (convención de
    Windows para indicar cuenta local), separa domain= y username= --
    mount.cifs no interpreta el backslash embebido como lo hace Windows, lo
    toma como parte literal del username y la autenticación falla con
    "Permission denied" aunque la contraseña sea correcta.
    """
    user = username or ""
    domain = None
    if "\\" in user:
        dom, _, rest = user.partition("\\")
        user = rest
        if dom and dom != ".":
            domain = dom
        # dom == "." o vacío => cuenta local, sin domain= (mount.cifs usa default)
    content = f"username={user}\npassword={password}\n"
    if domain:
        content += f"domain={domain}\n"
    return content


def _smb_mount_readonly(ip: str, share: str, username: str, password: str, mount_point: str) -> None:
    """Monta share CIFS solo lectura. Lanza RuntimeError si falla."""
    fd, cred_file = tempfile.mkstemp(prefix="shomer_cifs_test_", text=True)
    try:
        os.write(fd, _cifs_credentials_content(username, password).encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(cred_file, 0o600)
    try:
        r = subprocess.run(
            ["sudo", "/usr/sbin/mount.cifs", f"//{ip}/{share}", mount_point,
             "-o", f"credentials={cred_file},ro,vers=3.0,uid=1000"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            raise RuntimeError(f"mount CIFS falló: {(r.stderr or r.stdout or '')[:200]}")
    finally:
        try:
            os.remove(cred_file)
        except OSError:
            pass


def _smb_resolve_backup_target(mount_point: str, subpath: str) -> str:
    """Ruta local montada del origen a respaldar."""
    if not subpath:
        return mount_point
    target = os.path.join(mount_point, *subpath.split("/"))
    if not os.path.isdir(target):
        raise RuntimeError(f"Subcarpeta no encontrada en share: {subpath}")
    return target


import re as _re
import time as _time


def _parse_restic_stats(output: str) -> dict:
    """Parsea stdout+stderr de 'restic backup' → snapshot_id, total_files, size_mb."""
    result: dict = {}
    m = _re.search(r'snapshot\s+([0-9a-f]+)\s+saved', output)
    if m:
        result['snapshot_id'] = m.group(1)
    m = _re.search(r'processed\s+([\d,]+)\s+files', output)
    if m:
        result['total_files'] = int(m.group(1).replace(',', ''))
    m = _re.search(r'Added to the repository:\s+([\d.]+)\s+(B|KiB|MiB|GiB|TiB)', output, _re.IGNORECASE)
    if m:
        val, unit = float(m.group(1)), m.group(2).upper()
        mult = {'B': 1/1048576, 'KIB': 1/1024, 'MIB': 1.0, 'GIB': 1024.0, 'TIB': 1048576.0}
        result['size_mb'] = round(val * mult.get(unit, 1.0), 3)
    return result


def _get_retention_days() -> int:
    with _get_db() as conn:
        row = conn.execute(
            "SELECT value FROM system_state WHERE key='protector.retention_days'"
        ).fetchone()
    try:
        return max(1, int(row["value"])) if row and row["value"] else 7
    except Exception:
        return 7


def _b2_copy_one_snapshot(snapshot_id: str) -> bool:
    """Copia un snapshot específico del repo local → B2. Retorna True si OK."""
    cfg = _get_b2_config()
    account_id  = cfg.get("b2_account_id", "")
    app_key     = cfg.get("b2_app_key", "")
    bucket      = cfg.get("b2_bucket", "")
    b2_path     = _effective_b2_path()
    if not (account_id and app_key and bucket and snapshot_id):
        return False
    b2_repo     = f"b2:{bucket}:{b2_path}" if b2_path else f"b2:{bucket}"
    local_pass  = get_restic_password().strip()
    remote_pass = (cfg.get("b2_password") or local_pass or "").strip()
    if not local_pass or not remote_pass:
        return False
    env = {
        **os.environ,
        "RESTIC_PASSWORD":  local_pass,
        "RESTIC_PASSWORD2": remote_pass,
        "B2_ACCOUNT_ID":    account_id,
        "B2_ACCOUNT_KEY":   app_key,
    }
    r = subprocess.run(
        [RESTIC_BIN, "-r", RESTIC_REPO, "copy", "--repo2", b2_repo, snapshot_id],
        env=env, capture_output=True, text=True, timeout=3600,
    )
    return r.returncode == 0


def _prune_local() -> bool:
    """Elimina snapshots locales viejos según retention_days. Solo llamar después de B2 sync exitoso."""
    days = _get_retention_days()
    local_pass = get_restic_password().strip()
    if not local_pass:
        return False
    env = {**os.environ, "RESTIC_PASSWORD": local_pass}
    r = subprocess.run(
        # --group-by host,tags (sin "paths"): si el nombre de archivo trae la fecha
        # embebida (ej. equipos PMS tipo Zeus), cada día tiene rutas distintas y el
        # agrupado default de restic (host,paths) deja cada snapshot en su propio
        # grupo de 1 -- keep-daily nunca tiene nada que recortar.
        [RESTIC_BIN, "-r", RESTIC_REPO, "forget", f"--keep-daily={days}", "--group-by", "host,tags", "--prune"],
        env=env, capture_output=True, text=True, timeout=600,
    )
    return r.returncode == 0


def _get_b2_retention_days() -> int:
    """Retención en B2 (nube) -- independiente de la retención local. Default 30 días."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT value FROM system_state WHERE key='protector.b2_retention_days'"
        ).fetchone()
    try:
        return max(1, int(row["value"])) if row and row["value"] else 30
    except Exception:
        return 30


def _prune_b2() -> bool:
    """Elimina snapshots viejos del repo B2 según b2_retention_days. Solo llamar después de sync exitoso.

    Sin esto, B2 nunca borra nada por sí solo (restic copy solo agrega) -- crecería sin
    límite indefinidamente. Ver CLAUDE.md §AY/discusión retención Hotel Ópera (20 jun 2026)."""
    cfg = _get_b2_config()
    account_id = cfg.get("b2_account_id", "")
    app_key = cfg.get("b2_app_key", "")
    bucket = cfg.get("b2_bucket", "")
    if not (account_id and app_key and bucket):
        return False
    b2_password = cfg.get("b2_password") or get_restic_password()
    local_pass = get_restic_password().strip()
    remote_pass = (b2_password or local_pass or "").strip()
    if not remote_pass:
        return False
    b2_path = _effective_b2_path()
    b2_repo = f"b2:{bucket}:{b2_path}" if b2_path else f"b2:{bucket}"
    days = _get_b2_retention_days()
    env = {
        **os.environ,
        "RESTIC_PASSWORD": remote_pass,
        "B2_ACCOUNT_ID": account_id,
        "B2_ACCOUNT_KEY": app_key,
    }
    r = subprocess.run(
        # Mismo fix de --group-by que _prune_local() -- ver comentario ahí.
        [RESTIC_BIN, "-r", b2_repo, "forget", f"--keep-daily={days}", "--group-by", "host,tags", "--prune"],
        env=env, capture_output=True, text=True, timeout=1800,
    )
    return r.returncode == 0


async def _backup_linux(device: dict) -> dict:
    """SCP recursivo desde el equipo remoto → directorio staging → Restic."""
    ip          = device["ip"]
    username    = device["username"]
    try:
        password = _decrypt_device_password(device["password"] or "")
    except Exception as e:
        msg = f"Credencial inválida: {e}"
        _update_device_status(device["id"], f"error: {msg[:100]}")
        return {"success": False, "message": msg[:200]}
    source_path = device["source_path"] or "/home"
    device_id   = device["id"]
    local_stage = f"/srv/shomer_backups/staging_ssh/{device_id}"
    os.makedirs(local_stage, exist_ok=True)
    try:
        import asyncssh
        async with asyncssh.connect(
            ip, username=username, password=password,
            known_hosts=None, connect_timeout=15,
            preferred_auth='password',
        ) as ssh_conn:
            await asyncssh.scp((ssh_conn, source_path), local_stage, recurse=True, preserve=True)
        env = {**os.environ, "RESTIC_PASSWORD": get_restic_password()}
        t0 = _time.monotonic()
        dev_name_tag = (device.get("name") or "").strip().replace(" ", "_")[:40]
        tags = ["--tag", f"device_{device_id}", "--tag", "ssh"]
        if dev_name_tag:
            tags += ["--tag", dev_name_tag]
        r = subprocess.run(
            [RESTIC_BIN, "-r", RESTIC_REPO, "backup", local_stage] + tags,
            capture_output=True, text=True, env=env, timeout=600,
        )
        duration_sec = int(_time.monotonic() - t0)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[:300])
        stats   = _parse_restic_stats(r.stdout + r.stderr)
        snap_id = stats.get('snapshot_id')
        _update_device_status(device_id, "ok",
            files=stats.get('total_files'), size_mb=stats.get('size_mb'),
            duration_sec=duration_sec, snapshot_id=snap_id)
        name     = device.get('name', ip)
        size_str = f"{stats['size_mb']:.1f} MB" if stats.get('size_mb') else ""
        files_str= f"{stats.get('total_files', '')} archivos" if stats.get('total_files') else ""
        detail   = " | ".join(x for x in [files_str, size_str, f"{duration_sec}s"] if x)
        _telegram(f"✅ <b>Protector — copia local OK</b>\nEquipo: <b>{name}</b> ({ip})"
                  + (f"\n{detail}" if detail else ""))
        if device.get('schedule_b2_enabled') and snap_id:
            ok_b2 = _b2_copy_one_snapshot(snap_id)
            if ok_b2:
                _telegram(f"☁️ <b>Protector — sync B2 OK</b>\nEquipo: <b>{name}</b> — snapshot subido a la nube.")
            else:
                _telegram(f"🟡 <b>Protector — sync B2 FALLÓ</b>\nEquipo: <b>{name}</b> — copia local OK, nube pendiente.")
        return {"success": True, "message": f"Backup SSH — {ip}" + (f" ({detail})" if detail else "")}
    except Exception as e:
        msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        _update_device_status(device_id, f"error: {msg[:100]}")
        _telegram(f"🔴 <b>Protector — copia local FALLÓ</b>\nEquipo: <b>{device.get('name', ip)}</b> ({ip})\nError: {msg[:200]}")
        return {"success": False, "message": msg[:200]}


async def _backup_windows(device: dict) -> dict:
    """Monta share CIFS → Restic sobre subcarpeta (opcional), filtrando por
    include_pattern via glob (restic backup no soporta --include, ver §AX.4)."""
    ip          = device["ip"]
    username    = device["username"]
    try:
        password = _decrypt_device_password(device["password"] or "")
    except Exception as e:
        msg = f"Credencial inválida: {e}"
        _update_device_status(device["id"], f"error: {msg[:100]}")
        return {"success": False, "message": msg[:200]}
    source_path = (device["source_path"] or "").strip()
    include_pattern = device.get("include_pattern")
    share, subpath = _parse_smb_source_path(source_path)
    if not share:
        msg = "source_path debe indicar share SMB (ej: backups o C$/back_bases/Copias Diarias)"
        _update_device_status(device["id"], f"error: {msg[:100]}")
        return {"success": False, "message": msg[:200]}
    device_id   = device["id"]
    mount_point = f"{SMB_MOUNT_BASE}/{device_id}"
    os.makedirs(mount_point, exist_ok=True)
    cred_file: str = ""
    try:
        fd, cred_file = tempfile.mkstemp(prefix=f"shomer_cifs_{device_id}_", text=True)
        try:
            os.write(fd, _cifs_credentials_content(username, password).encode("utf-8"))
        finally:
            os.close(fd)
        os.chmod(cred_file, 0o600)
        r = subprocess.run(
            ["sudo", "/usr/sbin/mount.cifs", f"//{ip}/{share}", mount_point,
             "-o", f"credentials={cred_file},uid=1000,gid=1000,vers=3.0"],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            raise RuntimeError(f"mount CIFS falló: {r.stderr[:200]}")
        backup_target = _smb_resolve_backup_target(mount_point, subpath)
        if include_pattern:
            # restic backup no tiene bandera --include (solo restore/dump/ls) -- hay
            # que resolver el patrón a archivos reales y pasarlos como targets directos.
            import glob as _glob
            targets: list[str] = []
            for raw in str(include_pattern).split(","):
                pat = _expand_include_pattern(raw.strip())
                if pat:
                    targets.extend(_glob.glob(os.path.join(backup_target, pat)))
            targets = sorted(set(targets))
            if not targets:
                raise RuntimeError(f"include_pattern no encontró archivos: {include_pattern}")
        else:
            targets = [backup_target]
        env = {**os.environ, "RESTIC_PASSWORD": get_restic_password()}
        t0 = _time.monotonic()
        dev_name_tag = (device.get("name") or "").strip().replace(" ", "_")[:40]
        tags = ["--tag", f"device_{device_id}", "--tag", "smb"]
        if dev_name_tag:
            tags += ["--tag", dev_name_tag]
        restic_timeout = 3600 if include_pattern else 600
        r = subprocess.run(
            [RESTIC_BIN, "-r", RESTIC_REPO, "backup"] + targets + tags,
            capture_output=True, text=True, env=env, timeout=restic_timeout,
        )
        duration_sec = int(_time.monotonic() - t0)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[:300])
        stats   = _parse_restic_stats(r.stdout + r.stderr)
        snap_id = stats.get('snapshot_id')
        _update_device_status(device_id, "ok",
            files=stats.get('total_files'), size_mb=stats.get('size_mb'),
            duration_sec=duration_sec, snapshot_id=snap_id)
        name     = device.get('name', ip)
        size_str = f"{stats['size_mb']:.1f} MB" if stats.get('size_mb') else ""
        files_str= f"{stats.get('total_files', '')} archivos" if stats.get('total_files') else ""
        detail   = " | ".join(x for x in [files_str, size_str, f"{duration_sec}s"] if x)
        _telegram(f"✅ <b>Protector — copia local OK</b>\nEquipo: <b>{name}</b> ({ip})"
                  + (f"\n{detail}" if detail else ""))
        if device.get('schedule_b2_enabled') and snap_id:
            ok_b2 = _b2_copy_one_snapshot(snap_id)
            if ok_b2:
                _telegram(f"☁️ <b>Protector — sync B2 OK</b>\nEquipo: <b>{name}</b> — snapshot subido a la nube.")
            else:
                _telegram(f"🟡 <b>Protector — sync B2 FALLÓ</b>\nEquipo: <b>{name}</b> — copia local OK, nube pendiente.")
        return {"success": True, "message": f"Backup SMB — {ip}" + (f" ({detail})" if detail else "")}
    except Exception as e:
        msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        _update_device_status(device_id, f"error: {msg[:100]}")
        _telegram(f"🔴 <b>Protector — copia local FALLÓ</b>\nEquipo: <b>{device.get('name', ip)}</b> ({ip})\nError: {msg[:200]}")
        return {"success": False, "message": msg[:200]}
    finally:
        try:
            subprocess.run(["sudo", "/usr/bin/umount", "-l", mount_point], capture_output=True, timeout=15)
        except Exception:
            pass
        if cred_file:
            try:
                os.remove(cred_file)
            except OSError:
                pass


@router.post("/devices/backup_now")
async def backup_device_now(
    body: Dict[str, Any] = Body(default={}),
    _admin: Dict[str, Any] = Depends(require_admin),
):
    """Ejecuta backup inmediato de un equipo específico (SSH o SMB → Restic)."""
    device_id = body.get("device_id")
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id requerido")
    if not get_restic_password().strip():
        raise HTTPException(status_code=503, detail="RESTIC_PASSWORD no configurado — verifica variable de entorno o system_state")
    with _get_db() as conn:
        row = conn.execute(
            "SELECT id, name, ip, device_type, username, password, source_path, include_pattern, schedule_b2_enabled "
            "FROM backup_devices WHERE id=?",
            (device_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    device = dict(row)
    if device["device_type"] in ("linux", "macos"):
        return await _backup_linux(device)
    else:
        return await _backup_windows(device)


@router.post("/devices/backup_all")
async def backup_all_devices(_admin: Dict[str, Any] = Depends(require_admin)):
    """Ejecuta backup de todos los equipos activos. Usado por el cron diario."""
    if not get_restic_password().strip():
        raise HTTPException(status_code=503, detail="RESTIC_PASSWORD no configurado")
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, ip, device_type, username, password, source_path, include_pattern, schedule_b2_enabled "
            "FROM backup_devices WHERE is_active=1"
        ).fetchall()
    devices = [dict(r) for r in rows]
    if not devices:
        return {"success": True, "message": "Sin equipos activos configurados", "results": []}
    results = []
    for device in devices:
        if device["device_type"] in ("linux", "macos"):
            r = await _backup_linux(device)
        else:
            r = await _backup_windows(device)
        results.append({"id": device["id"], "name": device["name"], "ip": device["ip"], **r})
    total   = len(results)
    success = sum(1 for r in results if r["success"])
    return {
        "success": success == total,
        "message": f"{success}/{total} backups completados",
        "results": results,
    }


# ── Scheduler de backups por equipo ─────────────────────────────────────────────

import asyncio as _asyncio


async def _run_global_b2_sync() -> None:
    """Sync completo local→B2 + prune local. Se dispara a la hora global configurada."""
    print("[protector][b2-global] Iniciando sync B2 global + prune local...")
    cfg = _get_b2_config()
    account_id = cfg.get("b2_account_id", "")
    app_key    = cfg.get("b2_app_key", "")
    bucket     = cfg.get("b2_bucket", "")
    if not (account_id and app_key and bucket):
        print("[protector][b2-global] B2 no configurado — omitiendo sync")
        return
    b2_password = cfg.get("b2_password") or get_restic_password()
    result = await _asyncio.to_thread(
        _b2_sync_blocking, account_id, app_key, bucket, _effective_b2_path(), b2_password
    )
    if result.get("success"):
        pruned     = await _asyncio.to_thread(_prune_local)
        pruned_b2  = await _asyncio.to_thread(_prune_b2)
        retention    = _get_retention_days()
        retention_b2 = _get_b2_retention_days()
        detail = (
            f"Retención local: {retention} días." if pruned else "Prune local pendiente."
        ) + " " + (
            f"Retención B2: {retention_b2} días." if pruned_b2 else "Prune B2 pendiente."
        )
        _telegram(f"🔄 <b>Protector — sync B2 OK</b>\nSync global completado. {detail}")
        print(f"[protector][b2-global] OK — prune local: {pruned}, prune B2: {pruned_b2}")
    else:
        print(f"[protector][b2-global] Falló: {result.get('message', '')[:200]}")

_scheduler_running = False
_scheduler_fired: set = set()  # "device_id:HH:MM:YYYY-MM-DD" ya disparados hoy


def _site_timezone() -> str:
    """Timezone del sitio: base.timezone > protector.timezone > America/Denver."""
    return (_get_system_state("base.timezone")
            or _get_system_state("protector.timezone")
            or "America/Denver")


def _scheduler_now() -> _dt:
    """Hora actual en la timezone del sitio."""
    try:
        from zoneinfo import ZoneInfo
        return _dt.now(ZoneInfo(_site_timezone()))
    except Exception:
        from datetime import timezone as _tz
        return _dt.now(_tz.utc)


def _client_slug() -> str:
    """Slug del nombre del cliente para usar como b2_path (base.client_name → slug)."""
    import re as _re2
    name = _get_system_state("base.client_name") or ""
    slug = _re2.sub(r'[^a-z0-9]+', '-', name.lower().strip()).strip('-')
    return slug[:40]


def _effective_b2_path() -> str:
    """b2_path efectivo: usa protector.b2_path si está configurado, si no usa slug del cliente."""
    explicit = (_get_system_state("protector.b2_path") or "").strip()
    return explicit if explicit else _client_slug()


async def _scheduler_loop() -> None:
    """Revisa cada 60s si algún equipo tiene schedule_time == hora local del sitio."""
    global _scheduler_fired
    while True:
        try:
            now_local = _scheduler_now()
            current_hhmm = now_local.strftime("%H:%M")
            today = now_local.strftime("%Y-%m-%d")
            with _get_db() as conn:
                rows = conn.execute(
                    "SELECT id, name, ip, device_type, username, password, source_path, include_pattern, schedule_b2_enabled "
                    "FROM backup_devices WHERE is_active=1 AND schedule_enabled=1 AND schedule_time=?",
                    (current_hhmm,),
                ).fetchall()
            for row in rows:
                fire_key = f"{row['id']}:{current_hhmm}:{today}"
                if fire_key in _scheduler_fired:
                    continue
                _scheduler_fired.add(fire_key)
                device = dict(row)
                _asyncio.create_task(_run_scheduled_backup(device))
            # Scheduler global B2 sync + prune
            cfg_b2 = _get_b2_config()
            b2_sync_enabled = (cfg_b2.get("b2_sync_enabled") or "0") == "1"
            b2_sync_time    = (cfg_b2.get("b2_sync_time") or "").strip()
            if b2_sync_enabled and b2_sync_time and b2_sync_time == current_hhmm:
                fire_key = f"b2_global:{b2_sync_time}:{today}"
                if fire_key not in _scheduler_fired:
                    _scheduler_fired.add(fire_key)
                    _asyncio.create_task(_run_global_b2_sync())
            # Limpiar claves de días anteriores para evitar memory leak
            _scheduler_fired = {k for k in _scheduler_fired if k.endswith(today)}
        except Exception as e:
            print(f"[protector][scheduler] error: {e}")
        await _asyncio.sleep(60)


async def _run_scheduled_backup(device: dict) -> None:
    """Ejecuta backup programado y registra resultado."""
    name = device.get("name", device["ip"])
    print(f"[protector][scheduler] iniciando backup programado: {name} ({device['ip']})")
    if not get_restic_password().strip():
        print(f"[protector][scheduler] SKIP {name}: RESTIC_PASSWORD no configurado")
        return
    if device["device_type"] in ("linux", "macos"):
        result = await _backup_linux(device)
    else:
        result = await _backup_windows(device)
    status = "ok" if result.get("success") else f"error: {result.get('message','')[:80]}"
    print(f"[protector][scheduler] {name}: {status}")


def start_backup_scheduler() -> None:
    """Inicia el loop del scheduler en el event loop de FastAPI. Llamar desde lifespan.

    shomer-tools.service corre --workers 2 -- sin esto, ambos workers detectan el mismo
    schedule_time y disparan el mismo backup dos veces a la vez, compitiendo por el mismo
    mount_point SMB y el mismo repo Restic (ver CLAUDE.md §AZ). Solo el worker que adquiere
    el lock de líder (`protector-backup`) lo ejecuta.
    """
    global _scheduler_running
    if _scheduler_running:
        return
    from app.api.shomer_poller_leader import try_acquire_poller_leader
    if not try_acquire_poller_leader("protector-backup"):
        print(f"[protector][scheduler] worker pid={os.getpid()} omitido — otro worker es líder")
        return
    _scheduler_running = True
    _asyncio.create_task(_scheduler_loop())


@router.get("/scheduler/status")
async def scheduler_status(_admin: Dict[str, Any] = Depends(require_admin)):
    """Estado del scheduler y próximos backups programados."""
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT id, name, ip, schedule_enabled, schedule_time, last_backup_at, last_status "
            "FROM backup_devices WHERE schedule_enabled=1 ORDER BY schedule_time"
        ).fetchall()
    return {
        "success": True,
        "scheduler_running": _scheduler_running,
        "scheduled_devices": [dict(r) for r in rows],
    }


# ── Backblaze B2 Cloud Config ────────────────────────────────────────────────────

def _get_system_state(key: str) -> str | None:
    """Lee un valor de system_state por clave. Retorna None si no existe."""
    with _get_db() as conn:
        row = conn.execute("SELECT value FROM system_state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def _get_b2_config() -> dict:
    """Lee credenciales B2 desde system_state."""
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT key, value FROM system_state WHERE key LIKE 'protector.b2%'"
        ).fetchall()
    return {r["key"].replace("protector.", ""): r["value"] for r in rows}


def _set_b2_field(field: str, value: str) -> None:
    with _get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO system_state (key, value) VALUES (?, ?)",
            (f"protector.{field}", value)
        )
        conn.commit()


def _b2_sync_blocking(account_id: str, app_key: str, bucket: str, b2_path: str, b2_password: str) -> dict:
    """Copia snapshots al repo B2 via restic copy. Bloquea el hilo — usar con asyncio.to_thread."""
    local_pass = get_restic_password().strip()
    remote_pass = (b2_password or local_pass or "").strip()
    if not local_pass:
        return {
            "success": False,
            "message": "Repo local sin contraseña (RESTIC_PASSWORD / RESTIC_PASSWORD_FILE en el servidor).",
        }
    if not remote_pass:
        return {
            "success": False,
            "message": "Indica la contraseña de cifrado del repositorio Restic en B2 (panel Protector). "
            "No es la Application Key; es la frase que cifra el backup en B2.",
        }

    b2_repo = f"b2:{bucket}:{b2_path}" if b2_path else f"b2:{bucket}"

    # Comandos con solo -r b2:... usan RESTIC_PASSWORD para ESE repo (clave B2), no la del staging local.
    env_b2_only = {
        **os.environ,
        "RESTIC_PASSWORD": remote_pass,
        "B2_ACCOUNT_ID": account_id,
        "B2_ACCOUNT_KEY": app_key,
    }
    check = subprocess.run(
        [RESTIC_BIN, "-r", b2_repo, "snapshots"],
        env=env_b2_only,
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = (check.stderr or "") + (check.stdout or "")
    low = out.lower()
    if check.returncode != 0:
        if "does not exist" in low or "is there a repository" in low or "no repository" in low:
            init_r = subprocess.run(
                [RESTIC_BIN, "-r", b2_repo, "init"],
                env=env_b2_only,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if init_r.returncode != 0:
                return {"success": False, "message": f"Error init repo B2: {(init_r.stderr or init_r.stdout)[:400]}"}
        else:
            return {
                "success": False,
                "message": f"No se pudo abrir el repo Restic en B2 (revisa contraseña B2 en el panel): {out[:400]}",
            }

    # Origen = staging local, destino = B2 (restic usa PASSWORD y PASSWORD2).
    env_copy = {
        **os.environ,
        "RESTIC_PASSWORD": local_pass,
        "RESTIC_PASSWORD2": remote_pass,
        "B2_ACCOUNT_ID": account_id,
        "B2_ACCOUNT_KEY": app_key,
    }
    r = subprocess.run(
        [RESTIC_BIN, "-r", RESTIC_REPO, "copy", "--repo2", b2_repo],
        env=env_copy,
        capture_output=True,
        text=True,
        timeout=3600,
    )
    if r.returncode != 0:
        err_msg = (r.stderr or r.stdout)[:400]
        _telegram(f"🔴 <b>Protector — sync B2 FALLÓ</b>\nError: {err_msg[:300]}")
        return {"success": False, "message": f"restic copy: {err_msg}"}
    _telegram(f"☁️ <b>Protector — sync B2 OK</b>\nBackups sincronizados a Backblaze correctamente.")
    return {"success": True, "message": (r.stdout.strip() or "Sincronización B2 completada")[:500]}


def _b2_test_blocking(account_id: str, app_key: str, bucket: str, b2_path: str, b2_password: str) -> dict:
    """Comprueba acceso al repo Restic en B2 con `restic snapshots` (sin init ni copy)."""
    b2_repo = f"b2:{bucket}:{b2_path}" if b2_path else f"b2:{bucket}"
    pwd = (b2_password or get_restic_password() or "").strip()
    if not pwd:
        return {"success": False, "message": "Configura password del repo B2 (Restic) o RESTIC_PASSWORD en el servidor."}
    env = {
        **os.environ,
        "RESTIC_PASSWORD": pwd,
        "B2_ACCOUNT_ID": account_id,
        "B2_ACCOUNT_KEY": app_key,
    }
    check = subprocess.run(
        [RESTIC_BIN, "-r", b2_repo, "snapshots"],
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    out = (check.stdout or "") + (check.stderr or "")
    if check.returncode == 0:
        return {
            "success": True,
            "message": "Conexión B2 correcta (repositorio Restic accesible).",
            "detail": (check.stdout.strip() or "")[:500],
        }
    low = out.lower()
    if "does not exist" in low or "is there a repository" in low or "no repository" in low:
        return {
            "success": True,
            "message": "Credenciales B2 válidas; el repositorio Restic aún no existe (se creará al sincronizar).",
        }
    return {"success": False, "message": (check.stderr or check.stdout or "Error restic")[:400]}


def _b2_env_and_repo() -> tuple:
    """Devuelve (env_dict, b2_repo_string) con credenciales B2 o lanza ValueError."""
    cfg        = _get_b2_config()
    account_id = (cfg.get("b2_account_id") or "").strip()
    app_key    = (cfg.get("b2_app_key")    or "").strip()
    bucket     = (cfg.get("b2_bucket")     or "").strip()
    b2_path    = _effective_b2_path()
    b2_pass    = (cfg.get("b2_password")   or get_restic_password() or "").strip()
    if not (account_id and app_key and bucket and b2_pass):
        raise ValueError("Configuración B2 incompleta — verifica bucket, Account ID, App Key y contraseña repo.")
    b2_repo = f"b2:{bucket}:{b2_path}" if b2_path else f"b2:{bucket}"
    env = {
        **os.environ,
        "RESTIC_PASSWORD": b2_pass,
        "B2_ACCOUNT_ID":   account_id,
        "B2_ACCOUNT_KEY":  app_key,
    }
    return env, b2_repo


def _b2_list_snapshots_blocking() -> dict:
    """Lista snapshots del repositorio remoto en B2."""
    try:
        env, b2_repo = _b2_env_and_repo()
    except ValueError as e:
        return {"success": False, "message": str(e), "snapshots": []}
    try:
        import json as _json
        r = subprocess.run(
            [RESTIC_BIN, "-r", b2_repo, "snapshots", "--json"],
            env=env, capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            return {"success": False, "message": (r.stderr or r.stdout)[:400], "snapshots": []}
        snaps = _json.loads(r.stdout or "[]") or []
        return {"success": True, "snapshots": snaps, "repo": b2_repo}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Timeout al conectar con B2.", "snapshots": []}
    except Exception as e:
        return {"success": False, "message": str(e)[:300], "snapshots": []}


def _b2_restore_blocking(snapshot_id: str, target: str) -> dict:
    """Restaura un snapshot de B2 a un path local en el Shomer."""
    try:
        env, b2_repo = _b2_env_and_repo()
    except ValueError as e:
        return {"success": False, "error": str(e)}
    try:
        r = subprocess.run(
            [RESTIC_BIN, "-r", b2_repo, "restore", snapshot_id, "--target", target],
            env=env, capture_output=True, text=True, timeout=3600,
        )
        if r.returncode != 0:
            return {"success": False, "error": (r.stderr or r.stdout)[:500]}
        return {"success": True, "output": (r.stdout.strip() or "Restauración completada")[:500]}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout — el snapshot puede ser muy grande."}
    except Exception as e:
        return {"success": False, "error": str(e)[:300]}


@router.get("/b2/snapshots")
async def list_b2_snapshots(_admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    """Lista snapshots disponibles en el repositorio remoto B2."""
    result = await asyncio.to_thread(_b2_list_snapshots_blocking)
    if not result["success"]:
        raise HTTPException(status_code=503, detail=result["message"])
    return result


@router.post("/b2/restore/{snapshot_id}")
async def restore_from_b2(
    snapshot_id: str,
    body: Dict[str, Any] = Body(default={}),
    _admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Restaura un snapshot del repositorio B2 a un directorio local en el Shomer.
    target por defecto: /srv/shomer_restore/{snapshot_id}"""
    sid    = snapshot_id.strip()
    target = (body.get("target") or f"/srv/shomer_restore/{sid}").strip()
    _telegram(
        f"⏳ <b>Protector — restore B2 iniciado</b>\n"
        f"Snapshot <code>{sid[:8]}</code> → <code>{target}</code>"
    )
    result = await asyncio.to_thread(_b2_restore_blocking, sid, target)
    if not result["success"]:
        _telegram(
            f"❌ <b>Protector — restore B2 FALLÓ</b>\n"
            f"Snapshot <code>{sid[:8]}</code>\n{result['error'][:200]}"
        )
        raise HTTPException(status_code=500, detail=result["error"])
    _telegram(
        f"✅ <b>Protector — restore B2 completado</b>\n"
        f"Snapshot <code>{sid[:8]}</code> restaurado en <code>{target}</code>"
    )
    return {"success": True, "snapshot_id": sid, "target": target,
            "output": result.get("output", "")}


def _zip_restore_dir(src_path: str, zip_path: str) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for root, _dirs, files in os.walk(src_path):
            for fname in files:
                fp = os.path.join(root, fname)
                arcname = os.path.relpath(fp, src_path)
                zf.write(fp, arcname)


@router.get("/restore/{snapshot_id}/download")
async def download_restore_zip(
    snapshot_id: str,
    _admin: Dict[str, Any] = Depends(require_admin),
) -> FileResponse:
    """Genera un ZIP del directorio de restore y lo sirve como descarga."""
    sid = snapshot_id.strip()
    restore_path = f"/srv/shomer_restore/{sid}"
    if not os.path.isdir(restore_path):
        raise HTTPException(
            status_code=404,
            detail="No hay archivos restaurados para este snapshot. Ejecuta primero la restauración desde B2."
        )
    zip_path = f"/tmp/shomer_restore_{sid[:8]}.zip"
    if not os.path.exists(zip_path):
        await asyncio.to_thread(_zip_restore_dir, restore_path, zip_path)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"restore_{sid[:8]}.zip",
        headers={"Content-Disposition": f'attachment; filename="restore_{sid[:8]}.zip"'},
    )


@router.post("/b2/test")
async def test_b2_connection(_admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    """Prueba ligera: restic snapshots contra el bucket B2 configurado."""
    cfg = _get_b2_config()
    account_id = cfg.get("b2_account_id", "")
    app_key = cfg.get("b2_app_key", "")
    bucket = cfg.get("b2_bucket", "")
    b2_password = cfg.get("b2_password") or get_restic_password()
    b2_path = _effective_b2_path()
    if not (account_id and app_key and bucket):
        return {
            "success": False,
            "message": "Configura bucket, Account ID y Application Key antes de probar.",
        }
    try:
        return await asyncio.to_thread(
            _b2_test_blocking, account_id, app_key, bucket, b2_path, b2_password
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Timeout al conectar con B2 (revisa red/firewall)."}
    except Exception as e:
        return {"success": False, "message": str(e)[:400]}


@router.get("/b2config")
async def get_b2_config(_admin: Dict[str, Any] = Depends(require_admin)):
    """Lee configuración B2 (no expone secrets)."""
    cfg = _get_b2_config()
    return {
        "success":          True,
        "b2_bucket":        cfg.get("b2_bucket", ""),
        "b2_account_id":    cfg.get("b2_account_id", ""),
        "b2_has_key":       bool(cfg.get("b2_app_key")),
        "b2_has_pass":      bool(cfg.get("b2_password")),
        "b2_path":          cfg.get("b2_path", ""),
        "b2_path_effective": _effective_b2_path(),
        "b2_sync_enabled":  (cfg.get("b2_sync_enabled") or "0") == "1",
        "b2_sync_time":     cfg.get("b2_sync_time", ""),
        "site_timezone":    _site_timezone(),
    }


@router.post("/restore/{snapshot_id}")
async def restore_snapshot_endpoint(
    snapshot_id: str,
    body: Dict[str, Any] = Body(default={}),
    _admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Restaura un snapshot Restic al path indicado (default: restaura en sitio, target='/').
    Operación bloqueante — puede tardar varios minutos según el tamaño.
    """
    from app.backend.protector import restore_snapshot
    if not get_restic_password().strip():
        raise HTTPException(status_code=503, detail="RESTIC_PASSWORD no configurado")
    target = (body.get("target") or "/").strip() or "/"
    result = await asyncio.to_thread(restore_snapshot, snapshot_id, target)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error") or "Error al restaurar")
    return {"success": True, "snapshot_id": snapshot_id, "target": target,
            "output": result.get("output", "")}


@router.delete("/snapshot/{snapshot_id}")
async def delete_snapshot_endpoint(
    snapshot_id: str,
    _admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Elimina un snapshot del repositorio local (restic forget --prune).
    Operación irreversible.
    """
    from app.backend.protector import forget_snapshot
    if not get_restic_password().strip():
        raise HTTPException(status_code=503, detail="RESTIC_PASSWORD no configurado")
    result = await asyncio.to_thread(forget_snapshot, snapshot_id)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error") or "Error al eliminar")
    return {"success": True, "snapshot_id": snapshot_id,
            "output": result.get("output", "")}


@router.post("/b2/object-lock/enable")
async def enable_b2_object_lock(
    body: Dict[str, Any] = Body(default={}),
    _admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """
    R4 — Activa Object Lock (File Lock) en el bucket B2 configurado.
    Requiere application key con capacidad 'writeBucketRetentions'.
    Operación irreversible: una vez activado no se puede desactivar.

    NOTA (20 jun 2026): la tarjeta de panel que llamaba este endpoint se ocultó a
    pedido de Juan Pablo (ver app/templates/backups.html, sección comentada
    "Object Lock B2" + CLAUDE.md §AY). Este endpoint y el de abajo quedan intactos
    y funcionales por API directa -- solo no son alcanzables desde la UI por ahora.
    """
    import requests as _req

    lock_days = int(body.get("lock_days") or 90)
    if not (7 <= lock_days <= 36500):
        lock_days = 90

    cfg = _get_b2_config()
    account_id = cfg.get("b2_account_id", "").strip()
    app_key = cfg.get("b2_app_key", "").strip()
    bucket_name = cfg.get("b2_bucket", "").strip()
    if not (account_id and app_key and bucket_name):
        return {"success": False, "message": "Configura bucket, Account ID y App Key primero."}

    try:
        # 1. Autorizar
        auth = _req.post(
            "https://api.backblazeb2.com/b2api/v2/b2_authorize_account",
            auth=(account_id, app_key), timeout=15
        )
        auth.raise_for_status()
        auth_data = auth.json()
        api_url = auth_data["apiUrl"]
        token = auth_data["authorizationToken"]
        account_id_real = auth_data["accountId"]
        headers = {"Authorization": token}

        # 2. Obtener bucket ID
        buckets = _req.post(
            f"{api_url}/b2api/v2/b2_list_buckets",
            json={"accountId": account_id_real, "bucketName": bucket_name},
            headers=headers, timeout=15
        )
        buckets.raise_for_status()
        blist = buckets.json().get("buckets", [])
        if not blist:
            return {"success": False, "message": f"Bucket '{bucket_name}' no encontrado en tu cuenta B2."}
        bucket_id = blist[0]["bucketId"]
        current_lock = blist[0].get("fileLockConfiguration", {}).get("isFileLockEnabled", False)
        if current_lock:
            return {"success": True, "message": "Object Lock ya estaba activado en este bucket.", "already_enabled": True}

        # 3. Activar Object Lock con período de retención por defecto
        upd = _req.post(
            f"{api_url}/b2api/v2/b2_update_bucket",
            json={
                "accountId": account_id_real,
                "bucketId": bucket_id,
                "fileLockEnabled": True,
                "defaultRetentionMode": "compliance",
                "defaultRetentionPeriod": {"unit": "days", "duration": lock_days},
            },
            headers=headers, timeout=15
        )
        upd.raise_for_status()
        upd_data = upd.json()
        enabled = upd_data.get("fileLockConfiguration", {}).get("isFileLockEnabled", False)
        if enabled:
            from app.api.shomer_common import set_config
            set_config("protector.b2_object_lock", True)
            set_config("protector.b2_lock_days", lock_days)
            return {"success": True, "message": f"Object Lock activado en '{bucket_name}' con retención de {lock_days} días. Los snapshots ahora son inmutables.", "bucket_id": bucket_id}
        return {"success": False, "message": "B2 respondió OK pero Object Lock no aparece activado. Verifica capacidades de la clave."}
    except _req.HTTPError as e:
        body = e.response.text[:300] if e.response else str(e)
        return {"success": False, "message": f"Error B2 API: {body}"}
    except Exception as e:
        return {"success": False, "message": str(e)[:400]}


@router.get("/b2/object-lock/status")
async def b2_object_lock_status(_admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    """Estado del Object Lock B2 (consultado en vivo desde la API de B2)."""
    import requests as _req

    cfg = _get_b2_config()
    account_id = cfg.get("b2_account_id", "").strip()
    app_key = cfg.get("b2_app_key", "").strip()
    bucket_name = cfg.get("b2_bucket", "").strip()
    if not (account_id and app_key and bucket_name):
        return {"success": False, "enabled": False, "message": "B2 no configurado"}

    try:
        auth = _req.post(
            "https://api.backblazeb2.com/b2api/v2/b2_authorize_account",
            auth=(account_id, app_key), timeout=15
        )
        auth.raise_for_status()
        auth_data = auth.json()
        api_url = auth_data["apiUrl"]
        token = auth_data["authorizationToken"]
        account_id_real = auth_data["accountId"]

        buckets = _req.post(
            f"{api_url}/b2api/v2/b2_list_buckets",
            json={"accountId": account_id_real, "bucketName": bucket_name},
            headers={"Authorization": token}, timeout=15
        )
        buckets.raise_for_status()
        blist = buckets.json().get("buckets", [])
        if not blist:
            return {"success": False, "enabled": False, "message": "Bucket no encontrado"}
        enabled = blist[0].get("fileLockConfiguration", {}).get("isFileLockEnabled", False)
        from app.api.shomer_common import get_config as _gc
        lock_days = _gc("protector.b2_lock_days", 90)
        return {"success": True, "enabled": enabled, "bucket": bucket_name, "lock_days": lock_days}
    except Exception as e:
        return {"success": False, "enabled": False, "message": str(e)[:300]}


@router.post("/b2config")
async def save_b2_config(
    body: Dict[str, Any] = Body(default={}),
    _admin: Dict[str, Any] = Depends(require_admin),
):
    """Guarda credenciales B2 en system_state (no sobreescribe con '***')."""
    for field in ["b2_bucket", "b2_account_id", "b2_app_key", "b2_password", "b2_path", "b2_sync_time"]:
        val = (body.get(field) or "").strip()
        if val and val != "***":
            _set_b2_field(field, val)
        elif field == "b2_sync_time" and "b2_sync_time" in body and not val:
            _set_b2_field(field, "")   # permitir borrar la hora
    if "b2_sync_enabled" in body:
        _set_b2_field("b2_sync_enabled", "1" if body["b2_sync_enabled"] else "0")
    return {"success": True, "message": "Configuración B2 guardada"}
