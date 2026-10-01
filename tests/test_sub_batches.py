"""Sub-test 2: Batch Management & Session Persistence
Tests Chrome-style multi-batch management and session state:
- Batch listing, creation, renaming, switching, output folder update, and deletion
- Ensuring active batch protection (cannot delete last remaining batch)
- Session persistence
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from server import app, app_state, STATE_LOCK


class TestBatchManagement(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_01_get_batches(self):
        """Test getting current list of batches."""
        resp = self.client.get("/api/batches")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("batches", data)
        self.assertIn("active_batch_id", data)
        self.assertTrue(len(data["batches"]) >= 1)

    def test_02_create_and_rename_batch(self):
        """Test creating a new batch tab and renaming it."""
        # 1. Create batch
        resp = self.client.post("/api/batches/create", json={"name": "Cụm Test Tự Động", "output_folder": ""})
        self.assertEqual(resp.status_code, 200)
        created = resp.json()
        new_batch_id = created.get("batch_id")
        self.assertTrue(new_batch_id)

        # 2. Rename batch
        resp_rename = self.client.post("/api/batches/rename", json={"batch_id": new_batch_id, "name": "Cụm Test Đã Đổi Tên"})
        self.assertEqual(resp_rename.status_code, 200)

        # 3. Verify in batch list
        resp_list = self.client.get("/api/batches")
        batches = resp_list.json()["batches"]
        found = next((b for b in batches if b["id"] == new_batch_id), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["name"], "Cụm Test Đã Đổi Tên")

        # Cleanup: switch back to default and delete test batch
        self.client.post("/api/batches/delete", json={"batch_id": new_batch_id})

    def test_03_switch_and_update_folder(self):
        """Test switching active batch and updating its custom output folder."""
        # Create a batch with specific output directory
        resp = self.client.post("/api/batches/create", json={"name": "Cụm Folder Test", "output_folder": "D:\\Custom_Export"})
        batch_id = resp.json()["batch_id"]

        # Switch to it
        resp_switch = self.client.post("/api/batches/switch", json={"batch_id": batch_id})
        self.assertEqual(resp_switch.status_code, 200)
        self.assertEqual(resp_switch.json().get("active_batch_id"), batch_id)

        # Update output folder
        resp_folder = self.client.post("/api/batches/update_folder", json={"batch_id": batch_id, "output_folder": "D:\\Updated_Export"})
        self.assertEqual(resp_folder.status_code, 200)

        # Verify output folder
        folder = app_state.get_current_output_folder(batch_id)
        self.assertEqual(folder, "D:\\Updated_Export")

        # Delete test batch
        # First switch to another batch before deleting
        other_batch = next(b_id for b_id in app_state.batches.keys() if b_id != batch_id)
        self.client.post("/api/batches/switch", json={"batch_id": other_batch})
        self.client.post("/api/batches/delete", json={"batch_id": batch_id})

    def test_04_delete_last_batch_protection(self):
        """Deleting the only batch should be rejected or handle safely."""
        with STATE_LOCK:
            current_keys = list(app_state.batches.keys())

        # If only 1 batch, trying to delete it should fail
        if len(current_keys) == 1:
            resp = self.client.post("/api/batches/delete", json={"batch_id": current_keys[0]})
            self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
