#!/usr/bin/env python3
"""Generate the fork's upright and italic designspaces from the Glyphs source.

Both styles change two feature defaults:

* Coding ligatures are on by default. The ligature lookups move from ss01 to
  calt, and ss01 now disables them: it runs first and replaces each trigger
  character with an identical .noliga glyph that the ligature rules ignore.
* The slashed zero is the default. The zero and zero.zero outlines swap, so
  the zero feature now selects the plain zero.

The italic is an oblique: the Glyphs source is converted to UFO masters,
because the Glyphs 3 file format cannot store sheared component transforms.
Outlines, anchors, and components are then sheared by --angle degrees around
half the x-height so glyphs stay centred in their cells. Advance widths are
unchanged. Box Drawing and Block Elements stay upright so they keep joining
across terminal cells.
"""

import argparse
import math
import shutil
from pathlib import Path

import glyphsLib
import ufoLib2
from fontTools.misc.transform import Identity, Transform
from glyphsLib.classes import GSFeaturePrefix

ROOT = Path(__file__).resolve().parent.parent

# Box Drawing (U+2500-257F) and Block Elements (U+2580-259F).
UPRIGHT_CODEPOINTS = range(0x2500, 0x25A0)

# Every glyph that starts or continues a coding ligature in the ss01 code.
LIGATURE_TRIGGERS = [
    "ampersand", "asciitilde", "bar", "colon", "equal", "exclam",
    "greater", "hyphen", "less", "numbersign", "period", "slash",
]
NOLIGA_SUFFIX = ".noliga"
DISABLE_LIGATURES_LOOKUP = "disable_coding_ligatures"

ZERO_SWAP = {"zero": "zero.zero", "zero.zero": "zero"}


def italic_style_name(name):
    if name == "Regular":
        return "Italic"
    return f"{name} Italic"


def feature(font, tag):
    return next(item for item in font.features if item.name == tag)


def replace_feature_code(font, tag, old, new):
    item = feature(font, tag)
    if old not in item.code:
        raise ValueError(f"{tag} feature no longer contains {old!r}")
    item.code = item.code.replace(old, new)


def invert_ligature_feature(font):
    """Move the ligatures to calt and make ss01 disable them."""
    calt = feature(font, "calt")
    ss01 = feature(font, "ss01")
    calt.code = calt.code + "\n" + ss01.code

    # Lookups run in definition order, and prefixes are defined before every
    # feature, so this lookup replaces the triggers before calt sees them.
    triggers = " ".join(LIGATURE_TRIGGERS)
    aliases = " ".join(name + NOLIGA_SUFFIX for name in LIGATURE_TRIGGERS)
    prefix = GSFeaturePrefix()
    prefix.name = "Disable coding ligatures"
    prefix.code = (
        f"lookup {DISABLE_LIGATURES_LOOKUP} {{\n"
        f"    sub [{triggers}] by [{aliases}];\n"
        f"}} {DISABLE_LIGATURES_LOOKUP};\n"
    )
    font.featurePrefixes.append(prefix)

    # frac and ordn also match trigger characters, and their lookups run
    # after the prefix, so they must accept the aliases too.
    replace_feature_code(font, "frac", "[fraction slash]", "[fraction slash slash.noliga]")
    replace_feature_code(font, "ordn", "sub N o period", "sub N o [period period.noliga]")

    ss01.code = f"lookup {DISABLE_LIGATURES_LOOKUP};\n"
    ss01.labels = [{"language": "dflt", "value": "Disable coding ligatures"}]


def add_noliga_glyphs(ufo):
    """Add .noliga glyphs to every master layer as components of the triggers."""
    for name in LIGATURE_TRIGGERS:
        alias = name + NOLIGA_SUFFIX
        for layer in ufo.layers:
            if name not in layer or layer.name.endswith("background"):
                continue
            glyph = layer.newGlyph(alias)
            glyph.width = layer[name].width
            pen = glyph.getPen()
            pen.addComponent(name, Identity)
        ufo.glyphOrder = ufo.glyphOrder + [alias]


def swap_zero(ufo):
    """Swap the plain and slashed zero, keeping each component's shape."""
    for layer in ufo.layers:
        if "zero" not in layer or "zero.zero" not in layer:
            continue
        plain, slashed = layer["zero"], layer["zero.zero"]
        plain_shape = (list(plain.contours), list(plain.components), plain.width)
        slashed_shape = (list(slashed.contours), list(slashed.components), slashed.width)
        for glyph, (contours, components, width) in ((plain, slashed_shape), (slashed, plain_shape)):
            glyph.clearContours()
            glyph.clearComponents()
            for contour in contours:
                glyph.appendContour(contour)
            for component in components:
                glyph.components.append(component)
            glyph.width = width
        # Component references follow the shapes, not the names.
        for glyph in layer:
            for component in glyph.components:
                component.baseGlyph = ZERO_SWAP.get(component.baseGlyph, component.baseGlyph)


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


def make_italic(font, angle):
    for master in font.masters:
        master.italicAngle = angle
        master.name = italic_style_name(master.name)
    for instance in font.instances:
        instance.name = italic_style_name(instance.name)
        instance.isItalic = True


def write_designspace(font, path, transform_ufo):
    # Match the options fontmake uses when it builds from a Glyphs source.
    designspace = glyphsLib.to_designspace(
        font,
        ufo_module=ufoLib2,
        write_skipexportglyphs=True,
        store_editor_state=False,
        minimal=True,
    )
    # Several designspace sources (brace layers) can share one UFO.
    processed = set()
    for source in designspace.sources:
        ufo = source.font
        if id(ufo) in processed:
            continue
        swap_zero(ufo)
        add_noliga_glyphs(ufo)
        transform_ufo(ufo)
        ufo.save(path.parent / source.filename, overwrite=True)
        processed.add(id(ufo))
    designspace.write(path)
    print(f"Wrote {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--angle", type=float, default=10.0, help="Italic slant angle in degrees.")
    parser.add_argument("--center-y", type=float, default=254.0, help="Shear origin height (half the x-height).")
    parser.add_argument("--source", default=str(ROOT / "sources/PaperMono.glyphspackage"))
    parser.add_argument("--output-dir", default=str(ROOT / "sources/generated"))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    upright = glyphsLib.GSFont(args.source)
    invert_ligature_feature(upright)
    write_designspace(upright, output_dir / "PaperMono.designspace", lambda ufo: None)

    italic = glyphsLib.GSFont(args.source)
    invert_ligature_feature(italic)
    make_italic(italic, args.angle)
    slope = math.tan(math.radians(args.angle))
    shear = Transform(1, 0, slope, 1, -args.center_y * slope, 0)
    unsheared = upright_glyph_names(italic)

    def glyph_transform(name):
        if name in unsheared:
            return Identity
        return shear

    def shear_ufo(ufo):
        for layer in ufo.layers:
            for glyph in layer:
                shear_glyph(glyph, glyph_transform(glyph.name), glyph_transform)
        ufo.info.italicAngle = -args.angle

    write_designspace(italic, output_dir / "PaperMono-Italic.designspace", shear_ufo)


if __name__ == "__main__":
    main()
