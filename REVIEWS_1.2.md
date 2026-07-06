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

# REV-004 — Folder semantics are hierarchical, not local

## Severity

High

## Status

**Resolved (2026-07-05).** Implemented via `tokens_ancestros` in `discovery.py`/`evaluator.py`. Metrics held (correcto 15%, incorrecto 9%); 3 files now routed via `contexto` method. OCR additionally exposed two previously "validated" cases (`Calculo de varias variables 1.2.pdf`, `Calculo Vectorial 1.2.pdf`) as false positives — they scored 0.72 against `Ecuaciones Diferenciales/` only because `pdftotext` returned garbled bytes and the stem's `"1.2"` was the only token. With OCR providing real content ("Vectores y espacio tridimensional"), score dropped to 0.21 → `sin_destino`, which is correct. The user confirmed those files belonged to a Cálculo Vectorial folder that no longer exists.

### Problem

The current discovery model treats every indexed folder as an independent thematic destination. This assumption is false: a folder's semantic meaning is often defined by its ancestors, not by its own name alone.

The original framing focused on index collapsing — same structural names (`UNIT 1`, `EXAM`) from different subjects merging into a single canonical entry. Rejected attempt #1 (below) disproved this as the dominant failure mode. The actual mechanism is different: a short, purely-numeric folder name (e.g. `"1.2"`) has `tokens_nombre = {"1.2"}` — a single token. Any file with `"1.2"` anywhere in its stem produces a 100% name match with score ~0.72, regardless of subject. The contextual information that would disambiguate — `Ecuaciones Diferenciales` vs `Metodos Numericos` — exists in the folder's ancestor path but is never used by the scorer.

The root model is:

```
folder → keywords
```

Reality is closer to:

```
folder + parent + grandparent + existing path → semantic destination
```

`clasi evaluate` (2026-06-21) made this concrete: most "incorrect" holdout cases are cross-subject collisions where a loosely-named structural leaf folder (like `1.2`) attracts files from the wrong subject via a coincidental single-token stem match.

### Why it's hard

Two failure modes share the same evidence:

- **Variant A** — file with no useful content (blank cover page, generic template): there is no signal to distinguish `MN/.../1.2` from `ED/.../1.2`. `sin_destino` is the correct answer; no classification model can do better without inventing information.
- **Variant B** — file with relevant content (homework text that mentions the subject): the information exists, but the scorer never reaches it because the numeric name match wins at 0.72 before content scoring matters.

Both variants look identical to the scorer. The fix must handle them differently: variant A → `sin_destino` (no penalty; acceptable), variant B → correct routing (the content should win).

### Possible lines of investigation

- ~~Scope structural-folder index keys by their nearest non-structural/thematic ancestor...~~ Tried 2026-06-22, see "Rejected attempt #1" below — doesn't address the dominant failure mode.
- ~~Penalize purely-numeric `tokens_nombre` matches unless corroborated by ancestor name tokens (`tokens_ancla`)...~~ Tried 2026-06-22, see "Rejected attempt #2" below — correct idea, but blocked by garbled PDF extraction. **Unblocked since Phase 3 OCR implementation.**
- **[Current direction]** Add `tokens_ancestros` to each `EntradaCarpeta` at index-build time (union of `tokens_nombre` from all ancestor folders up to the scanned root). In `puntuar()`, for purely-numeric local names, suppress `score_nombre` and use `score_ancestros` as primary signal. For other folders, add `score_ancestros` as a small supplementary term. See "Proposed direction" below.
- Accept as a known limit and surface in `sim`/`evaluate` output (flag low-confidence matches into generically-named structural folders differently).

### Rejected attempt — anchor-scoped index keys (2026-06-22)

Implemented the first line of investigation above: for any folder classified "temática" by name-pattern or by depth (not by genuine content homogeneity), the index key became `f"{ancla}/{nombre_norm}"` instead of bare `nombre_norm`, where `ancla` is the nearest ancestor folder that *is* a genuine content-verified topic. Goal: stop two subjects' identically-named structural folders (`UNIT 1`/`UNIT 1`) from collapsing into one canonical index entry that hides the other.

Verified zero regression on the calibrated `~/Documents` baseline (byte-identical `clasi sim` output). But `clasi evaluate ~` showed no net improvement — `incorrecto` count moved from 5 to 7 across two runs (different holdout draws, not a clean paired comparison, but directionally not an improvement either).

Direct inspection of the actual incorrect cases (real paths, not the anonymized hashes from the report) showed why: **the dominant failure mode isn't index collapsing at all.** Folders like `Ecuaciones Diferenciales/UNIDAD1/1.2` and `Metodos Numericos/UNIDAD 1` never shared a bare normalized name in the first place (`"12"` vs `"unidad1"` — already distinct index entries before this attempt). The actual mechanism: a short, purely-numeric folder name (e.g. `"1.2"`, `"PAPC1.2"`) has its *entire* `tokens_nombre` set satisfied by a single matching token in *any* file's stem, anywhere in the tree, regardless of subject — producing a coincidental 0.7–0.97 "nombre" score with no connection to the actual topic. Scoping the index key by ancestor does nothing here, because the colliding entries were never merged to begin with; the bug is in `puntuar()`'s scoring, not in `construir_indice()`'s keying.

