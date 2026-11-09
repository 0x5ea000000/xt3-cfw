#!/usr/bin/env python3
"""Score photos from the camera against Lightroom exports of the same frames. Evidence label: camera.
Accepts JPEGs or RAFs; a RAF is scored through its embedded JPEG, which is the camera's own output (first frames must confirm the
table reaches it). Usage: score_worker.py <camera_dir> <lightroom_dir> <out.json> <sample_dir>"""
import json, struct, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research' / 'claude-look-fit'))
import pairs as P
F = P.F


def raf_jpeg(path, tmp):
    d = Path(path).read_bytes()
    if d[:16] != b'FUJIFILMCCD-RAW ':
        raise ValueError('not a RAF')
    off, size = struct.unpack_from('>II', d, 84)
    if d[off:off + 2] != b'\xff\xd8':
        raise ValueError('no embedded JPEG')
    out = Path(tmp) / (Path(path).stem + '.jpg'); out.write_bytes(d[off:off + size]); return out


def main():
    cam, lr, out, samples = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    samples.mkdir(parents=True, exist_ok=True); rows = []; skipped = []
    with tempfile.TemporaryDirectory() as tmp:
        for p in sorted(cam.glob('*')):
            if p.suffix.lower() not in ('.jpg', '.jpeg', '.raf'):
                continue
            hit = [q for q in lr.glob(p.stem + '.*') if q.suffix.lower() in ('.jpg', '.jpeg')]
            if not hit:
                skipped.append(p.stem); continue
            src = raf_jpeg(p, tmp) if p.suffix.lower() == '.raf' else p
            a0, b0 = P.load(src), P.load(hit[0])
            if a0.shape != b0.shape:
                skipped.append(p.stem); continue
            a, b, s, _ = P.shift(a0, b0, r=4)
            d = F.de(a.astype(np.float64), b.astype(np.float64))
            la, lb = F.lab(a.astype(np.float64)), F.lab(b.astype(np.float64))
            rows.append(dict(frame=p.stem, mean=round(float(d.mean()), 2), median=round(float(np.median(d)), 2), p95=round(float(np.percentile(d, 95)), 2),
                             mean_L_error=round(float((la - lb)[..., 0].mean()), 2), source='raf' if p.suffix.lower() == '.raf' else 'jpeg'))
            for c, tag in ((a, 'camera'), (b, 'lightroom')):
                Image.fromarray((np.clip(c, 0, 1) * 255 + .5).astype(np.uint8)).save(samples / f'{p.stem}.{tag}.jpg', quality=88)
            print(rows[-1], flush=True)
    res = dict(frames=rows, skipped=skipped, mean=round(float(np.mean([r['mean'] for r in rows])), 2) if rows else None, evidence='camera')
    out.write_text(json.dumps(res, indent=1) + '\n'); print(json.dumps({k: res[k] for k in ('mean', 'skipped')}))


if __name__ == '__main__':
    main()
