"""Recorre un directorio y devuelve los archivos a procesar, respetando exclusiones."""

import fnmatch
from pathlib import Path
from typing import Iterator

import yaml


def cargar_exclusiones(ruta_config: Path) -> dict:
    with open(ruta_config) as f:
        return yaml.safe_load(f)


def _expandir_rutas(rutas: list[str]) -> list[Path]:
    return [Path(r).expanduser().resolve() for r in rutas]


def escanear(directorio: Path, exclusiones: dict) -> Iterator[Path]:
    carpetas_excluidas = set(exclusiones.get("carpetas_exactas", []))
    patrones_excluidos = exclusiones.get("patrones_nombre", [])
    rutas_absolutas = _expandir_rutas(exclusiones.get("rutas_absolutas", []))

    directorio = directorio.expanduser().resolve()

    for archivo in directorio.iterdir():
        if not archivo.is_file() or archivo.is_symlink():
            continue
        if _excluido(archivo, carpetas_excluidas, patrones_excluidos, rutas_absolutas):
            continue
        yield archivo


def _excluido(
    archivo: Path,
    carpetas_excluidas: set,
    patrones: list[str],
    rutas_absolutas: list[Path],
) -> bool:
    # Ruta absoluta exacta
    for ruta in rutas_absolutas:
        if archivo == ruta or str(archivo).startswith(str(ruta) + "/"):
            return True

    # Algún componente del path está en la lista de carpetas excluidas
    for parte in archivo.parts:
        if parte in carpetas_excluidas:
            return True

    # Nombre coincide con un patrón glob
    nombre = archivo.name
    for patron in patrones:
        if fnmatch.fnmatch(nombre, patron):
            return True

    return False
