#!/usr/bin/env python3
"""Validate and render paper_presentation.json into pipeline artifacts.

The manifest is the content source of truth.  LaTeX remains responsible for
layout; this renderer only synchronizes metadata, frame bodies, narrations,
evidence audits, and Bilibili metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


MANIFEST_NAME = "paper_presentation.json"
SCHEMA_VERSION = 1
EVIDENCE_EXEMPT_KINDS = {"title", "outline", "section", "references", "closing"}
FIGURE_PATTERN = re.compile(r"\\(?:includegraphics(?:\[[^\]]*\])?|fitfigure)\{([^}]+)\}")
EQUATION_PATTERN = re.compile(
    r"\\begin\{(?:equation\*?|align\*?|gather\*?)\}|\\\[|\$\$"
)
FULL_EXPLAINER_BASELINE = {
    "minimum_slides": 14,
    "minimum_figure_slides": 3,
    "minimum_equation_slides": 1,
    "minimum_narration_characters": 2200,
}


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _atomic_json(path: Path, value: Any) -> None:
    _atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _required_string(mapping: dict[str, Any], key: str, where: str, errors: list[str]) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{where}.{key} must be a nonempty string")
        return ""
    return value.strip()


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must equal {SCHEMA_VERSION}")
    paper = manifest.get("paper")
    if not isinstance(paper, dict):
        errors.append("paper must be an object")
        paper = {}
    for key in ("title_zh", "title_en", "short_title", "venue", "year"):
        _required_string(paper, key, "paper", errors)
    authors = paper.get("authors")
    if not isinstance(authors, list) or not authors or not all(
        isinstance(item, str) and item.strip() for item in authors
    ):
        errors.append("paper.authors must be a nonempty string array")

    slides = manifest.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append("slides must be a nonempty array")
        slides = []
    elif not isinstance(slides[0], dict) or not (
        slides[0].get("kind") == "title"
        and r"\titlepage" in str(slides[0].get("latex_body", ""))
    ):
        errors.append(
            "slides[0] must be the Beamer title page with kind=title and \\titlepage"
        )
    seen_ids: set[str] = set()
    evidence_claims = 0
    evidenced_claims = 0
    figure_slides = 0
    equation_slides = 0
    narration_characters = 0
    for index, slide in enumerate(slides, start=1):
        where = f"slides[{index - 1}]"
        if not isinstance(slide, dict):
            errors.append(f"{where} must be an object")
            continue
        slide_id = _required_string(slide, "id", where, errors)
        if slide_id and not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slide_id):
            errors.append(f"{where}.id must use lowercase letters, digits, and hyphens")
        if slide_id in seen_ids:
            errors.append(f"duplicate slide id: {slide_id}")
        seen_ids.add(slide_id)
        kind = _required_string(slide, "kind", where, errors)
        latex_body = _required_string(slide, "latex_body", where, errors)
        narration = _required_string(slide, "narration", where, errors)
        narration_characters += len(re.sub(r"\s+", "", narration))
        has_figure = bool(FIGURE_PATTERN.search(latex_body))
        has_equation = bool(EQUATION_PATTERN.search(latex_body))
        figure_slides += int(has_figure)
        equation_slides += int(has_equation)
        if "\n" in narration:
            warnings.append(f"{where}.narration will be flattened to one line")
        evidence = slide.get("evidence", [])
        if not isinstance(evidence, list):
            errors.append(f"{where}.evidence must be an array")
            evidence = []
        if kind not in EVIDENCE_EXEMPT_KINDS and not evidence:
            errors.append(f"{where} requires at least one evidence item")
        if has_figure and not any(
            isinstance(item, dict) and item.get("figure") for item in evidence
        ):
            errors.append(f"{where} is a figure slide but has no figure evidence locator")
        if has_figure:
            if slide.get("kind") != "figure":
                errors.append(f"{where} contains a paper figure but kind is not 'figure'")
            if slide.get("frame_options") != "plain,c":
                errors.append(f"{where} figure frame_options must equal 'plain,c'")
            if re.search(r"\\begin\{(?:columns?|block|alertblock)\}", latex_body):
                errors.append(f"{where} must keep a detailed paper figure on a dedicated frame")
        for ev_index, item in enumerate(evidence):
            ev_where = f"{where}.evidence[{ev_index}]"
            if not isinstance(item, dict):
                errors.append(f"{ev_where} must be an object")
                continue
            _required_string(item, "claim", ev_where, errors)
            evidence_claims += 1
            locators = (
                item.get("paper_page"), item.get("figure"), item.get("equation"),
                item.get("table"), item.get("reference"), item.get("url"),
            )
            if not any(value not in (None, "") for value in locators):
                errors.append(f"{ev_where} needs a page, figure, equation, table, reference, or URL")
            else:
                evidenced_claims += 1

    quality = manifest.get("quality")
    if not isinstance(quality, dict):
        errors.append("quality must be an object")
        quality = {}
    if quality.get("profile") != "full-explainer":
        errors.append("quality.profile must equal 'full-explainer'")
    duration = quality.get("target_duration_minutes")
    if not (
        isinstance(duration, list) and len(duration) == 2
        and all(isinstance(value, (int, float)) and value > 0 for value in duration)
        and duration[0] < duration[1]
    ):
        errors.append("quality.target_duration_minutes must be [minimum, maximum]")
    elif duration[0] < 8:
        errors.append("full-explainer minimum target duration must be at least 8 minutes")
    thresholds = {
        "minimum_slides": len(slides),
        "minimum_figure_slides": figure_slides,
        "minimum_equation_slides": equation_slides,
        "minimum_narration_characters": narration_characters,
    }
    for key, actual in thresholds.items():
        expected = quality.get(key)
        if not isinstance(expected, int) or expected < 0:
            errors.append(f"quality.{key} must be a nonnegative integer")
        elif expected < FULL_EXPLAINER_BASELINE[key]:
            errors.append(
                f"quality.{key} cannot be below the full-explainer baseline "
                f"{FULL_EXPLAINER_BASELINE[key]}"
            )
        elif actual < expected:
            errors.append(f"{key} requires at least {expected}; found {actual}")
    maximum_narration = quality.get("maximum_narration_characters")
    if maximum_narration is not None:
        if not isinstance(maximum_narration, int) or maximum_narration < 1:
            errors.append("quality.maximum_narration_characters must be a positive integer")
        elif narration_characters > maximum_narration:
            warnings.append(
                f"narration has {narration_characters} characters; target maximum is {maximum_narration}"
            )

    publication = manifest.get("publication")
    if not isinstance(publication, dict):
        errors.append("publication must be an object")
        publication = {}
    _required_string(publication, "title", "publication", errors)
    _required_string(publication, "description", "publication", errors)
    tags = publication.get("tags")
    if not isinstance(tags, list) or not tags or not all(
        isinstance(tag, str) and tag.strip() for tag in tags
    ):
        errors.append("publication.tags must be a nonempty string array")
    if len(str(publication.get("title", ""))) > 80:
        errors.append("publication.title exceeds Bilibili's 80-character limit")
    description = str(publication.get("description", "")).strip()
    compact_description = re.sub(r"\s+", "", description)
    description_lines = [
        line.strip() for line in description.splitlines() if line.strip()
    ]
    summary = description_lines[0] if description_lines else ""
    if description and not (
        summary.startswith("一句话概述：")
        and "重要性在于" in summary
        and len(summary) >= 25
        and summary.endswith(("。", "！", "？"))
        and len(re.findall(r"[。！？]", summary)) == 1
    ):
        errors.append(
            "publication.description must start with exactly one sentence: "
            "一句话概述：本文做了什么；其重要性在于什么。"
        )
    if description and (
        len(compact_description) < 20
        or not any(
            marker in description
            for marker in ("本视频", "本期", "这期", "本次视频")
        )
    ):
        errors.append(
            "publication.description needs a short Chinese introduction containing "
            "本视频、本期、这期, or 本次视频"
        )
    if publication.get("copyright", 1) == 2 and not publication.get("source"):
        errors.append("publication.source is required when copyright is 2")
    if publication.get("cover_path", "cover.png") != "cover.png":
        errors.append(
            "publication.cover_path must be cover.png; the Beamer title page is the cover"
        )

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "slides": len(slides),
        "figure_slides": figure_slides,
        "equation_slides": equation_slides,
        "narration_characters": narration_characters,
        "target_duration_minutes": duration,
        "evidence_items": evidence_claims,
        "evidence_locator_coverage": (
            round(evidenced_claims / evidence_claims, 4) if evidence_claims else 1.0
        ),
    }


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("paper_presentation.json must contain a JSON object")
    report = validate_manifest(manifest)
    if not report["valid"]:
        raise ValueError("Invalid presentation manifest:\n- " + "\n- ".join(report["errors"]))
    return manifest


def _tex(value: Any, default: str = "") -> str:
    return str(value if value not in (None, "") else default).strip()


def render_metadata_tex(manifest: dict[str, Any]) -> str:
    paper = manifest["paper"]
    authors = r" \and ".join(_tex(item) for item in paper["authors"])
    author_short = _tex(paper.get("author_short"), paper["authors"][0] + " et al.")
    domains = "".join(r"\domaintag{" + _tex(item) + "}" for item in paper.get("domains", []))
    return "\n".join([
        "% Generated from paper_presentation.json; do not edit directly.",
        rf"\title[{_tex(paper['short_title'])}]{{{_tex(paper['title_zh'])}}}",
        rf"\subtitle{{{_tex(paper['title_en'])}}}",
        rf"\author[{author_short}]{{{authors}}}",
        rf"\institute[{_tex(paper.get('institute_short'), paper.get('institute', ''))}]{{{_tex(paper.get('institute'))}}}",
        rf"\setsource{{{_tex(paper['venue'])}}}{{{_tex(paper['year'])}}}",
        rf"\setdomains{{{domains}}}",
        rf"\setpresenter{{{_tex(paper.get('presenter'))}}}",
        rf"\setvenue{{{_tex(paper.get('location'))}}}",
        rf"\date{{{_tex(paper.get('date'))}}}",
        "",
    ])


def render_frames_tex(manifest: dict[str, Any]) -> str:
    lines = ["% Generated from paper_presentation.json; do not edit directly."]
    current_section: str | None = None
    for slide in manifest["slides"]:
        section = _tex(slide.get("section"))
        if section and section != current_section:
            blurb = _tex(slide.get("section_blurb"))
            if blurb:
                lines.append(rf"\renewcommand{{\secblurb}}{{{blurb}}}")
            lines.append(rf"\section{{{section}}}")
            current_section = section
        options = _tex(slide.get("frame_options"))
        title = _tex(slide.get("title"))
        begin = r"\begin{frame}"
        if options:
            begin += f"[{options}]"
        if title:
            begin += "{" + title + "}"
        lines.extend([
            "",
            f"% PRESENTATION_SLIDE_ID: {slide['id']}",
            begin,
            slide["latex_body"].rstrip(),
            r"\end{frame}",
            "% NARRATION: " + " ".join(slide["narration"].splitlines()).strip(),
        ])
    lines.append("")
    return "\n".join(lines)


def render_video_metadata(manifest: dict[str, Any]) -> dict[str, Any]:
    publication = manifest["publication"]
    result = {
        "title": publication["title"],
        "tid": int(publication.get("tid", 124)),
        "tag": publication["tags"],
        "desc": _tex(publication.get("description")),
        "copyright": int(publication.get("copyright", 1)),
        "no_reprint": int(publication.get("no_reprint", 0)),
        "cover_path": "cover.png",
    }
    for source, destination in (
        ("source", "source"), ("dynamic", "dynamic")
    ):
        if publication.get(source) not in (None, ""):
            result[destination] = publication[source]
    return result


def render_manifest(paper_dir: Path) -> dict[str, Any]:
    root = paper_dir.expanduser().resolve()
    manifest_path = root / MANIFEST_NAME
    manifest = load_manifest(manifest_path)
    report = validate_manifest(manifest)
    slides_dir = root / "slides-beamer"
    video_dir = root / "video"
    metadata_tex = slides_dir / "presentation_metadata.tex"
    frames_tex = slides_dir / "presentation_frames.tex"
    video_metadata = video_dir / "video_meta.json"
    narration_audit = video_dir / "narrations.json"
    evidence_audit = video_dir / "evidence-audit.json"
    missing_figures: list[str] = []
    for slide in manifest["slides"]:
        for raw_path in FIGURE_PATTERN.findall(slide["latex_body"]):
            candidate = Path(raw_path)
            search = [slides_dir / candidate, slides_dir / "figures" / candidate]
            if not candidate.suffix:
                search = [
                    path.with_suffix(suffix)
                    for path in search
                    for suffix in (".pdf", ".png", ".jpg", ".jpeg")
                ]
            if not any(path.is_file() and path.stat().st_size > 0 for path in search):
                missing_figures.append(raw_path)
    if missing_figures:
        raise ValueError("Missing figure assets: " + ", ".join(sorted(set(missing_figures))))
    _atomic_text(metadata_tex, render_metadata_tex(manifest))
    _atomic_text(frames_tex, render_frames_tex(manifest))
    _atomic_json(video_metadata, render_video_metadata(manifest))
    _atomic_json(narration_audit, {
        slide["id"]: {
            "narration": slide["narration"],
            "evidence": slide.get("evidence", []),
        }
        for slide in manifest["slides"]
    })
    _atomic_json(evidence_audit, report)

    main_tex = slides_dir / "main.tex"
    if not main_tex.exists():
        raise FileNotFoundError(main_tex)
    main_content = main_tex.read_text(encoding="utf-8")
    required_inputs = ("presentation_metadata.tex", "presentation_frames.tex")
    missing_inputs = [name for name in required_inputs if name not in main_content]
    if missing_inputs:
        raise ValueError(
            "main.tex is not manifest-enabled; copy the current SUSTech template. "
            "Missing input marker(s): " + ", ".join(missing_inputs)
        )
    # Keep a generated narration source for compatibility with existing video
    # tooling. It is derived from the same manifest and is never edited by hand.
    annotated = video_dir / "main_with_narration.tex"
    _atomic_text(annotated, render_frames_tex(manifest))
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return {
        "manifest": str(manifest_path),
        "manifest_sha256": digest,
        "slides": len(manifest["slides"]),
        "metadata_tex": str(metadata_tex),
        "frames_tex": str(frames_tex),
        "video_metadata": str(video_metadata),
        "annotated_tex": str(annotated),
        "validation": report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate or render paper_presentation.json")
    parser.add_argument("mode", choices=("validate", "render"))
    parser.add_argument("paper_dir", type=Path)
    args = parser.parse_args()
    if args.mode == "validate":
        manifest = json.loads((args.paper_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
        result = validate_manifest(manifest)
    else:
        result = render_manifest(args.paper_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.mode == "validate" and not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
