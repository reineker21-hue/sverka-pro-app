from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ASSETS = Path("assets")
ASSETS.mkdir(exist_ok=True)

NAVY = (20, 36, 64, 255)
BLUE = (40, 95, 210, 255)
GREEN = (24, 160, 88, 255)
LIGHT = (248, 250, 253, 255)
WHITE = (255, 255, 255, 255)
MUTED = (108, 120, 140, 255)


def draw_logo(size=512, background=True):
    image = Image.new("RGBA", (size, size), LIGHT if background else (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    s = size

    if background:
        pad = int(s * 0.045)
        draw.rounded_rectangle(
            [pad, pad, s - pad, s - pad],
            radius=int(s * 0.16),
            fill=WHITE,
        )

    stroke = max(6, int(s * 0.035))

    # Two overlapping reconciliation acts/documents
    draw.rounded_rectangle(
        [int(s * 0.22), int(s * 0.21), int(s * 0.61), int(s * 0.70)],
        radius=int(s * 0.04),
        outline=BLUE,
        width=stroke,
    )
    draw.rounded_rectangle(
        [int(s * 0.38), int(s * 0.29), int(s * 0.77), int(s * 0.78)],
        radius=int(s * 0.04),
        outline=NAVY,
        width=stroke,
    )

    for y, end_x in ((0.44, 0.64), (0.52, 0.68), (0.60, 0.62)):
        yy = int(s * y)
        draw.line(
            [(int(s * 0.45), yy), (int(s * end_x), yy)],
            fill=NAVY,
            width=stroke,
        )

    # Green match/check marker
    cx, cy = int(s * 0.69), int(s * 0.69)
    radius = int(s * 0.115)
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=GREEN,
    )
    draw.line(
        [
            (int(cx - radius * 0.45), cy),
            (int(cx - radius * 0.10), int(cy + radius * 0.36)),
            (int(cx + radius * 0.48), int(cy - radius * 0.35)),
        ],
        fill=WHITE,
        width=max(6, int(s * 0.035)),
        joint="curve",
    )
    return image


def font(size, bold=False):
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


icon = draw_logo(512, background=True)
icon.save(ASSETS / "icon.png", optimize=True)

# Minimal splash/start screen using the same reconciliation mark.
width, height = 1080, 1920
splash = Image.new("RGB", (width, height), LIGHT[:3])
draw = ImageDraw.Draw(splash)
logo = draw_logo(420, background=False)
splash.paste(logo, (width // 2 - 210, 520), logo)

lines = [
    ("Сравнение АС", font(62, bold=True), 1000, NAVY),
    ("from NB", font(30), 1082, GREEN),
    ("Сверка актов на Android", font(28), 1160, MUTED),
]
for text, text_font, y, color in lines:
    box = draw.textbbox((0, 0), text, font=text_font)
    x = (width - (box[2] - box[0])) / 2
    draw.text((x, y), text, font=text_font, fill=color)

splash.save(ASSETS / "presplash.png", optimize=True)
print("Generated assets/icon.png and assets/presplash.png")
