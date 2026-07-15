"""
Simulación de entornos reales para tests de integración de clasi.

Tres dimensiones de variación:
  1. Perfil del home (qué herramientas/directorios tiene el usuario)
  2. Estado del exclusions.yaml (generado automáticamente o editado a mano)
  3. Estructura del directorio objetivo (vacío, con symlinks, con permisos, etc.)

Cada test ejecuta el flujo completo: detectar → generar_yaml → cargar_exclusiones
→ construir_indice + escanear. Si no explota, el entorno está cubierto.
"""

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from clasi.discovery import construir_indice
from clasi.init import detectar, generar_yaml
from clasi.scanner import cargar_exclusiones, escanear


# ── Helper ─────────────────────────────────────────────────────────────────────

def _flujo_completo(home: Path, directorio: Path) -> None:
    """Ejecuta el flujo init→sim completo sin atrapar errores."""
    resultado = detectar(home)
    yaml_str = generar_yaml(resultado, home)
    yaml_path = home / "exclusions.yaml"
    yaml_path.write_text(yaml_str)
    exclusiones = cargar_exclusiones(yaml_path)
    construir_indice(directorio, exclusiones, 4, set())
    list(escanear(directorio, exclusiones))


# ── Perfiles de usuario ────────────────────────────────────────────────────────

class TestPerfilesDeUsuario(unittest.TestCase):
    """
    Simula distintos tipos de equipo ejecutando el flujo init→sim completo.
    Cada test construye un home falso con la estructura del perfil y luego
    corre todo el pipeline. Si no explota, el perfil está cubierto.
    """

    def test_estudiante_sin_herramientas(self):
        """Equipo básico de estudiante: solo carpetas XDG, sin dirs_proyecto.
        Reproduce el bug de Monik: rutas_absolutas queda null en el YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            for d in ["Documentos", "Descargas", "Imágenes", "Música", "Vídeos",
                      "Escritorio", ".config", ".local", ".cache"]:
                (home / d).mkdir()
            directorio = home / "Documentos"
            (directorio / "Tarea_1.pdf").write_text("algebra lineal")
            _flujo_completo(home, directorio)

    def test_desarrollador_python_js(self):
        """Desarrollador con .npm, .cargo, .vscode y un dir Proyectos."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            for d in [".npm", ".cargo", ".vscode", "Proyectos", ".config"]:
                (home / d).mkdir()
            directorio = home / "Documentos"
            directorio.mkdir()
            (directorio / "apuntes.txt").write_text("python javascript")
            _flujo_completo(home, directorio)

    def test_desarrollador_java_netbeans(self):
        """Desarrollador Java con Maven, Gradle, NetBeans y NetBeansProjects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            for d in [".m2", ".gradle", ".java", ".netbeans", "NetBeansProjects"]:
                (home / d).mkdir()
            directorio = home / "Descargas"
            directorio.mkdir()
            (directorio / "tutorial.pdf").write_text("java maven gradle")
            _flujo_completo(home, directorio)

    def test_usuario_snap_pki(self):
        """Usuario Ubuntu con snap y certificados PKI (perfil frecuente en instituciones)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            for d in ["snap", ".pki", ".config", "Documentos"]:
                (home / d).mkdir()
            directorio = home / "Documentos"
            (directorio / "contrato.pdf").write_text("firmado digitalmente")
            _flujo_completo(home, directorio)

    def test_usuario_gamer(self):
        """Usuario con Steam, Minecraft y Spicetify."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            for d in [".steam", ".minecraft", ".spicetify", "snap", ".config"]:
                (home / d).mkdir()
            directorio = home / "Descargas"
            directorio.mkdir()
            (directorio / "mods.zip").write_text("mod data")
            _flujo_completo(home, directorio)

    def test_power_user_multiples_dirs_proyecto(self):
        """Usuario con varios dirs de proyecto simultáneos: Proyectos, Work y repos."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            for d in [".cargo", ".npm", ".claude", "Proyectos", "Work", "repos"]:
                (home / d).mkdir()
            directorio = home / "Documentos"
            directorio.mkdir()
            (directorio / "informe.docx").write_text("reporte anual")
            _flujo_completo(home, directorio)

    def test_home_completamente_vacio(self):
        """Home mínimo: ninguna herramienta, ningún dir proyecto, ninguna carpeta XDG."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            directorio = home / "copia"
            directorio.mkdir()
            (directorio / "foto.jpg").write_bytes(b"\xff\xd8\xff")
            _flujo_completo(home, directorio)

    def test_todas_las_herramientas_detectadas(self):
        """Home con todas las herramientas reconocidas por init a la vez."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            for nombre in [".cargo", ".npm", ".m2", ".gradle", ".dotnet", ".java",
                           ".netbeans", ".vscode", ".vscode-shared", ".electron-gyp",
                           ".aws", ".pki", ".steam", ".minecraft", ".spicetify",
                           ".zen", ".windows", ".claude", ".codex", ".agents",
                           ".kiro", ".pi", "snap"]:
                (home / nombre).mkdir()
            directorio = home / "Documentos"
            directorio.mkdir()
            (directorio / "nota.txt").write_text("contenido")
            _flujo_completo(home, directorio)


