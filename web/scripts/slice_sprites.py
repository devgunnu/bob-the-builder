"""Slice a Bob sprite sheet into aligned frames.

Usage:
  python3 scripts/slice_sprites.py SHEET.png name-1 name-2 name-3

Frames are found automatically (columns separated by transparent space),
cropped, scaled to fit a 640x640 transparent canvas and aligned to the same
bottom-centre baseline, so poses can be swapped without the character
jumping. Output goes to src/assets/bob/<name>.webp.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

SIZE = 640
PAD = 12
OUT = Path(__file__).resolve().parent.parent / "src" / "assets" / "bob"


def frame_columns(img: Image.Image, min_width: int = 6) -> list[tuple[int, int]]:
    a = np.array(img.convert("RGBA"))
    alpha = a[..., 3] > 20
    near_white = (a[..., 0] > 245) & (a[..., 1] > 245) & (a[..., 2] > 245)
    cols = (alpha & ~near_white).any(axis=0)
    runs, start = [], None
    for i, c in enumerate(cols):
        if c and start is None:
            start = i
        if not c and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(cols)))
    return [r for r in runs if r[1] - r[0] > min_width]


def main() -> None:
    sheet, names = Path(sys.argv[1]), sys.argv[2:]
    img = Image.open(sheet).convert("RGBA")
    runs = frame_columns(img)
    if len(runs) != len(names):
        sys.exit(f"Found {len(runs)} frames {runs} but got {len(names)} names")
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (x0, x1) in zip(names, runs):
        crop = img.crop((max(0, x0 - 8), 0, min(img.width, x1 + 8), img.height))
        crop = crop.crop(crop.getbbox())
        scale = min((SIZE - 2 * PAD) / crop.width, (SIZE - 2 * PAD) / crop.height)
        crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.LANCZOS)
        canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        canvas.paste(crop, ((SIZE - crop.width) // 2, SIZE - PAD - crop.height), crop)
        canvas.save(OUT / f"{name}.webp", "WEBP", quality=88, method=6)
        print(f"wrote {name}.webp")


if __name__ == "__main__":
    main()
