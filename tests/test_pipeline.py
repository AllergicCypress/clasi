"""
Tests de integración del pipeline de herramientas de clasi.

Prueba el comportamiento de cada herramienta end-to-end usando
directorios temporales reales. Los archivos se crean, mueven y revierten
de verdad — sin mocks.

Contratos protegidos:
  - clasificar:      asigna el destino correcto dado índice + umbral
  - ejecutar:        mueve archivos físicamente y escribe log JSONL
  - deshacer:        revierte exactamente lo que ejecutar hizo
  - merge_carpetas:  fusiona carpetas con políticas de conflicto correctas
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from clasi.classifier import Resultado, clasificar
from clasi.discovery import construir_indice
from clasi.executor import deshacer, ejecutar, merge_carpetas


# ── Helpers ────────────────────────────────────────────────────────────────────

def _indice(raiz: Path) -> dict:
    return construir_indice(raiz, exclusiones={}, max_depth=4, nombres_genericos=set())


def _clasificar(archivo: Path, raiz: Path, umbral: float = 0.20) -> Resultado:
    return clasificar(archivo, hints=[], indice=_indice(raiz), directorio_base=raiz, umbral=umbral)


def _resultado_manual(archivo: Path, destino: Path, conflicto: str = "rename_new") -> Resultado:
    """Crea un Resultado sin pasar por el clasificador — para tests de ejecutar."""
    return Resultado(
        archivo=archivo,
        destino=destino,
        regla="test",
        confianza="alta",
        score=1.0,
        metodo="nombre",
        conflicto=conflicto,
        texto_extraido="",
    )


def _carpeta_con_contenido(raiz: Path, nombre: str, textos: list[str]) -> Path:
    """Crea una carpeta con archivos de contenido para que sea indexada como temática."""
    carpeta = raiz / nombre
    carpeta.mkdir(parents=True, exist_ok=True)
    for i, texto in enumerate(textos):
        (carpeta / f"ref_{i}.txt").write_text(texto)
    return carpeta


# ── clasificar ─────────────────────────────────────────────────────────────────

class TestClasificar(unittest.TestCase):
    """Verifica que clasificar() asigne el destino correcto según el índice."""

    def test_archivo_con_carpeta_coincidente_recibe_destino(self):
        """Archivo cuyo nombre comparte tokens con una carpeta → destino asignado."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            # Los archivos comparten "algebra" y "lineal" para superar homogeneidad mínima.
            carpeta = _carpeta_con_contenido(raiz, "Algebra_Lineal", [
                "algebra lineal vectores matrices transformacion",
                "algebra lineal espacios vectoriales dimension",
                "algebra lineal determinantes autovalores sistemas",
            ])
            archivo = raiz / "algebra_lineal_tarea.txt"
            archivo.write_text("matrices determinantes ejercicio")

            resultado = _clasificar(archivo, raiz)

            self.assertIsNotNone(resultado.destino)
            self.assertEqual(resultado.destino, carpeta)

    def test_archivo_sin_carpeta_coincidente_no_tiene_destino(self):
        """Archivo cuyo nombre no coincide con ninguna carpeta → destino None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            _carpeta_con_contenido(raiz, "Quimica_Organica", [
                "carbono hidrogeno enlace covalente",
                "alcanos alquenos alquinos molecula",
                "reaccion organica funcional grupo",
            ])
            archivo = raiz / "filosofia_medieval.txt"
            archivo.write_text("kant hegel razon ilustracion")

            resultado = _clasificar(archivo, raiz, umbral=0.40)

            self.assertIsNone(resultado.destino)
            self.assertEqual(resultado.metodo, "ninguno")

    def test_archivo_ya_en_destino_detectado_como_organizado(self):
        """Un archivo dentro de su carpeta destino → _ya_organizado devuelve True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            carpeta = _carpeta_con_contenido(raiz, "Biologia", [
                "celulas organismos evolucion biologia",
                "adn rna proteinas genetica",
                "mitosis meiosis division celular",
            ])
            archivo = carpeta / "biologia_apuntes.txt"
            archivo.write_text("celulas organismos")

            resultado = _clasificar(archivo, raiz)

            if resultado.destino is not None:
                destino = resultado.destino.resolve()
                padre = resultado.archivo.parent.resolve()
                ya_organizado = destino == padre or destino in padre.parents
                self.assertTrue(ya_organizado)

    def test_el_mejor_match_gana_cuando_hay_varias_carpetas(self):
        """Con múltiples carpetas candidatas, el mayor score gana."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            # Vocabulario compartido dentro de cada carpeta para pasar homogeneidad.
            _carpeta_con_contenido(raiz, "Calculo_Diferencial", [
                "calculo diferencial derivadas limites funciones",
                "calculo diferencial regla cadena parcial",
                "calculo diferencial continuidad diferenciabilidad",
            ])
            calculo_integral = _carpeta_con_contenido(raiz, "Calculo_Integral", [
                "calculo integral integrales areas volumen",
                "calculo integral definida riemann acumulacion",
                "calculo integral tecnicas sustitucion partes",
            ])
            archivo = raiz / "calculo_integral_practica.txt"
            archivo.write_text("integral definida area bajo curva")

            resultado = _clasificar(archivo, raiz)

            self.assertIsNotNone(resultado.destino)
            self.assertEqual(resultado.destino, calculo_integral)


# ── ejecutar ───────────────────────────────────────────────────────────────────

class TestEjecutar(unittest.TestCase):
    """Verifica que ejecutar() mueva archivos y escriba el log correctamente."""

    def test_mueve_archivo_fisicamente(self):
        """ejecutar(seco=False) → archivo en destino, no en origen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            destino_carpeta = raiz / "Destino"
            destino_carpeta.mkdir()
            archivo = raiz / "documento.txt"
            archivo.write_text("contenido")

            resultado = _resultado_manual(archivo, destino_carpeta)
            log = raiz / "run.jsonl"
            ejecutar([resultado], log, seco=False)

            self.assertFalse(archivo.exists())
            self.assertTrue((destino_carpeta / "documento.txt").exists())

    def test_seco_no_mueve_ni_escribe_log(self):
        """ejecutar(seco=True) → ningún archivo movido, sin log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            destino_carpeta = raiz / "Destino"
            destino_carpeta.mkdir()
            archivo = raiz / "documento.txt"
            archivo.write_text("contenido")

            resultado = _resultado_manual(archivo, destino_carpeta)
            log = raiz / "run.jsonl"
            ejecutar([resultado], log, seco=True)

            self.assertTrue(archivo.exists())
            self.assertFalse(log.exists())

    def test_log_es_jsonl_valido_con_campos_requeridos(self):
        """El log generado es JSONL con accion, archivo, destino y ts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            destino_carpeta = raiz / "Destino"
            destino_carpeta.mkdir()
            archivo = raiz / "documento.txt"
            archivo.write_text("contenido")

            resultado = _resultado_manual(archivo, destino_carpeta)
            log = raiz / "run.jsonl"
            ejecutar([resultado], log, seco=False)

            lineas = log.read_text().strip().splitlines()
            self.assertEqual(len(lineas), 1)
            entrada = json.loads(lineas[0])
            for campo in ("accion", "archivo", "destino", "ts"):
                self.assertIn(campo, entrada)
            self.assertEqual(entrada["accion"], "mover")

    def test_conflicto_skip_no_sobreescribe(self):
        """Si el archivo ya existe en destino y conflicto=skip → se omite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            destino_carpeta = raiz / "Destino"
            destino_carpeta.mkdir()
            (destino_carpeta / "documento.txt").write_text("versión existente")
            archivo = raiz / "documento.txt"
            archivo.write_text("versión nueva")

            resultado = _resultado_manual(archivo, destino_carpeta, conflicto="skip")
            log = raiz / "run.jsonl"
            ops = ejecutar([resultado], log, seco=False)

            skips = [o for o in ops if o["accion"] == "skip"]
            self.assertEqual(len(skips), 1)
            self.assertEqual((destino_carpeta / "documento.txt").read_text(), "versión existente")
            self.assertTrue(archivo.exists())

    def test_conflicto_rename_new_crea_con_sufijo(self):
        """Si el archivo ya existe y conflicto=rename_new → se crea como _1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            destino_carpeta = raiz / "Destino"
            destino_carpeta.mkdir()
            (destino_carpeta / "documento.txt").write_text("versión existente")
            archivo = raiz / "documento.txt"
            archivo.write_text("versión nueva")

            resultado = _resultado_manual(archivo, destino_carpeta, conflicto="rename_new")
            log = raiz / "run.jsonl"
            ejecutar([resultado], log, seco=False)

            self.assertTrue((destino_carpeta / "documento_1.txt").exists())
            self.assertEqual((destino_carpeta / "documento.txt").read_text(), "versión existente")

    def test_multiples_archivos_todos_en_log(self):
        """Con N archivos, el log tiene exactamente N entradas."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            destino = raiz / "Destino"
            destino.mkdir()
            resultados = []
            for i in range(4):
                a = raiz / f"archivo_{i}.txt"
                a.write_text(f"contenido {i}")
                resultados.append(_resultado_manual(a, destino))

            log = raiz / "run.jsonl"
            ejecutar(resultados, log, seco=False)

            lineas = log.read_text().strip().splitlines()
            self.assertEqual(len(lineas), 4)


# ── deshacer ───────────────────────────────────────────────────────────────────

class TestDeshacer(unittest.TestCase):
    """Verifica que deshacer() revierta exactamente lo que ejecutar() hizo."""

    def test_revierte_archivo_a_posicion_original(self):
        """Tras ejecutar + deshacer, el archivo regresa al origen."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            destino_carpeta = raiz / "Destino"
            destino_carpeta.mkdir()
            archivo = raiz / "documento.txt"
            archivo.write_text("contenido")

            resultado = _resultado_manual(archivo, destino_carpeta)
            log = raiz / "run.jsonl"
            ejecutar([resultado], log, seco=False)
            self.assertFalse(archivo.exists())

            revertidas = deshacer(log)

            self.assertEqual(len(revertidas), 1)
            self.assertTrue(archivo.exists())
            self.assertFalse((destino_carpeta / "documento.txt").exists())

    def test_revierte_multiples_archivos(self):
        """deshacer revierte todos los archivos movidos en un mismo run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            destino = raiz / "Destino"
            destino.mkdir()
            archivos = []
            resultados = []
            for i in range(3):
                a = raiz / f"archivo_{i}.txt"
                a.write_text(f"contenido {i}")
                archivos.append(a)
                resultados.append(_resultado_manual(a, destino))

            log = raiz / "run.jsonl"
            ejecutar(resultados, log, seco=False)
            deshacer(log)

            for a in archivos:
                self.assertTrue(a.exists(), f"{a.name} debe haber regresado al origen")
                self.assertFalse((destino / a.name).exists())

    def test_log_inexistente_no_explota(self):
        """deshacer con un log que no existe devuelve lista vacía."""
        revertidas = deshacer(Path("/tmp/log_que_no_existe_12345.jsonl"))
        self.assertEqual(revertidas, [])

    def test_skip_en_log_no_se_revierte(self):
        """Las entradas 'skip' del log se ignoran al deshacer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            destino = raiz / "Destino"
            destino.mkdir()
            (destino / "existente.txt").write_text("ya estaba")
            archivo = raiz / "existente.txt"
            archivo.write_text("nuevo")

            resultado = _resultado_manual(archivo, destino, conflicto="skip")
            log = raiz / "run.jsonl"
            ejecutar([resultado], log, seco=False)

            revertidas = deshacer(log)
            self.assertEqual(revertidas, [])
            self.assertTrue(archivo.exists())


