---
name: bilibili-video-uploader
description: Validate metadata and upload a completed paper-explanation MP4 to Bilibili through biliup. Use only when the user explicitly asks Codex to upload or publish an already generated video.
---

# Bilibili Video Uploader

Uploading is an external, consequential action. Never upload merely because a video was generated.

## Preconditions

1. Require an explicit upload request in the current conversation.
2. Locate `<paper-dir>/video/video_meta.json`, at least one MP4, and
   `video/cover.png`. Require `cover_path` to be `cover.png`. When
   `video/video_frames/slide_001.png` exists, refresh `cover.png` from that
   rendered Beamer title page before the dry run. Never fall back to
   `poster/poster.png` or another figure.
3. Validate and log title, category, tags, description, copyright, source, cover, and selected MP4 before submission. Make the first nonempty line exactly one Chinese sentence in the form `一句话概述：本文……；其重要性在于……。`, stating both what the paper did and why it matters. Follow it with one or two plain-language Chinese sentences introduced by “本视频”, “本期”, “这期”, or “本次视频”; briefly state the research question and what the viewer will learn. Then include the complete paper title and available venue, DOI, or canonical link. Reject descriptions containing only bibliographic metadata. An explicit request to upload, publish, or run `bilibili` mode authorizes the submission; do not require a second confirmation.
4. Keep cookies at `~/.bilibili/cookies.json`. Never print, copy into the repository, or commit cookie contents.
5. Reuse the existing sibling `.venv` containing `biliup>=1.2`, or set `BILIUP_PYTHON` to another isolated runtime. Install only when neither reusable runtime exists; never reinstall per paper or install into system Python.

## Commands

Resolve this skill directory at runtime:

```bash
python "$SKILL_DIR/scripts/upload.py" --login
python "$SKILL_DIR/scripts/upload.py" PAPER_DIR --dry-run
python "$SKILL_DIR/scripts/upload.py" PAPER_DIR --confirm-upload
```

For an explicitly requested replacement batch, withdraw only from an exact
audit plus a Creator Center snapshot. Preview first, then apply with a durable
receipt. Never accept an unbounded "all submissions" target:

```bash
python "$SKILL_DIR/scripts/withdraw_batch.py" AUDIT_JSON SNAPSHOT_JSON \
  --indices 3-20 --receipt WITHDRAWAL_RECEIPT_JSON
python "$SKILL_DIR/scripts/withdraw_batch.py" AUDIT_JSON SNAPSHOT_JSON \
  --indices 3-20 --receipt WITHDRAWAL_RECEIPT_JSON --apply
```

The withdrawal tool must live-query Creator Center and require exact BVID and
title matches before any deletion. Process serially, record every response
atomically, rescan after the batch, and keep protected/non-target submissions
untouched.

`--dry-run` must print the resolved media and sanitized command without contacting the upload endpoint. After a successful dry-run, use `--confirm-upload` for the actual upload without pausing for another confirmation.

## Validation and reporting

- Reject missing files, empty tags, titles over the platform limit, a missing one-sentence work-and-importance summary, missing simple introductions, or invalid copyright/source combinations. Print the complete description in every dry-run plan.
- Do not delete locks or terminate processes automatically. Diagnostics must remain read-only unless the user explicitly authorizes cleanup.
- On authentication failure, ask the user to run QR login; never request cookie text.
- On success, return the BV identifier and URL. On failure, classify authentication, duplicate, size, rate-limit, or unknown errors without automatic retries that could duplicate a submission.
