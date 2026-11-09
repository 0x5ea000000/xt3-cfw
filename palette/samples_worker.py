#!/usr/bin/env python3
"""Write comparison JPEGs for one look: base render, base through the table, Lightroom target.
Usage: samples_worker.py <base_dir> <after_dir> <lut16.npy> <out_dir> <shared_base_out> <jobs>"""
import multiprocessing as mp, sys
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research' / 'claude-look-fit'))
import pairs as P
F = P.F


def save(c, path):
    Image.fromarray((np.clip(c, 0, 1) * 255 + .5).astype(np.uint8)).save(path, quality=88, optimize=True)


def thumb(path, out):
    im = Image.open(path); im.thumbnail((360, 360), Image.Resampling.BOX); im.save(out, quality=80)


def one(job):
    n, before, after, lut, out, shared = job
    a = P.load(before)
    if not (shared / f'{n}.jpg').exists():
        save(a, shared / f'{n}.jpg'); thumb(shared / f'{n}.jpg', shared / f'{n}.t.jpg')
    save(P.load(after), out / f'{n}.lightroom.jpg')
    t = F.apply_lut(np.load(lut), a.astype(np.float64))
    save(t, out / f'{n}.table.jpg'); thumb(out / f'{n}.table.jpg', out / f'{n}.t.jpg')
    return n


if __name__ == '__main__':
    base, after, lut, out, shared, jobs = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), Path(sys.argv[5]), int(sys.argv[6])
    out.mkdir(parents=True, exist_ok=True); shared.mkdir(parents=True, exist_ok=True)
    work = []
    for p in sorted(base.glob('*')):
        hit = [q for q in after.glob(p.stem + '.*')]
        if hit:
            work.append((p.stem, p, hit[0], lut, out, shared))
    with mp.Pool(jobs) as pool:
        for i, n in enumerate(pool.imap_unordered(one, work), 1):
            print(f'{i}/{len(work)} {n}', flush=True)
