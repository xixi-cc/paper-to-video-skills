---
name: pdf-to-bilibili
description: Orchestrate a local academic-paper workflow from PDF through Markdown, SUSTech Beamer, narrated MP4, cover, and optional Bilibili upload. Use when Codex must run several stages as one reproducible pipeline while preserving review gates.
---

# PDF to Beamer, Video, and Optional Bilibili

Run the workflow in the active Codex task. Do not require subagents and do not delegate content authorship by default.

Use `<paper-root>/paper_presentation.json` as the source of truth for paper metadata, slide content, narrations, evidence, and publication metadata. Read `references/paper-presentation.schema.json`, then validate and render it with `scripts/presentation_manifest.py`. Legacy paper directories without a manifest remain readable, but all newly generated papers must use the manifest.

For full paper-explainer publication, read and enforce
[`references/publication-quality-standard.md`](references/publication-quality-standard.md).
Quality has priority over throughput. Parallelism may reduce waiting time but
must never reduce paper reading, figure selection, technical detail, or QA.
Use IndexTTS2 for every narration task. Do not select or fall back to another
local or network TTS backend.

## Modes

- `slides`: PDF → Markdown → Beamer source → compiled and rendered PDF.
- `video`: `slides` → page-aligned narration → TTS → verified MP4 and metadata.
- `bilibili`: `video` → metadata validation and dry-run → upload. Selecting this mode is explicit upload authorization; do not pause for a second confirmation.

Accept the PDF path, mode, optional output directory, language, target talk/video duration, and user emphasis. Default the paper directory to `<pdf-parent>/<paper-stem> - presentation/`.

## Stage 1: inspect and extract

1. Keep the original PDF unchanged.
2. Use the official PDF skill for page-level inspection and visual evidence.
3. Invoke the sibling `pdf-to-markdown` workflow when structured extraction is helpful.
4. Record extraction gaps before writing slides.

## Stage 2: create or refine Beamer

Invoke the sibling `paper-to-beamer` workflow and apply its
[`references/content-writing-guide.md`](../paper-to-beamer/references/content-writing-guide.md)
to every paper, including batch requests. Copy the sibling
`sustech-slides-template` resources by paths relative to this repository.
Compile with the official LaTeX skills, render every page, and stop until
errors, overflow, and unreadable figures are resolved.

Treat the first complete render of each paper as a draft. Before narration or
TTS, run the `paper-to-beamer` cold-read revision with narration hidden: read the
deck in order as a first-time viewer, reopen paper evidence for weak or
overstrong claims, and perform an information-density revision. Make each
substantive page deliver a complete local argument: question or condition,
mechanism or evidence, paper-specific technical information, and the resulting
conclusion. Restore supported details left only in narration, merge adjacent
sparse pages, and split only when supported content is genuinely hard to read.
Revise the manifest itself and recompile the whole deck. Allow this pass to
merge, split, reorder, add, or delete that paper's frames. Do not pad with
generic prose, emit a separate critique file, or pause the batch for approval.

Reject fixed-count text-only batch decks. Require the manifest quality profile,
paper-specific visual evidence, and a hash-matched `slides-beamer/visual-qa.json`
before TTS begins.

For both single-paper and batch generation, apply the standalone-slide contract
from the publication quality standard. Keep the research object, evidence or
mechanism, and take-home claim visible on each substantive page; do not move
technical content into narration to make slide authoring cheaper. Batch mode
is one continuous end-to-end workflow: for each paper, read and extract its
content, plan and write its manifest, compile and review its slides, and then
advance it through the shared TTS and video queues. It may share extraction and
rendering infrastructure, but it must plan and fill each paper's frames from
that paper's own argument and evidence. Never create a batch by changing only
the title, equation, and figures inside one fixed manifest, and never reuse
generic robustness, implication, limitation, or future-work bodies across
papers. Require the muted five-second readability review and an empty
`sparse_pages` list before TTS begins.

In batch mode, choose and revise the argument, page count, page order, evidence,
and depth independently for each paper without classifying papers. Run the full
cold-read revision when each paper's first render is ready rather than using one
aggregate batch review. The deterministic orchestrator drains its CPU preparation
queue before constructing the shared TTS manifest, and includes only papers whose
own revised render has been inspected.

When the user supplies a refinement prompt, modify only the affected entries in `paper_presentation.json` and rerender. For a legacy directory without a manifest, modify the existing `main.tex` rather than regenerating the deck. Recompile and rerender the complete presentation.

## Stage 3: create the video

Invoke the sibling `pdf-slides-to-video` workflow. Match only exact `slide_<digits>.png`, `.txt`, and `.mp3` names so audit sidecars cannot inflate coverage counts. Run TTS once, then assemble with `run_tts=False`. Require a nonempty narration, text file, and audio file for every rendered PDF page, including section dividers. Reuse valid per-page audio and video caches. Verify the final MP4 with `ffprobe` and sampled frames.

Write a hash-matched `video/video-visual-qa.json` only after inspecting sampled
frames from the final MP4. The pipeline must not mark `qa_passed` or publish
without both slide and video visual receipts plus automated audio/duration QA.

Generate `video/cover.png` only from the final rendered Beamer title page
(`video/video_frames/slide_001.png`) in both single-paper and batch modes. Fix
`publication.cover_path` to `cover.png` and regenerate it whenever the slide PDF
changes. Never substitute `poster/poster.png` or another paper figure for the
video or upload cover.

Optionally invoke `markdown-to-video-cover` for a separate promotional poster.
The poster is an independent artifact and must never replace the title-page
cover.

For two or more papers, use the deterministic batch orchestrator rather than invoking each paper's TTS separately:

