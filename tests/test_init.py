"""
Pruebas de regresión para init.py.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from clasi.init import detectar, generar_yaml


class TestDetectar(unittest.TestCase):
    def test_detecta_herramienta_presente(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            (home / ".cargo").mkdir()
            resultado = detectar(home)
            nombres = [n for n, _ in resultado["herramientas"]]
            self.assertIn(".cargo", nombres)

    def test_no_detecta_herramienta_ausente(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            resultado = detectar(home)
            nombres = [n for n, _ in resultado["herramientas"]]
            self.assertNotIn(".cargo", nombres)

    def test_detecta_directorio_de_proyecto(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            (home / "Proyectos").mkdir()
            resultado = detectar(home)
            self.assertIn(home / "Proyectos", resultado["dirs_proyecto"])

    def test_no_detecta_symlink_como_proyecto(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            target = Path(tmpdir) / "real"
            target.mkdir()
            (home / "Projects").symlink_to(target)
            resultado = detectar(home)
            self.assertNotIn(home / "Projects", resultado["dirs_proyecto"])

    def test_home_vacio_devuelve_listas_vacias(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            resultado = detectar(Path(tmpdir))
            self.assertEqual(resultado["herramientas"], [])
            self.assertEqual(resultado["dirs_proyecto"], [])


class TestGenerarYaml(unittest.TestCase):
    def _resultado_vacio(self):
        return {"herramientas": [], "dirs_proyecto": []}

    def test_yaml_contiene_version(self):
        yaml = generar_yaml(self._resultado_vacio())
        self.assertIn("version: 1", yaml)

    def test_yaml_contiene_seccion_carpetas_exactas(self):
        yaml = generar_yaml(self._resultado_vacio())
        self.assertIn("carpetas_exactas:", yaml)

    def test_yaml_contiene_seccion_patrones(self):
        yaml = generar_yaml(self._resultado_vacio())
        self.assertIn("patrones_nombre:", yaml)

    def test_yaml_contiene_seccion_rutas(self):
        yaml = generar_yaml(self._resultado_vacio())
        self.assertIn("rutas_absolutas:", yaml)

    def test_yaml_incluye_herramientas_detectadas(self):
        resultado = {
            "herramientas": [(".cargo", "Rust (cargo)"), (".npm", "Node.js (npm)")],
            "dirs_proyecto": [],
        }
        yaml = generar_yaml(resultado)
        self.assertIn(".cargo", yaml)
        self.assertIn(".npm", yaml)
        self.assertIn("Rust (cargo)", yaml)

    def test_yaml_incluye_dirs_proyecto_con_tilde(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            resultado = {
                "herramientas": [],
                "dirs_proyecto": [home / "Proyectos"],
            }
            yaml = generar_yaml(resultado, home=home)
            self.assertIn("~/Proyectos", yaml)

    def test_yaml_sin_herramientas_no_incluye_seccion_vacia(self):
        yaml = generar_yaml(self._resultado_vacio())
        self.assertNotIn("Herramientas detectadas", yaml)

    def test_yaml_termina_en_newline(self):
        yaml = generar_yaml(self._resultado_vacio())
        self.assertTrue(yaml.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
