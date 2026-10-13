"""Regenerate jevsorter.ico (run from the project root: py packaging/make_icon.py)."""
from PIL import Image, ImageDraw

S = 512
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((16, 16, S - 16, S - 16), radius=110, fill=(0, 95, 115, 255))
# three sorted file rows, staggered like a stack being filed
for i, (x, w) in enumerate(((96, 250), (136, 280), (96, 210))):
    y = 118 + i * 100
    d.rounded_rectangle((x, y, x + w, y + 64), radius=18, fill=(255, 255, 255, 255 - i * 35))
d.polygon([(380, 150), (440, 215), (380, 280)], fill=(238, 155, 0, 255))
img.save("jevsorter.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.resize((256, 256), Image.LANCZOS).save("jevsorter.png")   # Linux and macOS window icon
img.save("jevsorter.icns")                                     # macOS app bundle icon (Pillow writes icns)
