"""Sub-test 5: SSE Event Bus & Progress Streaming
Tests real-time SSE progress events and status updates:
- SSEBus subscription, push, broadcast, and unsubscription
- Export status reporting
"""

import sys
import unittest
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from server import app, _sse_bus, app_state
from fastapi.testclient import TestClient


class TestSSEAndProgress(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_sse_bus_broadcast(self):
        """Test subscribing to SSE bus and receiving pushed events."""
        q1 = _sse_bus.subscribe()
        q2 = _sse_bus.subscribe()

        try:
            _sse_bus.push("test_event", {"message": "hello world", "val": 42})

            # Check both subscribers got the payload
            self.assertFalse(q1.empty())
            self.assertFalse(q2.empty())

            raw1 = q1.get_nowait()
            data1 = json.loads(raw1)
            self.assertEqual(data1.get("type"), "test_event")
            self.assertEqual(data1.get("data", {}).get("val"), 42)

            raw2 = q2.get_nowait()
            data2 = json.loads(raw2)
            self.assertEqual(data2.get("type"), "test_event")
            self.assertEqual(data2.get("data", {}).get("val"), 42)
        finally:
            _sse_bus.unsubscribe(q1)
            _sse_bus.unsubscribe(q2)

    def test_export_status_endpoint(self):
        """Test getting real-time export progress."""
        resp = self.client.get("/api/export/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("status", data)
        self.assertIn("completed", data)
        self.assertIn("total", data)


if __name__ == "__main__":
    unittest.main()
