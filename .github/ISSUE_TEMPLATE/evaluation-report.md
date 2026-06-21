---
name: Evaluation report (clasi evaluate)
about: Paste the output of `clasi evaluate` — already anonymized, nothing to redact
title: "[evaluate] "
labels: testing, evaluate
---

<!--
Run: python3 src/cli.py evaluate <directory> --seed 1
Then paste the summary line + table below, or the contents of the
logs/evaluacion_*.md file it generates. Every name is already a short
hash — there is nothing identifying in this output.
-->

**Command run**
```
clasi evaluate <directory> [any extra flags you used]
```

**Summary**
```
Correct: __%   Incorrect: __%   No destination: __%
```

**Full table / report**

<!-- paste here -->

**Folder organization style** (one sentence, optional but helpful)
e.g. "One folder per client, each with year subfolders" / "Deeply nested by project > subproject > date"

**Environment**
- OS:
- Python version:
- Roughly how many folders/files in the directory you evaluated:
