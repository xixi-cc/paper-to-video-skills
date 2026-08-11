#!/usr/bin/env python3
"""Validate the repository's Skill frontmatter and UI metadata."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening YAML frontmatter marker")

    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("missing closing YAML frontmatter marker") from error

    values: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"invalid frontmatter line: {line!r}")
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"\'')
    return values


def parse_interface_metadata(path: Path) -> set[str]:
    keys: set[str] = set()
    in_interface = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith((" ", "\t")):
            in_interface = line.rstrip() == "interface:"
            continue
        if in_interface:
            match = re.match(r"^\s{2}([a-z_]+):\s*\S", line)
            if match:
                keys.add(match.group(1))
    return keys


def main() -> int:
    errors: list[str] = []
    skill_files = sorted(ROOT.glob("*/SKILL.md"))
    if not skill_files:
        errors.append("no top-level Skill directories found")

    names: set[str] = set()
    required_interface = {"display_name", "short_description", "default_prompt"}

    for skill_file in skill_files:
        relative = skill_file.relative_to(ROOT)
        directory_name = skill_file.parent.name
        try:
            metadata = parse_frontmatter(skill_file)
        except (OSError, UnicodeError, ValueError) as error:
            errors.append(f"{relative}: {error}")
            continue

        name = metadata.get("name", "")
        description = metadata.get("description", "")
        if not name:
            errors.append(f"{relative}: missing name")
        elif not NAME_PATTERN.fullmatch(name):
            errors.append(f"{relative}: invalid name {name!r}")
        elif name != directory_name:
            errors.append(
                f"{relative}: name {name!r} does not match directory "
                f"{directory_name!r}"
            )
        elif name in names:
            errors.append(f"{relative}: duplicate Skill name {name!r}")
        names.add(name)

        if not description:
            errors.append(f"{relative}: missing description")

        agent_file = skill_file.parent / "agents" / "openai.yaml"
        if not agent_file.is_file():
            errors.append(f"{agent_file.relative_to(ROOT)}: missing UI metadata")
            continue
        interface_keys = parse_interface_metadata(agent_file)
        missing = sorted(required_interface - interface_keys)
        if missing:
            errors.append(
                f"{agent_file.relative_to(ROOT)}: missing interface fields "
                f"{', '.join(missing)}"
            )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Validated {len(skill_files)} Skills and their agents/openai.yaml files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
