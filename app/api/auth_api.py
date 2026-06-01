"""
Auth JWT: login, /auth/me, dependencias RequireAdmin y get_current_user.
Rol: admin | operator. Endpoints sensibles exigen admin.
"""
import logging
import os
import hashlib
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.backend.db import connect
from app.api.security_http import cookie_secure_for_request

# JWT simple (payload base64 + firma). Alternativa: PyJWT si está instalado.
import base64
import json
import secrets

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)

_DEFAULT_JWT = "shomer-secret-change-in-production"
JWT_SECRET = os.environ.get("JWT_SECRET", _DEFAULT_JWT)


def _resolve_jwt_expire_hours() -> int:
    """
    Duración de la sesión del panel (cookie + token). Default 1 h (más seguro que 24 h).
    Override: entorno SHOMER_JWT_EXPIRE_HOURS (entero, horas, rango 1–168).
    """
    raw = (os.environ.get("SHOMER_JWT_EXPIRE_HOURS") or "1").strip()
    try:
        h = int(raw)
    except ValueError:
        h = 1
    return max(1, min(h, 168))


JWT_EXPIRE_HOURS = _resolve_jwt_expire_hours()

# Nonce derivado del JWT_SECRET para que ambos procesos (8000/8001) compartan
# el mismo valor y los tokens del proxy sean válidos en el servicio destino.
# Cambiar JWT_SECRET rota el nonce e invalida todos los tokens activos.
_BOOT_NONCE = hashlib.sha256(f"shomer-nonce:{JWT_SECRET}".encode()).hexdigest()[:32]

if JWT_SECRET == _DEFAULT_JWT:
    _log = logging.getLogger("shomer.auth")
    _log.warning("JWT_SECRET usa valor por defecto — definir JWT_SECRET en producción.")
    if os.environ.get("SHOMER_STRICT_AUTH", "").strip().lower() in ("1", "true", "yes"):
        raise RuntimeError(
            "SHOMER_STRICT_AUTH: configure JWT_SECRET distinto del valor por defecto."
        )


def _get_conn():
    return connect(timeout=10, check_same_thread=False)


def _ensure_users_table():
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'operator'
            )
        """)
        conn.commit()
        cur = conn.execute("SELECT COUNT(*) FROM users")
        n = cur.fetchone()[0]
        h_factory = hashlib.sha256("shomer2026".encode()).hexdigest()
        if n == 0:
            conn.execute(
                "INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("root", h_factory, "admin"),
            )
            conn.commit()
        else:
            # Garantizar que el usuario root de fábrica siempre exista
            conn.execute(
                "INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("root", h_factory, "admin"),
            )
            conn.commit()
    finally:
        conn.close()


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _create_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": (datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)).timestamp(),
        "bnonce": _BOOT_NONCE,
    }
    data = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hashlib.sha256((JWT_SECRET + data).encode()).hexdigest()
    return f"{data}.{sig}"


def _decode_token(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        data, sig = parts[0], parts[1]
        if hashlib.sha256((JWT_SECRET + data).encode()).hexdigest() != sig:
            return None
        payload = json.loads(base64.urlsafe_b64decode(data.encode()).decode())
        if payload.get("exp", 0) < datetime.utcnow().timestamp():
            return None
        if payload.get("bnonce") != _BOOT_NONCE:
            return None
        return payload
    except Exception:
        return None


def verify_token(token: Optional[str]) -> Optional[dict]:
    """Valida el token (cookie o Bearer) y devuelve el payload o None. Uso: protección de rutas HTML."""
    return _decode_token(token) if token else None


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(request: Request, req: LoginRequest):
    """Devuelve JWT y rol (admin | operator). Fija cookie access_token para protección de rutas HTML."""
    _ensure_users_table()
    conn = _get_conn()
    try:
        cur = conn.execute(
            "SELECT username, password_hash, role FROM users WHERE username = ?",
            (req.username.strip(),),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    if _hash_password(req.password) != row["password_hash"]:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    token = _create_token(row["username"], row["role"])
    _factory_hash = hashlib.sha256("shomer2026".encode()).hexdigest()
    _force_setup = (row["username"] == "root" and row["password_hash"] == _factory_hash)
    content = {"token": token, "username": row["username"], "role": row["role"]}
    if _force_setup:
        content["redirect"] = "/setup"
    response = JSONResponse(content=content)
    _sec = cookie_secure_for_request(request)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=_sec,
        max_age=JWT_EXPIRE_HOURS * 3600,
        path="/",
    )
    return response


@router.get("/me")
async def auth_me(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Devuelve usuario y rol. Acepta Bearer token o cookie access_token."""
    token = (credentials.credentials if credentials and credentials.credentials else None) \
            or request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Token requerido")
    payload = _decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return {"username": payload.get("sub"), "role": payload.get("role", "operator")}


