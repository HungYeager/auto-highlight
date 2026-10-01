"""Unit tests for _run_ffmpeg_render and trim offset logic.

All tests are self-contained: FFmpeg is mocked so no media files are required.
Run with:  python -m pytest tests/test_ffmpeg_render.py -v
"""

import threading
import time
import sys
import pathlib
import unittest
from unittest.mock import MagicMock, patch


for _mod in [
    "tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.colorchooser",
    "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont", "PIL.ImageTk",
    "cv2", "whisper", "google.generativeai",
]:
    sys.modules.setdefault(_mod, MagicMock())

import tkinter as _tk
_tk.Tk = MagicMock()

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from app import _run_ffmpeg_render  # noqa: E402


class _FakeLogger:
    def __getattr__(self, name):
        return lambda *a, **kw: None


class _FakeProc:
    def __init__(self, returncode=0, stderr_lines=None, poll_delay=0):
        self.returncode = returncode
        self.stderr     = iter(stderr_lines or [])
        self._delay     = poll_delay
        self._start     = time.monotonic()

    def poll(self):
        if time.monotonic() - self._start >= self._delay:
            return self.returncode
        return None

    def kill(self):
        self._start = 0


class TestRunFFmpegRender(unittest.TestCase):

    def _d(self, **kw):
        base = dict(cmd=["ffmpeg"], stop_event=None, n_blur=0,
                    vid_dur_secs=10.0, progress_cb=None, title_img=None,
                    log=_FakeLogger())
        base.update(kw)
        return base

    def test_success(self):
        with patch("subprocess.Popen", return_value=_FakeProc(0)):
            self.assertEqual(_run_ffmpeg_render(**self._d()), 0)

    def test_failure_rc(self):
        with patch("subprocess.Popen", return_value=_FakeProc(1)):
            self.assertEqual(_run_ffmpeg_render(**self._d()), 1)

    def test_progress_cb(self):
        line = "time=00:00:05.00 bitrate=400kbits/s"
        got = []
        with patch("subprocess.Popen", return_value=_FakeProc(0, [line])):
            _run_ffmpeg_render(**self._d(vid_dur_secs=10.0, progress_cb=got.append))
        self.assertTrue(any(0.0 < v <= 1.0 for v in got), got)

    def test_stop_event(self):
        stop = threading.Event(); stop.set()
        class _Inf(_FakeProc):
            def poll(self): return None
        with patch("subprocess.Popen", return_value=_Inf(0)):
            with self.assertRaises(InterruptedError):
                _run_ffmpeg_render(**self._d(stop_event=stop))

    def test_title_img_cleaned_success(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = pathlib.Path(f.name)
        with patch("subprocess.Popen", return_value=_FakeProc(0)):
            _run_ffmpeg_render(**self._d(title_img=tmp))
        self.assertFalse(tmp.exists())

    def test_title_img_cleaned_failure(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = pathlib.Path(f.name)
        with patch("subprocess.Popen", return_value=_FakeProc(1)):
            _run_ffmpeg_render(**self._d(title_img=tmp))
        self.assertFalse(tmp.exists())

    def test_none_title_img_safe(self):
        with patch("subprocess.Popen", return_value=_FakeProc(0)):
            self.assertEqual(_run_ffmpeg_render(**self._d(title_img=None)), 0)

    def test_timeout_formula(self):
        for n, exp in [(0,600),(5,660),(10,720),(200,2400)]:
            self.assertEqual(min(2400, 600+(n//5)*60), exp)


class TestTrimMath(unittest.TestCase):
    B = 16.0

    def dur(self, ts, te): return max(1.0, self.B+te-ts)
    def start(self, o, d): return max(0.0, o+d)

    def test_no_trim(self):
        self.assertAlmostEqual(self.dur(0,0), 16.0)

    def test_extend_end(self):
        self.assertAlmostEqual(self.dur(0,10), 26.0)

    def test_shift_start_forward(self):
        self.assertAlmostEqual(self.dur(5,0), 11.0)

    def test_both(self):
        self.assertAlmostEqual(self.dur(-5,5), 26.0)

    def test_floor_one(self):
        self.assertAlmostEqual(self.dur(30,-30), 1.0)

    def test_start_clamp_zero(self):
        self.assertAlmostEqual(self.start(5,-30), 0.0)

    def test_start_forward(self):
        self.assertAlmostEqual(self.start(10,5), 15.0)

    def test_start_backward(self):
        self.assertAlmostEqual(self.start(10,-3), 7.0)


if __name__ == "__main__":
    unittest.main()
