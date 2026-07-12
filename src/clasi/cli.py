"""Interfaz de línea de comandos: clasi sim | run | undo"""

import importlib.resources as _resources
import sys
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .classifier import Resultado, cargar_hints, clasificar
from .discovery import (
    MAX_DEPTH_DEFAULT,
    EntradaCarpeta,
    cargar_carpetas_genericas,
    construir_indice,
    tokenizar,
)
from .evaluator import CasoEvaluado, evaluar
from .executor import ejecutar, deshacer, merge_carpetas
from .scanner import cargar_exclusiones, escanear


def _ruta_config(nombre: str) -> Path:
    """~/.config/clasi/ primero; bundled en el paquete como fallback."""
    user = Path.home() / ".config" / "clasi" / nombre
    if user.exists():
        return user
    return Path(str(_resources.files("clasi").joinpath("config").joinpath(nombre)))


DEFAULT_HINTS     = _ruta_config("hints.yaml")
DEFAULT_EXCL      = _ruta_config("exclusions.yaml")
DEFAULT_GENERICAS = _ruta_config("carpetas_genericas.yaml")
LOGS_DIR          = Path.home() / ".local" / "share" / "clasi" / "logs"
_USER_CONFIG_DIR  = Path.home() / ".config" / "clasi"

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
    _sugerir_carpetas_nuevas(resultados)


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
    click.option("--verbose", is_flag=True, default=False,
                 help="Muestra rutas reales en lugar de hashes (no apto para compartir)."),
]

def _add_eval_options(func):
    for opcion in reversed(_opciones_evaluate):
        func = opcion(func)
    return func


@cli.command()
@_add_eval_options
def evaluate(directorio, exclusions, carpetas_genericas, umbral, max_depth, seed, verbose):
    """Mide qué tan seguido clasi regresa un archivo a la carpeta donde ya vivía (holdout)."""
    exclusiones = cargar_exclusiones(exclusions)
    genericos   = cargar_carpetas_genericas(carpetas_genericas)

    console.print(f"[dim]Descubriendo carpetas en {directorio} (profundidad ≤ {max_depth})…[/dim]")
    indice = construir_indice(directorio, exclusiones, max_depth, genericos)
    console.print(f"[dim]{len(indice)} carpetas indexadas.[/dim]")

    casos = evaluar(indice, umbral, seed, verbose=verbose)
    if not casos:
        console.print(
            "[yellow]No hay suficientes carpetas con ≥5 archivos para evaluar de forma confiable.[/yellow]"
        )
        return

    _mostrar_evaluacion(casos, verbose=verbose)


