# Automatic File Classifier

## Context and Motivation

This project started from the practical experience of organizing a `~/Downloads` folder with ~200 accumulated files. The manual process took hours and revealed repeatable patterns that justify automation.

**Core problem:** files pile up without structure because classifying them in the moment requires interrupting your workflow. Organizing them later is expensive because you have to remember or rediscover the context of each file.

**Immediate goal:** automate the organization of `~/Downloads`.
**Next goal:** extend the tool to all of `~/`, with all the safety controls that requires.
**Final goal:** a universal tool that works on any machine, learns from the folder structure the user already has, and automatically adapts to new topics as they appear — without deep manual configuration.

---

## Core design principle

> **The existing folder structure IS the configuration.**

The user doesn't write rules for every topic. The user organizes folders (as they naturally do anyway). The tool reads those folders, learns what kind of content lives in each one, and routes new files to where they belong.

Manual rules (`hints.yaml`) only exist for cases that automatic discovery cannot infer on its own: name-based duplicates, installers by extension, special exceptions.

```
Before: user writes rules → tool follows them
Now:    user organizes folders → tool learns from them
```

---

## Lessons learned

### Test session — 2026-06-16 (~200 real files)

1. **Text extraction classifies ~75% of files automatically.** `pdftotext` and reading the internal XML of DOCX/XLSX are enough to identify most academic documents.

2. **The remaining 25% are scanned PDFs or files without a descriptive name.** They require OCR or manual review. This percentage doesn't disappear — it's managed, not eliminated.

3. **User context is irreplaceable.** A file named `1.pdf` is only classifiable if you know the user is taking a Differential Equations course. Rules must be derived from context, not hardcoded.

4. **Duplicates are frequent and predictable.** Files with `(1)`, `(2)` in the name are almost always download duplicates.

5. **Running on `~/` is qualitatively different from `~/Downloads`.** Without strict exclusions, the tool can break the system.

6. **A readable catalog is more useful than a technical log.** The table format (file | detected content | suggested destination) was immediately useful.

7. **`_merged` files are not the duplicates — their original is.** An `X_merged.pdf` file contains `X.pdf`. The tool must detect the pair and flag the original as redundant.

8. **Thematic folders are created when there's enough density.** If >7 files of the same topic are detected with no existing folder → create the folder. If ≤7 → report without moving.

### Architecture review — 2026-06-17

9. **Hardcoded rules presuppose the user's structure and create redundancy.** If `rules.yaml` says "Numerical Methods → ~/Downloads/Numerical Methods/" but the user already has `~/Numerical Methods/`, two folders for the same topic get created. The fix is for rules to describe *content*, not *destinations*.

10. **Dynamic folder discovery makes the tool truly universal.** If the user creates a new folder ("Thermodynamics"), the next run already knows about it and can route files there without touching any configuration file.

11. **A document that MENTIONS a topic doesn't belong to it.** The scorer must distinguish between a file whose name is related to a folder (strong signal) and one whose body merely mentions the topic (weak signal). Solution: penalize when the file's stem contributes no tokens matching the folder name.

12. **The index must be global and recursive, not local to the directory.** When running on `~/`, the tool must discover every thematic folder across the whole directory tree (within exclusion limits), not just the immediate ones. Otherwise, `~/Downloads/Differential Equations/` is invisible when scanning `~/`.

13. **Folders in the wrong place are just as real a problem as files in the wrong place.** A `Calculus` folder inside `~/Downloads/` when it should be in `~/Documents/` causes silent fragmentation. The correct flow: the file goes to the correct thematic folder (wherever it is), and the tool suggests relocating the folder if it detects it's not in the optimal place.

14. **Two folders with the same normalized name are one folder.** If both `~/Downloads/Calculus/` and `~/Documents/Calculus/` exist, they're the same topic with accidental fragmentation. The tool must detect them, choose the canonical location, and propose unifying them — moving the contents of the "worse" one into the "better" one.

