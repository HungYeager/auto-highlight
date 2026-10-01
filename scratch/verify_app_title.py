import app
from PIL import Image

title = "He finally gave up his name as 'Robby' outside the red Challenger, but wait until you see what the officers found inside his pockets!"
p = app._make_title_image(
    title,
    font_name="montserrat",
    font_size=60,
    text_color_hex="#ffffff",
    text_bg="box",
    box_mode="capcut",
    box_bg_color_hex="#0f24c2",
    box_opacity=100,
    box_radius=40,
    text_align="center",
    stroke_width=2,
    stroke_color_hex="#000000",
    stroke_enabled=True,
    title_wrap_pct=1.0,
    text_y=329
)
print("Rendered image path:", p)
if p and p.exists():
    im = Image.open(p)
    print("Image size:", im.size, "mode:", im.mode)
    crop = im.crop((50, 100, 1030, 600))
    crop.save("scratch/verify_cropped.png")
    print("Saved scratch/verify_cropped.png")
