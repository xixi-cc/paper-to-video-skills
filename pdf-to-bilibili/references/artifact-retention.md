# Final artifact retention

After the final high-quality upload is verified, expose only three deliverables
in `<paper-root>/final/`:

- `article.pdf`: the unchanged source paper;
- `beamer.pdf`: the visually approved presentation;
- `video.mp4`: the quality-approved narrated video.

Keep the following small, non-user-facing recovery material in
`<paper-root>/.pipeline/`:

- `paper_presentation.json`, including narration and evidence locators;
- selected paper figures needed to revise or rebuild slides;
- `production-record.json`, consolidating artifact hashes, quality receipts,
  publication metadata, BVID, and pipeline state;
- the final cover when it was submitted to the platform.

After both the quality audit and exact BVID verification pass, remove redundant
working material: rendered slide PNGs, per-page narration files and audio,
normalized WAV/MP3 caches, encoded page segments, extraction text, contact
sheets, logs, LaTeX auxiliary files, and copied theme/template files. Never
retain cookies, tokens, local model copies, virtual environments, or dependency
caches inside a paper directory.

Run `scripts/finalize_artifacts.py` without `--apply` first. It must refuse to
clean a paper whose pipeline state is not `uploaded`, whose quality audit is not
valid, whose upload receipt lacks a verified BVID, or whose three deliverables
cannot be hashed and copied. Only then run it with `--apply`.

For two or more papers, use the batch wrapper. It applies the same gates and
processes papers serially so destructive cleanup never runs concurrently:

```bash
python scripts/batch.py finalize papers.json
python scripts/batch.py finalize papers.json --apply-finalize
```
