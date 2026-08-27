---
name: pdf-to-markdown
description: Convert an academic PDF or supported office document into structured Markdown with equations, tables, and extracted figures as the paper-to-Beamer intake stage; do not replace PDF or TeX verification.
metadata:
  stage_model: gpt-5.6-terra
  stage_reasoning_effort: medium
---

# PDF to Markdown

Convert a user-supplied file with the bundled `convert.py` before Beamer content
analysis. Keep the source file unchanged. Write paper-workflow outputs under
`<paper-root>/source/mineru/`. In an arXiv workflow, still prefer matching TeX
source for formulas, tables, and original figures; use Markdown as the initial
structured reading aid rather than the sole paper representation.

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
3. Choose the execution boundary before parsing:

   - Use `open-api` only when the user has authorized sending the document to
     the configured MinerU service. It provides precision extraction and rich
     assets without installing the local model stack.
   - Use `local` when the document must remain on the current machine. This is
     the converter's default so an omitted flag never causes a remote upload.

4. For the Open API route, check the CLI and token without displaying it:

   ```bash
   command -v mineru-open-api
   mineru-open-api version
   mineru-open-api auth --verify
   ```

   Run the converter with a dedicated per-paper output directory:

   ```bash
   python "$SKILL_DIR/convert.py" INPUT_PATH OUTPUT_DIR \
     --engine open-api --lang ch --api-model auto
   ```

   The CLI reads authentication from its private user config or
   `MINERU_TOKEN`; never pass a token in a prompt, tracked file, or logged
   command. The normal API output is `OUTPUT_DIR/<stem>.md` plus
   `OUTPUT_DIR/images/`.

5. For the local route, check the isolated runtime:

   ```bash
   command -v uv
   python --version
   python -c "import mineru"
   ```

6. If local MinerU is unavailable, either use an existing project environment
   or ask before installing the large MinerU/GPU dependency set. Do not modify
   the system Python and do not silently fall back to the hosted API.
7. Run the converter from this skill directory:

   ```bash
   python "$SKILL_DIR/convert.py" INPUT_PATH OUTPUT_DIR \
     --engine local --lang ch --backend pipeline --method auto
   ```

   `--lang ch` supports mixed Chinese and English. Use `--lang en` for English-only papers when OCR quality benefits.
8. Locate the generated Markdown at the path printed by the converter. Local
   MinerU normally writes under `OUTPUT_DIR/<stem>/auto/`; Open API normally
   writes `OUTPUT_DIR/<stem>.md` and `OUTPUT_DIR/images/`.
9. Verify that the Markdown contains the title, section headings, representative equations, figure references, tables, and references. Compare at least two equation-heavy or figure-heavy PDF pages against the extraction.

## Output contract

Report the Markdown path, extracted image directory, local/API engine,
parser/model, remote-upload boundary, and any missing or malformed material.
Never claim extraction fidelity without checking the source PDF visually.