# ── YAML adversarial ───────────────────────────────────────────────────────────

class TestYamlAdversarial(unittest.TestCase):
    """
    Inputs malformados o edge cases del exclusions.yaml.
    Cubre archivos vacíos, claves con null, edición manual incorrecta, etc.
    """

    def _cargar(self, contenido: str) -> dict:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(contenido)
            return cargar_exclusiones(Path(f.name))

    def _ejecutar(self, contenido: str, directorio: Path) -> None:
        exclusiones = self._cargar(contenido)
        construir_indice(directorio, exclusiones, 4, set())
        list(escanear(directorio, exclusiones))

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        d = Path(self._tmpdir.name)
        (d / "archivo.txt").write_text("contenido de prueba")
        self._dir = d

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_yaml_vacio(self):
        """Archivo completamente vacío."""
        self._ejecutar("", self._dir)

    def test_yaml_solo_comentarios(self):
        """yaml.safe_load devuelve None cuando solo hay comentarios."""
        self._ejecutar(
            "# Este archivo no tiene claves\n# solo comentarios\n",
            self._dir,
        )

    def test_rutas_absolutas_null(self):
        """El bug de Monik: rutas_absolutas sin valores después de clasi init."""
        yaml = textwrap.dedent("""\
            version: 1
            carpetas_exactas:
              - .git
            patrones_nombre:
              - "*.log"
            rutas_absolutas:
        """)
        self._ejecutar(yaml, self._dir)

    def test_carpetas_exactas_null(self):
        yaml = textwrap.dedent("""\
            version: 1
            carpetas_exactas:
            patrones_nombre:
              - "*.log"
            rutas_absolutas:
              - /tmp
        """)
        self._ejecutar(yaml, self._dir)

    def test_patrones_nombre_null(self):
        yaml = textwrap.dedent("""\
            version: 1
            carpetas_exactas:
              - .git
            patrones_nombre:
            rutas_absolutas:
        """)
        self._ejecutar(yaml, self._dir)

    def test_todas_las_secciones_null_explicito(self):
        """Todas las claves existen con null explícito en YAML."""
        yaml = textwrap.dedent("""\
            version: 1
            carpetas_exactas: null
            patrones_nombre: ~
            rutas_absolutas: null
        """)
        self._ejecutar(yaml, self._dir)

    def test_ruta_absoluta_inexistente(self):
        """rutas_absolutas apunta a una ruta que no existe en el sistema."""
        yaml = textwrap.dedent("""\
            version: 1
            carpetas_exactas: []
            patrones_nombre: []
            rutas_absolutas:
              - /home/usuario_que_no_existe/Proyectos
              - /ruta/completamente/falsa/12345
        """)
        self._ejecutar(yaml, self._dir)

    def test_yaml_sin_clave_version(self):
        """YAML válido pero sin la clave version (editado manualmente)."""
        yaml = textwrap.dedent("""\
            carpetas_exactas:
              - .git
              - node_modules
            patrones_nombre:
              - "*.bak"
        """)
        self._ejecutar(yaml, self._dir)

    def test_yaml_con_clave_desconocida(self):
        """YAML con claves que no reconoce clasi (ej. versión futura o error tipográfico)."""
        yaml = textwrap.dedent("""\
            version: 2
            carpetas_exactas:
              - .git
            extensiones_excluidas:
              - .tmp
            nueva_clave_futura: null
        """)
        self._ejecutar(yaml, self._dir)


