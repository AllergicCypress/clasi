"""
Motor de clasificación: decide el destino de cada archivo.

Orden de evaluación:
  1. hints.yaml  — casos especiales sin semántica temática (duplicados, instaladores…)
  2. Descubrimiento dinámico — índice de carpetas existentes (TF-IDF simple)
  3. Sin destino — reportar, no mover
"""

import fnmatch
from dataclasses import dataclass
from pathlib import Path

import yaml

from discovery import (
    EntradaCarpeta,
    ResultadoDescubrimiento,
    buscar_destino,
    tokenizar,
)
from extractor import extraer_texto


# ── Estructura de resultado ───────────────────────────────────────────────────

@dataclass
class Resultado:
    archivo: Path
    destino: Path | None        # None → no mover
    regla: str                  # nombre del hint o "descubrimiento"
    confianza: str              # "alta", "media", "baja"
    score: float                # score TF-IDF (0.0 si viene de hint)
    metodo: str                 # "hint", "nombre", "contenido", "ninguno"
    conflicto: str              # "skip", "rename_new", "rename_existing"
    texto_extraido: str


# ── Carga de hints ────────────────────────────────────────────────────────────

def cargar_hints(ruta: Path) -> list[dict]:
    with open(ruta) as f:
        config = yaml.safe_load(f)
    return config.get("hints", [])


# ── Evaluación de hints ───────────────────────────────────────────────────────

UMBRAL_TEXTO_CORRUPTO = 0.05


def _ratio_caracteres_control(texto: str) -> float:
    """
    Fracción de caracteres de control (fuera de \\n\\r\\t) en `texto`.

    Las letras acentuadas latinas (ñ, î, ø…) son alfabéticas para Python
    (`isalnum()` las acepta), así que no sirven para detectar texto corrupto.
    Los caracteres de control SÍ son una señal confiable: nunca aparecen en
    texto real, pero sí cuando `pdftotext` decodifica una fuente sin tabla
    de codificación real (PDF generado/escaneado sin capa de texto legible) —
    confirmado con casos reales (`clasi evaluate`, sesión 2026-06-22).
    """
    if not texto:
        return 0.0
    malos = sum(
        1 for c in texto
        if (ord(c) < 32 and c not in "\n\r\t") or 127 <= ord(c) <= 159
    )
    return malos / len(texto)


def _texto_corrupto(texto: str) -> bool:
    return _ratio_caracteres_control(texto) > UMBRAL_TEXTO_CORRUPTO


def _evaluar_filtro(archivo: Path, texto: str, filtro: dict) -> bool:
    if "extension" in filtro:
        return archivo.suffix.lower() in [e.lower() for e in filtro["extension"]]
    if "nombre_contiene" in filtro:
        nombre = archivo.name.lower()
        return any(p.lower() in nombre for p in filtro["nombre_contiene"])
    if "nombre_glob" in filtro:
        return fnmatch.fnmatch(archivo.name, filtro["nombre_glob"])
    if "texto_contiene" in filtro:
        texto_lower = texto.lower()
        return any(p.lower() in texto_lower for p in filtro["texto_contiene"])
    if "texto_corrupto" in filtro:
        return _texto_corrupto(texto)
    if "tiene_merged" in filtro:
        merged = archivo.parent / f"{archivo.stem}_merged{archivo.suffix}"
        return merged.is_file() and not merged.is_symlink()
    return False


def _coincide_hint(archivo: Path, texto: str, hint: dict) -> bool:
    filtros = hint.get("filtros", [])
    modo = hint.get("filter_mode", "any")
    if not filtros:
        return False
    resultados = [_evaluar_filtro(archivo, texto, f) for f in filtros]
    return any(resultados) if modo == "any" else all(resultados)


def _aplicar_hint(
    archivo: Path,
    hint: dict,
    directorio_base: Path,
) -> tuple[Path | None, str]:
    """
    Devuelve (ruta_destino, conflicto) para un hint que ya coincidió.
    `accion_especial` determina qué carpeta usar.
    """
    accion = hint.get("accion_especial", "carpeta_especial")
    conflicto = hint.get("conflicto", "skip")

    if accion == "marcar_duplicado":
        destino = directorio_base / "_Duplicados"
    elif accion == "carpeta_especial":
        nombre_carpeta = hint.get("nombre_carpeta", "_Especiales")
        destino = directorio_base / nombre_carpeta
    else:
        destino = None

    return destino, conflicto


# ── Clasificación principal ───────────────────────────────────────────────────

def clasificar(
    archivo: Path,
    hints: list[dict],
    indice: dict[str, EntradaCarpeta],
    directorio_base: Path,
    umbral: float = 0.20,
) -> Resultado:
    """
    Clasifica un archivo en dos etapas:
      1. Hints (prioridad alta, sin extracción de texto si solo usa extensión/nombre)
      2. Descubrimiento dinámico por TF-IDF
    """
    texto = extraer_texto(archivo)

    # ── Etapa 1: hints ────────────────────────────────────────────────────────
    for hint in hints:
        if _coincide_hint(archivo, texto, hint):
            destino, conflicto = _aplicar_hint(archivo, hint, directorio_base)
            return Resultado(
                archivo=archivo,
                destino=destino,
                regla=hint.get("nombre", "hint"),
                confianza="alta",
                score=0.0,
                metodo="hint",
                conflicto=conflicto,
                texto_extraido=texto,
            )

    # ── Etapa 2: descubrimiento dinámico ─────────────────────────────────────
    tokens_contenido = tokenizar(texto)
    tokens_stem      = tokenizar(archivo.stem)
    resultado: ResultadoDescubrimiento = buscar_destino(
        tokens_contenido, tokens_stem, indice, umbral
    )

    if resultado.entrada is not None:
        confianza = "alta" if resultado.score >= 0.5 else "media"
        return Resultado(
            archivo=archivo,
            destino=resultado.entrada.ruta,
            regla="descubrimiento",
            confianza=confianza,
            score=resultado.score,
            metodo=resultado.metodo,
            conflicto="skip",
            texto_extraido=texto,
        )

    # ── Etapa 3: sin destino ─────────────────────────────────────────────────
    return Resultado(
        archivo=archivo,
        destino=None,
        regla="sin_destino",
        confianza="baja",
        score=resultado.score,
        metodo="ninguno",
        conflicto="skip",
        texto_extraido=texto,
    )
