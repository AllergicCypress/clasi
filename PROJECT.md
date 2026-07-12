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

### 2026-06-21 session — `clasi evaluate` (holdout evaluation) and two real findings

17. **The "ground truth" for measuring accuracy already exists: it's wherever the user already filed each thing.** No human needs to judge "is this well organized" — 1-3 files are virtually held out from each thematic folder (max 20% of its contents), that folder's signal is rebuilt without them, and we check whether `clasi` routes them back to the same folder. This gives an objective, cross-user-comparable accuracy percentage without anyone sharing real files (reports only use short hashes). Implemented as `clasi evaluate <directory>` in `src/evaluator.py`.

18. **`MIN_LONGITUD_TOKEN` was erasing the numbers that distinguish structural folders.** The first `clasi evaluate` run against `~/Documents`: only 5% accuracy. Cause: `tokenizar()` discarded tokens under 3 characters as if they were stopwords like "the"/"a", but that also erased the numbers in `UNIT 1` vs `UNIT 6`, or split `2.6` into `"2"` + `"6"` (which then collided with `6.1`). Both folders ended up with the identical name token — indistinguishable to the scorer. Fixed in two steps: (a) purely numeric tokens are kept regardless of length, (b) decimals (`"2.6"`) are captured whole instead of being split at the dot. Result: 5%→19% accuracy, and "incorrect" (wrong destination) dropped from 56%→19% — most remaining failures now land on "no destination" (the safe side of the error), not on a wrong move.

19. **That same bug had inflated a result we'd counted as "validated."** The documented case `tarea_7_2.* → .../TAREA 3.1 (score 0.71)` wasn't a genuine match: `"TAREA 3.1"` and `"tarea_7_2"` both collapsed to the same `"tarea"` token (losing "3.1" and "7.2"), producing a false 100% name match even though the numbers don't correspond. After the fix, the real score (0.36–0.39) falls below the threshold and the file ends up with no destination — more honest than a move justified by a false signal. Lesson: a "high" score isn't evidence the algorithm understood anything; you should be able to explain *why* it matched before counting it as validation.

20. **Bigger finding, still unresolved: the global index collapses structural folders from different subjects into one.** `clasi evaluate` showed most remaining "incorrect" cases are cross-course collisions: `Numerical Methods/UNIT 1` gets confused with `Differential Equations/UNIT1/1.1` (score 0.91) because the index keeps only **one** canonical entry per normalized name, with no awareness of which subject each one belongs to. This limitation had already been flagged as "out of scope" in an earlier session; there's now quantitative evidence it's the dominant remaining error source. Logged as REV-004 (see `REVIEWS_1.2.md`) — design pending, since it's a bigger architectural change than a tokenization fix.

### 2026-06-22 session — `clasi evaluate ~` exposed an exclusions gap, not a "dot folder" bug

21. **Hint-managed flat destinations (`Software_Instaladores`, `Imágenes_Generales`, `Comprimidos`, `Temporales_Duplicados`) were being recursed into and indexed as thematic hierarchies.** Running `clasi evaluate ~` for the first time dropped accuracy to 8% with 16% wrong moves — far worse than the calibrated `~/Documents` run. Cause: a full Python 3.12.13 source tarball had been extracted inside `~/Downloads/Software_Instaladores/` (`Doc/`, `Include/`, `PC/`, `Modules/`...). Discovery has no concept of "this folder is a flat hint dump, not a hierarchy" — it indexed every subfolder as a candidate destination, producing dozens of `.py/.c/.h/.rst/.vcxproj` files matching unrelated folders at a suspiciously exact score of 0.70 (the structural-pattern shortcut, not a real content/name match). The user's assumption — "hidden (`.`) folders are already excluded so this shouldn't happen" — was correct but irrelevant: `exclusions.yaml` excludes by exact name regardless of dot-prefix, and none of the polluting folders were hidden. The actual gap was architectural: hint `carpeta_especial` destinations are written by `classifier.py` directly as `directorio_base / nombre_carpeta`, completely bypassing the discovery index — so excluding them from discovery costs nothing and removes a real pollution source. Fixed by adding the four hint destination names to `carpetas_exactas` in `exclusions.yaml`. Result on `~`: index 261→135 folders, correct 8%→15%, sin-destino 76%→70%, and the 0.70-score noise storm disappeared entirely. Remaining `incorrecto` cases after the fix are genuine academic-document misroutes, not archive noise — next target for calibration.

