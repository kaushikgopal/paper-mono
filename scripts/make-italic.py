#!/usr/bin/env python3
"""Generate an oblique (slanted) designspace from the upright Glyphs source.

The Glyphs source is converted to UFO masters first, because the Glyphs 3
file format cannot store sheared component transforms. Outlines, anchors, and
components in each master are then sheared by --angle degrees around half the
x-height so glyphs stay centered in their cells. Advance widths are unchanged.
Box Drawing and Block Elements stay upright so they keep joining across
terminal cells. Masters receive the italic angle and instances are renamed and
flagged as italic.
"""

import argparse
import math
import shutil
from pathlib import Path

import glyphsLib
import ufoLib2
from fontTools.misc.transform import Identity, Transform

ROOT = Path(__file__).resolve().parent.parent

# Box Drawing (U+2500-257F) and Block Elements (U+2580-259F).
UPRIGHT_CODEPOINTS = range(0x2500, 0x25A0)


def italic_style_name(name):
    if name == "Regular":
        return "Italic"
    return f"{name} Italic"


def upright_glyph_names(font):
    return {
        glyph.name
        for glyph in font.glyphs
        if any(int(code, 16) in UPRIGHT_CODEPOINTS for code in glyph.unicodes)
    }


def shear_glyph(glyph, shear, base_transform):
    for contour in glyph.contours:
        for point in contour.points:
            point.x, point.y = shear.transformPoint((point.x, point.y))
    for anchor in glyph.anchors:
        anchor.x, anchor.y = shear.transformPoint((anchor.x, anchor.y))
    for component in glyph.components:
        # The base glyph is already transformed by base_transform (B). For
        # the composite to equal this glyph's transform (S) applied to the
        # original composite, the new component matrix is S * M * B^-1.
        matrix = Transform(*component.transformation)
        base = base_transform(component.baseGlyph)
        component.transformation = tuple(shear.transform(matrix).transform(base.inverse()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--angle", type=float, default=10.0, help="Slant angle in degrees.")
    parser.add_argument("--center-y", type=float, default=254.0, help="Shear origin height (half the x-height).")
    parser.add_argument("--source", default=str(ROOT / "sources/PaperMono.glyphspackage"))
    parser.add_argument("--output-dir", default=str(ROOT / "sources/italic"))
    args = parser.parse_args()

    slope = math.tan(math.radians(args.angle))
    shear = Transform(1, 0, slope, 1, -args.center_y * slope, 0)

    font = glyphsLib.GSFont(args.source)
    upright = upright_glyph_names(font)

    def glyph_transform(name):
        return Identity if name in upright else shear

    for master in font.masters:
        master.italicAngle = args.angle
        master.name = italic_style_name(master.name)
    for instance in font.instances:
        instance.name = italic_style_name(instance.name)
        instance.isItalic = True

    # Match the options fontmake uses when it builds from a Glyphs source.
    designspace = glyphsLib.to_designspace(
        font,
        ufo_module=ufoLib2,
        write_skipexportglyphs=True,
        store_editor_state=False,
        minimal=True,
    )

    output_dir = Path(args.output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # Several designspace sources (brace layers) can share one UFO.
    processed = {}
    for source in designspace.sources:
        ufo = source.font
        if id(ufo) in processed:
            continue
        for layer in ufo.layers:
            for glyph in layer:
                shear_glyph(glyph, glyph_transform(glyph.name), glyph_transform)
        ufo.info.italicAngle = -args.angle
        ufo.save(output_dir / source.filename, overwrite=True)
        processed[id(ufo)] = source.filename

    designspace_path = output_dir / "PaperMono-Italic.designspace"
    designspace.write(designspace_path)
    print(f"Wrote {designspace_path} (angle {args.angle} degrees)")


if __name__ == "__main__":
    main()
