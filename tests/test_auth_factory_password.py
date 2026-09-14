"""14 sep 2026: la cuenta root de fábrica dejó de crearse con la contraseña
fija "shomer2026" -- ese mismo valor viajaba en CADA instalación de Shomer,
así que conocerlo una vez significaba conocerlo para siempre en cualquier
sitio nuevo. Verificado en vivo el 14 sep: los 3 labs que se están por enviar
a Bogotá como hardware para clientes nuevos seguían con esa contraseña
activa. Estas pruebas cubren que la nueva cuenta de fábrica sea aleatoria,
distinta por instalación, recuperable una sola vez desde archivo, y que
cambiarla limpie la bandera que fuerza pasar por /setup.
"""
import importlib
import os
import stat

import pytest


@pytest.fixture()
def anyio_backend():
    return "asyncio"


@pytest.fixture()
def auth(tmp_path, monkeypatch):
    from app.backend import db as db_module
    from app.api import auth_api as _auth

    db_path = str(tmp_path / "network_monitor_test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(db_module, "STORAGE_DB", str(tmp_path))
    importlib.reload(_auth)
    monkeypatch.setattr(_auth, "STORAGE_DB", str(tmp_path))
    monkeypatch.setattr(_auth, "FACTORY_PASSWORD_FILE", str(tmp_path / ".factory_root_password"))
    yield _auth


def test_password_de_fabrica_no_es_shomer2026(auth):
    auth._ensure_users_table()
    con = auth._get_conn()
    row = con.execute("SELECT password_hash FROM users WHERE username='root'").fetchone()
    con.close()
    assert row["password_hash"] != auth._hash_password("shomer2026")


def test_password_de_fabrica_es_distinta_en_cada_instalacion(tmp_path, monkeypatch):
    from app.backend import db as db_module
    from app.api import auth_api as _auth

    passwords = []
    for i in range(2):
        db_path = str(tmp_path / f"nm_{i}.db")
        monkeypatch.setattr(db_module, "DB_PATH", db_path)
        importlib.reload(_auth)
        monkeypatch.setattr(_auth, "FACTORY_PASSWORD_FILE", str(tmp_path / f"factory_{i}"))
        _auth._ensure_users_table()
        with open(tmp_path / f"factory_{i}") as f:
            passwords.append(f.read().strip())

    assert passwords[0] != passwords[1]
    assert all(len(p) >= 10 for p in passwords)


def test_archivo_de_password_queda_con_permisos_600(auth, tmp_path):
    auth._ensure_users_table()
    factory_file = tmp_path / ".factory_root_password"
    assert factory_file.is_file()
    mode = stat.S_IMODE(os.stat(factory_file).st_mode)
    assert mode == 0o600


def test_must_change_password_activo_para_root_de_fabrica(auth):
    auth._ensure_users_table()
    con = auth._get_conn()
    row = con.execute(
        "SELECT must_change_password FROM users WHERE username='root'"
    ).fetchone()
    con.close()
    assert row["must_change_password"] == 1


def test_no_se_recrea_root_si_hay_otro_admin_ya_creado(auth):
    """Sesión 79: el bug original era que 'root' volvía a aparecer con la
    contraseña de fábrica en cada acción del panel aunque un admin ya
    hubiera creado su propia cuenta y borrado root a propósito -- una
    puerta trasera de facto mientras la tabla tuviera algún usuario. La
    guarda es "tabla vacía", no "sin root": con otro admin ya presente,
    borrar root debe quedar borrado."""
    auth._ensure_users_table()
    con = auth._get_conn()
    con.execute(
        "INSERT INTO users (username, password_hash, role) VALUES ('jp_admin', 'x', 'admin')"
    )
    con.execute("DELETE FROM users WHERE username='root'")
    con.commit()
    con.close()

    auth._ensure_users_table()
    con = auth._get_conn()
    row = con.execute("SELECT * FROM users WHERE username='root'").fetchone()
    con.close()
    assert row is None


def test_root_se_recrea_si_la_tabla_queda_completamente_vacia(auth):
    """Caso borde intencional: si se borra el ÚNICO usuario que existía, la
    tabla vuelve a estar vacía y el sistema debe recrear un acceso de
    fábrica -- la alternativa es un panel sin ningún admin posible, que es
    peor que una contraseña de fábrica aleatoria y de un solo uso."""
    auth._ensure_users_table()
    con = auth._get_conn()
    con.execute("DELETE FROM users WHERE username='root'")
    con.commit()
    con.close()

    auth._ensure_users_table()
    con = auth._get_conn()
    row = con.execute("SELECT * FROM users WHERE username='root'").fetchone()
    con.close()
    assert row is not None
    assert row["must_change_password"] == 1


@pytest.mark.anyio
async def test_login_con_password_de_fabrica_pide_redirect_a_setup(auth, tmp_path):
    auth._ensure_users_table()
    with open(tmp_path / ".factory_root_password") as f:
        factory_password = f.read().strip()

    from unittest.mock import MagicMock

    req = auth.LoginRequest(username="root", password=factory_password)
    request = MagicMock()
    request.headers = {}
    request.url.scheme = "https"

    resp = await auth.login(request, req)
    import json
    body = json.loads(resp.body)
    assert body["redirect"] == "/setup"


@pytest.mark.anyio
async def test_cambiar_password_limpia_must_change_password(auth, tmp_path):
    auth._ensure_users_table()
    con = auth._get_conn()
    user_id = con.execute("SELECT id FROM users WHERE username='root'").fetchone()["id"]
    con.close()

    req = auth.ChangePasswordRequest(password="unaClaveNueva123")
    current = {"role": "admin", "username": "root"}
    await auth.change_user_password(user_id, req, current)

    con = auth._get_conn()
    row = con.execute(
        "SELECT must_change_password, password_hash FROM users WHERE id=?", (user_id,)
    ).fetchone()
    con.close()
    assert row["must_change_password"] == 0
    assert row["password_hash"] == auth._hash_password("unaClaveNueva123")


class TestLongitudMinima:
    def test_ocho_caracteres_es_el_minimo_al_crear_usuario(self, auth):
        assert "8 caracteres" in _extraer_mensaje_min(auth, crear=True)

    def test_ocho_caracteres_es_el_minimo_al_cambiar_password(self, auth):
        assert "8 caracteres" in _extraer_mensaje_min(auth, crear=False)


def _extraer_mensaje_min(auth, crear: bool) -> str:
    import inspect
    src = inspect.getsource(auth.create_user if crear else auth.change_user_password)
    for line in src.splitlines():
        if "ontraseña" in line and "caracteres" in line:
            return line
    return ""