### Architecture review — 2026-06-20 (REV-001, see `REVIEWS_1.2.md`)

15. **Not every existing folder is a topic — some are administrative containers.** The principle "the existing structure is the configuration" assumed that any indexable folder represents a topic. Folders like `University`, `Work`, `Documents`, `Important` group things by context (who, where, when), not by content, and if indexed they degrade discovery with every run (they attract unrelated files → their vocabulary becomes more heterogeneous → they attract even more files). Fix: a categorization stage before indexing (`_categoria_carpeta` in `discovery.py`) that discards container folders via a blocklist (`config/carpetas_genericas.yaml`) and content homogeneity between sampled files (average Jaccard, `UMBRAL_HOMOGENEIDAD = 0.15`).

16. **Content homogeneity must NOT be required on narrow (deep) subfolders.** The first version of the heuristic applied the homogeneity test to every folder, regardless of depth. Result: `ACTIVIDAD 5.3`, `PAPC1.3`, `2.2`, `EU4` — correct destinations already validated in real tests — fell below the threshold and got excluded from the index. The cause: in those folders, the file matches by **exact name** (`ACTIVIDAD 5.3.xlsx` → folder `ACTIVIDAD 5.3`), not by content topic, so their files can be heterogeneous among themselves without that invalidating the folder as a destination. Fix: the homogeneity test only applies up to `MAX_PROFUNDIDAD_HOMOGENEIDAD = 2` levels from the scanned root; deeper than that, the folder is assumed thematic by design (same as folders with a structural name, which are exempt regardless of depth). Verified with `clasi sim ~/Documents`: the exact same 7 files with a destination / 12 without, and the same scores (0.70–0.79), as the real test documented in previous sessions — zero regression.

---

## Prior art — similar tools

### `organize` (tfeldmann) — the closest reference

- **Repository:** https://github.com/tfeldmann/organize · **PyPI:** `pip install organize-tool`
- **What it is:** Python CLI, open source, YAML rules, with `sim` (dry-run) and `run` (execute).
- **What it does well:** filters by name, extension, date, PDF/DOCX text; hash-based duplicate detection; `filter_mode: any/all`; configurable depth (`min_depth`, `max_depth`); regex with named groups that become variables; no forced catch-all (unmatched files are left in place).
- **What it does NOT do:** dynamic folder discovery, OCR for scanned PDFs, density-based folders, `_merged` pair detection, universality across machines.
- **Why not use it as a base:** its destination paths are hardcoded per rule — exactly the problem we want to avoid.

### What we adopted from its design

| Decision | Origin | Application in `clasi` |
|---|---|---|
| `filter_mode: any/all` | `organize` | OR/AND between filters of the same rule |
| `min_depth` / `max_depth` | `organize` | Depth control in the scanner |
| Regex with groups → variables | `organize` | Metadata extraction from content |
| No forced catch-all | `organize` | Unmatched files → report, don't move |
| `on_conflict` per action | `organize` | `skip`, `rename_new`, `rename_existing` |

---

## Requirements

### Functional

| ID | Requirement | Priority |
|----|-----------|----------|
| F1 | Extract text and metadata from all common file types | High |
| F2 | Automatically discover existing folders and learn from their content | High |
| F3 | `clasi sim <directory>`: show what it would move without moving anything | High |
| F4 | `clasi run <directory>`: move files according to the discovery engine | High |
| F5 | Log every operation so it can be reverted | High |
| F6 | `clasi undo`: revert the last run | High |
| F7 | Generate a catalog of unclassified files | Medium |
| F8 | OCR as a fallback for PDFs with no extractable text | Medium |
| F9 | Interactive terminal review for ambiguous files | Medium |
| F10 | Detect name-based duplicates (`(1)`, `(2)`) and redundant `_merged` pairs | Medium |
| F11 | Automatically create a thematic folder when >7 files have no destination folder | Medium |
| F12 | Configurable exclusions (folders, patterns, absolute paths) | High |
| F13 | Configurable conflict resolution per type: `skip`, `rename_new`, `rename_existing` | High |
| F14 | Support for `filter_mode: any/all` per hint rule | Medium |
| F15 | Configurable scan depth (`max_depth`) | Medium |
| F16 | Global recursive discovery: index of every thematic folder on the system | High |
| F17 | Duplicate folder detection (same normalized name at different paths) | High |
| F18 | Canonical folder selection by parent location priority | High |
| F19 | `clasi merge`: unify duplicate folders into the canonical one with a reversible log | High |
| F20 | `clasi move-folder`: relocate a folder to a more appropriate place | Medium |
| F21 | Suggestions in `sim`: warn about duplicate folders and folders in a suboptimal location | High |