Reverted (`src/discovery.py` restored to pre-attempt state). The fix needs to happen in the scorer, not the index: something like requiring a minimum number of matching tokens (not just "the whole tokens_nombre set, which may be size 1") before granting a high "nombre" score, or requiring the file to also sit somewhere under the same subject tree (proximity-aware scoring) before a bare numeric match counts at full weight. Not attempted yet — needs its own calibration pass against `~/Documents` to avoid regressing the validated `ACTIVIDAD 5.3`-style exact-name matches, which rely on the same "small token set, full match" mechanism for legitimate cases.

### Rejected attempt #2 — scorer-side penalty for purely-numeric folder names (2026-06-22, same session)

Moved the fix into `puntuar()` as the first attempt's postmortem suggested. Two variants tried, both reverted:

**Variant A — penalize a purely-numeric `tokens_nombre` match (e.g. `{"1.2"}`) unless the folder's own sampled content overlaps the file's tokens.** Zero effect on the real failing cases: direct inspection showed `hits_contenido` was almost never exactly 0, because every folder's content sample is dominated by a shared administrative cover-page template (institute name, professor, student name, "asignatura", "grupo", "semestre") that floods `tokens_contenido` for every subject alike — confirmed by printing the actual token set for the offending `Ecuaciones Diferenciales/.../1.2` entry: it contained `"metodos"`, `"numericos"` even though the folder itself is filed under a different subject. Generic content overlap is not a meaningful corroboration signal for this user's documents.

**Variant B — same penalty, but require overlap specifically with the tokens of the nearest non-structural ancestor folder's name (`tokens_ancla`, e.g. `{"ecuaciones", "diferenciales"}`) instead of the whole content sample.** This follows directly from the user's clarification that assignment cover pages *do* state the subject name even though they share the rest of the template. Implemented `_ancla_tematica()` + a `tokens_ancla` field on `EntradaCarpeta`, populated at index-build time and reused by `evaluator.py`.

This is conceptually the right idea, but broke a real validated case on the `~/Documents` baseline: `Calculo de varias variables 1.2.pdf` (and its sibling `Calculo Vectorial 1.2.pdf`), previously correctly matched (score 0.72) by the literal "1.2" in its stem against `Ecuaciones Diferenciales/.../UNIDAD1/1.2`. Direct inspection of `extraer_texto()`'s output for this PDF showed garbled, non-text byte soup (`'îïðñòòóîîïôîõö÷øùùùúûüýÿÿõÿ0ïï...'`) — the extractor is failing on this file (broken encoding or a scanned page with no real text layer), so the subject name is not recoverable from content, and the stem itself (`"Calculo de varias variables 1.2"`) doesn't mention the subject either. There is no signal anywhere in what `clasi` can read from this file to distinguish it from a genuine cross-subject collision — confirming the REVIEWS_1.2.md "inherent information limit" framing isn't just theoretical caution, it's the literal blocker on a real, previously-validated case.

