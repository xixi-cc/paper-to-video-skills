#!/usr/bin/env python3
"""Check local Markdown link targets without making network requests."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
EXTERNAL_SCHEMES = {"http", "https", "mailto", "tel"}


def link_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    return target.split(maxsplit=1)[0]


def main() -> int:
    errors: list[str] = []
    checked = 0

    for markdown_file in sorted(ROOT.rglob("*.md")):
        text = markdown_file.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in LINK_PATTERN.finditer(line):
                target = link_target(match.group(1))
                parsed = urlsplit(target)
                if not target or target.startswith("#"):
                    continue
                if parsed.scheme.lower() in EXTERNAL_SCHEMES or target.startswith("//"):
                    continue

                decoded_path = unquote(parsed.path)
                if not decoded_path:
                    continue
                candidate = (markdown_file.parent / decoded_path).resolve()
                checked += 1
                try:
                    candidate.relative_to(ROOT)
                except ValueError:
                    errors.append(
                        f"{markdown_file.relative_to(ROOT)}:{line_number}: "
                        f"link escapes repository: {target}"
                    )
                    continue
                if not candidate.exists():
                    errors.append(
                        f"{markdown_file.relative_to(ROOT)}:{line_number}: "
                        f"missing target: {target}"
                    )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Checked {checked} local Markdown links.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
