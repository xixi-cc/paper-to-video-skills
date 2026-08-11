#!/usr/bin/env python3
"""Compile Python source in memory so validation leaves no bytecode caches."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIPPED_DIRECTORIES = {".git", ".venv", "venv", "__pycache__"}


def main() -> int:
    errors: list[str] = []
    checked = 0

    for path in sorted(ROOT.rglob("*.py")):
        if any(part in SKIPPED_DIRECTORIES for part in path.relative_to(ROOT).parts):
            continue
        checked += 1
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
        except (OSError, UnicodeError, SyntaxError) as error:
            errors.append(f"{path.relative_to(ROOT)}: {error}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Checked Python syntax in {checked} files without writing bytecode.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
