# clasi — Automatic File Classifier

> 🇪🇸 **Resumen rápido en español:** `clasi` es una herramienta de línea de comandos en Python que organiza tus archivos automáticamente, aprendiendo de la estructura de carpetas que ya tienes (no necesitas escribir reglas). La meta final **no es solo ordenar `~/Downloads`**: es leer todo tu árbol de directorios (todo `~/`, con las exclusiones de seguridad necesarias) para tener una imagen global de dónde vive cada tema, y enrutar cualquier archivo suelto hacia ahí — por eso el descubrimiento de carpetas es recursivo y global, no solo de una carpeta aislada. **Necesitamos ayuda de la comunidad probándola contra árboles de carpetas reales y distintos** — entre más variada la forma en que cada persona organiza su computadora, mejor podemos encontrar casos donde la herramienta se equivoca. Es 100% seguro de probar: `clasi sim <carpeta>` **nunca mueve nada**, solo te muestra qué haría, sin importar qué tan grande sea el árbol que le pidas analizar. Ve a [¿Cómo puedo ayudar?](#-help-us-test-we-need-real-world-folder-structures) para los pasos. El resto de este documento está en inglés para llegar a más gente, pero toda la herramienta (CLI, mensajes, configuración) funciona en español. La documentación de diseño completa está en [`PROJECT.md`](PROJECT.md) y [`REVIEWS_1.1.md`](REVIEWS_1.1.md) / [`REVIEWS_1.2.md`](REVIEWS_1.2.md) (en inglés).

---

`clasi` is a Python CLI that organizes your files automatically by learning from the folder structure you *already have* — you don't write destination rules. If you have a folder named `Numerical Methods`, files about numerical methods go there. No config file says so; the tool discovered it.

```
Most tools: you write rules → the tool follows them
clasi:      you organize folders (like you already do) → the tool learns from them
```

**The goal is not "tidy up one folder."** `clasi` builds its destination index by walking the *entire* directory tree you point it at — recursively, across however many subfolders exist — so it has the same global picture of "where everything lives" that you'd have in your own head. Pointing it at `~/Downloads` only exercises a small, shallow slice of that. Pointing it at `~/Documents` or your whole `~/` is what actually tests the thing this project is for.

It's a personal project, still in active development (Phase 2 of 4 — see [`PROJECT.md`](PROJECT.md) for the full roadmap), built and tested so far against one real, full `~/Documents` tree. That's exactly the problem this README is about.

## Why we need your help

Every person organizes their files differently. Some have one folder per course; some dump everything into `Misc`; some nest five levels deep, some never go past two. The discovery and scoring logic in `clasi` was designed and calibrated against a single real home directory's *entire tree* — which means it is almost certainly missing edge cases that only show up on *other* people's folder structures, especially ones with a shape nothing like "academic student with course folders."

Building synthetic test folders by hand doesn't really solve this: it's slow, and worse, it's not an accurate simulation of how real people actually organize their stuff — least of all at the scale and depth of an entire real home directory. The most useful test data is your real, full directory tree (`~/Documents`, or all of `~/` if you're comfortable reviewing the exclusion list first), exactly as messy or tidy as it already is.

That's why this is being open-sourced: **we need testers with genuinely different, genuinely large folder trees**, not more code right now.

## What `clasi` does

- **Discovers** your existing folders and learns what topic each one represents, from its name and a sample of its contents.
- **Classifies** loose files by scoring them against that discovered index (a simple TF-IDF-style match, with penalties to avoid false positives — see [`PROJECT.md`](PROJECT.md) for the algorithm).
- **Never deletes.** It only moves files, and every move is logged so it can be undone.
- **Never overwrites.** Name conflicts are resolved by skipping, renaming the new file, or renaming the existing one — configurable, never silent overwrite.
- Ships with a sane default exclusion list (`.git`, `.ssh`, `node_modules`, dev tool configs, etc.) so it won't wander into places it shouldn't.

It does **not** use any external AI/ML model — discovery and scoring are local, deterministic, and fast.

## Installation

Requires Python 3.10+ and `pdftotext` (from `poppler-utils`) for PDF text extraction.

```bash
# Arch Linux
sudo pacman -S python-click python-yaml python-rich poppler

# Debian/Ubuntu
sudo apt install python3-click python3-yaml python3-rich poppler-utils

# or, in a virtualenv:
pip install -r requirements.txt
```

Clone the repo and run it from `src/`:

```bash
git clone <your-fork-or-this-repo-url>
cd clasificador-archivos/src
python3 cli.py sim ~/Documents   # or ~/, or any directory with real subfolders
```

## Usage

```bash
clasi sim <directory>       # Dry run — shows what WOULD move, moves nothing
clasi run <directory>       # Actually moves files, writes a log
clasi undo                   # Reverts the most recent run
clasi evaluate <directory>  # Measures accuracy against your own existing organization (read-only)
```

Useful flags (see `--help` on any subcommand):

