---
name: Real-world test report
about: Share what happened when you ran `clasi sim` on your own folders
title: "[test] "
labels: testing
---

<!--
Thanks for testing! You do NOT need to share real file names, folder contents,
or anything sensitive — a description of the structure and what went wrong
is already useful. Screenshots with names blurred are great too.
-->

**Folder organization style** (one or two sentences)
e.g. "One folder per client, each with year subfolders inside" / "Everything loose in Downloads, no subfolders at all" / "Deeply nested by project > subproject > date"

**Command run**
```
clasi sim <directory> [any extra flags you used]
```

**What happened vs. what you expected**
- [ ] A file got a confident destination that's clearly wrong
- [ ] A file got no destination but obviously belongs in a folder you have
- [ ] A folder was flagged as "duplicate" but isn't (or a real duplicate was missed)
- [ ] Something else (describe below)

**Details**

<!-- Paste the relevant rows from the `sim` table, or a screenshot. Blur/replace
real file or folder names if you'd rather not share them, but keep the general
shape (extension, rough topic, depth) since that's what matters for debugging. -->

**Environment**
- OS:
- Python version:
- Roughly how many files/folders in the directory you tested:
