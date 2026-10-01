from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONTS_DIR = Path("fonts")
title = "He finally gave up his name as 'Robby' outside the red Challenger, but wait until you see what the officers found inside his pockets!"
font_fp = str(FONTS_DIR / "Montserrat-Bold.ttf")

SCALE = 2
font_size = 60
font = ImageFont.truetype(font_fp, font_size)
font2 = ImageFont.truetype(font_fp, font_size * SCALE)

width = 1080
height = 1920
w2 = width * SCALE
h2 = height * SCALE

text_x = 9
text_y = 329
box_mode = "capcut"
box_bg_color_hex = "#0f24c2"
box_opacity = 100
box_radius = 40
stroke_width = 2
stroke_color_hex = "#000000"
stroke_enabled = True
text_color_hex = "#ffffff"
line_height = 1.35
title_wrap_pct = 1.0

# Exact preview geometry:
# In 324 scale:
# fullContainerW = 324 - 16 = 308px.
# boxW = 308 * wrapPct = 308px.
# In 1080 scale (scale factor 1080/324 = 3.33333):
# box_w = 308 * (1080 / 324) = 1026.67px.
# Available width inside container for text:
# In preview: p-1 = 4px (8px both sides) + padH = 6px (12px both sides) + span padH = 6px (12px both sides)
# Total pad in 324 scale = 32px. In 1080 scale = 32 * 3.33333 = 106.67px (53.33px each side).
# max_text_w = 1026.67 - 106.67 = 920.0px.
wrap_ratio = max(0.3, min(1.0, title_wrap_pct))
box_w = (324 - 16) * (1080 / 324) * wrap_ratio # 1026.67
pad_x = 53.33
max_text_w = max(50.0, box_w - 2 * pad_x) # 920.0

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

box_w2 = box_w * SCALE
pad_x2 = pad_x * SCALE
pad_y2 = 26.67 * SCALE

try:
    ascent2, descent2 = font2.getmetrics()
except Exception:
    ascent2, descent2 = int(font_size * SCALE * 0.8), int(font_size * SCALE * 0.2)
natural_lh2 = ascent2 + descent2
pil_spacing2 = max(0, int(natural_lh2 * (line_height - 1.0)))
total_lh2 = natural_lh2 + pil_spacing2

text_block_h2 = len(lines) * natural_lh2 + max(0, len(lines) - 1) * pil_spacing2
box_h2 = int(text_block_h2 + 2 * pad_y2)

box_top2 = int((text_y * SCALE) - (box_h2 / 2))
box_bottom2 = box_top2 + box_h2
box_left2 = int((w2 - box_w2) / 2 + (text_x * SCALE))
box_right2 = int(box_left2 + box_w2)
text_top2 = int(box_top2 + pad_y2)

layer2 = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
draw2 = ImageDraw.Draw(layer2)

# Colors
_ch = box_bg_color_hex.lstrip("#")
_rgb = (int(_ch[0:2], 16), int(_ch[2:4], 16), int(_ch[4:6], 16))
_alpha = max(0, min(255, int(box_opacity * 2.55)))
_fill = (*_rgb, _alpha)
_radius2 = max(0, int((box_radius if box_radius > 0 else 40) * SCALE))

# Background Box
if _alpha > 0:
    if box_mode == "capcut":
        cur_y_box2 = text_top2
        box_mask2 = Image.new("L", (w2, h2), 0)
        bm_draw2  = ImageDraw.Draw(box_mask2)

        # In CapCut continuous bubble:
        # Each line has padding l_pad_x2.
        # When lines 1..N-1 are wrapped at container width, their widths are aligned to the container!
        l_pad_x2 = int(font_size * SCALE * 0.35)
        l_pad_y2 = int(natural_lh2 * 0.16 + pil_spacing2 / 2 + 1)

        for line in lines:
            if not line.strip():
                cur_y_box2 += total_lh2
                continue
            lw2 = font2.getlength(line)
            line_x2 = int(box_left2 + pad_x2)

            l_box_left   = int(line_x2 - l_pad_x2)
            l_box_right  = int(line_x2 + lw2 + l_pad_x2)
            l_box_top    = int(cur_y_box2 - l_pad_y2)
            l_box_bottom = int(cur_y_box2 + natural_lh2 + l_pad_y2)
            l_rad2       = min(_radius2, int((l_box_bottom - l_box_top) / 4))

            if l_rad2 > 0:
                bm_draw2.rounded_rectangle([l_box_left, l_box_top, l_box_right, l_box_bottom], radius=l_rad2, fill=255)
            else:
                bm_draw2.rectangle([l_box_left, l_box_top, l_box_right, l_box_bottom], fill=255)

            cur_y_box2 += total_lh2

        box_solid2 = Image.new("RGBA", (w2, h2), (*_rgb, _alpha))
        layer2.paste(box_solid2, (0, 0), box_mask2)

# Text Mask & Drawing
text_mask2 = Image.new("L", (w2, h2), 0)
tm_draw2 = ImageDraw.Draw(text_mask2)

cur_y2 = text_top2
for line in lines:
    line_x2 = int(box_left2 + pad_x2)
    tm_draw2.text((line_x2, cur_y2), line, font=font2, fill=255)
    cur_y2 += total_lh2

# Stroke
_user_sw = int(stroke_width)
if stroke_enabled and _user_sw > 0:
    stroke_r = max(1, _user_sw * SCALE)
    dilated = text_mask2.filter(ImageFilter.MaxFilter(2 * stroke_r + 1))
    smooth_sigma = max(0.8, stroke_r * 0.4)
    stroke_mask2 = dilated.filter(ImageFilter.GaussianBlur(radius=smooth_sigma))
    from PIL import ImageChops as _IC
    stroke_mask2 = _IC.lighter(stroke_mask2, text_mask2)

    _sc = stroke_color_hex.lstrip("#")
    _stroke_rgb = (int(_sc[0:2], 16), int(_sc[2:4], 16), int(_sc[4:6], 16)) if len(_sc) == 6 else (0, 0, 0)
    stroke_layer2 = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
    stroke_layer2.paste((*_stroke_rgb, 255), (0, 0), stroke_mask2)
    layer2 = Image.alpha_composite(layer2, stroke_layer2)

# Fill
fg_color = (255, 255, 255)
text_fill_layer2 = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
text_fill_layer2.paste((*fg_color, 255), (0, 0), text_mask2)
layer2 = Image.alpha_composite(layer2, text_fill_layer2)

text_layer = layer2.resize((width, height), Image.Resampling.LANCZOS)
text_layer.save("scratch/exact_title_test.png", "PNG")
print("Saved scratch/exact_title_test.png successfully!")
