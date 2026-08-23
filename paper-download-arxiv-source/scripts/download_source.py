#!/usr/bin/env python3
"""Safely download an arXiv e-print and emit a provenance receipt."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


NEW_ID = re.compile(r"\d{4}\.\d{4,5}(?:v\d+)?")
OLD_ID = re.compile(r"[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?", re.IGNORECASE)
MAX_MEMBERS = 20_000
MAX_EXTRACTED_BYTES = 2 * 1024**3
EPRINT_URL = "https://arxiv.org/e-print/{arxiv_id}"
PDF_URL = "https://arxiv.org/pdf/{arxiv_id}"
USER_AGENT = "paper-to-video-skills/1.0 (+https://github.com/xixi-cc/paper-to-video-skills)"


class SourceError(RuntimeError):
    """A bounded, user-facing source intake failure."""


def parse_arxiv_ref(value: str) -> str:
    raw = value.strip()
    if NEW_ID.fullmatch(raw) or OLD_ID.fullmatch(raw):
        return raw
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "arxiv.org", "www.arxiv.org", "export.arxiv.org"
    }:
        raise SourceError(f"cannot parse arXiv reference: {value}")
    match = re.fullmatch(r"/(?:abs|pdf|e-print)/(.+)", parsed.path)
    if not match:
        raise SourceError(f"unsupported arXiv URL: {value}")
    arxiv_id = urllib.parse.unquote(match.group(1)).removesuffix(".pdf")
    if not (NEW_ID.fullmatch(arxiv_id) or OLD_ID.fullmatch(arxiv_id)):
        raise SourceError(f"invalid arXiv identifier in URL: {value}")
    return arxiv_id


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_bytes(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


def _download_url(url: str, label: str) -> tuple[bytes, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
                content_type = response.headers.get("Content-Type", "")
                final_url = response.geturl()
            if not data:
                raise SourceError("arXiv returned an empty response")
            return data, content_type, final_url
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, SourceError) as error:
            last_error = error
            if attempt == 0:
                time.sleep(2)
    raise SourceError(f"download failed for {label}: {last_error}")


def download(arxiv_id: str) -> tuple[bytes, str, str]:
    return _download_url(EPRINT_URL.format(arxiv_id=arxiv_id), f"arXiv source {arxiv_id}")


def download_pdf(arxiv_id: str) -> tuple[bytes, str, str]:
    data, content_type, final_url = _download_url(
        PDF_URL.format(arxiv_id=arxiv_id), f"arXiv PDF {arxiv_id}"
    )
    if not data.startswith(b"%PDF"):
        raise SourceError("arXiv PDF endpoint returned a non-PDF payload")
    return data, content_type, final_url


def detect_payload(data: bytes) -> tuple[str, bytes]:
    candidate = data
    if data.startswith(b"\x1f\x8b"):
        try:
            uncompressed = gzip.decompress(data)
        except OSError as error:
            raise SourceError(f"invalid gzip payload: {error}") from error
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*"):
                return "archive", data
        except tarfile.TarError:
            candidate = uncompressed
    else:
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:*"):
                return "archive", data
        except tarfile.TarError:
            pass
    if candidate.startswith(b"%PDF"):
        return "pdf", candidate
    head = candidate[:8192].lstrip()
    if head.startswith(b"\\documentclass") or b"\\begin{document}" in head:
        return "tex", candidate
    raise SourceError("arXiv returned an unrecognized payload")


def _safe_members(archive_data: bytes) -> tuple[list[tarfile.TarInfo], bool]:
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:*") as archive:
            members = archive.getmembers()
    except tarfile.TarError as error:
        raise SourceError(f"cannot read source archive: {error}") from error
    if len(members) > MAX_MEMBERS:
        raise SourceError(f"archive has too many members: {len(members)}")
    total = 0
    normalized: list[tarfile.TarInfo] = []
    top_parts: set[str] = set()
    all_nested_or_top_directory = True
    for member in members:
        name = member.name.replace("\\", "/").removeprefix("./")
        parts = PurePosixPath(name).parts
        if not name or name == ".":
            continue
        if name.startswith("/") or ".." in parts:
            raise SourceError(f"unsafe archive member: {member.name}")
        if member.issym() or member.islnk() or member.isdev():
            raise SourceError(f"links and device members are not allowed: {member.name}")
        if not (member.isfile() or member.isdir()):
            continue
        total += member.size
        if total > MAX_EXTRACTED_BYTES:
            raise SourceError("archive exceeds the extracted-size limit")
        member.name = name
        normalized.append(member)
        top_parts.add(parts[0])
        all_nested_or_top_directory = all_nested_or_top_directory and (
            len(parts) > 1 or member.isdir()
        )
    flatten = (
        len(top_parts) == 1
        and all_nested_or_top_directory
        and any(len(PurePosixPath(member.name).parts) > 1 for member in normalized)
    )
    return normalized, flatten


def extract_archive(archive_data: bytes, destination: Path) -> list[str]:
    members, flatten = _safe_members(archive_data)
    if destination.exists():
        raise SourceError(f"source tree already exists: {destination}; use --force to replace it")
    temporary = Path(tempfile.mkdtemp(prefix="tex-source-", dir=destination.parent))
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:*") as archive:
            for member in members:
                parts = list(PurePosixPath(member.name).parts)
                if flatten:
                    parts = parts[1:]
                if not parts:
                    continue
                target = temporary.joinpath(*parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise SourceError(f"cannot read archive member: {member.name}")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
        tex_files = sorted(str(path.relative_to(temporary)) for path in temporary.rglob("*.tex"))
        if not tex_files:
            raise SourceError("source archive contains no TeX files")
        os.replace(temporary, destination)
        return tex_files
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _compact_tex(value: str, limit: int = 280) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _strip_tex_comments(text: str) -> str:
    return "\n".join(
        re.split(r"(?<!\\)%", line, maxsplit=1)[0]
        for line in text.splitlines()
    )


def _balanced_argument(text: str, opening: int) -> str | None:
    depth = 0
    for position in range(opening, len(text)):
        if text[position] == "{" and (position == 0 or text[position - 1] != "\\"):
            depth += 1
        elif text[position] == "}" and (position == 0 or text[position - 1] != "\\"):
            depth -= 1
            if depth == 0:
                return text[opening + 1:position]
    return None


def build_source_index(tex_root: Path, index_path: Path) -> dict[str, Any]:
    """Build a compact routing index so models need not preload the full TeX tree."""
    command_patterns = {
        "section": re.compile(r"\\(?:part|section|subsection|subsubsection)\*?\s*\{"),
        "caption": re.compile(r"\\caption(?:\[[^\]]*\])?\s*\{"),
        "figure": re.compile(r"\\includegraphics(?:\[[^\]]*\])?\s*\{"),
        "equation_label": re.compile(r"\\label\s*\{(?=(?:eq|equation))", re.IGNORECASE),
    }
    files: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    for path in sorted(tex_root.rglob("*.tex")):
        relative = path.relative_to(tex_root).as_posix()
        payload = path.read_bytes()
        text = _strip_tex_comments(payload.decode("utf-8", errors="replace"))
        files.append({
            "path": relative,
            "bytes": len(payload),
            "sha256": _sha256(payload),
        })
        for kind, pattern in command_patterns.items():
            for match in pattern.finditer(text):
                opening = match.end() - 1
                argument = _balanced_argument(text, opening)
                if argument is None:
                    continue
                entries.append({
                    "kind": kind,
                    "file": relative,
                    "line": text.count("\n", 0, match.start()) + 1,
                    "value": _compact_tex(argument),
                })
    index = {
        "schema_version": 1,
        "purpose": "compact-routing-index-not-a-substitute-for-source-evidence",
        "tex_root": str(tex_root.name),
        "files": files,
        "entries": entries,
    }
    _atomic_json(index_path, index)
    return index


def _artifact_complete(output: Path, provenance: dict[str, Any], arxiv_id: str) -> bool:
    if provenance.get("arxiv_id") != arxiv_id:
        return False
    artifacts = provenance.get("artifacts")
    if not isinstance(artifacts, dict):
        return False
    paths = [value for key, value in artifacts.items() if key != "tex_files"]
    return bool(paths) and all((output / str(path)).exists() for path in paths)


def materialize(ref: str, output: Path, force: bool = False) -> dict[str, Any]:
    arxiv_id = parse_arxiv_ref(ref)
    output = output.resolve()
    source_dir = output / "source"
    provenance_path = source_dir / "source-provenance.json"
    if provenance_path.exists() and not force:
        cached = json.loads(provenance_path.read_text(encoding="utf-8"))
        if _artifact_complete(output, cached, arxiv_id):
            cached["cache_status"] = "reused"
            return cached
        raise SourceError("existing provenance is incomplete or belongs to another source; use --force")

    data, content_type, final_url = download(arxiv_id)
    payload_kind, payload = detect_payload(data)
    if payload_kind == "pdf":
        pdf_payload, pdf_content_type, pdf_url = payload, content_type, final_url
    else:
        pdf_payload, pdf_content_type, pdf_url = download_pdf(arxiv_id)
    safe_id = arxiv_id.replace("/", "_")
    if force:
        for path in (source_dir / "tex", source_dir / "paper.pdf"):
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
    source_dir.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Any] = {}
    source_index_sha256: str | None = None
    source_index_bytes: int | None = None
    if payload_kind == "archive":
        archive_path = source_dir / f"arxiv-{safe_id}.tar.gz"
        _atomic_bytes(archive_path, payload)
        artifacts["archive_path"] = str(archive_path.relative_to(output))
        tex_root = source_dir / "tex"
        artifacts["tex_files"] = extract_archive(payload, tex_root)
        artifacts["tex_root"] = str(tex_root.relative_to(output))
    elif payload_kind == "tex":
        tex_root = source_dir / "tex"
        if tex_root.exists() and not force:
            raise SourceError(f"source tree already exists: {tex_root}; use --force")
        tex_root.mkdir(parents=True, exist_ok=True)
        tex_path = tex_root / "main.tex"
        _atomic_bytes(tex_path, payload)
        artifacts.update({"tex_root": str(tex_root.relative_to(output)), "tex_files": ["main.tex"]})
    if payload_kind in {"archive", "tex"}:
        source_index_path = source_dir / "source-index.json"
        build_source_index(source_dir / "tex", source_index_path)
        artifacts["source_index_path"] = str(source_index_path.relative_to(output))
        index_payload = source_index_path.read_bytes()
        source_index_sha256 = _sha256(index_payload)
        source_index_bytes = len(index_payload)
    pdf_path = source_dir / "paper.pdf"
    if pdf_path.exists() and not force:
        raise SourceError(f"source PDF already exists: {pdf_path}; use --force")
    _atomic_bytes(pdf_path, pdf_payload)
    artifacts["pdf_path"] = str(pdf_path.relative_to(output))

    provenance = {
        "schema_version": 1,
        "source_kind": "arxiv",
        "arxiv_id": arxiv_id,
        "version_pinned": bool(re.search(r"v\d+$", arxiv_id)),
        "requested_ref": ref,
        "retrieval_url": final_url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "content_type": content_type,
        "payload_kind": payload_kind,
        "payload_sha256": _sha256(payload),
        "payload_bytes": len(payload),
        "pdf_retrieval_url": pdf_url,
        "pdf_content_type": pdf_content_type,
        "pdf_sha256": _sha256(pdf_payload),
        "pdf_bytes": len(pdf_payload),
        "source_index_sha256": source_index_sha256,
        "source_index_bytes": source_index_bytes,
        "artifacts": artifacts,
        "cache_status": "downloaded",
    }
    _atomic_json(provenance_path, provenance)
    return provenance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ref", help="arXiv URL or identifier")
    parser.add_argument("--output", type=Path, default=Path.cwd(), help="paper root")
    parser.add_argument("--force", action="store_true", help="replace the existing source snapshot")
    args = parser.parse_args(argv)
    try:
        result = materialize(args.ref, args.output, force=args.force)
    except (OSError, ValueError, SourceError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
