#!/usr/bin/env python3
"""v3 of fit_lut_pairs.py: nodes without data follow a well-behaved global model,
a shared monotone tone curve (per channel, 16 linear segments) followed by a 3x3
matrix, instead of v2's cubic polynomial (which extrapolated saturated colours to
white/magenta). Smoothness acts on the difference from that model. Also reports
how the table treats greys and saturated colours, so a bad extrapolation is caught
before it reaches the camera. Camera pixels at clipping (any channel >= 250) are left
out of the fit: Lightroom recovers detail there from the RAW, which a table on the
camera's output cannot; instead white is anchored to WHITE. Writes fit-report-v3.json and lut16_from_pairs_v3.npy
next to <pairs_dir>.

Usage: python fit_lut_pairs_v3.py <pairs_dir> <lightroom_exports_dir>"""
import json
import sys
from pathlib import Path

import numpy as np
import fit_lut_pairs as F

K = 16                     # tone-curve segments
CLIP = 250 / 255           # camera pixels with any channel at/above this are not fitted
WHITE = 0.98               # anchor for the white node


def hats(x):
    """Piecewise-linear basis on K+1 knots over 0..1: x (n,) -> (n, K+1)."""
    t = np.clip(x, 0, 1) * K
    i = np.minimum(np.floor(t).astype(int), K - 1); f = t - i
    H = np.zeros((len(x), K + 1)); r = np.arange(len(x))
    H[r, i] = 1 - f; H[r, i + 1] = f
    return H


def curve(knots, c):
    return np.stack([hats(c[:, k]) @ knots for k in range(3)], -1)


def fit_global(src, dst, iters=12):
    """dst ~ T(src) @ M.T with T monotone, T(0) = 0. Alternating least squares."""
    knots = np.linspace(0, 1, K + 1); M = np.eye(3)
    Hs = [hats(src[:, k]) for k in range(3)]
    for _ in range(iters):
        Tc = np.stack([H @ knots for H in Hs], -1)
        M = np.linalg.lstsq(Tc, dst, rcond=None)[0].T
        # dst_j = sum_k M[j,k] * H_k @ knots  -> linear in knots
        A = np.concatenate([sum(M[j, k] * Hs[k] for k in range(3)) for j in range(3)])
        knots = np.linalg.lstsq(A + 0, dst.T.ravel(), rcond=None)[0]
        knots[0] = 0; knots = np.maximum.accumulate(np.clip(knots, 0, None))
    Tc = np.stack([H @ knots for H in Hs], -1)
    M = np.linalg.lstsq(Tc, dst, rcond=None)[0].T
    return knots, M


def apply_global(model, c):
    knots, M = model
    flat = c.reshape(-1, 3)
    return np.clip(curve(knots, flat) @ M.T, 0, 1).reshape(c.shape)


def fit_lut(src, dst, smooth=0.3, prior_w=0.05):
    from scipy.sparse import coo_matrix, vstack
    from scipy.sparse.linalg import lsqr
    keep = src.max(-1) < CLIP
    src, dst = src[keep], dst[keep]
    N = F.N; n3 = N ** 3
    model = fit_global(src, dst)
    grid = np.stack(np.meshgrid(*[np.linspace(0, 1, N)] * 3, indexing='ij'), -1).reshape(-1, 3)
    prior = apply_global(model, grid)
    x = np.clip(src, 0, 1) * (N - 1)
    i0 = np.minimum(np.floor(x).astype(int), N - 2); f = x - i0
    m = len(src); r = np.arange(m); rows, cols, vals = [], [], []
    for dr in (0, 1):
        for dg in (0, 1):
            for db in (0, 1):
                w = ((f[:, 0] if dr else 1 - f[:, 0]) * (f[:, 1] if dg else 1 - f[:, 1]) * (f[:, 2] if db else 1 - f[:, 2]))
                rows.append(r); cols.append(np.ravel_multi_index((i0[:, 0] + dr, i0[:, 1] + dg, i0[:, 2] + db), (N, N, N))); vals.append(w)
    A = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(m, n3)).tocsr()
    idx = np.arange(n3).reshape(N, N, N); srows, scols, svals, k = [], [], [], 0
    for ax in range(3):
        a0 = np.take(idx, range(N - 1), axis=ax).ravel(); a1 = np.take(idx, range(1, N), axis=ax).ravel()
        kk = np.arange(k, k + len(a0)); k += len(a0)
        srows += [kk, kk]; scols += [a0, a1]; svals += [np.ones(len(a0)), -np.ones(len(a0))]
    S = coo_matrix((np.concatenate(svals), (np.concatenate(srows), np.concatenate(scols))), shape=(k, n3)).tocsr()
    I = coo_matrix((np.full(n3, prior_w), (np.arange(n3), np.arange(n3))), shape=(n3, n3)).tocsr()
    scale = np.sqrt(m / n3)
    W = coo_matrix(([1.0], ([0], [n3 - 1])), shape=(1, n3)).tocsr()     # white node anchor
    wa = 50 * scale
    big = vstack([A, S * smooth * scale, I * scale, W * wa]).tocsr()
    lut = np.zeros((n3, 3))
    for c in range(3):
        sp = S @ prior[:, c]
        rhs = np.concatenate([dst[:, c], sp * smooth * scale, prior[:, c] * prior_w * scale, [WHITE * wa]])
        lut[:, c] = lsqr(big, rhs, atol=1e-8, btol=1e-8, iter_lim=4000, x0=prior[:, c])[0]
    return np.clip(lut, 0, 1).reshape(N, N, N, 3), model


