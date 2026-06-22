"""Protector SMB — parseo de ruta subcarpeta y filtros de fecha."""
import asyncio
import unittest
from datetime import date
import os
from unittest.mock import patch

from app.api import backups as bm


class TestParseSmbSourcePath(unittest.TestCase):
    def test_share_only(self):
        self.assertEqual(bm._parse_smb_source_path("backups"), ("backups", ""))

    def test_admin_share_subpath(self):
        self.assertEqual(
            bm._parse_smb_source_path(r"C$\back_bases\Copias Diarias"),
            ("C$", "back_bases/Copias Diarias"),
        )

    def test_forward_slashes(self):
        self.assertEqual(
            bm._parse_smb_source_path("C$/back_bases/Copias Diarias"),
            ("C$", "back_bases/Copias Diarias"),
        )

    def test_drive_colon_autocorrected_to_admin_share(self):
        """'C:' no es un share SMB válido -- error común al copiar la ruta de Windows.
        Debe corregirse a 'C$' (admin share real) en vez de fallar como credencial mala."""
        self.assertEqual(
            bm._parse_smb_source_path("C:/back_bases/Copias Diarias"),
            ("C$", "back_bases/Copias Diarias"),
        )

    def test_drive_colon_backslash_autocorrected(self):
        self.assertEqual(
            bm._parse_smb_source_path(r"D:\backups"),
            ("D$", "backups"),
        )

    def test_drive_colon_only_no_subpath(self):
        self.assertEqual(bm._parse_smb_source_path("E:"), ("E$", ""))


class TestCifsCredentialsContent(unittest.TestCase):
    """mount.cifs no entiende 'DOMINIO\\usuario' embebido en username= como lo
    hace Windows -- hay que separarlo en domain= o la auth falla con
    Permission denied aunque la contraseña sea correcta."""

    def test_dot_backslash_is_local_account_no_domain_line(self):
        content = bm._cifs_credentials_content(r".\administrador", "Secreta1*")
        self.assertIn("username=administrador\n", content)
        self.assertIn("password=Secreta1*\n", content)
        self.assertNotIn("domain=", content)

    def test_real_domain_is_split_out(self):
        content = bm._cifs_credentials_content(r"HOTELOPERA\administrador", "x")
        self.assertIn("username=administrador\n", content)
        self.assertIn("domain=HOTELOPERA\n", content)

    def test_plain_username_no_backslash(self):
        content = bm._cifs_credentials_content("administrador", "x")
        self.assertIn("username=administrador\n", content)
        self.assertNotIn("domain=", content)


class TestDeviceTestPasswordFallback(unittest.TestCase):
    """El botón 'Probar conexión' del panel reenvía '***' literal si el técnico
    no vuelve a escribir la contraseña tras editar un equipo ya guardado --
    el endpoint debe descifrar la contraseña real de BD en ese caso."""

    def _run(self, body):
        return asyncio.run(bm.test_backup_device(body=body, _admin={"username": "test"}))

    def test_mask_falls_back_to_decrypted_db_password(self):
        captured = {}

        def fake_mount(ip, share, username, password, mount_point):
            captured["password"] = password
            return None  # simula mount exitoso, sin tocar el filesystem real

        class FakeRow(dict):
            pass

        class FakeConn:
            def execute(self, *a, **kw):
                return self
            def fetchone(self):
                return FakeRow(password=bm._encrypt_device_password("ClaveReal123"))
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        with patch.object(bm, "_smb_mount_readonly", side_effect=fake_mount), \
             patch.object(bm, "_get_db", return_value=FakeConn()):
            result = self._run({
                "device_id": 99,
                "ip": "192.168.0.5",
                "username": "administrador",
                "password": "***",
                "device_type": "windows",
                "source_path": "backups",  # share-only: evita resolver subcarpeta en disco real
            })

        self.assertTrue(result["success"])
        self.assertEqual(captured["password"], "ClaveReal123")

    def test_empty_password_without_device_id_stays_empty(self):
        """Sin device_id no hay BD que consultar -- debe seguir usando '' tal cual
        (comportamiento previo, para equipos nuevos aún no guardados)."""
        captured = {}

        def fake_mount(ip, share, username, password, mount_point):
            captured["password"] = password
            return None

        with patch.object(bm, "_smb_mount_readonly", side_effect=fake_mount):
            self._run({
                "ip": "192.168.0.5",
                "username": "administrador",
                "password": "",
                "device_type": "windows",
                "source_path": "backups",
            })

        self.assertEqual(captured["password"], "")


class TestExpandIncludePattern(unittest.TestCase):
    @patch.object(bm, "_dt")
    def test_today_tokens(self, mock_dt):
        mock_dt.now.return_value.date.return_value = date(2026, 6, 19)
        mock_dt.utcnow.return_value.date.return_value = date(2026, 6, 19)
        with patch.object(bm, "_get_system_state", return_value="America/Bogota"):
            out = bm._expand_include_pattern("*_{today}_*")
        self.assertEqual(out, "*_2026_06_19_*")

    @patch.object(bm, "_dt")
    def test_today_compact(self, mock_dt):
        mock_dt.now.return_value.date.return_value = date(2026, 6, 19)
        mock_dt.utcnow.return_value.date.return_value = date(2026, 6, 19)
        with patch.object(bm, "_get_system_state", return_value="America/Bogota"):
            out = bm._expand_include_pattern("*{today_compact}*")
        self.assertEqual(out, "*20260619*")


class TestBackupWindowsIncludeTargets(unittest.TestCase):
    """restic backup no soporta --include (solo restore/dump/ls) -- _backup_windows debe
    resolver el patrón a archivos reales y pasarlos como targets directos, no como bandera."""

    def test_only_matching_files_passed_as_targets(self):
        import tempfile as _tf

        tmp_mount = _tf.mkdtemp(prefix="test_mount_")
        try:
            open(os.path.join(tmp_mount, "ActivosFijos_backup_2026_06_19_x.bak"), "w").close()
            open(os.path.join(tmp_mount, "ActivosFijos_backup_2026_06_18_x.bak"), "w").close()
            open(os.path.join(tmp_mount, "otro_archivo.txt"), "w").close()

            captured = {}

            def fake_restic_run(cmd, **kw):
                captured["cmd"] = cmd
                class R:
                    returncode = 0
                    stdout = "snapshot abc123 saved\nFiles: 1 new\nAdded to the repo: 1.000 KiB\n"
                    stderr = ""
                return R()

            device = {
                "id": 1, "name": "SRV Zeus PMS", "ip": "192.168.0.5",
                "username": ".\\administrador",
                "password": bm._encrypt_device_password("opera2023*"),
                "source_path": "backups", "include_pattern": "*2026_06_19*",
                "schedule_b2_enabled": 0,
            }

            with patch.object(bm, "SMB_MOUNT_BASE", os.path.dirname(tmp_mount)), \
                 patch.object(bm.os.path, "isdir", return_value=True), \
                 patch.object(bm, "_smb_resolve_backup_target", return_value=tmp_mount), \
                 patch.object(bm, "_telegram"), \
                 patch.object(bm, "_update_device_status"), \
                 patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})(),  # mount.cifs
                    fake_restic_run(None),  # restic backup
                ]
                asyncio.run(bm._backup_windows(device))

            cmd = mock_run.call_args_list[1].args[0]
            targets = [a for a in cmd if a.endswith(".bak") or a.endswith(".txt")]
            self.assertEqual(len(targets), 1)
            self.assertIn("2026_06_19", targets[0])
            self.assertNotIn("--include", cmd)
        finally:
            import shutil as _sh
            _sh.rmtree(tmp_mount, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
