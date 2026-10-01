"""Unit tests for Tab 2 Gemini Key Rotation and 429 retry mechanism."""

import threading
import sys
import pathlib
import unittest
from unittest.mock import MagicMock, patch

for _mod in [
    "tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.colorchooser",
    "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont", "PIL.ImageTk",
    "cv2", "whisper", "google.generativeai", "fastapi", "fastapi.responses",
    "fastapi.middleware", "fastapi.middleware.cors", "fastapi.staticfiles",
    "uvicorn",
]:
    sys.modules.setdefault(_mod, MagicMock())

import tkinter as _tk
_tk.Tk = MagicMock()

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from app import KeyRotator
from server import _gemini_generate_video_title


class TestGeminiTitleRotation(unittest.TestCase):

    def test_key_rotation_on_429_quota_error(self):
        """Simulate 429 RESOURCE_EXHAUSTED on first key, success on second key."""
        rotator = KeyRotator(["key1", "key2"])
        stop_event = threading.Event()
        logs = []

        fake_remote = MagicMock(uri="https://fake.uri", mime_type="video/mp4")

        call_count = 0
        def fake_build_client(key):
            nonlocal call_count
            call_count += 1
            mock_client = MagicMock()
            mock_model = MagicMock()
            if key == "key1":
                mock_model.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: Quota exceeded")
            else:
                mock_resp = MagicMock()
                mock_resp.text = "COP STOPS SPEEDER INSTANT REGRET"
                mock_model.generate_content.return_value = mock_resp
            mock_client.GenerativeModel.return_value = mock_model
            return mock_client, "old"

        with patch("server.build_client", side_effect=fake_build_client), \
             patch("server.upload_video", return_value=fake_remote), \
             patch("server.delete_remote", return_value=None):
            
            title, err = _gemini_generate_video_title(
                video_path=pathlib.Path("test_video.mp4"),
                prompt_tpl=None,
                rotator=rotator,
                model_name="gemini-3.5-flash-lite",
                stop_event=stop_event,
                log_fn=lambda lvl, msg: logs.append((lvl, msg)),
            )

        self.assertEqual(title, "COP STOPS SPEEDER INSTANT REGRET")
        self.assertIsNone(err)
        self.assertEqual(call_count, 2)

    def test_all_keys_exhausted_returns_error(self):
        """When all keys return 429 quota exhausted, returns error description."""
        rotator = KeyRotator(["key1", "key2"])
        stop_event = threading.Event()
        logs = []
        fake_remote = MagicMock(uri="https://fake.uri", mime_type="video/mp4")

        def fake_build_client(key):
            mock_client = MagicMock()
            mock_model = MagicMock()
            mock_model.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: Quota exceeded")
            mock_client.GenerativeModel.return_value = mock_model
            return mock_client, "old"

        with patch("server.build_client", side_effect=fake_build_client), \
             patch("server.upload_video", return_value=fake_remote), \
             patch("server.delete_remote", return_value=None):
            
            title, err = _gemini_generate_video_title(
                video_path=pathlib.Path("test_video.mp4"),
                prompt_tpl=None,
                rotator=rotator,
                model_name="gemini-3.5-flash-lite",
                stop_event=stop_event,
                log_fn=lambda lvl, msg: logs.append((lvl, msg)),
            )

        self.assertIsNone(title)
        self.assertIn("429", str(err))


if __name__ == "__main__":
    unittest.main()
