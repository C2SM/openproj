"""Build `static/openproj-meter.ttf`, the priority meter as one character per rung.

The graph draws a box's name as cytoscape canvas text, which is one string in one
colour, so the meter there cannot be the SVG every other page draws. It is a
glyph instead, at `chr(METER_FONT_BASE + level)` (`render/tokens.py`), in a face
that draws nothing else. Canvas text is one colour, so a lit bar is a solid bar
and an unlit one is a short stub on the baseline: a hairline outline round an
empty bar is under a pixel at the 12px a box's name is drawn at, and vanished.

Our own drawing, BSD-3-Clause like the rest of this repository. Built here
rather than taken from a Nerd Font: there is no official Nerd Font patch of Inter,
the signal glyphs those fonts carry stop at three or four levels where the
ladder has five, one weight of a patched face is 2 to 3 MB against about 1 KB
here, and the one place the face could otherwise have helped, a native macOS
select popup, ignores web fonts anyway.

Run from anywhere, with the dev group installed (fontTools is needed to rebuild
this file, not to run the app):

    uv run python tools/meter_font.py

It writes the font and prints its sha256, which goes into `static/SHA256SUMS`.
The output is byte-for-byte reproducible: the two timestamps in `head` are fixed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.misc.timeTools import timestampFromString
from fontTools.pens.ttGlyphPen import TTGlyphPen

from openproj.render.tokens import METER_FONT_BASE, PRIORITIES

OUT = Path(__file__).resolve().parent.parent / "static" / "openproj-meter.ttf"
FAMILY = "openproj meter"

# Font units, 1000 to the em. Five bars and four gaps fill 990 units, inside a
# 1070 advance, so the glyph sits a little narrower than an em with air either
# side and reads as one mark rather than as five letters.
UPM = 1000
BAR, GAP, LEFT, ADVANCE = 150, 60, 40, 1070
# Rising from about a third of Inter's cap height to all of it, so the full meter
# is as tall as the capitals it sits beside on a box's name.
HEIGHTS = tuple(220 + 125 * i for i in range(len(PRIORITIES)))
STUB = 90
# Fixed, so a rebuild writes the same bytes and the checksum only moves when the
# drawing does.
STAMP = timestampFromString("Tue Nov 24 00:00:00 2026")


def _rect(pen: TTGlyphPen, x: int, height: int) -> None:
    # Clockwise, which is TrueType's winding for a filled contour.
    pen.moveTo((x, 0))
    pen.lineTo((x, height))
    pen.lineTo((x + BAR, height))
    pen.lineTo((x + BAR, 0))
    pen.closePath()


def _meter(level: int):
    pen = TTGlyphPen(None)
    for i, height in enumerate(HEIGHTS):
        _rect(pen, LEFT + i * (BAR + GAP), height if i < level else STUB)
    return pen.glyph()


def build(out: Path = OUT) -> bytes:
    levels = range(1, len(PRIORITIES) + 1)
    names = [".notdef", *(f"meter{level}" for level in levels)]
    builder = FontBuilder(UPM, isTTF=True)
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({METER_FONT_BASE + level: f"meter{level}" for level in levels})
    glyphs = {".notdef": TTGlyphPen(None).glyph()}
    glyphs |= {f"meter{level}": _meter(level) for level in levels}
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(
        {".notdef": (ADVANCE, 0)} | {f"meter{level}": (ADVANCE, LEFT) for level in levels}
    )
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(
        {
            "copyright": "Copyright the openproj authors",
            "familyName": FAMILY,
            "styleName": "Regular",
            "licenseDescription": "BSD-3-Clause, the licence of the openproj repository",
        }
    )
    builder.setupOS2(
        sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200
    )
    builder.setupPost()
    builder.setupHead(unitsPerEm=UPM, created=STAMP, modified=STAMP)
    builder.save(out)
    return out.read_bytes()


if __name__ == "__main__":
    raw = build()
    print(f"{hashlib.sha256(raw).hexdigest()}  {OUT.name}  ({len(raw)} bytes)")
