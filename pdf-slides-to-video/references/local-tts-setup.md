# Local IndexTTS2 setup

IndexTTS2 is the only supported narration backend. It runs locally, does not call an LLM API, and does not consume API tokens. Keep the model, CUDA runtime, and G2PW runtime outside the skill directory. Voice 319 is the one intentionally bundled reference asset.

## Runtime

Use the provided setup script only when no reusable IndexTTS2 runtime exists:

```bash
"$SKILL_DIR/scripts/setup_indextts2_runtime.sh"
```

The script keeps the repository, Python environment, and model outside the skill directory. Do not reinstall it per paper or per batch.

## Reference voice

Verify and install the bundled prompt at the stable configured path:

```bash
mkdir -p ~/.config/article-to-video/voice
cd "$SKILL_DIR"
(cd assets/voices && sha256sum -c SHA256SUMS)
install -m 0644 assets/voices/voice-319-reference.wav \
  ~/.config/article-to-video/voice/index-319-reference.wav
mkdir -p ~/.config/article-to-video
cp references/tts-config.example.json \
  ~/.config/article-to-video/tts.json
```

Use the `indextts2` zero-shot voice entry with preset ID 319. Read the
[Voice 319 reproducibility card](voice-319.md) for its exact hash, tested
revisions, license, and reproducibility boundary. Replacing the WAV with a
custom authorized prompt creates a different voice identity.

## Acceleration policy

- Load one model for the complete pending batch.
- Run G2PW and validate IndexTTS2 pinyin tokens before loading the GPU model.
- Enable `use_accel`, `use_torch_compile`, and the CUDA kernel only when at least six pages are pending; use the lightweight path for shorter jobs.
- Keep `num_beams=1`, `use_fp16=true`, and the tested sampling parameters unless a controlled listening A/B supports a change.
- Keep GPU synthesis serial; use two CPU normalization workers with at most four WAVs in flight.
- Reuse page-level `.tts-cache.json` results. A model, voice, text, synthesis, or loudness change invalidates only the affected pages.

## Verify

```bash
"$SKILL_DIR/.venv/bin/python" "$SKILL_DIR/scripts/verify_local_tts.py" \
  --config ~/.config/article-to-video/tts.json \
  --synthesize /tmp/article-tts-verification.mp3
ffprobe -v error -show_streams -show_format /tmp/article-tts-verification.mp3
```

## Operations

- Regenerate selected slides: `batch_tts.py FRAME_DIR --only-slides 3,8 --force`.
- Override config with `ARTICLE_TTS_CONFIG=/path/to/tts.json` or `--config`.
- `--backend` accepts only `indextts2`; another value is a configuration error.
- Clear one cached slide with `--only-slides N --force`; do not delete the entire cache.
