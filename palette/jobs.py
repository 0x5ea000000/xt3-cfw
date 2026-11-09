"""One background job at a time: fitting uses most of the CPU. Each step is a subprocess with its output kept for the page."""
import json, os, shutil, subprocess, sys, threading, time, uuid
from collections import deque
import library as L, exports as X, quality as Q, engine as G

PY = sys.executable
FIT_JOBS = int(os.environ.get('PALETTE_JOBS', '6'))
jobs = {}
order = deque(maxlen=50)
_lock = threading.Lock()
_queue = deque()
_wake = threading.Event()


def public(j):
    return {k: j[k] for k in ('id', 'kind', 'slug', 'state', 'step', 'done', 'total', 'error', 'started', 'finished')} | dict(log=j['log'][-12:])


def submit(kind, slug, fn):
    j = dict(id=uuid.uuid4().hex[:10], kind=kind, slug=slug, state='queued', step='Waiting', done=0, total=0, error=None, started=None, finished=None, log=[], fn=fn)
    with _lock:
        jobs[j['id']] = j; order.append(j['id']); _queue.append(j)
    _wake.set(); return j


def active(slug=None):
    return [public(jobs[i]) for i in order if i in jobs and jobs[i]['state'] in ('queued', 'running') and (slug is None or jobs[i]['slug'] == slug)]


def latest(slug):
    for i in reversed(order):
        if i in jobs and jobs[i]['slug'] == slug:
            return public(jobs[i])
    return None


def _run(j, step, cmd, cwd=None, total=0):
    j.update(step=step, done=0, total=total)
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=dict(os.environ, PYTHONUNBUFFERED='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1'))
    for line in p.stdout:
        j['log'].append(line.rstrip()[:200]); j['done'] += 1
        del j['log'][:-200]
    if p.wait():
        raise RuntimeError(f'{step} failed: ' + ' | '.join(j['log'][-3:]))


def _worker():
    while True:
        _wake.wait(); _wake.clear()
        while True:
            with _lock:
                j = _queue.popleft() if _queue else None
            if j is None:
                break
            j.update(state='running', started=time.time())
            try:
                j['fn'](j); j.update(state='done', step='Finished')
            except Exception as e:
                j.update(state='failed', error=str(e), step='Failed')
                if j['slug']:
                    try:
                        k = L.get(j['slug'])
                        if k['status'] == 'fitting':
                            k.update(status='fitted' if k.get('table_sha256') else 'failed', error=str(e)); L.save(k)   # a failed re-fit keeps the old table
                    except KeyError:
                        pass
            j['finished'] = time.time()


threading.Thread(target=_worker, daemon=True).start()


def make_samples(j, look):
    d = L.look_dir(look['slug']); w = L.work_dir(look['slug'])
    _run(j, 'Making comparison images', [PY, str(L.HERE / 'samples_worker.py'), str(L.BASE), str(L.exports_dir(look)), str(d / 'lut16.npy'), str(w / 'samples'), str(L.DATA / 'base-samples'), str(min(FIT_JOBS, 4))], total=X_count())


def X_count():
    return len(X.stems())


def fit(slug):
    k = L.get(slug); k.update(status='fitting', error=None); L.save(k)

    def go(j):
        look = L.get(slug); w = L.work_dir(slug); w.mkdir(parents=True, exist_ok=True); d = L.look_dir(slug)
        j['step'] = 'Checking exports'
        c = X.check(look, L.all_looks())
        if not c['ok']:
            raise RuntimeError('Exports did not pass the checks.')
        cache = w / 'pairs.npz'
        try:
            _run(j, 'Lining up photo pairs', [PY, 'pairs.py', str(L.PHOTOS), str(L.exports_dir(look)), str(L.BASE), str(cache)], cwd=L.FIT_DIR, total=X_count())
            tmp = w / 'fit'
            _run(j, 'Fitting the colour table', [PY, 'fit_fast.py', str(cache), str(tmp), '--jobs', str(FIT_JOBS), '--write'], cwd=L.FIT_DIR)
            for f in ('lut16.bin', 'lut16.npy', 'fit-report.json'):
                shutil.move(str(tmp / f), str(d / f))
        finally:
            cache.unlink(missing_ok=True); cache.with_suffix('.json').unlink(missing_ok=True)
        rep = L.report(slug); tb = L.table(slug)
        G.require(len(tb) == G.TABLE_SIZE, 'fit produced a wrong table size')
        look = L.get(slug); look.update(status='fitted', fit=Q.verdict(rep), table_sha256=G.sha256(tb), fitted=time.time()); L.save(look)
        make_samples(j, look)
    return submit('fit', slug, go)


def samples(slug):
    return submit('samples', slug, lambda j: make_samples(j, L.get(slug)))


def score(slug):
    def go(j):
        w = L.work_dir(slug)
        n = len([p for p in (w / 'camera').glob('*')]) if (w / 'camera').is_dir() else 0
        _run(j, 'Scoring camera photos', [PY, str(L.HERE / 'score_worker.py'), str(w / 'camera'), str(w / 'camera-lightroom'), str(L.look_dir(slug) / 'camera-score.json'), str(w / 'camera-samples')], total=n)
    return submit('score', slug, go)
