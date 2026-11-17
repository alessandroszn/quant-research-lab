"""Draw the app's icon (design note 12.4).

Usage, from the repository root: ``uv run python packaging/make_icon.py``

An original mark, drawn here so it can be checked and redrawn: a rounded square with three
bars and a rising line. It writes ``src/qrlab_app/resources/qrlab.png`` (256 px, the window's
icon) and ``packaging/qrlab.ico`` (16 to 256 px, the programs' and the installer's icon). A test
redraws both and compares the pixels with the committed files.

Pillow comes with Matplotlib, so drawing the icon needs no new dependency.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw

__all__ = ["ICO", "ICO_SIZES", "PNG", "draw", "main"]

ROOT = Path(__file__).resolve().parents[1]
PNG = ROOT / "src" / "qrlab_app" / "resources" / "qrlab.png"
ICO = ROOT / "packaging" / "qrlab.ico"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
_CANVAS = 1024  # drawn large, then scaled down for smooth edges
_BACKGROUND = (30, 79, 134, 255)
_BARS = (141, 182, 232, 255)
_LINE = (255, 255, 255, 255)


def draw(size: int) -> Image.Image:
    """Return the icon at ``size`` by ``size`` pixels (RGBA)."""
    image = Image.new("RGBA", (_CANVAS, _CANVAS), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    pen.rounded_rectangle((32, 32, 992, 992), radius=200, fill=_BACKGROUND)
    for left, top in ((232, 640), (452, 520), (672, 400)):
        pen.rounded_rectangle((left, top, left + 120, 832), radius=24, fill=_BARS)
    points = [(208, 600), (400, 470), (560, 520), (816, 232)]
    pen.line(points, fill=_LINE, width=56, joint="curve")
    for x, y in (points[0], points[-1]):
        pen.ellipse((x - 44, y - 44, x + 44, y + 44), fill=_LINE)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main(argv: Sequence[str] | None = None) -> int:
    """Write the PNG and the ICO; return 0, or 2 when called with arguments."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print(__doc__)
        return 2
    PNG.parent.mkdir(parents=True, exist_ok=True)
    draw(256).save(PNG, format="PNG")
    draw(256).save(ICO, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    print(f"wrote {PNG.relative_to(ROOT)} and {ICO.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":  # pragma: no cover - the command line
    raise SystemExit(main())
