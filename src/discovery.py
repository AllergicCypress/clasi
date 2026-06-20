"""
Motor de descubrimiento: construye un índice dinámico de carpetas existentes
y puntúa archivos nuevos contra ese índice.

Principio: la estructura de carpetas del usuario ES la configuración.
Las reglas no prescriben destinos; este módulo los descubre en tiempo de ejecución.
"""

import fnmatch
import re
import unicodedata
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Iterator

import yaml

from extractor import extraer_texto

# ── Parámetros ────────────────────────────────────────────────────────────────

MAX_ARCHIVOS_MUESTRA = 5   # archivos a muestrear por carpeta para enriquecer índice
MIN_LONGITUD_TOKEN   = 3   # ignorar tokens muy cortos ("de", "la", "el"…)
UMBRAL_DEFAULT       = 0.40
MAX_DEPTH_DEFAULT    = 4   # profundidad máxima del descubrimiento recursivo

# Homogeneidad de contenido entre archivos de una misma carpeta (REV-001):
# detecta contenedoras no listadas en carpetas_genericas.yaml. Provisional,
# pendiente de calibrar con datos reales (igual que se calibró UMBRAL_DEFAULT).
UMBRAL_HOMOGENEIDAD      = 0.15
MIN_ARCHIVOS_HOMOGENEIDAD = 3   # con menos muestras la métrica no es confiable

# Más allá de esta profundidad, una carpeta ya vive dentro de un tema
# (ej. Metodos Numericos/UNIDAD 2/2.2) y el archivo encaja por nombre,
# no por homogeneidad de contenido — exigirla generaría falsos positivos
# (confirmado con datos reales: PAPC1.3, 2.2, EU4 cayeron por homogeneidad
# pese a ser destinos correctos por nombre exacto).
MAX_PROFUNDIDAD_HOMOGENEIDAD = 2

# 0.40 requiere match completo del nombre de carpeta (score_nombre=1.0 → 0.70)
# o match parcial + contenido significativo. Calibrado para evitar que
# documentos que MENCIONAN un tema sean clasificados como pertenecientes a él.

STOPWORDS = {
    # Español
    "del", "los", "las", "una", "uno", "con", "por", "para", "que",
    "como", "mas", "sin", "sobre", "entre", "desde", "hasta", "hacia",
    "bajo", "ante", "tras", "segun", "durante", "mediante", "estos",
    "esta", "este", "esos", "esas", "ese", "esa", "sus", "son", "fue",
    "ser", "hay", "muy", "pero", "sino", "cuando", "donde", "porque",
    "aunque", "tanto", "cada", "todo", "toda", "todos", "todas",
    # Inglés
    "the", "and", "for", "that", "this", "with", "from", "are", "was",
    "were", "been", "have", "has", "had", "not", "but", "can", "will",
    "its", "our", "your", "their", "they", "them", "then", "than",
    "also", "into", "onto", "upon", "would", "could", "should",
}


# ── Estructuras de datos ──────────────────────────────────────────────────────

@dataclass
class EntradaCarpeta:
    ruta: Path
    nombre: str
    # Tokens del nombre de carpeta — señal primaria (peso 0.7)
    tokens_nombre: set[str] = field(default_factory=set)
    # Tokens extraídos de una muestra del contenido — señal secundaria (peso 0.3)
    tokens_contenido: set[str] = field(default_factory=set)
    # Otras rutas con el mismo nombre normalizado (no canónicas)
    duplicadas: list[Path] = field(default_factory=list)


@dataclass
class ResultadoDescubrimiento:
    entrada: EntradaCarpeta | None
    score: float
    metodo: str   # "nombre", "contenido", "ninguno"


# ── Normalización de texto ────────────────────────────────────────────────────

def _quitar_acentos(texto: str) -> str:
    normalizado = unicodedata.normalize("NFD", texto)
    return "".join(c for c in normalizado if unicodedata.category(c) != "Mn")


def normalizar_nombre(nombre: str) -> str:
    """
    Normaliza el nombre de una carpeta para comparación de duplicados:
    sin acentos, minúsculas, sin espacios ni separadores.
    Ejemplo: "Métodos Numéricos" → "metodosnumericos"
    """
    sin_acentos = _quitar_acentos(nombre)
    return re.sub(r"[\s_\-]+", "", sin_acentos.lower())


