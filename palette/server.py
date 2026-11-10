#!/usr/bin/env python3
"""Palette: add, compare and build looks for the X-T3 SD boot firmware. Usage: server.py [--host H] [--port P]

The app never writes to a card or the camera, and it has no DAT path. It produces two files for the user to copy.
"""
import argparse, base64, io, json, re, struct, time
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, abort, jsonify, request, send_file, send_from_directory
import builds as B, engine as G, exports as X, jobs as J, library as L, seed

app = Flask(__name__, static_folder=None)
app.config['MAX_FORM_MEMORY_SIZE'] = 4 << 20
ENG = G.Engine()
ENGINE_STATUS = dict(ok=False, error='not checked')
WEB = L.HERE / 'web'
SAFE_FILE = re.compile(r'^[A-Za-z0-9._ ()-]+$')


def startup_check():
    """Rule 3: nothing is built unless the approved image rebuilds byte for byte from its own rows."""
    try:
        G.self_check(ENG)
        ENGINE_STATUS.update(ok=True, error=None, label=ENG.label, sha256=ENG.config['ffboot_sha256'])
    except Exception as e:
        ENGINE_STATUS.update(ok=False, error=str(e), label=ENG.label)


@app.before_request
def same_origin():
    """Writes must come from this app's own page."""
    if request.method not in ('GET', 'HEAD'):
        o = request.headers.get('Origin')
        if o and urlparse(o).netloc != request.host:
            abort(403)


@app.errorhandler(G.EngineError)
def engine_error(e):
    return jsonify(error=str(e)), 409


@app.errorhandler(KeyError)
def not_found(e):
    return jsonify(error=f'not found: {e}'), 404


@app.errorhandler(ValueError)
def bad_value(e):
    return jsonify(error=str(e)), 400


def look_public(k):
    out = dict(k); out['job'] = J.latest(k['slug']); out['icon'] = L.icon_of(k); out['icon_chosen'] = bool(k.get('icon'))
    s = L.look_dir(k['slug']) / 'camera-score.json'
    out['camera_score'] = json.loads(s.read_text()) if s.exists() else None
    out['samples'] = (L.work_dir(k['slug']) / 'samples').is_dir() and any((L.work_dir(k['slug']) / 'samples').glob('*.t.jpg'))
    return out


@app.get('/')
def index():
    return send_from_directory(WEB, 'index.html')


@app.get('/web/<path:name>')
def web(name):
    return send_from_directory(WEB, name)


@app.get('/api/state')
def state():
    looks = [look_public(k) for k in L.all_looks()] + ([look_public(L.get(s)) for s in L.FILMS] if ENG.film_base else [])
    bl = B.all_builds(); rows = B.padded(ENG, L.rows())
    fp = B.fingerprint(rows); current = next((m for m in bl if m.get('fingerprint') == fp and m.get('engine') == ENG.id), None)
    return jsonify(engine=dict(ENGINE_STATUS, id=ENG.id, rows=ENG.rows, slots=ENG.slots, name_max=ENG.name_max, line_max=ENG.line_max, bases=list(G.BASE_FILMS) if ENG.film_base else None), looks=looks, rows=rows, builds=bl, current_build=current['id'] if current else None,
                   base=X.check_base(), active=J.active(), photos=len(X.stems()), photos_folder=str(L.PHOTOS))


@app.post('/api/preset')
def preset():
    f = request.files.get('file')
    if not f:
        raise ValueError('No file')
    d = f.read(2 << 20); return jsonify(X.parse_preset(d) | dict(filename=f.filename))


def text_fields(b):
    return dict(menu_name=b['menu_name'].strip(), lines=[t.strip() for t in b['lines']])


@app.post('/api/looks')
def add_look():
    b = request.get_json(); t = text_fields(b)
    G.check_text(ENG, t['menu_name'], t['lines'])
    name = b['name'].strip()
    if not name:
        raise ValueError('Name needed')
    return jsonify(look_public(L.create(name, t['menu_name'], t['lines'], (b.get('lightroom_look') or '').strip() or name, b.get('preset'))))


