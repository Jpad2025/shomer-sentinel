"""La subred a barrer es la real del sitio, nunca una fija.

12 sep 2026. Antes MAC_RECONCILE_SUBNET era un default puesto a mano,
"192.168.0.0/24" -- la red de Ópera al momento de escribir el módulo. Ahí
funcionaba por coincidencia (su LAN real es exactamente esa). Verificado en
vivo: en los 3 labs, cuya LAN real es 192.168.1.0/24, el proceso llevaba todo
ese tiempo barriendo la red equivocada, en silencio, sin ningún error.

Pedido explícito de Juan Pablo (12 sep): "hay que generar un mecanismo que
funcione de manera genérica para cualquier cliente, cualquier hotel, ...
inclusive con la Ópera, por si llega a cambiar la subnet o la red." Dos
cosas que probar entonces: que funcione en cualquier sitio, Y que siga a un
sitio que cambia de red sin necesitar un reinicio ni un cambio de código.
"""
import unittest
from unittest.mock import patch

from app.api import shomer_mac_reconcile as mr


class TestResuelveLaRedDelSitio(unittest.TestCase):
    def test_usa_base_subnet_del_sitio_cuando_no_hay_override(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("MAC_RECONCILE_SUBNET", None)
            with patch(
                "app.scripts.network_context.get_network_context",
                return_value={"subnet": "10.20.30.0/24"},
            ):
                self.assertEqual(mr._resolve_subnet(), "10.20.30.0/24")

    def test_el_override_explicito_manda_sobre_todo(self):
        with patch.dict("os.environ", {"MAC_RECONCILE_SUBNET": "172.16.5.0/24"}):
            with patch("app.scripts.network_context.get_network_context",
                      return_value={"subnet": "10.20.30.0/24"}) as m:
                self.assertEqual(mr._resolve_subnet(), "172.16.5.0/24")
                m.assert_not_called()

    def test_sin_ninguna_fuente_no_inventa_una_red(self):
        """El fallo exacto que existía: adivinar 192.168.0.0/24 en vez de
        admitir que no se sabe."""
        import os
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("MAC_RECONCILE_SUBNET", None)
            with patch("app.scripts.network_context.get_network_context",
                      return_value={"subnet": None}):
                self.assertIsNone(mr._resolve_subnet())

    def test_un_error_al_detectar_no_rompe_ni_inventa_nada(self):
        import os
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("MAC_RECONCILE_SUBNET", None)
            with patch("app.scripts.network_context.get_network_context",
                      side_effect=RuntimeError("sin interfaz")):
                self.assertIsNone(mr._resolve_subnet())

    def test_ningun_valor_de_opera_queda_como_default_fijo(self):
        """Ópera funcionaba por coincidencia -- que no vuelva a ser un
        literal escrito a mano en el CÓDIGO ejecutable (el docstring sí puede
        mencionarlo como contexto histórico, eso no es el bug)."""
        import ast
        import inspect
        arbol = ast.parse(inspect.getsource(mr._resolve_subnet))
        fn = arbol.body[0]
        cuerpo_sin_docstring = fn.body[1:] if ast.get_docstring(fn) else fn.body
        codigo = ast.unparse(ast.Module(body=cuerpo_sin_docstring, type_ignores=[]))
        self.assertNotIn("192.168.0", codigo)


class TestSigueASiUnSitioCambiaDeRed(unittest.TestCase):
    """El requisito explícito: Ópera (o cualquier cliente) puede cambiar de
    proveedor o de rango algún día, y esto debe seguirlo SIN reinicio."""

    def test_dos_ciclos_con_redes_distintas_sin_reiniciar_nada(self):
        import os
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("MAC_RECONCILE_SUBNET", None)
            with patch("app.scripts.network_context.get_network_context",
                      return_value={"subnet": "192.168.5.0/24"}):
                primero = mr._resolve_subnet()
            with patch("app.scripts.network_context.get_network_context",
                      return_value={"subnet": "10.1.1.0/24"}):
                segundo = mr._resolve_subnet()
        self.assertEqual(primero, "192.168.5.0/24")
        self.assertEqual(segundo, "10.1.1.0/24")
        self.assertNotEqual(primero, segundo, "debe reflejar el cambio de red al vuelo")


class TestElBarridoUsaLaSubredResuelta(unittest.TestCase):
    def test_sin_subred_no_barre_nada_y_lo_dice(self):
        """Preferible admitir que no se sabe a barrer una red inventada."""
        with patch.object(mr, "_resolve_subnet", return_value=None):
            with patch.object(mr, "_ping_sweep") as ping:
                resultado = mr._scan_mac_ip()
        ping.assert_not_called()
        self.assertEqual(resultado, {})

    def test_con_subred_barre_exactamente_esa_y_ninguna_otra(self):
        """El fallo real: pinguear siempre 192.168.0.0/24 sin importar el sitio."""
        with patch.object(mr, "_resolve_subnet", return_value="10.7.7.0/24"):
            with patch.object(mr, "_ping_sweep") as ping, \
                 patch("subprocess.run") as run:
                run.return_value.stdout = "[]"
                mr._scan_mac_ip()
        ping.assert_called_once_with("10.7.7.0/24")


class TestCasoRealOperaYLabs(unittest.TestCase):
    """El caso concreto que motivó el arreglo: Ópera funcionaba por
    coincidencia, los 3 labs barrían la red equivocada."""

    def test_opera_con_su_red_real_resuelve_correcto(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("MAC_RECONCILE_SUBNET", None)
            with patch("app.scripts.network_context.get_network_context",
                      return_value={"subnet": "192.168.0.0/24"}):
                self.assertEqual(mr._resolve_subnet(), "192.168.0.0/24")

    def test_un_lab_con_su_propia_red_ya_no_hereda_la_de_opera(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("MAC_RECONCILE_SUBNET", None)
            with patch("app.scripts.network_context.get_network_context",
                      return_value={"subnet": "192.168.1.0/24"}):
                resultado = mr._resolve_subnet()
        self.assertEqual(resultado, "192.168.1.0/24")
        self.assertNotEqual(resultado, "192.168.0.0/24")


if __name__ == "__main__":
    unittest.main()
