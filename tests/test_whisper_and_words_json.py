import unittest
import json
import tempfile
from pathlib import Path
from app import _burn_subtitles_pass, _whisper_transcribe

class DummyLogger:
    def info(self, m): pass
    def ok(self, m): pass
    def warn(self, m): pass
    def error(self, m): pass
    def dim(self, m): pass
    def header(self, m): pass

class TestWhisperAndWordsJson(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.srt_path = self.tmp_dir / "sample.srt"
        self.words_path = self.tmp_dir / "sample.words.json"
        self.dummy_video = self.tmp_dir / "sample.mp4"
        self.dummy_video.write_bytes(b"\x00" * 1024)

        # 1 cue in SRT
        self.srt_path.write_text(
            "1\n00:00:01,000 --> 00:00:03,000\nFast speaker shouts stop\n\n",
            encoding="utf-8"
        )

        # Acoustic timestamps: speaker spoke "Fast speaker" very quickly (1.0s to 1.4s),
        # paused, then "shouts stop" (2.2s to 2.8s)
        self.words_data = [
            {"word": "Fast", "start": 1.000, "end": 1.150},
            {"word": "speaker", "start": 1.150, "end": 1.400},
            {"word": "shouts", "start": 2.200, "end": 2.500},
            {"word": "stop", "start": 2.500, "end": 2.800},
        ]
        self.words_path.write_text(json.dumps(self.words_data), encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_word_pop_uses_real_words_json(self):
        """Verify Word Pop mode uses timestamps from .words.json instead of dividing cue linearly."""
        st = {
            "sub_style": "Word Pop",
            "subtitles": True,
            "sub_offset_ms": 0,
            "sub_font_size": 40,
        }
        logger = DummyLogger()
        _burn_subtitles_pass(
            src=self.dummy_video,
            srt_path=self.srt_path,
            st=st,
            log=logger,
            words_json_path=self.words_path
        )
        
        # Look for the generated wordpop ASS file in temp dir
        tmp_files = list(Path(tempfile.gettempdir()).glob("wordpop_*sample*.ass"))
        self.assertTrue(len(tmp_files) > 0, "ASS file for Word Pop was not generated")
        latest_ass = sorted(tmp_files, key=lambda f: f.stat().st_mtime)[-1]
        content = latest_ass.read_text(encoding="utf-8-sig")

        # Fast started at 1.000 (0:00:01.00)
        self.assertIn("0:00:01.00", content)
        self.assertIn("Fast", content)
        self.assertIn("shouts", content)
        # Verify the 4 acoustic words are represented
        dialogue_lines = [l for l in content.splitlines() if l.startswith("Dialogue:")]
        self.assertEqual(len(dialogue_lines), 4)

    def test_karaoke_highlight_uses_real_words_json(self):
        """Verify Highlight Line mode uses acoustic word timestamps from .words.json."""
        st = {
            "sub_style": "Highlight Line",
            "subtitles": True,
            "sub_offset_ms": 0,
            "sub_font_size": 40,
        }
        logger = DummyLogger()
        _burn_subtitles_pass(
            src=self.dummy_video,
            srt_path=self.srt_path,
            st=st,
            log=logger,
            words_json_path=self.words_path
        )

        tmp_files = list(Path(tempfile.gettempdir()).glob("karaoke_*sample*.ass"))
        self.assertTrue(len(tmp_files) > 0, "ASS file for Karaoke was not generated")
        latest_ass = sorted(tmp_files, key=lambda f: f.stat().st_mtime)[-1]
        content = latest_ass.read_text(encoding="utf-8-sig")

        # Must have \k karaoke duration tags
        self.assertIn(r"{\k", content)
        self.assertIn("Fast", content)
        self.assertIn("speaker", content)

    def test_fallback_when_no_words_json(self):
        """Verify fallback to interpolated cue when .words.json does not exist."""
        st = {
            "sub_style": "Word Pop",
            "subtitles": True,
            "sub_offset_ms": 0,
            "sub_font_size": 40,
        }
        logger = DummyLogger()
        fake_video = self.tmp_dir / "fallback_vid.mp4"
        fake_video.write_bytes(b"\x00" * 1024)
        fake_words = self.tmp_dir / "non_existent.words.json"
        fake_srt = self.tmp_dir / "no_json.srt"
        fake_srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello world\n\n", encoding="utf-8")

        _burn_subtitles_pass(
            src=fake_video,
            srt_path=fake_srt,
            st=st,
            log=logger,
            words_json_path=fake_words
        )
        tmp_files = list(Path(tempfile.gettempdir()).glob("wordpop_*fallback_vid*.ass"))
        self.assertTrue(len(tmp_files) > 0, "Fallback ASS file was not generated")

if __name__ == "__main__":
    unittest.main()
