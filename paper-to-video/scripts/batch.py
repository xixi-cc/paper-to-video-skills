#!/usr/bin/env python3
"""Build verified local paper videos with one resumable batch pipeline.

CPU preparation is parallel, all local-TTS tasks share one GPU worker process,
and video assembly is parallel. Uploading is owned by the separate
``bilibili-video-uploader`` Skill.

Usage:
    python batch.py papers.json --cpu-workers 4 --post-workers 2
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SUITE_DIR = SCRIPT_DIR.parents[1]
VIDEO_SCRIPTS = SUITE_DIR / "pdf-slides-to-video" / "scripts"
MANIFEST_SCRIPT_DIR = SUITE_DIR / "paper-to-video" / "scripts"
STATE_FILE = "pipeline-state.json"
STAGES = ("queued", "slides_done", "narration_done", "tts_done", "video_done")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analyze_audio_quality(video: Path) -> dict[str, Any]:
    loudness = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(video),
            "-filter_complex", "ebur128=peak=true", "-f", "null", "-",
        ],
        capture_output=True, text=True, check=True,
    ).stderr
    integrated_values = re.findall(
        r"^\s*I:\s*(-?\d+(?:\.\d+)?) LUFS", loudness, re.MULTILINE,
    )
    lra_values = re.findall(
        r"^\s*LRA:\s*(-?\d+(?:\.\d+)?) LU", loudness, re.MULTILINE,
    )
    peak_values = re.findall(
        r"^\s*Peak:\s*(-?\d+(?:\.\d+)?) dBFS", loudness, re.MULTILINE,
    )
    if not integrated_values or not lra_values or not peak_values:
        raise RuntimeError("Could not parse FFmpeg EBU R128 audio analysis")
    integrated = float(integrated_values[-1])
    lra = float(lra_values[-1])
    true_peak = float(peak_values[-1])

    silence = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(video),
            "-af", "silencedetect=noise=-45dB:d=2", "-f", "null", "-",
        ],
        capture_output=True, text=True, check=True,
    ).stderr
    silence_durations = [
        float(value) for value in re.findall(r"silence_duration:\s*([0-9.]+)", silence)
    ]
    if not -17.0 <= integrated <= -15.0:
        raise RuntimeError(f"Integrated loudness {integrated:.1f} LUFS is outside -17 to -15")
    if true_peak > -2.0:
        raise RuntimeError(f"True peak {true_peak:.1f} dBFS is higher than -2 dBFS")
    if silence_durations:
        raise RuntimeError(
            "Unintended silence over two seconds detected: "
            + ", ".join(f"{value:.2f}s" for value in silence_durations)
        )
    return {
        "integrated_loudness_lufs": integrated,
        "loudness_range_lu": lra,
        "true_peak_dbfs": true_peak,
        "long_silence_over_2s_detected": False,
    }


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def exact_slide_files(directory: Path, suffix: str) -> dict[str, Path]:
    """Return only slide_<digits>.<suffix> files, excluding audit sidecars."""
    if not directory.exists():
        return {}
    pattern = re.compile(rf"slide_\d+\.{re.escape(suffix.lstrip('.'))}")
    return {
        path.stem: path
        for path in directory.iterdir()
        if path.is_file() and pattern.fullmatch(path.name)
    }


def require_matching_slides(
    expected: dict[str, Path], actual: dict[str, Path], label: str, paper_name: str,
) -> None:
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    empty = sorted(name for name, path in actual.items() if path.stat().st_size == 0)
    if missing or extra or empty:
        details = []
        if missing:
            details.append("missing=" + ",".join(missing[:10]))
        if extra:
            details.append("extra=" + ",".join(extra[:10]))
        if empty:
            details.append("empty=" + ",".join(empty[:10]))
        raise RuntimeError(
            f"{label} coverage mismatch for {paper_name}: " + "; ".join(details)
        )


def write_narration_files(
    narration_path: Path, frame_dir: Path, slides: dict[str, Path],
) -> dict[str, Any]:
    if not narration_path.exists():
        raise FileNotFoundError(f"Missing page narration: {narration_path}")
    narrations = json.loads(narration_path.read_text(encoding="utf-8"))
    if not isinstance(narrations, dict):
        raise ValueError("video/narrations.json must contain a slide_NNN to text object")
    expected = set(slides)
    actual = set(narrations)
    if expected != actual:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise RuntimeError(
            "Narration coverage mismatch: "
            f"missing={','.join(missing[:10]) or 'none'}; "
            f"extra={','.join(extra[:10]) or 'none'}"
        )
    characters = 0
    for name in sorted(expected):
        text = narrations[name]
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Narration is empty for {name}")
        normalized = " ".join(text.splitlines()).strip()
        (frame_dir / f"{name}.txt").write_text(normalized + "\n", encoding="utf-8")
        characters += len(re.sub(r"\s+", "", normalized))
    return {"pages": len(expected), "characters": characters}


def load_papers(path: Path) -> list[dict[str, Any]]:
    papers = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(papers, list):
        raise ValueError("papers.json must contain a JSON array")
    return papers


def paper_dir(paper: dict[str, Any]) -> Path:
    value = paper.get("dir_path") or paper.get("paper_dir")
    if not value:
        raise ValueError("Each paper needs dir_path or paper_dir")
    return Path(value).expanduser().resolve()


def state_path(root: Path) -> Path:
    return root / "video" / STATE_FILE


def load_state(root: Path) -> dict[str, Any]:
    path = state_path(root)
    if path.exists():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}
    else:
        state = {}
    state["schema_version"] = 2
    state.setdefault("paper", root.name)
    previous_stages = state.get("stages", {})
    state["stages"] = {
        stage: bool(previous_stages.get(stage, False))
        for stage in STAGES
    }
    state["stages"]["queued"] = True
    state.setdefault("hashes", {})
    state.setdefault("events", [])
    state.setdefault("status", "queued")
    return state


def save_state(root: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    atomic_json(state_path(root), state)


def invalidate_from(state: dict[str, Any], stage: str) -> None:
    """Clear a changed stage and everything downstream of it."""
    start = STAGES.index(stage)
    for name in STAGES[start:]:
        state["stages"][name] = False


def mark_stage(root: Path, state: dict[str, Any], stage: str, **details: Any) -> None:
    state["stages"][stage] = True
    state["status"] = stage
    state["last_error"] = None
    state["events"].append({"at": utc_now(), "stage": stage, **details})
    save_state(root, state)


def mark_failure(
    root: Path, state: dict[str, Any], queue: str, error: BaseException,
) -> None:
    state["status"] = "failed"
    state["last_error"] = {"queue": queue, "message": str(error), "at": utc_now()}
    save_state(root, state)


def compile_deck(
    root: Path, force: bool = False, latex_semaphore: threading.Semaphore | None = None,
) -> None:
    deck = root / "slides-beamer"
    tex = deck / "main.tex"
    pdf = deck / "main.pdf"
    if not tex.exists():
        raise FileNotFoundError(f"Missing Beamer source: {tex}")
    content = tex.read_text(encoding="utf-8")
    # Manifest-backed decks keep the stock template as an unreachable
    # \IfFileExists fallback; only reject placeholders when those generated
    # include files are absent and the fallback would actually be rendered.
    generated_includes_exist = (
        (deck / "presentation_metadata.tex").exists()
        and (deck / "presentation_frames.tex").exists()
    )
    if not generated_includes_exist and len(re.findall(r"\\ph\{", content)) > 5:
        raise RuntimeError(f"Unresolved Beamer placeholders: {root.name}")
    dependencies = [
        tex,
        deck / "presentation_metadata.tex",
        deck / "presentation_frames.tex",
    ]
    latest_input_mtime = max(
        path.stat().st_mtime for path in dependencies if path.exists()
    )
    if not force and pdf.exists() and pdf.stat().st_mtime >= latest_input_mtime:
        return
    guard = latex_semaphore if latex_semaphore is not None else contextlib.nullcontext()
    with guard:
        result = subprocess.run(
            ["latexmk", "-xelatex", "main.tex"], cwd=deck,
            capture_output=True, text=True, timeout=300,
        )
    log = root / "video" / "compile.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != 0 or not pdf.exists():
        raise RuntimeError(f"Beamer compile failed; see {log}")


def _prune_unexpected_frames(frame_dir: Path, expected: set[str]) -> None:
    """Remove only obsolete generated slide artifacts after a page-count change."""
    generated_suffixes = (
        ".png", ".txt", ".mp3", ".tts.txt", ".pronunciation.json",
        ".tts-cache.json", "_final.mp4", ".video-cache.json",
    )
    for path in frame_dir.glob("slide_*"):
        name = path.name
        match = re.match(r"(slide_\d+)", name)
        if not match or match.group(1) in expected:
            continue
        if any(name.endswith(suffix) for suffix in generated_suffixes):
            path.unlink(missing_ok=True)


def prepare_paper(
    paper: dict[str, Any], force_compile: bool = False,
    latex_semaphore: threading.Semaphore | None = None,
) -> dict[str, Any]:
    """CPU queue: compile, render, load page narration, and collect hashes."""
    sys.path.insert(0, str(VIDEO_SCRIPTS))
    from slides_to_video import generate_cover, render_slides  # type: ignore

    root = paper_dir(paper)
    state = load_state(root)
    started = time.perf_counter()
    try:
        manifest_path = root / "paper_presentation.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Missing Beamer manifest: {manifest_path}")
        sys.path.insert(0, str(MANIFEST_SCRIPT_DIR))
        from presentation_manifest import render_manifest  # type: ignore
        manifest_result = render_manifest(root)
        manifest_hash = manifest_result["manifest_sha256"]
        if state["hashes"].get("presentation_manifest_sha256") != manifest_hash:
            invalidate_from(state, "slides_done")
        state["hashes"]["presentation_manifest_sha256"] = manifest_hash
        compile_deck(root, force=force_compile, latex_semaphore=latex_semaphore)
        slides_pdf = root / "slides-beamer" / "main.pdf"
        slides_tex = root / "slides-beamer" / "main.tex"
        narration_path = root / "video" / "narrations.json"

        previous_pdf_hash = state["hashes"].get("slides_pdf_sha256")
        previous_tex_hash = state["hashes"].get("slides_tex_sha256")
        previous_narration_hash = state["hashes"].get("narrations_sha256")
        pdf_hash = sha256_file(slides_pdf)
        tex_hash = sha256_file(slides_tex)
        narration_hash = sha256_file(narration_path)
        if previous_pdf_hash != pdf_hash or previous_tex_hash != tex_hash:
            invalidate_from(state, "slides_done")
        elif previous_narration_hash != narration_hash:
            invalidate_from(state, "narration_done")
        state["hashes"].update({
            "slides_pdf_sha256": pdf_hash,
            "slides_tex_sha256": tex_hash,
            "narrations_sha256": narration_hash,
        })
        previous_slide_review = state.get("slides", {})
        state["slides"] = {
            "pdf_sha256": pdf_hash,
            "compiled": True,
            "visually_reviewed": bool(
                previous_slide_review.get("pdf_sha256") == pdf_hash
                and previous_slide_review.get("visually_reviewed") is True
            ),
            "defects": previous_slide_review.get("defects", [])
            if previous_slide_review.get("pdf_sha256") == pdf_hash else [],
        }
        mark_stage(root, state, "slides_done")

        frame_dir = root / "video" / "video_frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        png_files = exact_slide_files(frame_dir, "png")
        if previous_pdf_hash != pdf_hash or not png_files:
            for path in png_files.values():
                path.unlink(missing_ok=True)
            render_slides(str(slides_pdf), str(frame_dir), dpi=200)
            png_files = exact_slide_files(frame_dir, "png")
        if not png_files:
            raise RuntimeError(f"No rendered slides for {root.name}")
        state["slides"]["pages"] = len(png_files)
        title_slide = png_files.get("slide_001")
        if title_slide is None:
            raise RuntimeError(f"Missing rendered Beamer title page for {root.name}")
        generate_cover(str(title_slide), str(root / "video" / "cover.png"))

        _prune_unexpected_frames(frame_dir, set(png_files))
        narration_result = write_narration_files(narration_path, frame_dir, png_files)
        txt_files = exact_slide_files(frame_dir, "txt")
        require_matching_slides(png_files, txt_files, "Narration", root.name)
        narration_chars = int(narration_result["characters"])
        previous_pages = state["hashes"].get("pages", {})
        pages = {}
        for name in sorted(png_files):
            page_hashes = {
                "slide_sha256": sha256_file(png_files[name]),
                "narration_sha256": sha256_file(txt_files[name]),
            }
            previous_page = previous_pages.get(name, {})
            if (
                previous_page.get("narration_sha256")
                == page_hashes["narration_sha256"]
                and previous_page.get("audio_sha256")
            ):
                page_hashes["audio_sha256"] = previous_page["audio_sha256"]
            pages[name] = page_hashes
        state["hashes"]["pages"] = pages
        state["metrics"] = {
            **state.get("metrics", {}),
            "pages": len(png_files),
            "narration_characters": narration_chars,
            "average_characters_per_page": round(narration_chars / len(png_files), 1),
        }
        state["narration"] = {
            "sha256": narration_hash,
            "pages": len(txt_files),
            "covered_pages": len(txt_files),
        }
        mark_stage(
            root, state, "narration_done",
            pages=len(png_files), narration_characters=narration_chars,
        )

        paper_id = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:12]
        tasks = [
            {
                "name": f"{paper_id}:{name}",
                "text": txt_files[name].read_text(encoding="utf-8").strip(),
                "output": str(txt_files[name].with_suffix(".mp3")),
                "paper_id": paper_id,
                "slide": name,
            }
            for name in sorted(txt_files)
        ]
        return {
            "paper": paper,
            "paper_id": paper_id,
            "root": root,
            "state": state,
            "frame_dir": frame_dir,
            "png_files": png_files,
            "tasks": tasks,
            "narration": narration_result,
            "presentation_manifest": manifest_result,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        mark_failure(root, state, "cpu", exc)
        return {"paper": paper, "root": root, "state": state, "error": str(exc)}


def _ffprobe_video(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    payload = json.loads(result.stdout)
    video = next((s for s in payload.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in payload.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not video or not audio:
        raise RuntimeError(f"Video/audio stream missing: {path}")
    if int(video.get("width", 0)) != 1920 or int(video.get("height", 0)) != 1200:
        raise RuntimeError(f"Unexpected video resolution: {video.get('width')}x{video.get('height')}")
    return {
        "duration_seconds": float(payload["format"]["duration"]),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "resolution": f"{video.get('width')}x{video.get('height')}",
    }


def postprocess_paper(
    context: dict[str, Any],
    tts_results: dict[str, dict[str, Any]],
    segment_executor: ThreadPoolExecutor | None = None,
    ffmpeg_semaphore: threading.Semaphore | None = None,
) -> dict[str, Any]:
    """Post queue: validate audio, reuse page segments, assemble, and ffprobe."""
    sys.path.insert(0, str(VIDEO_SCRIPTS))
    from slides_to_video import (  # type: ignore
        DEFAULT_PLAYBACK_SPEED,
        assemble_video,
    )

    root: Path = context["root"]
    state = load_state(root)
    started = time.perf_counter()
    try:
        failed = [
            task["name"] for task in context["tasks"]
            if tts_results.get(task["name"], {}).get("status") == "failed"
        ]
        if failed:
            raise RuntimeError("TTS failed: " + ", ".join(failed[:10]))
        png_files = exact_slide_files(context["frame_dir"], "png")
        mp3_files = exact_slide_files(context["frame_dir"], "mp3")
        require_matching_slides(png_files, mp3_files, "Audio", root.name)
        previous_audio_hashes = {
            name: values.get("audio_sha256")
            for name, values in state.get("hashes", {}).get("pages", {}).items()
        }
        audio_changed = False
        for name, path in mp3_files.items():
            new_hash = sha256_file(path)
            audio_changed = audio_changed or previous_audio_hashes.get(name) != new_hash
            state["hashes"]["pages"][name]["audio_sha256"] = new_hash
        if audio_changed:
            invalidate_from(state, "tts_done")
        mark_stage(root, state, "tts_done")

        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", root.name).strip("_")
        output = root / "video" / f"{safe_name}_narrated.mp4"
        video_summary = assemble_video(
            str(context["frame_dir"]), str(output), pad_sec=0.5,
            speed=DEFAULT_PLAYBACK_SPEED,
            run_tts=False, segment_executor=segment_executor,
            ffmpeg_semaphore=ffmpeg_semaphore,
        )
        video_hash = sha256_file(output)
        if state["hashes"].get("video_sha256") != video_hash:
            invalidate_from(state, "video_done")
        state["hashes"]["video_sha256"] = video_hash
        mark_stage(root, state, "video_done")
        probe = _ffprobe_video(output)
        state["metrics"].update(probe)
        audio_quality = analyze_audio_quality(output)
        pronunciation_sidecars = sorted(
            context["frame_dir"].glob("slide_*.pronunciation.json")
        )
        if len(pronunciation_sidecars) != len(png_files):
            raise RuntimeError(
                "Pronunciation audit count does not match video pages: "
                f"{len(pronunciation_sidecars)} != {len(png_files)}"
            )
        invalid_pronunciation = []
        for path in pronunciation_sidecars:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("invalid_tokens") or payload.get("valid") is False:
                invalid_pronunciation.append(path.name)
        if invalid_pronunciation:
            raise RuntimeError(
                "Pronunciation audits failed: " + ", ".join(invalid_pronunciation)
            )
        cover = root / "video" / "cover.png"
        cover_hash = sha256_file(cover) if cover.exists() else None
        state["hashes"]["cover_sha256"] = cover_hash
        previous_video_review = state.get("video", {})
        state["audio"] = {
            "pages": len(mp3_files),
            "valid_pages": len(mp3_files),
            "pronunciation_pages_valid": len(pronunciation_sidecars),
            **audio_quality,
        }
        state["video"] = {
            "sha256": video_hash,
            "has_video_stream": True,
            "has_audio_stream": True,
            **probe,
            "sampled": bool(
                previous_video_review.get("sha256") == video_hash
                and previous_video_review.get("sampled") is True
            ),
            "defects": previous_video_review.get("defects", [])
            if previous_video_review.get("sha256") == video_hash else [],
        }
        save_state(root, state)
        return {
            "paper": root.name,
            "status": "video_done",
            "video": str(output),
            "video_summary": video_summary,
            "qa": {**probe, **audio_quality},
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        mark_failure(root, state, "post", exc)
        return {"paper": root.name, "status": "failed", "error": str(exc)}


def run_pipeline(
    papers: list[dict[str, Any]], cpu_workers: int, post_workers: int,
    latex_workers: int, ffmpeg_workers: int,
    config_path: str | None, force_compile: bool,
) -> dict[str, Any]:
    """Run one batch-scoped GPU worker and overlap completed papers with post."""
    sys.path.insert(0, str(VIDEO_SCRIPTS))
    from tts_backends import (  # type: ignore
        load_tts_config,
        run_local_tts_batch,
    )

    started = time.perf_counter()
    prepare_started = time.perf_counter()
    prepared: list[dict[str, Any]] = []
    latex_semaphore = threading.BoundedSemaphore(max(1, latex_workers))
    with ThreadPoolExecutor(max_workers=cpu_workers) as executor:
        futures = {
            executor.submit(prepare_paper, p, force_compile, latex_semaphore): p
            for p in papers
        }
        for future in as_completed(futures):
            prepared.append(future.result())
    prepare_finished = time.perf_counter()
    ready = [item for item in prepared if "error" not in item]
    cpu_failed = [item for item in prepared if "error" in item]

    selected = "indextts2"
    tasks = [task for item in ready for task in item["tasks"]]
    tts_payload: dict[str, Any] = {
        "backend": selected, "tasks": [], "worker_closed": True,
    }
    gpu_error: str | None = None
    config = load_tts_config(config_path)
    normalization_workers = max(
        1, int(config.get("synthesis", {}).get("audio_normalization_workers", 2))
    )
    overlap_enabled = ffmpeg_workers > normalization_workers
    reserved_for_tts = normalization_workers if overlap_enabled else 0
    post_ffmpeg_workers = max(1, ffmpeg_workers - reserved_for_tts)
    ready_by_id = {str(item["paper_id"]): item for item in ready}
    submitted_papers: set[str] = set()
    deferred_events: dict[str, dict[str, Any]] = {}
    post_futures: dict[Any, str] = {}
    post_results: list[dict[str, Any]] = []
    first_post_submitted_at: float | None = None
    post_submitted_before_tts_finished = 0
    tts_started = time.perf_counter()
    tts_finished = tts_started

    # Reserve the TTS normalization workers from the original FFmpeg budget.
    # This keeps the combined number of overlapping FFmpeg processes within
    # the caller's existing --ffmpeg-workers limit.
    ffmpeg_semaphore = threading.BoundedSemaphore(post_ffmpeg_workers)
    with (
        ThreadPoolExecutor(
            max_workers=post_ffmpeg_workers, thread_name_prefix="ffmpeg-segment",
        ) as segment_executor,
        ThreadPoolExecutor(
            max_workers=max(1, post_workers), thread_name_prefix="paper-post",
        ) as post_executor,
    ):
        tts_running = bool(tasks)

        def submit_completed_paper(event: dict[str, Any]) -> None:
            nonlocal first_post_submitted_at, post_submitted_before_tts_finished
            paper_id = str(event["paper_id"])
            if paper_id in submitted_papers or paper_id not in ready_by_id:
                return
            if not overlap_enabled and tts_running:
                deferred_events[paper_id] = event
                return
            task_results = {
                str(item["name"]): item for item in event.get("tasks", [])
            }
            context = ready_by_id[paper_id]
            submitted_papers.add(paper_id)
            submitted_at = time.perf_counter()
            if first_post_submitted_at is None:
                first_post_submitted_at = submitted_at
            if tts_running:
                post_submitted_before_tts_finished += 1
            future = post_executor.submit(
                postprocess_paper,
                context,
                task_results,
                segment_executor,
                ffmpeg_semaphore,
            )
            post_futures[future] = paper_id

        def on_tts_event(event: dict[str, Any]) -> None:
            if event.get("type") == "paper_done":
                submit_completed_paper(event)

        if tasks:
            try:
                # The full batch still performs one G2PW preflight and one
                # IndexTTS2 model load. Each completed paper is released to
                # post-processing while the worker continues with later pages.
                tts_payload = run_local_tts_batch(
                    selected,
                    tasks,
                    config_path=config_path,
                    on_event=on_tts_event,
                )
                tts_payload["worker_closed"] = True
            except Exception as exc:
                gpu_error = str(exc)
            finally:
                tts_running = False
                tts_finished = time.perf_counter()
        else:
            tts_finished = time.perf_counter()

        for event in deferred_events.values():
            submit_completed_paper(event)

        missing_events = sorted(set(ready_by_id) - submitted_papers)
        if missing_events and gpu_error is None:
            gpu_error = "TTS worker did not emit paper_done for: " + ", ".join(missing_events)

        if gpu_error is not None:
            error = RuntimeError(gpu_error)
            for paper_id, item in ready_by_id.items():
                if paper_id not in submitted_papers:
                    state = load_state(item["root"])
                    mark_failure(item["root"], state, "gpu", error)

        for future in as_completed(post_futures):
            post_results.append(future.result())
    post_finished = time.perf_counter()

    summary = {
        "status": "complete" if not cpu_failed and not gpu_error and all(
            item.get("status") != "failed" for item in post_results
        ) else "partial_failure",
        "papers": len(papers),
        "cpu_ready": len(ready),
        "cpu_failed": len(cpu_failed),
        "resources": {
            "cpu_workers": cpu_workers,
            "latex_workers": latex_workers,
            "post_workers": post_workers,
            "ffmpeg_workers_global": ffmpeg_workers,
            "ffmpeg_workers_reserved_for_tts": reserved_for_tts,
            "ffmpeg_workers_available_to_post": post_ffmpeg_workers,
            "per_paper_ffmpeg_pools": 0,
        },
        "gpu": {
            "backend": selected,
            "requested_pages": len(tasks),
            "generated": sum(x.get("status") == "generated" for x in tts_payload.get("tasks", [])),
            "cached": sum(x.get("status") == "cached" for x in tts_payload.get("tasks", [])),
            "failed": sum(x.get("status") == "failed" for x in tts_payload.get("tasks", [])),
            "worker_processes": 1 if tasks else 0,
            "worker_closed": True,
            "error": gpu_error,
        },
        "post": post_results,
        "overlap": {
            "enabled": overlap_enabled,
            "papers_submitted_to_post_before_tts_finished": (
                post_submitted_before_tts_finished
            ),
        },
        "timings": {
            "prepare_wall_seconds": round(prepare_finished - prepare_started, 3),
            "tts_wall_seconds": round(tts_finished - tts_started, 3),
            "post_tail_after_tts_seconds": round(post_finished - tts_finished, 3),
            "post_span_seconds": round(
                post_finished - (first_post_submitted_at or post_finished), 3
            ),
        },
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("papers_json", type=Path)
    parser.add_argument("--cpu-workers", type=int, default=min(4, os.cpu_count() or 2))
    parser.add_argument("--post-workers", type=int, default=2)
    parser.add_argument("--latex-workers", type=int, default=2)
    parser.add_argument("--ffmpeg-workers", type=int, default=min(6, os.cpu_count() or 2))
    parser.add_argument("--tts-config")
    parser.add_argument("--force-compile", action="store_true")
    args = parser.parse_args()
    papers = load_papers(args.papers_json)
    summary = run_pipeline(
        papers, args.cpu_workers, args.post_workers,
        args.latex_workers, args.ffmpeg_workers, args.tts_config,
        force_compile=args.force_compile,
    )
    raise SystemExit(0 if summary["status"] == "complete" else 1)


if __name__ == "__main__":
    main()
