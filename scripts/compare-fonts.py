#!/usr/bin/env python3
"""Pixel-compare the fork's fonts against the original upstream font.

The fork must look exactly like the original, apart from the intended
changes. Each case shapes the same text with HarfBuzz in both fonts,
rasterizes it with FreeType at several weights, and compares the images.

* Feature defaults are inverted, so the fork with no features must match the
  original with ss01 and zero, and the reverse.
* Other features (cv01, ss02, ss03, ss04, frac) must behave as before.
* The italic must match the original rendered with the same shear applied by
  FreeType, except Box Drawing and Block Elements, which stay upright.

Failing cases are written to the output directory as images that show the
original, the fork, and their difference.
"""

import argparse
import math
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import freetype
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
UPRIGHT = ROOT / "fonts/variable/PaperMono[wght].ttf"
ITALIC = ROOT / "fonts/variable/PaperMono-Italic[wght].ttf"
ORIGINAL_PATH = "fonts/variable/PaperMono[wght].ttf"

WEIGHTS = (100, 250, 400, 550, 700, 800)
PPEM = 48
PADDING = 24
# A pixel counts as different when its coverage differs by more than this
# (0-255). The italic stores sheared outlines rounded to whole font units, so
# antialiased edges can differ slightly from FreeType's exact shear.
PIXEL_TOLERANCE = 48
UPRIGHT_CODEPOINTS = range(0x2500, 0x25A0)

INVERTED = {"ss01", "zero"}
EXTRA_FEATURES = ["cv01", "ss02", "ss03", "ss04", "frac"]
PARAGRAPH = (
    "Paper Mono 0123456789 1/2 3/4 aáàâä mwæœ AÆMŒW ←↑→↓↔↕↖↗↘↙ "
    "ö́ û̃ Ắ ḝ "
    "if (a != b && c <= d) { return x => y; } // a == b !== c"
)


@dataclass
class Case:
    name: str
    text: str
    original_features: set
    fork_features: set


class Renderer:
    def __init__(self, data):
        self.face = freetype.Face(_bytes_stream(data))
        self.face.set_pixel_sizes(0, PPEM)
        self.hb_face = hb.Face(data)
        self.hb_font = hb.Font(self.hb_face)
        self.units_per_em = self.hb_face.upem
        ttfont = TTFont(_bytes_stream(data))
        self.glyph_order = ttfont.getGlyphOrder()
        cmap = ttfont.getBestCmap()
        self.codepoints = sorted(cmap)
        self.unsheared = {cmap[code] for code in cmap if code in UPRIGHT_CODEPOINTS}
        self.liga_strings = _ligature_strings(ttfont, cmap)

    def render(self, text, features, weight, slope=0.0, center_y=0.0):
        self.hb_font.set_variations({"wght": weight})
        self.face.set_var_design_coords((weight,))
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        hb.shape(self.hb_font, buffer, {tag: True for tag in features})

        scale = PPEM / self.units_per_em
        width = int(sum(p.x_advance for p in buffer.glyph_positions) * scale) + 2 * PADDING
        height = int(PPEM * 1.6) + 2 * PADDING
        image = Image.new("L", (max(width, 1), height), 0)
        baseline = PADDING + int(PPEM * 1.1)
        pen_x = 0
        for info, position in zip(buffer.glyph_infos, buffer.glyph_positions):
            name = self.glyph_order[info.codepoint]
            glyph_slope = 0.0 if name in self.unsheared else slope
            matrix = freetype.Matrix(0x10000, int(round(glyph_slope * 0x10000)), 0, 0x10000)
            delta = freetype.Vector(int(round(-center_y * glyph_slope * scale * 64)), 0)
            self.face.set_transform(matrix, delta)
            self.face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
            glyph = self.face.glyph
            bitmap = glyph.bitmap
            if bitmap.width and bitmap.rows:
                tile = Image.frombytes("L", (bitmap.width, bitmap.rows), bytes(bitmap.buffer), "raw", "L", bitmap.pitch)
                # The shear also moves marks that GPOS raises or lowers.
                x_offset = position.x_offset + glyph_slope * position.y_offset
                x = PADDING + int(round((pen_x + x_offset) * scale)) + glyph.bitmap_left
                y = baseline - int(round(position.y_offset * scale)) - glyph.bitmap_top
                layer = Image.new("L", image.size, 0)
                layer.paste(tile, (x, y))
                image = ImageChops.lighter(image, layer)
            pen_x += position.x_advance
        return image


def _bytes_stream(data):
    import io
    return io.BytesIO(data)


