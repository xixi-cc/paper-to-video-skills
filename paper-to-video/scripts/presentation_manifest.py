#!/usr/bin/env python3
"""Validate and render a Beamer-only paper presentation manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


MANIFEST_NAME = "paper_presentation.json"
SCHEMA_VERSION = 2
EVIDENCE_EXEMPT_KINDS = {"title", "outline", "section", "references", "closing"}
FIGURE_PATTERN = re.compile(
    r"\\(?:includegraphics(?:\[[^\]]*\])?|fitfigure|paperfigure)\{([^}]+)\}"
)
EQUATION_PATTERN = re.compile(
    r"\\begin\{(?:equation\*?|align\*?|gather\*?)\}|\\equationderivation\{|\\\[|\$\$"
)
SEMANTIC_FRAME_KINDS = {
    "paperfigure": "figure",
    "equationderivation": "equation",
    "baselinecomparison": "comparison",
}


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _required_string(
    mapping: dict[str, Any], key: str, where: str, errors: list[str],
) -> str:
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

    source = manifest.get("source")
    if source is not None:
        if not isinstance(source, dict):
            errors.append("source must be an object")
            source = {}
        primary_format = source.get("primary_format")
        if primary_format not in {"pdf", "tex"}:
            errors.append("source.primary_format must equal pdf or tex")
        _required_string(source, "provenance_path", "source", errors)
        primary_path = source.get("pdf_path") if primary_format == "pdf" else source.get("tex_root")
        if not isinstance(primary_path, str) or not primary_path.strip():
            errors.append(
                "source.pdf_path is required for PDF input"
                if primary_format == "pdf"
                else "source.tex_root is required for TeX input"
            )

    slides = manifest.get("slides")
    if not isinstance(slides, list) or not slides:
        errors.append("slides must be a nonempty array")
        slides = []
    elif not isinstance(slides[0], dict) or not (
        slides[0].get("kind") == "title"
        and r"\titlepage" in str(slides[0].get("latex_body", ""))
    ):
        errors.append("slides[0] must have kind=title and contain \\titlepage")

    seen_ids: set[str] = set()
    evidence_items = 0
    evidenced_items = 0
    figure_slides = 0
    equation_slides = 0
    semantic_frame_counts = {name: 0 for name in SEMANTIC_FRAME_KINDS}
    for index, slide in enumerate(slides):
        where = f"slides[{index}]"
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
        has_figure = bool(FIGURE_PATTERN.search(latex_body))
        has_equation = bool(EQUATION_PATTERN.search(latex_body))
        figure_slides += int(has_figure)
        equation_slides += int(has_equation)

        semantic_uses = {
            name: bool(re.search(rf"\\{name}\{{", latex_body))
            for name in SEMANTIC_FRAME_KINDS
        }
        for name, used in semantic_uses.items():
            semantic_frame_counts[name] += int(used)
            if used and kind != SEMANTIC_FRAME_KINDS[name]:
                errors.append(
                    f"{where} uses \\{name} but kind is not "
                    f"'{SEMANTIC_FRAME_KINDS[name]}'"
                )

        evidence = slide.get("evidence", [])
        if not isinstance(evidence, list):
            errors.append(f"{where}.evidence must be an array")
            evidence = []
        if kind not in EVIDENCE_EXEMPT_KINDS and not evidence:
            errors.append(f"{where} requires at least one evidence item")
        if has_figure:
            if kind != "figure":
                errors.append(f"{where} contains a paper figure but kind is not 'figure'")
            if slide.get("frame_options") != "plain,c":
                errors.append(f"{where} figure frame_options must equal 'plain,c'")
            if re.search(r"\\begin\{(?:columns?|block|alertblock)\}", latex_body):
                errors.append(f"{where} must keep a detailed paper figure on a dedicated frame")
            if not any(isinstance(item, dict) and item.get("figure") for item in evidence):
                errors.append(f"{where} is a figure slide but has no figure evidence locator")

        for evidence_index, item in enumerate(evidence):
            item_where = f"{where}.evidence[{evidence_index}]"
            if not isinstance(item, dict):
                errors.append(f"{item_where} must be an object")
                continue
            _required_string(item, "claim", item_where, errors)
            evidence_items += 1
            locators = (
                item.get("paper_page"), item.get("figure"), item.get("equation"),
                item.get("table"), item.get("reference"), item.get("url"),
                item.get("tex_file"),
            )
            if any(value not in (None, "") for value in locators):
                evidenced_items += 1
            else:
                errors.append(f"{item_where} needs a paper or source locator")

    obsolete = sorted(set(manifest) & {"quality", "publication"})
    if obsolete:
        errors.append("remove obsolete v1 field(s): " + ", ".join(obsolete))
    if any(isinstance(slide, dict) and "narration" in slide for slide in slides):
        errors.append("remove slide narration; video/narrations.json owns narration")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "slides": len(slides),
        "figure_slides": figure_slides,
        "equation_slides": equation_slides,
        "semantic_frame_counts": semantic_frame_counts,
        "evidence_items": evidence_items,
        "evidence_locator_coverage": (
            round(evidenced_items / evidence_items, 4) if evidence_items else 1.0
        ),
    }


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("paper_presentation.json must contain a JSON object")
    report = validate_manifest(manifest)
    if not report["valid"]:
        raise ValueError("Invalid presentation manifest:\n- " + "\n- ".join(report["errors"]))

    source = manifest.get("source")
    if isinstance(source, dict):
        paper_root = path.resolve().parent
        for field in ("provenance_path", "pdf_path", "tex_root", "source_index_path"):
            value = source.get(field)
            if not value:
                continue
            candidate = Path(str(value))
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError(f"source.{field} must be a safe paper-root-relative path")
            if not (paper_root / candidate).exists():
                raise ValueError(f"source.{field} does not exist: {candidate}")
        provenance = json.loads(
            (paper_root / str(source["provenance_path"])).read_text(encoding="utf-8")
        )
        if provenance.get("schema_version") != 1:
            raise ValueError("source provenance schema_version must equal 1")
        if source.get("arxiv_id") and provenance.get("arxiv_id") != source["arxiv_id"]:
            raise ValueError("manifest arxiv_id does not match source provenance")
        if not re.fullmatch(r"[0-9a-f]{64}", str(provenance.get("payload_sha256", ""))):
            raise ValueError("source provenance needs a valid payload_sha256")
        if source.get("pdf_path") and not re.fullmatch(
            r"[0-9a-f]{64}", str(provenance.get("pdf_sha256", "")),
        ):
            raise ValueError("source provenance needs a valid pdf_sha256")
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
        begin = r"\begin{frame}" + (f"[{options}]" if options else "")
        if title:
            begin += "{" + title + "}"
        lines.extend([
            "",
            f"% PRESENTATION_SLIDE_ID: {slide['id']}",
            begin,
            slide["latex_body"].rstrip(),
            r"\end{frame}",
        ])
    lines.append("")
    return "\n".join(lines)


def render_manifest(paper_dir: Path) -> dict[str, Any]:
    root = paper_dir.expanduser().resolve()
    manifest_path = root / MANIFEST_NAME
    manifest = load_manifest(manifest_path)
    report = validate_manifest(manifest)
    slides_dir = root / "slides-beamer"
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

    metadata_tex = slides_dir / "presentation_metadata.tex"
    frames_tex = slides_dir / "presentation_frames.tex"
    _atomic_text(metadata_tex, render_metadata_tex(manifest))
    _atomic_text(frames_tex, render_frames_tex(manifest))
    main_tex = slides_dir / "main.tex"
    if not main_tex.exists():
        raise FileNotFoundError(main_tex)
    main_content = main_tex.read_text(encoding="utf-8")
    missing_inputs = [
        name for name in ("presentation_metadata.tex", "presentation_frames.tex")
        if name not in main_content
    ]
    if missing_inputs:
        raise ValueError(
            "main.tex is not manifest-enabled; missing: " + ", ".join(missing_inputs)
        )
    return {
        "manifest": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "slides": len(manifest["slides"]),
        "metadata_tex": str(metadata_tex),
        "frames_tex": str(frames_tex),
        "validation": report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "render"))
    parser.add_argument("paper_dir", type=Path)
    args = parser.parse_args()
    if args.action == "validate":
        manifest = json.loads((args.paper_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
        result = validate_manifest(manifest)
    else:
        result = render_manifest(args.paper_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.action == "validate" and not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
