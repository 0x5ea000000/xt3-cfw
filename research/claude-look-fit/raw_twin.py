#!/usr/bin/env python3
"""Recreate a camera film from the RAF alone: demosaic, undo the frame's exposure bias, fit a 16^3 table to the camera's render.

Writes pairs in pairs.py's cache format with the RAF rendering as "before" and the given renders as "after".
Usage: raw_twin.py <sample_photos> <after_dir> <raf-metadata.json> <cache.npz> [--jobs N]
"""
import json, multiprocessing as mp, os, sys
os.environ.setdefault('OMP_NUM_THREADS', '1')
from pathlib import Path
import numpy as np
import rawpy
from PIL import Image
import pairs as P

HEAD = 4.0       # headroom in linear: 2 stops above the camera's white after the bias is undone

def raw_render(path, bias):
    with rawpy.imread(str(path)) as r:
        rgb = r.postprocess(use_camera_wb=True, no_auto_bright=True, gamma=(1, 1), output_bps=16, output_color=rawpy.ColorSpace.raw, bright=1.0)
    lin = rgb.astype(np.float32) / 65535 * 2.0 ** (-bias) / HEAD
    enc = np.clip(lin, 0, 1) ** (1 / 2.2)
    size = (1080, 720) if enc.shape[1] >= enc.shape[0] else (720, 1080)
    out = [np.asarray(Image.fromarray(enc[..., c]).resize(size, Image.Resampling.BOX), dtype=np.float32) for c in range(3)]
    return np.stack(out, -1)

def one(a):
    raf, after, bias = a
    x = raw_render(raf, bias); y = P.load(next(Path(after).glob(raf.stem + '.*')))
    if x.shape != y.shape:
        return raf.stem, None, None, None, None
    p, q, s, e = P.shift(x, y, r=6)
    return raf.stem, p, q, s, e

if __name__ == '__main__':
    root, after, meta, cache = Path(sys.argv[1]), sys.argv[2], json.load(open(sys.argv[3])), sys.argv[4]
    jobs = int(sys.argv[6]) if len(sys.argv) > 6 else 6
    bias = {Path(m['SourceFile']).stem: float(m['RawExposureBias']) for m in meta}
    work = [(p, after, bias[p.stem]) for p in sorted(root.glob('*.RAF'))]
    with mp.Pool(jobs) as pool:
        res = pool.map(one, work)
    out = {}
    for n, p, q, s, e in res:
        print(n, s, None if e is None else round(e * 1e4, 1), flush=True)
        if p is not None:
            out[n + '_a'] = p; out[n + '_b'] = q
    np.savez(cache, **out)
