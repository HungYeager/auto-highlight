"""Sub-test 1: Folder Operations & Batch Folders
Tests opening folders via API (/api/open_folder, /open_folder, /api/open_raw_cuts, /api/open_export_folder)
Ensures auto-creation of folders on disk if they don't exist yet and backward compatibility for payload keys.
"""

import sys
import shutil
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

# Add parent directory to path
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from server import app, app_state


class TestFolderOperations(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.temp_dir = Path(tempfile.mkdtemp(prefix="opencut_test_folders_"))

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("os.startfile", return_value=None)
    def test_open_folder_with_path_key(self, mock_startfile):
        """Test opening a folder using {"path": ...} as sent by App.jsx."""
        cluster_dir = self.temp_dir / "Cum_1_Output"
        self.assertFalse(cluster_dir.exists())

        response = self.client.post("/api/open_folder", json={"path": str(cluster_dir)})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("ok"))

        # Check directory was automatically created on disk
        self.assertTrue(cluster_dir.exists())
        mock_startfile.assert_called_once()

    @patch("os.startfile", return_value=None)
    def test_open_folder_with_folder_key(self, mock_startfile):
        """Test opening a folder using legacy {"folder": ...} parameter."""
        cluster_dir = self.temp_dir / "Cum_2_Legacy"
        self.assertFalse(cluster_dir.exists())

        response = self.client.post("/api/open_folder", json={"folder": str(cluster_dir)})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("ok"))
        self.assertTrue(cluster_dir.exists())

    @patch("os.startfile", return_value=None)
    def test_open_folder_empty_fallback(self, mock_startfile):
        """Test opening with empty payload falls back to default output_folder."""
        with patch.object(app_state, "get_current_output_folder", return_value=str(self.temp_dir)):
            response = self.client.post("/api/open_folder", json={})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json().get("ok"))

    @patch("os.startfile", return_value=None)
    def test_open_raw_cuts_folder(self, mock_startfile):
        """Test /api/open_raw_cuts endpoint auto-creates raw_cuts subdirectory."""
        with patch.object(app_state, "get_current_output_folder", return_value=str(self.temp_dir)):
            raw_cuts_expected = self.temp_dir / "raw_cuts"
            self.assertFalse(raw_cuts_expected.exists())

            response = self.client.post("/api/open_raw_cuts", json={})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json().get("ok"))
            self.assertTrue(raw_cuts_expected.exists())

    @patch("os.startfile", return_value=None)
    def test_open_export_folder(self, mock_startfile):
        """Test /api/open_export_folder endpoint."""
        with patch.object(app_state, "get_current_output_folder", return_value=str(self.temp_dir)):
            response = self.client.post("/api/open_export_folder", json={})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json().get("ok"))


if __name__ == "__main__":
    unittest.main()