# ── Directorio objetivo ────────────────────────────────────────────────────────

class TestDirectorioObjetivo(unittest.TestCase):
    """
    Variantes adversariales del directorio que se le pasa a sim/run.
    Prueba estructuras de sistema de archivos que pueden romper el recorrido.
    """

    _EXCL = {
        "carpetas_exactas": [".git", "node_modules", "__pycache__"],
        "patrones_nombre": ["*.log", "*.sock"],
        "rutas_absolutas": [],
    }

    def test_directorio_vacio(self):
        """Sin archivos ni subdirectorios."""
        with tempfile.TemporaryDirectory() as d:
            construir_indice(Path(d), self._EXCL, 4, set())
            self.assertEqual(list(escanear(Path(d), self._EXCL)), [])

    def test_directorio_solo_archivos_planos(self):
        """Solo archivos en la raíz, sin ninguna subcarpeta."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            for i in range(5):
                (d / f"archivo_{i}.txt").write_text(f"contenido {i}")
            construir_indice(d, self._EXCL, 4, set())
            archivos = list(escanear(d, self._EXCL))
            self.assertEqual(len(archivos), 5)

    def test_directorio_con_symlinks(self):
        """Symlinks deben ignorarse sin lanzar excepciones."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            real = d / "real"
            real.mkdir()
            (real / "dato.txt").write_text("contenido real")
            (d / "enlace_a_real").symlink_to(real)
            archivos = list(escanear(d, self._EXCL))
            rutas = [str(a) for a in archivos]
            self.assertTrue(all("enlace" not in r for r in rutas))

    def test_directorio_con_nombres_acentuados(self):
        """Carpetas con acentos, ñ y caracteres del español."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            for nombre in ["Matemáticas", "Álgebra Lineal", "Ecuaciones Diferenciales",
                           "Español y Redacción", "Año Escolar 2024-2025"]:
                carpeta = d / nombre
                carpeta.mkdir()
                (carpeta / "apunte.txt").write_text(nombre.lower())
            construir_indice(d, self._EXCL, 4, set())

    def test_directorio_con_carpeta_sin_permisos(self):
        """Una subcarpeta inaccesible no detiene el escaneo de las demás."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            accesible = d / "Documentos"
            accesible.mkdir()
            (accesible / "nota.txt").write_text("contenido")
            restringida = d / "Privado"
            restringida.mkdir()
            restringida.chmod(0o000)
            try:
                archivos = list(escanear(d, self._EXCL))
                nombres = [a.name for a in archivos]
                self.assertIn("nota.txt", nombres)
            finally:
                restringida.chmod(0o755)

    def test_directorio_muy_profundo_respeta_max_depth(self):
        """Árbol de 10 niveles: con max_depth=4 no debe recorser más allá."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            actual = d
            for i in range(10):
                actual = actual / f"nivel_{i}"
                actual.mkdir()
                (actual / f"archivo_{i}.txt").write_text(f"profundidad {i}")
            archivos = list(escanear(d, self._EXCL, max_depth=4))
            for archivo in archivos:
                profundidad = len(archivo.relative_to(d).parts)
                self.assertLessEqual(profundidad, 5)

    def test_directorio_con_carpetas_excluidas_presentes(self):
        """Carpetas en carpetas_exactas deben ignorarse aunque existan."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / ".git").mkdir()
            (d / ".git" / "config").write_text("[core]")
            (d / "node_modules").mkdir()
            (d / "node_modules" / "paquete.js").write_text("module.exports={}")
            (d / "Documentos").mkdir()
            (d / "Documentos" / "nota.txt").write_text("visible")
            archivos = list(escanear(d, self._EXCL))
            nombres = [a.name for a in archivos]
            self.assertIn("nota.txt", nombres)
            self.assertNotIn("config", nombres)
            self.assertNotIn("paquete.js", nombres)


if __name__ == "__main__":
    unittest.main()
