# clasi — Automatic File Classifier

> 🇪🇸 **Resumen rápido en español:** `clasi` es una herramienta de línea de comandos en Python que organiza tus archivos automáticamente, aprendiendo de la estructura de carpetas que ya tienes (no necesitas escribir reglas). **Necesitamos ayuda de la comunidad probándola contra estructuras de carpetas reales y distintas** — entre más variada la forma en que cada persona organiza su computadora, mejor podemos encontrar casos donde la herramienta se equivoca. Es 100% seguro de probar: `clasi sim <carpeta>` **nunca mueve nada**, solo te muestra qué haría. Ve a [¿Cómo puedo ayudar?](#-help-us-test-we-need-real-world-folder-structures) para los pasos. El resto de este documento está en inglés para llegar a más gente, pero toda la herramienta (CLI, mensajes, configuración) funciona en español. La documentación de diseño original en español se conserva en [`PROYECTO.md`](PROYECTO.md) y [`Revisiones_1.1.md`](Revisiones_1.1.md) / [`Revisiones_1.2.md`](Revisiones_1.2.md).

---

`clasi` is a Python CLI that organizes your files automatically by learning from the folder structure you *already have* — you don't write destination rules. If you have a folder named `Numerical Methods`, files about numerical methods go there. No config file says so; the tool discovered it.

```
Most tools: you write rules → the tool follows them
clasi:      you organize folders (like you already do) → the tool learns from them
```

It's a personal project, still in active development (Phase 2 of 4 — see [`PROJECT.md`](PROJECT.md) for the full roadmap), built and tested so far against one real `~/Documents` tree. That's exactly the problem this README is about.

## Why we need your help

Every person organizes their files differently. Some have one folder per course; some dump everything into `Misc`; some nest five levels deep, some never go past two. The discovery and scoring logic in `clasi` was designed and calibrated against a single real home directory — which means it is almost certainly missing edge cases that only show up on *other* people's folder structures.

Building synthetic test folders by hand doesn't really solve this: it's slow, and worse, it's not an accurate simulation of how real people actually organize their stuff. The most useful test data is your real `~/Documents` or `~/Downloads`, exactly as messy or tidy as it already is.

That's why this is being open-sourced: **we need testers with genuinely different folder habits**, not more code right now.

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
python3 cli.py sim ~/Downloads
```

## Usage

```bash
clasi sim <directory>    # Dry run — shows what WOULD move, moves nothing
clasi run <directory>    # Actually moves files, writes a log
clasi undo                # Reverts the most recent run
```

Useful flags (see `--help` on any subcommand):

- `--max-depth N` — how deep to recurse when discovering folders (default 4)
- `--umbral X` — minimum confidence score to accept a match, 0.0–1.0 (default 0.40)
- `--exclusions <path>` / `--hints <path>` / `--carpetas-genericas <path>` — point to custom config files instead of the defaults in `config/`

**Always run `sim` first.** It's read-only by design — it builds the same index and makes the same decisions as `run`, but only prints a table.

## Safety notes

- `sim` never touches the filesystem. Run it as many times as you want.
- `run` only **moves** files (never deletes), and always logs to `logs/*.jsonl` before/while moving, so `clasi undo` can reverse it.
- Review `config/exclusions.yaml` before pointing `clasi` at anything beyond `~/Downloads` — especially before trying it on your full home directory. Add any paths you don't want touched (project folders, game saves, etc.).
- When in doubt, test on a copy of a folder, not the original.

## 🧪 Help us test: we need real-world folder structures

This is the main ask. If you're willing to spend 10 minutes:

1. Clone the repo and install dependencies (see above).
2. Open `config/exclusions.yaml` and skim it — add any paths specific to your machine that you don't want touched (it already covers common system/dev folders).
3. Run the **dry run only**, against a real folder of yours (`~/Downloads` is usually the most interesting, since it's the messiest):
   ```bash
   python3 src/cli.py sim ~/Downloads
   ```
4. Look at the output table. Did it make sense? Specifically:
   - Files that got a confident destination that's clearly *wrong*.
   - Files that got **no destination** but obviously belong somewhere you have a folder for.
   - Folders it warned about as "duplicate" that aren't, or duplicates it missed.
5. Open a [GitHub issue](../../issues/new/choose) with what you found. You do **not** need to share your actual file names or folder contents if you'd rather not — a description of your folder organization style (e.g. "I have one folder per client, each with year subfolders" or "everything lives loose in Downloads, no subfolders at all") plus which file got misrouted is already useful. Screenshots of the `sim` table with sensitive names blurred work great too.

The more different your folder habits are from "academic student with course folders," the more valuable your test is — that's the structure this was built and tuned against, so it's already the best-covered case.

## Project status & architecture

This project tracks its own design decisions and known weaknesses in plain markdown instead of hiding them:

- [`PROJECT.md`](PROJECT.md) — full architecture, design rationale, requirements, development phases, calibration history.
- [`REVIEWS_1.1.md`](REVIEWS_1.1.md), [`REVIEWS_1.2.md`](REVIEWS_1.2.md) — an open log of architectural risks and questionable assumptions found during self-review, including ones found and partially fixed *because* of real-data testing. Worth reading if you want to know what's already known to be shaky.

Currently in **Phase 2** (global discovery engine + folder de-duplication). Phases 3 (OCR, interactive review) and 4 (one-command install, zero-config on a new machine) are not started.

## License

GPLv3 — see [`LICENSE`](LICENSE). You're free to use, study, modify, and redistribute this, including modified versions, as long as those stay under the same license.
