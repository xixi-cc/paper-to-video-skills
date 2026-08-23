---
name: bilibili-video-uploader
description: Validate metadata and upload a completed paper-explanation MP4 to Bilibili through biliup. Use only when the user explicitly asks Codex to upload or publish an already generated video.
metadata:
  stage_model: gpt-5.6-terra
  stage_reasoning_effort: medium
---

# Bilibili video uploader

Upload only after an explicit publication request in the current conversation.
Video generation alone is not authorization.

## Required model route

Run this stage in exactly one model-routed worker. If the current delegated
prompt contains `PAPER_TO_VIDEO_STAGE_WORKER=terra:gpt-5.6-terra:medium`,
execute the Skill directly and do not delegate again. Otherwise, before doing
stage work, spawn one subagent with model `gpt-5.6-terra` and reasoning effort
`medium`. In its prompt, require this Skill, include the marker above, and carry
forward the exact paper paths, explicit publication authorization (if any), and
all current authorization boundaries. Wait for that worker and return its
result; the parent may verify the handoff but must not redo the stage. If the
exact worker profile cannot start, stop and report that routing failure instead
of silently inheriting or falling back to the parent model. Delegation never
creates upload authorization.

## Inputs

Under `<paper-dir>/video/`, require:

- a completed MP4;
- `cover.png`, derived from the rendered Beamer title page;
- `video_meta.json` with a nonempty title, tag list, and description.

The description is free-form. Prefer a concise explanation plus the paper title
and canonical link, but do not enforce a sentence template or exact paragraph
shape. Validate copyright/source consistency. Keep cookies only at
`~/.bilibili/cookies.json` and never print their contents.

## Upload

Resolve this Skill directory at runtime, then preview before submission:

```bash
python "$SKILL_DIR/scripts/upload.py" PAPER_DIR --dry-run
python "$SKILL_DIR/scripts/upload.py" PAPER_DIR --confirm-upload
```

The uploader owns `video/upload-receipt.json`. It fingerprints the video,
cover, and metadata; a matching verified receipt prevents duplicate submission.
If a command may have succeeded but no BVID is known, verify the exact title and
do not automatically retry. Use `--verify-only` to complete that verification.

On authentication failure, ask the user to run:

```bash
python "$SKILL_DIR/scripts/upload.py" --login
```

## biliup locks

Diagnosis is read-only. Cleanup terminates only biliup processes holding a
discovered lock, waits for them to exit, and then removes unheld locks:

```bash
python "$SKILL_DIR/scripts/upload.py" --diagnose-locks
python "$SKILL_DIR/scripts/upload.py" --cleanup-locks --confirm-cleanup
```

Never trigger cleanup merely because an upload failed. Use `--force-kill` only
after explicit authorization when graceful termination fails.

For explicitly scoped withdrawals, preview `scripts/withdraw_batch.py` first,
require exact BVID and title matches, then apply with a durable receipt. Never
use an unbounded target or an actual upload/withdrawal as a smoke test.

Return the verified BVID and URL. Classify authentication, duplicate, size,
rate-limit, and unknown failures without automatic submission retries.