@app.get('/api/looks/<slug>')
def look(slug):
    k = L.get(slug); r = look_public(k)
    r['check'] = X.check(k, L.all_looks()) if k['status'] != 'fitted' or request.args.get('check') else None
    return jsonify(r)


@app.patch('/api/looks/<slug>')
def edit_look(slug):
    k = L.get(slug); b = request.get_json(); t = text_fields(b)
    G.check_text(ENG, t['menu_name'], t['lines'])
    k.update(t)
    if b.get('base'):
        if b['base'] not in G.BASE_FILMS:
            raise ValueError('Base film is PRO Neg. Std, Classic Neg. or Bleach Bypass.')
        if b['base'] != 'PRO Neg. Std' and not ENG.film_base:
            raise G.EngineError('This firmware builds every row on PRO Neg. Std.')
        k['base'] = b['base']
    if b.get('name'):
        k['name'] = b['name'].strip()
    if b.get('lightroom_look'):
        k['lightroom_look'] = b['lightroom_look'].strip()
    return jsonify(look_public(L.save(k)))


@app.patch('/api/looks/<slug>/icon')
def edit_icon(slug):
    k = L.get(slug); pair = (request.get_json().get('icon') or '').strip().upper()
    if len(pair) != 2 or any(c not in G.I.ALLOWED for c in pair):
        raise ValueError('An icon is one big and one small character: A to Z or 0 to 9.')
    G.icons_for(pair)
    k['icon'] = pair
    return jsonify(look_public(L.save(k)))


@app.get('/icon/<pair>.png')
def icon_image(pair):
    pair = pair.upper()
    kind = request.args.get('kind', 'list'); scale = min(max(request.args.get('scale', 3, type=int), 1), 6)
    if len(pair) != 2 or any(c not in G.I.ALLOWED for c in pair) or kind not in G.I.KINDS:
        abort(404)
    buf = io.BytesIO(); G.I.render(G.icons_for(pair)[kind], scale).save(buf, 'PNG'); buf.seek(0)
    return send_file(buf, mimetype='image/png', max_age=3600)


@app.delete('/api/looks/<slug>')
def remove_look(slug):
    L.get(slug)
    if slug in L.rows():
        raise G.EngineError('Take this look off its row first.')
    if J.active(slug):
        raise G.EngineError('This look has a job running.')
    L.delete(slug); return jsonify(ok=True)


def receive(folder, name):
    if not SAFE_FILE.match(name) or name.startswith('.'):
        raise ValueError('Bad file name')
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f'.{name}.part'
    with tmp.open('wb') as f:
        while True:
            c = request.stream.read(1 << 20)
            if not c:
                break
            f.write(c)
    tmp.replace(folder / name)
    return jsonify(ok=True)


@app.put('/api/looks/<slug>/exports/<name>')
def upload_export(slug, name):
    return receive(L.exports_dir(L.get(slug)), name)


@app.post('/api/looks/<slug>/fit')
def start_fit(slug):
    k = L.get(slug)
    if J.active(slug):
        raise G.EngineError('This look is already running.')
    if not X.check_base()['ok']:
        raise G.EngineError('The PRO Neg. Std base renders are incomplete.')
    if not X.check(k, L.all_looks())['ok']:
        raise G.EngineError('Fix the export problems first.')
    return jsonify(J.public(J.fit(slug)))


@app.post('/api/looks/<slug>/samples')
def start_samples(slug):
    L.get(slug)
    if J.active(slug):
        raise G.EngineError('This look is already running.')
    return jsonify(J.public(J.samples(slug)))


@app.put('/api/looks/<slug>/camera/<kind>/<name>')
def upload_camera(slug, kind, name):
    L.get(slug)
    if kind not in ('camera', 'camera-lightroom'):
        abort(404)
    return receive(L.work_dir(slug) / kind, name)


@app.post('/api/looks/<slug>/score')
def start_score(slug):
    L.get(slug)
    return jsonify(J.public(J.score(slug)))


@app.get('/api/frames')
def frames():
    """Frame list with per-look scores, for the comparison view."""
    out = {}
    for k in L.all_looks():
        r = L.report(k['slug'])
        if r:
            for n, v in r['held_out'].items():
                out.setdefault(n, {})[k['slug']] = dict(table=v['table']['mean'], before=v['before']['mean'])
    return jsonify(frames=[dict(name=n, scores=out[n]) for n in sorted(out)])