```bash
VIDEO_SKILL="$SKILL_DIR/../pdf-slides-to-video"
"$VIDEO_SKILL/.venv/bin/python" "$SKILL_DIR/scripts/batch.py" video papers.json \
  --cpu-workers 4 --latex-workers 2 --post-workers 2 --ffmpeg-workers 6
```

It implements three queues:

1. Render the presentation manifest, then run existing-source compilation, rendering, narration alignment, cover, and metadata preparation on the CPU queue. Drain this queue before constructing the TTS manifest.
2. Merge every ready paper's page tasks into one single-GPU IndexTTS2 manifest. Run one whole-batch G2PW preflight, load the model once, keep GPU inference serial, and automatically close the worker when the queue finishes. After each MP3 is normalized, emit a page event; after all pages for one paper are ready, emit one paper event. Reject any other backend selection.
3. On each successful paper event, immediately encode cached page segments, concatenate the video, and run `ffprobe` QA on the shared post queue while IndexTTS2 continues later papers. A failed paper event enters the same post path only to record its isolated failure.

Maintain `video/pipeline-state.json` for every paper with the ordered checklist `queued → slides_done → narration_done → tts_done → video_done → qa_passed → uploaded`. Record hashes for the slide PDF, narrated TeX, every page image and narration, every audio file, final video, cover, and metadata. Resume from valid hashes, isolate paper-level failures, and continue other papers.

Use batch-scoped resource limits: `--latex-workers` controls all concurrent XeLaTeX processes. Treat `--ffmpeg-workers` as the total FFmpeg budget during TTS/post overlap: reserve the configured IndexTTS2 audio-normalization workers and give only the remainder to the shared segment executor and semaphore. If no remainder is available, finish TTS before starting post-processing. Never create a separate FFmpeg pool for each paper.

## Stage 4: publish only on request

Do not upload in `slides` or `video` mode. In `bilibili` mode, validate and log the exact title, tags, category, copyright, source, description, cover, and MP4, run the uploader dry-run, then upload without a second confirmation prompt. The user's initial choice of `bilibili` mode is the explicit publication request. Never infer publication permission from `slides` or `video` mode.

Format every Bilibili video title as `<VENUE> <YEAR>｜<中文论文题目>`, for
example `PRL 2024｜具有状态依赖记忆的广义 Langevin 方程的数据驱动学习`.
Use the established journal or conference abbreviation only when the PDF,
DOI, or authoritative publication metadata confirms it. Otherwise use
`arXiv` and the first arXiv-submission year; never infer a journal from an
arXiv subject category. Normalize the separator to the full-width `｜` and the
preprint label to the exact spelling `arXiv`. Preserve the complete faithful
Chinese title when it fits Bilibili's 80-character limit. If it does not fit,
retain the venue/year prefix and make the smallest meaning-preserving
shortening, while keeping the complete Chinese and English titles in the
manifest and description.

Write `publication.description` as a short viewer-facing introduction followed
by bibliographic details. Make the first nonempty line exactly one sentence in
the form `一句话概述：本文……；其重要性在于……。`, stating both what the paper did
and why it matters. Then write one or two plain-language Chinese sentences using
“本视频”, “本期”, “这期”, or “本次视频”; state the central question, main method
or evidence, and what the viewer will learn without hype. Finally add the
complete paper title and available venue, DOI, or canonical link. Do not submit
a description made only of title, venue, DOI, tags, or generated boilerplate.

Run batch publication with the same orchestrator and no extra confirmation flag:

```bash
VIDEO_SKILL="$SKILL_DIR/../pdf-slides-to-video"
"$VIDEO_SKILL/.venv/bin/python" "$SKILL_DIR/scripts/batch.py" bilibili papers.json \
  --cpu-workers 4 --latex-workers 2 --post-workers 2 --ffmpeg-workers 6
```

Reuse `bilibili-video-uploader/.venv` or `BILIUP_PYTHON`; never reinstall `biliup` for each paper. Write `video/upload-receipt.json` after a successful submission and block a second upload when video, cover, and metadata hashes match the receipt. Serialize uploads even when CPU and post-processing use parallel workers.

## Runtime and paths

- Resolve every sibling skill and script relative to this repository.
- Use workspace-relative or absolute paths supplied at runtime.
- Use `uv` environments and discovered executables; never assume a username, drive letter, global skill folder, or fixed Python binary.
- Keep intermediates inside the paper directory or a task-specific temporary directory.

## Final artifact retention

After the final upload and exact BVID verification, follow
[`references/artifact-retention.md`](references/artifact-retention.md). Present
only `final/article.pdf`, `final/beamer.pdf`, and `final/video.mp4` to the user.
Keep the minimal hidden recovery record, then remove redundant page caches,
logs, extraction output, and LaTeX build files with the deterministic finalizer.
Always dry-run the finalizer before applying cleanup.

For a batch, run finalization serially after every intended upload has a
verified BVID. The first command only previews and validates; the second
creates the three visible deliverables, writes the hidden recovery package,
and removes redundant working files:

```bash
VIDEO_SKILL="$SKILL_DIR/../pdf-slides-to-video"
"$VIDEO_SKILL/.venv/bin/python" "$SKILL_DIR/scripts/batch.py" finalize papers.json
"$VIDEO_SKILL/.venv/bin/python" "$SKILL_DIR/scripts/batch.py" finalize papers.json \
  --apply-finalize
```

Finalization is paper-isolated and serial. A paper that fails its upload,
quality, BVID, or hash gate remains untouched and does not prevent valid papers
later in the batch from being checked or finalized.

## Reporting

For each completed stage, write verbose output to the paper's log files and return a compact JSON summary with output paths and validation results. Include slide/PDF page counts, narration coverage, cache hits, video duration/codecs, and upload status. Never report a later stage as complete when an earlier validation gate failed.
