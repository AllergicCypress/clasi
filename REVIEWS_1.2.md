# REVIEWS

## Purpose

This document collects weaknesses, architectural risks, and questionable assumptions found during design reviews of `clasi`.

Its goal is not to propose final implementations, but to identify points where the architecture might misbehave when faced with users, directory structures, or organizational habits different from the ones used during the initial design.

The reviews recorded here should be considered open until a solution has been validated through real-world testing.

---

# REV-001 — Folder semantics don't always exist

## Severity

**CRITICAL**

## Status

**Partially resolved** (implemented in the 2026-06-20 session, see `PROJECT.md` § Architecture review — 2026-06-20)

### Implementation summary

A categorization stage (`_categoria_carpeta` in `discovery.py`) was added that runs before building the index. Each candidate folder is evaluated as follows:

1. Structural name (`unidad1`, `actividad5.3`…) → always **thematic**, regardless of depth or content. There, the file matches by name, not by topic — requiring homogeneity would unfairly penalize it (this was discovered and fixed during implementation: see point 2 below).
2. Name on the blocklist (`config/carpetas_genericas.yaml`, e.g. `Universidad`, `Documentos`, `Trabajo`, `Varios`) → **container**, excluded from the index.
3. If neither of the above applies and the folder is ≤ 2 levels from the scanned root (`MAX_PROFUNDIDAD_HOMOGENEIDAD`): content homogeneity is measured (average Jaccard between sampled files, minimum 3 samples). Below `UMBRAL_HOMOGENEIDAD = 0.15` → **container**.
4. Otherwise → **thematic**.

**Validation:** audited against a real `~/Documents` (not synthetic). The first version applied the homogeneity test without distinguishing depth and produced serious false positives: `ACTIVIDAD 5.3`, `PAPC1.3`, `2.2`, `EU4` — correct destinations already validated in previous tests — fell below the threshold. This was fixed by bounding the test to shallow folders (point 3). After the fix, `clasi sim ~/Documents` reproduces exactly the previously documented results (7 files with a destination / 12 without, same scores 0.70–0.79) and additionally correctly excludes `THE DEEP` (a real folder with heterogeneous personal notes, not on the blocklist).

### Why "partially" and not "resolved"

