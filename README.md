# clasi

An automatic file classifier that learns from the folder structure you already have.

Instead of writing rules such as:

- PDFs → Documents
- Invoices → Finance
- Notes → School

`clasi` discovers the folders that already exist on your computer, learns what kind of content belongs in each one, and routes new files accordingly.

```text
Most tools: you write rules → the tool follows them
clasi:      you organize folders → the tool learns from them
```

---

## Why this exists

This project started after manually organizing roughly 200 accumulated files in a Downloads folder.

The process revealed something interesting:

Most placement decisions followed patterns that could be inferred automatically from the folders that already existed.

`clasi` is an attempt to automate those decisions without forcing the user to maintain a large set of destination rules.

---

## Example

Suppose your computer already contains:

```text
Documents/
├── Numerical Methods/
├── Differential Equations/
├── Programming/
└── Astronomy/
```

A new file appears:

```text
Downloads/
└── Newton-Raphson.pdf
```

Running:

```bash
clasi sim ~/Downloads
```

might produce:

```text
FILE                 DESTINATION
----------------------------------------------
Newton-Raphson.pdf   Numerical Methods
```

No destination rule was written.

The folder already existed, so `clasi` learned from it.

---

## Current status

**Phase 3 complete — Phase 4 planned**

### Implemented

- Dynamic folder discovery
- Recursive indexing
- TF-IDF classification
- Dry-run mode (`sim`)
- Real execution (`run`)
- Undo support
- Folder duplicate detection and warnings
- Holdout evaluation (`evaluate`)
- Folder merging (`merge`)
- Folder relocation (`move-folder`)
- Markdown catalog generation (`catalog`)
- Redundant original detection (`X.pdf` when `X_merged.pdf` already exists)
- Corrupt/unextractable PDF isolation (`PDF_Texto_Corrupto`)
- New folder suggestions when ≥7 loose files share a theme
- OCR fallback for scanned PDFs (Tesseract, `pdftoppm`, first 2 pages)
- OCR for images — falls back to EXIF metadata when no readable text found
- Interactive review (`review`) — per-file panel with extracted text and suggestion; folder search by partial name
- `python` filter in `hints.yaml` — inline Python expressions for custom routing logic

**Supported file types:**

| Category | Formats | Extraction |
|---|---|---|
| Documents | PDF, DOCX, XLSX, PPTX, ODT, ODS | pdftotext / internal XML |
| Plain text | TXT, MD, CSV, LOG, RTF | direct read |
| Scanned PDF | any PDF with no text layer | Tesseract OCR (spa+eng) |
| Images | JPG, PNG, WEBP, TIFF, BMP, SVG | Tesseract OCR → EXIF fallback |
| Audio | MP3, FLAC, OGG, WAV, M4A, AAC | ID3/Vorbis/MP4 tags (mutagen) |
| Video | MP4, MKV, AVI, MOV, WEBM | ffprobe metadata |
| Source code | .py .js .java .c .go .rs .html .sql … | first line + language detection |
| Archives | ZIP, TAR, GZ, XZ, RAR, 7Z | internal content listing |
| Ebooks | EPUB | content.opf (title, author, subject) |

### Planned (Phase 4)

- `pip install clasi` — clean install on any machine
- `clasi init` — scans the system, generates `exclusions.yaml` adapted to the detected environment
- Folder type detection (code projects, system config) to avoid disrupting them
- Regression tests
- User documentation

See [`PROJECT.md`](PROJECT.md) for the complete roadmap and architecture.

---

## Safety

`clasi` is designed to be conservative.

- `sim`, `evaluate`, and `catalog` never modify the filesystem.
- Files are moved, never deleted.
- Every operation is logged as JSON Lines.
- `undo` can revert any run, merge, or move-folder.
- System folders are excluded by default.

If you're just curious, use:

```bash
clasi sim ~/Documents
```

Nothing will be modified.

---

## Installation

Requirements:

- Python 3.10+
- `pdftotext` (from Poppler) — PDF text extraction
- `pdftoppm` (from Poppler) — converts scanned PDF pages to images for OCR
- `tesseract` + language data — OCR for scanned PDFs and images
- `ffprobe` (from FFmpeg) — video metadata and audio fallback
- `mutagen` — audio tag reading (optional; falls back to `ffprobe` if not installed)
- `Pillow` — image reading for OCR and EXIF extraction
- `pytesseract` — Python wrapper for Tesseract

### Arch Linux

```bash
sudo pacman -S python-click python-yaml python-rich python-mutagen \
               python-pillow python-pytesseract \
               poppler ffmpeg tesseract tesseract-data-spa tesseract-data-eng
```

### Debian / Ubuntu

