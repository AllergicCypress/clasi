"""
Evaluación de precisión por holdout: mide qué tan seguido `clasi` regresa un
archivo a la misma carpeta donde el usuario ya lo tenía archivado.

La carpeta donde el archivo YA vive es el ground truth — no se necesita que
nadie juzgue manualmente "esto está bien organizado". Por cada carpeta
temática del índice, se "sacan" virtualmente 1-3 archivos (sin tocar el
disco), se reconstruye la señal de contenido de esa carpeta SIN esos
archivos (para no comparar al archivo contra sí mismo), y se clasifica el
archivo como si estuviera suelto contra el índice completo.
"""

import hashlib
import random
from dataclasses import dataclass
from pathlib import Path

from discovery import EntradaCarpeta, MAX_ARCHIVOS_MUESTRA, UMBRAL_DEFAULT, buscar_destino, tokenizar
from extractor import extraer_texto

MAX_HOLDOUT_POR_CARPETA = 3
FRACCION_MAX_HOLDOUT = 0.20
# Con menos archivos, ni 1 holdout cabe dentro del 20% sin vaciar la carpeta de señal.
MIN_ARCHIVOS_PARA_EVALUAR = 5


@dataclass
class CasoEvaluado:
    carpeta_id: str             # hash corto de la carpeta canónica, ej. "carpeta_07"
    archivo_id: str             # hash corto + extensión, ej. "a3f1c2.pdf"
    destino_id: str | None      # carpeta_id que predijo clasi, o None si "sin destino"
    estado: str                 # "correcto", "incorrecto" o "sin_destino"
    score: float
    metodo: str
    ruta_archivo: Path | None = None
    ruta_carpeta: Path | None = None
    ruta_predicha: Path | None = None


def _id_corto(texto: str) -> str:
    return hashlib.sha1(texto.encode()).hexdigest()[:6]


def _listar_archivos(carpeta: Path) -> list[Path]:
    try:
        return [f for f in carpeta.iterdir() if f.is_file() and not f.is_symlink()]
    except PermissionError:
        return []


def _elegir_holdout(archivos: list[Path], rng: random.Random) -> list[Path]:
    if len(archivos) < MIN_ARCHIVOS_PARA_EVALUAR:
        return []
    n = min(MAX_HOLDOUT_POR_CARPETA, int(len(archivos) * FRACCION_MAX_HOLDOUT))
    if n < 1:
        return []
    return rng.sample(archivos, n)


def evaluar(
    indice: dict[str, EntradaCarpeta],
    umbral: float = UMBRAL_DEFAULT,
    seed: int | None = None,
    verbose: bool = False,
) -> list[CasoEvaluado]:
    rng = random.Random(seed)
    casos: list[CasoEvaluado] = []

    for clave, entrada in indice.items():
        archivos = _listar_archivos(entrada.ruta)
        holdout = _elegir_holdout(archivos, rng)
        if not holdout:
            continue

        # Reconstruir la señal de contenido de la carpeta SIN los archivos
        # elegidos, para no comparar cada archivo contra sí mismo.
        restantes = [f for f in archivos if f not in holdout]
        contenido_restante: set[str] = set()
        for archivo in restantes[:MAX_ARCHIVOS_MUESTRA]:
            contenido_restante |= tokenizar(extraer_texto(archivo))

        entrada_sin_holdout = EntradaCarpeta(
            ruta=entrada.ruta,
            nombre=entrada.nombre,
            tokens_nombre=entrada.tokens_nombre,
            tokens_contenido=contenido_restante,
            tokens_ancestros=entrada.tokens_ancestros,
            duplicadas=entrada.duplicadas,
        )
        indice_modificado = dict(indice)
        indice_modificado[clave] = entrada_sin_holdout

        carpeta_id = f"carpeta_{_id_corto(str(entrada.ruta))}"

        for archivo in holdout:
            tokens_contenido = tokenizar(extraer_texto(archivo))
            tokens_stem = tokenizar(archivo.stem)
            resultado = buscar_destino(tokens_contenido, tokens_stem, indice_modificado, umbral)

            if resultado.entrada is None:
                estado, destino_id = "sin_destino", None
            elif resultado.entrada.ruta == entrada.ruta:
                estado, destino_id = "correcto", carpeta_id
            else:
                estado = "incorrecto"
                destino_id = f"carpeta_{_id_corto(str(resultado.entrada.ruta))}"

            archivo_id = f"{_id_corto(str(archivo))}{archivo.suffix.lower()}"
            casos.append(CasoEvaluado(
                carpeta_id=carpeta_id,
                archivo_id=archivo_id,
                destino_id=destino_id,
                estado=estado,
                score=resultado.score,
                metodo=resultado.metodo,
                ruta_archivo=archivo if verbose else None,
                ruta_carpeta=entrada.ruta if verbose else None,
                ruta_predicha=resultado.entrada.ruta if (verbose and resultado.entrada) else None,
            ))

    return casos
