"""Auditoría de Protector — Sesión 82.

Dos bugs reales encontrados contra el sitio de producción:

1. _parse_restic_stats buscaba "Added to the repository:" (redacción de restic
   0.14+) pero el binario instalado es 0.12.1, que imprime "Added to the repo:".
   La regex no matcheaba nunca, así que last_size_mb quedaba NULL en todas las
   copias y el técnico no veía el tamaño ni en el panel ni en Telegram -- que es
   justo la señal que delata un backup que se encogió.
2. Sin b2_path, el repo B2 caía a la RAÍZ del bucket, mezclando los backups de
   todos los clientes en un repositorio Restic indistinguible (contra la norma
   D.1 del proyecto). Ópera se salvaba solo por el slug de base.client_name.
"""
import unittest
from unittest.mock import patch

from app.api.backups import (
    B2_PATH_FALTANTE,
    _b2_repo_url,
    _parse_restic_stats,
)

# Salida real capturada del restic 0.12.1 instalado en el servidor de Ópera.
SALIDA_012 = """no parent snapshot found, will read all files

Files:           9 new,     0 changed,     0 unmodified
Dirs:            2 new,     0 changed,     0 unmodified
Added to the repo: 1.145 KiB

processed 9 files, 1.234 GiB in 0:38
snapshot bda4a7ea saved"""

# Redacción de restic 0.14+, por si el binario se actualiza.
SALIDA_014 = """Files:           9 new,     0 changed,     0 unmodified
Added to the repository: 512.5 MiB (498.2 MiB stored)

processed 9 files, 1.234 GiB in 0:38
snapshot bda4a7ea saved"""


class TestParseResticStats(unittest.TestCase):
    def test_version_instalada_0_12(self):
        s = _parse_restic_stats(SALIDA_012)
        self.assertEqual(s.get("snapshot_id"), "bda4a7ea")
        self.assertEqual(s.get("total_files"), 9)
        self.assertIsNotNone(
            s.get("size_mb"),
            "el tamaño no puede quedar en None: es lo que delata un backup encogido",
        )
        self.assertAlmostEqual(s["size_mb"], 1263.616, places=2)

    def test_version_futura_0_14(self):
        s = _parse_restic_stats(SALIDA_014)
        self.assertEqual(s.get("snapshot_id"), "bda4a7ea")
        self.assertAlmostEqual(s["size_mb"], 1263.616, places=2)
        self.assertAlmostEqual(s["added_mb"], 512.5, places=1)

    def test_size_es_el_total_no_el_delta(self):
        """Con deduplicación el delta diario es ~0 aunque la copia esté sana:
        si size_mb fuera el delta, el panel mostraría 0 MB todos los días."""
        s = _parse_restic_stats(SALIDA_012)
        self.assertGreater(s["size_mb"], 1000)
        self.assertLess(s["added_mb"], 1)

    def test_salida_vacia_no_rompe(self):
        self.assertEqual(_parse_restic_stats(""), {})


class TestB2PathObligatorio(unittest.TestCase):
    def test_path_valido(self):
        self.assertEqual(
            _b2_repo_url("shomer-backups", "hotel-opera"),
            "b2:shomer-backups:hotel-opera",
        )

    def test_vacio_es_rechazado(self):
        for malo in ("", "   ", "/", None):
            with self.assertRaises(ValueError, msg=f"debió rechazar {malo!r}"):
                _b2_repo_url("shomer-backups", malo)

    def test_mensaje_es_accionable(self):
        self.assertIn("b2_path", B2_PATH_FALTANTE)
        self.assertIn("base.client_name", B2_PATH_FALTANTE)

    def test_prune_b2_se_cancela_sin_path(self):
        """Nunca debe correr forget --prune contra la raíz compartida."""
        from app.api import backups as b

        cfg = {
            "b2_account_id": "x", "b2_app_key": "y",
            "b2_bucket": "shomer-backups", "b2_password": "p",
        }
        with patch.object(b, "_get_b2_config", return_value=cfg), \
             patch.object(b, "_effective_b2_path", return_value=""), \
             patch.object(b, "get_restic_password", return_value="p"), \
             patch.object(b.subprocess, "run") as run:
            self.assertFalse(b._prune_b2())
            run.assert_not_called()

    def test_sync_sin_path_devuelve_mensaje_no_excepcion(self):
        from app.api import backups as b

        with patch.object(b, "get_restic_password", return_value="p"):
            r = b._b2_sync_blocking("id", "key", "shomer-backups", "", "pass")
        self.assertFalse(r["success"])
        self.assertIn("b2_path", r["message"])


if __name__ == "__main__":
    unittest.main()