@cli.command()
@click.argument("redundante", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("canonica",   type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--conflicto", default="rename_new",
              type=click.Choice(["skip", "rename_new", "rename_existing"]),
              show_default=True,
              help="Qué hacer si el archivo ya existe en el destino.")
def merge(redundante, canonica, conflicto):
    """Unifica una carpeta redundante en la canónica (reversible con undo).

    Mueve todo el contenido de REDUNDANTE a CANONICA preservando subdirectorios.
    La carpeta REDUNDANTE queda vacía pero no se elimina.
    """
    redundante = redundante.expanduser().resolve()
    canonica   = canonica.expanduser().resolve()

    if redundante == canonica:
        console.print("[red]Las dos rutas son la misma carpeta.[/red]")
        raise SystemExit(1)
    if canonica.is_relative_to(redundante):
        console.print("[red]La canónica está dentro de la redundante — operación no segura.[/red]")
        raise SystemExit(1)

    ops_preview = merge_carpetas(redundante, canonica, conflicto, seco=True)

    if not ops_preview:
        console.print(f"[yellow]La carpeta está vacía: {redundante}[/yellow]")
        return

    _mostrar_merge_preview(ops_preview, redundante, canonica)

    movidos  = sum(1 for o in ops_preview if o["accion"] == "mover")
    omitidos = sum(1 for o in ops_preview if o["accion"] == "skip")
    console.print(
        f"\nSe moverán [bold]{movidos}[/bold] archivo(s)"
        + (f", se omitirán [yellow]{omitidos}[/yellow] (ya existen en destino)." if omitidos else ".")
        + " ¿Continuar? [y/N] ",
        end="",
    )
    if input().strip().lower() != "y":
        console.print("[yellow]Cancelado.[/yellow]")
        return

    nombre_log = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    ruta_log   = LOGS_DIR / nombre_log
    ops = merge_carpetas(redundante, canonica, conflicto, seco=False)

    movidos_real  = sum(1 for o in ops if o["accion"] == "mover")
    omitidos_real = sum(1 for o in ops if o["accion"] == "skip")

    if ops:
        ruta_log.parent.mkdir(parents=True, exist_ok=True)
        import json as _json
        with open(ruta_log, "w") as f:
            for op in ops:
                f.write(_json.dumps(op, ensure_ascii=False) + "\n")

    console.print(f"\n[green]Movidos:[/green] {movidos_real}  [yellow]Omitidos:[/yellow] {omitidos_real}")
    console.print(f"Log guardado en: [dim]{ruta_log}[/dim]")

    archivos_restantes = [f for f in redundante.rglob("*") if f.is_file() and not f.is_symlink()]
    if archivos_restantes:
        console.print(
            f"\n[yellow]⚠  La carpeta redundante aún tiene {len(archivos_restantes)} archivo(s) "
            f"(omitidos por conflicto).[/yellow]\n  {redundante}"
        )
    else:
        console.print(f"\n[dim]La carpeta redundante quedó vacía:[/dim] {redundante}")
        console.print(f"[dim]  Puedes eliminarla manualmente con: rm -r \"{redundante}\"[/dim]")


def _mostrar_merge_preview(ops: list[dict], origen: Path, destino: Path):
    tabla = Table(title=f"Merge: {origen.name} → {destino}", show_lines=False)
    tabla.add_column("Archivo",  style="cyan",  max_width=40)
    tabla.add_column("Destino",  style="green", max_width=40)
    tabla.add_column("Acción",   justify="center", max_width=12)

    for op in ops:
        archivo_rel = Path(op["archivo"]).relative_to(origen)
        if op["accion"] == "mover":
            destino_rel = Path(op["destino"]).relative_to(destino)
            accion_str  = "[green]mover[/green]"
            destino_str = str(destino_rel)
        else:
            accion_str  = "[yellow]skip[/yellow]"
            destino_str = "[dim]ya existe[/dim]"
        tabla.add_row(str(archivo_rel), destino_str, accion_str)

    console.print(tabla)


@cli.command("move-folder")
@click.argument("carpeta",     type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("nuevo_padre", type=click.Path(exists=True, file_okay=False, path_type=Path))
def move_folder(carpeta, nuevo_padre):
    """Reubica CARPETA dentro de NUEVO_PADRE (reversible con undo).

    Ejemplo: clasi move-folder ~/Downloads/Cálculo ~/Documents/
    """
    carpeta     = carpeta.expanduser().resolve()
    nuevo_padre = nuevo_padre.expanduser().resolve()
    destino     = nuevo_padre / carpeta.name

    if destino == carpeta:
        console.print("[red]El destino es el mismo que el origen.[/red]")
        raise SystemExit(1)
    if destino.exists():
        console.print(f"[red]Ya existe una carpeta con ese nombre en el destino:[/red] {destino}")
        raise SystemExit(1)
    if nuevo_padre.is_relative_to(carpeta):
        console.print("[red]El destino está dentro de la carpeta origen — operación no segura.[/red]")
        raise SystemExit(1)

    archivos = [f for f in carpeta.rglob("*") if f.is_file() and not f.is_symlink()]
    console.print(
        f"\nMover [bold]{carpeta.name}[/bold] ({len(archivos)} archivos)"
        f"\n  de: [dim]{carpeta.parent}[/dim]"
        f"\n  a:  [dim]{nuevo_padre}[/dim]"
        f"\n\n¿Continuar? [y/N] ",
        end="",
    )
    if input().strip().lower() != "y":
        console.print("[yellow]Cancelado.[/yellow]")
        return

    import json as _json
    import shutil as _shutil
    ops = []
    for f in archivos:
        ruta_rel   = f.relative_to(carpeta)
        dest_final = destino / ruta_rel
        ops.append({
            "accion":     "mover",
            "archivo":    str(f),
            "destino":    str(dest_final),
            "regla":      "move-folder",
            "confianza":  "alta",
            "ts":         datetime.now().isoformat(),
        })

    destino.parent.mkdir(parents=True, exist_ok=True)
    _shutil.move(str(carpeta), str(destino))

    nombre_log = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    ruta_log   = LOGS_DIR / nombre_log
    ruta_log.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta_log, "w") as f_log:
        for op in ops:
            f_log.write(_json.dumps(op, ensure_ascii=False) + "\n")

    console.print(f"[green]Carpeta movida:[/green] {destino}")
    console.print(f"Log guardado en: [dim]{ruta_log}[/dim]")


@cli.command()
@_add_options
@click.option("--output", default=None, type=click.Path(path_type=Path),
              help="Ruta del archivo markdown de salida (por defecto: logs/catalogo_<ts>.md).")
def catalog(directorio, hints, exclusions, carpetas_genericas, umbral, max_depth, output):
    """Genera un catálogo markdown de los archivos y sus destinos sugeridos."""
    resultados, _ = _clasificar(directorio, hints, exclusions, carpetas_genericas, umbral, max_depth)

    if output is None:
        nombre = f"catalogo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        output = LOGS_DIR / nombre

    directorio_resuelto = directorio.expanduser().resolve()
    con_destino = [r for r in resultados if r.destino]
    sin_destino = [r for r in resultados if not r.destino]

    lineas = [
        f"# Catálogo clasi — {directorio_resuelto}",
        f"",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"Total: {len(resultados)} archivos — "
        f"{len(con_destino)} con destino · {len(sin_destino)} sin destino",
        f"",
    ]

    if con_destino:
        lineas += [
            "## Con destino",
            "",
            "| Archivo | Destino | Método | Score |",
            "|---|---|---|---|",
        ]
        for r in con_destino:
            try:
                dest_str = str(r.destino.relative_to(directorio_resuelto))
            except ValueError:
                dest_str = str(r.destino)
            score_str = f"{r.score:.2f}" if r.score > 0 else "—"
            lineas.append(f"| {r.archivo.name} | {dest_str} | {r.metodo} | {score_str} |")
        lineas.append("")

    if sin_destino:
        lineas += [
            "## Sin destino",
            "",
            "| Archivo | Score más alto |",
            "|---|---|",
        ]
        for r in sin_destino:
            score_str = f"{r.score:.2f}" if r.score > 0 else "—"
            lineas.append(f"| {r.archivo.name} | {score_str} |")
        lineas.append("")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lineas))
    console.print(f"Catálogo guardado en: [dim]{output}[/dim]")
    console.print(
        f"[green]{len(con_destino)} con destino[/green] · "
        f"[red]{len(sin_destino)} sin destino[/red]"
    )


