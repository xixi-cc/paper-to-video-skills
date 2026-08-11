"""IndexTTS2 configuration and local batch dispatch."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


DEFAULT_CONFIG_PATH = Path("~/.config/article-to-video/tts.json").expanduser()
ONLY_BACKEND = "indextts2"
RESULT_MARKER = "INDEXTTS2_RESULT_JSON="
EVENT_MARKER = "INDEXTTS2_EVENT_JSON="


def load_tts_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    config_path = Path(path or os.environ.get("ARTICLE_TTS_CONFIG", DEFAULT_CONFIG_PATH)).expanduser()
    if not config_path.exists():
        raise FileNotFoundError(
            f"TTS config not found: {config_path}. Copy references/tts-config.example.json "
            "and configure an authorized reference voice."
        )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    return config


def resolve_backend(backend: str | None, config_path: str | None = None) -> str:
    requested = backend or os.environ.get("ARTICLE_TTS_BACKEND")
    if requested is None:
        requested = str(load_tts_config(config_path).get("backend", ONLY_BACKEND))
    if requested != ONLY_BACKEND:
        raise ValueError(
            f"Only IndexTTS2 is supported; requested backend was {requested!r}"
        )
    return ONLY_BACKEND


def _config_for_backend(config: dict[str, Any], backend: str) -> dict[str, Any]:
    """Resolve IndexTTS2 runtime and voice sections, including the legacy config layout."""
    prepared = dict(config)
    runtimes = config.get("runtimes")
    voices = config.get("voices")
    if runtimes is not None:
        if backend not in runtimes:
            raise KeyError(f"No runtime configured for backend {backend!r}")
        prepared["runtime"] = runtimes[backend]
    if voices is not None:
        if backend not in voices:
            raise KeyError(f"No voice configured for backend {backend!r}")
        prepared["voice"] = voices[backend]
    return prepared


def _run_local_worker(
    backend: str,
    tasks: list[dict[str, Any]],
    config_path: str | None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if not tasks:
        return {"backend": ONLY_BACKEND, "device": "not-loaded", "tasks": []}
    config = _config_for_backend(load_tts_config(config_path), backend)
    # Preserve the virtual-environment entry path. Resolving its symlink can
    # bypass pyvenv.cfg and launch the bare uv-managed interpreter.
    runtime_python = Path(config["runtime"]["python"]).expanduser().absolute()
    if not runtime_python.exists():
        raise FileNotFoundError(f"{backend} runtime Python not found: {runtime_python}")
    if backend != ONLY_BACKEND:
        raise ValueError(f"Only IndexTTS2 is supported; got {backend!r}")
    worker = Path(__file__).resolve().parent / "indextts2_worker.py"
    if not worker.exists():
        raise FileNotFoundError(f"TTS worker not found: {worker}")
    manifest = {"config": config, "tasks": tasks}
    manifest_dir = Path(tasks[0]["output"]).expanduser().resolve().parent
    manifest_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=f".{backend}.json", dir=manifest_dir,
        encoding="utf-8", delete=False,
    ) as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        manifest_path = Path(handle.name)
    try:
        process = subprocess.Popen(
            [str(runtime_python), str(worker), "--manifest", str(manifest_path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        log_path = manifest_dir / f"{backend}-worker.log"
        final_result: dict[str, Any] | None = None
        tail_lines: list[str] = []
        try:
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] {backend} batch\n")
                assert process.stdout is not None
                for raw_line in process.stdout:
                    log.write(raw_line)
                    log.flush()
                    line = raw_line.rstrip("\r\n")
                    tail_lines.append(line)
                    if len(tail_lines) > 200:
                        del tail_lines[:-200]
                    if line.startswith(EVENT_MARKER):
                        event = json.loads(line[len(EVENT_MARKER):])
                        if on_event is not None:
                            on_event(event)
                    elif line.startswith(RESULT_MARKER):
                        final_result = json.loads(line[len(RESULT_MARKER):])
            returncode = process.wait()
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise
        if returncode != 0:
            raise RuntimeError(
                f"{backend} batch failed; full log: {log_path}\n"
                + "\n".join(tail_lines)[-4000:]
            )
        if final_result is None:
            raise RuntimeError(
                f"{backend} worker returned no machine-readable result; full log: {log_path}"
            )
        return final_result
    finally:
        manifest_path.unlink(missing_ok=True)


def run_indextts2_batch(
    tasks: list[dict[str, Any]], config_path: str | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    return _run_local_worker("indextts2", tasks, config_path, on_event=on_event)


def run_local_tts_batch(
    backend: str,
    tasks: list[dict[str, Any]],
    config_path: str | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if backend == "indextts2":
        return run_indextts2_batch(tasks, config_path, on_event=on_event)
    raise ValueError(f"Only IndexTTS2 is supported; got {backend!r}")
