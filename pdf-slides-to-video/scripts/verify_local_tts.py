"""Verify CUDA, G2PW disambiguation, config paths, and optional synthesis."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from tts_backends import (
    _config_for_backend,
    load_tts_config,
    resolve_backend,
    run_local_tts_batch,
)


TEST_TEXT = "重整化群描述尺度变化，重量保持不变，Wasserstein度量用于测量距离。"
PRONUNCIATION_MARKER = "PRONUNCIATION_RESULT_JSON="


def _verify_pronunciation(config: dict, backend: str) -> dict:
    pronunciation = config["pronunciation"]
    manifest = {
        "model_dir": pronunciation["model_dir"],
        "output_style": "indextts2",
        "pinyin_vocab": str(
            Path(config["runtime"]["model"]).expanduser() / "pinyin.vocab"
        ),
        "items": [{"name": "verification", "text": TEST_TEXT}],
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".pronunciation.json", encoding="utf-8", delete=False,
    ) as handle:
        json.dump(manifest, handle, ensure_ascii=False)
        manifest_path = Path(handle.name)
    try:
        result = subprocess.run(
            [
                str(Path(pronunciation["python"]).expanduser()),
                str(Path(__file__).with_name("pronunciation.py")),
                "--batch-manifest", str(manifest_path),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
    finally:
        manifest_path.unlink(missing_ok=True)
    for line in reversed(result.stdout.splitlines()):
        if line.startswith(PRONUNCIATION_MARKER):
            data = json.loads(line[len(PRONUNCIATION_MARKER):])["items"][0]
            break
    else:
        raise RuntimeError("G2PW verification returned no machine-readable result")
    expected = ("CHONG2", "ZHONG4", "DU4", "LIANG2")
    missing = [token for token in expected if token not in data["tts_text"]]
    if missing:
        raise RuntimeError(f"G2PW verification missing IndexTTS2 tokens: {missing}")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--backend", choices=("indextts2",), default="indextts2")
    parser.add_argument("--synthesize", type=Path)
    args = parser.parse_args()
    backend = resolve_backend(args.backend, args.config)
    config = _config_for_backend(load_tts_config(args.config), backend)
    python = str(Path(config["runtime"]["python"]).expanduser())
    gpu = subprocess.run(
        [
            python, "-c",
            "import torch; print(torch.__version__); "
            "print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CUDA unavailable')",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    print(gpu.stdout.strip())
    _verify_pronunciation(config, backend)
    if args.synthesize:
        output = args.synthesize.expanduser().resolve()
        result = run_local_tts_batch(
            backend,
            [{"name": "verification", "text": TEST_TEXT, "output": str(output)}],
            config_path=args.config,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