### Non-functional

| ID | Requirement |
|----|-------------|
| NF1 | **Safety:** never touch `.git/`, `.config/`, `.ssh/` and similar by default |
| NF2 | **Idempotency:** running it twice produces the same result |
| NF3 | **Transparency:** always show what it does and why |
| NF4 | **Non-destructiveness:** move, never delete |
| NF5 | **Portability:** works on Linux with no prior user configuration |
| NF6 | **Universality:** adapts to any machine's folder structure without rewriting rules |
| NF7 | **Self-updating knowledge:** a new folder created by the user → available on the next run without touching any configuration file |

---

## Architecture

### Global discovery and folder conflict resolution

#### Recursive discovery

The index is built by walking **the entire directory tree** within the allowed scope (respecting exclusions), not just the immediate level of the target directory. This means that when running on `~/`, the tool knows about `~/Downloads/Differential Equations/`, `~/Documents/Numerical Methods/`, etc.

#### Folder name normalization

To detect duplicates, every name is normalized with `normalizar_nombre()`:
```
"Numerical Methods"  →  "numericalmethods"
"Numerical_Methods"  →  "numericalmethods"
"NUMERICAL METHODS"  →  "numericalmethods"
```
Process: strip accents → lowercase → remove spaces, `_` and `-`.
This key is used as the dictionary index in `construir_indice()`.

#### Duplicate filtering: criteria for a "real" duplicate

Not every normalized-name match is a thematic duplicate. The following are discarded:

1. **Parent-child relationships**: `Differential Equations/` and its child `DIFFERENTIAL EQUATIONS/` are the same folder with different casing, not duplicates.
2. **Structural course names**: `UNIT 1`, `EXAM`, `SCREENSHOTS`, `ACTIVITY 2.4` appear by design in every course — they are not real duplicates. Detected via `_PATRON_ESTRUCTURAL` + names with < 5 letters.
3. **Deep subfolders** (> 4 levels): `UNIT1/SCREENSHOTS` vs `UNIT5/SCREENSHOTS` are the same structure repeated by design.

#### Canonical folder — location priority

When two or more folders with the same normalized name are detected, one is chosen as **canonical** using this priority order:

| Priority | Parent location | Reason |
|---|---|---|
| 1 | `~/Documents/` | Semantic home for documents |
| 2 | `~/` (home root) | Accessible, visible |
| 3 | Any other user folder | Neutral |
| 4 | `~/Downloads/` | Transient by nature |

