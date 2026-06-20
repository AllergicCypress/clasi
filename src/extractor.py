"""Extrae texto de los primeros fragmentos de PDF, DOCX y XLSX."""

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_CHARS = 500


def extraer_texto(ruta: Path) -> str:
    ext = ruta.suffix.lower()
    try:
        if ext == ".pdf":
            return _pdf(ruta)
        if ext == ".docx":
            return _docx(ruta)
        if ext in (".xlsx", ".xls"):
            return _xlsx(ruta)
        if ext in (".txt", ".md", ".csv"):
            return ruta.read_text(errors="ignore")[:MAX_CHARS]
    except Exception:
        pass
    return ""


def _pdf(ruta: Path) -> str:
    import subprocess
    resultado = subprocess.run(
        ["pdftotext", "-l", "2", str(ruta), "-"],
        capture_output=True, text=True, timeout=10
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
