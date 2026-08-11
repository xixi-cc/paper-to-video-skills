#!/usr/bin/env python3
"""Safe, portable Bilibili upload wrapper for Codex.

Use ``--dry-run`` to validate inputs. An actual upload uses the internal
``--confirm-upload`` safety flag after either an explicit publication request
or selection of the parent pipeline's ``bilibili`` mode.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests


COOKIE_PATH = Path(
    os.environ.get("BILIBILI_COOKIE_FILE", Path.home() / ".bilibili" / "cookies.json")
).expanduser()

INTRO_MARKERS = ("本视频", "本期", "这期", "本次视频")


def description_text(metadata: dict) -> str:
    return str(metadata.get("desc") or metadata.get("description") or "").strip()


def has_simple_introduction(description: str) -> bool:
    compact = re.sub(r"\s+", "", description)
    return len(compact) >= 20 and any(marker in description for marker in INTRO_MARKERS)


def has_one_sentence_summary(description: str) -> bool:
    lines = [line.strip() for line in description.splitlines() if line.strip()]
    if not lines:
        return False
    summary = lines[0]
    return (
        summary.startswith("一句话概述：")
        and "重要性在于" in summary
        and len(summary) >= 25
        and summary.endswith(("。", "！", "？"))
        and len(re.findall(r"[。！？]", summary)) == 1
    )


def cookie_values() -> dict[str, str]:
    payload = json.loads(COOKIE_PATH.read_text(encoding="utf-8"))
    records = payload.get("cookie_info", {}).get("cookies", [])
    return {
        str(item["name"]): str(item["value"])
        for item in records
        if isinstance(item, dict) and item.get("name") and item.get("value")
    }


def verify_bvid(title: str, attempts: int = 3) -> tuple[str | None, str | None]:
    """Resolve an exact title through Creator Center without exposing cookies."""
    if not COOKIE_PATH.exists():
        return None, None
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://member.bilibili.com/platform/upload-manager/article",
    }
    statuses = ("pubed", "is_pubing", "not_pubed")
    for attempt in range(attempts):
        for status in statuses:
            response = requests.get(
                "https://member.bilibili.com/x/web/archives",
                params={"status": status, "pn": 1, "ps": 30, "coop": 1, "interactive": 1},
                cookies=cookie_values(), headers=headers, timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                continue
            data = payload.get("data") or {}
            for record in data.get("arc_audits") or []:
                archive = record.get("Archive", {})
                if archive.get("title") == title and archive.get("bvid"):
                    return str(archive["bvid"]), str(archive.get("state_desc") or status)
        if attempt + 1 < attempts:
            time.sleep(3)
    return None, None


def login() -> None:
    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "biliup", "-u", str(COOKIE_PATH), "login"]
    print("Scan the QR code with the Bilibili app.")
    print(f"Cookie file: {COOKIE_PATH}")
    subprocess.run(command, check=True)


def find_cover(paper_dir: Path, video_dir: Path, metadata: dict) -> Path | None:
    """Return a cover derived only from the rendered Beamer title page."""
    configured = metadata.get("cover_path") or "cover.png"
    if configured != "cover.png":
        raise SystemExit(
            "video_meta.json cover_path must be cover.png; the Beamer title page "
            "is the only supported video cover"
        )
    cover = video_dir / "cover.png"
    title_slide = video_dir / "video_frames" / "slide_001.png"
    if title_slide.exists():
        cover.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(title_slide, cover)
        return cover
    if cover.exists():
        return cover
    return None


def resolve_inputs(paper_dir: Path) -> tuple[Path, Path | None, dict]:
    paper_dir = paper_dir.expanduser().resolve()
    video_dir = paper_dir / "video"
    metadata_path = video_dir / "video_meta.json"
    if not metadata_path.exists():
        raise SystemExit(f"Missing metadata: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    videos = sorted(video_dir.glob("*.mp4"))
    if not videos:
        raise SystemExit(f"No MP4 found in {video_dir}")
    return videos[0], find_cover(paper_dir, video_dir, metadata), metadata


def validate_metadata(metadata: dict) -> None:
    title = str(metadata.get("title", "")).strip()
    tags = metadata.get("tag") or metadata.get("tags") or []
    if not title:
        raise SystemExit("Metadata title is empty")
    if len(title) > 80:
        raise SystemExit(f"Metadata title exceeds 80 characters: {len(title)}")
    if not isinstance(tags, list) or not any(str(tag).strip() for tag in tags):
        raise SystemExit("Metadata tags are empty")
    description = description_text(metadata)
    if not has_one_sentence_summary(description):
        raise SystemExit(
            "Metadata description must start with exactly one Chinese sentence: "
            "一句话概述：本文做了什么；其重要性在于什么。"
        )
    if not has_simple_introduction(description):
        raise SystemExit(
            "Metadata description needs a short Chinese introduction containing "
            "本视频、本期、这期, or 本次视频; bibliographic metadata alone is insufficient"
        )
    if metadata.get("copyright", 1) == 2 and not metadata.get("source"):
        raise SystemExit("Reposted content requires metadata.source")


def build_command(video: Path, cover: Path | None, metadata: dict) -> list[str]:
    tags = metadata.get("tag") or metadata.get("tags") or []
    command = [
        sys.executable, "-m", "biliup", "-u", str(COOKIE_PATH),
        "upload", str(video),
        "--title", metadata["title"],
        "--tid", str(metadata.get("tid", 124)),
        "--tag", ",".join(str(tag) for tag in tags[:10]),
        "--desc", description_text(metadata),
        "--copyright", str(metadata.get("copyright", 1)),
        "--no-reprint", str(metadata.get("no_reprint", 0)),
        "--submit", "web",
    ]
    if cover:
        command.extend(["--cover", str(cover)])
    if metadata.get("copyright", 1) == 2:
        command.extend(["--source", str(metadata["source"])])
    if metadata.get("dynamic"):
        command.extend(["--dynamic", str(metadata["dynamic"])[:256]])
    return command


def display_plan(video: Path, cover: Path | None, metadata: dict, command: list[str]) -> None:
    print("Bilibili upload plan")
    print(f"  title: {metadata['title']}")
    print(f"  video: {video} ({video.stat().st_size / 1024 / 1024:.1f} MiB)")
    print(f"  cover: {cover or '(none)'}")
    print(f"  category: {metadata.get('tid', 124)}")
    print(f"  tags: {metadata.get('tag') or metadata.get('tags')}")
    print(f"  description: {description_text(metadata)}")
    print(f"  copyright: {metadata.get('copyright', 1)}")
    sanitized = ["<cookie-file>" if item == str(COOKIE_PATH) else item for item in command]
    print("  command:")
    print("    " + " ".join(repr(item) if " " in item else item for item in sanitized))


def upload(paper_dir: Path, dry_run: bool, confirmed: bool, verify_only: bool = False) -> None:
    video, cover, metadata = resolve_inputs(paper_dir)
    validate_metadata(metadata)
    if verify_only:
        bvid, status = verify_bvid(metadata["title"])
        if not bvid:
            raise SystemExit("Bilibili verification pending: exact title not found")
        print(f"BV: {bvid}")
        print(f"STATUS: {status}")
        print(f"URL: https://www.bilibili.com/video/{bvid}")
        return
    command = build_command(video, cover, metadata)
    display_plan(video, cover, metadata, command)
    if dry_run:
        print("Dry run complete; no network upload was attempted.")
        return
    if not confirmed:
        raise SystemExit("Upload blocked: use --confirm-upload only after publication authorization")
    if not COOKIE_PATH.exists():
        raise SystemExit(f"Cookie file not found: {COOKIE_PATH}; run --login")

    result = subprocess.run(command, capture_output=True, text=True)
    output = result.stdout + result.stderr
    if result.returncode != 0:
        if any(term in output.lower() for term in ("login", "cookie", "expired", "credential", "鉴权")):
            raise SystemExit("Authentication failed; run --login and retry after user confirmation")
        if any(term in output.lower() for term in ("already exists", "duplicate", "已存在")):
            raise SystemExit("Upload may be a duplicate; inspect the Bilibili account before retrying")
        if any(term in output.lower() for term in ("too large", "exceeds", "过大")):
            raise SystemExit("Upload failed because the media exceeds a platform limit")
        if any(term in output.lower() for term in ("rate", "频繁", "过快")):
            raise SystemExit("Upload was rate-limited; do not retry automatically")
        raise SystemExit(f"Upload failed with exit code {result.returncode}: {output[-1000:]}")

    match = re.search(r"BV[0-9A-Za-z]{10}", output)
    bvid = match.group(0) if match else None
    status = None
    if not bvid:
        bvid, status = verify_bvid(metadata["title"])
    if bvid:
        print(f"BV: {bvid}")
        if status:
            print(f"STATUS: {status}")
        print(f"URL: https://www.bilibili.com/video/{bvid}")
    else:
        print("Upload command succeeded, but no BV identifier was found in its output.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Safe Bilibili uploader for Codex")
    parser.add_argument("paper_dir", nargs="?", type=Path)
    parser.add_argument("--login", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-upload", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    if args.login:
        login()
    elif args.paper_dir:
        upload(
            args.paper_dir, dry_run=args.dry_run,
            confirmed=args.confirm_upload, verify_only=args.verify_only,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
