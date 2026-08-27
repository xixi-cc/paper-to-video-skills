#!/usr/bin/env python3
"""Convert a document to Markdown with a local or hosted MinerU engine.

The local engine calls MinerU's in-process API. The open-api engine invokes
``mineru-open-api extract`` and therefore uploads the input document to the
configured MinerU service. API tokens stay in the CLI's user config or the
``MINERU_TOKEN`` environment variable; this wrapper never reads or prints them.

Usage:
    python convert.py INPUT OUTPUT_DIR --engine open-api [--lang en]
    python convert.py INPUT OUTPUT_DIR --engine local [--backend pipeline]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


OPEN_API_ENV = "MINERU_OPEN_API_BIN"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Document -> Markdown via MinerU.")
    parser.add_argument("input", help="Input PDF/image/office document.")
    parser.add_argument("output_dir", help="Dedicated output directory.")
    parser.add_argument(
        "--engine",
        choices=("local", "open-api"),
        default="local",
        help=(
            "MinerU execution engine. 'local' keeps the document on this "
            "machine; 'open-api' uploads it to the configured MinerU service. "
            "Default: local."
        ),
    )
    parser.add_argument(
        "--lang",
        default="ch",
        help="Document/OCR language. 'ch' handles mixed EN+CN. Default: ch.",
    )
    parser.add_argument(
        "--backend",
        default="pipeline",
        help="Local MinerU backend. Default: pipeline.",
    )
    parser.add_argument(
        "--method",
        default="auto",
        choices=("auto", "txt", "ocr"),
        help="Local pipeline parse method. Default: auto.",
    )
    parser.add_argument(
        "--api-model",
        default="auto",
        choices=("auto", "vlm", "pipeline", "html"),
        help="MinerU Open API model. Default: auto.",
    )
    parser.add_argument(
        "--pages",
        help="Optional Open API page range, for example '1-10,15'.",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Enable OCR explicitly for the Open API engine.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Open API timeout in seconds. Default: 300.",
    )
    return parser


def resolve_open_api_binary() -> str:
    configured = os.environ.get(OPEN_API_ENV)
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise SystemExit(f"{OPEN_API_ENV} is not an executable file: {path}")
        return str(path)

    discovered = shutil.which("mineru-open-api")
    if discovered is None:
        raise SystemExit(
            "mineru-open-api is not on PATH. Install it or set "
            f"{OPEN_API_ENV} to its executable path."
        )
    return discovered


def build_open_api_command(
    binary: str,
    src: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> list[str]:
    command = [
        binary,
        "extract",
        str(src),
        "--output",
        str(output_dir),
        "--format",
        "md",
        "--language",
        args.lang,
        "--model",
        args.api_model,
        "--timeout",
        str(args.timeout),
    ]
    if args.pages:
        command.extend(("--pages", args.pages))
    if args.ocr:
        command.append("--ocr")
    return command


def run_open_api(src: Path, output_dir: Path, args: argparse.Namespace) -> Path:
    binary = resolve_open_api_binary()
    command = build_open_api_command(binary, src, output_dir, args)
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as error:
        raise SystemExit(
            "MinerU Open API extraction failed. Check `mineru-open-api auth "
            "--verify`, connectivity, quota, and the error above."
        ) from error

    markdown_path = output_dir / f"{src.stem}.md"
    if not markdown_path.is_file():
        candidates = sorted(output_dir.rglob("*.md"))
        if len(candidates) != 1:
            raise SystemExit(
                "MinerU Open API completed but the Markdown output could not "
                f"be identified under {output_dir}."
            )
        markdown_path = candidates[0]
    return markdown_path


def run_local(src: Path, output_dir: Path, args: argparse.Namespace) -> Path:
    try:
        from mineru.cli.common import do_parse, read_fn
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "MinerU is not installed in this Python environment. Use an "
            "isolated local MinerU environment, or explicitly select "
            "`--engine open-api` after authorizing remote document upload."
        ) from exc

    do_parse(
        output_dir=str(output_dir),
        pdf_file_names=[src.stem],
        pdf_bytes_list=[read_fn(src)],
        p_lang_list=[args.lang],
        backend=args.backend,
        parse_method=args.method,
    )
    markdown_path = output_dir / src.stem / args.method / f"{src.stem}.md"
    if not markdown_path.is_file():
        candidates = sorted((output_dir / src.stem).rglob("*.md"))
        if len(candidates) == 1:
            markdown_path = candidates[0]
    return markdown_path


def main() -> None:
    args = build_parser().parse_args()
    src = Path(args.input).expanduser().resolve()
    if not src.is_file():
        raise SystemExit(f"Input not found: {src}")

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.engine == "open-api":
        markdown_path = run_open_api(src, output_dir, args)
    else:
        markdown_path = run_local(src, output_dir, args)

    print(f"ENGINE -> {args.engine}")
    print(f"DONE -> {markdown_path}")


if __name__ == "__main__":
    main()