```bash
sudo apt install python3-click python3-yaml python3-rich python3-mutagen \
                 python3-pil python3-pytesseract \
                 poppler-utils ffmpeg \
                 tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng
```

### Python dependencies

```bash
pip install -r requirements.txt
```

### Clone

```bash
git clone https://github.com/AllergicCypress/clasi.git
cd clasi
```

---

## Usage

### Dry run

```bash
clasi sim <directory>
```

Shows what would happen without modifying anything. Also warns about duplicate folders and suggests new ones when applicable.

---

### Execute

```bash
clasi run <directory>
```

Moves files and creates a reversible log.

---

### Undo

```bash
clasi undo
```

Reverts the most recent `run`, `merge`, or `move-folder` log.

---

### Evaluate

```bash
clasi evaluate <directory>
```

Measures accuracy using the user's existing organization as ground truth. Holds out 1–3 files per thematic folder and checks whether `clasi` would route them back correctly.

Reports are anonymized automatically (short hashes, no real names). Add `--verbose` to see real paths locally.

```bash
clasi evaluate ~/Documents --seed 1
```

---

### Merge duplicate folders

```bash
clasi merge <redundant> <canonical>
```

Moves the contents of a redundant folder into its canonical location, preserving subdirectories. Reversible with `undo`. `sim` suggests the exact command when it detects duplicates.

---

### Relocate a misplaced folder

```bash
clasi move-folder <folder> <new-parent>
```

Moves an entire folder to a better location. Reversible with `undo`.

---

### Interactive review

```bash
clasi review <directory>
```

Shows a panel for each unclassifiable file with its extracted text (including OCR output) and the classifier's suggestion. You can confirm the suggestion, search for another folder by partial name, or skip.

```
╭──────── review 1/14 · sin destino ────────────────────────╮
│ Investigacion de Operaciones.pdf                          │
│                                                           │
│ la investigacion de operaciones lineales...               │
│                                                           │
│ Sugerencia: sin destino  (score máx: 0.09)               │
╰───────────────────────────────────────────────────────────╯
  [c] elegir carpeta  [n] saltar  [q] salir
```

Keys: `[s]` confirm, `[c]` search folder by name, `[n]` skip, `[q]` quit.

All moves are logged and reversible with `undo`.

Add `--con-inciertos` to also review medium-confidence files (score < 0.5) before they are moved automatically.

---

### Generate a catalog

```bash
clasi catalog <directory>
```

Writes a markdown file to `logs/catalogo_<timestamp>.md` listing every file and its suggested destination.

---

### Custom logic with the `python` filter

`hints.yaml` supports a `python` filter that evaluates an arbitrary Python expression per file. This handles cases that don't fit the built-in filters.

Available variables: `archivo` (Path), `texto` (str, including OCR output), `nombre`, `stem`, `sufijo`, `re` (module), `Path` (class).

```yaml
hints:
  - nombre: facturas_noviembre
    filter_mode: all
    filtros:
      - python: "sufijo == '.pdf' and re.search(r'factura|invoice', texto, re.I) is not None"
      - python: "re.search(r'noviembre|november', texto, re.I) is not None"
    accion_especial: carpeta_especial
    nombre_carpeta: Facturas/2024-11
    conflicto: rename_new
```

If the expression raises an error, `clasi` prints a one-time warning to stderr and treats the filter as non-matching (the file is not routed by that hint).

---

## Help wanted

The biggest unknown is not the code.

It's whether the discovery engine works on folder structures different from my own.

Most development and calibration has been performed against a single real home directory.

If your organization style is different, your tests are extremely valuable.

Especially if you organize by:

- Projects
- Clients
- Years
- Subjects
- Research topics

Or if you barely organize at all.

Try:

```bash
clasi evaluate ~/Documents
```

and open an issue with the results.

The report is anonymized automatically and can be shared safely.

---

## Project goals

### Immediate goal

Automatically organize accumulated files in `~/Downloads`.

### Next goal

Extend the system to all of `~/` with appropriate safety controls.

### Final goal

Create a universal file organizer that:

- Learns from the folders users already have.
- Requires little or no configuration.
- Adapts automatically when new topics appear.
- Works on different machines without rewriting rules.

---

## Documentation

### Project design

- [`PROJECT.md`](PROJECT.md)

Architecture, requirements, roadmap, design decisions, lessons learned, and implementation details.

### Architecture reviews

- [`REVIEWS_1.1.md`](REVIEWS_1.1.md)
- [`REVIEWS_1.2.md`](REVIEWS_1.2.md)

Known weaknesses, architectural risks, and investigated solutions — including ones tried and rejected with full reasoning.

---

## License

GPLv3

See [`LICENSE`](LICENSE).
