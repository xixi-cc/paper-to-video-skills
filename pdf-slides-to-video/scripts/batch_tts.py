"""Generate slide narration audio with local IndexTTS2."""

from __future__ import annotations

import argparse
from pathlib import Path

from tts_backends import resolve_backend, run_local_tts_batch


def _collect_tasks(
    frame_dir: Path, only_slides: set[int] | None, force: bool,
    include_existing: bool,
) -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    for txt_path in sorted(frame_dir.glob("slide_*.txt")):
        try:
            slide_number = int(txt_path.stem.removeprefix("slide_"))
        except ValueError:
            continue
        if only_slides and slide_number not in only_slides:
            continue
        output = txt_path.with_suffix(".mp3")
        if force:
            output.unlink(missing_ok=True)
            Path(f"{output.with_suffix('')}.tts-cache.json").unlink(missing_ok=True)
        if not include_existing and output.exists() and output.stat().st_size > 500:
            continue
        text = txt_path.read_text(encoding="utf-8").strip()
        if text:
            tasks.append({"name": txt_path.stem, "text": text, "output": str(output)})
    return tasks


def batch_tts(
    frame_dir: str,
    backend: str | None = None,
    config_path: str | None = None,
    max_workers: int = 8,
    max_retries: int = 3,
    lang: str = "zh",
    only_slides: set[int] | None = None,
    force: bool = False,
) -> tuple[int, int]:
    """Run one IndexTTS2 batch; legacy worker/retry arguments are compatibility-only."""
    directory = Path(frame_dir).expanduser().resolve()
    selected = resolve_backend(backend, config_path)
    tasks = _collect_tasks(
        directory, only_slides, force, include_existing=True,
    )
    if not tasks:
        print("All selected MP3s are up to date")
        return 0, 0

    print(f"TTS batch: {len(tasks)} slides, backend={selected}")
    result = run_local_tts_batch(selected, tasks, config_path=config_path)
    failed = [item for item in result.get("tasks", []) if item["status"] == "failed"]
    return len(tasks), len(failed)


def _parse_slide_numbers(value: str | None) -> set[int] | None:
    if not value:
        return None
    return {int(item.strip()) for item in value.split(",") if item.strip()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch slide TTS")
    parser.add_argument("frame_dir")
    parser.add_argument("--backend", choices=("indextts2",), default="indextts2")
    parser.add_argument("--config")
    parser.add_argument("--lang", choices=("zh", "en"), default="zh")
    parser.add_argument(
        "--max-workers", type=int, default=8,
        help="Compatibility option; IndexTTS2 GPU inference remains serial.",
    )
    parser.add_argument(
        "--max-retries", type=int, default=3,
        help="Compatibility option; failed IndexTTS2 pages are not auto-retried.",
    )
    parser.add_argument("--only-slides", help="Comma-separated slide numbers")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    total, failed = batch_tts(
        args.frame_dir,
        backend=args.backend,
        config_path=args.config,
        max_workers=args.max_workers,
        max_retries=args.max_retries,
        lang=args.lang,
        only_slides=_parse_slide_numbers(args.only_slides),
        force=args.force,
    )
    print(f"Done: {total} total, {failed} failed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
