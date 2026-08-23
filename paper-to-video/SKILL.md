---
name: paper-to-video
description: Turn completed SUSTech Beamer decks into page-aligned narrated local videos with one resumable IndexTTS2 batch pipeline. Does not upload.
---

# Paper to Video

Build a verified local MP4 from a completed, visually reviewed Beamer deck.
Uploading is owned by `bilibili-video-uploader` and is never triggered here.

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

The command has one purpose: render slides, align narration, run one shared
IndexTTS2 worker, assemble videos, and verify page/audio coverage plus media
streams. It has no slides, upload, publication, status, or finalization mode.

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
