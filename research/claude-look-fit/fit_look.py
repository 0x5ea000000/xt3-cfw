#!/usr/bin/env python3
"""Fit a look as a 16^3 table from many pairs and score it on photos it did not see.

Same model as research/look-fit-model/fit_lut_pairs_v3.py: trilinear table, smoothness on the difference from a
global tone-curve + 3x3 model, white node anchored, pixels clipped in the "before" image left out. With 48 frames the
solve uses normal equations: each frame's A'A and A'b are kept, so leaving a frame out is a subtraction.

Scores are mean / median / p95 CIELAB dE76 at about 1050x700. "held-out" = the frame was not in the fit.
Usage: fit_look.py <pairs.npz> <out_dir> [--smooth S] [--prior P] [--tune] [--curve]
"""
import argparse, json, sys, time
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix, csc_matrix, diags, identity
from scipy.sparse.linalg import splu
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'look-fit-model'))
import fit_lut_pairs as F
import fit_lut_pairs_v3 as V

N, n3 = 16, 16 ** 3
CLIP = 250 / 255
GRID = np.stack(np.meshgrid(*[np.linspace(0, 1, N)] * 3, indexing='ij'), -1).reshape(-1, 3)
GRID32 = GRID.astype(np.float32)

def smooth_matrix():
    idx = np.arange(n3).reshape(N, N, N); r, c, v, k = [], [], [], 0
    for ax in range(3):
        a0 = np.take(idx, range(N - 1), axis=ax).ravel(); a1 = np.take(idx, range(1, N), axis=ax).ravel()
        kk = np.arange(k, k + len(a0)); k += len(a0)
        r += [kk, kk]; c += [a0, a1]; v += [np.ones(len(a0)), -np.ones(len(a0))]
    return coo_matrix((np.concatenate(v), (np.concatenate(r), np.concatenate(c))), shape=(k, n3)).tocsr()
S = smooth_matrix(); StS = (S.T @ S).tocsr()

def design(src):
    x = np.clip(src, 0, 1) * (N - 1); i0 = np.minimum(np.floor(x).astype(int), N - 2); f = x - i0
    r = np.arange(len(src)); rows, cols, vals = [], [], []
    for dr in (0, 1):
        for dg in (0, 1):
            for db in (0, 1):
                w = ((f[:, 0] if dr else 1 - f[:, 0]) * (f[:, 1] if dg else 1 - f[:, 1]) * (f[:, 2] if db else 1 - f[:, 2]))
                rows.append(r); cols.append((i0[:, 0] + dr) * 256 + (i0[:, 1] + dg) * 16 + i0[:, 2] + db); vals.append(w)
    return coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(len(src), n3)).tocsr()

