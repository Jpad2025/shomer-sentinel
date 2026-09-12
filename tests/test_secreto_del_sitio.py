"""Las herramientas de consola deben usar el MISMO secreto que los servicios.

11 sep 2026. systemd le pasa JWT_SECRET a los servicios por EnvironmentFile,
asi que una herramienta lanzada a mano por el tecnico no lo tenia en su
entorno y caia al literal por defecto del repositorio. No era solo el aviso
enganoso ("JWT_SECRET usa valor por defecto") apareciendo en un sitio bien
configurado: la clave de cifrado de credenciales de Protector se deriva de
ese valor, asi que cualquier script de mantenimiento fallaba de verdad al
descifrar la contrasena del equipo de respaldo -- confirmado en Opera con un
ValueError sobre la credencial de 'SRV Zeus PMS'.

Ademas el instalador dejaba el permiso muerto: creaba shomer-runtime.env como
640 root:$SERVICE_USER pero /etc/shomer como root:root 750, de modo que el
usuario del servicio no podia entrar al directorio a leerlo.
"""
import importlib
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


def _recargar_auth(runtime_file: str, entorno: dict):
    """Recarga auth_api con un entorno controlado.

    Si la prueba no define JWT_SECRET, se quita del entorno: en un equipo donde
    ya este exportado, dejarlo taparia justo lo que se quiere comprobar.
    """
    entorno = dict(entorno)
    entorno["SHOMER_RUNTIME_ENV"] = runtime_file
    with patch.dict(os.environ, entorno, clear=False):
        if "JWT_SECRET" not in entorno:
            os.environ.pop("JWT_SECRET", None)
        from app.api import auth_api

        return importlib.reload(auth_api)


class TestSecretoDelSitio(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.env_file = str(Path(self.tmp.name) / "shomer-runtime.env")
        Path(self.env_file).write_text(
            "JWT_SECRET=secreto-propio-de-este-hotel\nSHOMER_JWT_EXPIRE_HOURS=1\n"
        )

    def tearDown(self):
        self.tmp.cleanup()
        from app.api import auth_api
        importlib.reload(auth_api)

    def test_consola_toma_el_secreto_del_archivo_de_runtime(self):
        """Sin JWT_SECRET en el entorno, se lee el del sitio, no el literal."""
        a = _recargar_auth(self.env_file, {})
        self.assertEqual(a.JWT_SECRET, "secreto-propio-de-este-hotel")
        self.assertNotEqual(a.JWT_SECRET, a._DEFAULT_JWT)

    def test_el_entorno_manda_sobre_el_archivo(self):
        """El servicio recibe el suyo por systemd: ese tiene prioridad."""
        a = _recargar_auth(self.env_file, {"JWT_SECRET": "el-del-servicio"})
        self.assertEqual(a.JWT_SECRET, "el-del-servicio")

    def test_sin_archivo_legible_no_se_inventa_un_secreto(self):
        """Sin poder confirmarlo se cae al default, que ya avisa por log."""
        a = _recargar_auth(str(Path(self.tmp.name) / "no-existe.env"), {})
        self.assertEqual(a.JWT_SECRET, a._DEFAULT_JWT)

    def test_valor_entre_comillas(self):
        Path(self.env_file).write_text('JWT_SECRET="con-comillas"\n')
        a = _recargar_auth(self.env_file, {})
        self.assertEqual(a.JWT_SECRET, "con-comillas")


class TestProtectorUsaElMismoSecreto(unittest.TestCase):
    def test_la_clave_de_credenciales_sale_del_secreto_resuelto(self):
        """Lo que cifra el servicio lo descifra la consola, y al reves."""
        from app.api import backups

        with patch("app.api.auth_api.JWT_SECRET", "secreto-propio-de-este-hotel"):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("BACKUP_CRED_SECRET", None)
                cifrada = backups._encrypt_device_password("clave-real")
                self.assertEqual(backups._decrypt_device_password(cifrada), "clave-real")
                clave_sitio = backups._enc_key_material()

        # Con el literal por defecto la clave debe ser OTRA: si fuera la misma,
        # el secreto del sitio no estaria entrando en la derivacion.
        with patch("app.api.auth_api.JWT_SECRET", backups_default()):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("BACKUP_CRED_SECRET", None)
                self.assertNotEqual(backups._enc_key_material(), clave_sitio)


def backups_default():
    from app.api.auth_api import _DEFAULT_JWT
    return _DEFAULT_JWT


class TestInstaladorDejaLeerElArchivo(unittest.TestCase):
    def test_el_directorio_va_al_grupo_del_usuario_del_servicio(self):
        """Con /etc/shomer en root:root 750 el permiso 640 del archivo es letra muerta."""
        sh = Path(__file__).resolve().parents[1] / "tools" / "install_shomer.sh"
        texto = sh.read_text()
        self.assertIn('chown root:"$SERVICE_USER" "$CONF_DIR"', texto)
        self.assertNotIn('chown root:root "$CONF_DIR"', texto)
        self.assertIn('chmod 750 "$CONF_DIR"', texto)


if __name__ == "__main__":
    unittest.main()
