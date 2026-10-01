from pathlib import Path
from PIL import ImageFont

FONTS_DIR = Path("fonts")
title = "He finally gave up his name as 'Robby' outside the red Challenger, but wait until you see what the officers found inside his pockets!"
font_fp = str(FONTS_DIR / "Montserrat-Bold.ttf")
font = ImageFont.truetype(font_fp, 60)

# Preview geometry scaled to 1080p:
# 324 scale: fullContainerW = 308px.
# p-1 = 4px each side (8px).
# padH = round(18 * 0.35) = 6px each side (12px).
# span padH = 6px each side (12px).
# Net available text width in 324px: 308 - 8 - 12 - 12 = 276px.
# Scaled to 1080p: 276 * (1080 / 324) = 920.0px.
max_text_w = 916.0

words = title.split(' ')
lines = []
cur = []
for w in words:
    test = ' '.join(cur + [w]) if cur else w
    tw = font.getlength(test)
    if tw <= max_text_w:
        cur.append(w)
    else:
        lines.append(' '.join(cur))
        cur = [w]
if cur:
    lines.append(' '.join(cur))

print("Lines wrapped with max_text_w=916.0:")
for i, l in enumerate(lines):
    print(f"Line {i+1}: '{l}' (width: {font.getlength(l):.1f})")
