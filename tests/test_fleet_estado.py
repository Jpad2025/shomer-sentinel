"""El verificador de flota: que detecte lo que nadie estaba mirando.

12 sep 2026. Nueve archivos del core llevaban días corriendo en producción sin
commitear y los tres labs no los tenían. Nada lo detectó porque nada lo
buscaba: el servicio funcionaba, las pruebas pasaban y `git log` se veía
limpio.

La trampa de esta herramienta es que puede "funcionar" dando siempre el
resultado tranquilizador. Ya pasó una vez mientras se escribía: el guion iba
dentro de la línea de comando de ssh, el shell LOCAL expandía el
`$(git rev-parse ...)` antes de que viajara y cada sitio respondía con datos
del maestro -- todo salía "al día". Por eso se prueba que el guion viaje por
la entrada estándar y no como argumento.
"""
import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

_ruta = Path(__file__).resolve().parents[1] / "tools" / "fleet_estado.py"
_spec = importlib.util.spec_from_file_location("fleet_estado", _ruta)
fe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fe)


class TestQueEsDelSitioYQueEsDelProducto(unittest.TestCase):
    """Confundirlos arruina la herramienta en las dos direcciones."""

    def test_lo_propio_de_cada_instalacion_no_es_deriva(self):
        for ruta in (".env", "SITE.md", "tools/servers.txt", "data/devices.json",
                     "storage/network_monitor.db", "app/__pycache__/x.pyc",
                     "venv/bin/python", "tools/fleet_sync.log"):
            self.assertTrue(fe.es_del_sitio(ruta), ruta)

    def test_el_codigo_del_producto_si_cuenta(self):
        for ruta in ("app/api/backups.py", "tools/install_shomer.sh",
                     "tests/test_x.py", "app/static/panel.html"):
            self.assertFalse(fe.es_del_sitio(ruta), ruta)

    def test_un_reporte_de_sitio_no_es_documentacion_generica(self):
        """12 sep 2026: un reporte con nombres de equipos de un hotel puntual
        ya se propago una vez a los 3 labs por vivir en docs/ compartido."""
        for ruta in ("docs/sitios/opera/REPORTE_CAIDAS_POS.md",
                     "docs/sitios/hotel-nuevo/notas.md"):
            self.assertTrue(fe.es_del_sitio(ruta), ruta)
        self.assertFalse(fe.es_del_sitio("docs/GUIA_PROYECTO_SHOMER.md"))

    def test_un_env_de_ejemplo_es_del_producto(self):
        """`.env` es del sitio; `.env.example` se versiona y debe viajar igual."""
        self.assertFalse(fe.es_del_sitio(".env.example"))


class TestComparacion(unittest.TestCase):
    def test_detecta_lo_que_falta_lo_que_difiere_y_lo_que_sobra(self):
        maestro = {"presente": True, "hashes": {"a.py": "1", "b.py": "2", "c.py": "3"}}
        sitio = {"presente": True, "hashes": {"a.py": "1", "b.py": "DISTINTO", "d.py": "9"}}
        r = fe.comparar(maestro, sitio)
        self.assertEqual(r["faltan"], ["c.py"])
        self.assertEqual(r["difieren"], ["b.py"])
        self.assertEqual(r["sobran"], ["d.py"])

    def test_iguales_no_reportan_nada(self):
        m = {"presente": True, "hashes": {"a.py": "1"}}
        r = fe.comparar(m, dict(m))
        self.assertEqual((r["faltan"], r["difieren"], r["sobran"]), ([], [], []))

    def test_commits_distintos_con_mismo_contenido_no_son_deriva(self):
        """Cada sitio reconcilia con commits propios: comparar hashes de git miente."""
        m = {"presente": True, "head": "aaaaaaa", "hashes": {"a.py": "1"}}
        s = {"presente": True, "head": "zzzzzzz", "hashes": {"a.py": "1"}}
        self.assertEqual(fe.comparar(m, s)["difieren"], [])


