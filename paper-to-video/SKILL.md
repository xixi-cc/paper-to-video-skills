---
name: paper-to-video
description: Turn completed SUSTech Beamer decks into page-aligned narrated local videos with one resumable IndexTTS2 batch pipeline. Does not upload.
metadata:
  stage_model: gpt-5.6-terra
  stage_reasoning_effort: medium
  beamer_quality_model: gpt-5.6-sol
  beamer_quality_reasoning_effort: medium
---

# Paper to Video

Build a verified local MP4 from a completed, visually reviewed Beamer deck.
Uploading is owned by `bilibili-video-uploader` and is never triggered here.

## Required staged model route

The default worker for this Skill is `gpt-5.6-terra` with reasoning effort
`medium`. If the current prompt contains
`PAPER_TO_VIDEO_STAGE_WORKER=video:gpt-5.6-terra:medium`, execute directly and
do not delegate again.

Before spawning the video worker, inspect the Beamer quality gate. It is current
only when `paper_presentation.json`, `main.tex`, and `main.pdf` exist, the
reviewed PDF hash still matches the current PDF, and no unresolved content or
content-related layout defect is recorded. A Sol review completed in the
current workflow for that exact PDF hash also satisfies the gate.

- If the gate is current, spawn only the Terra video worker. Deterministic
  manifest replay, compilation of unchanged content, page rendering, narration,
  TTS, media assembly, and video QA remain in Terra.
- If the gate is absent, stale, or fails, first spawn one `gpt-5.6-sol`
  subagent with reasoning effort `medium`. Require `paper-to-beamer`, include
  `PAPER_TO_VIDEO_STAGE_WORKER=beamer:gpt-5.6-sol:medium`, and scope it to the
  Beamer content-quality work needed: scientific accuracy, narrative structure,
  slide text, equations, figures, information density, content-related layout,
  and narration-hidden cold-read review. After the exact resulting PDF passes,
  spawn the Terra video worker.
- If Terra later discovers a needed content or content-related layout change,
  stop before TTS and return that work to a fresh Sol quality pass. Mechanical
  TeX, path, font, macro, rendering, or cache failures stay in Terra unless
  resolving them requires a content-quality decision.

Carry paper paths, hashes, review evidence, user requirements, and authorization
boundaries into each worker. If an exact required profile cannot start, stop and
report the routing failure instead of inheriting or falling back to the parent
model.

## Inputs

Each paper directory contains:

- `paper_presentation.json` and `slides-beamer/main.tex` from `paper-to-beamer`;
- `video/narrations.json`, a JSON object whose exact keys are `slide_001`,
  `slide_002`, and so on for every rendered PDF page;
- optional TTS configuration at the documented user config path.

Write narration after the final Beamer render so automatic section pages are
included. Every value must be a nonempty string. There is no fixed character or
duration quota; match the requested explanation and keep every rendered page
covered.

## Run

For one or more papers, create `papers.json` with `dir_path` or `paper_dir` for
each entry, then run:

```bash
VIDEO_SKILL="$SKILL_DIR/../pdf-slides-to-video"
"$VIDEO_SKILL/.venv/bin/python" "$SKILL_DIR/scripts/batch.py" papers.json \
  --cpu-workers 4 --latex-workers 2 --post-workers 2 --ffmpeg-workers 6
```

The command deterministically replays the approved manifest, compiles and
renders slides, aligns narration, runs one shared IndexTTS2 worker, assembles
videos, and verifies page/audio coverage plus media streams. It does not author
or revise slide content and has no upload, publication, status, or finalization
mode.

## State and review

`video/pipeline-state.json` is the only local QA/state record. It stores artifact
hashes, stage completion, page coverage, pronunciation and audio checks, FFprobe
results, and the current slide/video review fields. A changed PDF or MP4 clears
the corresponding review flag.

After assembly, sample the opening, an equation or method page, a figure or
result page, a transition, and the ending. Record `sampled: true` and any defects
in the existing `video` object; do not create another QA receipt.

Keep page-level TTS and video caches when their content hashes match. Report the
page count, generated and cached audio, video duration, codecs, resolution,
audio measurements, and any failed paper. Do not claim or perform publication.

Final artifact cleanup remains a separate explicit maintenance command described
in [`references/artifact-retention.md`](references/artifact-retention.md).
