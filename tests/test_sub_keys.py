"""Sub-test 4: Bulk API Keys & KeyRotator
Tests KeyRotator mechanics and config updates for multi-key bulk pasting:
- KeyRotator least-connection balancing
- Cooldown penalization on rate limit or network error
- Updating config with bulk API keys list
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app import KeyRotator
from server import app
from fastapi.testclient import TestClient


class TestKeyRotation(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_key_rotator_least_connections(self):
        keys = ["KEY_ALPHA", "KEY_BETA", "KEY_GAMMA"]
        rotator = KeyRotator(keys)

        # First acquire should give one key, second acquire should balance to a different key
        k1 = rotator.acquire()
        k2 = rotator.acquire()
        self.assertNotEqual(k1, k2)

        rotator.release(k1)
        rotator.release(k2)

    def test_key_rotator_penalty(self):
        keys = ["KEY_FAILING", "KEY_HEALTHY"]
        rotator = KeyRotator(keys)

        # Penalize KEY_FAILING with 60s cooldown
        rotator.penalize("KEY_FAILING", 60.0)

        # Next acquire must be KEY_HEALTHY
        k = rotator.acquire()
        self.assertEqual(k, "KEY_HEALTHY")
        rotator.release(k)

    def test_config_bulk_keys_update(self):
        sample_keys = [
            "AIzaSyDemoKey11111111111111111111111",
            "AIzaSyDemoKey22222222222222222222222",
            "AIzaSyDemoKey33333333333333333333333",
        ]
        resp = self.client.post("/api/config", json={"api_keys": sample_keys})
        self.assertEqual(resp.status_code, 200)

        # Verify saved in config
        resp_get = self.client.get("/api/config")
        self.assertEqual(resp_get.status_code, 200)
        saved_keys = resp_get.json().get("api_keys", [])
        self.assertEqual(saved_keys, sample_keys)


if __name__ == "__main__":
    unittest.main()