class TestVeredicto(unittest.TestCase):
    def _revisar(self, respuestas):
        with patch.object(fe, "inspeccionar", side_effect=respuestas):
            return fe.revisar(["lab1"], ["/opt/network_monitor"])

    def test_sin_commitear_en_el_maestro_rompe_la_consistencia(self):
        """El caso real: código vivo en producción que no está en ningún historial."""
        maestro = {"alcanzable": True, "presente": True, "head": "abc",
                   "sin_commitear": ["app/api/inventory.py"], "hashes": {"a.py": "1"}}
        sitio = {"alcanzable": True, "presente": True, "head": "abc",
                 "sin_commitear": [], "hashes": {"a.py": "1"}}
        r = self._revisar([maestro, sitio])
        self.assertFalse(r["consistente"])
        self.assertIn("sin commitear", fe.redactar(r))
        self.assertIn("inventory.py", fe.redactar(r))

    def test_todo_igual_da_consistente(self):
        igual = {"alcanzable": True, "presente": True, "head": "abc",
                 "sin_commitear": [], "hashes": {"a.py": "1"}}
        r = self._revisar([dict(igual), dict(igual)])
        self.assertTrue(r["consistente"])
        self.assertIn("al día", fe.redactar(r))

    def test_un_host_caido_no_se_da_por_bueno(self):
        maestro = {"alcanzable": True, "presente": True, "head": "abc",
                   "sin_commitear": [], "hashes": {"a.py": "1"}}
        r = self._revisar([maestro, {"alcanzable": False, "detalle": "timeout"}])
        self.assertFalse(r["consistente"], "no responder no es estar al día")
        self.assertIn("no responde", fe.redactar(r))

    def test_el_texto_no_exige_saber_git(self):
        maestro = {"alcanzable": True, "presente": True, "head": "abc",
                   "sin_commitear": [], "hashes": {"a.py": "1", "b.py": "2"}}
        sitio = {"alcanzable": True, "presente": True, "head": "abc",
                 "sin_commitear": [], "hashes": {"a.py": "1"}}
        texto = fe.redactar(self._revisar([maestro, sitio]))
        self.assertIn("le faltan", texto)
        self.assertIn("b.py", texto)


class TestElGuionViajaPorLaEntradaEstandar(unittest.TestCase):
    """La regresión que ya ocurrió: metido en la línea de comando, el shell
    local expandía `$(git rev-parse ...)` y todos los sitios contestaban con
    datos del maestro. El verificador decía "al día" sin haber mirado nada."""

    def test_no_se_interpola_en_el_comando(self):
        vistos = {}

        def falso_run(argv, **kw):
            vistos["argv"] = argv
            vistos["input"] = kw.get("input", "")
            return subprocess.CompletedProcess(argv, 0, stdout="HEAD abc\n", stderr="")

        with patch("subprocess.run", side_effect=falso_run):
            fe.inspeccionar("lab1", "/opt/network_monitor")

        self.assertIn("git rev-parse", vistos["input"])
        for arg in vistos["argv"]:
            self.assertNotIn("git rev-parse", arg,
                             "el guion no puede ir como argumento: lo expande el shell local")
        self.assertIn("bash", vistos["argv"])

    def test_el_maestro_no_pasa_por_ssh(self):
        vistos = {}

        def falso_run(argv, **kw):
            vistos["argv"] = argv
            return subprocess.CompletedProcess(argv, 0, stdout="HEAD abc\n", stderr="")

        with patch("subprocess.run", side_effect=falso_run):
            fe.inspeccionar("", "/opt/network_monitor")
        self.assertNotIn("ssh", vistos["argv"])


class TestLaGuardiaDelSync(unittest.TestCase):
    def test_el_sync_del_core_se_niega_con_el_maestro_sucio(self):
        """Propagar un árbol sucio reparte un estado que no está en ningún historial."""
        sh = (Path(__file__).resolve().parents[1] / "tools" / "fleet_sync_core.sh").read_text()
        self.assertIn("NO se sincroniza", sh)
        self.assertIn("PERMITIR_SUCIO", sh)
        self.assertIn("exit 2", sh)

    def test_no_copia_archivos_propios_del_sitio(self):
        sh = (Path(__file__).resolve().parents[1] / "tools" / "fleet_sync_core.sh").read_text()
        for propio in ("--exclude='.env'", "--exclude='SITE.md'", "--exclude='*.db'"):
            self.assertIn(propio, sh)

    def test_no_borra_en_el_remoto(self):
        """Se miran solo las líneas de código: el encabezado explica el criterio
        y menciona --delete, que no es lo mismo que usarlo."""
        sh = (Path(__file__).resolve().parents[1] / "tools" / "fleet_sync_core.sh").read_text()
        codigo = [l for l in sh.splitlines() if not l.lstrip().startswith("#")]
        self.assertNotIn("--delete", "\n".join(codigo))


if __name__ == "__main__":
    unittest.main()
