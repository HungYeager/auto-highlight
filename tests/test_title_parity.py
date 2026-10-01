import unittest
from pathlib import Path
from PIL import ImageFont
from app import _make_title_image, FONTS_DIR

class TestTitleParity(unittest.TestCase):
    def test_title_fallback_wrapping_exact_5_lines(self):
        """Verify that the user's title wraps into the exact 5 lines seen in Preview."""
        title = "She hugged her crying friend goodbye during the chaotic nighttime encounter, but wait until you see where she gets escorted next!"
        
        # Test PIL font metric with Montserrat-Bold (or fallback)
        fp = FONTS_DIR / "Montserrat-Bold.ttf"
        font = ImageFont.truetype(str(fp), 60)
        
        box_w = 1080 - 2 * 26.67
        l_pad_x = max(6.0, 60 * 0.35)
        pad_x = 20.0 + l_pad_x
        max_text_w = box_w - 2 * pad_x
        
        words = title.split(' ')
        lines = []
        cur = []
        for w in words:
            test = (' '.join(cur + [w])) if cur else w
            if font.getlength(test) <= max_text_w:
                cur.append(w)
            else:
                if cur: lines.append(' '.join(cur))
                cur = [w]
        if cur: lines.append(' '.join(cur))
        
        expected_lines = [
            "She hugged her crying friend",
            "goodbye during the chaotic",
            "nighttime encounter, but",
            "wait until you see where she",
            "gets escorted next!"
        ]
        self.assertEqual(lines, expected_lines)

    def test_make_title_image_with_title_lines(self):
        """Verify _make_title_image accepts title_lines and generates output PNG."""
        custom_lines = [
            "She hugged her crying friend",
            "goodbye during the chaotic",
            "nighttime encounter, but",
            "wait until you see where she",
            "gets escorted next!"
        ]
        img_path = _make_title_image(
            title="She hugged her crying friend...",
            font_name="montserrat",
            font_size=60,
            box_mode="capcut",
            box_bg_color_hex="#001eb3",
            box_opacity=100,
            text_color_hex="#ffffff",
            title_lines=custom_lines,
        )
        self.assertIsNotNone(img_path)
        self.assertTrue(Path(img_path).exists())
        if Path(img_path).exists():
            Path(img_path).unlink(missing_ok=True)

if __name__ == '__main__':
    unittest.main()
