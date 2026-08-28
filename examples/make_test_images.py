#!/usr/bin/env python
"""Generate synthetic CAPTCHA-style test images (distorted text + math).

Draws characters left-to-right (no overlap) with per-character jitter and
interference, mimicking the look of a distorted-text CAPTCHA well enough for
the OCR pipeline to recognize.
"""
from __future__ import annotations

import random
import string
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    from PIL import ImageFont
    for cand in ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                 "/System/Library/Fonts/Helvetica.ttc",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        if Path(cand).exists():
            return ImageFont.truetype(cand, size)
    return ImageFont.load_default()


def _draw_photo_captcha(text, out, seed, compact=False):
    rng = random.Random(seed)
    w, h = 480, 120
    img = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)
    fs = 64
    font = _font(fs)

    # Math expressions are rendered compactly (no wide gaps) so the thin '+'/'='
    # strokes stay detectable; text captchas use wider, separated glyphs.
    step = 50 if compact else (fs + rng.randint(2, 8))

    x = 90 if compact else 18
    y = 18
    for ch in text:
        dy = rng.randint(-5, 5)
        draw.text((x, y + dy), ch, font=font, fill=(25, 25, 25))
        x += step

    # Faint interference (like a real captcha's moiré) + light speckle.
    draw.line([(0, rng.randint(40, 90)), (w, rng.randint(40, 90))],
              fill=(165, 165, 165), width=2)
    for _ in range(100):
        draw.point((rng.randint(0, w - 1), rng.randint(0, h - 1)),
                   fill=(rng.randint(200, 255),) * 3)

    img.save(out)
    print(f"wrote {out} text={text!r}")


def make_text_captcha(text: str, out: str, seed: int = 1) -> None:
    _draw_photo_captcha(text, out, seed)


def make_math_captcha(a: int, op: str, b: int, out: str, seed: int = 2) -> None:
    _draw_photo_captcha(f"{a}{op}{b}=?", out, seed, compact=True)


if __name__ == "__main__":
    outdir = Path("examples")
    outdir.mkdir(exist_ok=True)
    make_text_captcha("K7pM2Q", str(outdir / "sample_captcha.png"), seed=1)
    make_math_captcha(3, "+", 5, str(outdir / "sample_math.png"), seed=2)
    make_math_captcha(12, "x", 4, str(outdir / "sample_math2.png"), seed=3)
    letters = "".join(random.Random(5).choices(string.ascii_uppercase + string.digits, k=5))
    make_text_captcha(letters, str(outdir / "sample_captcha2.png"), seed=5)
