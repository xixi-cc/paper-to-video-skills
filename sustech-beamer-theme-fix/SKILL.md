---
name: sustech-beamer-theme-fix
description: Diagnose and repair SUSTech Beamer theme integration, missing macros, asset paths, and compilation failures. Use when a SUSTech-themed Beamer deck fails to compile or renders incorrectly in Codex Desktop, WSL, Linux, or Windows.
---

# Fix the SUSTech Beamer Theme

1. Work only in the requested deck directory and preserve unrelated user edits.
2. Use `latex:latex-doctor` to discover the available TeX runtime; prefer XeLaTeX for Chinese Beamer.
3. Confirm that `main.tex`, `latexmkrc`, and `sustech-theme/` are colocated and that `TEXINPUTS` in `latexmkrc` includes the local theme directory.
4. Compare used macros with `beamerthemesustech-elements.sty`. Repair the smallest compatible surface; do not replace the entire theme unless requested.
5. Compile with `latexmk -xelatex main.tex` from the deck directory.
6. Inspect the log for missing files, undefined controls, font errors, and overfull boxes.
7. Render the resulting PDF and visually inspect title, section, content, figure, reference, Q&A, and appendix frames.
8. Report the root cause, files changed, compiler used, final page count, and remaining warnings.

Do not introduce machine-specific absolute paths or silently substitute fonts in committed source.
