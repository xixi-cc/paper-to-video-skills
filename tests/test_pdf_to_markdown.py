from __future__ import annotations

import argparse
import importlib.util
import os
import sys
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


class PdfToMarkdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.converter = load_module(
            "test_pdf_to_markdown_converter",
            ROOT / "pdf-to-markdown" / "convert.py",
        )

    def api_args(self, **overrides):
        values = {
            "lang": "en",
            "api_model": "auto",
            "timeout": 300,
            "pages": None,
            "ocr": False,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_open_api_command_never_contains_a_token(self) -> None:
        command = self.converter.build_open_api_command(
            "/usr/bin/mineru-open-api",
            Path("/tmp/paper.pdf"),
            Path("/tmp/output"),
            self.api_args(pages="1-2", ocr=True),
        )
        self.assertEqual(command[:2], ["/usr/bin/mineru-open-api", "extract"])
        self.assertIn("--pages", command)
        self.assertIn("--ocr", command)
        self.assertNotIn("--token", command)
        self.assertNotIn("MINERU_TOKEN", " ".join(command))

    def test_default_engine_is_local(self) -> None:
        args = self.converter.build_parser().parse_args(["paper.pdf", "output"])
        self.assertEqual(args.engine, "local")

    def test_configured_binary_must_be_executable(self) -> None:
        # Use the Linux filesystem because WSL's Windows-mounted temp directory
        # does not preserve POSIX execute bits.
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            binary = Path(directory) / "mineru-open-api"
            binary.write_text("not executable", encoding="utf-8")
            binary.chmod(0o600)
            with patch.dict(
                os.environ,
                {self.converter.OPEN_API_ENV: str(binary)},
                clear=False,
            ):
                with self.assertRaisesRegex(SystemExit, "not an executable"):
                    self.converter.resolve_open_api_binary()


if __name__ == "__main__":
    unittest.main()
