from pathlib import Path

from PIL import Image, ImageDraw

scale = 4
size = 256
canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
draw = ImageDraw.Draw(canvas)

def s(value):
    return int(round(value * scale))

draw.rounded_rectangle((s(4), s(4), s(252), s(252)), radius=s(52), fill=(10, 13, 15, 255), outline=(41, 47, 51, 255), width=s(2))
line_color = (232, 237, 239, 255)
node_color = (255, 104, 0, 255)
width = s(12)
draw.line((s(80), s(126), s(176), s(66)), fill=line_color, width=width)
draw.line((s(80), s(130), s(176), s(190)), fill=line_color, width=width)
draw.ellipse((s(40), s(94), s(116), s(170)), fill=node_color)
draw.ellipse((s(150), s(42), s(204), s(96)), fill=node_color)
draw.ellipse((s(150), s(160), s(204), s(214)), fill=node_color)

canvas = canvas.resize((size, size), Image.Resampling.LANCZOS)
root = Path(__file__).resolve().parent.parent
root.joinpath("assets").mkdir(exist_ok=True)
canvas.save(root / "assets" / "icon.png")
canvas.save(root / "assets" / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