22. **`puntuar()` let numeric DATA inside a document's body count as a structural NAME match.** Reviewing the 8 remaining `incorrecto` cases on `~`: `ACTIVIDAD 5.4.docx` (real subject: Métodos Numéricos) scored 0.75 against the unrelated folder `ACTIVIDAD 2.7` — confirmed by direct inspection: the file's body is a results table containing the literal text "2.7" as a data value, and `puntuar()` computed `tokens_todos = tokens_contenido | tokens_stem` *before* checking name-token hits, so that coincidental number counted as a full name-token match. The penalty that should have caught this (`score_nombre × 0.35` when the stem contributes nothing) never triggered, because the stem *did* contribute the generic word "actividad" — enough to waive the penalty while the numeric token rode in for free on body content. This is a second-order regression from finding #18 (keeping numeric tokens as the structural identity of a folder) — correct identity signal, but only trustworthy when it comes from the file's own name, never from data inside it. Fix in `discovery.py::puntuar()`: numeric name-tokens now only count as hits against `tokens_stem`, never against `tokens_contenido`; non-numeric name-tokens are unaffected. Verified on `~`: `incorrecto` 8→5 (15%→9%), with **zero regression** on the calibrated `~/Documents` baseline (`clasi sim ~/Documents` gives byte-identical output before/after — 6 con destino, 13 sin destino). Two previously-"correct" cases also disappeared (`carpeta_2c8154`, `carpeta_3bfba4`, both `metodo=contenido`, scores 0.41 and 0.54) — not a loss: inspection showed they were the *same* bug landing on the right folder by luck (the same kind of inflated, unexplainable score flagged in finding #19), now honestly `sin_destino` instead of an accidentally-correct guess.

    **Remaining 5 `incorrecto` after this fix, all genuine and NOT calibration-fixable:**
    - 3 cases are confirmed instances of REV-004 (see finding #20): files named bare `1.1.pdf`, `1.2.pdf`… inside `Metodos Numericos/UNIDAD 1` don't token-match their own parent folder at all (`"1.1"` as a whole decimal token vs. `{"unidad", "1"}` — no overlap), but score a perfect 1.0 name-match against an unrelated subject's actual subfolder named exactly `"1.1"` (`Ecuaciones Diferenciales/UNIDAD1/1.1`, scores 0.91–0.96). No threshold or weight change fixes this: the index has no concept of "subject," so a bare numeric subfolder name in any subject is a global attractor for any file sharing that number, anywhere. Needs the index design change already logged as REV-004 — out of scope for a calibration pass.
    - 1 case (score 0.44) is a genuine borderline miss right at the 0.40 threshold (`ACT_3.2` → wrong unit's `ACTIVIDAD 6.6`). Raising the global umbral to clear it isn't free: the lowest validated `correcto` score in this same run is 0.41 (`contenido` method) — moving the threshold above 0.44 would kill that real match to suppress this one false one. Not adjusted without re-validating against the full `~/Documents` baseline first.
    - 1 case (score 0.55) is a parent→child move within the *same* unit (`UNIDAD 6` loose file → `UNIDAD 6/ACTIVIDAD RUNGE KUTTA`) — arguably a "too specific" suggestion rather than a wrong one, since both folders share the real topic. Not a misrouting in the harmful sense the metric is meant to catch.

23. **REV-004 isn't an index-collapsing bug — it's a scorer bug.** Tried the line of investigation logged in `REVIEWS_1.2.md` (REV-004): scope the index key for structural-by-position folders by their nearest genuine-topic ancestor, so `Numerical Methods/UNIT 1` and `Differential Equations/UNIT1` get separate index entries instead of one canonical entry shadowing the other. Verified zero regression on the `~/Documents` baseline, but `clasi evaluate ~` showed no real improvement (`incorrecto` count went 5→7 across comparable runs). Direct inspection of the real paths behind the incorrect cases (not the anonymized report) showed why: the colliding folders in the actual failures had never shared a bare normalized name to begin with (`Ecuaciones Diferenciales/UNIDAD1/1.2` vs `Metodos Numericos/UNIDAD 1` — already distinct entries). The real mechanism is in `puntuar()`: a short, purely-numeric folder name like `"1.2"` has its entire `tokens_nombre` satisfied by one matching token in *any* file's stem anywhere in the tree, producing a 0.7–0.97 "nombre" score regardless of subject — `construir_indice()`'s key structure was never the bottleneck. Reverted the change; `discovery.py` is back to the #21/#22 state. Next attempt needs to live in the scorer (e.g. requiring more than a single coincidental token before granting full "nombre" weight, or factoring in tree proximity to the candidate folder), calibrated carefully against `~/Documents` since legitimate matches like `ACTIVIDAD 5.3` rely on the same "small token set, full match" mechanism. Full writeup in `REVIEWS_1.2.md` § REV-004, "Rejected attempt."

24. **Two scorer-side penalties for purely-numeric folder names, both reverted — REV-004 is a genuine information limit, not a missing calibration knob.** Following on #23, tried penalizing a purely-numeric `tokens_nombre` match (`{"1.2"}`) unless corroborated by (a) the folder's sampled content, then (b) the nearest non-structural ancestor's name tokens (`tokens_ancla`) — directly motivated by the user's clarification that assignment cover pages do state the subject name even when the rest of the template (institute, professor) is shared. Variant (a) had no effect: every folder's content sample is dominated by that shared administrative template regardless of subject, so `hits_contenido` is almost never 0. Variant (b) is conceptually correct but broke a real validated baseline case: `Calculo de varias variables 1.2.pdf` (score 0.72, previously correct) has a PDF with completely garbled, non-extractable text (confirmed by printing `extraer_texto()`'s raw output — byte soup, not text) and a stem that doesn't mention the subject either — there is no signal anywhere `clasi` can read to tell this apart from a real cross-subject collision. Both variants reverted; `discovery.py`/`evaluator.py` are back to the #21/#22 baseline (verified identical diff). Conclusion: incremental scorer penalties on this specific signal just trade one error type for the other, because both failure modes draw on the same single starved data point. Don't retry a blanket penalty here without first fixing something orthogonal (OCR fallback for garbled-extraction PDFs) or pivoting to the "surface as low-confidence in the UI" line of investigation. Full writeup in `REVIEWS_1.2.md` § REV-004, "Rejected attempt #2."

### 2026-06-25 session — Phase 2 completion

25. **Content-type subfolder names (`Imágenes`, `Software`, `Música`, `Vídeos`…) appear in every subject folder by design, producing dozens of false duplicate warnings.** Running `clasi sim ~/Downloads` after implementing `clasi merge` surfaced a noisy storm of merge suggestions: `~/Downloads/Cálculo/Imágenes` flagged as a duplicate of `~/Downloads/Circuitos/Imágenes`, `~/Downloads/Métodos Numéricos/Imágenes`, etc. — 34 false warnings for just three shared names. These folders are structurally repetitive (each subject organizes its own images/software/videos/music in a same-named subfolder) exactly like `UNIDAD 1`, `ACTIVIDAD`, `TAREA`. Fix: add these names to `_PATRON_ESTRUCTURAL` in `discovery.py`. Effect: they remain valid index entries and classification targets (files *can* be routed to `Circuitos/Imágenes`), but `_filtrar_duplicadas_reales` ignores them as candidates for duplicate reporting. Verified: the 34 false warnings disappeared; the one genuine duplicate (`~/Downloads/Código` vs `~/Downloads/Programación/Código`) was correctly reported.

---

### 2026-07-05 session — REV-004 resolved; Phase 2 + Phase 3 fully complete

26. **OCR exposes false positives that were previously undetectable.** `Calculo de varias variables 1.2.pdf` and `Calculo Vectorial 1.2.pdf` were recorded as "correct" at score 0.72 → `Ecuaciones Diferenciales/`. With OCR recovering the real content ("Vectores y espacio tridimensional"), the score dropped to 0.21 → `sin_destino`. Both files belonged to a Cálculo Vectorial folder that no longer exists — the old score was a false positive driven purely by `"1.2"` in the stem. Lesson: when pdftotext fails, only the stem token survives; any numeric-stem file appears to match any same-numbered structural folder at 0.72. Before OCR, these false positives were invisible and could be validated as correct by mistake.

27. **`tokens_ancestros` is the right fix for purely-numeric folder name ambiguity, but it only moves the needle for Variant B (file with readable content).** Variant A (blank file, no signal) correctly becomes `sin_destino`. The aggregate metrics didn't change (8/15% correct, 5/9% incorrect) because the files that moved from sin_destino → correct via `contexto` were offset by OCR removing the false positives that had been counted as correct. The net effect is: same numbers, but the 8 correct are now genuinely correct.

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
├── PROJECT.md           ← this document
├── REVIEWS_1.1.md       ← architecture review log
├── REVIEWS_1.2.md
├── pyproject.toml       ← pip-installable package (setuptools src-layout; build-backend: setuptools.build_meta)
├── requirements.txt     ← pip fallback for non-pacman systems
├── install.sh           ← single-command installer (Arch, Debian/Ubuntu/Zorin/Mint)
├── src/
│   └── clasi/           ← installable Python package
│       ├── __init__.py
│       ├── __main__.py
│       ├── discovery.py     ← dynamic folder index; TF-IDF scoring with penalties
│       ├── scanner.py       ← walks the directory, applies exclusions, skips symlinks
│       ├── extractor.py     ← extracts text/metadata depending on file type
│       ├── classifier.py    ← hints first, then TF-IDF discovery
│       ├── executor.py      ← moves files, JSON Lines log, undo
│       ├── evaluator.py     ← holdout accuracy evaluation
│       ├── init.py          ← system detection for clasi init
│       ├── cli.py           ← clasi sim | run | undo | merge | move-folder | catalog | evaluate | review | init
│       └── config/          ← bundled defaults (user overrides go in ~/.config/clasi/)
│           ├── hints.yaml              ← special cases with no thematic semantics (v3)
│           ├── exclusions.yaml         ← folders and patterns to ignore
│           └── carpetas_genericas.yaml ← container (non-thematic) folder names (REV-001)
├── config/              ← project-level originals (tracked in git; not loaded at runtime)
├── logs/                ← local dev logs (gitignored except .gitkeep)
└── tests/
    ├── test_discovery.py
    ├── test_executor.py
    ├── test_classifier.py
    └── test_init.py
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

  # Compressed files
  - nombre: comprimidos
    filtros:
      - extension: [".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar"]
    accion_especial: carpeta_especial
    nombre_carpeta: Comprimidos
    conflicto: skip

  # Originals whose _merged version already exists — the original is redundant
  - nombre: original_con_merged
    filtros:
      - tiene_merged: true
    accion_especial: marcar_duplicado
    conflicto: skip

  # PDFs with garbled/unextractable text — isolate for manual review or OCR
  - nombre: pdf_texto_corrupto
    filter_mode: all
    filtros:
      - extension: [".pdf"]
      - texto_corrupto: true
    accion_especial: carpeta_especial
    nombre_carpeta: PDF_Texto_Corrupto
    conflicto: skip
```

**Available filter keys:**
- `extension: [list]` — matches by file extension
- `nombre_contiene: [list]` — matches if any string appears in the filename
- `nombre_glob: pattern` — matches filename against a glob pattern
- `texto_contiene: [list]` — matches if any string appears in the extracted text
- `texto_corrupto: true` — matches PDFs/docs with >5% control characters in extracted text
- `sin_texto_util: true` — matches when extracted text (including OCR output) is under 40 chars; used to route non-OCR-readable images to `Imágenes_Generales`
- `tiene_merged: true` — matches `X.ext` when `X_merged.ext` exists in the same directory
- `python: "<expr>"` — evaluates an arbitrary Python expression; available variables: `archivo` (Path), `texto` (str), `nombre`, `stem`, `sufijo`, `re` (module), `Path` (class); returns True/False

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
  # Flat destinations managed by hints.yaml (carpeta_especial): never
  # thematic hierarchies, and may contain extracted archive/installer
  # content whose subfolders must not be indexed as classification targets
  - Software_Instaladores
  - Imágenes_Generales
  - Comprimidos
  - Temporales_Duplicados

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
- [x] `src/cli.py` — `clasi sim`, `clasi run`, `clasi undo`, `clasi merge`, `clasi move-folder`, `clasi catalog`, `clasi evaluate`, `clasi review`, `clasi init` subcommands
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
- [x] `clasi evaluate`: holdout accuracy evaluation against the user's own existing organization (`src/evaluator.py`)
- [x] Numeric and decimal tokens preserved in `tokenizar()` (previously lost to `MIN_LONGITUD_TOKEN`)
- [x] REV-004: hierarchy-aware scoring via `tokens_ancestros` — purely-numeric folder names use ancestor context as primary signal (resolved 2026-07-05, see REVIEWS_1.2.md)
- [x] `clasi merge`: unify duplicate folders into the canonical one (with log and undo)
- [x] `clasi move-folder`: relocate a folder to a more appropriate place
- [x] Support for: audio (mutagen/ffprobe), video (ffprobe), source code, ZIP, TAR, EPUB, PPTX
- [x] Redundant pair detection `(X.pdf, X_merged.pdf)` — `tiene_merged` filter in hints.yaml
- [x] `clasi sim` suggests new thematic folders when ≥7 sin-destino files share a topic token
- [x] `clasi catalog`: markdown catalog of processed files
- [x] `clasi evaluate --verbose`: show real paths instead of hashes (for local debugging)

### Phase 3 — OCR, interactive review, and confidence
Goal: classify the 25% of files Phase 2 can't resolve on its own.

- [x] OCR with Tesseract for scanned PDFs and images
- [x] Interactive review: show file, extracted text, candidate destination → user confirms (`clasi review`)
- [x] Configurable confidence threshold (only move if score ≥ X) — `--umbral` flag on `sim`/`run`/`evaluate`
- [x] EXIF support for images (organize by date/camera) — `_exif()` in extractor.py reads ImageDescription, XPTitle, XPComment, Artist, Copyright
- [x] `python` filter for advanced custom logic (inspired by `organize`) — inline Python expression in hints.yaml; variables: archivo, texto, nombre, stem, sufijo, re, Path

### Phase 4 — Universality and deployment on any machine ✦ (completed)
Goal: anyone can install `clasi` and use it without manual configuration.

- [x] `install.sh` — single-command installer for Arch Linux, Debian, Ubuntu, Zorin, and Linux Mint; installs system tools via package manager, creates an isolated venv, and registers `clasi` as a global command in `~/.local/bin/` via symlink. On unsupported distros, skips the package step, prints specific instructions, and continues with the Python setup. Verifies that `pdftotext`, `tesseract`, and `ffprobe` are available after install. Re-running is safe (all steps are idempotent).
- [x] `pyproject.toml`: fixed build backend from `setuptools.backends.legacy:build` (non-standard, not present in bundled setuptools) to `setuptools.build_meta` (the correct standard backend). This was discovered when a real installation attempt failed on a fresh venv.
- [x] `clasi init`: scans `~` for dev tools and project dirs, generates `~/.config/clasi/exclusions.yaml`
- [x] Full recursive support with configurable `max_depth` (`--max-depth`, default 4)
- [x] Code project detection — folders with `.git`, `Cargo.toml`, `package.json`, etc. are skipped entirely including their subtrees
- [x] Regression test suite — 60 tests covering tokenization, scoring, conflict resolution, hint evaluation, and project detection
- [x] User documentation — README updated to reflect all phases and commands; future improvement paths documented in PROJECT.md

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
- [x] **Holdout evaluation (`clasi evaluate`)** — 1-3 files per thematic folder, never exceeding 20% of its contents; folders need ≥5 files to be evaluated at all. Reports are anonymized with a short (irreversible) hash + extension.
- [x] **`tokenizar()` keeps numbers** — purely numeric tokens skip the length filter; decimals (`"2.6"`) are captured whole instead of being split at the dot. Fixed after `clasi evaluate` showed it collapsed folders like `UNIT 1`/`UNIT 6` into the same token.
- [x] **Init subcommand name** — `clasi init` (generates `~/.config/clasi/exclusions.yaml` from system scan).

---

## Future improvement paths

Phases 1–4 are complete. `clasi` is deterministic — TF-IDF + static rules, no learning.
The following paths describe how it could improve over time, ordered from least to most disruptive.

---

### Path 1 — Review decisions as auto-generated hints

**What it is:** `clasi review` already captures explicit user decisions (confirm / redirect / skip).
Those decisions are currently discarded after being written to the log. If instead they were
stored as patterns, each review session would generate new entries in `hints.yaml` automatically.

**How to build it:**
1. After each `review` session, scan the log for `regla: "review-manual"` entries.
2. For each one, extract: file extension, tokens from the filename, destination folder.
3. If the same pattern appears ≥3 times across sessions, propose a new hint in `hints.yaml`.
4. User approves, rejects, or edits the proposed hint before it takes effect.

**Why this matters:** It's the only path that makes daily use into training.
After a week of `review` sessions, the tool would handle the user's recurring file types
without manual intervention — no ML required, fully auditable rules.

**Tradeoff:** The generated hints must be reviewed before activation, or the tool risks
encoding a one-off decision as a permanent rule. A "pending hints" queue with explicit
approval is necessary.

---

### Path 2 — Undo as negative feedback

**What it is:** When a user runs `clasi undo`, that signals that the previous run
produced at least one incorrect move. The specific files that were undone are the signal.

**How to build it:**
1. When `clasi undo` runs, compare the reverted files against the original classification log.
2. For each reverted file, record: what score it had, what folder it was sent to, what tokens matched.
3. Store this in a `feedback.jsonl` log alongside the regular operation logs.
4. On future runs, `buscar_destino()` checks `feedback.jsonl`: if a file matches a pattern
   that was previously undone, apply a penalty to that candidate folder's score.

**Why this matters:** It closes the loop on errors without requiring any manual annotation.
The user just uses undo as they normally would — the tool learns from it implicitly.

**Tradeoff:** Requires careful scoping. A single undo of one file should not permanently
penalize a folder that was correct for dozens of other files. The penalty must be
file-pattern-specific, not folder-wide.

---

### Path 3 — Embeddings-based scoring (semantic matching)

**What it is:** Replace TF-IDF with a local embedding model. Instead of checking whether
tokens overlap between a file and a folder, compute a semantic similarity score.
This would allow "redes neuronales" to match a folder called "IA", or "heat transfer"
to match "Transferencia de Calor" — relationships that TF-IDF cannot see.

**How to build it:**
- Use a small multilingual model (e.g. `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`,
  ~45 MB) running locally via `sentence-transformers`.
- At index build time, embed each folder name + content sample → store in a vector cache.
- At classification time, embed the file's text → cosine similarity against the cached vectors.
- Keep the TF-IDF scorer as a fallback for when the embedding model is not installed.

**Why this matters:** This is the only path that resolves cross-language and cross-synonym
ambiguity. The current system requires the file and the folder to share literal tokens.
An embedding model removes that constraint entirely.

**Tradeoff:** This is the most disruptive change — it adds a ~45 MB dependency, increases
classification time (GPU optional but recommended), and the model's behavior is less
auditable than a token count. It also requires a vector cache that must be invalidated
when folders are added or renamed.

**When to pursue this:** Only after Paths 1 and 2 are implemented and the feedback loop
produces enough signal to evaluate whether TF-IDF is the real bottleneck. If `evaluate`
accuracy plateaus above 80%, embeddings may not be worth the complexity.

---

### Path 4 — Filesystem event listener (passive learning)

**What it is:** Watch the filesystem with `inotify` (Linux) for file moves that the user
performs manually — outside of `clasi`. When the user moves a file themselves, that's
ground truth: where they put it is where it belongs.

**How to build it:**
- A background daemon using `watchdog` or direct `inotify` bindings.
- Detects `IN_MOVED_FROM` + `IN_MOVED_TO` pairs in monitored directories.
- Logs them to the same `feedback.jsonl` format as Path 2.
- Over time, this data trains the hint generator from Path 1.

**Why this matters:** It's zero-effort learning — the user doesn't need to do anything
differently. Just organizing files normally generates training signal.

**Tradeoff:** A background process raises privacy and resource concerns.
The daemon must be opt-in, explicit about what it records, and must not store file content —
only filenames, extensions, source directory, and destination directory.

---

### Summary

| Path | Effort | Impact | Fits current architecture |
|------|--------|--------|--------------------------|
| 1 — Review → hints | Low | High | Yes — log already exists |
| 2 — Undo → penalty | Medium | Medium | Yes — log already exists |
| 3 — Embeddings | High | High | No — scorer rewrite |
| 4 — inotify daemon | High | Medium | Partial — new component |

**Recommended starting point:** Path 1. The `review` log already contains everything needed.
The work is: parsing the log, proposing hints, and building an approval UI. No new data
collection, no model training, no architecture change.

---

## A note on language

The codebase, CLI output, and config files are in Spanish (the original author's language) — that's intentional and won't change, since it's already tested and working end to end. This document and the review log (`REVIEWS_*.md`) are in English to reach a wider audience for testing help. See `README.md` for a quick bilingual orientation.