def sanity(lut):
    """How the table treats greys and saturated colours (things the photos may not cover)."""
    N = F.N
    g = np.stack(np.meshgrid(*[np.linspace(0, 1, N)] * 3, indexing='ij'), -1)
    grey_in = g[np.arange(N), np.arange(N), np.arange(N)]; grey = lut[np.arange(N), np.arange(N), np.arange(N)]
    lab_in, lab_out = F.lab(g.reshape(-1, 3)), F.lab(lut.reshape(-1, 3))
    c_in = np.hypot(lab_in[:, 1], lab_in[:, 2]); c_out = np.hypot(lab_out[:, 1], lab_out[:, 2])
    sat = c_in > 60
    dh = np.degrees(np.abs(np.angle(np.exp(1j * (np.arctan2(lab_out[:, 2], lab_out[:, 1]) - np.arctan2(lab_in[:, 2], lab_in[:, 1]))))))
    prim = {n: [int(round(v * 255)) for v in lut[c]] for n, c in
            (('red', (15, 0, 0)), ('green', (0, 15, 0)), ('blue', (0, 0, 15)), ('yellow', (15, 15, 0)),
             ('cyan', (0, 15, 15)), ('magenta', (15, 0, 15)), ('white', (15, 15, 15)), ('black', (0, 0, 0)))}
    return {'grey_L_monotone': bool(np.all(np.diff(F.lab(grey)[:, 0]) > 0)),
            'grey_max_chroma': round(float(np.hypot(*F.lab(grey)[:, 1:].T).max()), 2),
            'saturated_nodes': int(sat.sum()),
            'saturated_hue_shift_deg_mean_p95_max': [round(float(np.mean(dh[sat])), 1), round(float(np.percentile(dh[sat], 95)), 1), round(float(dh[sat].max()), 1)],
            'saturated_chroma_ratio_min_median': [round(float((c_out[sat] / c_in[sat]).min()), 2), round(float(np.median(c_out[sat] / c_in[sat])), 2)],
            'corners_rgb255': prim}


def main(pairs, exports):
    pairs, exports = Path(pairs), Path(exports)
    frames = {}
    for cam in sorted(pairs.glob('*.camera.jpg')):
        name = cam.name.split('.')[0]
        a, b, _ = F.align(F.load(cam), F.load(exports / f'{name}.jpg'))
        frames[name] = (a, b)
    rep = {'frames': sorted(frames), 'cross_validation': {}}
    names = list(frames)
    for held in names:
        tr = [n for n in names if n != held]
        src = np.concatenate([frames[n][0].reshape(-1, 3) for n in tr]); dst = np.concatenate([frames[n][1].reshape(-1, 3) for n in tr])
        lut, model = fit_lut(src, dst)
        a, b = frames[held]
        rep['cross_validation'][held] = {'v5': F.stats(F.de(a, b)), 'global_only': F.stats(F.de(apply_global(model, a), b)),
                                         'table_v3': F.stats(F.de(F.apply_lut(lut, a), b))}
    src = np.concatenate([f[0].reshape(-1, 3) for f in frames.values()]); dst = np.concatenate([f[1].reshape(-1, 3) for f in frames.values()])
    lut, model = fit_lut(src, dst)
    np.save(pairs.parent / 'lut16_from_pairs_v3.npy', lut)
    rep['in_sample_v3'] = {n: F.stats(F.de(F.apply_lut(lut, f[0]), f[1])) for n, f in frames.items()}
    rep['global_model'] = {'tone_knots': [round(float(v), 4) for v in model[0]], 'matrix': np.round(model[1], 4).tolist()}
    rep['sanity'] = sanity(lut)
    (pairs.parent / 'fit-report-v3.json').write_text(json.dumps(rep, indent=1) + '\n')
    print(json.dumps(rep, indent=1))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
