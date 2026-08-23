# Final artifact retention

After the final high-quality upload is verified, expose only three deliverables
in `<paper-root>/final/`:

- `article.pdf`: the unchanged source paper;
- `beamer.pdf`: the visually approved presentation;
- `video.mp4`: the quality-approved narrated video.

Keep the following small, non-user-facing recovery material in
`<paper-root>/.pipeline/`:

- `paper_presentation.json`, containing Beamer content and evidence locators;
- `video/narrations.json`;
- selected paper figures needed to revise or rebuild slides;
- `production-record.json`, consolidating final artifact hashes, BVID, and the
  pipeline state;
- the final cover when it was submitted to the platform.

After the final video checks and exact BVID verification pass, remove redundant
working material: rendered slide PNGs, per-page narration files and audio,
normalized WAV/MP3 caches, encoded page segments, extraction text, contact
sheets, logs, LaTeX auxiliary files, and copied theme/template files. Never
retain cookies, tokens, local model copies, virtual environments, or dependency
caches inside a paper directory.

Run `scripts/finalize_artifacts.py` without `--apply` first. It must refuse to
clean a paper whose pipeline state does not match the final video, whose upload
receipt lacks a verified BVID, or whose three deliverables cannot be hashed and
copied. Only then run it with `--apply`.

Finalization is an explicit per-paper maintenance command, not a video-pipeline
mode.
