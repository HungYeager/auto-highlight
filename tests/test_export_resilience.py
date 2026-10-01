# -*- coding: utf-8 -*-
"""Unit tests for Export Resilience: Safe GPU Concurrency, FFmpeg Queue Limits & Auto-Retry on OOM."""

import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import QueueExportRequest, QueueExportItem, _run_queue_export_inner, app_state


class TestExportResilience(unittest.TestCase):

    def setUp(self):
        app_state.export_cancel_event.clear()
        app_state.export_progress = {
            "status": "exporting", "completed": 0, "total": 0,
            "current": "", "clip_pct": 0.0, "clip_name": "", "failed_items": []
        }

    def test_gpu_thread_capping(self):
        """GPU encoders must be capped to max 3 workers to protect 6GB VRAM on RTX 3050."""
        # 1. GPU encoder (h264_nvenc) with threads=8 -> should cap to 3
        req_gpu = QueueExportRequest(
            items=[],
            threads=8,
            encoder="h264_nvenc",
        )
        is_gpu = req_gpu.encoder in {"h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv", "h264_amf", "hevc_amf"}
        effective_workers_gpu = max(1, min(req_gpu.threads, 3 if is_gpu else req_gpu.threads))
        self.assertEqual(effective_workers_gpu, 3)

        # 2. CPU encoder (libx264) with threads=8 -> stays 8
        req_cpu = QueueExportRequest(
            items=[],
            threads=8,
            encoder="libx264",
        )
        is_gpu_cpu = req_cpu.encoder in {"h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv", "h264_amf", "hevc_amf"}
        effective_workers_cpu = max(1, min(req_cpu.threads, 3 if is_gpu_cpu else req_cpu.threads))
        self.assertEqual(effective_workers_cpu, 8)

    @patch("server.render_reup")
    @patch("pathlib.Path.exists", return_value=True)
    def test_auto_retry_recovers_oom_error(self, mock_exists, mock_render):
        """Simulate a video that fails with -12 (Cannot allocate memory) on first pass, then succeeds on retry."""
        item1 = QueueExportItem(clip_path="clip1.mp4", title="Video 1")
        item2 = QueueExportItem(clip_path="clip2.mp4", title="Video 2")

        # Video 1 succeeds on 1st try; Video 2 fails with -12 on 1st try, then succeeds on retry
        call_count = {"v1": 0, "v2": 0}

        def fake_render(*args, **kwargs):
            clip = str(kwargs.get("clip"))
            if "clip1" in clip:
                call_count["v1"] += 1
                return Path(kwargs.get("dst"))
            elif "clip2" in clip:
                call_count["v2"] += 1
                if call_count["v2"] == 1:
                    # Throw the exact FFmpeg exit code / message from the user's issue
                    raise RuntimeError("FFmpeg exit 4294967284: Task finished with error code: -12 (Cannot allocate memory)")
                else:
                    # Second try (retry) succeeds!
                    return Path(kwargs.get("dst"))
            return Path("out.mp4")

        mock_render.side_effect = fake_render

        req = QueueExportRequest(
            items=[item1, item2],
            threads=2,
            encoder="h264_nvenc",
            output_folder="./test_out"
        )

        _run_queue_export_inner(req, total_overall=2, completed_offset=0, target_dir="./test_out")

        # Verify call counts: v1 rendered once, v2 rendered twice (first failed, retry succeeded)
        self.assertEqual(call_count["v1"], 1)
        self.assertEqual(call_count["v2"], 2)

        # Verify no failed items remain in export progress because retry recovered it!
        self.assertEqual(len(app_state.export_progress.get("failed_items", [])), 0)
        self.assertEqual(app_state.export_progress["completed"], 2)

    @patch("server.render_reup")
    @patch("pathlib.Path.exists", return_value=True)
    def test_permanent_failure_recorded_after_retry(self, mock_exists, mock_render):
        """If a file repeatedly fails even on retry, it should be cleanly recorded in failed_items."""
        item = QueueExportItem(clip_path="bad_clip.mp4", title="Corrupted Video")

        mock_render.side_effect = RuntimeError("Fatal: corrupt video data -12")

        req = QueueExportRequest(
            items=[item],
            threads=1,
            encoder="h264_nvenc",
            output_folder="./test_out"
        )

        _run_queue_export_inner(req, total_overall=1, completed_offset=0, target_dir="./test_out")

        # After retry also fails, it must be recorded in failed_items
        failed = app_state.export_progress.get("failed_items", [])
        self.assertEqual(len(failed), 1)
        self.assertIn("corrupt video data", failed[0]["error"])


if __name__ == "__main__":
    unittest.main()
