#!/usr/bin/env python3
"""Caches for comparing bases on frames that share one in-camera recipe, using the JPEG embedded in each RAF.
Usage: film_caches.py <sample_photos> <embedded_dir> <raf-metadata.json> <out_prefix> <film> <color> <ht> <st>"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
import pairs as P

root, emb, meta, prefix, film, color, ht, st = Path(sys.argv[1]), Path(sys.argv[2]), json.load(open(sys.argv[3])), sys.argv[4], *sys.argv[5:9]
names = [Path(m['SourceFile']).stem for m in meta if m['FilmMode'] == int(film) and m['Saturation'] == int(color) and m['HighlightTone'] == int(ht) and m['ShadowTone'] == int(st)]
print(len(names), names)
rot = {Path(m['SourceFile']).stem: m.get('Orientation', 1) for m in meta}
def emb_load(n):
    im = Image.open(emb / f'{n}.jpg'); im.draft('RGB', (2200, 2200)); im = im.convert('RGB')
    if rot[n] in (6, 8):
        im = im.rotate({6: 270, 8: 90}[rot[n]], expand=True)
    size = (1080, 720) if im.width >= im.height else (720, 1080)
    return np.asarray(im.resize(size, Image.Resampling.BOX), dtype=np.float32) / 255
c = {'base-vs-lr': {}, 'std-vs-lr': {}, 'std-to-base': {}}
for n in names:
    std = P.load(next((root / 'pro-neg-std').glob(n + '.*'))); lr = P.load(next((root / 'pro400h').glob(n + '.*'))); e = emb_load(n)
    assert std.shape == lr.shape == e.shape, n
    a, b, s, _ = P.shift(std, e); assert tuple(s) == (0, 0), (n, s)
    c['std-to-base'][n + '_a'] = a; c['std-to-base'][n + '_b'] = b
    a, b, s, _ = P.shift(e, lr); c['base-vs-lr'][n + '_a'] = a; c['base-vs-lr'][n + '_b'] = b
    a, b, s, _ = P.shift(std, lr); c['std-vs-lr'][n + '_a'] = a; c['std-vs-lr'][n + '_b'] = b
for k, v in c.items():
    np.savez(f'{prefix}{k}.npz', **v)
