"""Batch IndexTTS2 worker executed inside the isolated Python 3.11 runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Callable


SCRIPT_DIR = Path(__file__).resolve().parent
RESULT_MARKER = "INDEXTTS2_RESULT_JSON="
EVENT_MARKER = "INDEXTTS2_EVENT_JSON="
PRONUNCIATION_MARKER = "PRONUNCIATION_RESULT_JSON="


def _paper_id(task: dict[str, Any]) -> str:
    return str(task.get("paper_id") or str(task["name"]).partition(":")[0] or "default")


def _task_result(task: dict[str, Any], **values: Any) -> dict[str, Any]:
    return {
        "name": task["name"],
        "paper_id": _paper_id(task),
        "slide": task.get("slide") or str(task["name"]).rpartition(":")[2],
        **values,
    }


def _completion_recorder(
    tasks: list[dict[str, Any]],
    event_callback: Callable[[dict[str, Any]], None] | None,
) -> Callable[[dict[str, Any]], None]:
    """Build a recorder that emits one page event and one terminal paper event."""
    expected_by_paper: dict[str, int] = {}
    completed_by_paper: dict[str, list[dict[str, Any]]] = {}
    emitted_papers: set[str] = set()
    for task in tasks:
        paper_id = _paper_id(task)
        expected_by_paper[paper_id] = expected_by_paper.get(paper_id, 0) + 1

    def record_result(result: dict[str, Any]) -> None:
        paper_id = str(result["paper_id"])
        paper_results = completed_by_paper.setdefault(paper_id, [])
        paper_results.append(result)
        if event_callback is not None:
            event_callback({"type": "page_done", **result})
        if (
            paper_id not in emitted_papers
            and len(paper_results) == expected_by_paper[paper_id]
        ):
            emitted_papers.add(paper_id)
            if event_callback is not None:
                event_callback({
                    "type": "paper_done",
                    "paper_id": paper_id,
                    "status": (
                        "failed"
                        if any(item.get("status") == "failed" for item in paper_results)
                        else "complete"
                    ),
                    "tasks": sorted(paper_results, key=lambda item: str(item["name"])),
                })

    return record_result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_task_seed(base_seed: int, task_name: str) -> int:
    suffix = int(hashlib.sha256(task_name.encode("utf-8")).hexdigest()[:8], 16)
    return (base_seed + suffix) % (2**31 - 1)


def _cache_key(
    task: dict[str, Any], config: dict[str, Any], tts_text: str,
    reference_audio: Path, reference_audio_sha256: str | None = None,
) -> str:
    payload = {
        "pipeline_version": 1,
        "backend": "indextts2",
        "source_text": task["text"],
        "tts_text": tts_text,
        "model": str(Path(config["runtime"]["model"]).expanduser().resolve()),
        "model_revision": config["runtime"].get("model_revision", "unknown"),
        "reference_audio_sha256": reference_audio_sha256 or _sha256_file(reference_audio),
        "voice_preset_id": config["voice"].get("preset_id", "custom"),
        "synthesis": config.get("synthesis", {}),
        "target_lufs": float(config["audio"].get("target_lufs", -16.0)),
        "true_peak_db": float(config["audio"].get("true_peak_db", -1.5)),
        "output_sample_rate": int(config["audio"].get("output_sample_rate", 44100)),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_audio(source_wav: Path, output_mp3: Path, config: dict[str, Any]) -> None:
    target_lufs = float(config["audio"].get("target_lufs", -16.0))
    true_peak = float(config["audio"].get("true_peak_db", -1.5))
    sample_rate = int(config["audio"].get("output_sample_rate", 44100))
    base_filter = f"loudnorm=I={target_lufs}:TP={true_peak}:LRA=11"
    measurement = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(source_wav),
            "-af", f"{base_filter}:print_format=json", "-f", "null", "-",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    start = measurement.stderr.rfind("{")
    if start < 0:
        raise RuntimeError("ffmpeg loudness analysis returned no JSON")
    measured = json.loads(measurement.stderr[start:])
    second_pass = (
        f"{base_filter}:measured_I={measured['input_i']}:"
        f"measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:"
        f"measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:"
        "linear=true"
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(source_wav),
            "-af", second_pass, "-ar", str(sample_rate), "-ac", "2",
            "-codec:a", "libmp3lame", "-b:a", "192k", str(output_mp3),
        ],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(output_mp3), "-f", "null", "-"],
        check=True,
    )


def _finalize_audio(
    item: dict[str, Any], native_wav: Path, config: dict[str, Any], seed: int,
) -> dict[str, Any]:
    """Normalize one completed GPU WAV on a CPU worker and commit its cache."""
    task = item["task"]
    try:
        _normalize_audio(native_wav, item["output_mp3"], config)
        item["cache_path"].write_text(
            json.dumps(
                {
                    "key": item["key"], "backend": "indextts2",
                    "voice_preset_id": config["voice"].get("preset_id", "custom"),
                    "seed": seed,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return _task_result(
            task,
            status="generated",
            polyphones=item["pronunciation"]["polyphone_count"],
            seed=seed,
            inference_seconds=item.get("inference_seconds"),
        )
    except Exception as exc:
        item["output_mp3"].unlink(missing_ok=True)
        return _task_result(task, status="failed", error=str(exc))
    finally:
        native_wav.unlink(missing_ok=True)


def _synthesize_pending(
    tts: Any,
    pending: list[dict[str, Any]],
    config: dict[str, Any],
    reference_audio: Path,
    np_module: Any,
    torch_module: Any,
    on_result: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int | bool]]:
    """Keep GPU inference serial while CPU workers normalize earlier pages."""
    synthesis = config.get("synthesis", {})
    base_seed = int(synthesis.get("seed", 42))
    normalization_workers = max(
        1, int(synthesis.get("audio_normalization_workers", 2))
    )
    max_in_flight = max(
        normalization_workers,
        int(synthesis.get("audio_normalization_max_in_flight", normalization_workers * 2)),
    )
    results: list[dict[str, Any]] = []
    futures: set[Any] = set()

    def collect_completed() -> None:
        nonlocal futures
        if not futures:
            return
        done, remaining = wait(
            futures,
            return_when=FIRST_COMPLETED,
        )
        futures = set(remaining)
        for future in done:
            item = future.result()
            results.append(item)
            if on_result is not None:
                on_result(item)

    with ThreadPoolExecutor(
        max_workers=normalization_workers,
        thread_name_prefix="audio-normalize",
    ) as executor:
        for item in pending:
            while len(futures) >= max_in_flight:
                collect_completed()
            task = item["task"]
            native_wav = Path(f"{item['stem']}.native.wav")
            native_wav.unlink(missing_ok=True)
            seed = _stable_task_seed(base_seed, task["name"])
            random.seed(seed)
            np_module.random.seed(seed)
            torch_module.manual_seed(seed)
            torch_module.cuda.manual_seed_all(seed)
            try:
                inference_started = time.perf_counter()
                tts.infer(
                    spk_audio_prompt=str(reference_audio),
                    text=item["tts_text"],
                    output_path=str(native_wav),
                    emo_audio_prompt=None,
                    emo_alpha=float(synthesis.get("emo_alpha", 0.8)),
                    emo_vector=None,
                    use_emo_text=False,
                    use_random=False,
                    verbose=bool(synthesis.get("verbose", False)),
                    max_text_tokens_per_segment=int(synthesis.get("max_text_tokens_per_segment", 120)),
                    do_sample=bool(synthesis.get("do_sample", True)),
                    top_p=float(synthesis.get("top_p", 0.8)),
                    top_k=int(synthesis.get("top_k", 30)),
                    temperature=float(synthesis.get("temperature", 0.8)),
                    length_penalty=float(synthesis.get("length_penalty", 0.0)),
                    num_beams=int(synthesis.get("num_beams", 1)),
                    repetition_penalty=float(synthesis.get("repetition_penalty", 10.0)),
                    max_mel_tokens=int(synthesis.get("max_mel_tokens", 1500)),
                )
                item["inference_seconds"] = round(
                    time.perf_counter() - inference_started, 3
                )
                futures.add(executor.submit(_finalize_audio, item, native_wav, config, seed))
            except Exception as exc:
                native_wav.unlink(missing_ok=True)
                item["output_mp3"].unlink(missing_ok=True)
                result = _task_result(task, status="failed", error=str(exc))
                results.append(result)
                if on_result is not None:
                    on_result(result)
        while futures:
            collect_completed()
    return results, {
        "gpu_inference_serial": True,
        "audio_normalization_parallel": True,
        "audio_normalization_workers": normalization_workers,
        "audio_normalization_max_in_flight": max_in_flight,
    }


def _pronounce_tasks(
    tasks: list[dict[str, str]], config: dict[str, Any], model_dir: Path,
) -> dict[str, dict[str, Any]]:
    cached: dict[str, dict[str, Any]] = {}
    missing: list[dict[str, str]] = []
    for task in tasks:
        output_mp3 = Path(task["output"]).expanduser().resolve()
        sidecar = Path(f"{output_mp3.with_suffix('')}.pronunciation.json")
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            missing.append(task)
            continue
        if (
            payload.get("source_text") == task["text"]
            and payload.get("engine") == "g2pw"
            and payload.get("output_style") == "indextts2"
            and str(payload.get("tts_text", "")).strip()
            and isinstance(payload.get("replacements"), list)
        ):
            cached[task["name"]] = payload
        else:
            missing.append(task)
    if not missing:
        return cached

    pronunciation_config = config["pronunciation"]
    pronunciation_python = Path(pronunciation_config["python"]).expanduser().absolute()
    if not pronunciation_python.exists():
        raise FileNotFoundError(f"G2PW runtime Python not found: {pronunciation_python}")
    manifest = {
        "model_dir": pronunciation_config["model_dir"],
        "output_style": "indextts2",
        "pinyin_vocab": str(model_dir / "pinyin.vocab"),
        "items": [{"name": task["name"], "text": task["text"]} for task in missing],
    }
    manifest_dir = Path(tasks[0]["output"]).expanduser().resolve().parent
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".pronunciation.json", dir=manifest_dir,
        encoding="utf-8", delete=False,
    ) as handle:
        json.dump(manifest, handle, ensure_ascii=False)
        manifest_path = Path(handle.name)
    try:
        result = subprocess.run(
            [
                str(pronunciation_python), str(SCRIPT_DIR / "pronunciation.py"),
                "--batch-manifest", str(manifest_path),
            ],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError("G2PW batch failed:\n" + (result.stderr or result.stdout)[-4000:])
        for line in reversed(result.stdout.splitlines()):
            if line.startswith(PRONUNCIATION_MARKER):
                payload = json.loads(line[len(PRONUNCIATION_MARKER):])
                generated = {item["name"]: item for item in payload["items"]}
                return {**cached, **generated}
        raise RuntimeError("G2PW batch returned no machine-readable result")
    finally:
        manifest_path.unlink(missing_ok=True)


def run_manifest(
    manifest_path: Path,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config = manifest["config"]
    tasks = manifest["tasks"]
    if not tasks:
        return {"backend": "indextts2", "device": "not-loaded", "tasks": []}

    record_result = _completion_recorder(tasks, event_callback)

    repo = Path(config["runtime"]["repo"]).expanduser().resolve()
    model_dir = Path(config["runtime"]["model"]).expanduser().resolve()
    reference_audio = Path(config["voice"]["reference_audio"]).expanduser().resolve()
    for required in (repo, model_dir, model_dir / "config.yaml", reference_audio):
        if not required.exists():
            raise FileNotFoundError(required)

    # Run pronunciation for the whole batch before importing or constructing
    # IndexTTS2. Any unsupported pinyin token therefore fails before the costly
    # GPU model load and before a partial audio batch can be produced.
    pronunciations = _pronounce_tasks(tasks, config, model_dir)
    missing_pronunciations = sorted(
        task["name"] for task in tasks if task["name"] not in pronunciations
    )
    if missing_pronunciations:
        raise RuntimeError(
            "Pronunciation preflight missed task(s): "
            + ", ".join(missing_pronunciations[:10])
        )
    empty_tts_text = sorted(
        task["name"] for task in tasks
        if not pronunciations[task["name"]].get("tts_text", "").strip()
    )
    if empty_tts_text:
        raise RuntimeError(
            "Pronunciation preflight produced empty TTS text: "
            + ", ".join(empty_tts_text[:10])
        )
    preflight = {
        "status": "passed",
        "task_count": len(tasks),
        "polyphone_count": sum(
            int(item.get("polyphone_count", 0)) for item in pronunciations.values()
        ),
        "engine": "g2pw",
        "output_style": "indextts2",
        "items": [
            {
                "name": task["name"],
                "polyphone_count": int(
                    pronunciations[task["name"]].get("polyphone_count", 0)
                ),
                "replacements": pronunciations[task["name"]].get("replacements", []),
            }
            for task in tasks
        ],
    }
    preflight_path = (
        Path(tasks[0]["output"]).expanduser().resolve().parent
        / "pronunciation-preflight.json"
    )
    preflight_path.write_text(
        json.dumps(preflight, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    results: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    reference_audio_sha256 = _sha256_file(reference_audio)
    for task in tasks:
        output_mp3 = Path(task["output"]).expanduser().resolve()
        output_mp3.parent.mkdir(parents=True, exist_ok=True)
        stem = output_mp3.with_suffix("")
        tts_text_path = Path(f"{stem}.tts.txt")
        pronunciation_path = Path(f"{stem}.pronunciation.json")
        cache_path = Path(f"{stem}.tts-cache.json")
        pronunciation = pronunciations[task["name"]]
        tts_text = pronunciation["tts_text"]
        key = _cache_key(
            task, config, tts_text, reference_audio,
            reference_audio_sha256=reference_audio_sha256,
        )
        # Keep audit sidecars complete even when the MP3 itself is a cache hit.
        tts_text_path.write_text(tts_text, encoding="utf-8")
        pronunciation_path.write_text(
            json.dumps(pronunciation, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if output_mp3.exists() and cache_path.exists():
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            if cache.get("key") == key and output_mp3.stat().st_size > 500:
                result = _task_result(task, status="cached")
                results.append(result)
                record_result(result)
                continue
        pending.append(
            {
                "task": task,
                "output_mp3": output_mp3,
                "stem": stem,
                "cache_path": cache_path,
                "pronunciation": pronunciation,
                "tts_text": tts_text,
                "key": key,
            }
        )

    synthesis = config.get("synthesis", {})
    sys.path.insert(0, str(repo))
    os.chdir(repo)
    cuda_home = Path(
        synthesis.get("cuda_home", os.environ.get("CUDA_HOME", "/usr/local/cuda"))
    ).expanduser()
    nvcc = cuda_home / "bin" / "nvcc"
    if nvcc.is_file() and os.access(nvcc, os.X_OK):
        os.environ.setdefault("CUDA_HOME", str(cuda_home))
        os.environ.setdefault("CUDACXX", str(nvcc))
        os.environ["PATH"] = f"{nvcc.parent}{os.pathsep}{os.environ.get('PATH', '')}"
    import numpy as np
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("IndexTTS2 GPU backend requested but CUDA is unavailable")
    device_name = torch.cuda.get_device_name(0)
    compute_capability = torch.cuda.get_device_capability(0)
    os.environ.setdefault(
        "TORCH_CUDA_ARCH_LIST", f"{compute_capability[0]}.{compute_capability[1]}"
    )
    if not pending:
        return {
            "backend": "indextts2",
            "device": device_name,
            "preflight": {key: value for key, value in preflight.items() if key != "items"},
            "preflight_report": str(preflight_path),
            "tasks": results,
        }

    from indextts.infer_v2 import IndexTTS2

    acceleration_min_pages = max(
        1, int(synthesis.get("native_acceleration_min_pages", 6))
    )
    native_acceleration_active = len(pending) >= acceleration_min_pages
    use_cuda_kernel = bool(synthesis.get("use_cuda_kernel", False)) and native_acceleration_active
    use_accel = bool(synthesis.get("use_accel", False)) and native_acceleration_active
    use_torch_compile = (
        bool(synthesis.get("use_torch_compile", False)) and native_acceleration_active
    )
    model_load_started = time.perf_counter()
    tts = IndexTTS2(
        cfg_path=str(model_dir / "config.yaml"),
        model_dir=str(model_dir),
        use_fp16=bool(synthesis.get("use_fp16", True)),
        use_cuda_kernel=use_cuda_kernel,
        use_deepspeed=bool(synthesis.get("use_deepspeed", False)),
        use_accel=use_accel,
        use_torch_compile=use_torch_compile,
    )
    model_load_seconds = round(time.perf_counter() - model_load_started, 3)
    generated, concurrency = _synthesize_pending(
        tts, pending, config, reference_audio, np, torch, on_result=record_result,
    )
    results.extend(generated)

    return {
        "backend": "indextts2",
        "device": device_name,
        "preflight": {key: value for key, value in preflight.items() if key != "items"},
        "preflight_report": str(preflight_path),
        "acceleration": {
            "num_beams": int(synthesis.get("num_beams", 1)),
            "fp16": bool(synthesis.get("use_fp16", True)),
            "gpt_accel": bool(getattr(tts, "use_accel", False)),
            "torch_compile": bool(getattr(tts, "use_torch_compile", False)),
            "cuda_kernel": bool(getattr(tts, "use_cuda_kernel", False)),
            "deepspeed_requested": bool(synthesis.get("use_deepspeed", False)),
            "compute_capability": list(compute_capability),
            "model_load_seconds": model_load_seconds,
            "policy": {
                "pending_pages": len(pending),
                "native_acceleration_min_pages": acceleration_min_pages,
                "native_acceleration_active": native_acceleration_active,
            },
        },
        "concurrency": concurrency,
        "tasks": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an IndexTTS2 batch manifest")
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    def emit_event(event: dict[str, Any]) -> None:
        print(
            EVENT_MARKER + json.dumps(event, ensure_ascii=False, separators=(",", ":")),
            flush=True,
        )

    result = run_manifest(args.manifest.resolve(), event_callback=emit_event)
    print(
        RESULT_MARKER + json.dumps(result, ensure_ascii=False, separators=(",", ":")),
        flush=True,
    )


if __name__ == "__main__":
    main()
