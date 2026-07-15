"""Recorre un directorio y devuelve los archivos a procesar, respetando exclusiones."""

import fnmatch
from pathlib import Path
from typing import Iterator

import yaml

SCAN_DEPTH_DEFAULT = 8


def cargar_exclusiones(ruta_config: Path) -> dict:
    with open(ruta_config) as f:
        return yaml.safe_load(f) or {}


def _expandir_rutas(rutas: list[str]) -> list[Path]:
    return [Path(r).expanduser().resolve() for r in rutas]


def escanear(directorio: Path, exclusiones: dict, max_depth: int = SCAN_DEPTH_DEFAULT) -> Iterator[Path]:
    carpetas_excluidas = set(exclusiones.get("carpetas_exactas") or [])
    patrones_excluidos = exclusiones.get("patrones_nombre") or []
    rutas_absolutas = _expandir_rutas(exclusiones.get("rutas_absolutas") or [])

    directorio = directorio.expanduser().resolve()

    def _recorrer(carpeta: Path, profundidad: int) -> Iterator[Path]:
        if profundidad > max_depth:
            return
        try:
            entradas = list(carpeta.iterdir())
        except PermissionError:
            return
        for entrada in entradas:
            if entrada.is_symlink():
                continue
            if entrada.is_file():
                if not _excluido(entrada, carpetas_excluidas, patrones_excluidos, rutas_absolutas):
                    yield entrada
            elif entrada.is_dir():
                if not _directorio_excluido(entrada, carpetas_excluidas, rutas_absolutas):
                    yield from _recorrer(entrada, profundidad + 1)

    yield from _recorrer(directorio, 1)


def _directorio_excluido(
    directorio: Path,
    carpetas_excluidas: set,
    rutas_absolutas: list[Path],
) -> bool:
    for ruta in rutas_absolutas:
        if directorio == ruta or str(directorio).startswith(str(ruta) + "/"):
            return True
    for parte in directorio.parts:
        if parte in carpetas_excluidas:
            return True
    return False


def _excluido(
    archivo: Path,
    carpetas_excluidas: set,
    patrones: list[str],
    rutas_absolutas: list[Path],
) -> bool:
    for ruta in rutas_absolutas:
        if archivo == ruta or str(archivo).startswith(str(ruta) + "/"):
            return True
    for parte in archivo.parts:
        if parte in carpetas_excluidas:
            return True
    nombre = archivo.name
    for patron in patrones:
        if fnmatch.fnmatch(nombre, patron):
            return True
    return False
