#!/usr/bin/env python3
"""Data-driven Pro400H table: camera v5 JPEG colours -> Lightroom export colours.

For each sample frame: the camera's own render (JPEG embedded in the RAF, shot on
Bleach Bypass = v5 Pro400H) and the Lightroom export (Adobe Standard v2 + Pro400H look).
Both are reduced to the same small size (area average, which also hides sharpening/NR
differences), aligned, and compared in CIELAB (D65, sRGB). Then a 16x16x16 table
(sRGB-encoded in and out, trilinear, the camera's format) is fitted on some frames and
tested on the held-out frame.

Assumes the camera's table sees the camera's output colours (sRGB-encoded). Test 08
will show whether that holds; if not, the same pairs are refitted in the right domain.

Run with the scratch venv (numpy, pillow):
  python fit_lut_pairs.py <pairs_dir> <lightroom_exports_dir>
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

W, H = 1080, 720          # comparison size (3:2)
N = 16                    # camera table size


def load(path):
    im = Image.open(path).convert('RGB')
    im = im.resize((W, H), Image.Resampling.BOX)
    return np.asarray(im, dtype=np.float64) / 255.0


def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
WHITE = np.array([0.95047, 1.0, 1.08883])


def lab(c):
    xyz = srgb_to_lin(c) @ M.T / WHITE
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def align(a, b, r=12):
    """Integer shift of b that best matches a (luminance), searched in +-r pixels."""
    la, lb = a.mean(-1), b.mean(-1)
    best = (1e9, 0, 0)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            A = la[r:-r, r:-r]
            B = lb[r + dy:H - r + dy, r + dx:W - r + dx]
            e = np.mean((A - B) ** 2)
            if e < best[0]:
                best = (e, dy, dx)
    _, dy, dx = best
    return a[r:-r, r:-r], b[r + dy:H - r + dy, r + dx:W - r + dx], (dy, dx)


def de(a, b):
    return np.linalg.norm(lab(a) - lab(b), axis=-1)


def stats(d):
    d = d.ravel()
    return {'mean': round(float(d.mean()), 2), 'median': round(float(np.median(d)), 2),
            'p95': round(float(np.percentile(d, 95)), 2)}


def apply_lut(lut, c):
    """Trilinear lookup; lut[r, g, b] -> rgb, all 0..1."""
    x = np.clip(c, 0, 1) * (N - 1)
    i0 = np.minimum(np.floor(x).astype(int), N - 2)
    f = x - i0
    out = np.zeros_like(c)
    for dr in (0, 1):
        for dg in (0, 1):
            for db in (0, 1):
                w = ((f[..., 0] if dr else 1 - f[..., 0]) * (f[..., 1] if dg else 1 - f[..., 1])
                     * (f[..., 2] if db else 1 - f[..., 2]))
                out += w[..., None] * lut[i0[..., 0] + dr, i0[..., 1] + dg, i0[..., 2] + db]
    return out


def fit_lut(src, dst, smooth=0.3):
    """Least-squares 16^3 table under trilinear interpolation (scipy sparse lsqr), with a
    smoothness term (neighbouring nodes similar) and a weak pull towards identity so nodes
    with no data stay sensible."""
    from scipy.sparse import coo_matrix, vstack
    from scipy.sparse.linalg import lsqr
    n3 = N ** 3
    x = np.clip(src, 0, 1) * (N - 1)
    i0 = np.minimum(np.floor(x).astype(int), N - 2)
    f = x - i0
    rows, cols, vals = [], [], []
    m = len(src)
    r = np.arange(m)
    for dr in (0, 1):
        for dg in (0, 1):
            for db in (0, 1):
                w = ((f[:, 0] if dr else 1 - f[:, 0]) * (f[:, 1] if dg else 1 - f[:, 1]) * (f[:, 2] if db else 1 - f[:, 2]))
                rows.append(r); cols.append(np.ravel_multi_index((i0[:, 0] + dr, i0[:, 1] + dg, i0[:, 2] + db), (N, N, N))); vals.append(w)
    A = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(m, n3)).tocsr()
    # smoothness: differences between neighbouring nodes along each axis
    idx = np.arange(n3).reshape(N, N, N)
    srows, scols, svals, k = [], [], [], 0
    for ax in range(3):
        a0 = np.take(idx, range(N - 1), axis=ax).ravel(); a1 = np.take(idx, range(1, N), axis=ax).ravel()
        kk = np.arange(k, k + len(a0)); k += len(a0)
        srows += [kk, kk]; scols += [a0, a1]; svals += [np.full(len(a0), 1.0), np.full(len(a0), -1.0)]
    S = coo_matrix((np.concatenate(svals), (np.concatenate(srows), np.concatenate(scols))), shape=(k, n3)).tocsr()
    I = coo_matrix((np.full(n3, 0.02), (np.arange(n3), np.arange(n3))), shape=(n3, n3)).tocsr()
    scale = np.sqrt(m / n3)          # balance data and priors regardless of sample count
    big = vstack([A, S * smooth * scale, I * scale]).tocsr()
    grid = np.stack(np.meshgrid(*[np.linspace(0, 1, N)] * 3, indexing='ij'), -1).reshape(-1, 3)
    lut = np.zeros((n3, 3))
    for c in range(3):
        rhs = np.concatenate([dst[:, c], np.zeros(k), grid[:, c] * 0.02 * scale])
        lut[:, c] = lsqr(big, rhs, atol=1e-8, btol=1e-8, iter_lim=4000, x0=grid[:, c])[0]
    return np.clip(lut, 0, 1).reshape(N, N, N, 3)


def main(pairs, exports):
    pairs, exports = Path(pairs), Path(exports)
    frames = {}
    for cam in sorted(pairs.glob('*.camera.jpg')):
        name = cam.name.split('.')[0]
        lr = exports / f'{name}.jpg'
        a, b, shift = align(load(cam), load(lr))
        frames[name] = (a, b, shift)
    report = {'frames': {}, 'cross_validation': {}}
    for name, (a, b, shift) in frames.items():
        report['frames'][name] = {'shift_px_at_1080': shift, 'v5_vs_lightroom_dE76': stats(de(a, b))}
    names = list(frames)
    for held in names:
        train = [n for n in names if n != held]
        src = np.concatenate([frames[n][0].reshape(-1, 3) for n in train])
        dst = np.concatenate([frames[n][1].reshape(-1, 3) for n in train])
        lut = fit_lut(src, dst)
        a, b, _ = frames[held]
        report['cross_validation'][held] = {'trained_on': train,
                                            'v5': stats(de(a, b)),
                                            'v5_plus_fitted_table': stats(de(apply_lut(lut, a), b))}
    src = np.concatenate([f[0].reshape(-1, 3) for f in frames.values()])
    dst = np.concatenate([f[1].reshape(-1, 3) for f in frames.values()])
    lut = fit_lut(src, dst)
    np.save(Path(pairs).parent / 'lut16_from_pairs.npy', lut)
    report['all_frames_fit_in_sample'] = {n: stats(de(apply_lut(lut, f[0]), f[1])) for n, f in frames.items()}
    print(json.dumps(report, indent=1))
    (Path(pairs).parent / 'fit-report.json').write_text(json.dumps(report, indent=1) + '\n')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
