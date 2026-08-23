---
name: pdf-to-markdown
description: Convert an academic PDF or supported office document into structured Markdown with equations, tables, and extracted figures. Use when Codex needs machine-readable structure and no matching TeX source is available or PDF extraction remains useful; do not replace visual PDF verification.
metadata:
  stage_model: gpt-5.6-terra
  stage_reasoning_effort: medium
---

# PDF to Markdown

Convert a user-supplied file with the bundled `convert.py`. Keep the source file unchanged. In an arXiv workflow, prefer matching TeX source for formulas, tables, and original figures; use Markdown as a structured aid rather than the sole paper representation.

## Required model route

Run this stage in exactly one model-routed worker. If the current delegated
prompt contains `PAPER_TO_VIDEO_STAGE_WORKER=terra:gpt-5.6-terra:medium`,
execute the Skill directly and do not delegate again. Otherwise, before doing
stage work, spawn one subagent with model `gpt-5.6-terra` and reasoning effort
`medium`. In its prompt, require this Skill, include the marker above, and carry
forward the input paths, user requirements, and current authorization
boundaries. Wait for that worker and return its result; the parent may verify
the handoff but must not redo the stage. If the exact worker profile cannot
start, stop and report that routing failure instead of silently inheriting or
falling back to the parent model.

## Workflow

1. Resolve the input and output paths to absolute paths inside the current workspace.
2. Use the official PDF skill first to inspect page count, selectable text, figures, and visual quality.
3. Check the local runtime:

   ```bash
   command -v uv
   python --version
   python -c "import mineru"
   ```

4. If MinerU is unavailable, either use an existing project environment or ask before installing the large MinerU/GPU dependency set. Do not modify the system Python.
5. Run the converter from this skill directory:

   ```bash
   python "$SKILL_DIR/convert.py" INPUT_PATH OUTPUT_DIR --lang ch --backend pipeline --method auto
   ```

   `--lang ch` supports mixed Chinese and English. Use `--lang en` for English-only papers when OCR quality benefits.
6. Locate the generated Markdown under `OUTPUT_DIR/<stem>/auto/` (MinerU versions may use a nearby method directory).
7. Verify that the Markdown contains the title, section headings, representative equations, figure references, tables, and references. Compare at least two equation-heavy or figure-heavy PDF pages against the extraction.

## Output contract

Report the Markdown path, extracted image directory, parser/backend, and any missing or malformed material. Never claim extraction fidelity without checking the source PDF visually.
