"""Extrae texto/metadatos de archivos para clasificación."""

import subprocess
import tarfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

MAX_CHARS = 500

# Extensiones de código fuente → solo necesitamos el nombre del archivo
# para clasificar; no extraemos contenido (demasiado heterogéneo).
_EXTENSIONES_CODIGO = {
    ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".hpp",
    ".go", ".rs", ".cs", ".rb", ".php", ".swift", ".kt", ".scala",
    ".sh", ".bash", ".zsh", ".fish", ".sql", ".html", ".css",
    ".r", ".m", ".lua", ".pl",
}

_EXTENSIONES_AUDIO = {".mp3", ".flac", ".ogg", ".wav", ".m4a", ".aac", ".opus", ".wma"}
_EXTENSIONES_VIDEO = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v"}
_EXTENSIONES_ZIP   = {".zip", ".jar", ".whl", ".apk"}
_EXTENSIONES_TAR   = {".tar", ".gz", ".bz2", ".xz", ".tgz", ".txz"}
_EXTENSIONES_RAR   = {".rar", ".7z"}


def extraer_texto(ruta: Path) -> str:
    ext = ruta.suffix.lower()
    try:
        if ext == ".pdf":
            return _pdf(ruta)
        if ext == ".docx":
            return _docx(ruta)
        if ext in (".xlsx", ".xls"):
            return _xlsx(ruta)
        if ext == ".pptx":
            return _pptx(ruta)
        if ext in (".txt", ".md", ".csv", ".log", ".rst"):
            return ruta.read_text(errors="ignore")[:MAX_CHARS]
        if ext == ".epub":
            return _epub(ruta)
        if ext in _EXTENSIONES_AUDIO:
            return _audio(ruta)
        if ext in _EXTENSIONES_VIDEO:
            return _video(ruta)
        if ext in _EXTENSIONES_ZIP:
            return _zip(ruta)
        if ext in _EXTENSIONES_TAR or (ext in {".gz", ".bz2", ".xz"} and ".tar" in ruta.name):
            return _tar(ruta)
        if ext in _EXTENSIONES_CODIGO:
            return _codigo(ruta)
    except Exception:
        pass
    return ""


# ── Documentos ────────────────────────────────────────────────────────────────

def _pdf(ruta: Path) -> str:
    resultado = subprocess.run(
        ["pdftotext", "-l", "2", str(ruta), "-"],
        capture_output=True, text=True, timeout=10,
    )
    return resultado.stdout[:MAX_CHARS]


def _docx(ruta: Path) -> str:
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(ruta) as z:
        with z.open("word/document.xml") as f:
            tree = ET.parse(f)
    textos = [n.text for n in tree.iter(f"{ns}t") if n.text]
    return " ".join(textos)[:MAX_CHARS]


def _xlsx(ruta: Path) -> str:
    with zipfile.ZipFile(ruta) as z:
        if "xl/sharedStrings.xml" not in z.namelist():
            return ""
        with z.open("xl/sharedStrings.xml") as f:
            tree = ET.parse(f)
    textos = [n.text for n in tree.iter() if n.text and n.text.strip()]
    return " ".join(textos)[:MAX_CHARS]


def _pptx(ruta: Path) -> str:
    textos = []
    with zipfile.ZipFile(ruta) as z:
        slides = sorted(n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
        for slide in slides[:3]:
            with z.open(slide) as f:
                tree = ET.parse(f)
            textos += [n.text for n in tree.iter() if n.text and n.text.strip()]
            if len(" ".join(textos)) >= MAX_CHARS:
                break
    return " ".join(textos)[:MAX_CHARS]


# ── Ebooks ────────────────────────────────────────────────────────────────────

def _epub(ruta: Path) -> str:
    with zipfile.ZipFile(ruta) as z:
        opf_names = [n for n in z.namelist() if n.endswith(".opf")]
        if not opf_names:
            return ""
        with z.open(opf_names[0]) as f:
            tree = ET.parse(f)
    # Namespaces de Dublin Core usados en content.opf
    campos = []
    for elem in tree.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag in ("title", "creator", "subject", "description") and elem.text:
            campos.append(elem.text.strip())
    return " ".join(campos)[:MAX_CHARS]


# ── Audio ─────────────────────────────────────────────────────────────────────

def _audio(ruta: Path) -> str:
    try:
        from mutagen import File as MutagenFile
        tags = MutagenFile(ruta, easy=True)
        if tags is None:
            return ""
        campos = []
        for clave in ("title", "album", "artist", "genre", "comment"):
            val = tags.get(clave)
            if val:
                campos.append(str(val[0]) if isinstance(val, list) else str(val))
        return " ".join(campos)[:MAX_CHARS]
    except ImportError:
        return _ffprobe(ruta)


# ── Video ─────────────────────────────────────────────────────────────────────

def _video(ruta: Path) -> str:
    return _ffprobe(ruta)


def _ffprobe(ruta: Path) -> str:
    resultado = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(ruta),
        ],
        capture_output=True, text=True, timeout=15,
    )
    if resultado.returncode != 0:
        return ""
    import json
    data = json.loads(resultado.stdout)
    tags = data.get("format", {}).get("tags", {})
    campos = []
    for clave in ("title", "album", "artist", "comment", "description", "genre"):
        val = tags.get(clave) or tags.get(clave.upper())
        if val:
            campos.append(val)
    return " ".join(campos)[:MAX_CHARS]


# ── Archivos comprimidos ──────────────────────────────────────────────────────

def _zip(ruta: Path) -> str:
    with zipfile.ZipFile(ruta) as z:
        nombres = [n for n in z.namelist() if not n.endswith("/")]
    return " ".join(nombres)[:MAX_CHARS]


def _tar(ruta: Path) -> str:
    modo = "r:*"
    with tarfile.open(ruta, modo) as t:
        nombres = [m.name for m in t.getmembers() if m.isfile()]
    return " ".join(nombres)[:MAX_CHARS]


# ── Código fuente ─────────────────────────────────────────────────────────────

def _codigo(ruta: Path) -> str:
    # El nombre ya contiene la señal principal; el contenido es demasiado
    # heterogéneo para ser útil como señal temática.
    try:
        primera_linea = ruta.read_text(errors="ignore").splitlines()[0]
        return primera_linea[:MAX_CHARS]
    except (IndexError, OSError):
        return ""