def _ligature_strings(ttfont, cmap):
    """Recover the character sequence of each ligature from its glyph name."""
    by_name = {name: chr(code) for code, name in cmap.items()}
    strings = []
    for name in ttfont.getGlyphOrder():
        if not name.endswith(".liga"):
            continue
        parts = name[: -len(".liga")].split("_")
        if all(part in by_name for part in parts):
            strings.append("".join(by_name[part] for part in parts))
    return strings


def compare(original, fork):
    width = max(original.width, fork.width)
    height = max(original.height, fork.height)
    a = Image.new("L", (width, height), 0)
    b = Image.new("L", (width, height), 0)
    a.paste(original, (0, 0))
    b.paste(fork, (0, 0))
    diff = ImageChops.difference(a, b)
    over = sum(diff.point(lambda value: 255 if value > PIXEL_TOLERANCE else 0).histogram()[255:])
    return over, diff.getextrema()[1], (a, b, diff)


def write_failure(path, label, images):
    a, b, diff = images
    sheet = Image.new("RGB", (a.width, a.height * 3 + 60), "white")
    draw = ImageDraw.Draw(sheet)
    for row, (title, image) in enumerate((("original", a), ("fork", b), ("difference", diff))):
        top = row * (a.height + 20) + 20
        draw.text((4, top - 16), title, fill="black")
        sheet.paste(Image.eval(image, lambda value: 255 - value).convert("RGB"), (0, top))
    draw.text((4, sheet.height - 14), label, fill="red")
    sheet.save(path)


def build_cases(original):
    # Each combining mark sits on its own base letter, as it would in text,
    # instead of stacking on the previous mark.
    characters = "".join(
        f" o{chr(code)} " if unicodedata.category(chr(code)) == "Mn" else chr(code)
        for code in original.codepoints
        if code >= 0x20
    )
    ligatures = "  ".join(original.liga_strings)
    cases = [
        Case("characters, defaults", characters, INVERTED, set()),
        Case("characters, ss01 zero", characters, set(), INVERTED),
        Case("ligatures, defaults", ligatures, INVERTED, set()),
        Case("ligatures, ss01 zero", ligatures, set(), INVERTED),
        Case("ligatures, ss01 only", ligatures, {"zero"}, {"ss01"}),
        Case("ligatures, zero only", ligatures, {"ss01"}, {"zero"}),
    ]
    for tag in EXTRA_FEATURES:
        cases.append(Case(f"paragraph, {tag}", PARAGRAPH, INVERTED | {tag}, {tag}))
        cases.append(Case(f"paragraph, {tag} ss01 zero", PARAGRAPH, {tag}, INVERTED | {tag}))
    return cases


def chunks(text, size):
    for start in range(0, len(text), size):
        yield start, text[start : start + size]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-ref", default="v1.000", help="Git ref of the original upstream font.")
    parser.add_argument("--angle", type=float, default=10.0, help="Italic angle used by make build.")
    parser.add_argument("--center-y", type=float, default=254.0, help="Shear origin used by make build.")
    parser.add_argument("--output-dir", default=str(ROOT / "out/compare"))
    args = parser.parse_args()

    original_data = subprocess.check_output(["git", "show", f"{args.original_ref}:{ORIGINAL_PATH}"], cwd=ROOT)
    original = Renderer(original_data)
    styles = [
        ("upright", Renderer(UPRIGHT.read_bytes()), 0.0),
        ("italic", Renderer(ITALIC.read_bytes()), math.tan(math.radians(args.angle))),
    ]

    output_dir = Path(args.output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)

    failures = 0
    checks = 0
    peaks = {}
    for style, fork, slope in styles:
        for case in build_cases(original):
            # Short chunks keep images small and point a failure at the
            # characters that caused it.
            for start, text in chunks(case.text, 40):
                for weight in WEIGHTS:
                    checks += 1
                    reference = original.render(text, case.original_features, weight, slope, args.center_y)
                    candidate = fork.render(text, case.fork_features, weight)
                    over, peak, images = compare(reference, candidate)
                    peaks[style] = max(peaks.get(style, 0), peak)
                    if over:
                        failures += 1
                        output_dir.mkdir(parents=True, exist_ok=True)
                        label = f"{style} | {case.name} | wght {weight} | {over} px over tolerance, peak {peak} | {text!r}"
                        slug = f"{style}-{case.name}-{start}-{weight}".replace(" ", "_").replace(",", "")
                        write_failure(output_dir / f"{slug}.png", label, images)
                        print(f"FAIL {label}")

    for style, peak in peaks.items():
        print(f"{style}: largest pixel difference {peak}/255")
    print(f"{checks - failures}/{checks} comparisons match (tolerance {PIXEL_TOLERANCE}/255, {PPEM} ppem).")
    if failures:
        print(f"Difference images: {output_dir}")
        sys.exit(1)


if __name__ == "__main__":
    main()
