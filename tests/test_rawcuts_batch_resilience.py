# -*- coding: utf-8 -*-
"""
Unit tests for:
1. Raw cuts start_time timestamp resolution in /api/cut
2. Batch send all candidates to Tab 2 (/api/candidates/send_all_to_edit)
3. Cross-machine _safe_resolve_path and output folder fallback
4. Subtitle directory resilience
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from server import app, app_state, STATE_LOCK, _safe_resolve_path
from app import _find_tool, _gemini_transcribe, _whisper_transcribe


class TestRawCutsBatchResilience(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.temp_dir = tempfile.mkdtemp(prefix="opencut_test_res_")
        self.out_dir = Path(self.temp_dir) / "output"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        app_state.config["output_folder"] = str(self.out_dir)

    def tearDown(self):
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def test_cut_uses_start_time_not_default_zero(self):
        """Test that /api/cut uses candidate start_time (e.g. 00:03:22) instead of 00:00:00."""
        dummy_video = Path(self.temp_dir) / "test_src.mp4"
        dummy_video.write_bytes(b"dummy_video_bytes")

        # Mock candidate with start_time as returned by Gemini
        cand = {
            "id": 1,
            "start_time": "00:03:22",
            "end_time": "00:03:38",
            "clip_duration": 16,
            "suggested_titles": ["Title 1", "Title 2"],
        }
        with STATE_LOCK:
            app_state.video_results[str(dummy_video)] = {
                "status": "done",
                "candidates": [cand]
            }

        with patch("server.get_video_duration", return_value=600.0), \
             patch("server.cut_clip_exact") as mock_cut:
            resp = self.client.post("/api/cut", json={
                "video_path": str(dummy_video),
                "candidate_index": 0,
                "title": "",
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            output_file = data["output"]
            # File name must reflect start timestamp 00-03-22, NOT 00-00-00
            self.assertIn("00-03-22", output_file)
            self.assertNotIn("00-00-00", output_file)
            # cut_clip_exact must have been called with start_ts="00:03:22"
            mock_cut.assert_called_once()
            call_args = mock_cut.call_args[0]
            self.assertEqual(call_args[1], "00:03:22")

    def test_send_all_candidates_to_edit(self):
        """Test /api/candidates/send_all_to_edit cuts all candidates and adds with Title #1."""
        dummy_video = Path(self.temp_dir) / "test_bulk.mp4"
        dummy_video.write_bytes(b"dummy_bulk_video")

        cands = [
            {
                "id": 1,
                "start_time": "00:01:10",
                "clip_duration": 16,
                "suggested_titles": ["First Title Clip 1", "Alt Title B"],
            },
            {
                "id": 2,
                "start_time": "00:05:40",
                "clip_duration": 20,
                "suggested_titles": ["First Title Clip 2", "Alt Title C"],
            },
        ]
        with STATE_LOCK:
            app_state.video_results[str(dummy_video)] = {
                "status": "done",
                "candidates": cands
            }
            app_state.edit_queue = []

        with patch("server.get_video_duration", return_value=900.0), \
             patch("server.cut_clip_exact") as mock_cut:
            resp = self.client.post("/api/candidates/send_all_to_edit", json={
                "video_path": str(dummy_video)
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "ok")
            self.assertEqual(data["added_count"], 2)
            self.assertEqual(len(data["entries"]), 2)

            # Check that first title was assigned
            self.assertEqual(data["entries"][0]["title"], "First Title Clip 1")
            self.assertEqual(data["entries"][1]["title"], "First Title Clip 2")

            # Check that timestamps are in the filenames
            self.assertIn("00-01-10", data["entries"][0]["name"])
            self.assertIn("00-05-40", data["entries"][1]["name"])

            # Check edit queue state in app_state
            self.assertEqual(len(app_state.edit_queue), 2)
            self.assertEqual(app_state.edit_queue[0]["title"], "First Title Clip 1")
            self.assertEqual(app_state.edit_queue[1]["title"], "First Title Clip 2")

    def test_safe_resolve_cross_machine_fallback(self):
        """Test _safe_resolve_path finds existing file by filename when absolute path has wrong drive."""
        real_file = self.out_dir / "raw_cuts" / "my_clip_01.mp4"
        real_file.parent.mkdir(parents=True, exist_ok=True)
        real_file.write_bytes(b"clip_bytes")

        # Fake path on non-existent drive Z:
        fake_remote_path = "Z:\\nonexistent\\folder\\raw_cuts\\my_clip_01.mp4"
        resolved = _safe_resolve_path(fake_remote_path)
        self.assertIsNotNone(resolved)
        self.assertTrue(resolved.exists())
        self.assertEqual(resolved.name, "my_clip_01.mp4")

    def test_output_folder_fallback_on_invalid_drive(self):
        """Test get_current_output_folder falls back gracefully when drive letter doesn't exist."""
        app_state.config["output_folder"] = "Z:\\nonexistent_drive_folder"
        if "default" in app_state.batches:
            app_state.batches["default"]["output_folder"] = "Z:\\nonexistent_drive_folder"

        folder = app_state.get_current_output_folder()
        self.assertIsNotNone(folder)
        # Must resolve to an existing writable directory
        self.assertTrue(Path(folder).exists())
        self.assertNotIn("Z:", folder)

    def test_transcribe_guards_against_missing_clip(self):
        """Test that transcribe functions return None gracefully when clip is missing."""
        missing_clip = Path(self.temp_dir) / "does_not_exist.mp4"
        logger = MagicMock()
        stop_event = MagicMock()

        res_gemini = _gemini_transcribe(missing_clip, None, "new", logger, stop_event)
        self.assertIsNone(res_gemini)

        res_whisper = _whisper_transcribe(missing_clip, logger)
        self.assertIsNone(res_whisper)


if __name__ == "__main__":
    unittest.main()
