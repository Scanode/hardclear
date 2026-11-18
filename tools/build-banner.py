#!/usr/bin/env python3
"""
Colour-pick an ASCII banner from its reference image and bake it into Hugo files.

Usage (from the repo root):
    python3 tools/build-banner.py NAME reference.png art.txt [--rows A-B] [--cols A-B]
                                  [--colours 20] [--accent "#ff6266"]

  NAME           banner id, e.g. hardclear-1 (letters, digits, dashes)
  reference.png  the coloured export of art.txt from your ASCII generator
  art.txt        the full plain-text art that the PNG was made from
  --rows/--cols  1-based inclusive crop, e.g. --rows 22-46 (default: everything)
  --colours      palette size (default 20)
  --accent       the theme accent the red palette is built around (default #ff6266)

For every character the script samples the brightest pixels in its cell, then groups the
samples into a palette. The grid is fitted to the image, so a full export or a crop both work.

Writes:
    assets/ascii/banners/NAME.txt             the cropped plain text
    layouts/partials/ascii-banners/NAME.html  the art as coloured <span>s (no JS needed)
    assets/css/ascii-banners/NAME.css         two palettes for this banner:
        data-palette="image"  colours picked from the reference
        data-palette="red"    same brightness per character, in the theme accent's hue

Needs: pillow, numpy
"""
import argparse
import html
import os
import re

import numpy as np
from PIL import Image

LETTERS = "abcdefghijklmnopqrstuvwxyz"


def luminance(rgb):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(float(v)) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def fit_axis(profile, n, first_index):
    """Fit one axis of the character grid from the ink profile along it.

    Monospace glyphs repeat at a fixed pitch, so the ink profile is periodic: its strongest
    period near (ink extent / characters) is the cell size, and its phase puts the cell
    centres on the glyph centres. `first_index` is the row/column of the first character
    with ink, which pins the grid to the right cell.
    """
    lit = np.nonzero(profile)[0]
    lo, hi = lit.min(), lit.max()
    x = np.arange(len(profile), dtype=float)
    guess = (hi - lo + 1) / n
    best = (0, guess, 0.0)
    for period in np.arange(guess * 0.92, guess * 1.08, guess * 0.0005):
        z = (profile * np.exp(2j * np.pi * x / period)).sum()
        if abs(z) > best[0]:
            best = (abs(z), period, np.angle(z))
    _, period, phase = best
    centre = (phase / (2 * np.pi)) * period % period       # a glyph centre, mod period
    start = centre - period / 2                            # a cell boundary, mod period
    k = np.floor((lo - start) / period)                    # cell index holding the first ink
    origin = start + (k - first_index) * period
    return period, origin