@cli.command()
@_add_options
@click.option(
    "--con-inciertos", is_flag=True, default=False,
    help="También muestra archivos con destino sugerido pero score < 0.5.",
)
def review(directorio, hints, exclusions, carpetas_genericas, umbral, max_depth, con_inciertos):
    """Revisión interactiva: confirma o redirige cada archivo sin destino.

    Muestra un panel por archivo con el texto extraído y la sugerencia del clasificador.
    Las decisiones se aplican de inmediato y quedan registradas para clasi undo.
    """
    import json as _json
    import re as _re
    import shutil as _shutil

    from rich.panel import Panel

    if not sys.stdin.isatty():
        console.print("[red]clasi review requiere una terminal interactiva.[/red]")
        raise SystemExit(1)

    resultados, indice = _clasificar(directorio, hints, exclusions, carpetas_genericas, umbral, max_depth)
    directorio_resuelto = directorio.expanduser().resolve()

    candidatos = [r for r in resultados if r.destino is None]
    if con_inciertos:
        candidatos += [r for r in resultados if r.destino is not None and r.score < 0.5]

    if not candidatos:
        console.print("[green]No hay archivos que revisar.[/green]")
        return

    tipo_desc = "sin destino" + (" + inciertos" if con_inciertos else "")
    console.print(f"\n[bold]{len(candidatos)} archivo(s) para revisar[/bold] [dim]({tipo_desc})[/dim]")
    console.print("[dim]  [[s]] confirmar sugerencia · [[c]] elegir carpeta · [[n]] saltar · [[q]] salir[/dim]\n")

    ops: list[dict] = []
    movidos = 0
    quit_review = False

    for i, resultado in enumerate(candidatos, 1):
        if quit_review:
            break

        tiene_sugerencia = resultado.destino is not None

        texto_raw = _re.sub(r"\s+", " ", resultado.texto_extraido.strip())[:250]
        texto_panel = texto_raw if texto_raw else "[dim](sin texto extraído)[/dim]"

        if tiene_sugerencia:
            try:
                dest_rel = str(resultado.destino.relative_to(directorio_resuelto))
            except ValueError:
                dest_rel = str(resultado.destino)
            sugerencia_str = f"[green]{dest_rel}[/green]  (score: {resultado.score:.2f})"
        else:
            sugerencia_str = f"[red]sin destino[/red]  (score máx: {resultado.score:.2f})"

        encabezado = f"review {i}/{len(candidatos)} · {'incierto' if tiene_sugerencia else 'sin destino'}"
        contenido = (
            f"[bold cyan]{resultado.archivo.name}[/bold cyan]\n\n"
            f"[dim]{texto_panel}[/dim]\n\n"
            f"Sugerencia: {sugerencia_str}"
        )
        console.print(Panel(contenido, title=encabezado, border_style="blue"))

        if tiene_sugerencia:
            console.print("  [cyan][[s]][/cyan] confirmar  [cyan][[c]][/cyan] otra carpeta  [cyan][[n]][/cyan] saltar  [cyan][[q]][/cyan] salir", end="  ")
        else:
            console.print("  [cyan][[c]][/cyan] elegir carpeta  [cyan][[n]][/cyan] saltar  [cyan][[q]][/cyan] salir", end="  ")

        while True:
            tecla = click.getchar().lower()

            if tecla == "q":
                console.print("\n[dim]Revisión terminada.[/dim]")
                quit_review = True
                break

            if tecla == "n":
                console.print("\n[dim]  → saltado[/dim]")
                break

            if tecla == "s" and tiene_sugerencia:
                destino_final = resultado.destino
                nombre_dest = destino_final / resultado.archivo.name
                if nombre_dest.exists():
                    console.print(f"\n[yellow]  Ya existe en destino — saltando.[/yellow]")
                    break
                destino_final.mkdir(parents=True, exist_ok=True)
                _shutil.move(str(resultado.archivo), str(nombre_dest))
                ops.append({
                    "accion":    "mover",
                    "archivo":   str(resultado.archivo),
                    "destino":   str(nombre_dest),
                    "regla":     "review",
                    "confianza": resultado.confianza,
                    "ts":        datetime.now().isoformat(),
                })
                movidos += 1
                console.print(f"\n[green]  → {dest_rel}[/green]")
                break

            if tecla == "c":
                console.print()
                destino_elegido = _elegir_carpeta(indice, directorio_resuelto)
                if destino_elegido is not None:
                    nombre_dest = destino_elegido / resultado.archivo.name
                    if nombre_dest.exists():
                        console.print(f"[yellow]  Ya existe en destino — saltando.[/yellow]")
                        break
                    destino_elegido.mkdir(parents=True, exist_ok=True)
                    _shutil.move(str(resultado.archivo), str(nombre_dest))
                    try:
                        dest_display = str(destino_elegido.relative_to(directorio_resuelto))
                    except ValueError:
                        dest_display = str(destino_elegido)
                    ops.append({
                        "accion":    "mover",
                        "archivo":   str(resultado.archivo),
                        "destino":   str(nombre_dest),
                        "regla":     "review-manual",
                        "confianza": "alta",
                        "ts":        datetime.now().isoformat(),
                    })
                    movidos += 1
                    console.print(f"[green]  → {dest_display}[/green]")
                    break
                # usuario canceló el buscador — volver a mostrar opciones
                if tiene_sugerencia:
                    console.print("  [cyan][[s]][/cyan] confirmar  [cyan][[c]][/cyan] otra carpeta  [cyan][[n]][/cyan] saltar  [cyan][[q]][/cyan] salir", end="  ")
                else:
                    console.print("  [cyan][[c]][/cyan] elegir carpeta  [cyan][[n]][/cyan] saltar  [cyan][[q]][/cyan] salir", end="  ")

        console.print()

    if ops:
        nombre_log = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        ruta_log = LOGS_DIR / nombre_log
        ruta_log.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta_log, "w") as f_log:
            for op in ops:
                f_log.write(_json.dumps(op, ensure_ascii=False) + "\n")
        console.print(f"[green]Movidos:[/green] {movidos}  Log: [dim]{ruta_log}[/dim]")
    else:
        console.print("[yellow]Ningún archivo movido.[/yellow]")