def tokenizar(texto: str) -> set[str]:
    """Convierte texto a conjunto de tokens: sin acentos, minúsculas, sin stopwords."""
    tokens = re.findall(r"[a-zA-Z0-9]+", _quitar_acentos(texto).lower())
    return {t for t in tokens if t not in STOPWORDS and len(t) >= MIN_LONGITUD_TOKEN}


def _profundidad_relativa(ruta: Path, *bases: Path) -> int:
    """Profundidad de `ruta` respecto a la primera `base` de la que es descendiente."""
    for base in bases:
        try:
            return len(ruta.relative_to(base).parts)
        except ValueError:
            continue
    return 999


# ── Prioridad canónica de carpetas ────────────────────────────────────────────

def _prioridad(ruta: Path) -> tuple[int, int]:
    """
    Determina la prioridad de una carpeta para selección canónica entre duplicadas.
    Menor = mejor. Devuelve (nivel, -num_archivos) para que sorted() elija la canónica.

    Niveles:
      0 → bajo ~/Documents  (mejor)
      1 → hijo directo de ~/
      2 → cualquier otro lugar
      3 → bajo ~/Downloads  (peor)
    """
    home = Path.home()
    docs = home / "Documents"
    downloads = home / "Downloads"

    nivel = 2
    try:
        ruta.relative_to(docs)
        nivel = 0
    except ValueError:
        try:
            ruta.relative_to(downloads)
            nivel = 3
        except ValueError:
            if ruta.parent == home:
                nivel = 1

    try:
        num_archivos = sum(
            1 for f in ruta.iterdir()
            if f.is_file() and not f.is_symlink()
        )
    except PermissionError:
        num_archivos = 0

    # Negativo para tiebreak: más archivos = menor valor = mayor prioridad
    return (nivel, -num_archivos)


# ── Exclusión de carpetas ─────────────────────────────────────────────────────

def _carpeta_excluida(
    ruta: Path,
    carpetas_excluidas: set[str],
    rutas_absolutas: list[Path],
    patrones: list[str],
) -> bool:
    for ruta_abs in rutas_absolutas:
        try:
            ruta.relative_to(ruta_abs)
            return True
        except ValueError:
            pass

    for parte in ruta.parts:
        if parte in carpetas_excluidas:
            return True

    for patron in patrones:
        if fnmatch.fnmatch(ruta.name, patron):
            return True

    return False


# ── Recorrido recursivo ───────────────────────────────────────────────────────

def _recorrer(
    raiz: Path,
    carpetas_excluidas: set[str],
    rutas_absolutas: list[Path],
    patrones: list[str],
    max_depth: int,
    profundidad: int = 0,
) -> Iterator[Path]:
    if profundidad > max_depth:
        return

    try:
        hijos = sorted(raiz.iterdir())
    except PermissionError:
        return

    for entrada in hijos:
        if not entrada.is_dir() or entrada.is_symlink():
            continue
        if entrada.name.startswith("."):
            continue
        if _carpeta_excluida(entrada, carpetas_excluidas, rutas_absolutas, patrones):
            continue

        yield entrada
        yield from _recorrer(
            entrada, carpetas_excluidas, rutas_absolutas, patrones,
            max_depth, profundidad + 1,
        )


# ── Muestreo de contenido ────────────────────────────────────────────────────

def _tokens_por_archivo(carpeta: Path) -> list[set[str]]:
    """Tokens de cada archivo muestreado, por separado (no unidos)."""
    try:
        archivos = [
            f for f in carpeta.iterdir()
            if f.is_file() and not f.is_symlink()
        ]
    except PermissionError:
        return []

    por_archivo = []
    for archivo in archivos[:MAX_ARCHIVOS_MUESTRA]:
        tokens = tokenizar(extraer_texto(archivo))
        if tokens:
            por_archivo.append(tokens)
    return por_archivo


def _muestrear_contenido(tokens_por_archivo: list[set[str]]) -> set[str]:
    """Une los tokens de los archivos muestreados en un solo conjunto."""
    tokens: set[str] = set()
    for t in tokens_por_archivo:
        tokens |= t
    return tokens