@app.get('/media/base/<name>')
def media_base(name):
    return send_from_directory(L.DATA / 'base-samples', name, max_age=3600)


@app.get('/media/look/<slug>/<name>')
def media_look(slug, name):
    L.look_dir(slug)
    return send_from_directory(L.work_dir(slug) / 'samples', name, max_age=60)


@app.get('/media/camera/<slug>/<name>')
def media_camera(slug, name):
    L.look_dir(slug)
    return send_from_directory(L.work_dir(slug) / 'camera-samples', name, max_age=60)


@app.post('/api/rows')
def set_rows():
    r = [x for x in request.get_json()['rows'] if x]
    G.require(r, 'Row 1 needs a look')
    G.require(len(r) <= ENG.rows, f'At most {ENG.rows} rows')
    G.require(len(set(r)) == len(r), 'A look can only be on one row')
    for s in r:
        G.require(L.get(s)['status'] == 'fitted', 'That look has no fitted table yet')
    L.set_rows(r); return jsonify(rows=B.padded(ENG, r))


@app.post('/api/builds')
def new_build():
    G.require(ENGINE_STATUS['ok'], f"Engine check failed: {ENGINE_STATUS['error']}")
    b = request.get_json(silent=True) or {}
    m, new = B.build(ENG, L.rows(), b.get('label'))
    return jsonify(build=m, new=new)


@app.patch('/api/builds/<bid>')
def camera_result(bid):
    m = B.get(bid); b = request.get_json()
    if b.get('status') not in ('not-tested', 'passed', 'failed'):
        raise ValueError('bad status')
    m['camera'] = dict(status=b['status'], note=(b.get('note') or '')[:500], at=time.time()); return jsonify(B.save(m))


@app.post('/api/builds/<bid>/restore')
def restore(bid):
    m = B.get(bid)
    for s in m['rows']:
        if s:
            G.require((L.LIBRARY / s).exists(), f'Look {s} is no longer in the library')
    L.set_rows(m['rows']); return jsonify(rows=m['rows'])


@app.get('/download/<bid>/<kind>')
def download(bid, kind):
    B.get(bid)
    speed = request.args.get('speed', 'fast')
    if speed not in ('fast', 'standard'):
        abort(404)
    if kind == 'zip':
        tag = '' if speed == 'fast' else '-standard'
        return send_file(B.zip_path(bid, speed), as_attachment=True, download_name=f'xt3-looks-{bid}{tag}.zip')
    if kind in ('ffboot.bin', 'ffinit.bin'):
        return send_file(B.card_file(bid, kind, speed), as_attachment=True, download_name=kind)
    abort(404)


@app.get('/api/card/spec')
def card_spec():
    return jsonify(slices=B.slices(ENG), init_offset=G.INIT_FIELDS, image_size=ENG.size, table=[G.FAST_START, G.FAST_END])


@app.post('/api/card/inspect')
def card_inspect():
    b = request.get_json()
    slices = {int(a): base64.b64decode(d) for a, d in b['slices'].items()}
    return jsonify(B.inspect(ENG, dict(size=b['size'], crc=b['crc'], word=b.get('word'), sampled=b.get('sampled'), compact=b.get('compact'), init=b.get('init'), slices=slices)))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--host', default='127.0.0.1'); ap.add_argument('--port', type=int, default=8877); a = ap.parse_args()
    seed.run(); startup_check()
    if ENGINE_STATUS['ok']:
        for m in B.all_builds():                             # builds from before the fast loader get their card files once
            B.make_card(ENG, m)
    for k in L.all_looks():                                  # a fit cut off by a restart is not still running
        if k['status'] == 'fitting':
            k.update(status='fitted' if k.get('table_sha256') else 'failed', error='The app restarted during the fit.'); L.save(k)
    print(f"Palette on http://{a.host}:{a.port}  engine: {'OK' if ENGINE_STATUS['ok'] else ENGINE_STATUS['error']}", flush=True)
    app.run(host=a.host, port=a.port, threaded=True, debug=False)


if __name__ == '__main__':
    main()
