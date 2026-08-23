#!/usr/bin/env python3
"""Validate the repository's Skill frontmatter and UI metadata."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MODEL_ROUTES = {
    "paper-to-beamer": (
        "gpt-5.6-sol",
        "medium",
        "PAPER_TO_VIDEO_STAGE_WORKER=beamer:gpt-5.6-sol:medium",
    ),
    "bilibili-video-uploader": (
        "gpt-5.6-terra",
        "medium",
        "PAPER_TO_VIDEO_STAGE_WORKER=terra:gpt-5.6-terra:medium",
    ),
    "markdown-to-video-cover": (
        "gpt-5.6-terra",
        "medium",
        "PAPER_TO_VIDEO_STAGE_WORKER=terra:gpt-5.6-terra:medium",
    ),
    "paper-download-arxiv-source": (
        "gpt-5.6-terra",
        "medium",
        "PAPER_TO_VIDEO_STAGE_WORKER=terra:gpt-5.6-terra:medium",
    ),
    "paper-to-video": (
        "gpt-5.6-terra",
        "medium",
        "PAPER_TO_VIDEO_STAGE_WORKER=video:gpt-5.6-terra:medium",
    ),
    "pdf-slides-to-video": (
        "gpt-5.6-terra",
        "medium",
        "PAPER_TO_VIDEO_STAGE_WORKER=terra:gpt-5.6-terra:medium",
    ),
    "pdf-to-markdown": (
        "gpt-5.6-terra",
        "medium",
        "PAPER_TO_VIDEO_STAGE_WORKER=terra:gpt-5.6-terra:medium",
    ),
    "sustech-beamer-theme-fix": (
        "gpt-5.6-terra",
        "medium",
        "PAPER_TO_VIDEO_STAGE_WORKER=terra:gpt-5.6-terra:medium",
    ),
}


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

        expected_route = MODEL_ROUTES.get(name)
        if expected_route is None:
            errors.append(f"{relative}: missing required model route")
        else:
            expected_model, expected_effort, expected_marker = expected_route
            if metadata.get("stage_model") != expected_model:
                errors.append(
                    f"{relative}: stage_model must be {expected_model!r}"
                )
            if metadata.get("stage_reasoning_effort") != expected_effort:
                errors.append(
                    f"{relative}: stage_reasoning_effort must be "
                    f"{expected_effort!r}"
                )
            skill_text = skill_file.read_text(encoding="utf-8")
            routing_headings = (
                "## Required model route",
                "## Required staged model route",
            )
            if not any(heading in skill_text for heading in routing_headings):
                errors.append(f"{relative}: missing model-routing instructions")
            if expected_marker not in skill_text:
                errors.append(f"{relative}: missing recursion-safe worker marker")
            if name in {"paper-to-video", "sustech-beamer-theme-fix"}:
                if metadata.get("beamer_quality_model") != "gpt-5.6-sol":
                    errors.append(
                        f"{relative}: beamer_quality_model must be "
                        "'gpt-5.6-sol'"
                    )
                if (
                    metadata.get("beamer_quality_reasoning_effort")
                    != "medium"
                ):
                    errors.append(
                        f"{relative}: beamer_quality_reasoning_effort must be "
                        "'medium'"
                    )
                beamer_marker = (
                    "PAPER_TO_VIDEO_STAGE_WORKER="
                    "beamer:gpt-5.6-sol:medium"
                )
                if beamer_marker not in skill_text:
                    errors.append(
                        f"{relative}: missing Sol Beamer-stage worker marker"
                    )

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

    print(
        f"Validated {len(skill_files)} Skills, model routes, and "
        "agents/openai.yaml files."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
