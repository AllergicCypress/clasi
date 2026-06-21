"""Interfaz de línea de comandos: clasi sim | run | undo"""

import sys
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent))

from classifier import Resultado, cargar_hints, clasificar
from discovery import (
    MAX_DEPTH_DEFAULT,
    EntradaCarpeta,
    cargar_carpetas_genericas,
    construir_indice,
)
from evaluator import CasoEvaluado, evaluar
from executor import ejecutar, deshacer
from scanner import cargar_exclusiones, escanear

PROYECTO_DIR    = Path(__file__).parent.parent
DEFAULT_HINTS   = PROYECTO_DIR / "config" / "hints.yaml"
DEFAULT_EXCL    = PROYECTO_DIR / "config" / "exclusions.yaml"
DEFAULT_GENERICAS = PROYECTO_DIR / "config" / "carpetas_genericas.yaml"
LOGS_DIR        = PROYECTO_DIR / "logs"

console = Console()


@click.group()
def cli():
    """clasi — clasificador automático de archivos."""


# ── Opciones comunes ──────────────────────────────────────────────────────────

_opciones_comunes = [
    click.argument("directorio", type=click.Path(exists=True, file_okay=False, path_type=Path)),
    click.option("--hints",      default=DEFAULT_HINTS, type=click.Path(path_type=Path), show_default=True),
    click.option("--exclusions", default=DEFAULT_EXCL,  type=click.Path(path_type=Path), show_default=True),
    click.option("--carpetas-genericas", default=DEFAULT_GENERICAS, type=click.Path(path_type=Path),
                 show_default=True,
                 help="Carpetas contenedoras (no temáticas) que no deben usarse como destino."),
    click.option("--umbral",     default=0.40, type=float, show_default=True,
                 help="Score mínimo TF-IDF para aceptar un match (0.0–1.0)."),
    click.option("--max-depth",  default=MAX_DEPTH_DEFAULT, type=int, show_default=True,
                 help="Profundidad máxima del descubrimiento recursivo de carpetas."),
]

def _add_options(func):
    for opcion in reversed(_opciones_comunes):
        func = opcion(func)
    return func


# ── Subcomandos ───────────────────────────────────────────────────────────────

@cli.command()
@_add_options
def sim(directorio, hints, exclusions, carpetas_genericas, umbral, max_depth):
    """Simula la clasificación sin mover nada."""
    resultados, indice = _clasificar(directorio, hints, exclusions, carpetas_genericas, umbral, max_depth)
    _mostrar_tabla(resultados, directorio, seco=True)
    _mostrar_advertencias_duplicadas(indice)


@cli.command()
@_add_options
def run(directorio, hints, exclusions, carpetas_genericas, umbral, max_depth):
    """Clasifica y mueve los archivos."""
    resultados, indice = _clasificar(directorio, hints, exclusions, carpetas_genericas, umbral, max_depth)
    _mostrar_tabla(resultados, directorio, seco=False)
    _mostrar_advertencias_duplicadas(indice)

    con_destino = [r for r in resultados if r.destino is not None]
    if not con_destino:
        console.print("[yellow]No hay archivos para mover.[/yellow]")
        return

    console.print(f"\nSe moverán [bold]{len(con_destino)}[/bold] archivo(s). ¿Continuar? [y/N] ", end="")
    if input().strip().lower() != "y":
        console.print("[yellow]Cancelado.[/yellow]")
        return

    nombre_log = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    ruta_log   = LOGS_DIR / nombre_log

    ops     = ejecutar(resultados, ruta_log, seco=False)
    movidos = sum(1 for o in ops if o["accion"] == "mover")
    omitidos= sum(1 for o in ops if o["accion"] == "skip")

    console.print(f"\n[green]Movidos:[/green] {movidos}  [yellow]Omitidos:[/yellow] {omitidos}")
    console.print(f"Log guardado en: [dim]{ruta_log}[/dim]")


_opciones_evaluate = [
    click.argument("directorio", type=click.Path(exists=True, file_okay=False, path_type=Path)),
    click.option("--exclusions", default=DEFAULT_EXCL, type=click.Path(path_type=Path), show_default=True),
    click.option("--carpetas-genericas", default=DEFAULT_GENERICAS, type=click.Path(path_type=Path),
                 show_default=True),
    click.option("--umbral",    default=0.40, type=float, show_default=True),
    click.option("--max-depth", default=MAX_DEPTH_DEFAULT, type=int, show_default=True),
    click.option("--seed", default=None, type=int,
                 help="Semilla para reproducir la misma selección de archivos holdout."),
]

