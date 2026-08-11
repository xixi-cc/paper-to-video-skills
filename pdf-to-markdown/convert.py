#!/usr/bin/env python
"""Convert a PDF (or image/docx/pptx/xlsx) to Markdown with MinerU's in-process API.

Call ``do_parse`` directly so the script works from an isolated Codex project
environment without relying on a machine-specific MinerU service.

Usage:
    python convert.py <input_path> <output_dir> [--lang ch] [--backend pipeline] [--method auto]

Output:
    <output_dir>/<name>/<method>/<name>.md   (+ extracted images/)
"""
import argparse
from pathlib import Path

def main() -> None:
    ap = argparse.ArgumentParser(description="PDF -> Markdown via MinerU (in-process).")
    ap.add_argument("input", help="Input file (pdf/png/jpg/docx/pptx/xlsx).")
    ap.add_argument("output_dir", help="Output directory.")
    ap.add_argument("--lang", default="ch",
                    help="OCR language hint (pipeline backend). 'ch' handles EN+CN. Default: ch")
    ap.add_argument("--backend", default="pipeline",
                    help="MinerU backend. Default: pipeline.")
    ap.add_argument("--method", default="auto", choices=["auto", "txt", "ocr"],
                    help="Parse method for pipeline backend. Default: auto")
    args = ap.parse_args()

    try:
        from mineru.cli.common import do_parse, read_fn
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "MinerU is not installed in this Python environment. Use an "
            "isolated project environment or the official Codex PDF skill."
        ) from exc

    src = Path(args.input)
    if not src.exists():
        raise SystemExit(f"Input not found: {src}")

    do_parse(
        output_dir=args.output_dir,
        pdf_file_names=[src.stem],
        pdf_bytes_list=[read_fn(src)],
        p_lang_list=[args.lang],
        backend=args.backend,
        parse_method=args.method,
    )

    out_md = Path(args.output_dir) / src.stem / args.method / f"{src.stem}.md"
    print(f"\nDONE -> {out_md}")


if __name__ == "__main__":
    main()
