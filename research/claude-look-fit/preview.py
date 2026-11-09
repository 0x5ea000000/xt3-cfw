#!/usr/bin/env python3
"""Side-by-sides: "before" render, the same render through the fitted table, Lightroom export. Writes a JPEG sheet.
Usage: preview.py <before_dir> <after_dir> <lut16.npy> <out.jpg> <frame> [frame...]"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
import pairs as P
F = P.F
before, after, lut, out = Path(sys.argv[1]), Path(sys.argv[2]), np.load(sys.argv[3]), sys.argv[4]
names = sys.argv[5:]; H = 300; rows = []
for n in names:
    a = P.load(next(before.glob(f'DSCF{n}.*'))); b = P.load(next(after.glob(f'DSCF{n}.*')))
    t = F.apply_lut(lut, a.astype(np.float64)); d = F.stats(F.de(t, b.astype(np.float64)))['mean']
    tiles = []
    for c in (a, t, b):
        im = Image.fromarray((np.clip(c, 0, 1) * 255 + .5).astype(np.uint8)); im = im.resize((round(im.width * H / im.height), H), Image.Resampling.LANCZOS); tiles.append(im)
    rows.append((n, d, tiles))
W = max(sum(i.width + 8 for i in r[2]) for r in rows) + 8
sheet = Image.new('RGB', (W, (H + 26) * len(rows) + 26), (28, 28, 28)); dr = ImageDraw.Draw(sheet); y = 6
for lbl, x in (('PRO Neg. Std', 8), ('+ table (camera prediction)', W // 3 + 4), ('Lightroom target', 2 * W // 3)):
    dr.text((x, y), lbl, fill=(255, 220, 120))
y = 24
for n, d, tiles in rows:
    dr.text((8, y), f'DSCF{n}  table vs Lightroom: {d:.1f} dE', fill=(235, 235, 235)); y += 16; x = 8
    for t in tiles:
        sheet.paste(t, (x, y)); x += t.width + 8
    y += H + 10
sheet.save(out, quality=88); print(sheet.size)