def _add_eval_options(func):
    for opcion in reversed(_opciones_evaluate):
        func = opcion(func)
    return func


@cli.command()
@_add_eval_options
def evaluate(directorio, exclusions, carpetas_genericas, umbral, max_depth, seed):
    """Mide qué tan seguido clasi regresa un archivo a la carpeta donde ya vivía (holdout)."""
    exclusiones = cargar_exclusiones(exclusions)
    genericos   = cargar_carpetas_genericas(carpetas_genericas)

    console.print(f"[dim]Descubriendo carpetas en {directorio} (profundidad ≤ {max_depth})…[/dim]")
    indice = construir_indice(directorio, exclusiones, max_depth, genericos)
    console.print(f"[dim]{len(indice)} carpetas indexadas.[/dim]")

    casos = evaluar(indice, umbral, seed)
    if not casos:
        console.print(
            "[yellow]No hay suficientes carpetas con ≥5 archivos para evaluar de forma confiable.[/yellow]"
        )
        return

    _mostrar_evaluacion(casos)


@cli.command()
def undo():
    """Revierte la última ejecución."""
    logs = sorted(LOGS_DIR.glob("*.jsonl"))
    if not logs:
        console.print("[red]No hay ningún log para revertir.[/red]")
        return

    ruta_log = logs[-1]
    console.print(f"Revirtiendo: [dim]{ruta_log.name}[/dim]")
    revertidas = deshacer(ruta_log)

    if revertidas:
        ruta_log.unlink()
        console.print(f"[green]Revertidas {len(revertidas)} operaciones.[/green]")
    else:
        console.print("[yellow]No había operaciones que revertir.[/yellow]")


# ── Lógica interna ────────────────────────────────────────────────────────────

def _clasificar(
    directorio: Path,
    hints_path: Path,
    exclusions_path: Path,
    carpetas_genericas_path: Path,
    umbral: float,
    max_depth: int,
) -> tuple[list[Resultado], dict[str, EntradaCarpeta]]:
    exclusiones = cargar_exclusiones(exclusions_path)
    hints       = cargar_hints(hints_path)
    genericos   = cargar_carpetas_genericas(carpetas_genericas_path)

    console.print(f"[dim]Descubriendo carpetas en {directorio} (profundidad ≤ {max_depth})…[/dim]")
    indice = construir_indice(directorio, exclusiones, max_depth, genericos)
    console.print(f"[dim]{len(indice)} carpetas indexadas.[/dim]")

    archivos   = list(escanear(directorio, exclusiones))
    directorio = directorio.expanduser().resolve()

    resultados = [
        clasificar(a, hints, indice, directorio, umbral)
        for a in archivos
    ]
    return resultados, indice


def _mostrar_tabla(resultados: list[Resultado], directorio: Path, seco: bool):
    titulo = "Simulación — ningún archivo será movido" if seco else "Clasificación"
    tabla  = Table(title=titulo, show_lines=False)

    tabla.add_column("Archivo",  style="cyan",  no_wrap=True, max_width=35)
    tabla.add_column("Destino",  style="green",               max_width=30)
    tabla.add_column("Método",   style="dim",                 max_width=14)
    tabla.add_column("Score",    justify="right",              max_width=6)
    tabla.add_column("Conf.",    justify="center",             max_width=6)

    directorio = directorio.expanduser().resolve()

    for r in resultados:
        if r.destino:
            try:
                destino_str = str(r.destino.relative_to(directorio))
            except ValueError:
                destino_str = str(r.destino)
        else:
            destino_str = "[red]sin destino[/red]"

        score_str = f"{r.score:.2f}" if r.score > 0 else "—"
        conf_color = {"alta": "green", "media": "yellow", "baja": "red"}.get(r.confianza, "dim")

        tabla.add_row(
            r.archivo.name,
            destino_str,
            r.metodo,
            score_str,
            f"[{conf_color}]{r.confianza}[/{conf_color}]",
        )

    console.print(tabla)

    con_destino = sum(1 for r in resultados if r.destino)
    sin_destino = len(resultados) - con_destino
    console.print(
        f"Total: [bold]{len(resultados)}[/bold] archivos — "
        f"[green]{con_destino} con destino[/green] · "
        f"[red]{sin_destino} sin destino[/red]"
    )