class Frame:
    def __init__(s, name, a, b):
        s.name, s.a, s.b = name, a, b
        H, W = a.shape[:2]; h, w = H // 2 * 2, W // 2 * 2
        def half(c): return c[:h, :w].reshape(h // 2, 2, w // 2, 2, c.shape[-1]).mean((1, 3))
        ok = half((a[:h, :w].max(-1) < CLIP).astype(np.float32)[..., None])[..., 0] > 0.999
        s.src = half(a)[ok].astype(np.float64); s.dst = half(b)[ok].astype(np.float64)
        A = design(s.src); s.AtA = (A.T @ A).tocsr(); s.Atb = A.T @ s.dst; s.m = len(s.src)
        pick = np.linspace(0, s.m - 1, min(s.m, 8000)).astype(int); s.gs, s.gd = s.src[pick], s.dst[pick]

def solve(frames, smooth, prior_w):
    src = np.concatenate([f.gs for f in frames]); dst = np.concatenate([f.gd for f in frames])
    model = V.fit_global(src, dst); prior = V.apply_global(model, GRID)
    m = sum(f.m for f in frames); scale2 = m / n3
    AtA = sum((f.AtA for f in frames[1:]), frames[0].AtA.copy()); Atb = sum(f.Atb for f in frames)
    w2 = (50 ** 2) * scale2
    W = coo_matrix(([1.0], ([n3 - 1], [n3 - 1])), shape=(n3, n3))
    K = AtA + StS * (smooth ** 2 * scale2) + identity(n3) * (prior_w ** 2 * scale2) + W * w2
    lu = splu(csc_matrix(K))
    rhs = Atb + (StS @ prior) * (smooth ** 2 * scale2) + prior * (prior_w ** 2 * scale2)
    rhs[n3 - 1] += V.WHITE * w2
    lut = np.stack([lu.solve(rhs[:, c]) for c in range(3)], -1)
    return np.clip(lut, 0, 1).reshape(N, N, N, 3), model

def score(lut, f):
    a, b = f.a, f.b; ok = a.max(-1) < CLIP
    out = F.apply_lut(lut.astype(np.float32), a[ok]); return out, b[ok]

def de_stats(p, t):
    d = F.de(p.astype(np.float64), t.astype(np.float64)); return F.stats(d)

def no_L(p, t):
    """dE after taking out the frame's mean lightness error: what is left besides exposure."""
    lp, lt = F.lab(p.astype(np.float64)), F.lab(t.astype(np.float64)); off = float((lt - lp)[:, 0].mean())
    lp[:, 0] += off; return float(np.linalg.norm(lp - lt, axis=-1).mean()), round(off, 2)

def fold(frames, i, smooth, prior):
    tr = frames[:i] + frames[i + 1:]; lut, model = solve(tr, smooth, prior); f = frames[i]
    p, t = score(lut, f); g = V.apply_global(model, f.a[f.a.max(-1) < CLIP].astype(np.float64))
    e, off = no_L(p, t)
    return {'before': de_stats(f.a[f.a.max(-1) < CLIP], t), 'global_only': de_stats(g, t), 'table': de_stats(p, t), 'table_without_mean_L': round(e, 2), 'mean_L_error': off}

def means(rows, key):
    return {s: round(float(np.mean([r[key][s] for r in rows])), 2) for s in ('mean', 'median', 'p95')}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('cache'); ap.add_argument('out')
    ap.add_argument('--smooth', type=float, default=0.3); ap.add_argument('--prior', type=float, default=0.05)
    ap.add_argument('--tune', action='store_true'); ap.add_argument('--curve', action='store_true'); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); z = np.load(a.cache)
    names = sorted({k[:-2] for k in z.files}); t0 = time.time()
    frames = [Frame(n, z[n + '_a'], z[n + '_b']) for n in names]; print('loaded', len(frames), round(time.time() - t0), 's', flush=True)
    rep = {'frames': names, 'settings': {'smooth': a.smooth, 'prior': a.prior}}
    if a.tune:
        test = list(range(0, len(frames), 4)); rep['tuning'] = []
        for sm in (0.1, 0.3, 1.0):
            for pr in (0.02, 0.05, 0.15):
                r = [fold(frames, i, sm, pr) for i in test]
                rep['tuning'].append(dict(smooth=sm, prior=pr, table=means(r, 'table'))); print(rep['tuning'][-1], flush=True)
        best = min(rep['tuning'], key=lambda r: r['table']['mean']); a.smooth, a.prior = best['smooth'], best['prior']
        rep['settings'] = {'smooth': a.smooth, 'prior': a.prior, 'chosen_by': 'held-out mean over every 4th frame'}
    if a.curve:
        rng = np.random.default_rng(1); test = list(range(2, len(frames), 6)); rep['learning_curve'] = []
        for size in (4, 8, 16, 32, 40):
            vals = []
            for i in test:
                pool = [k for k in range(len(frames)) if k not in test]
                for _ in range(3):
                    pick = sorted(rng.choice(pool, size=size, replace=False).tolist())
                    lut, _m = solve([frames[k] for k in pick], a.smooth, a.prior); p, t = score(lut, frames[i]); vals.append(de_stats(p, t)['mean'])
            rep['learning_curve'].append(dict(train_frames=size, test_frames=len(test), held_out_mean=round(float(np.mean(vals)), 2))); print(rep['learning_curve'][-1], flush=True)
    rep['held_out'] = {}
    for i, n in enumerate(names):
        rep['held_out'][n] = fold(frames, i, a.smooth, a.prior); print(n, rep['held_out'][n], flush=True)
    r = list(rep['held_out'].values())
    rep['held_out_mean'] = {'before': means(r, 'before'), 'global_only': means(r, 'global_only'), 'table': means(r, 'table'), 'table_without_mean_L': round(float(np.mean([x['table_without_mean_L'] for x in r])), 2)}
    lut, model = solve(frames, a.smooth, a.prior)
    rep['in_sample'] = {}
    for f in frames:
        p, t = score(lut, f); rep['in_sample'][f.name] = de_stats(p, t)
    rep['in_sample_mean'] = means(list(rep['in_sample'].values()), 'mean') if False else {s: round(float(np.mean([x[s] for x in rep['in_sample'].values()])), 2) for s in ('mean', 'median', 'p95')}
    rep['global_model'] = {'tone_knots': [round(float(v), 4) for v in model[0]], 'matrix': np.round(model[1], 4).tolist()}
    rep['sanity'] = V.sanity(lut)
    np.save(out / 'lut16.npy', lut); (out / 'lut16.bin').write_bytes(np.round(lut * 255).astype(np.uint8).tobytes())
    (out / 'fit-report.json').write_text(json.dumps(rep, indent=1) + '\n')
    print(json.dumps({k: rep[k] for k in ('settings', 'held_out_mean', 'in_sample_mean', 'sanity')}, indent=1)); print('total', round(time.time() - t0), 's')

if __name__ == '__main__':
    main()