In case of a tie, the folder with **more files** wins (it's the established one).

#### Behavior with duplicate folders

```
Situation: "Calculus" exists in ~/Downloads/ AND in ~/Documents/

clasi sim:
  → Picks ~/Documents/Calculus/ as canonical (priority 1 > 4)
  → New files go to ~/Documents/Calculus/
  → Shows a warning:
    ⚠ DUPLICATE FOLDER: "Calculus"
      Canonical:  ~/Documents/Calculus/        (3 files)
      Redundant:  ~/Downloads/Calculus/         (1 file)
      Suggestion: unify with `clasi merge`

clasi run:
  → Moves the files to the canonical folder
  → Asks the user whether to unify the folders now

clasi merge:
  → Moves the contents of the redundant folder into the canonical one
  → Logs it (reversible with undo)
  → Reports whether the redundant folder ended up empty (the user decides whether to delete it)
```

#### Behavior with a folder in a suboptimal location (no duplicate)

```
Situation: "Calculus" only exists in ~/Downloads/

clasi sim:
  → Files go to ~/Downloads/Calculus/ (that's what's there)
  → Shows a suggestion:
    💡 SUGGESTION: The "Calculus" folder is in ~/Downloads/ (transient).
       It might live better in ~/Documents/. Use `clasi move-folder` to relocate it.

clasi move-folder "Calculus":
  → Moves ~/Downloads/Calculus/ → ~/Documents/Calculus/
  → Logs it (reversible)
```

### Three layers

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1 — DISCOVERY ENGINE                                 │
│                                                             │
│  - Walks existing folders in the target directory           │
│  - Extracts semantics from: folder name + sample of         │
│    content from files already living there                  │
│  - Builds a dynamic index:                                   │
│    { "Numerical Methods": { path, keywords, score_model } } │
│  - Rebuilt on every run → always up to date                 │
└─────────────────────┬───────────────────────────────────────┘
                      │ index of known folders
┌─────────────────────▼───────────────────────────────────────┐
│  LAYER 2 — CLASSIFICATION ENGINE                            │
│                                                             │
│  For each file to process:                                  │
│  1. Extract text / metadata (depending on file type)        │
│  2. Score against every index entry (simple TF-IDF)         │
│  3. If score > threshold → destination candidate            │
│  4. Apply hints.yaml for special cases                      │
│     (duplicates, installers, specific extensions)           │
│  5. No candidate + >7 of the same topic → propose a folder  │
│  6. No candidate + ≤7 → report, don't move                  │
└─────────────────────┬───────────────────────────────────────┘
                      │ list of decisions
┌─────────────────────▼───────────────────────────────────────┐
│  LAYER 3 — EXECUTION ENGINE                                 │
│                                                             │
│  - `clasi sim`: shows a decision table without acting       │
│  - `clasi run`: executes the moves, writes a JSON Lines log │
│  - `clasi undo`: reverts from the most recent log            │
│  - Per-rule conflict resolution                              │
└─────────────────────────────────────────────────────────────┘
```

### Detailed flow

```
[Target directory]
        │
        ▼
[0. DISCOVERY — new]
  - Iterates over subfolders (not files)
  - For each folder: extracts name + keywords from a content sample
  - Builds index: folder → keyword vector
  - Detects pairs (X.pdf, X_merged.pdf) among loose files
        │ index
        ▼
[1. SCAN]
  - Lists loose files in the directory (respecting exclusions)
  - Configurable max_depth (default: 1 for ~/, null for ~/Downloads)
  - Skips symlinks
        │ file list
        ▼
[2. EXTRACTION]
  - PDF with text   → pdftotext / PyMuPDF
  - Scanned PDF     → Tesseract OCR [Phase 3]
  - DOCX            → word/document.xml
  - XLSX            → xl/sharedStrings.xml
  - PPTX            → ppt/slides/*.xml
  - TXT/MD/CSV      → direct read
  - Images          → EXIF + OCR [Phase 3]
  - Audio           → ID3/Vorbis tags (title, album, artist)
  - Video           → ffprobe metadata (title, description)
  - Source code     → first line + language detection
  - ZIP files       → internal content listing
  - EPUB            → content.opf (title, author, subject)
  - Unknown         → magic bytes + file name
        │ text / metadata
        ▼
[3. CLASSIFICATION]
  - Simple TF-IDF score: file text vs each folder's keywords
  - Applies hints.yaml (special cases: duplicates, extensions)
  - Returns: { file, destination, confidence, method }
        │ decisions
        ▼
[4. PRESENTATION — clasi sim]
  - Table: file | destination | confidence | classification method
  - Marks no-candidate as [NO DESTINATION] — not [REVIEW]
  - Shows proposals for new folders (topic + count)
        │ user confirmation
        ▼
[5. EXECUTION — clasi run]
  - Moves files
  - Creates new folders if needed
  - Writes a JSON Lines log
        │
        ▼
[6. UNDO]
  - Reads the most recent log
  - Reverses each operation
```

### Project file structure

```
clasificador-archivos/
├── README.md
├── PROJECT.md           ← this document (English)
├── REVIEWS_1.1.md       ← architecture review log (English)
├── REVIEWS_1.2.md
├── PROYECTO.md          ← original Spanish checkpoint, kept as-is
├── Revisiones_1.1.md    ← original Spanish checkpoint, kept as-is
├── Revisiones_1.2.md
├── src/
│   ├── discovery.py     ← dynamic folder index; TF-IDF scoring with penalties
│   ├── scanner.py       ← walks the directory, applies exclusions, skips symlinks
│   ├── extractor.py     ← extracts text/metadata depending on file type
│   ├── classifier.py    ← hints first, then TF-IDF discovery
│   ├── executor.py      ← moves files, JSON Lines log, undo
│   └── cli.py           ← clasi sim | run | undo  [merge | move-folder in Phase 2]
├── config/
│   ├── hints.yaml              ← special cases with no thematic semantics (v3)
│   ├── exclusions.yaml         ← folders and patterns to ignore
│   └── carpetas_genericas.yaml ← container (non-thematic) folder names (REV-001)
├── logs/
│   └── .gitkeep
├── tests/
└── requirements.txt
```

---

## File type support

| Category | Formats | Extraction method | Phase |
|---|---|---|---|
| Text documents | PDF (with text layer), DOCX, XLSX, PPTX, ODT, ODS | pdftotext / internal XML | 1 |
| Plain text | TXT, MD, CSV, LOG, RTF | direct read | 1 |
| Scanned PDF | PDF with no text layer | Tesseract OCR | 3 |
| Images | JPG, PNG, WEBP, TIFF, RAW | EXIF + OCR | 3 |
| Audio | MP3, FLAC, OGG, WAV, M4A, AAC | ID3/Vorbis tags (mutagen) | 2 |
| Video | MP4, MKV, AVI, MOV, WEBM | ffprobe metadata | 2 |
| Source code | PY, JAVA, JS, TS, C, CPP, GO, RS, HTML, SQL | first line + language detection | 2 |
| Archives | ZIP, TAR, GZ, RAR, 7Z | internal content listing | 2 |
| Ebooks | EPUB | content.opf (title, author, subject) | 2 |
| Unknown | any unlisted extension | magic bytes + file name | 1 |

---

## hints.yaml format

`hints.yaml` replaces `rules.yaml`. Its scope is limited: it only covers cases that automatic discovery cannot infer by itself (special cases with no thematic semantics).

```yaml
version: 3

hints:

  # Name-based duplicates — discovery can't infer this from content
  - nombre: duplicados_descarga
    filter_mode: any
    filtros:
      - nombre_contiene: [" (1)", " (2)", " (3)", ".crdownload"]
    accion_especial: marcar_duplicado
    conflicto: rename_new

  # Installers — classified by extension, not by topic
  - nombre: instaladores
    filtros:
      - extension: [".exe", ".msi", ".run", ".deb", ".rpm", ".AppImage"]
    accion_especial: carpeta_especial
    nombre_carpeta: Software_Instaladores
    conflicto: skip

  # Images with no thematic context
  - nombre: imagenes_sueltas
    filtros:
      - extension: [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"]
    accion_especial: carpeta_especial
    nombre_carpeta: Imágenes_Generales
    conflicto: rename_new
```

**What is NO LONGER in hints.yaml:**
- Hardcoded destination paths (`~/Downloads/Numerical Methods/`)
- Academic or thematic topic names
- Anything folder discovery can infer on its own

---

## Exclusions format (exclusions.yaml)

```yaml
version: 1

# Folders that are never touched (by exact name, at any level)
carpetas_exactas:
  # System and configuration
  - .git
  - .config
  - .local
  - .ssh
  - .gnupg
  - .cache
  - .mozilla
  - .thunderbird
  - .var
  - snap
  - node_modules
  - __pycache__
  # Dev environments
  - .cargo
  - .dotnet
  - .java
  - .m2
  - .netbeans
  - .npm
  - .vscode
  - .vscode-shared
  - .electron-gyp
  # Tools and agents
  - .claude
  - .codex
  - .agents
  - .kiro
  - .pi
  - .aws
  - .pki
  - .windows
  # User apps
  - .minecraft
  - .steam
  - .spicetify
  - .zen

# Files that are never touched (by glob pattern)
patrones_nombre:
  - "*.sock"
  - "*.pid"
  - "*.lock"
  - "*.env"
  - "*.log"
  - "*.bak"
  - "desktop.ini"
  - "thumbs.db"
  - ".DS_Store"
  - ".gitignore"
  - ".bash_history"
  - ".bash_logout"
  - ".bash_profile"
  - ".bashrc"
  - ".python_history"
  - ".XCompose"
  - ".pulse-cookie"
  - ".claude.json"
  - "*.desktop"

# Absolute paths that are never touched
rutas_absolutas:
  - ~/Proyectos/clasificador-archivos
  - ~/Proyectos
  - ~/Projects
  - ~/NetBeansProjects
```

---

## Development phases

### Phase 1 — Downloads MVP ✦ (completed)
Goal: replicate what we did manually, but runnable at any time.

**Interface decisions that lay the foundation for every phase:**
- The target directory is always an argument: `clasi run <directory>`
- Hints always come from an external file: `--hints <path>`
- Exclusions are active from day 1: `--exclusions <path>`

**Deliverables:**
- [x] `config/exclusions.yaml` — full exclusion list based on the real home structure
- [x] `config/hints.yaml` — special cases v3 (replaces rules.yaml; migration completed in Phase 1)
- [x] `src/extractor.py` — extracts text from PDF (pdftotext), DOCX and XLSX (internal XML)
- [x] `src/scanner.py` — lists files in the given directory, applies exclusions, skips symlinks
- [x] `src/classifier.py` — two-stage classification: hints first, then TF-IDF discovery
- [x] `src/executor.py` — moves files with conflict resolution, JSON Lines log, undo
- [x] `src/cli.py` — `clasi sim`, `clasi run`, `clasi undo` subcommands
- [x] `requirements.txt` — click, pyyaml, rich
- [x] Install dependencies: `sudo pacman -S python-click python-yaml python-rich`
- [x] Real test on `~/Downloads` — tool works correctly
- [x] Test on `~/` — found and fixed 2 bugs (symlinks, .bash_logout)

**Success criterion:** ✅ `clasi sim ~/Downloads` and `clasi sim ~/` work correctly.

### Phase 2 — Global discovery engine + folder unification
Goal: recursive index, detection of duplicate or misplaced folders, and extended file types.

- [x] `src/discovery.py` — folder index with TF-IDF scoring and content-only-match penalty
- [x] TF-IDF-based classifier against the index (threshold 0.40, configurable)
- [x] Migrate `rules.yaml` → `hints.yaml` (special cases only)
- [x] Recursive discovery: global index of every thematic folder on the system
- [x] Folder name normalization for duplicate detection (`normalizar_nombre()`)
- [x] Canonical folder selection by location priority (Documents > ~/ > other > Downloads)
- [x] `clasi sim`: duplicate folder warnings and relocation suggestions
- [x] `max_depth` as a CLI argument (`--max-depth`, default 4)
- [x] Folder categorization (thematic/container) before indexing — REV-001: blocklist (`carpetas_genericas.yaml`) + content homogeneity bounded by depth (`MAX_PROFUNDIDAD_HOMOGENEIDAD = 2`)
- [ ] `clasi merge`: unify duplicate folders into the canonical one (with log and undo)
- [ ] `clasi move-folder`: relocate a folder to a more appropriate place
- [ ] Support for: audio (mutagen), video (ffprobe), source code, ZIP, EPUB
- [ ] Redundant pair detection `(X.pdf, X_merged.pdf)`
- [ ] Automatic thematic folder creation when >7 files have no existing destination
- [ ] `clasi catalog`: markdown catalog of processed files

### Phase 3 — OCR, interactive review, and confidence
Goal: classify the 25% of files Phase 2 can't resolve on its own.

- [ ] OCR with Tesseract for scanned PDFs and images
- [ ] Interactive review: show file, extracted text, candidate destination → user confirms
- [ ] Configurable confidence threshold (only move if score ≥ X)
- [ ] EXIF support for images (organize by date/camera)
- [ ] `python` filter for advanced custom logic (inspired by `organize`)

### Phase 4 — Universality and deployment on any machine
Goal: anyone can install `clasi` and use it without manual configuration.

- [ ] Clean install: `pip install clasi` → works immediately
- [ ] `clasi init`: scans the machine, generates an `exclusions.yaml` adapted to the detected system
- [ ] Full recursive support with configurable `max_depth`
- [ ] Folder type detection (code project, system config) to avoid disorganizing it
- [ ] Regression tests before running on the home directory
- [ ] User documentation

---

## Success metrics

| Metric | Goal |
|---------|------|
| Files classified automatically (Phase 1) | ≥ 75% |
| Files classified automatically (Phase 2+) | ≥ 90% |
| False positives (misclassified files) | < 5% |
| Moved files that can be reverted | 100% |
| Run time on ~/Downloads (~200 files) | < 30 seconds |
| New folder created by the user → available without reconfiguration | 100% |
| Works on a new machine with no configuration file edits | ✓ |

---

## Pending decisions

- [x] **Implementation language** — Python. Dependencies: pdfplumber or PyMuPDF, python-docx, click, pyyaml, rich.
- [x] **CLI command name** — `clasi`.
- [x] **Log format** — JSON Lines. One line per operation, independently reversible.
- [x] **Interactive review interface** — `rich` for terminal tables (Phase 1); evaluate `textual` in Phase 3.
- [x] **Conflict resolution** — `skip`, `rename_new`, `rename_existing`. Never overwrite.
- [x] **Rules YAML structure** — migrated to `hints.yaml` in Phase 2; special cases with no thematic semantics only.
- [x] **Classification algorithm** — simple TF-IDF against the index of existing folders. No external ML model.
- [x] **TF-IDF confidence threshold** — 0.40. Calibrated to avoid false positives from "mentioning" vs. "belonging to" a topic. Configurable via CLI with `--umbral`.
- [x] **Content-only-match penalty** — if the file's stem contributes no token matching the folder, the score is multiplied by 0.35. Prevents documents that MENTION a topic from being classified as belonging to it.
- [x] **Folder categorization (REV-001)** — `UMBRAL_HOMOGENEIDAD = 0.15` (average Jaccard between sampled files, minimum 3 samples) and `MAX_PROFUNDIDAD_HOMOGENEIDAD = 2`. Both provisional: calibrated only against the real test on `~/Documents`; recalibration pending against more user structures.
- [ ] **Init subcommand name** — `clasi init`, `clasi setup`, something else?

---

## A note on language

The codebase, CLI output, and config files are in Spanish (the original author's language) — that's intentional and won't change, since it's already tested and working end to end. This document and the review log (`REVIEWS_*.md`) are English translations of the original `PROYECTO.md` / `Revisiones_*.md`, kept in the repo as Spanish checkpoints of the project's history. The English versions exist to reach a wider audience for testing help. See `README.md` for a quick bilingual orientation.