def _elegir_carpeta(
    indice: dict[str, "EntradaCarpeta"],
    directorio_resuelto: Path,
) -> Path | None:
    """Buscador interactivo de carpetas por texto parcial. Devuelve la ruta elegida o None."""
    console.print("[bold]Buscar carpeta[/bold] (Enter para cancelar):")
    try:
        query = input("  > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None
    if not query:
        return None

    matches = [
        entrada
        for nombre, entrada in sorted(indice.items())
        if query in nombre.lower()
    ]

    if not matches:
        console.print("[yellow]  Sin resultados.[/yellow]")
        return None

    visible = matches[:10]
    console.print()
    for j, entrada in enumerate(visible, 1):
        try:
            nombre_rel = str(entrada.ruta.relative_to(directorio_resuelto))
        except ValueError:
            nombre_rel = str(entrada.ruta)
        console.print(f"  [bold]{j}.[/bold] {nombre_rel}")

    if len(matches) > 10:
        console.print(f"  [dim]… y {len(matches) - 10} más (refina la búsqueda)[/dim]")

    console.print()
    try:
        eleccion = input(f"  Número (1–{len(visible)}) o Enter para cancelar: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not eleccion:
        return None
    try:
        idx = int(eleccion) - 1
        if 0 <= idx < len(visible):
            return visible[idx].ruta
    except ValueError:
        pass

    console.print("[yellow]  Elección inválida.[/yellow]")
    return None


@cli.command()
@click.option("--output", default=None, type=click.Path(path_type=Path),
              help="Ruta de salida (por defecto: config/exclusions.yaml del proyecto).")
@click.option("--forzar", is_flag=True,
              help="Sobreescribir sin pedir confirmación si ya existe.")
def init(output, forzar):
    """Genera exclusions.yaml adaptado al sistema detectado.

    Detecta herramientas de desarrollo presentes (~/.cargo, ~/.npm, etc.)
    y directorios de proyectos de código (~/Projects, ~/Proyectos, etc.)
    para construir una configuración de exclusiones desde cero.
    """
    from .init import detectar, generar_yaml

    ruta_salida = Path(output) if output else _USER_CONFIG_DIR / "exclusions.yaml"

    if ruta_salida.exists() and not forzar:
        console.print(f"[yellow]Ya existe:[/yellow] {ruta_salida}")
        console.print("Usa [bold]--forzar[/bold] para sobreescribir.")
        raise SystemExit(1)

    console.print("[dim]Escaneando el sistema…[/dim]")
    home = Path.home()
    resultado = detectar(home)

    herramientas  = resultado["herramientas"]
    dirs_proyecto = resultado["dirs_proyecto"]

    console.print()
    if herramientas:
        console.print("[bold]Herramientas detectadas:[/bold]")
        for nombre, desc in herramientas:
            console.print(f"  [green]✓[/green] [dim]{nombre}[/dim]  {desc}")
    else:
        console.print("[dim]No se detectaron herramientas de desarrollo en ~.[/dim]")

    console.print()
    if dirs_proyecto:
        console.print("[bold]Directorios de proyectos detectados:[/bold]")
        for ruta in dirs_proyecto:
            console.print(f"  [green]✓[/green] {ruta}")
    else:
        console.print("[dim]No se detectaron directorios de proyectos en ~.[/dim]")

    console.print()
    console.print(f"Se generará: [bold]{ruta_salida}[/bold]")
    console.print("¿Continuar? [y/N] ", end="")
    if input().strip().lower() != "y":
        console.print("[yellow]Cancelado.[/yellow]")
        return

    contenido = generar_yaml(resultado, home)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    ruta_salida.write_text(contenido)
    console.print(f"\n[green]Generado:[/green] {ruta_salida}")
    console.print(
        "[dim]Edita el archivo para añadir rutas específicas de tu sistema.[/dim]"
    )


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


MIN_ARCHIVOS_PARA_CARPETA = 7
# Tokens demasiado genéricos para nombrar una carpeta nueva
_TOKENS_IGNORADOS = {
    "tarea", "portada", "actividad", "practica", "examen", "unidad",
    "proyecto", "ejercicio", "notas", "apuntes", "resumen", "clase",
    "documento", "archivo", "nuevo", "copia", "sin", "con", "de", "la",
    "el", "los", "las", "del", "al", "por", "para",
}


def _sugerir_carpetas_nuevas(resultados: list):
    """
    Analiza archivos sin destino y sugiere crear una carpeta cuando
    ≥ MIN_ARCHIVOS_PARA_CARPETA comparten un token temático en su nombre.
    """
    sin_destino = [r for r in resultados if r.destino is None]
    if len(sin_destino) < MIN_ARCHIVOS_PARA_CARPETA:
        return

    from collections import defaultdict
    token_a_archivos: dict[str, list] = defaultdict(list)

    for r in sin_destino:
        tokens = tokenizar(r.archivo.stem) - _TOKENS_IGNORADOS
        # Solo tokens alfabéticos de ≥4 letras (excluye números y códigos cortos)
        tokens = {t for t in tokens if t.isalpha() and len(t) >= 4}
        for t in tokens:
            token_a_archivos[t].append(r.archivo.name)

    candidatos = [
        (t, archivos)
        for t, archivos in token_a_archivos.items()
        if len(archivos) >= MIN_ARCHIVOS_PARA_CARPETA
    ]
    if not candidatos:
        return

    console.print()
    console.print("[bold yellow]💡 Posibles carpetas nuevas[/bold yellow]")
    console.print(
        f"[dim]  {MIN_ARCHIVOS_PARA_CARPETA}+ archivos sin destino comparten un tema "
        f"— podrías crear estas carpetas:[/dim]"
    )
    for token, archivos in sorted(candidatos, key=lambda x: -len(x[1])):
        console.print(f"\n  [cyan]{token!r}[/cyan] — {len(archivos)} archivos:")
        for nombre in archivos[:5]:
            console.print(f"    [dim]· {nombre}[/dim]")
        if len(archivos) > 5:
            console.print(f"    [dim]  … y {len(archivos) - 5} más[/dim]")


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


def _mostrar_evaluacion(casos: list[CasoEvaluado], verbose: bool = False):
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

    if verbose:
        titulo = "Detalle — rutas reales (no apto para compartir)"
        tabla = Table(title=titulo)
        tabla.add_column("Carpeta real",      style="dim", max_width=40)
        tabla.add_column("Archivo",           style="cyan", max_width=30)
        tabla.add_column("Resultado")
        tabla.add_column("Predicho",          style="dim", max_width=40)
        tabla.add_column("Score", justify="right")
        tabla.add_column("Método", style="dim")

        for c in casos:
            carpeta_str  = str(c.ruta_carpeta) if c.ruta_carpeta else c.carpeta_id
            archivo_str  = c.ruta_archivo.name if c.ruta_archivo else c.archivo_id
            predicho_str = str(c.ruta_predicha) if c.ruta_predicha else ("—" if c.destino_id is None else c.destino_id)
            tabla.add_row(
                carpeta_str,
                archivo_str,
                f"[{color_estado[c.estado]}]{c.estado}[/{color_estado[c.estado]}]",
                predicho_str,
                f"{c.score:.2f}",
                c.metodo,
            )
    else:
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
    if not verbose:
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
