from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SUITE_DIR = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CompletionEventTests(unittest.TestCase):
    def test_paper_event_waits_for_all_pages_and_propagates_failure(self) -> None:
        worker = load_module(
            "test_indextts2_worker",
            SUITE_DIR / "pdf-slides-to-video" / "scripts" / "indextts2_worker.py",
        )
        tasks = [
            {"name": "paper-a:slide_001", "paper_id": "paper-a"},
            {"name": "paper-a:slide_002", "paper_id": "paper-a"},
        ]
        events: list[dict] = []
        record = worker._completion_recorder(tasks, events.append)

        record(worker._task_result(tasks[1], status="generated"))
        self.assertEqual([event["type"] for event in events], ["page_done"])
        record(worker._task_result(tasks[0], status="failed", error="synthetic"))

        self.assertEqual(
            [event["type"] for event in events],
            ["page_done", "page_done", "paper_done"],
        )
        self.assertEqual(events[-1]["status"], "failed")
        self.assertEqual(
            [item["name"] for item in events[-1]["tasks"]],
            ["paper-a:slide_001", "paper-a:slide_002"],
        )


class PipelineOverlapTests(unittest.TestCase):
    def test_first_paper_enters_post_before_tts_worker_returns(self) -> None:
        batch = load_module(
            "test_batch",
            SUITE_DIR / "paper-to-video" / "scripts" / "batch.py",
        )
        post_started = threading.Event()
        overlap_observed = threading.Event()

        def fake_prepare(paper, force_compile=False, latex_semaphore=None):
            paper_id = paper["id"]
            return {
                "paper_id": paper_id,
                "paper": paper,
                "root": Path(temp_dir) / paper_id,
                "tasks": [{
                    "name": f"{paper_id}:slide_001",
                    "paper_id": paper_id,
                    "slide": "slide_001",
                    "text": "synthetic",
                    "output": str(Path(temp_dir) / paper_id / "slide_001.mp3"),
                }],
            }

        def fake_post(context, tts_results, segment_executor, ffmpeg_semaphore):
            if context["paper_id"] == "paper-a":
                post_started.set()
            return {"paper": context["root"].name, "status": "video_done"}

        def fake_tts(backend, tasks, config_path=None, on_event=None):
            assert on_event is not None
            results = []
            for paper_id in ("paper-a", "paper-b"):
                result = {
                    "name": f"{paper_id}:slide_001",
                    "paper_id": paper_id,
                    "slide": "slide_001",
                    "status": "generated",
                }
                on_event({
                    "type": "paper_done",
                    "paper_id": paper_id,
                    "status": "complete",
                    "tasks": [result],
                })
                results.append(result)
                if paper_id == "paper-a" and post_started.wait(timeout=2):
                    overlap_observed.set()
            return {"backend": "indextts2", "tasks": results}

        fake_backend = types.ModuleType("tts_backends")
        fake_backend.load_tts_config = lambda path=None: {
            "synthesis": {"audio_normalization_workers": 1}
        }
        fake_backend.run_local_tts_batch = fake_tts

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            sys.modules, {"tts_backends": fake_backend}
        ), patch.object(batch, "prepare_paper", side_effect=fake_prepare), patch.object(
            batch, "postprocess_paper", side_effect=fake_post
        ), contextlib.redirect_stdout(io.StringIO()):
            summary = batch.run_pipeline(
                [{"id": "paper-a"}, {"id": "paper-b"}],
                cpu_workers=1,
                post_workers=1,
                latex_workers=1,
                ffmpeg_workers=3,
                config_path=None,
                force_compile=False,
            )

        self.assertTrue(overlap_observed.is_set())
        self.assertEqual(summary["status"], "complete")
        self.assertGreaterEqual(
            summary["overlap"]["papers_submitted_to_post_before_tts_finished"], 1
        )
        self.assertEqual(summary["resources"]["ffmpeg_workers_reserved_for_tts"], 1)
        self.assertEqual(summary["resources"]["ffmpeg_workers_available_to_post"], 2)

    def test_narrations_json_requires_exact_page_coverage(self) -> None:
        batch = load_module(
            "test_batch_narration",
            SUITE_DIR / "paper-to-video" / "scripts" / "batch.py",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frame_dir = root / "frames"
            frame_dir.mkdir()
            slides = {
                "slide_001": frame_dir / "slide_001.png",
                "slide_002": frame_dir / "slide_002.png",
            }
            for path in slides.values():
                path.write_bytes(b"png")
            narration_path = root / "narrations.json"
            narration_path.write_text(
                '{"slide_001": "第一页", "slide_002": "第二页"}',
                encoding="utf-8",
            )
            result = batch.write_narration_files(narration_path, frame_dir, slides)
            self.assertEqual(result["pages"], 2)
            self.assertEqual((frame_dir / "slide_002.txt").read_text().strip(), "第二页")
            narration_path.write_text('{"slide_001": "第一页"}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "coverage mismatch"):
                batch.write_narration_files(narration_path, frame_dir, slides)


if __name__ == "__main__":
    unittest.main()
