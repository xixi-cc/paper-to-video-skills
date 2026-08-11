---
name: pdf-slides-to-video
description: Convert compiled Beamer PDF slides into a narrated Chinese or English MP4 with page-aligned scripts, local IndexTTS2 voice cloning, cover art, and metadata. Use when Codex must turn a local slide deck into a lecture or paper-explanation video and verify page-to-audio alignment.
---

# PDF Slides to Narrated Video

Operate on a paper directory containing `slides-beamer/main.tex` and `slides-beamer/main.pdf`. Keep generated media under `<paper-dir>/video/`.

## Environment

Use the lightweight skill environment for parsing and video assembly:

```bash
uv sync --project "$SKILL_DIR"
"$SKILL_DIR/.venv/bin/python" --version
ffmpeg -version
ffprobe -version
pdftoppm -v
```

Use the separate NVIDIA runtime configured in `~/.config/article-to-video/tts.json` for IndexTTS2. Voice 319 is the bundled reference prompt. IndexTTS2 is the only supported narration backend; do not add an automatic or network fallback. If the configuration is absent, follow [references/local-tts-setup.md](references/local-tts-setup.md). For exact Voice 319 reproduction, also follow [references/voice-319.md](references/voice-319.md). Do not install large models or CUDA packages inside the skill directory.

## Workflow

1. Parse `main.tex` and render `main.pdf` at 200 DPI with `scripts/slides_to_video.py`.
2. Confirm rendered PNG count equals PDF page count, including implicit section-divider pages.
3. When `paper_presentation.json` exists, use the generated `presentation_frames.tex` and `video/main_with_narration.tex`; edit narrations only in the manifest. For a legacy paper without a manifest, copy `main.tex` to `video/main_with_narration.tex` and add `% NARRATION:` after every explicit `\end{frame}`.
4. Write self-contained narration. Avoid “这一页”, “本页”, and “如图所示”. Explain axes, panels, trends, symbols, and numerical values.
5. Keep narration concise but complete: target 35–50 Chinese words for title/outline, 100–175 for content/equations, 80–145 for figures, 35–50 for references, and 15–30 for closing. Compress an existing script to 80–85% only when the result still satisfies the requested duration and every quality gate. Never apply a compression percentage to a newly authored outline or use it to remove assumptions, equations, axes, quantitative results, or limitations.
6. Run `write_narrations_to_files`; replace generic implicit-divider transitions when useful. Require one nonempty `.txt` per PDF page.
7. Run local batch TTS:

```bash
"$SKILL_DIR/.venv/bin/python" "$SKILL_DIR/scripts/batch_tts.py" \
  "$PAPER_DIR/video/video_frames" --backend indextts2
```

IndexTTS2 receives the G2PW-audited narration, writes `.tts.txt` and `.pronunciation.json` audit files, and reuses `.tts-cache.json` when text, model, voice, sampling, pronunciation, or loudness settings are unchanged. For multiple papers, collect every paper's invalidated page tasks into one manifest and one batch-scoped worker process. Load the model once and keep GPU inference serial. Enable native acceleration only when at least six pages are pending; shorter jobs use the lightweight path. Submit each completed native WAV to the bounded CPU normalization pool while the GPU starts the next page; default to two normalization workers and at most four in-flight WAVs. Emit one page completion event only after its MP3 is finalized, then one paper completion event after all of that paper's pages finish; callers may start that paper's FFmpeg post-processing immediately. Let the worker exit automatically after both queues drain so CUDA memory is released.

8. Require one-to-one coverage among `.png`, `.txt`, and nonempty `.mp3`; then assemble H.264/AAC MP4 at 1920×1200. Synthesize TTS at its native `1.0` cadence, then default the final video to pitch-preserving `speed=1.25` with FFmpeg `atempo=1.25` and synchronized video PTS. Keep `pad_sec=0.5`; audio targets −16 LUFS and −1.5 dBTP. Do not change the model-native speed as well, because that would double-accelerate backends that honor it.
9. Generate `cover.png` by copying the final rendered Beamer first page
   (`slide_001.png`) without substituting, cropping, or selecting a poster. The
   first page must be the title page. Generate `video_meta.json` with
   `cover_path` fixed to `cover.png`. Regenerate the cover whenever the slide PDF
   changes.

For publishable paper explainers, follow
[`../pdf-to-bilibili/references/publication-quality-standard.md`](../pdf-to-bilibili/references/publication-quality-standard.md).
Require the actual duration, loudness, true peak, long-silence, pronunciation,
and final-video visual receipts after the fixed 1.25× playback transform. Do not
vary playback speed per paper or insert silence merely to meet a duration target.

## Verification

- Run `scripts/verify_local_tts.py --config ~/.config/article-to-video/tts.json` after runtime changes.
- Use `ffprobe` for duration, codec, resolution, and audio stream.
- Compare segment and audio counts with the PDF page count.
- Sample the opening, an equation, a figure, a transition, and the final page.
- Run TTS exactly once. When a caller already generated and verified MP3 files, invoke `assemble_video(..., run_tts=False)`.
- Reuse `.video-cache.json` segment caches when the PNG, MP3, padding, and encoding settings are unchanged. The TTS and video cache keys are page-level content hashes, so editing one page regenerates only that page's audio and segment.
- In multi-paper mode, pass the batch-scoped segment executor and FFmpeg semaphore into `assemble_video`; do not create a per-paper encoding pool.
- Keep verbose worker output in `*-worker.log`; report only compact stage summaries in the controlling session.
- Report page count, narrated-page count, duration, backend, reference voice/preset ID, speed, cache hits, polyphone replacements, and warnings.

Reject any backend other than `indextts2`. Never upload video from this skill.
