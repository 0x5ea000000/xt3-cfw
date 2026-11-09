#!/usr/bin/env python3
"""Routine look fit: same model and leave-one-out test as fit_look.py, in about a minute.

Differences, all for speed: one LU factorisation of the full problem preconditions conjugate gradients for each fold,
folds run in parallel, scoring uses the half-size masked samples, and the global model uses fewer samples per frame.
Usage: fit_fast.py <pairs.npz> <out_dir> [--smooth S] [--prior P] [--jobs N] [--write]
"""
import argparse, json, multiprocessing as mp, os, time
os.environ.setdefault('OMP_NUM_THREADS', '1'); os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix, csc_matrix, identity
from scipy.sparse.linalg import LinearOperator, cg, splu
import fit_look as L
from fit_look import F, V, GRID, StS, n3, N

class Lite(L.Frame):
    def __init__(s, name, a, b, picks):
        L.Frame.__init__(s, name, a, b)
        p = np.linspace(0, s.m - 1, min(s.m, picks)).astype(int); s.gs, s.gd = s.src[p], s.dst[p]
        s.a = s.b = None

def system(frames, sm, pr):
    src = np.concatenate([f.gs for f in frames]); dst = np.concatenate([f.gd for f in frames])
    model = V.fit_global(src, dst); prior = V.apply_global(model, GRID)
    m = sum(f.m for f in frames); k = m / n3; w2 = 2500 * k
    AtA = sum((f.AtA for f in frames[1:]), frames[0].AtA.copy())
    K = (AtA + StS * (sm ** 2 * k) + identity(n3) * (pr ** 2 * k) + coo_matrix(([1.0], ([n3 - 1], [n3 - 1])), shape=(n3, n3)) * w2).tocsr()
    rhs = sum(f.Atb for f in frames) + (StS @ prior) * (sm ** 2 * k) + prior * (pr ** 2 * k); rhs[n3 - 1] += V.WHITE * w2
    return K, rhs, model

def direct(frames, sm, pr):
    K, rhs, model = system(frames, sm, pr); lu = splu(csc_matrix(K))
    return np.stack([lu.solve(rhs[:, c]) for c in range(3)], -1), lu, model

G = {}
def one(i):
    fr, sm, pr, lu, x0 = G['frames'], G['sm'], G['pr'], G['lu'], G['x0']
    tr = fr[:i] + fr[i + 1:]; K, rhs, model = system(tr, sm, pr)
    M = LinearOperator((n3, n3), matvec=lu.solve); x = np.zeros_like(x0); iters = 0
    for c in range(3):
        n = [0]
        def cb(_): n[0] += 1
        x[:, c], info = cg(K, rhs[:, c], x0=x0[:, c], M=M, rtol=1e-6, maxiter=60, callback=cb); iters += n[0]
    lut = np.clip(x, 0, 1).reshape(N, N, N, 3); f = fr[i]
    p = F.apply_lut(lut, f.src); g = V.apply_global(model, f.src)
    e, off = L.no_L(p, f.dst)
    return f.name, {'before': L.de_stats(f.src, f.dst), 'global_only': L.de_stats(g, f.dst), 'table': L.de_stats(p, f.dst), 'table_without_mean_L': round(e, 2), 'mean_L_error': off, 'cg_iters': iters}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('cache'); ap.add_argument('out')
    ap.add_argument('--smooth', type=float, default=0.3); ap.add_argument('--prior', type=float, default=0.05)
    ap.add_argument('--jobs', type=int, default=6); ap.add_argument('--picks', type=int, default=2000); ap.add_argument('--write', action='store_true')
    a = ap.parse_args(); t0 = time.time(); z = np.load(a.cache); names = sorted({k[:-2] for k in z.files})
    frames = [Lite(n, z[n + '_a'], z[n + '_b'], a.picks) for n in names]; del z; t1 = time.time()
    x0, lu, model = direct(frames, a.smooth, a.prior); t2 = time.time()
    G.update(frames=frames, sm=a.smooth, pr=a.prior, lu=lu, x0=x0)
    with mp.get_context('fork').Pool(a.jobs) as p: res = p.map(one, range(len(frames)))
    t3 = time.time(); h = dict(res); r = list(h.values()); lut = np.clip(x0, 0, 1).reshape(N, N, N, 3)
    s = V.sanity(lut); ins = np.mean([L.de_stats(F.apply_lut(lut, f.src), f.dst)['mean'] for f in frames])
    rep = dict(settings=dict(smooth=a.smooth, prior=a.prior), held_out=h, held_out_mean=dict(before=L.means(r, 'before'), global_only=L.means(r, 'global_only'), table=L.means(r, 'table'),
               table_without_mean_L=round(float(np.mean([v['table_without_mean_L'] for v in r])), 2)), in_sample_mean=round(float(ins), 2), sanity=s,
               global_model=dict(tone_knots=[round(float(v), 4) for v in model[0]], matrix=np.round(model[1], 4).tolist()),
               seconds=dict(load=round(t1 - t0), full_solve=round(t2 - t1), folds=round(t3 - t2)), mean_cg_iters=round(float(np.mean([v['cg_iters'] for v in r])), 1))
    print(json.dumps({k: rep[k] for k in ('settings', 'held_out_mean', 'in_sample_mean', 'seconds', 'mean_cg_iters')}))
    print({k: s[k] for k in ('grey_max_chroma', 'saturated_hue_shift_deg_mean_p95_max', 'saturated_chroma_ratio_min_median')}, s['corners_rgb255'])
    if a.write:
        o = Path(a.out); o.mkdir(parents=True, exist_ok=True); np.save(o / 'lut16.npy', lut); (o / 'lut16.bin').write_bytes(np.round(lut * 255).astype(np.uint8).tobytes())
        (o / 'fit-report.json').write_text(json.dumps(rep, indent=1) + '\n')

if __name__ == '__main__':
    main()