def _homogeneidad(tokens_por_archivo: list[set[str]]) -> float | None:
    """
    Similitud promedio (Jaccard) entre los archivos muestreados de una carpeta.

    Una carpeta temática tiende a compartir vocabulario entre sus archivos;
    una contenedora (Documentos, Varios…) mezcla temas sin relación entre sí.
    Devuelve None si hay muy pocas muestras para que la métrica sea confiable.
    """
    if len(tokens_por_archivo) < MIN_ARCHIVOS_HOMOGENEIDAD:
        return None

    similitudes = []
    for a, b in combinations(tokens_por_archivo, 2):
        union = a | b
        if union:
            similitudes.append(len(a & b) / len(union))
    return sum(similitudes) / len(similitudes) if similitudes else 0.0


# ── Construcción del índice ───────────────────────────────────────────────────

def _mismo_nombre_que_padre(ruta: Path) -> bool:
    """
    Detecta carpetas redundantes de organización como:
      Ecuaciones Diferenciales/ → ECUACIONES DIFERENCIALES/
    donde el hijo es solo una versión en mayúsculas del padre.
    Estas carpetas no se indexan (el padre ya las representa), pero
    sus hijos sí se recorren normalmente.
    """
    return normalizar_nombre(ruta.name) == normalizar_nombre(ruta.parent.name)



# Patrón para nombres de carpetas organizativas/estructurales que
# repiten el mismo esquema en cada materia (unidad1, tarea2, examen…).
# Estas carpetas NO son duplicadas temáticas aunque compartan nombre.
_PATRON_ESTRUCTURAL = re.compile(
    r"^(unidad|tarea|practica|examen|parcial|actividad|capturas|"
    r"ejercicio|notas|apuntes|resumen|proyecto|laboratorio|final|"
    r"clase|lectura|clase)\d*$"
)


def cargar_carpetas_genericas(ruta: Path) -> set[str]:
    """Carga nombres de carpetas contenedoras (no temáticas), ya normalizados."""
    with open(ruta) as f:
        config = yaml.safe_load(f)
    nombres = (config or {}).get("nombres", [])
    return {normalizar_nombre(n) for n in nombres}


def _categoria_carpeta(
    nombre_norm: str,
    tokens_por_archivo: list[set[str]],
    nombres_genericos: set[str],
    profundidad: int,
) -> str:
    """
    Clasifica una carpeta como "tematica" o "contenedora" antes de decidir
    si entra al índice semántico (REV-001). Las contenedoras se siguen
    recorriendo (sus hijos pueden ser temáticos), pero no son candidatas
    a destino ni aportan tokens al índice.

    La prueba de homogeneidad de contenido solo se aplica hasta
    MAX_PROFUNDIDAD_HOMOGENEIDAD: carpetas más profundas suelen ser
    subcarpetas narrow donde el archivo encaja por COINCIDENCIA DE NOMBRE
    (ej. "ACTIVIDAD 5.3.xlsx" → carpeta "ACTIVIDAD 5.3"), no por tema del
    contenido — exigir homogeneidad ahí generaría falsos positivos
    (confirmado con datos reales: "ACTIVIDAD 5.3", "PAPC1.3", "2.2", "EU4"
    cayeron por homogeneidad pese a ser destinos correctos y validados).
    Lo mismo aplica a los nombres estructurales ("unidad1"…), sin importar
    la profundidad a la que aparezcan.
    """
    solo_alfanum = re.sub(r"[^a-z0-9]", "", nombre_norm)
    if _PATRON_ESTRUCTURAL.match(solo_alfanum):
        return "tematica"
    if nombre_norm in nombres_genericos:
        return "contenedora"
    if profundidad > MAX_PROFUNDIDAD_HOMOGENEIDAD:
        return "tematica"

    homogeneidad = _homogeneidad(tokens_por_archivo)
    if homogeneidad is not None and homogeneidad < UMBRAL_HOMOGENEIDAD:
        return "contenedora"

    return "tematica"


