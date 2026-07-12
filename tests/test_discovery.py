"""
Pruebas de regresión para discovery.py.

Protege los comportamientos que han fallado en producción:
  - tokenizar conserva números y decimales (lección #18: 5%→19% accuracy tras el fix)
  - puntuar penaliza match solo de contenido (×0.35)
  - puntuar ignora números del cuerpo para carpetas puramente numéricas (lección #22)
  - construir_indice excluye proyectos de código (Fase 4)
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from clasi.discovery import (
    EntradaCarpeta,
    _categoria_carpeta,
    _es_proyecto_codigo,
    construir_indice,
    normalizar_nombre,
    puntuar,
    tokenizar,
)


class TestTokenizar(unittest.TestCase):
    def test_token_numerico_corto_se_conserva(self):
        # "UNIDAD 1" → el "1" debe conservarse aunque tenga < MIN_LONGITUD_TOKEN
        tokens = tokenizar("UNIDAD 1")
        self.assertIn("1", tokens)
        self.assertIn("unidad", tokens)

    def test_decimal_se_captura_completo(self):
        # "ACTIVIDAD 2.6" → "2.6" completo, no "2" y "6" por separado
        tokens = tokenizar("ACTIVIDAD 2.6")
        self.assertIn("2.6", tokens)
        self.assertNotIn("2", tokens)
        self.assertNotIn("6", tokens)

    def test_numeros_distintos_producen_tokens_distintos(self):
        # "UNIDAD 1" y "UNIDAD 6" deben distinguirse
        t1 = tokenizar("UNIDAD 1")
        t6 = tokenizar("UNIDAD 6")
        self.assertNotEqual(t1, t6)

    def test_decimales_distintos_producen_tokens_distintos(self):
        # "ACTIVIDAD 2.6" y "ACTIVIDAD 6.1" no deben colisionar
        t26 = tokenizar("ACTIVIDAD 2.6")
        t61 = tokenizar("ACTIVIDAD 6.1")
        self.assertFalse(t26 & t61 - {"actividad"})

    def test_stopwords_filtradas(self):
        self.assertNotIn("el", tokenizar("el documento"))
        self.assertNotIn("de", tokenizar("de la materia"))
        self.assertNotIn("the", tokenizar("the file"))

    def test_tokens_cortos_no_numericos_filtrados(self):
        # "de", "la", "el" — cortos y en stopwords
        tokens = tokenizar("de la")
        self.assertEqual(tokens, set())

    def test_acentos_normalizados(self):
        tokens = tokenizar("Ecuaciones Diferenciales")
        self.assertIn("ecuaciones", tokens)
        self.assertIn("diferenciales", tokens)


class TestNormalizarNombre(unittest.TestCase):
    def test_acentos_y_mayusculas(self):
        self.assertEqual(normalizar_nombre("Métodos Numéricos"), "metodosnumericos")

    def test_todo_mayusculas(self):
        self.assertEqual(normalizar_nombre("CÁLCULO"), "calculo")

    def test_espacios_eliminados(self):
        self.assertEqual(
            normalizar_nombre("Ecuaciones Diferenciales"), "ecuacionesdiferenciales"
        )

    def test_guiones_y_guion_bajo(self):
        self.assertEqual(normalizar_nombre("my-folder_name"), "myfoldername")

    def test_mismo_nombre_normalizado(self):
        # "Cálculo" y "CALCULO" deben colapsar al mismo índice
        self.assertEqual(normalizar_nombre("Cálculo"), normalizar_nombre("CALCULO"))


class TestPuntuar(unittest.TestCase):
    def _entrada(self, nombre, tokens_nombre, tokens_contenido=None, tokens_ancestros=None):
        return EntradaCarpeta(
            ruta=Path(f"/fake/{nombre}"),
            nombre=nombre,
            tokens_nombre=set(tokens_nombre),
            tokens_contenido=set(tokens_contenido or []),
            tokens_ancestros=set(tokens_ancestros or []),
        )

    def test_match_nombre_via_stem_da_score_alto(self):
        entrada = self._entrada(
            "Ecuaciones Diferenciales",
            tokens_nombre={"ecuaciones", "diferenciales"},
            tokens_contenido={"derivada", "integral"},
        )
        score = puntuar(
            tokens_contenido=set(),
            tokens_stem={"ecuaciones", "diferenciales"},
            entrada=entrada,
        )
        self.assertGreater(score, 0.60)

    def test_penalizacion_match_solo_contenido(self):
        # Stem no aporta hits → penalización ×0.35 sobre score_nombre.
        # Se usa tokens_contenido vacío en la carpeta para aislar el efecto:
        # sin señal de contenido, score_total = score_nombre × 0.70,
        # y la relación penalizado/sin_penal es exactamente 0.35.
        entrada = self._entrada(
            "Matematicas",
            tokens_nombre={"matematicas"},
            tokens_contenido=[],   # sin muestra de contenido → score_contenido = 0
        )
        score_penalizado = puntuar(
            tokens_contenido={"matematicas"},
            tokens_stem={"tarea"},        # stem no tiene "matematicas" → penalización
            entrada=entrada,
        )
        score_sin_penal = puntuar(
            tokens_contenido=set(),
            tokens_stem={"matematicas"},  # stem sí tiene "matematicas" → sin penalización
            entrada=entrada,
        )
        self.assertLess(score_penalizado, score_sin_penal)
        # Con tokens_contenido de carpeta vacío, la relación es exactamente 0.35
        self.assertAlmostEqual(score_penalizado / score_sin_penal, 0.35, places=5)

    def test_carpeta_numerica_sin_hit_de_stem_da_cero(self):
        # Carpeta "1.2" — si el stem del archivo no contiene "1.2" → 0.0
        entrada = self._entrada(
            "1.2",
            tokens_nombre={"1.2"},
            tokens_contenido={"vector", "espacio"},
            tokens_ancestros={"metodos", "numericos"},
        )
        score = puntuar(
            tokens_contenido={"1.2"},   # el número aparece en el cuerpo
            tokens_stem={"tarea"},      # pero NO en el stem
            entrada=entrada,
        )
        self.assertEqual(score, 0.0)

    def test_carpeta_numerica_con_hit_de_stem_y_ancestros(self):
        # Carpeta "1.2" con stem que contiene "1.2" y ancestros que coinciden
        entrada = self._entrada(
            "1.2",
            tokens_nombre={"1.2"},
            tokens_contenido={"vector"},
            tokens_ancestros={"metodos", "numericos"},
        )
        score = puntuar(
            tokens_contenido={"metodos", "numericos"},
            tokens_stem={"1.2"},        # stem comparte el número
            entrada=entrada,
        )
        self.assertGreater(score, 0.40)

    def test_cero_tokens_da_cero(self):
        entrada = self._entrada("Cualquier", tokens_nombre={"cualquier"})
        score = puntuar(set(), set(), entrada)
        self.assertEqual(score, 0.0)

    def test_numeros_del_cuerpo_no_inflan_carpeta_numerica(self):
        # Lección #22: tabla de resultados con "2.7" no debe clasificar en ACTIVIDAD 2.7
        entrada = self._entrada(
            "2.7",
            tokens_nombre={"2.7"},
            tokens_contenido={"resultado", "calculo"},
            tokens_ancestros={"metodos", "numericos"},
        )
        # El archivo tiene "2.7" en el CUERPO (tabla de resultados), no en el stem
        score = puntuar(
            tokens_contenido={"resultado", "2.7"},
            tokens_stem={"actividad", "practica"},
            entrada=entrada,
        )
        self.assertEqual(score, 0.0)


class TestEsProyectoCodigo(unittest.TestCase):
    def test_carpeta_con_git_es_proyecto(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            (p / ".git").mkdir()
            self.assertTrue(_es_proyecto_codigo(p))

    def test_carpeta_con_cargo_toml_es_proyecto(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            (p / "Cargo.toml").write_text("[package]\nname = \"test\"")
            self.assertTrue(_es_proyecto_codigo(p))

    def test_carpeta_con_package_json_es_proyecto(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            (p / "package.json").write_text("{}")
            self.assertTrue(_es_proyecto_codigo(p))

    def test_carpeta_sin_marcadores_no_es_proyecto(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            (p / "apuntes.txt").write_text("notas de clase")
            self.assertFalse(_es_proyecto_codigo(p))

    def test_carpeta_vacia_no_es_proyecto(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertFalse(_es_proyecto_codigo(Path(tmpdir)))


class TestConstruirIndice(unittest.TestCase):
    def test_excluye_proyectos_de_codigo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)

            # Carpeta temática normal
            tematica = raiz / "Matematicas"
            tematica.mkdir()
            (tematica / "apuntes.txt").write_text("algebra calculo")

            # Proyecto de código — ni él ni sus subcarpetas deben indexarse
            proyecto = raiz / "mi-app"
            proyecto.mkdir()
            (proyecto / ".git").mkdir()
            (proyecto / "src").mkdir()

            indice = construir_indice(raiz)

            self.assertIn("matematicas", indice)
            self.assertNotIn("miapp", indice)
            self.assertNotIn("src", indice)

    def test_excluye_carpetas_ocultas(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            oculta = raiz / ".config"
            oculta.mkdir()
            (oculta / "app.conf").write_text("config")

            indice = construir_indice(raiz)
            self.assertNotIn("config", indice)

    def test_detecta_duplicadas(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            (raiz / "Calculo").mkdir()
            (raiz / "CALCULO").mkdir()
            # Añadir archivos para que no sean carpetas vacías sin muestra
            (raiz / "Calculo" / "a.txt").write_text("derivada integral")
            (raiz / "CALCULO" / "b.txt").write_text("derivada integral")

            indice = construir_indice(raiz)
            self.assertIn("calculo", indice)
            # Una de las dos queda como duplicada de la canónica
            self.assertEqual(len(indice["calculo"].duplicadas), 1)

    def test_no_indexa_subcarpeta_mismo_nombre_que_padre(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            padre = raiz / "Calculo"
            hijo = padre / "CALCULO"
            hijo.mkdir(parents=True)
            (hijo / "a.txt").write_text("derivada")

            indice = construir_indice(raiz)
            # "calculo" puede estar (padre), pero el hijo no crea entrada separada
            if "calculo" in indice:
                # el hijo no debe ser la entrada canónica con duplicada en sí mismo
                self.assertNotEqual(indice["calculo"].ruta, hijo)


if __name__ == "__main__":
    unittest.main()
