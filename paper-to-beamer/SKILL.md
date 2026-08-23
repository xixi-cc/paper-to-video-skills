---
name: paper-to-beamer
description: Turn an academic paper into a compiled, visually reviewed SUSTech Beamer deck with source-linked claims and faithful equations and figures.
metadata:
  stage_model: gpt-5.6-sol
  stage_reasoning_effort: medium
---

# Paper to Beamer

Create Beamer as the editable deliverable. Narration, video, and publication
metadata are outside this Skill.

## Required model route

Run this stage in exactly one model-routed worker. If the current delegated
prompt contains `PAPER_TO_VIDEO_STAGE_WORKER=beamer:gpt-5.6-sol:medium`,
execute the Skill directly and do not delegate again. Otherwise, before doing
paper analysis or editing files, spawn one subagent with model `gpt-5.6-sol`
and reasoning effort `medium`. In its prompt, require this Skill, include the
marker above, and carry forward the paper paths, user requirements, and current
authorization boundaries. Wait for that worker and return its result; the
parent may verify the handoff but must not redo Beamer authorship. If the exact
worker profile cannot start, stop and report that routing failure instead of
silently inheriting or falling back to the parent model.

## Read the paper

1. For an arXiv URL or ID, invoke `paper-download-arxiv-source` and read its
   source contract. For a local PDF, preserve the original file.
2. Inspect the complete rendered PDF. The PDF is the visual authority; use
   matching TeX first for equations, tables, captions, references, and original
   figure assets. Use `pdf-to-markdown` only when it adds useful structure.
3. Read [`references/content-writing-guide.md`](references/content-writing-guide.md)
   and map each planned claim to a paper page, figure, equation, table,
   reference, URL, or exact TeX location.

## Build the deck

1. Copy `main_template.tex`, `latexmkrc`, and `sustech-theme/` from the sibling
   `sustech-slides-template` into `<paper-root>/slides-beamer/`; copy the template
   to `main.tex`.
2. Create `<paper-root>/paper_presentation.json` using
   [`references/manifest-format.md`](references/manifest-format.md). It contains
   paper metadata, source provenance, frames, and evidence only.
3. Validate and render it:

   ```bash
   python ../paper-to-video/scripts/presentation_manifest.py validate "$PAPER_ROOT"
   python ../paper-to-video/scripts/presentation_manifest.py render "$PAPER_ROOT"
   ```

4. Use `aspectratio=1610` and `\usetheme{sustech}`. The first manifest frame is
   the title page and later becomes the video cover.
5. For dedicated paper figures, equation derivations, and baseline comparisons,
   read [`references/semantic-frame-macros.md`](references/semantic-frame-macros.md).

Choose page count and structure from the paper and the user's requested talk.
Do not add an equation, figure, section, or extra narration to satisfy a quota.

## Compile and review

Compile with XeLaTeX, inspect the log, render every PDF page, and review the deck
without narration. Correct clipping, unreadable figures or equations, unsupported
claims, missing inference steps, repetition, and sparse pages whose local argument
is incomplete. Reopen the cited paper evidence before strengthening a claim.

The finished deck must be understandable on screen: each substantive frame shows
its object or condition, supporting mechanism or evidence, and the conclusion that
follows. This is a writing requirement, not a fixed page or bullet count.

Return `paper_presentation.json`, `slides-beamer/main.tex`, the compiled PDF,
figures, and a concise report of inspected pages and unresolved warnings.