def _filtrar_duplicadas_reales(
    canonica: Path,
    candidatas: list[Path],
    nombre_norm: str,
    raiz: Path,
) -> list[Path]:
    """
    Filtra las carpetas candidatas a "duplicada" para reportar solo las que son
    duplicados temáticos reales. Se descartan:

    1. Nombres estructurales de curso ("unidad1", "examen", "capturas"…):
       aparecen por diseño en cada materia y no son duplicados reales.
    2. Nombres con < 5 letras sin dígitos: códigos cortos sin valor semántico.
    3. Relaciones padre-hijo: "Cálculo/CÁLCULO" no es un duplicado.
    4. Ambas a profundidad > 4 desde la raíz o desde ~/: subcarpetas organizativas
       profundas (ej. UNIDAD1/CAPTURAS vs UNIDAD5/CAPTURAS) son estructura, no tema.
    """
    solo_alfanum = re.sub(r"[^a-z0-9]", "", nombre_norm)
    solo_letras  = re.sub(r"[^a-z]",    "", nombre_norm)

    if len(solo_letras) < 5:
        return []
    if _PATRON_ESTRUCTURAL.match(solo_alfanum):
        return []

    home = Path.home()
    canon_depth = _profundidad_relativa(canonica, raiz, home)
    reales: list[Path] = []

    for cand in candidatas:
        # Excluir relaciones padre-hijo en cualquier dirección
        try:
            cand.relative_to(canonica)
            continue
        except ValueError:
            pass
        try:
            canonica.relative_to(cand)
            continue
        except ValueError:
            pass

        # Ambas muy profundas → subcarpetas organizativas repetidas por diseño
        cand_depth = _profundidad_relativa(cand, raiz, home)
        if min(canon_depth, cand_depth) > 4:
            continue

        reales.append(cand)

    return reales


def construir_indice(
    directorio: Path,
    exclusiones: dict | None = None,
    max_depth: int = MAX_DEPTH_DEFAULT,
    nombres_genericos: set[str] | None = None,
) -> dict[str, EntradaCarpeta]:
    """
    Recorre recursivamente `directorio` y construye un índice de carpetas temáticas.

    Antes de indexar, cada carpeta se categoriza como temática o contenedora
    (REV-001) — solo las temáticas entran al índice como destino. Las carpetas
    con nombre estructural ("unidad1", "actividad5.3"…) siempre son temáticas:
    ahí el archivo encaja por nombre, no por homogeneidad de contenido.

    Cuando dos carpetas tienen el mismo nombre normalizado, selecciona la canónica
    según prioridad de ubicación (Documents > ~/ > otras > Downloads) y registra
    las demás como `duplicadas` en la EntradaCarpeta ganadora.

    Clave del índice: nombre normalizado (sin acentos, minúsculas, sin espacios).
    El índice se reconstruye en cada ejecución para reflejar el estado actual.
    """
    directorio = directorio.expanduser().resolve()
    excl = exclusiones or {}

    carpetas_excluidas = set(excl.get("carpetas_exactas", []))
    rutas_absolutas = [
        Path(r).expanduser().resolve() for r in excl.get("rutas_absolutas", [])
    ]
    patrones = excl.get("patrones_nombre", [])

    todas: list[Path] = list(_recorrer(
        directorio, carpetas_excluidas, rutas_absolutas, patrones, max_depth
    ))

    # Excluir carpetas cuyo nombre normalizado es igual al de su padre:
    # son variantes organizativas (ej. "Cálculo/CÁLCULO"), el padre ya representa el tema.
    a_indexar = [c for c in todas if not _mismo_nombre_que_padre(c)]

    genericos = nombres_genericos or set()
    home = Path.home()

    # Categorizar antes de indexar: solo las temáticas son destino válido.
    # El muestreo de contenido se hace una sola vez por carpeta y se reutiliza
    # tanto para decidir la categoría (homogeneidad) como para tokens_contenido.
    tematicas: list[Path] = []
    tokens_cache: dict[Path, list[set[str]]] = {}
    for carpeta in a_indexar:
        nombre_norm = normalizar_nombre(carpeta.name)
        if not nombre_norm:
            continue
        tokens_archivo = _tokens_por_archivo(carpeta)
        profundidad = _profundidad_relativa(carpeta, directorio, home)
        if _categoria_carpeta(nombre_norm, tokens_archivo, genericos, profundidad) == "tematica":
            tematicas.append(carpeta)
            tokens_cache[carpeta] = tokens_archivo

    # Agrupar por nombre normalizado para detectar duplicadas
    por_nombre: dict[str, list[Path]] = {}
    for carpeta in tematicas:
        clave = normalizar_nombre(carpeta.name)
        por_nombre.setdefault(clave, []).append(carpeta)

    indice: dict[str, EntradaCarpeta] = {}
    for clave, rutas in por_nombre.items():
        ordenadas = sorted(rutas, key=_prioridad)
        canonica = ordenadas[0]
        duplicadas = _filtrar_duplicadas_reales(canonica, ordenadas[1:], clave, directorio)

        entrada = EntradaCarpeta(
            ruta=canonica,
            nombre=canonica.name,
            tokens_nombre=tokenizar(canonica.name),
            tokens_contenido=_muestrear_contenido(tokens_cache[canonica]),
            duplicadas=duplicadas,
        )
        indice[clave] = entrada

    return indice


