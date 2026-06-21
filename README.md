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

**Phase 2 of 4**

### Implemented

- Dynamic folder discovery
- Recursive indexing
- TF-IDF classification
- Dry-run mode (`sim`)
- Real execution (`run`)
- Undo support
- Folder duplicate detection
- Holdout evaluation (`evaluate`)

### In progress

- Folder merging (`merge`)
- Folder relocation (`move-folder`)
- Additional file formats

### Planned

- OCR
- Interactive review
- One-command installation

See [`PROJECT.md`](PROJECT.md) for the complete roadmap and architecture.

---

## Safety

`clasi` is designed to be conservative.

- `sim` never modifies the filesystem.
- Files are moved, never deleted.
- Every operation is logged.
- `undo` can revert the latest run.
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
- `pdftotext` (from Poppler)

### Arch Linux

```bash
sudo pacman -S python-click python-yaml python-rich poppler
```

### Debian / Ubuntu

```bash
sudo apt install python3-click python3-yaml python3-rich poppler-utils
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

Shows what would happen without modifying anything.

Example:

```bash
clasi sim ~/Downloads
```

---

### Execute

```bash
clasi run <directory>
```

Moves files and creates a reversible log.

Example:

```bash
clasi run ~/Downloads
```

---

### Undo

```bash
clasi undo
```

Reverts the most recent execution log.

---

### Evaluate

```bash
clasi evaluate <directory>
```

Measures accuracy using the user's existing organization as ground truth.

Example:

```bash
clasi evaluate ~/Documents
```

Reports are anonymized automatically.

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

Known weaknesses, architectural risks, and proposed solutions.

---

## License

GPLv3

See [`LICENSE`](LICENSE).