@router.post("/logout")
async def logout(request: Request):
    """Cierra sesión eliminando la cookie access_token."""
    response = JSONResponse(content={"success": True})
    response.delete_cookie("access_token", path="/", secure=cookie_secure_for_request(request))
    return response


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Dependencia: usuario actual o 401. Misma lógica que /auth/me: Bearer o cookie access_token."""
    token = (credentials.credentials if credentials and credentials.credentials else None) or request.cookies.get(
        "access_token"
    )
    if not token:
        raise HTTPException(status_code=401, detail="Token requerido")
    payload = _decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    return {"username": payload.get("sub"), "role": payload.get("role", "operator")}


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Dependencia: solo admin; si no, 403."""
    if (user.get("role") or "").lower() != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol admin")
    return user


# ── Gestión de usuarios ──────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "operator"

class ChangePasswordRequest(BaseModel):
    password: str

class ChangeRoleRequest(BaseModel):
    role: str


@router.get("/users")
async def list_users(user: dict = Depends(require_admin)):
    """Lista todos los usuarios. Solo admin."""
    _ensure_users_table()
    conn = _get_conn()
    try:
        cur = conn.execute("SELECT id, username, role FROM users ORDER BY id")
        rows = [{"id": r["id"], "username": r["username"], "role": r["role"]} for r in cur.fetchall()]
    finally:
        conn.close()
    return {"users": rows}


@router.post("/users")
async def create_user(req: CreateUserRequest, user: dict = Depends(require_admin)):
    """Crea un usuario nuevo. Solo admin."""
    if req.role not in ("admin", "operator"):
        raise HTTPException(status_code=400, detail="Rol inválido. Usa: admin | operator")
    if not req.username or len(req.username.strip()) < 3:
        raise HTTPException(status_code=400, detail="Usuario mínimo 3 caracteres")
    if not req.password or len(req.password) < 4:
        raise HTTPException(status_code=400, detail="Contraseña mínimo 4 caracteres")
    _ensure_users_table()
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (req.username.strip(), _hash_password(req.password), req.role),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"El usuario '{req.username}' ya existe")
    finally:
        conn.close()
    return {"success": True, "message": f"Usuario '{req.username}' creado con rol {req.role}"}


@router.api_route("/users/{user_id}/password", methods=["PUT", "POST"])
async def change_user_password(user_id: int, req: ChangePasswordRequest, current: dict = Depends(get_current_user)):
    """Cambia contraseña. PUT o POST (algunos proxies solo dejan pasar POST). Admin: cualquier usuario; operator: solo la suya."""
    if not req.password or len(req.password) < 4:
        raise HTTPException(status_code=400, detail="Contraseña mínimo 4 caracteres")
    _ensure_users_table()
    conn = _get_conn()
    try:
        cur = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
        target = cur.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        if target["username"] == "admin":
            raise HTTPException(status_code=403, detail="La contraseña de este usuario no puede modificarse desde el panel")
        if current["role"] != "admin" and target["username"] != current["username"]:
            raise HTTPException(status_code=403, detail="Solo puedes cambiar tu propia contraseña")
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (_hash_password(req.password), user_id))
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "message": "Contraseña actualizada"}


@router.put("/users/{user_id}/role")
async def change_user_role(user_id: int, req: ChangeRoleRequest, current: dict = Depends(require_admin)):
    """Cambia rol de un usuario. Solo admin."""
    if req.role not in ("admin", "operator"):
        raise HTTPException(status_code=400, detail="Rol inválido. Usa: admin | operator")
    _ensure_users_table()
    conn = _get_conn()
    try:
        cur = conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
        target = cur.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        if target["username"] == current["username"] and req.role != "admin":
            raise HTTPException(status_code=400, detail="No puedes quitarte el rol admin a ti mismo")
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (req.role, user_id))
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "message": f"Rol actualizado a {req.role}"}


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, current: dict = Depends(require_admin)):
    """Elimina usuario. Admin no puede eliminarse a sí mismo."""
    _ensure_users_table()
    conn = _get_conn()
    name = ""
    try:
        cur = conn.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,))
        target = cur.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        # sqlite3.Row: acceso por índice evita fallos si el nombre de columna varía
        t_username = target[1]
        t_role = target[2]
        if t_username == "admin":
            raise HTTPException(status_code=403, detail="Este usuario no puede eliminarse desde el panel")
        if t_username == current.get("username"):
            raise HTTPException(status_code=400, detail="No puedes eliminarte a ti mismo")
        cur2 = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role='admin'")
        rowc = cur2.fetchone()
        n_admins = int(rowc[0]) if rowc is not None else 0
        if n_admins <= 1 and t_role == "admin":
            raise HTTPException(status_code=400, detail="Debe quedar al menos un admin en el sistema")
        name = t_username
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "message": f"Usuario '{name}' eliminado"}