# ── Puntuación ────────────────────────────────────────────────────────────────

def puntuar(
    tokens_contenido: set[str],
    tokens_stem: set[str],
    entrada: EntradaCarpeta,
) -> float:
    """
    Calcula qué tan bien coincide un archivo con una carpeta del índice.

    Se separan los tokens del nombre del archivo (stem) de los del cuerpo,
    porque un documento que MENCIONA un tema no debería clasificarse ahí
    si su propio nombre no tiene relación con esa carpeta.

    Fórmula:
      - Si el stem aporta al menos 1 token → señal de nombre completa (peso 0.7)
      - Si el stem no aporta nada          → penalización: score_nombre × 0.35
      - Contenido de muestra               → señal secundaria (peso 0.3)

    Devuelve un float en [0.0, 1.0].
    """
    if not tokens_contenido and not tokens_stem:
        return 0.0

    tokens_todos = tokens_contenido | tokens_stem

    # ── Señal primaria: tokens del nombre de carpeta en el archivo ─────────
    if entrada.tokens_nombre:
        hits_nombre = len(entrada.tokens_nombre & tokens_todos)
        score_nombre = hits_nombre / len(entrada.tokens_nombre)

        # Si el stem del archivo no aporta ningún hit, penalizar:
        # el contenido menciona el tema pero el archivo no "pertenece" a él.
        hits_stem = len(entrada.tokens_nombre & tokens_stem)
        if hits_stem == 0 and hits_nombre > 0:
            score_nombre *= 0.35   # penalización por match solo de contenido
    else:
        score_nombre = 0.0

    # ── Señal secundaria: tokens de contenido de muestra ──────────────────
    if entrada.tokens_contenido:
        hits_contenido = len(entrada.tokens_contenido & tokens_todos)
        score_contenido = hits_contenido / len(entrada.tokens_contenido)
    else:
        score_contenido = 0.0

    return score_nombre * 0.7 + score_contenido * 0.3


# ── Búsqueda de destino ───────────────────────────────────────────────────────

def buscar_destino(
    tokens_contenido: set[str],
    tokens_stem: set[str],
    indice: dict[str, EntradaCarpeta],
    umbral: float = UMBRAL_DEFAULT,
) -> ResultadoDescubrimiento:
    """
    Busca la carpeta más probable para un archivo dado sus tokens.

    Recibe por separado los tokens del cuerpo del archivo y los del nombre
    para aplicar la penalización por match solo de contenido.

    Devuelve la entrada con mayor score si supera el umbral,
    o un resultado vacío si ninguna carpeta coincide lo suficiente.
    """
    mejor_entrada: EntradaCarpeta | None = None
    mejor_score = 0.0

    for entrada in indice.values():
        score = puntuar(tokens_contenido, tokens_stem, entrada)
        if score > mejor_score:
            mejor_score = score
            mejor_entrada = entrada

    if mejor_entrada is None or mejor_score < umbral:
        return ResultadoDescubrimiento(None, mejor_score, "ninguno")

    # Determinar qué señal fue la dominante (para transparencia en la tabla)
    hits_stem = len(mejor_entrada.tokens_nombre & tokens_stem)
    metodo = "nombre" if hits_stem > 0 else "contenido"

    return ResultadoDescubrimiento(mejor_entrada, mejor_score, metodo)
