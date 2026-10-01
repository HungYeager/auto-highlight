from PIL import ImageFont

font_path = "fonts/impact.ttf"
font = ImageFont.truetype(font_path, 60)

text = "He finally gave up his name as 'Robby' outside the red Challenger, but wait until you see what the officers found inside his pockets!"
words = text.split(" ")

box_w = (1080 - 53.33) * 1.0

for name, max_w in [
    ("Old hardcoded pad_x=40", box_w - 80),
    ("Preview-matched pad", box_w - (26.67 + 1.4 * 60))
]:
    print(f"=== {name} (max_w={max_w:.2f}) ===")
    lines = []
    cur = []
    for w in words:
        test = " ".join(cur + [w]) if cur else w
        if font.getlength(test) <= max_w:
            cur.append(w)
        else:
            if cur:
                lines.append(" ".join(cur))
                cur = [w]
            else:
                lines.append(w)
                cur = []
    if cur:
        lines.append(" ".join(cur))
    for i, l in enumerate(lines, 1):
        print(f"  Line {i} ({font.getlength(l):.1f}px): {l}")
