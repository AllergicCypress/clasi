"""
Pruebas de regresión para classifier.py.

Protege:
  - _evaluar_filtro aplica correctamente cada tipo de filtro
  - el filtro python no lanza excepción ante expresiones inválidas
  - tiene_merged detecta el par correcto (el original, no el merged)
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from clasi.classifier import _evaluar_filtro, _coincide_hint


class TestEvaluarFiltro(unittest.TestCase):
    def _archivo(self, nombre, tmpdir):
        p = Path(tmpdir) / nombre
        p.write_text("")
        return p

    def test_filtro_extension(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf = self._archivo("doc.pdf", tmpdir)
            txt = self._archivo("doc.txt", tmpdir)
            filtro = {"extension": [".pdf", ".PDF"]}
            self.assertTrue(_evaluar_filtro(pdf, "", filtro))
            self.assertFalse(_evaluar_filtro(txt, "", filtro))

    def test_filtro_extension_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            exe = self._archivo("setup.EXE", tmpdir)
            filtro = {"extension": [".exe"]}
            self.assertTrue(_evaluar_filtro(exe, "", filtro))

    def test_filtro_nombre_contiene(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dup = self._archivo("informe (1).pdf", tmpdir)
            orig = self._archivo("informe.pdf", tmpdir)
            filtro = {"nombre_contiene": ["(1)", "(2)"]}
            self.assertTrue(_evaluar_filtro(dup, "", filtro))
            self.assertFalse(_evaluar_filtro(orig, "", filtro))

    def test_filtro_texto_contiene(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archivo = self._archivo("doc.txt", tmpdir)
            filtro = {"texto_contiene": ["factura", "total"]}
            self.assertTrue(_evaluar_filtro(archivo, "esta es una factura", filtro))
            self.assertFalse(_evaluar_filtro(archivo, "apuntes de calculo", filtro))

    def test_filtro_tiene_merged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # El original tiene su versión merged → debe detectarse
            orig = Path(tmpdir) / "reporte.pdf"
            merged = Path(tmpdir) / "reporte_merged.pdf"
            orig.write_text("")
            merged.write_text("")
            filtro = {"tiene_merged": True}
            self.assertTrue(_evaluar_filtro(orig, "", filtro))
            # El merged en sí no tiene un "merged del merged"
            self.assertFalse(_evaluar_filtro(merged, "", filtro))

    def test_filtro_python_expresion_valida(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            iso = self._archivo("arch-2026.iso", tmpdir)
            filtro = {"python": "sufijo == '.iso'"}
            self.assertTrue(_evaluar_filtro(iso, "", filtro))

    def test_filtro_python_expresion_invalida_devuelve_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archivo = self._archivo("doc.txt", tmpdir)
            filtro = {"python": "esto no es python válido !!!"}
            # No debe lanzar excepción — devuelve False
            resultado = _evaluar_filtro(archivo, "", filtro)
            self.assertFalse(resultado)

    def test_filtro_python_sin_acceso_a_import(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archivo = self._archivo("doc.txt", tmpdir)
            # __import__ no debe estar disponible en el entorno del filtro
            filtro = {"python": "__import__('os').listdir('/')"}
            resultado = _evaluar_filtro(archivo, "", filtro)
            self.assertFalse(resultado)


class TestCoincideHint(unittest.TestCase):
    def _archivo(self, nombre, tmpdir):
        p = Path(tmpdir) / nombre
        p.write_text("")
        return p

    def test_modo_any_coincide_con_uno(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            exe = self._archivo("setup.exe", tmpdir)
            hint = {
                "filter_mode": "any",
                "filtros": [
                    {"extension": [".exe"]},
                    {"extension": [".msi"]},
                ],
            }
            self.assertTrue(_coincide_hint(exe, "", hint))

    def test_modo_all_requiere_todos(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # archivo.pdf con "(1)" en el nombre Y texto corrupto
            archivo = self._archivo("informe (1).pdf", tmpdir)
            hint_all = {
                "filter_mode": "all",
                "filtros": [
                    {"nombre_contiene": ["(1)"]},
                    {"extension": [".pdf"]},
                ],
            }
            self.assertTrue(_coincide_hint(archivo, "", hint_all))

    def test_modo_all_falla_si_falta_uno(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archivo = self._archivo("informe.pdf", tmpdir)
            hint_all = {
                "filter_mode": "all",
                "filtros": [
                    {"nombre_contiene": ["(1)"]},  # falla — no tiene "(1)"
                    {"extension": [".pdf"]},
                ],
            }
            self.assertFalse(_coincide_hint(archivo, "", hint_all))

    def test_hint_sin_filtros_no_coincide(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archivo = self._archivo("doc.txt", tmpdir)
            hint = {"nombre": "vacio", "filtros": []}
            self.assertFalse(_coincide_hint(archivo, "", hint))


if __name__ == "__main__":
    unittest.main()
