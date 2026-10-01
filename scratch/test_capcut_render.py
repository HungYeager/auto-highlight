import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONTS_DIR = Path("fonts")
REGULAR = {
    "montserrat": str(FONTS_DIR / "Montserrat-Bold.ttf"),
    "impact": "C:/Windows/Fonts/impact.ttf",
}

def render_title_test(title, font_name="montserrat", font_size=60, box_mode="capcut",
                      box_bg_color_hex="#0f24c2", box_opacity=100, box_radius=40,
                      stroke_width=2, stroke_color_hex="#000000", stroke_enabled=True,
                      text_color="white", text_align="center", title_wrap_pct=1.0,
                      line_height=1.35, text_x=0, text_y=329):
    width, height = 1080, 1920
    fp = REGULAR.get(font_name, REGULAR["montserrat"])
    font = ImageFont.truetype(fp, font_size)

    # ── Geometry matching Web Preview 100% ──
    margin_x = 26.67
    full_container_w = width - 2 * margin_x
    wrap_ratio = max(0.3, min(1.0, title_wrap_pct))
    box_w = full_container_w * wrap_ratio

    if box_mode in ("capcut", "badges"):
        text_pad_total = 26.67 + 1.4 * font_size
        pad_x = text_pad_total / 2.0
        pad_y = max(1.0, font_size * 0.16)
        max_text_w = max(50.0, box_w - text_pad_total)
    else:
        pad_x = 40.0
        pad_y = 26.67
        max_text_w = max(50.0, box_w - 2 * pad_x)

    # ── Word wrapping ──
    clean = title.replace("\r", "").strip()
    paragraphs = clean.split('\n')
    lines = []
    for para in paragraphs:
        words = para.split(' ')
        if not words or words == ['']:
            lines.append('')
            continue
        cur_line = []
        for word in words:
            test = ' '.join(cur_line + [word]) if cur_line else word
            try:
                tw = font.getlength(test)
            except Exception:
                tw = len(test) * (font_size * 0.55)
            if tw <= max_text_w:
                cur_line.append(word)
            else:
                if cur_line:
                    lines.append(' '.join(cur_line))
                    cur_line = [word]
                else:
                    lines.append(word)
                    cur_line = []
        if cur_line:
            lines.append(' '.join(cur_line))

    if not lines:
        lines = [clean]

    print("Wrapped Lines:")
    for idx, l in enumerate(lines, 1):
        print(f"  Line {idx}: {l}")

    # ── High-Resolution 2x Supersampling ──
    SCALE = 2
    w2, h2 = width * SCALE, height * SCALE
    font2 = ImageFont.truetype(fp, font_size * SCALE)

    margin_x2 = margin_x * SCALE
    full_container_w2 = w2 - 2 * margin_x2
    box_w2 = full_container_w2 * wrap_ratio
    pad_x2 = pad_x * SCALE
    pad_y2 = pad_y * SCALE
    max_text_w2 = max(100.0, box_w2 - 2 * pad_x2)

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

    _ch = box_bg_color_hex.lstrip("#")
    _rgb = (int(_ch[0:2], 16), int(_ch[2:4], 16), int(_ch[4:6], 16))
    _alpha = max(0, min(255, int(box_opacity * 2.55)))
    _fill = (*_rgb, _alpha)
    _radius2 = max(0, int((box_radius if box_radius > 0 else 40) * SCALE))

    if _alpha > 0 and box_mode == "capcut":
        cur_y_box2 = text_top2
        box_mask2 = Image.new("L", (w2, h2), 0)
        bm_draw2 = ImageDraw.Draw(box_mask2)

        for line in lines:
            if not line.strip():
                cur_y_box2 += total_lh2
                continue
            lw2 = font2.getlength(line)
            if text_align == "center":
                line_x2 = int(box_left2 + pad_x2 + (max_text_w2 - lw2) / 2)
            elif text_align == "right":
                line_x2 = int(box_right2 - pad_x2 - lw2)
            else:
                line_x2 = int(box_left2 + pad_x2)

            l_pad_x2 = int(font_size * SCALE * 0.35)
            l_pad_y2 = int(natural_lh2 * 0.16 + pil_spacing2 / 2 + 1)

            l_box_left = int(line_x2 - l_pad_x2)
            l_box_right = int(line_x2 + lw2 + l_pad_x2)
            l_box_top = int(cur_y_box2 - l_pad_y2)
            l_box_bottom = int(cur_y_box2 + natural_lh2 + l_pad_y2)
            l_rad2 = min(_radius2, int((l_box_bottom - l_box_top) * 0.30))

            if l_rad2 > 0:
                bm_draw2.rounded_rectangle([l_box_left, l_box_top, l_box_right, l_box_bottom], radius=l_rad2, fill=255)
            else:
                bm_draw2.rectangle([l_box_left, l_box_top, l_box_right, l_box_bottom], fill=255)

            cur_y_box2 += total_lh2

        box_solid2 = Image.new("RGBA", (w2, h2), (*_rgb, _alpha))
        layer2.paste(box_solid2, (0, 0), box_mask2)

    # Text mask
    text_mask2 = Image.new("L", (w2, h2), 0)
    tm_draw2 = ImageDraw.Draw(text_mask2)
    cur_y2 = text_top2
    for line in lines:
        lw2 = font2.getlength(line)
        if text_align == "center":
            line_x2 = int(box_left2 + pad_x2 + (max_text_w2 - lw2) / 2)
        elif text_align == "right":
            line_x2 = int(box_right2 - pad_x2 - lw2)
        else:
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

    # Text fill
    fg_color = (255, 255, 255)
    text_fill_layer2 = Image.new("RGBA", (w2, h2), (0, 0, 0, 0))
    text_fill_layer2.paste((*fg_color, 255), (0, 0), text_mask2)
    layer2 = Image.alpha_composite(layer2, text_fill_layer2)

    text_layer = layer2.resize((width, height), Image.Resampling.LANCZOS)
    return text_layer

if __name__ == "__main__":
    title = "He finally gave up his name as 'Robby' outside the red Challenger, but wait until you see what the officers found inside his pockets!"
    img = render_title_test(title)
    img.save("scratch/test_capcut_compare.png", "PNG")
    print("Generated scratch/test_capcut_compare.png successfully!")
