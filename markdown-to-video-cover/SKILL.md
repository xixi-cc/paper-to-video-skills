---
name: markdown-to-video-cover
description: Create a separate 16:10 academic promotional poster from MinerU Markdown, extracted paper figures, and optional user overrides. Use when Codex needs a poster artifact alongside a paper presentation or narrated video; the Beamer title page remains the video cover.
---

# Markdown to Video Cover

Create poster assets under `<paper-dir>/poster/` without changing the paper, Markdown, or slides.
Treat this as a promotional poster only. Never copy it to `video/cover.png` or
use it in place of the rendered Beamer title page.

## Inputs

- `<paper-dir>/md_output/*/auto/*.md`
- extracted images beside the Markdown
- optional JSON overrides containing card text, selected figures, and `title_font`

## Workflow

1. Use the official PDF skill to inspect the paper title page and candidate
   figures before selecting promotional-poster content.
2. Resolve this skill directory from the current `SKILL.md`; do not assume a global installation path.
3. Confirm `lualatex`, `pdftoppm`, and `ffmpeg` are on `PATH`. Use `latex:latex-doctor` when TeX discovery fails.
4. Run:

   ```bash
   python "$SKILL_DIR/scripts/generate_poster.py" PAPER_DIR
   ```

   Add `--data overrides.json`, `--title-font N`, or `--no-png` when required.
5. Keep the title, venue/year, method, and key result faithful to the paper. Prefer one or two legible figures over a dense collage.
6. Compile `poster.tex`, render `poster.pdf` to `poster.png`, and inspect the full-size image for cropping, unreadable labels, missing glyphs, and weak contrast.

## Output contract

Return `poster/poster.tex`, `poster/poster.pdf`, and `poster/poster.png`. State selected figures and any manual overrides. Do not reuse a low-resolution poster as the slide deck itself.
