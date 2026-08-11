#!/usr/bin/env bash
set -euo pipefail

runtime_root="${ARTICLE_TTS_RUNTIME_ROOT:-$HOME/.local/share/article-to-video}"
model_root="${ARTICLE_TTS_MODEL_ROOT:-$HOME/.cache/article-to-video/models}"
index_repo="$runtime_root/IndexTTS2"
index_model="$model_root/IndexTTS-2"
index_commit="${INDEXTTS_COMMIT:-90ca4d608209584bad3a5bd5becc0b80c146e60f}"
model_revision="${INDEXTTS_MODEL_REVISION:-740dcaff396282ffb241903d150ac011cd4b1ede}"
uv_bin="${UV_BIN:-$(command -v uv || true)}"

if [[ -z "$uv_bin" ]]; then
  echo "uv is required: https://docs.astral.sh/uv/" >&2
  exit 1
fi
if [[ ! -d "$index_repo/.git" ]]; then
  mkdir -p "$runtime_root"
  git clone https://github.com/index-tts/index-tts.git "$index_repo"
  git -C "$index_repo" checkout --detach "$index_commit"
else
  current_commit="$(git -C "$index_repo" rev-parse HEAD)"
  if [[ "$current_commit" != "$index_commit" ]]; then
    printf 'Existing IndexTTS2 checkout is %s, expected %s.\n' \
      "$current_commit" "$index_commit" >&2
    printf 'Use a fresh ARTICLE_TTS_RUNTIME_ROOT; this script will not rewrite an existing runtime.\n' >&2
    exit 1
  fi
fi

"$uv_bin" sync --project "$index_repo"
MAX_JOBS="${MAX_JOBS:-2}" "$uv_bin" pip install \
  --python "$index_repo/.venv/bin/python" --no-build-isolation \
  "flash-attn==2.8.3.post1"
mkdir -p "$index_model"
"$uv_bin" run --project "$index_repo" hf download IndexTeam/IndexTTS-2 \
  --revision "$model_revision" --local-dir "$index_model" --max-workers 8

INDEXTTS_MODEL_DIR="$index_model" PYTHONPATH="$index_repo" \
  "$uv_bin" run --project "$index_repo" python - <<'PY'
import os
from indextts.utils import model_download

model_download._USING_MODELSCOPE = False
model_download.ensure_models_available(os.environ["INDEXTTS_MODEL_DIR"])
PY

"$uv_bin" run --project "$index_repo" indextts2 check \
  --model-dir "$index_model" --device cuda
printf 'IndexTTS2 runtime: %s\n' "$index_repo"
printf 'IndexTTS2 model:   %s\n' "$index_model"
printf 'IndexTTS2 commit:  %s\n' "$index_commit"
printf 'Model revision:    %s\n' "$model_revision"
