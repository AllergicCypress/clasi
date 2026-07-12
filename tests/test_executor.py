"""
Pruebas de regresión para executor.py.

Protege:
  - resolver_conflicto nunca sobreescribe (política "skip" → None)
  - rename_new genera nombres únicos
  - deshacer revierte en orden inverso
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from clasi.executor import deshacer, resolver_conflicto


class TestResolverConflicto(unittest.TestCase):
    def test_destino_libre_devuelve_la_misma_ruta(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destino = Path(tmpdir) / "archivo.pdf"
            resultado = resolver_conflicto(destino, "skip")
            self.assertEqual(resultado, destino)

    def test_skip_con_archivo_existente_devuelve_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destino = Path(tmpdir) / "archivo.pdf"
            destino.write_text("contenido")
            resultado = resolver_conflicto(destino, "skip")
            self.assertIsNone(resultado)

    def test_rename_new_genera_ruta_unica(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destino = Path(tmpdir) / "archivo.pdf"
            destino.write_text("original")
            resultado = resolver_conflicto(destino, "rename_new")
            self.assertIsNotNone(resultado)
            self.assertNotEqual(resultado, destino)
            self.assertFalse(resultado.exists())

    def test_rename_new_incrementa_sufijo_si_ya_existe(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destino = Path(tmpdir) / "archivo.pdf"
            destino.write_text("v1")
            (Path(tmpdir) / "archivo_1.pdf").write_text("v2")
            resultado = resolver_conflicto(destino, "rename_new")
            self.assertEqual(resultado.name, "archivo_2.pdf")


class TestDeshacer(unittest.TestCase):
    def test_revierte_operacion_simple(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            origen = raiz / "origen" / "archivo.txt"
            destino = raiz / "destino" / "archivo.txt"

            origen.parent.mkdir()
            destino.parent.mkdir()
            destino.write_text("contenido")

            ruta_log = raiz / "clasi.log"
            with open(ruta_log, "w") as f:
                f.write(json.dumps({
                    "accion": "mover",
                    "archivo": str(origen),
                    "destino": str(destino),
                    "regla": "descubrimiento",
                    "confianza": "alta",
                    "ts": "2026-01-01T00:00:00",
                }) + "\n")

            revertidas = deshacer(ruta_log)

            self.assertEqual(len(revertidas), 1)
            self.assertTrue(origen.exists())
            self.assertFalse(destino.exists())

    def test_revierte_en_orden_inverso(self):
        # Si se movieron A→X y luego B→X/sub, el undo debe revertir B primero
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            orden = []

            a_orig = raiz / "a_orig.txt"
            a_dest = raiz / "dest" / "a_orig.txt"
            b_orig = raiz / "b_orig.txt"
            b_dest = raiz / "dest" / "b_orig.txt"

            (raiz / "dest").mkdir()
            a_dest.write_text("a")
            b_dest.write_text("b")

            ruta_log = raiz / "clasi.log"
            with open(ruta_log, "w") as f:
                # primera operación: a, segunda: b
                for archivo, destino in [(a_orig, a_dest), (b_orig, b_dest)]:
                    f.write(json.dumps({
                        "accion": "mover",
                        "archivo": str(archivo),
                        "destino": str(destino),
                        "regla": "test",
                        "confianza": "alta",
                        "ts": "2026-01-01T00:00:00",
                    }) + "\n")

            revertidas = deshacer(ruta_log)
            # Debe revertir las dos
            self.assertEqual(len(revertidas), 2)
            # b_orig debe existir (fue la segunda → se revirtió primero)
            self.assertTrue(b_orig.exists())
            self.assertTrue(a_orig.exists())

    def test_log_inexistente_devuelve_lista_vacia(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ruta_log = Path(tmpdir) / "no_existe.log"
            resultado = deshacer(ruta_log)
            self.assertEqual(resultado, [])

    def test_ignora_operaciones_que_no_son_mover(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ruta_log = Path(tmpdir) / "clasi.log"
            with open(ruta_log, "w") as f:
                f.write(json.dumps({"accion": "skip", "archivo": "/fake", "razon": "destino_existe", "regla": "test"}) + "\n")
            revertidas = deshacer(ruta_log)
            self.assertEqual(revertidas, [])


if __name__ == "__main__":
    unittest.main()
