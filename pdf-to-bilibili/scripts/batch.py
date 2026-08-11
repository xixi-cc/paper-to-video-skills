#!/usr/bin/env python3
"""Resumable three-stage batch pipeline for paper videos.

CPU preparation is parallel, all local-TTS tasks share one GPU worker process,
and video/QA is parallel.  Selecting ``bilibili`` is publication authority;
the script still dry-runs every upload and records an idempotency receipt.

Usage:
    python batch.py status papers.json
    python batch.py compile papers.json --cpu-workers 4
    python batch.py video papers.json --cpu-workers 4 --post-workers 2
    python batch.py bilibili papers.json --cpu-workers 4 --post-workers 2
    python batch.py finalize papers.json
    python batch.py finalize papers.json --apply-finalize
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
UPLOAD_SCRIPT = SUITE_DIR / "bilibili-video-uploader" / "scripts" / "upload.py"
FINALIZE_SCRIPT = SUITE_DIR / "pdf-to-bilibili" / "scripts" / "finalize_artifacts.py"
MANIFEST_SCRIPT_DIR = SUITE_DIR / "pdf-to-bilibili" / "scripts"
UPLOAD_VENV_PYTHON = SUITE_DIR / "bilibili-video-uploader" / ".venv" / "bin" / "python"
STATE_FILE = "pipeline-state.json"
UPLOAD_RECEIPT = "upload-receipt.json"
STAGES = (
    "queued", "slides_done", "narration_done", "tts_done",
    "video_done", "qa_passed", "uploaded",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_visual_receipt(
    path: Path,
    artifact_hash: str,
    hash_key: str,
    reviewed_key: str,
) -> dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"Missing visual QA receipt: {path}")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get(hash_key) != artifact_hash:
        raise RuntimeError(f"Visual QA receipt is stale for {path}")
    if receipt.get(reviewed_key) is not True:
        raise RuntimeError(f"Visual QA is incomplete in {path}")
    if reviewed_key == "all_pages_reviewed":
        if receipt.get("standalone_readability_reviewed") is not True:
            raise RuntimeError(
                f"Standalone slide readability was not reviewed in {path}"
            )
        if receipt.get("sparse_pages"):
            raise RuntimeError(
                f"Sparse or narration-dependent slides remain in {path}: "
                f"{receipt['sparse_pages']}"
            )
    if receipt.get("defects"):
        raise RuntimeError(f"Visual QA defects remain in {path}: {receipt['defects']}")
    return receipt


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
    state.setdefault("schema_version", 1)
    state.setdefault("paper", root.name)
    state.setdefault("stages", {stage: False for stage in STAGES})
    for stage in STAGES:
        state["stages"].setdefault(stage, False)
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
    if len(re.findall(r"\\ph\{", content)) > 5:
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
    """CPU queue: compile, render, align narrations, and collect page hashes."""
    sys.path.insert(0, str(VIDEO_SCRIPTS))
    from slides_to_video import (  # type: ignore
        generate_cover,
        render_slides,
        write_narrations_to_files,
    )

    root = paper_dir(paper)
    state = load_state(root)
    started = time.perf_counter()
    try:
        manifest_path = root / "paper_presentation.json"
        manifest_result = None
        if manifest_path.exists():
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
        annotation = root / "video" / "main_with_narration.tex"
        plan_tex = (
            Path(manifest_result["frames_tex"])
            if manifest_result is not None else slides_tex
        )
        if not annotation.exists():
            raise FileNotFoundError(f"Missing narrated TeX: {annotation}")

        previous_pdf_hash = state["hashes"].get("slides_pdf_sha256")
        previous_tex_hash = state["hashes"].get("slides_tex_sha256")
        previous_annotation_hash = state["hashes"].get("narrated_tex_sha256")
        pdf_hash = sha256_file(slides_pdf)
        tex_hash = sha256_file(slides_tex)
        annotation_hash = sha256_file(annotation)
        if previous_pdf_hash != pdf_hash or previous_tex_hash != tex_hash:
            invalidate_from(state, "slides_done")
        elif previous_annotation_hash != annotation_hash:
            invalidate_from(state, "narration_done")
        state["hashes"].update({
            "slides_pdf_sha256": pdf_hash,
            "slides_tex_sha256": tex_hash,
            "narrated_tex_sha256": annotation_hash,
        })
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
        title_slide = png_files.get("slide_001")
        if title_slide is None:
            raise RuntimeError(f"Missing rendered Beamer title page for {root.name}")
        generate_cover(str(title_slide), str(root / "video" / "cover.png"))

        if manifest_result is not None:
            slide_visual_qa = require_visual_receipt(
                root / "slides-beamer" / "visual-qa.json",
                pdf_hash,
                "slides_pdf_sha256",
                "all_pages_reviewed",
            )
            if slide_visual_qa.get("page_count") != len(png_files):
                raise RuntimeError(
                    "Slide visual QA page count does not match the rendered PDF: "
                    f"{slide_visual_qa.get('page_count')} != {len(png_files)}"
                )
            state["hashes"]["slide_visual_qa_sha256"] = sha256_file(
                root / "slides-beamer" / "visual-qa.json"
            )

        _prune_unexpected_frames(frame_dir, set(png_files))
        narration_result = write_narrations_to_files(
            str(frame_dir), str(plan_tex), annotated_tex_path=str(annotation),
            # A manifest is the source of truth and contains one narration for
            # every explicit video page.  Synthesizing additional narration
            # from \section markers creates orphan text files whenever the deck
            # intentionally suppresses automatic section-transition frames.
            # Preserve the legacy behavior only for non-manifest projects.
            narrate_sections=manifest_result is None,
        )
        txt_files = exact_slide_files(frame_dir, "txt")
        require_matching_slides(png_files, txt_files, "Narration", root.name)
        narration_chars = sum(
            len(path.read_text(encoding="utf-8").strip()) for path in txt_files.values()
        )
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
        manifest_path = root / "paper_presentation.json"
        quality_report: dict[str, Any] | None = None
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            duration_target = manifest.get("quality", {}).get("target_duration_minutes", [])
            if not (
                isinstance(duration_target, list) and len(duration_target) == 2
                and duration_target[0] * 60 <= probe["duration_seconds"] <= duration_target[1] * 60
            ):
                raise RuntimeError(
                    f"Video duration {probe['duration_seconds'] / 60:.2f} min is outside "
                    f"the manifest quality target {duration_target} min"
                )
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
            quality_report = {
                "valid": False,
                "automated_checks_passed": True,
                "video_sha256": video_hash,
                "duration_seconds": probe["duration_seconds"],
                "target_duration_minutes": duration_target,
                "pages": len(png_files),
                "pronunciation_pages_valid": len(pronunciation_sidecars),
                **audio_quality,
                "checked_at": utc_now(),
            }
            atomic_json(root / "video" / "quality-audit.json", quality_report)
        metadata = root / "video" / "video_meta.json"
        cover = root / "video" / "cover.png"
        metadata_hash = sha256_file(metadata) if metadata.exists() else None
        cover_hash = sha256_file(cover) if cover.exists() else None
        if (
            state["hashes"].get("metadata_sha256") != metadata_hash
            or state["hashes"].get("cover_sha256") != cover_hash
        ):
            state["stages"]["uploaded"] = False
        state["hashes"]["metadata_sha256"] = metadata_hash
        state["hashes"]["cover_sha256"] = cover_hash
        if quality_report is not None:
            video_visual_path = root / "video" / "video-visual-qa.json"
            try:
                video_visual = require_visual_receipt(
                    video_visual_path,
                    video_hash,
                    "video_sha256",
                    "all_samples_reviewed",
                )
            except RuntimeError as exc:
                quality_report["video_visual_qa"] = str(exc)
                atomic_json(root / "video" / "quality-audit.json", quality_report)
                state["status"] = "awaiting_video_visual_qa"
                state["last_error"] = None
                save_state(root, state)
                return {
                    "paper": root.name,
                    "status": "awaiting_video_visual_qa",
                    "video": str(output),
                    "video_summary": video_summary,
                    "qa": {**probe, **quality_report},
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                }
            quality_report["valid"] = True
            quality_report["video_visual_qa_sha256"] = sha256_file(video_visual_path)
            quality_report["sampled_video_seconds"] = video_visual.get(
                "sampled_video_seconds", []
            )
            atomic_json(root / "video" / "quality-audit.json", quality_report)
            state["hashes"]["video_visual_qa_sha256"] = sha256_file(video_visual_path)
        mark_stage(root, state, "qa_passed")
        return {
            "paper": root.name,
            "status": "qa_passed",
            "video": str(output),
            "video_summary": video_summary,
            "qa": probe,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        mark_failure(root, state, "post", exc)
        return {"paper": root.name, "status": "failed", "error": str(exc)}


def resolve_biliup_python() -> Path:
    override = os.environ.get("BILIUP_PYTHON")
    candidates = [Path(override).expanduser() if override else None, UPLOAD_VENV_PYTHON, Path(sys.executable)]
    for candidate in candidates:
        if not candidate or not candidate.exists():
            continue
        probe = subprocess.run(
            [str(candidate), "-c", "import biliup"], capture_output=True, text=True,
        )
        if probe.returncode == 0:
            return candidate
    raise RuntimeError(
        "No reusable biliup environment found. Create bilibili-video-uploader/.venv once; "
        "the batch pipeline never installs into system Python."
    )


def upload_paper(context: dict[str, Any]) -> dict[str, Any]:
    """Upload once after dry-run; an existing matching receipt prevents duplicates."""
    root: Path = context["root"]
    state = load_state(root)
    try:
        video_dir = root / "video"
        quality_audit = video_dir / "quality-audit.json"
        if not quality_audit.exists():
            raise RuntimeError("Missing video/quality-audit.json; refusing publication")
        quality = json.loads(quality_audit.read_text(encoding="utf-8"))
        if not quality.get("valid"):
            raise RuntimeError("Quality audit did not pass; refusing publication")
        videos = sorted(video_dir.glob("*.mp4"))
        metadata = video_dir / "video_meta.json"
        if not videos or not metadata.exists():
            raise RuntimeError("Upload inputs are incomplete")
        if quality.get("video_sha256") != sha256_file(videos[0]):
            raise RuntimeError("Quality audit does not match the current video; refusing publication")
        require_visual_receipt(
            video_dir / "video-visual-qa.json",
            sha256_file(videos[0]),
            "video_sha256",
            "all_samples_reviewed",
        )
        slides_pdf = root / "slides-beamer" / "main.pdf"
        require_visual_receipt(
            root / "slides-beamer" / "visual-qa.json",
            sha256_file(slides_pdf),
            "slides_pdf_sha256",
            "all_pages_reviewed",
        )
        cover = video_dir / "cover.png"
        fingerprint = sha256_json({
            "video": sha256_file(videos[0]),
            "metadata": sha256_file(metadata),
            "cover": sha256_file(cover) if cover.exists() else None,
        })
        receipt_path = video_dir / UPLOAD_RECEIPT
        if not receipt_path.exists():
            # Migrate older successful runs so adopting this orchestrator never
            # republishes an already submitted video.
            for legacy_path in (video_dir / "generation_metrics.json", video_dir / "pipeline-summary.json"):
                if not legacy_path.exists():
                    continue
                try:
                    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                legacy_bvid = legacy.get("bilibili_bvid") or legacy.get("bvid")
                if legacy_bvid:
                    atomic_json(receipt_path, {
                        "success": True,
                        "fingerprint": fingerprint,
                        "submitted_at": legacy.get("upload_verified_at") or utc_now(),
                        "bvid": legacy_bvid,
                        "verification_required": False,
                        "migrated_from": str(legacy_path),
                    })
                    break
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if receipt.get("fingerprint") == fingerprint and receipt.get("success"):
                if receipt.get("bvid") and not receipt.get("verification_required"):
                    mark_stage(root, state, "uploaded", cached_receipt=True)
                    return {"paper": root.name, "status": "uploaded", "cached": True, **receipt}
                # The network submission succeeded earlier but biliup did not
                # return a BV id. Verify the exact title; never resubmit a
                # pending receipt because that can create a duplicate video.
                python = resolve_biliup_python()
                verify = subprocess.run(
                    [str(python), str(UPLOAD_SCRIPT), str(root), "--verify-only"],
                    capture_output=True, text=True,
                )
                match = re.search(r"BV[0-9A-Za-z]{10}", verify.stdout + verify.stderr)
                if match:
                    receipt["bvid"] = match.group(0)
                    receipt["verification_required"] = False
                    receipt["verified_at"] = utc_now()
                    atomic_json(receipt_path, receipt)
                    mark_stage(root, state, "uploaded", cached_receipt=True, bvid=receipt["bvid"])
                    return {"paper": root.name, "status": "uploaded", "cached": True, **receipt}
                state["status"] = "verification_pending"
                save_state(root, state)
                return {"paper": root.name, "status": "verification_pending", **receipt}
            if receipt.get("success"):
                raise RuntimeError(
                    "An earlier successful upload receipt exists but its content hash differs. "
                    "Refusing to create a duplicate; update or replace the existing Bilibili submission explicitly."
                )

        python = resolve_biliup_python()
        dry = subprocess.run(
            [str(python), str(UPLOAD_SCRIPT), str(root), "--dry-run"],
            capture_output=True, text=True,
        )
        if dry.returncode != 0:
            raise RuntimeError("Upload dry-run failed: " + (dry.stderr or dry.stdout)[-1000:])
        actual = subprocess.run(
            [str(python), str(UPLOAD_SCRIPT), str(root), "--confirm-upload"],
            capture_output=True, text=True,
        )
        output = actual.stdout + actual.stderr
        log = video_dir / "bilibili-upload.log"
        log.write_text(dry.stdout + dry.stderr + "\n" + output, encoding="utf-8")
        if actual.returncode != 0:
            raise RuntimeError("Upload failed: " + output[-1000:])
        match = re.search(r"BV[0-9A-Za-z]{10}", output)
        receipt = {
            "success": True,
            "fingerprint": fingerprint,
            "submitted_at": utc_now(),
            "bvid": match.group(0) if match else None,
            "verification_required": match is None,
            "log": str(log),
        }
        atomic_json(receipt_path, receipt)
        if receipt["bvid"]:
            receipt["verification_required"] = False
            atomic_json(receipt_path, receipt)
            mark_stage(root, state, "uploaded", bvid=receipt["bvid"])
            return {"paper": root.name, "status": "uploaded", **receipt}
        state["status"] = "verification_pending"
        save_state(root, state)
        return {"paper": root.name, "status": "verification_pending", **receipt}
    except Exception as exc:
        mark_failure(root, state, "upload", exc)
        return {"paper": root.name, "status": "failed", "error": str(exc)}


def compile_existing(
    papers: list[dict[str, Any]], workers: int, latex_workers: int, force: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    latex_semaphore = threading.BoundedSemaphore(max(1, latex_workers))

    def render_then_compile(paper: dict[str, Any]) -> None:
        root = paper_dir(paper)
        if (root / "paper_presentation.json").exists():
            sys.path.insert(0, str(MANIFEST_SCRIPT_DIR))
            from presentation_manifest import render_manifest  # type: ignore
            render_manifest(root)
        compile_deck(root, force, latex_semaphore)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(render_then_compile, p): p
            for p in papers
        }
        for future in as_completed(futures):
            root = paper_dir(futures[future])
            try:
                future.result()
                results.append({"paper": root.name, "status": "slides_done"})
            except Exception as exc:
                results.append({"paper": root.name, "status": "failed", "error": str(exc)})
    return results


def run_pipeline(
    papers: list[dict[str, Any]], cpu_workers: int, post_workers: int,
    latex_workers: int, ffmpeg_workers: int,
    backend: str | None, config_path: str | None, upload: bool,
    force_compile: bool,
) -> dict[str, Any]:
    """Run one batch-scoped GPU worker and overlap completed papers with post."""
    sys.path.insert(0, str(VIDEO_SCRIPTS))
    from tts_backends import (  # type: ignore
        load_tts_config,
        resolve_backend,
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

    selected = resolve_backend(backend, config_path)
    if selected != "indextts2":
        raise ValueError("The production GPU queue supports IndexTTS2 only")
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

        # Preserve compatibility if an older worker returns only the final
        # result marker, and release deferred papers when overlap was disabled
        # because the configured FFmpeg budget was too small.
        final_results = {
            str(item["name"]): item for item in tts_payload.get("tasks", [])
        }
        for paper_id, context in ready_by_id.items():
            if paper_id in submitted_papers:
                continue
            event = deferred_events.get(paper_id)
            if event is None:
                names = [str(task["name"]) for task in context["tasks"]]
                if all(name in final_results for name in names):
                    event = {
                        "type": "paper_done",
                        "paper_id": paper_id,
                        "tasks": [final_results[name] for name in names],
                    }
            if event is not None:
                submit_completed_paper(event)

        if gpu_error is not None:
            error = RuntimeError(gpu_error)
            for paper_id, item in ready_by_id.items():
                if paper_id not in submitted_papers:
                    state = load_state(item["root"])
                    mark_failure(item["root"], state, "gpu", error)

        for future in as_completed(post_futures):
            post_results.append(future.result())
    post_finished = time.perf_counter()

    upload_started = time.perf_counter()
    upload_results: list[dict[str, Any]] = []
    if upload:
        passed_names = {
            result["paper"] for result in post_results if result.get("status") == "qa_passed"
        }
        # Keep publishing serial to avoid account rate-limit bursts. Ordinary
        # paper failures remain isolated, but a platform rate limit is global:
        # trip a circuit breaker and defer the rest instead of hammering the
        # account with requests that are certain to fail.
        rate_limited = False
        for item in ready:
            if item["root"].name in passed_names:
                if rate_limited:
                    upload_results.append({
                        "paper": item["root"].name,
                        "status": "deferred_rate_limit",
                    })
                    continue
                result = upload_paper(item)
                upload_results.append(result)
                if "rate-limit" in str(result.get("error", "")).lower():
                    rate_limited = True
    upload_finished = time.perf_counter()

    summary = {
        "status": "complete" if not cpu_failed and not gpu_error and all(
            item.get("status") != "failed" for item in post_results + upload_results
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
        "uploads": upload_results,
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
            "upload_wall_seconds": round(upload_finished - upload_started, 3),
        },
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def print_dashboard(papers: list[dict[str, Any]]) -> None:
    rows = []
    for paper in papers:
        root = paper_dir(paper)
        state = load_state(root)
        save_state(root, state)
        rows.append({
            "paper": root.name,
            "status": state.get("status", "queued"),
            "stages": state["stages"],
            "last_error": state.get("last_error"),
        })
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def finalize_papers(
    papers: list[dict[str, Any]], apply: bool = False,
) -> dict[str, Any]:
    """Finalize uploaded papers serially, isolating paper-level failures.

    Cleanup is deliberately not parallel: each paper is destructive only when
    ``apply`` is true, and serial execution keeps the audit output unambiguous.
    """
    results: list[dict[str, Any]] = []
    for paper in papers:
        root = paper_dir(paper)
        command = [sys.executable, str(FINALIZE_SCRIPT), str(root)]
        if apply:
            command.append("--apply")
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout).strip()
            results.append({
                "paper": root.name,
                "status": "failed",
                "mode": "applied" if apply else "dry-run",
                "error": message[-2000:],
            })
            continue
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            results.append({
                "paper": root.name,
                "status": "failed",
                "mode": "applied" if apply else "dry-run",
                "error": f"Finalizer returned invalid JSON: {exc}",
            })
            continue
        results.append({
            "paper": root.name,
            "status": "finalized" if apply else "ready_to_finalize",
            **payload,
        })
    failures = sum(item.get("status") == "failed" for item in results)
    return {
        "status": "complete" if failures == 0 else "partial_failure",
        "mode": "applied" if apply else "dry-run",
        "papers": len(papers),
        "failed": failures,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=["status", "compile", "video", "bilibili", "finalize"],
    )
    parser.add_argument("papers_json", type=Path)
    parser.add_argument("--cpu-workers", type=int, default=min(4, os.cpu_count() or 2))
    parser.add_argument("--post-workers", type=int, default=2)
    parser.add_argument("--latex-workers", type=int, default=2)
    parser.add_argument("--ffmpeg-workers", type=int, default=min(6, os.cpu_count() or 2))
    parser.add_argument("--backend", choices=["indextts2"], default="indextts2")
    parser.add_argument("--tts-config")
    parser.add_argument("--force-compile", action="store_true")
    parser.add_argument(
        "--confirm-upload", action="store_true",
        help="Deprecated compatibility flag; bilibili mode already grants upload authority.",
    )
    parser.add_argument(
        "--apply-finalize", action="store_true",
        help=(
            "Apply final artifact cleanup. Without this flag, finalize mode is a "
            "non-mutating dry-run."
        ),
    )
    args = parser.parse_args()
    papers = load_papers(args.papers_json)
    if args.mode == "status":
        print_dashboard(papers)
        return
    if args.mode == "compile":
        print(json.dumps(
            compile_existing(
                papers, args.cpu_workers, args.latex_workers, args.force_compile,
            ),
            ensure_ascii=False, indent=2,
        ))
        return
    if args.mode == "finalize":
        summary = finalize_papers(papers, apply=args.apply_finalize)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        raise SystemExit(0 if summary["status"] == "complete" else 1)
    summary = run_pipeline(
        papers, args.cpu_workers, args.post_workers,
        args.latex_workers, args.ffmpeg_workers, args.backend,
        args.tts_config, upload=args.mode == "bilibili",
        force_compile=args.force_compile,
    )
    raise SystemExit(0 if summary["status"] == "complete" else 1)


if __name__ == "__main__":
    main()
