"""Sub-test 3: Video Re-analysis & Key Rotation
Tests /api/videos/reanalyze endpoint:
- Rejects requests with missing paths (HTTP 400)
- Rejects non-existent video files (HTTP 404)
- Successfully resets status to QUEUED and queues background analysis for valid video
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from server import app, app_state, ST_QUEUED, _norm_path


class TestReanalysis(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_reanalyze_missing_path(self):
        """Reanalyze with empty payload should return HTTP 400."""
        resp = self.client.post("/api/videos/reanalyze", json={})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Missing video path", resp.json().get("detail", ""))

    def test_reanalyze_nonexistent_file(self):
        """Reanalyze a non-existent file path should return HTTP 404."""
        resp = self.client.post("/api/videos/reanalyze", json={"path": "C:/nonexistent_file_12345.mp4"})
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json().get("detail", "").lower())

    @patch("server._run_analysis_worker", return_value=None)
    def test_reanalyze_valid_file(self, mock_worker):
        """Reanalyze an existing video file queues it and returns ok."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            temp_path = Path(f.name)

        try:
            resp = self.client.post("/api/videos/reanalyze", json={"path": str(temp_path)})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json().get("status"), "ok")

            # Check status was reset to QUEUED
            norm_k = _norm_path(temp_path)
            self.assertIn(norm_k, app_state.video_results)
            self.assertEqual(app_state.video_results[norm_k]["status"], ST_QUEUED)
        finally:
            if temp_path.exists():
                temp_path.unlink()


if __name__ == "__main__":
    unittest.main()
