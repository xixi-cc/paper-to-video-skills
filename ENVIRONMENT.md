# Dependencies and environment configuration

This document describes the tested environment boundaries without changing
the repository's existing runtime configuration files. Keep models, virtual
environments, credentials, private/custom reference audio, and generated media
outside the repository. Voice 319 is the intentionally bundled exception.

## Supported baseline

- Linux or WSL2; Ubuntu 24.04 is the primary tested platform.
- Python 3.12 for the slide/video utility environment.
- NVIDIA GPU and a compatible CUDA toolkit for IndexTTS2 generation.
- A CPU-only machine can inspect Skills, compile slides, render PDFs, and run
  non-TTS validation, but it cannot run the production narration backend.
- Codex Desktop or another agent runtime capable of loading `SKILL.md` files.

## System programs

Install equivalent packages for your distribution. On Ubuntu 24.04, a typical
baseline is:

```bash
sudo apt update
sudo apt install -y \
  python3.12 python3.12-venv git git-lfs \
  ffmpeg poppler-utils latexmk \
  texlive-xetex texlive-latex-extra texlive-lang-chinese
```

Install `uv` using its official instructions, then verify the tools:

```bash
uv --version
python3.12 --version
latexmk -v
xelatex --version
ffmpeg -version
ffprobe -version
pdftoppm -v
```

## Lightweight slide/video Python environment

The checked-in lock file covers the lightweight PDF rendering dependencies:

```bash
uv sync --project pdf-slides-to-video
```

This creates `pdf-slides-to-video/.venv` locally. The directory is ignored and
must not be committed.

## IndexTTS2 runtime

IndexTTS2 is the only supported narration backend. It has its own license and
large CUDA/model dependencies, so keep it outside this repository. Review
`THIRD_PARTY_NOTICES.md` before installation.

If no reusable runtime exists, run:

```bash
pdf-slides-to-video/scripts/setup_indextts2_runtime.sh
```

The script uses these optional environment variables:

```bash
export ARTICLE_TTS_RUNTIME_ROOT="$HOME/.local/share/article-to-video"
export ARTICLE_TTS_MODEL_ROOT="$HOME/.cache/article-to-video/models"
export INDEXTTS_COMMIT="90ca4d608209584bad3a5bd5becc0b80c146e60f"
export INDEXTTS_MODEL_REVISION="740dcaff396282ffb241903d150ac011cd4b1ede"
export MAX_JOBS=2
```

The upstream repository, model weights, PyTorch, CUDA components, and
FlashAttention are external dependencies. The setup script defaults to the
tested source and model revisions recorded in the Voice 319 reproducibility
card; both may be overridden explicitly. Record the effective revisions, CUDA
version, and GPU model used for any reproducibility report.

## G2PW pronunciation runtime

The production pipeline performs a G2PW pronunciation preflight before loading
IndexTTS2. Install G2PW in a separate Python environment and download its model
outside this repository. The configured paths must identify:

- a Python executable that can import the G2PW runtime;
- the G2PW model directory;
- the IndexTTS2 `pinyin.vocab` supplied by the selected model checkout.

This repository does not currently provide a G2PW bootstrap installer. Verify
the configured runtime before starting a large batch.

## TTS configuration and reference voice

Create a private configuration from the example:

```bash
mkdir -p ~/.config/article-to-video/voice
install -m 0644 \
  pdf-slides-to-video/assets/voices/voice-319-reference.wav \
  ~/.config/article-to-video/voice/index-319-reference.wav
cp pdf-slides-to-video/references/tts-config.example.json \
  ~/.config/article-to-video/tts.json
(cd pdf-slides-to-video/assets/voices && sha256sum -c SHA256SUMS)
```

Edit `~/.config/article-to-video/tts.json` so that all runtime, model, G2PW,
and reference-audio paths match your machine. The example is the tested Voice
319 preset, not a placeholder. Keep the bundled WAV byte-identical when exact
Voice 319 reproduction is required; see
`pdf-slides-to-video/references/voice-319.md`.

Never commit `tts.json`, private/custom reference audio, model files, or
synthesized voices. The bundled Voice 319 WAV is the intentional public
exception. Use another reference voice only when you own it or have explicit
authorization to use and publish it.

Run a local verification only after reviewing the paths and license:

```bash
pdf-slides-to-video/.venv/bin/python \
  pdf-slides-to-video/scripts/verify_local_tts.py \
  --config ~/.config/article-to-video/tts.json
```

## MinerU environments

### Hosted MinerU Open API

The `pdf-to-markdown` wrapper supports the separately installed
`mineru-open-api` CLI. This route uploads each input document to the configured
MinerU service, so use it only for documents whose remote processing has been
authorized. Authenticate once in the private user configuration:

```bash
mineru-open-api version
mineru-open-api auth
mineru-open-api auth --verify
```

The CLI stores its token outside this repository. For non-interactive runs it
may instead read `MINERU_TOKEN`; never put the token in a tracked file or pass
it on the command line. The workflow invokes precision extraction explicitly:

```bash
python pdf-to-markdown/convert.py INPUT OUTPUT_DIR \
  --engine open-api --lang ch --api-model auto
```

`--engine local` remains the converter default, so a missing engine flag cannot
silently upload a document. Set `MINERU_OPEN_API_BIN` only when the executable
is not discoverable on `PATH`.

### Local MinerU

The local route uses MinerU's in-process API. Because MinerU is a large,
optional dependency, install it in a separate environment. Follow the current
upstream documentation; a typical full installation is:

```bash
uv venv ~/.local/share/article-to-video/mineru
uv pip install --python ~/.local/share/article-to-video/mineru/bin/python \
  -U "mineru[all]"
```

Run `pdf-to-markdown/convert.py --engine local` with that environment's Python.
GPU support and model downloads depend on the MinerU version and selected
backend.

## Bilibili upload environment

Uploading is optional and externally consequential. Install uploader
dependencies in a separate environment:

```bash
uv venv bilibili-video-uploader/.venv --python 3.11
uv pip install --python bilibili-video-uploader/.venv/bin/python \
  "biliup>=1.2" requests "psutil>=5.9"
```

Store cookies outside the repository:

```bash
export BILIBILI_COOKIE_FILE="$HOME/.bilibili/cookies.json"
```

Do not paste cookies into issues, logs, examples, or Git commits. Upload and
withdrawal code uses dry-run and explicit authorization gates, but users remain
responsible for account security and compliance with Bilibili platform rules.

## Validation without GPU or network side effects

From the repository root:

```bash
python3 -m compileall .
python3 -m unittest discover -s tests -v
```

Validate every Skill with the `skill-creator` validator available in your
Codex installation. Compile the Beamer template separately and visually inspect
its rendered PDF. Never use a real upload or withdrawal as a smoke test.