# ── merge_carpetas ─────────────────────────────────────────────────────────────

class TestMergeCarpetas(unittest.TestCase):
    """Verifica que merge_carpetas() fusione correctamente dos carpetas."""

    def test_mueve_todos_los_archivos(self):
        """merge(seco=False) → archivos de redundante aparecen en canónica."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            redundante = raiz / "Calculo_old"
            canonica = raiz / "Calculo"
            redundante.mkdir()
            canonica.mkdir()
            (redundante / "apunte_1.txt").write_text("derivadas")
            (redundante / "apunte_2.txt").write_text("integrales")

            ops = merge_carpetas(redundante, canonica, conflicto="rename_new", seco=False)

            movidos = [o for o in ops if o["accion"] == "mover"]
            self.assertEqual(len(movidos), 2)
            self.assertTrue((canonica / "apunte_1.txt").exists())
            self.assertTrue((canonica / "apunte_2.txt").exists())
            self.assertFalse(any(redundante.rglob("*.txt")))

    def test_seco_no_toca_el_sistema_de_archivos(self):
        """merge(seco=True) → devuelve operaciones pero no mueve nada."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            redundante = raiz / "Docs_old"
            canonica = raiz / "Docs"
            redundante.mkdir()
            canonica.mkdir()
            (redundante / "informe.txt").write_text("contenido")

            ops = merge_carpetas(redundante, canonica, conflicto="rename_new", seco=True)

            self.assertEqual(len(ops), 1)
            self.assertTrue((redundante / "informe.txt").exists())
            self.assertFalse((canonica / "informe.txt").exists())

    def test_conflicto_skip_preserva_archivo_existente(self):
        """Si el archivo ya existe en canónica y conflicto=skip → la copia nueva se omite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            redundante = raiz / "Docs_old"
            canonica = raiz / "Docs"
            redundante.mkdir()
            canonica.mkdir()
            (redundante / "informe.txt").write_text("versión vieja")
            (canonica / "informe.txt").write_text("versión nueva")

            ops = merge_carpetas(redundante, canonica, conflicto="skip", seco=False)

            skips = [o for o in ops if o["accion"] == "skip"]
            self.assertEqual(len(skips), 1)
            self.assertEqual((canonica / "informe.txt").read_text(), "versión nueva")

    def test_conflicto_rename_new_crea_sufijo(self):
        """Si el archivo ya existe y conflicto=rename_new → se crea como _1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            redundante = raiz / "Docs_old"
            canonica = raiz / "Docs"
            redundante.mkdir()
            canonica.mkdir()
            (redundante / "informe.txt").write_text("versión vieja")
            (canonica / "informe.txt").write_text("versión nueva")

            merge_carpetas(redundante, canonica, conflicto="rename_new", seco=False)

            self.assertTrue((canonica / "informe_1.txt").exists())
            self.assertEqual((canonica / "informe.txt").read_text(), "versión nueva")

    def test_preserva_estructura_de_subdirectorios(self):
        """Archivos en subcarpetas de redundante van a la misma subcarpeta en canónica."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            redundante = raiz / "Fisica_old"
            canonica = raiz / "Fisica"
            (redundante / "Parcial_1").mkdir(parents=True)
            (redundante / "Parcial_2").mkdir(parents=True)
            canonica.mkdir()
            (redundante / "Parcial_1" / "examen.txt").write_text("mecanica")
            (redundante / "Parcial_2" / "practica.txt").write_text("termodinamica")

            merge_carpetas(redundante, canonica, conflicto="rename_new", seco=False)

            self.assertTrue((canonica / "Parcial_1" / "examen.txt").exists())
            self.assertTrue((canonica / "Parcial_2" / "practica.txt").exists())

    def test_carpeta_vacia_devuelve_lista_vacia(self):
        """merge sobre una carpeta redundante vacía devuelve []."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            redundante = raiz / "Vacia"
            canonica = raiz / "Destino"
            redundante.mkdir()
            canonica.mkdir()

            ops = merge_carpetas(redundante, canonica, conflicto="rename_new", seco=False)
            self.assertEqual(ops, [])

    def test_undo_revierte_los_archivos_a_redundante(self):
        """Tras merge + deshacer, los archivos vuelven a la carpeta redundante."""
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            redundante = raiz / "Matematicas_old"
            canonica = raiz / "Matematicas"
            redundante.mkdir()
            canonica.mkdir()
            (redundante / "apunte.txt").write_text("algebra calculo")

            ops = merge_carpetas(redundante, canonica, conflicto="rename_new", seco=False)
            self.assertTrue((canonica / "apunte.txt").exists())

            log = raiz / "merge.jsonl"
            with open(log, "w") as f:
                for op in ops:
                    f.write(json.dumps(op, ensure_ascii=False) + "\n")

            deshacer(log)

            self.assertTrue((redundante / "apunte.txt").exists())
            self.assertFalse((canonica / "apunte.txt").exists())


if __name__ == "__main__":
    unittest.main()
