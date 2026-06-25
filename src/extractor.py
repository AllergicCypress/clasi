"""Extrae texto/metadatos de archivos para clasificación."""

import subprocess
import tarfile
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

MAX_CHARS = 500
OCR_LANG  = "spa+eng"
# Fracción mínima de caracteres alfabéticos para considerar que el OCR
# produjo texto útil (filtra resultados de páginas en blanco o con solo ruido).
_MIN_RATIO_ALFA_OCR = 0.30

_EXTENSIONES_CODIGO = {
    ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".hpp",
    ".go", ".rs", ".cs", ".rb", ".php", ".swift", ".kt", ".scala",
    ".sh", ".bash", ".zsh", ".fish", ".sql", ".html", ".css",
    ".r", ".m", ".lua", ".pl",
}
_EXTENSIONES_AUDIO  = {".mp3", ".flac", ".ogg", ".wav", ".m4a", ".aac", ".opus", ".wma"}
_EXTENSIONES_VIDEO  = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v"}
_EXTENSIONES_ZIP    = {".zip", ".jar", ".whl", ".apk"}
_EXTENSIONES_TAR    = {".tar", ".gz", ".bz2", ".xz", ".tgz", ".txz"}
_EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}


_UMBRAL_TEXTO_CORRUPTO = 0.05


def texto_corrupto(texto: str) -> bool:
    """
    True si más del 5% de los caracteres son caracteres de control
    (excluyendo \\n \\r \\t). Señal confiable de PDFs sin capa de texto real.
    Las letras acentuadas latinas son alfabéticas para Python y no se cuentan.
    """
    if not texto:
        return False
    malos = sum(
        1 for c in texto
        if (ord(c) < 32 and c not in "\n\r\t") or 127 <= ord(c) <= 159
    )
    return malos / len(texto) > _UMBRAL_TEXTO_CORRUPTO


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
        if ext in _EXTENSIONES_IMAGEN:
            return _imagen(ruta)
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


# ── Helpers OCR ───────────────────────────────────────────────────────────────

def _ocr_util(texto: str) -> bool:
    """True si el texto tiene suficientes letras para ser clasificable."""
    if not texto or len(texto) < 20:
        return False
    letras = sum(1 for c in texto if c.isalpha())
    return letras / len(texto) >= _MIN_RATIO_ALFA_OCR


def _tesseract_imagen(ruta_imagen: Path) -> str:
    """Corre tesseract sobre una imagen y devuelve el texto reconocido."""
    try:
        import pytesseract
        from PIL import Image
        texto = pytesseract.image_to_string(Image.open(ruta_imagen), lang=OCR_LANG)
        return texto.strip()
    except Exception:
        return ""


# ── Documentos ────────────────────────────────────────────────────────────────

def _pdf(ruta: Path) -> str:
    resultado = subprocess.run(
        ["pdftotext", "-l", "2", str(ruta), "-"],
        capture_output=True, text=True, timeout=10,
    )
    texto = resultado.stdout[:MAX_CHARS]

    # Fallback OCR: si pdftotext devolvió texto corrupto o vacío, intentar
    # convertir las primeras páginas a imagen y pasarlas por Tesseract.
    if not texto or texto_corrupto(texto):
        texto_ocr = _pdf_ocr(ruta)
        if _ocr_util(texto_ocr):
            return texto_ocr[:MAX_CHARS]

    return texto


def _pdf_ocr(ruta: Path) -> str:
    """
    Convierte las primeras 2 páginas del PDF a imagen con pdftoppm
    y aplica Tesseract. No requiere pdf2image — usa pdftoppm (poppler).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        prefijo = Path(tmpdir) / "pagina"
        ret = subprocess.run(
            ["pdftoppm", "-l", "2", "-r", "200", str(ruta), str(prefijo)],
            capture_output=True, timeout=30,
        )
        if ret.returncode != 0:
            return ""

        imagenes = sorted(Path(tmpdir).glob("pagina-*.ppm"))
        fragmentos = []
        for img in imagenes:
            t = _tesseract_imagen(img)
            if t:
                fragmentos.append(t)

    return " ".join(fragmentos)


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
    campos = []
    for elem in tree.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag in ("title", "creator", "subject", "description") and elem.text:
            campos.append(elem.text.strip())
    return " ".join(campos)[:MAX_CHARS]


# ── Imágenes ──────────────────────────────────────────────────────────────────

def _imagen(ruta: Path) -> str:
    """OCR sobre la imagen + EXIF como fallback si el OCR no produce texto útil."""
    texto_ocr = _tesseract_imagen(ruta)
    if _ocr_util(texto_ocr):
        return texto_ocr[:MAX_CHARS]
    return _exif(ruta)


def _exif(ruta: Path) -> str:
    """Extrae metadatos EXIF relevantes para clasificación (sin coordenadas GPS)."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        img = Image.open(ruta)
        exif_raw = img._getexif()
        if not exif_raw:
            return ""
        campos = []
        for tag_id, valor in exif_raw.items():
            nombre = TAGS.get(tag_id, "")
            if nombre in ("ImageDescription", "XPComment", "XPTitle",
                          "Artist", "Copyright", "Software"):
                if isinstance(valor, (str, bytes)):
                    texto = valor.decode("utf-16-le", errors="ignore").rstrip("\x00") \
                            if isinstance(valor, bytes) else valor
                    if texto.strip():
                        campos.append(texto.strip())
        return " ".join(campos)[:MAX_CHARS]
    except Exception:
        return ""


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
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(ruta)],
        capture_output=True, text=True, timeout=15,
    )
    if resultado.returncode != 0:
        return ""
    import json
    data  = json.loads(resultado.stdout)
    tags  = data.get("format", {}).get("tags", {})
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
    with tarfile.open(ruta, "r:*") as t:
        nombres = [m.name for m in t.getmembers() if m.isfile()]
    return " ".join(nombres)[:MAX_CHARS]


# ── Código fuente ─────────────────────────────────────────────────────────────

def _codigo(ruta: Path) -> str:
    try:
        primera_linea = ruta.read_text(errors="ignore").splitlines()[0]
        return primera_linea[:MAX_CHARS]
    except (IndexError, OSError):
        return ""