- `--max-depth N` — how deep to recurse when discovering folders (default 4)
- `--umbral X` — minimum confidence score to accept a match, 0.0–1.0 (default 0.40)
- `--exclusions <path>` / `--hints <path>` / `--carpetas-genericas <path>` — point to custom config files instead of the defaults in `config/`
- `evaluate` only: `--seed N` — fix the random seed so the same holdout files are picked on a re-run

**Always run `sim` first.** It's read-only by design — it builds the same index and makes the same decisions as `run`, but only prints a table.

### `clasi evaluate`: a number instead of "looks fine to me"

`sim` output is easy to skim but hard to compare across two people's completely different folders — "looks reasonable" from one tester isn't comparable to "looks reasonable" from another. `evaluate` fixes that by using something that's already there: **the folder you already filed each file into is the correct answer.** It temporarily (no disk writes) pulls 1-3 files out of each thematic folder, rebuilds that folder's signature without them, then checks whether `clasi` would route each held-out file back to where it actually already lives.

```bash
python3 src/cli.py evaluate ~/Documents
```

You get a real, comparable percentage (correct / wrong-folder / no-destination) plus a per-case table — with every file and folder name replaced by a short hash (`a3f1c2.pdf` in `carpeta_07`), so it's safe to paste directly into a GitHub issue. A report is also saved to `logs/evaluacion_<timestamp>.md` for the same purpose.

## Safety notes

- `sim` never touches the filesystem, **no matter how large or how high up the tree you point it at** — `clasi sim ~/` is exactly as safe as `clasi sim ~/Downloads`. Run it as many times as you want.
- `run` only **moves** files (never deletes), and always logs to `logs/*.jsonl` before/while moving, so `clasi undo` can reverse it.
- Review `config/exclusions.yaml` before running `run` (not `sim`) anywhere beyond a small test folder — especially before trying it on your full home directory. Add any paths you don't want touched (project folders, game saves, etc.).
- When in doubt about `run`, test on a copy of a folder, not the original. `sim` doesn't have this concern — it's read-only by construction.

## 🧪 Help us test: we need real, full folder trees

This is the main ask. If you're willing to spend 10 minutes:

1. Clone the repo and install dependencies (see above).
2. Open `config/exclusions.yaml` and skim it — add any paths specific to your machine that you don't want touched. This matters more for `run`, but it's good practice either way.
3. Run `evaluate` against the most complete, realistic directory tree you're comfortable with — ideally `~/Documents` or your whole `~/`, not just `~/Downloads`. This is **read-only**, the same as `sim`:
   ```bash
   python3 src/cli.py evaluate ~/Documents --seed 1
   ```
   Open a [test report issue](../../issues/new/choose) and paste the table it prints (or the `logs/evaluacion_*.md` file) — it's pre-anonymized, nothing to redact. This single number/table is far more useful to us than a description, because it's directly comparable across everyone's completely different folders.
4. Optionally, also run a plain `sim` and look at the output table for anything `evaluate`'s numeric summary wouldn't catch (it only tests files already filed into folders — `sim` shows what happens to truly loose ones):
   ```bash
   python3 src/cli.py sim ~/Documents
   ```
   Did it make sense? Specifically:
   - Files that got a confident destination that's clearly *wrong*.
   - Files that got **no destination** but obviously belong somewhere you have a folder for.
   - Folders it warned about as "duplicate" that aren't, or duplicates it missed.
   - Whether it picked the destination you'd have picked yourself, when you have more than one folder that could plausibly fit.
5. Open a [GitHub issue](../../issues/new/choose) with what you found. You do **not** need to share your actual file names or folder contents if you'd rather not — a description of your folder organization style (e.g. "I have one folder per client, each with year subfolders" or "everything lives loose in Downloads, no subfolders at all") plus which file got misrouted is already useful. Screenshots of the `sim` table with sensitive names blurred work great too.

The more different your folder habits are from "academic student with course folders," and the bigger/deeper your real tree is, the more valuable your test is — that's the structure and scale this was built and tuned against so far, so it's already the best-covered case.

## Project status & architecture

This project tracks its own design decisions and known weaknesses in plain markdown instead of hiding them:

- [`PROJECT.md`](PROJECT.md) — full architecture, design rationale, requirements, development phases, calibration history.
- [`REVIEWS_1.1.md`](REVIEWS_1.1.md), [`REVIEWS_1.2.md`](REVIEWS_1.2.md) — an open log of architectural risks and questionable assumptions found during self-review, including ones found and partially fixed *because* of real-data testing. Worth reading if you want to know what's already known to be shaky.

Currently in **Phase 2** (global discovery engine + folder de-duplication). Phases 3 (OCR, interactive review) and 4 (one-command install, zero-config on a new machine) are not started.

## License

GPLv3 — see [`LICENSE`](LICENSE). You're free to use, study, modify, and redistribute this, including modified versions, as long as those stay under the same license.