Reverted both variants entirely (`discovery.py` and `evaluator.py` back to pre-session state, diff identical to the #21/#22 baseline). **Conclusion: incremental scorer penalties keep trading one error type for the other** (cross-subject false positive vs. false negative on a file with no extractable subject signal) without a net win, because the two failure modes draw on the exact same starved evidence (a single short numeric token, nothing else). Don't re-attempt a blanket per-token-pattern penalty without first improving something orthogonal — e.g. OCR fallback for garbled-extraction PDFs (so the subject signal becomes recoverable at all), or accepting the "surface it as low-confidence in the UI" line of investigation instead of trying to silently auto-resolve it.

### Why the blocker is now removed (2026-06-25)

Variant B was blocked by `Calculo de varias variables 1.2.pdf` — a garbled PDF whose extractor returned byte soup, making subject name recovery impossible from content alone. Phase 3 OCR (Tesseract fallback in `extractor.py`) now recovers readable text from scanned and encoding-broken PDFs. Direct verification: `clasi sim ~/Documents` shows that file now classified correctly via content. The specific evidence cited as "inherent information limit" in the rejected attempt #2 writeup no longer applies.

The same file that broke variant B is now an argument in favor of the proposed direction: OCR gives it text → ancestor context can check whether that text mentions the correct subject → disambiguation becomes possible for variant B cases.

---

### Proposed direction — hierarchy-aware scoring via `tokens_ancestros` (2026-06-25)

**Paradigm change:** the existing folder structure is still the configuration, but the configuration is not the individual folders — it is the hierarchy they form. The classifier should learn *contexts* rather than isolated folder names.

**Implementation sketch (flat index preserved; no tree restructure required):**

1. **`EntradaCarpeta` gains a new field:** `tokens_ancestros: set[str]` — union of `tokenizar(nombre)` for every ancestor folder between the entry and the scanned root. Populated in `construir_indice()` as folders are indexed, walking `ruta.parents` up to `directorio`.

2. **`puntuar()` gains two paths:**

   - **Purely-numeric local name** (`tokens_nombre` has no non-numeric tokens, e.g. `{"1.2"}`, `{"2.2"}`): `score_nombre = 0` (coincidental match suppressed). Ancestor context becomes the primary signal:
     ```
     score = score_ancestros * 0.60 + score_contenido * 0.40
     ```
     A file about Métodos Numéricos scores well against `MN/.../1.2` (ancestors match) but near-zero against `ED/.../1.2` (ancestors don't match). A file with no content scores 0 for both → `sin_destino`.

   - **Non-numeric local name** (`ACTIVIDAD 5.3`, `UNIDAD 1`, `Ecuaciones Diferenciales`): existing scoring preserved. Ancestor context added as a small supplementary term to avoid disrupting calibrated baselines:
     ```
     score = score_nombre * 0.60 + score_ancestros * 0.10 + score_contenido * 0.30
     ```

**Expected behavior by case:**

| Case | Before | After |
|---|---|---|
| Blank `1.1.pdf` vs wrong subject's `1.1` | incorrecto | sin_destino |
| `1.1.pdf` with MN content vs `MN/.../1.1` | incorrecto (loses to ED) | **correcto** |
| Blank `1.1.pdf` vs correct `MN/.../1.1` | sometimes correcto (coincidental) | sin_destino |
| `ACTIVIDAD 5.3.xlsx` → `MN/UNIDAD5/ACTIVIDAD 5.3` | correcto (0.78) | correcto (unchanged) |
| `zill-d.g.-ecuaciones-diferenciales.pdf` → `ED` | correcto (0.70) | correcto (unchanged) |

The third row represents a genuine information limit (blank file, no signal): it was previously "correct" by coincidence. Converting it to `sin_destino` is more honest. The second row is where the real gain comes from: variant-B incorrectos become correctos.

**Tradeoffs:**

- Purely-numeric folders can no longer be reached without either content or ancestor context. Files with no readable content and a numeric name will always be `sin_destino` for these folders.
- Changing one ancestor folder's name requires rebuilding the affected descendants' `tokens_ancestros` on the next run — this happens automatically since the index is rebuilt every time.
- The `0.60 / 0.40` and `0.60 / 0.10 / 0.30` weight splits are initial estimates; calibration against `clasi evaluate` after implementation will determine whether they need adjustment.

**Open questions:**

- Should ancestor inheritance decay with depth? (grandparent contributes less than parent)
- Should container folders (blocklisted in `carpetas_genericas.yaml`) be skipped during ancestor collection, or kept?
- Should `tokens_ancestros` include content tokens from ancestor folders, or only name tokens? (name tokens are cleaner and more reliable)

### Implementation outcome (2026-07-05)

Implemented the proposed direction exactly, with two deviations from the sketch:

1. **Non-numeric path (B):** ancestor bonus omitted. The proposed `0.60/0.10/0.30` split was not implemented — the original `0.70/0.30` weights were kept to avoid disturbing the calibrated baselines for alphabetic-name folders. The value of `tokens_ancestros` is limited to path A; adding it as a supplementary signal in path B carried regression risk without a measured upside.

2. **Purely-numeric path (A):** a floor of `+0.20` is added when `tokens_numericos & tokens_stem` is non-empty (i.e. the stem shares the number), rather than the flat `score_ancestros * 0.60 + score_contenido * 0.40` from the sketch. This preserves the intent (ancestor context as primary discriminator) while ensuring a blank file with the right number in its name still scores 0.40 (floor 0.20 + anything from ancestors/content) — right at the threshold, not silently dropped to zero. If neither ancestors nor content contribute, it scores exactly 0.20 < 0.40 → `sin_destino`.

3. **Ancestor token collection:** structural folders (matching `_PATRON_ESTRUCTURAL`: `unidad\d*`, `actividad\d*`, etc.) are excluded from `_tokens_de_ancestros()`. They repeat across every subject and add noise rather than disambiguation signal. Only thematic folder names (e.g. "Metodos Numericos") are collected.

**`clasi evaluate ~` results (2026-07-05, 53 holdout files):**

```
Correctos: 8 (15%)   Incorrectos: 5 (9%)   Sin destino: 40 (75%)
```

Same aggregate metrics as post-#22 baseline. The 3 `contexto`-method correctos were previously counted under another classification path (or borderline); no regressions introduced. All 5 remaining incorrectos route via `nombre`, none via `contexto` — confirming the new path adds no false positives.

The 5 remaining incorrectos are accepted as a known limit: 3 are xlsx files from the same folder with a generic name that collides with a different subject, 1 is a borderline alphabetic match, 1 is a parent→child same-topic edge case. None are addressable by further scorer changes without data to separate them.

---

# Priority summary

| ID | Severity | Status |
|----|----------|--------|
| REV-001 | Critical | Open |
| REV-002 | High | Open |
| REV-003 | Medium | Open |
| REV-004 | High | **Resolved 2026-07-05** |

REV-001 remains the main open architectural risk.