def _mostrar_advertencias_duplicadas(indice: dict[str, EntradaCarpeta]):
    """Muestra advertencias de carpetas duplicadas detectadas durante el descubrimiento."""
    duplicadas = [
        entrada for entrada in indice.values()
        if entrada.duplicadas
    ]
    if not duplicadas:
        return

    console.print()
    console.print("[yellow bold]⚠  Carpetas duplicadas detectadas[/yellow bold]")
    console.print("[dim]  Se usará la carpeta canónica (mejor ubicación) como destino.[/dim]")

    for entrada in sorted(duplicadas, key=lambda e: e.nombre):
        console.print(f"\n  [green]✓[/green] Canónica: [bold]{entrada.ruta}[/bold]")
        for otra in entrada.duplicadas:
            console.print(f"  [yellow]⚠[/yellow] Duplicada: {otra}")
            console.print(
                f"     [dim]→ Considera ejecutar: clasi merge '{otra}' '{entrada.ruta}'[/dim]"
            )


def _mostrar_evaluacion(casos: list[CasoEvaluado]):
    total       = len(casos)
    correctos   = sum(1 for c in casos if c.estado == "correcto")
    incorrectos = sum(1 for c in casos if c.estado == "incorrecto")
    sin_destino = sum(1 for c in casos if c.estado == "sin_destino")

    console.print()
    console.print(f"[bold]Evaluación por holdout — {total} archivo(s) de prueba[/bold]")
    console.print(
        f"[green]Correctos: {correctos} ({correctos/total:.0%})[/green]  "
        f"[red]Incorrectos: {incorrectos} ({incorrectos/total:.0%})[/red]  "
        f"[yellow]Sin destino: {sin_destino} ({sin_destino/total:.0%})[/yellow]"
    )

    color_estado = {"correcto": "green", "incorrecto": "red", "sin_destino": "yellow"}

    tabla = Table(title="Detalle — identificadores con hash, seguro de compartir")
    tabla.add_column("Carpeta",           style="dim")
    tabla.add_column("Archivo",           style="cyan")
    tabla.add_column("Resultado")
    tabla.add_column("Destino predicho",  style="dim")
    tabla.add_column("Score", justify="right")
    tabla.add_column("Método", style="dim")

    for c in casos:
        tabla.add_row(
            c.carpeta_id,
            c.archivo_id,
            f"[{color_estado[c.estado]}]{c.estado}[/{color_estado[c.estado]}]",
            c.destino_id or "—",
            f"{c.score:.2f}",
            c.metodo,
        )
    console.print(tabla)

    nombre_log = f"evaluacion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    ruta_log   = LOGS_DIR / nombre_log
    _guardar_reporte_evaluacion(ruta_log, casos, total, correctos, incorrectos, sin_destino)
    console.print(f"\nReporte guardado en: [dim]{ruta_log}[/dim]")
    console.print("[dim]Solo contiene identificadores con hash (no nombres reales) — seguro de adjuntar a un issue.[/dim]")


def _guardar_reporte_evaluacion(
    ruta: Path,
    casos: list[CasoEvaluado],
    total: int,
    correctos: int,
    incorrectos: int,
    sin_destino: int,
):
    lineas = [
        "# clasi evaluate report",
        "",
        "All identifiers below are short hashes, not real file or folder names — safe to paste into a GitHub issue as-is.",
        "",
        f"- Total evaluated: {total}",
        f"- Correct: {correctos} ({correctos/total:.0%})",
        f"- Incorrect (routed elsewhere): {incorrectos} ({incorrectos/total:.0%})",
        f"- No destination: {sin_destino} ({sin_destino/total:.0%})",
        "",
        "| Folder | File | Result | Predicted destination | Score | Method |",
        "|---|---|---|---|---|---|",
    ]
    for c in casos:
        lineas.append(
            f"| {c.carpeta_id} | {c.archivo_id} | {c.estado} | {c.destino_id or '—'} | {c.score:.2f} | {c.metodo} |"
        )
    ruta.write_text("\n".join(lineas) + "\n")


if __name__ == "__main__":
    cli()