- Both thresholds (`UMBRAL_HOMOGENEIDAD`, `MAX_PROFUNDIDAD_HOMOGENEIDAD`) are calibrated against a single real user structure. They still need to be validated against other users'/teams' structures before being considered stable (relevant to the project's universality goal).
- The `carpetas_genericas.yaml` blocklist is static, in common Spanish/English; its real coverage hasn't been tested because none of the listed names currently exist in this user's `~/Documents` (all container detection observed so far comes from homogeneity, not the blocklist).
- There's no documented manual override yet (open question 4 below remains unresolved).

## Open questions — updated

1. ~~How do you objectively measure whether a folder is thematic?~~ → Resolved for v1: content homogeneity (Jaccard) bounded by depth, plus a name blocklist.
2. ~~What homogeneity threshold should be required?~~ → `0.15`, provisional, calibrated against a single real case.
3. Can a folder change category over time? → Resolved by design: the index is rebuilt on every run, so the category is always re-evaluated against the current state.
4. Should there be manual intervention to correct classifications? → Still open. Today the only possible override is editing `carpetas_genericas.yaml` by hand.
5. Is a heuristic enough, or is a statistical model required? → A heuristic is enough for now; no evidence that more is needed.

## Problem description

The project's core principle states:

> The existing folder structure is the configuration.

The current architecture assumes that existing folders represent useful topics or semantic categories.

Valid examples:

- Numerical Methods
- Programming
- Astronomy
- Russian

In these cases the folder has:

- a descriptive name
- consistent content
- a clear thematic identity

So it can be incorporated into the system's semantic index.

## The hidden assumption

Currently it is assumed that:

existing folder → valid topic

But this relationship isn't always true.

Many users organize information using generic, structural, or transient folders:

- University
- Work
- Documents
- Important
- Pending
- PDFs
- Misc

These folders don't represent topics. They represent containers.

## Architectural risk

This problem introduces a progressive degradation phenomenon:

1. A generic folder enters the index.
2. New files get sent to it.
3. Its content becomes even more heterogeneous.
4. The index learns incorrect information.
5. The folder attracts even more files.
6. Accuracy decreases with every run.

## Proposed reformulation

The statement:

> Existing folders are the configuration.

should be reformulated as:

> Only folders that prove to be thematic are part of the configuration.

## Solution hypothesis

Introduce a stage prior to semantic discovery:

Scan → Folder classification → Semantic discovery → File classification

### Proposed categories

#### Thematic folder

Represents a knowledge area or content domain.

Examples:

- Numerical Methods
- Astronomy
- Programming
- History

Can be used as a destination and be part of the index.

#### Container folder

Represents an organizational grouping.

Examples:

- University
- Work
- Personal
- Documents

Should not be used as a semantic destination.

#### Structural folder

Represents repetitive internal organization.

Examples:

- Unit 1
- Unit 2
- Exams
- Screenshots
- Assignments

> **Correction after implementation (2026-06-20):** the original idea of excluding these from the index turned out to be wrong. Folders like `Unit 5/ACTIVITY 5.3` were already validated as correct destinations in earlier real tests (the file matches by exact name, not by topic). Excluding them broke that behavior. They remain in the index just like before; the structural pattern is only used to avoid reporting them as "duplicates" across courses — see "Implementation summary" above.

(Open questions moved above, next to the implementation summary.)

---

# REV-002 — Excessive reliance on simple TF-IDF

## Severity

High

## Status

Open

### Problem

TF-IDF works well when topics have distinctive vocabulary, but can fail when two domains share a large part of their vocabulary.

### Possible lines of investigation

- Local embeddings
- Sentence Transformers
- TF-IDF + embeddings combination
- Hybrid scoring

---

# REV-003 — No learning from user corrections

## Severity

Medium

## Status

Open

### Problem

The system currently classifies files but doesn't learn from errors the user detects.

### Possible lines of investigation

- Correction history
- Weight adjustment
- Local decision memory
- Incremental feedback system

---

# REV-004 — The global index collapses same-named structural folders across different subjects

## Severity

High

## Status

Open — found via `clasi evaluate`, design not started

### Problem

`construir_indice()` keys its index by normalized folder name alone. When the *same* structural name (`UNIT 1`, `EXAM`, `TAREA 3.1`...) appears under more than one unrelated subject — e.g. `Numerical Methods/UNIT 1` and `Differential Equations/UNIT1/1.1` — only **one** canonical entry survives (chosen by the existing location-priority rule), and the other becomes invisible as a destination. A loose file that actually belongs to the *losing* subject's `UNIT 1` gets scored against the *winning* subject's `UNIT 1` instead, since the index has no notion of "which subject this structural folder belongs to."

This was already noted as a known limitation during the REV-001 work (2026-06-20 session) and deliberately left out of scope. `clasi evaluate` (added 2026-06-21) turned it from a theoretical concern into the dominant measured error source: most "incorrect" holdout cases after fixing the tokenization bug (see `PROJECT.md` §17-19) are exactly this — cross-subject collisions, not name-matching defects.

### Why it's hard

A genuinely loose file (sitting outside any folder) carries no explicit "which subject tree" signal beyond its own name/content. If that content is generic (a short homework file, a cover page), there may be no reliable way to disambiguate `UNIT 1` in subject A from `UNIT 1` in subject B without more context than the file itself provides — this isn't purely an implementation bug, part of it is an inherent information limit.

### Possible lines of investigation

- Scope structural-folder index keys by their nearest non-structural/thematic ancestor (e.g. index `"numericalmethods/unidad1"` and `"ecuacionesdiferenciales/unidad1"` separately) instead of by bare normalized name.
- When scoring a loose file, weight matches by how strongly the file's content also matches the *ancestor* subject folder, not just the structural leaf.
- Accept this as a known limitation for now and surface it explicitly in `sim`/`evaluate` output (e.g. flag low-confidence matches into generically-named structural folders differently from matches into uniquely-named ones).

---

# Priority summary

| ID | Severity | Priority |
|----|----------|----------|
| REV-001 | Critical | 1 |
| REV-004 | High | 2 |
| REV-002 | High | 3 |
| REV-003 | Medium | 4 |

REV-001 should be considered the main architectural risk identified so far, with REV-004 a close second now that it has measured evidence behind it.

