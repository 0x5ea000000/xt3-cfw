#!/usr/bin/env python3
"""Load look-fit pairs: X RAW Studio "before" JPEG and Lightroom "after" JPEG of one RAF.

Both are upright (EXIF honoured), area-averaged to 1080x720 (or 720x1080) and registered.
Usage is as a module; `python pairs.py <sample_photos> <after_dir> <before_dir> <cache.npz>` builds the cache
and prints per-frame offsets, which show white-balance or exposure mismatch between the two renders.
"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'look-fit-model'))
import fit_lut_pairs as F

def load(path):
    im = Image.open(path)
    im.draft('RGB', (2200, 2200))           # decode the JPEG at reduced size: much faster, still far above 1080 px
    im = ImageOps.exif_transpose(im).convert('RGB')
    size = (1080, 720) if im.width >= im.height else (720, 1080)
    return np.asarray(im.resize(size, Image.Resampling.BOX), dtype=np.float32) / 255.0

def shift(a, b, r=2):
    """Integer shift of b onto a, from phase-free SSD on a 1/1 grey image, +-r px."""
    la, lb = a.mean(-1), b.mean(-1); best = (1e9, 0, 0)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            A = la[r:-r, r:-r]; B = lb[r + dy:lb.shape[0] - r + dy, r + dx:lb.shape[1] - r + dx]
            A2 = A - A.mean(); B2 = B - B.mean()
            e = float(np.mean((A2 - B2) ** 2))
            if e < best[0]: best = (e, dy, dx)
    _, dy, dx = best
    return a[r:-r, r:-r], b[r + dy:lb.shape[0] - r + dy, r + dx:lb.shape[1] - r + dx], (dy, dx), best[0]

if __name__ == '__main__':
    root, after, before, cache = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    out = {}; rows = []
    for p in sorted(root.glob('*.RAF')):
        n = p.stem
        a0 = load(next(before.glob(n + '.*'))); b0 = load(next(after.glob(n + '.*')))
        if a0.shape != b0.shape: raise SystemExit(f'{n}: shapes {a0.shape} {b0.shape}')
        a, b, s, err = shift(a0, b0)
        out[n + '_a'] = a; out[n + '_b'] = b
        la, lb = F.lab(a.astype(float)), F.lab(b.astype(float))
        ok = a.max(-1) < 250 / 255
        d = (lb - la)[ok]
        rows.append(dict(n=n, shift=s, ssd=round(err * 1e4, 2), dL=round(float(d[:, 0].mean()), 1), da=round(float(d[:, 1].mean()), 1), db=round(float(d[:, 2].mean()), 1),
                         Lb=round(float(la[..., 0].mean()), 1), La=round(float(lb[..., 0].mean()), 1), clip=round(float((~ok).mean() * 100), 1)))
        print(rows[-1], flush=True)
    np.savez(cache, **out)
    Path(cache).with_suffix('.json').write_text(json.dumps(rows, indent=0))
