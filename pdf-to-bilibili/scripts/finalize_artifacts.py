#!/usr/bin/env python3
"""Create three final deliverables and optionally purge redundant work files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BV_PATTERN = re.compile(r"BV[0-9A-Za-z]{10}")
WORK_DIRECTORIES = ("source", "evidence", "slides-beamer", "video")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def locate_inputs(root: Path) -> dict[str, Path]:
    article_candidates = sorted((root / "source").glob("*.pdf"))
    article = next((path for path in article_candidates if path.name == "paper.pdf"), None)
    article = article or (article_candidates[0] if article_candidates else None)
    beamer = root / "slides-beamer" / "main.pdf"
    videos = sorted((root / "video").glob("*_narrated.mp4"))
    if article is None or not article.is_file():
        raise FileNotFoundError("Could not locate the source paper PDF")
    if not beamer.is_file():
        raise FileNotFoundError(beamer)
    if len(videos) != 1:
        raise RuntimeError(f"Expected one narrated MP4; found {len(videos)}")
    return {"article": article, "beamer": beamer, "video": videos[0]}


def validate_completion(root: Path, inputs: dict[str, Path]) -> dict[str, Any]:
    state = load_json(root / "video" / "pipeline-state.json")
    quality = load_json(root / "video" / "quality-audit.json")
    receipt = load_json(root / "video" / "upload-receipt.json")
    bvid = receipt.get("bvid")
    if state.get("status") != "uploaded":
        raise RuntimeError("Pipeline state is not uploaded")
    if quality.get("valid") is not True:
        raise RuntimeError("Final quality audit is not valid")
    if not isinstance(bvid, str) or not BV_PATTERN.fullmatch(bvid):
        raise RuntimeError("Upload receipt has no verified BVID")
    video_hash = sha256_file(inputs["video"])
    if quality.get("video_sha256") != video_hash:
        raise RuntimeError("Quality audit does not match the final video")
    return {"state": state, "quality": quality, "receipt": receipt, "bvid": bvid}


def copy_if_changed(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and sha256_file(source) == sha256_file(target):
        return
    temporary = target.with_suffix(target.suffix + ".tmp")
    shutil.copy2(source, temporary)
    temporary.replace(target)


def prepare_outputs(
    root: Path, inputs: dict[str, Path], completion: dict[str, Any], apply: bool,
) -> dict[str, Any]:
    final_dir = root / "final"
    pipeline_dir = root / ".pipeline"
    final_paths = {
        "article": final_dir / "article.pdf",
        "beamer": final_dir / "beamer.pdf",
        "video": final_dir / "video.mp4",
    }
    if apply:
        for key, source in inputs.items():
            copy_if_changed(source, final_paths[key])
        manifest = root / "paper_presentation.json"
        copy_if_changed(manifest, pipeline_dir / manifest.name)
        figures = root / "slides-beamer" / "figures"
        figure_target = pipeline_dir / "figures"
        if figure_target.exists():
            shutil.rmtree(figure_target)
        if figures.exists():
            shutil.copytree(figures, figure_target)
        cover = root / "video" / "cover.png"
        if cover.exists():
            copy_if_changed(cover, pipeline_dir / "cover.png")

    hashes = {
        key: sha256_file(path if not apply else final_paths[key])
        for key, path in inputs.items()
    }
    record = {
        "schema_version": 1,
        "finalized_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bvid": completion["bvid"],
        "deliverables": {
            key: {"path": str(final_paths[key]), "sha256": hashes[key]}
            for key in final_paths
        },
        "quality_audit": completion["quality"],
        "upload_receipt": completion["receipt"],
        "pipeline_state": completion["state"],
    }
    if apply:
        pipeline_dir.mkdir(parents=True, exist_ok=True)
        (pipeline_dir / "production-record.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return record


def purge_work_files(root: Path) -> list[str]:
    removed: list[str] = []
    for name in WORK_DIRECTORIES:
        target = (root / name).resolve()
        if target.parent != root or target.name != name:
            raise RuntimeError(f"Unsafe cleanup target: {target}")
        if target.exists():
            shutil.rmtree(target)
            removed.append(str(target))
    manifest = root / "paper_presentation.json"
    if manifest.exists():
        manifest.unlink()
        removed.append(str(manifest))
    return removed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paper_dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = args.paper_dir.expanduser().resolve()
    if root == Path("/") or root.parent == root:
        raise RuntimeError(f"Unsafe paper directory: {root}")
    inputs = locate_inputs(root)
    completion = validate_completion(root, inputs)
    record = prepare_outputs(root, inputs, completion, args.apply)
    removed = purge_work_files(root) if args.apply else [
        str(root / name) for name in WORK_DIRECTORIES
    ] + [str(root / "paper_presentation.json")]
    result = {
        "mode": "applied" if args.apply else "dry-run",
        "paper_dir": str(root),
        "final_dir": str(root / "final"),
        "pipeline_dir": str(root / ".pipeline"),
        "bvid": completion["bvid"],
        "would_remove" if not args.apply else "removed": removed,
        "record": record,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
