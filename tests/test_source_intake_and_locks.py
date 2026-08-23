from __future__ import annotations

import importlib.util
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def source_archive() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, data in {
            "paper/main.tex": (
                b"\\documentclass{article}\n"
                b"\\begin{document}\n"
                b"\\section{Method}\n"
                b"\\includegraphics{figures/result.pdf}\n"
                b"\\caption{Matched-budget result}\n"
                b"\\begin{equation}x=1\\label{eq:result}\\end{equation}\n"
                b"\\end{document}\n"
            ),
            "paper/figures/result.pdf": b"synthetic-vector-figure",
        }.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class ArxivSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = load_module(
            "test_arxiv_source",
            ROOT / "paper-download-arxiv-source" / "scripts" / "download_source.py",
        )

    def test_parse_modern_legacy_and_url_references(self) -> None:
        self.assertEqual(self.source.parse_arxiv_ref("2509.07996v4"), "2509.07996v4")
        self.assertEqual(
            self.source.parse_arxiv_ref("https://arxiv.org/pdf/2509.07996v4.pdf"),
            "2509.07996v4",
        )
        self.assertEqual(self.source.parse_arxiv_ref("hep-th/9901001v2"), "hep-th/9901001v2")
        with self.assertRaises(self.source.SourceError):
            self.source.parse_arxiv_ref("https://example.com/abs/2509.07996")

    def test_materialize_writes_hash_backed_provenance_and_reuses_it(self) -> None:
        payload = source_archive()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            self.source,
            "download",
            return_value=(payload, "application/gzip", "https://arxiv.org/e-print/2509.07996v4"),
        ) as mocked_download, patch.object(
            self.source,
            "download_pdf",
            return_value=(b"%PDF-synthetic", "application/pdf", "https://arxiv.org/pdf/2509.07996v4"),
        ) as mocked_pdf:
            root = Path(directory)
            receipt = self.source.materialize("2509.07996v4", root)
            self.assertTrue((root / "source" / "tex" / "main.tex").is_file())
            self.assertTrue((root / "source" / "tex" / "figures" / "result.pdf").is_file())
            self.assertTrue((root / "source" / "paper.pdf").is_file())
            index_path = root / "source" / "source-index.json"
            self.assertTrue(index_path.is_file())
            index = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(index["files"][0]["path"], "main.tex")
            self.assertEqual(
                {entry["kind"] for entry in index["entries"]},
                {"section", "figure", "caption", "equation_label"},
            )
            self.assertEqual(
                receipt["artifacts"]["source_index_path"],
                "source/source-index.json",
            )
            self.assertEqual(len(receipt["payload_sha256"]), 64)
            self.assertEqual(len(receipt["pdf_sha256"]), 64)
            self.assertEqual(len(receipt["source_index_sha256"]), 64)
            self.assertGreater(receipt["source_index_bytes"], 0)
            self.assertTrue(receipt["version_pinned"])
            cached = self.source.materialize("2509.07996v4", root)
            self.assertEqual(cached["cache_status"], "reused")
            mocked_download.assert_called_once()
            mocked_pdf.assert_called_once()

    def test_archive_links_are_rejected(self) -> None:
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            link = tarfile.TarInfo("paper/escape")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../outside"
            archive.addfile(link)
        with self.assertRaises(self.source.SourceError):
            self.source._safe_members(buffer.getvalue())


class ManifestSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_module(
            "test_presentation_manifest_source",
            ROOT / "paper-to-video" / "scripts" / "presentation_manifest.py",
        )

    def valid_manifest(self) -> dict:
        slides = [{
            "id": "title",
            "kind": "title",
            "latex_body": "\\titlepage",
            "evidence": [],
        }]
        for index in range(1, 6):
            is_figure = index == 1
            body = f"\\includegraphics{{figure-{index}.pdf}}" if is_figure else "技术内容"
            if index == 2:
                body += "\\[x=1\\]"
            slides.append({
                "id": f"slide-{index}",
                "kind": "figure" if is_figure else "content",
                "frame_options": "plain,c" if is_figure else "",
                "latex_body": body,
                "evidence": [{
                    "claim": "论文支持的结论",
                    "paper_page": index,
                    **({"figure": f"Figure {index}", "asset_sha256": "a" * 64} if is_figure else {}),
                }],
            })
        return {
            "schema_version": 2,
            "paper": {
                "title_zh": "测试论文",
                "title_en": "Test Paper",
                "short_title": "Test",
                "authors": ["A. Author"],
                "venue": "arXiv",
                "year": "2026",
            },
            "source": {
                "primary_format": "tex",
                "provenance_path": "source/source-provenance.json",
                "arxiv_id": "2509.07996v4",
                "version_pinned": True,
                "tex_root": "source/tex",
            },
            "slides": slides,
        }

    def test_load_manifest_checks_source_receipt_and_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source" / "tex").mkdir(parents=True)
            provenance = {
                "schema_version": 1,
                "arxiv_id": "2509.07996v4",
                "payload_sha256": "b" * 64,
                "pdf_sha256": "c" * 64,
            }
            (root / "source" / "source-provenance.json").write_text(
                json.dumps(provenance), encoding="utf-8"
            )
            slides_dir = root / "slides-beamer"
            slides_dir.mkdir()
            (slides_dir / "main.tex").write_text(
                "\\input{presentation_metadata.tex}\n"
                "\\input{presentation_frames.tex}\n",
                encoding="utf-8",
            )
            (slides_dir / "figure-1.pdf").write_bytes(b"synthetic figure")
            path = root / "paper_presentation.json"
            path.write_text(json.dumps(self.valid_manifest()), encoding="utf-8")
            loaded = self.manifest.load_manifest(path)
            self.assertEqual(loaded["source"]["primary_format"], "tex")
            rendered = self.manifest.render_manifest(root)
            self.assertEqual(rendered["slides"], len(self.valid_manifest()["slides"]))
            frames = (root / "slides-beamer" / "presentation_frames.tex").read_text(
                encoding="utf-8"
            )
            self.assertIn(r"\begin{frame}[plain,c]", frames)
            self.assertNotIn("NARRATION", frames)
            provenance["arxiv_id"] = "2509.07996v3"
            (root / "source" / "source-provenance.json").write_text(
                json.dumps(provenance), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "does not match"):
                self.manifest.load_manifest(path)

    def test_semantic_macros_are_counted_and_kind_checked(self) -> None:
        manifest = self.valid_manifest()
        manifest["slides"][1]["latex_body"] = (
            r"\paperfigure{figure-1.pdf}{1}{Measured trend and condition.}{Visible conclusion.}"
        )
        manifest["slides"][2].update({
            "kind": "equation",
            "latex_body": (
                r"\equationderivation{Linear regime.}{x&=1}{Defines x.}{Therefore x is fixed.}"
            ),
        })
        manifest["slides"][3].update({
            "kind": "comparison",
            "latex_body": (
                r"\baselinecomparison{Same budget.}{Accuracy}{80\%}{85\%}{+5 pp}{The method improves.}"
            ),
        })
        report = self.manifest.validate_manifest(manifest)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["semantic_frame_counts"], {
            "paperfigure": 1,
            "equationderivation": 1,
            "baselinecomparison": 1,
        })
        manifest["slides"][3]["kind"] = "content"
        report = self.manifest.validate_manifest(manifest)
        self.assertIn(
            "slides[3] uses \\baselinecomparison but kind is not 'comparison'",
            report["errors"],
        )

    def test_beamer_manifest_rejects_video_and_publication_fields(self) -> None:
        manifest = self.valid_manifest()
        manifest["slides"][1]["narration"] = "不应写入 Beamer 清单"
        manifest["publication"] = {"title": "不应写入 Beamer 清单"}
        report = self.manifest.validate_manifest(manifest)
        self.assertFalse(report["valid"])
        self.assertTrue(any("obsolete v1" in item for item in report["errors"]))
        self.assertTrue(any("narration" in item for item in report["errors"]))


class BiliupLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.uploader = load_module(
            "test_bilibili_uploader_locks",
            ROOT / "bilibili-video-uploader" / "scripts" / "upload.py",
        )

    def test_biliup_command_detection_is_scoped(self) -> None:
        self.assertTrue(self.uploader.is_biliup_command(["python", "-m", "biliup", "upload"]))
        self.assertTrue(self.uploader.is_biliup_command(["/venv/bin/biliup", "upload"]))
        self.assertFalse(self.uploader.is_biliup_command(["python", "unrelated_upload.py"]))

    def test_cleanup_requires_explicit_confirmation_before_loading_psutil(self) -> None:
        with self.assertRaisesRegex(SystemExit, "Cleanup blocked"):
            self.uploader.cleanup_locks(False)

    def test_free_form_nonempty_description_is_accepted(self) -> None:
        metadata = {
            "title": "论文解读",
            "tags": ["论文"],
            "description": "用简短的自然语言介绍这篇论文。",
            "copyright": 1,
        }
        self.uploader.validate_metadata(metadata)

    def test_empty_description_is_rejected(self) -> None:
        with self.assertRaisesRegex(SystemExit, "description is empty"):
            self.uploader.validate_metadata({
                "title": "论文解读", "tags": ["论文"], "description": "",
            })


if __name__ == "__main__":
    unittest.main()
