#!/usr/bin/env python3
"""Safe, portable Bilibili upload wrapper for Codex.

Use ``--dry-run`` to validate inputs. An actual upload uses the internal
``--confirm-upload`` safety flag after an explicit publication request.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


COOKIE_PATH = Path(
    os.environ.get("BILIBILI_COOKIE_FILE", Path.home() / ".bilibili" / "cookies.json")
).expanduser()

UPLOAD_RECEIPT = "upload-receipt.json"


def _requests() -> Any:
    try:
        import requests
    except ImportError as error:
        raise SystemExit(
            "Bilibili verification requires requests; install the uploader "
            "environment from ENVIRONMENT.md"
        ) from error
    return requests


def _psutil() -> Any:
    try:
        import psutil
    except ImportError as error:
        raise SystemExit(
            "Lock diagnostics require psutil; install the uploader environment "
            "from ENVIRONMENT.md"
        ) from error
    return psutil


def lock_directories() -> list[Path]:
    candidates: list[Path] = []
    configured = os.environ.get("BILIUP_LOCK_DIR")
    if configured:
        candidates.append(Path(configured).expanduser())
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "biliup" / "locks")
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    candidates.append(cache_root / "biliup" / "locks")
    unique: list[Path] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def is_biliup_command(command: list[str]) -> bool:
    lowered = [str(part).lower() for part in command]
    direct_cli = bool(lowered) and Path(lowered[0]).name.startswith("biliup")
    return direct_cli or any(
        lowered[index:index + 2] == ["-m", "biliup"]
        for index in range(max(0, len(lowered) - 1))
    )


def _lock_snapshot() -> list[dict[str, Any]]:
    psutil = _psutil()
    processes = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            command = process.info.get("cmdline") or [process.info.get("name") or ""]
            if is_biliup_command(command):
                processes.append(process)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    snapshot: list[dict[str, Any]] = []
    for directory in lock_directories():
        if not directory.is_dir():
            snapshot.append({"directory": directory, "exists": False, "locks": []})
            continue
        locks = []
        for lock_path in sorted(directory.glob("*.lock")):
            holders = []
            for process in processes:
                try:
                    open_paths = {Path(item.path).resolve() for item in process.open_files()}
                    if lock_path.resolve() in open_paths:
                        holders.append(process)
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
            locks.append({"path": lock_path, "holders": holders})
        snapshot.append({"directory": directory, "exists": True, "locks": locks})
    return snapshot


def diagnose_locks() -> list[dict[str, Any]]:
    snapshot = _lock_snapshot()
    print("biliup lock diagnosis")
    for directory in snapshot:
        print(f"  directory: {directory['directory']}")
        if not directory["exists"]:
            print("    missing")
            continue
        if not directory["locks"]:
            print("    no lock files")
        for record in directory["locks"]:
            holders = record["holders"]
            state = "ACTIVE" if holders else "STALE"
            pids = ",".join(str(process.pid) for process in holders) or "none"
            print(f"    [{state}] {record['path'].name} holders={pids}")
    return snapshot


def cleanup_locks(confirmed: bool, force_kill: bool = False) -> None:
    if not confirmed:
        raise SystemExit(
            "Cleanup blocked: use --confirm-cleanup after explicitly authorizing "
            "termination of biliup lock holders and removal of stale lock files"
        )
    psutil = _psutil()
    snapshot = diagnose_locks()
    holders = {
        process.pid: process
        for directory in snapshot
        for record in directory["locks"]
        for process in record["holders"]
    }
    for process in holders.values():
        try:
            print(f"  terminating biliup PID {process.pid}")
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(list(holders.values()), timeout=5)
    if alive and force_kill:
        for process in alive:
            try:
                print(f"  force-killing biliup PID {process.pid}")
                process.kill()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(alive, timeout=5)
    if alive:
        raise SystemExit(
            "Some biliup processes are still active; stale locks were not removed. "
            "Review the diagnosis or rerun with --force-kill after explicit authorization."
        )
    refreshed = _lock_snapshot()
    removed = 0
    for directory in refreshed:
        for record in directory["locks"]:
            if record["holders"]:
                continue
            try:
                record["path"].unlink()
                removed += 1
                print(f"  removed stale lock: {record['path']}")
            except FileNotFoundError:
                pass
    print(f"Cleanup complete; removed {removed} stale lock file(s).")


def description_text(metadata: dict) -> str:
    return str(metadata.get("desc") or metadata.get("description") or "").strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upload_fingerprint(video: Path, cover: Path | None, metadata: dict) -> str:
    value = {
        "video": sha256_file(video),
        "cover": sha256_file(cover) if cover else None,
        "metadata": metadata,
    }
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    temporary.replace(path)


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
    requests = _requests()
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
    if not description:
        raise SystemExit("Metadata description is empty")
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
    receipt_path = paper_dir.expanduser().resolve() / "video" / UPLOAD_RECEIPT
    fingerprint = upload_fingerprint(video, cover, metadata)
    if verify_only:
        bvid, status = verify_bvid(metadata["title"])
        if not bvid:
            raise SystemExit("Bilibili verification pending: exact title not found")
        receipt = {
            "success": True,
            "fingerprint": fingerprint,
            "bvid": bvid,
            "verification_required": False,
            "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        atomic_json(receipt_path, receipt)
        print(f"BV: {bvid}")
        print(f"STATUS: {status}")
        print(f"URL: https://www.bilibili.com/video/{bvid}")
        return
    command = build_command(video, cover, metadata)
    display_plan(video, cover, metadata, command)
    if dry_run:
        if receipt_path.exists():
            print(f"  existing receipt: {receipt_path}")
        print("Dry run complete; no network upload was attempted.")
        return
    if not confirmed:
        raise SystemExit("Upload blocked: use --confirm-upload only after publication authorization")
    if not COOKIE_PATH.exists():
        raise SystemExit(f"Cookie file not found: {COOKIE_PATH}; run --login")

    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("success"):
            if receipt.get("fingerprint") != fingerprint:
                raise SystemExit(
                    "A verified upload receipt exists for different content; "
                    "replace the existing submission explicitly instead of uploading again"
                )
            if receipt.get("bvid") and not receipt.get("verification_required"):
                print(f"BV: {receipt['bvid']}")
                print(f"URL: https://www.bilibili.com/video/{receipt['bvid']}")
                print("Upload skipped; matching verified receipt already exists.")
                return
            bvid, status = verify_bvid(metadata["title"])
            if not bvid:
                raise SystemExit(
                    "A matching upload may already have succeeded; exact-title "
                    "verification is still pending, so resubmission is blocked"
                )
            receipt.update({
                "bvid": bvid,
                "verification_required": False,
                "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            atomic_json(receipt_path, receipt)
            print(f"BV: {bvid}")
            if status:
                print(f"STATUS: {status}")
            print(f"URL: https://www.bilibili.com/video/{bvid}")
            return

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
    receipt = {
        "success": True,
        "fingerprint": fingerprint,
        "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bvid": bvid,
        "verification_required": bvid is None,
    }
    atomic_json(receipt_path, receipt)
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
    parser.add_argument("--diagnose-locks", action="store_true")
    parser.add_argument("--cleanup-locks", action="store_true")
    parser.add_argument("--confirm-cleanup", action="store_true")
    parser.add_argument("--force-kill", action="store_true")
    args = parser.parse_args()

    if args.login:
        login()
    elif args.diagnose_locks:
        diagnose_locks()
    elif args.cleanup_locks:
        cleanup_locks(args.confirm_cleanup, force_kill=args.force_kill)
    elif args.paper_dir:
        upload(
            args.paper_dir, dry_run=args.dry_run,
            confirmed=args.confirm_upload, verify_only=args.verify_only,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