def span(spec, n):
    if not spec:
        return 0, n
    a, b = (int(x) for x in spec.split("-"))
    return a - 1, b


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name")
    ap.add_argument("png")
    ap.add_argument("txt")
    ap.add_argument("--rows")
    ap.add_argument("--cols")
    ap.add_argument("--colours", type=int, default=20)
    ap.add_argument("--accent", default="#ff6266")
    a = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9-]+", a.name):
        ap.error("NAME may only contain lowercase letters, digits and dashes")

    lines = open(a.txt, newline="").read().replace("\r\n", "\n").rstrip("\n").split("\n")
    cols, rows = max(len(l) for l in lines), len(lines)

    # --- fit the character grid to the image ---
    im = np.array(Image.open(a.png).convert("RGB")).astype(float)
    H, W = im.shape[:2]
    lit = im.sum(2) > 120
    first_col = min(len(l) - len(l.lstrip(" ")) for l in lines if l.strip())
    first_row = next(i for i, l in enumerate(lines) if l.strip())
    cw, x0 = fit_axis(lit.sum(0).astype(float), cols, first_col)
    ch, y0 = fit_axis(lit.sum(1).astype(float), rows, first_row)
    print(f"{a.name}: {cols}x{rows} chars, cell {cw:.2f}x{ch:.2f}px, origin ({x0:.1f},{y0:.1f})")

    # --- sample every character ---
    samples, where = [], []
    for r, line in enumerate(lines):
        for c, char in enumerate(line):
            if char == " ":
                continue
            cell = im[max(0, int(y0 + r * ch)):max(0, int(y0 + (r + 1) * ch)),
                      max(0, int(x0 + c * cw)):max(0, int(x0 + (c + 1) * cw))].reshape(-1, 3)
            lum = cell.sum(1) if len(cell) else np.zeros(1)
            if not len(cell) or lum.max() < 30:
                samples.append(np.array([20., 20., 24.]))
            else:
                samples.append(cell[lum >= np.percentile(lum, 85)].mean(0))
            where.append((r, c))

    # --- crop ---
    r0, r1 = span(a.rows, rows)
    c0, c1 = span(a.cols, cols)
    keep = [i for i, (r, c) in enumerate(where) if r0 <= r < r1 and c0 <= c < c1]
    S = np.array([samples[i] for i in keep])
    where = [(where[i][0] - r0, where[i][1] - c0) for i in keep]
    lines = [l[c0:c1].rstrip() for l in lines[r0:r1]]
    rows = len(lines)

    # --- palette: seed with the most distinct colours so rare highlights survive ---
    k = min(a.colours, len(S))
    C = [S.mean(0)]
    for _ in range(k - 1):
        d = ((S[:, None] - np.array(C)[None]) ** 2).sum(2).min(1)
        C.append(S[d.argmax()])
    C = np.array(C)
    for _ in range(60):
        lab = ((S[:, None] - C[None]) ** 2).sum(2).argmin(1)
        C = np.array([S[lab == i].mean(0) if (lab == i).any() else C[i] for i in range(k)])
    order = np.argsort([luminance(c) for c in C])          # 'a' = darkest
    C, lab = C[order], np.argsort(order)[lab]
    err = np.sqrt(((S - C[lab]) ** 2).sum(1)).mean()
    grid = {}
    for (r, c), i in zip(where, lab):
        grid[(r, c)] = LETTERS[i]

    # --- outputs ---
    for d in ("assets/ascii/banners", "layouts/partials/ascii-banners", "assets/css/ascii-banners"):
        os.makedirs(d, exist_ok=True)
    with open(f"assets/ascii/banners/{a.name}.txt", "w") as f:
        f.write("\n".join(lines) + "\n")

    out = []
    for r, line in enumerate(lines):
        c = 0
        while c < len(line):
            key = grid.get((r, c)) if line[c] != " " else None
            end = c
            while end < len(line) and (grid.get((r, end)) if line[end] != " " else None) == key:
                end += 1
            chunk = html.escape(line[c:end], quote=False)
            out.append(f'<span class="ab-{key}">{chunk}</span>' if key else chunk)
            c = end
        if r < rows - 1:
            out.append("\n")
    with open(f"layouts/partials/ascii-banners/{a.name}.html", "w") as f:
        # no whitespace trimming: the art can start with meaningful spaces
        f.write("{{/* generated by tools/build-banner.py; do not edit */}}" + "".join(out))

    hexes = ["#%02x%02x%02x" % tuple(int(round(v)) for v in c) for c in C]
    acc = tuple(int(a.accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    acc_l = luminance(acc)
    sel = f'.ascii-banner[data-palette="%s"] [data-banner="{a.name}"] .ab-%s'
    width = max(len(l) for l in lines)
    em = round(width * 0.605, 2)    # Fira Code's advance is 0.6em; a hair extra covers fallback fonts
    css = ["/* generated by tools/build-banner.py; do not edit */",
           f"/* {a.name}: size so all {width} columns fit. Plain values only (no var()), so each line",
           "   either works or is skipped by the browser in favour of the line above it.",
           "   !important wins over any theme rule for <pre>; the JS sets an exact inline size. */",
           f'.ascii-banner pre[data-banner="{a.name}"] {{',
           f"  font-size: 8px !important;",
           f"  font-size: min(calc((100vw - 48px) / {em}), 16px) !important;",
           f"  font-size: min(calc(100cqi / {em}), 16px) !important;",
           "}",
           f"/* {a.name}: colours picked from the reference image */"]
    css += [f"{sel % ('image', LETTERS[i])} {{ color: {h} !important; }}" for i, h in enumerate(hexes)]
    css.append(f"/* {a.name}: same brightness per character, in the hue of --ab-hi (built for {a.accent}) */")
    for i, c in enumerate(C):
        l = luminance(c)
        if l <= acc_l:   # darker than the accent: accent mixed toward black
            v = f"color-mix(in srgb, var(--ab-hi) {max(8, round(100 * (l / acc_l) ** (1 / 2.2)))}%, #000)"
        else:            # brighter than the accent: accent mixed toward white
            v = f"color-mix(in srgb, var(--ab-hi), #fff {round(100 * ((l - acc_l) / (1 - acc_l)) ** (1 / 2.2))}%)"
        css.append(f"{sel % ('red', LETTERS[i])} {{ color: {v} !important; }}")
    with open(f"assets/css/ascii-banners/{a.name}.css", "w") as f:
        f.write("\n".join(css) + "\n")

    print(f"  cropped to {max(len(l) for l in lines)}x{rows}, {len(S)} characters, "
          f"palette of {k}, mean picking error {err:.1f}/441")
    print("  palette:", " ".join(hexes))


if __name__ == "__main__":
    main()
