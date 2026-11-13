"""Draw the program icons (run from the repository root).

    python packaging/make_icons.py

Writes work/editor .ico (Windows, 16-256 px) and .png (window icon) into
imposing/gui/assets/. The icons are drawn here, not taken from elsewhere.
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "imposing" / "gui" / "assets"
S = 1024  # drawing size; icons are scaled down from this
SIZES = [16, 24, 32, 48, 64, 128, 256]
INK = (28, 34, 44)
CMYK = [(0, 166, 232), (232, 0, 138), (255, 214, 0), INK]


def canvas(top, bottom):
    """Rounded square with a vertical gradient."""
    gradient = Image.new("RGB", (S, S))
    draw = ImageDraw.Draw(gradient)
    for y in range(S):
        t = y / (S - 1)
        draw.line(
            [(0, y), (S, y)],
            fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)),
        )
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([24, 24, S - 24, S - 24], 200, fill=255)
    image = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    image.paste(gradient, (0, 0), mask)
    return image


def sheet(image):
    """A white printing sheet with a soft shadow; returns its rectangle."""
    box = (232, 132, 792, 892)
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [box[0] + 14, box[1] + 22, box[2] + 14, box[3] + 22], 36, fill=(0, 0, 0, 70)
    )
    image.alpha_composite(shadow)
    ImageDraw.Draw(image).rounded_rectangle(box, 36, fill=(255, 255, 255, 255))
    return box


def cells(box, columns=2, rows=3, margin=64, gap=30):
    left, top, right, bottom = box
    width = (right - left - 2 * margin - (columns - 1) * gap) / columns
    height = (bottom - top - 2 * margin - (rows - 1) * gap) / rows
    for row in range(rows):
        for column in range(columns):
            x = left + margin + column * (width + gap)
            y = top + margin + row * (height + gap)
            yield row * columns + column, [x, y, x + width, y + height]


def work_icon():
    """Cards placed on the sheet: the work program."""
    image = canvas((36, 122, 214), (18, 70, 150))
    draw = ImageDraw.Draw(image)
    for index, rect in cells(sheet(image)):
        if index == 5:  # the next empty cell
            draw.rounded_rectangle(rect, 18, outline=(30, 155, 224), width=14)
            continue
        draw.rounded_rectangle(rect, 18, fill=CMYK[index % 4])
    return image


def editor_icon():
    """Empty cell outlines and a measuring corner: the template editor."""
    image = canvas((255, 156, 46), (224, 96, 12))
    draw = ImageDraw.Draw(image)
    box = sheet(image)
    for _, rect in cells(box):
        draw.rounded_rectangle(rect, 18, outline=(30, 155, 224), width=14)
    # Ruler along the top-left corner of the sheet (origin of the mm grid).
    x, y = box[0] - 84, box[1] - 84
    draw.rounded_rectangle([x, y, x + 520, y + 62], 14, fill=INK)
    draw.rounded_rectangle([x, y, x + 62, y + 520], 14, fill=INK)
    for step in range(1, 8):
        length = 34 if step % 2 == 0 else 22
        offset = 62 + step * 58
        draw.line([(x + offset, y + 62 - length), (x + offset, y + 62)], fill="white", width=10)
        draw.line([(x + 62 - length, y + offset), (x + 62, y + offset)], fill="white", width=10)
    return image


def save(image, name):
    OUT.mkdir(parents=True, exist_ok=True)
    image.resize((256, 256), Image.LANCZOS).save(OUT / f"{name}.png")
    image.save(OUT / f"{name}.ico", sizes=[(size, size) for size in SIZES])


if __name__ == "__main__":
    save(work_icon(), "work")
    save(editor_icon(), "editor")
    print(OUT)
