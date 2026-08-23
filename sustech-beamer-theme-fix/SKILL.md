---
name: sustech-beamer-theme-fix
description: Diagnose and repair SUSTech Beamer theme integration, missing macros, asset paths, and compilation failures. Use when a SUSTech-themed Beamer deck fails to compile or renders incorrectly in Codex Desktop, WSL, Linux, or Windows.
metadata:
  stage_model: gpt-5.6-terra
  stage_reasoning_effort: medium
  beamer_quality_model: gpt-5.6-sol
  beamer_quality_reasoning_effort: medium
---

# Fix the SUSTech Beamer Theme

## Required model route

Start this Skill in one `gpt-5.6-terra` worker with reasoning effort `medium`.
If the current delegated prompt contains
`PAPER_TO_VIDEO_STAGE_WORKER=terra:gpt-5.6-terra:medium`, diagnose and repair
mechanical theme, path, macro, font, compiler, and rendering failures directly.
Otherwise, spawn that Terra worker first and wait for it.

Escalate only the content-quality part to one `gpt-5.6-sol` medium worker with
`PAPER_TO_VIDEO_STAGE_WORKER=beamer:gpt-5.6-sol:medium` when the repair requires
changing scientific content, narrative structure, slide text, equations,
figures, information density, or content-related layout, or when it requires a
fresh narration-hidden quality judgment. The Sol worker must not redo purely
mechanical diagnosis. If an exact required profile cannot start, stop and report
the routing failure instead of silently inheriting or falling back to the
parent model.

1. Work only in the requested deck directory and preserve unrelated user edits.
2. Use `latex:latex-doctor` to discover the available TeX runtime; prefer XeLaTeX for Chinese Beamer.
3. Confirm that `main.tex`, `latexmkrc`, and `sustech-theme/` are colocated and that `TEXINPUTS` in `latexmkrc` includes the local theme directory.
4. Compare used macros with `beamerthemesustech-elements.sty`. Repair the smallest compatible surface; do not replace the entire theme unless requested.
5. Compile with `latexmk -xelatex main.tex` from the deck directory.
6. Inspect the log for missing files, undefined controls, font errors, and overfull boxes.
7. Render the resulting PDF and visually inspect title, section, content, figure, reference, Q&A, and appendix frames.
8. Report the root cause, files changed, compiler used, final page count, and remaining warnings.

Do not introduce machine-specific absolute paths or silently substitute fonts in committed source.
