"""Card builds. Each one is approved firmware plus look data, and is checked before it is written anywhere."""
import base64, io, json, re, struct, time, zipfile, zlib
from pathlib import Path
import engine as G, library as L
I = G.I

PACKS = L.DATA / 'packs'
SMALL = 0x3000000                                            # below this an ffboot is the small kind, its zero runs left out


def row_payload(slug):
    k = L.get(slug)
    G.require(k['status'] == 'fitted' and k.get('table_sha256'), f"{k['name']} has no fitted table")
    tb = L.table(slug)
    G.require(G.sha256(tb) == k['table_sha256'], f"{k['name']}: table file changed since it was fitted")
    return dict(name=k['menu_name'], lines=k['lines'], lut=tb, icon=L.icon_of(k))


def fingerprint(rows):
    """Identifies what would be on the card, so an edited name or a refitted table counts as a change."""
    parts = []
    for slug in [x for x in rows if x]:
        try:
            k = L.get(slug)
        except KeyError:
            return None
        parts.append(json.dumps([k.get('table_sha256'), k['menu_name'], k['lines'], L.icon_of(k)]))
    return G.sha256('|'.join(parts).encode())


def all_builds():
    out = []
    if PACKS.exists():
        for p in sorted(PACKS.glob('*/manifest.json')):
            out.append(json.loads(p.read_text()))
    return sorted(out, key=lambda m: -m['created'])


def get(bid):
    if not re.fullmatch(r'[a-z0-9-]+', bid):
        raise KeyError(bid)
    p = PACKS / bid / 'manifest.json'
    if not p.exists():
        raise KeyError(bid)
    return json.loads(p.read_text())


def save(m):
    p = PACKS / m['id'] / 'manifest.json'
    t = p.with_suffix('.tmp'); t.write_text(json.dumps(m, indent=1) + '\n'); t.replace(p)
    return m


def padded(eng, rows):
    """Rows as stored may be shorter than the engine's count (older builds). Looks fill from the top."""
    r = [x for x in rows if x]
    return r + [None] * (eng.rows - len(r))


def build(eng, rows, label=None):
    """rows: slugs from the top, the rest None."""
    rows = padded(eng, rows)
    G.require(rows[0], 'Row 1 needs a look')
    used = [s for s in rows if s]
    G.require(len(set(used)) == len(used), 'A look can only be on one row')
    payload = [row_payload(s) if s else None for s in rows]
    image = G.apply(eng, payload)
    changed = G.check_diff(eng, image)
    G.require(eng.code_hash(image) == eng.code_hash(), 'code range changed')
    G.check_store_sum(eng, image)
    ffinit = G.make_ffinit(eng, image); G.check_pair(eng, image, ffinit)
    back = G.read_rows(eng, lambda a, s: image[a:a + s])
    G.require(len(back) == len(used), 'row count read-back mismatch')
    for b, r in zip(back, payload):
        G.require(b['name'] == r['name'] and b['lines'] == list(r['lines']) and b['table_sha256'] == G.sha256(r['lut']), 'row read-back mismatch')
        G.require(b['icons'] == G.icons_for(r['icon']), 'row icon read-back mismatch')
    sha = G.sha256(image)
    for m in all_builds():
        if m['ffboot_sha256'] == sha:
            return make_card(eng, m), False
    n = 1 + max([int(m['id'].split('-')[0]) for m in all_builds()] or [0])
    names = '-'.join(L.slugify(L.get(s)['menu_name'])[:10] for s in used[:3])
    bid = f'{n:03d}-{names}'
    d = PACKS / bid; d.mkdir(parents=True)
    (d / 'ffboot.bin').write_bytes(image); (d / 'ffinit.bin').write_bytes(ffinit)
    same_as_engine = sha == eng.config['ffboot_sha256']
    notes = []
    if len(used) != eng.rows:
        notes.append(f"{len(used)} row{'s' if len(used) != 1 else ''} shown. So far the camera has only run the full {eng.rows} row list.")
    m = dict(id=bid, label=label or f"{len(used)} looks: " + ', '.join(L.get(s)['menu_name'] for s in used[:3]) + (' and more' if len(used) > 3 else ''),
             created=time.time(), engine=eng.id, rows=rows, row_names=[L.get(s)['menu_name'] for s in used], row_icons=[L.icon_of(L.get(s)) for s in used], ffboot_sha256=sha, ffinit_sha256=G.sha256(ffinit),
             crc=G.init_fields(image)[1], fingerprint=fingerprint(rows), changed_bytes=changed, shown_rows=len(used), notes=notes,
             camera=dict(status='passed' if same_as_engine else 'not-tested', note='Same bytes as the approved firmware.' if same_as_engine else ''))
    save(m)
    return make_card(eng, m), True


def make_card(eng, m):
    """The files for the card: the same image without its zero runs, and the fast loader. Older firmware keeps its full pair."""
    if not eng.fast or m.get('engine') != eng.id or m.get('card', {}).get('loader') == eng.fast['sha256']:
        return m                                             # a new approved loader gives every build of this firmware fresh card files
    d = PACKS / m['id']
    image = (d / 'ffboot.bin').read_bytes()
    G.require(G.sha256(image) == m['ffboot_sha256'], 'build file changed')
    ffinit, small = G.make_fast(eng, image); G.check_fast(eng, image, ffinit, small)
    c = d / 'card'; c.mkdir(exist_ok=True)
    (c / 'ffboot.bin').write_bytes(small); (c / 'ffinit.bin').write_bytes(ffinit)
    (d / 'xt3-card-files-fast.zip').unlink(missing_ok=True)
    m['card'] = dict(loader=eng.fast['sha256'], ffboot_sha256=G.sha256(small), ffinit_sha256=G.sha256(ffinit), size=len(small), file_crc=zlib.crc32(small) & 0xFFFFFFFF)
    return save(m)


def card_file(bid, kind, speed='fast'):
    """speed 'fast': the small image and the fast loader (about 5 s), when the build has them. 'standard': the full image and
    the original loader (about 95 s). Both carry the same looks; the build folder always keeps the standard pair."""
    G.require(speed in ('fast', 'standard'), 'speed is fast or standard')
    d = PACKS / bid
    return d / 'card' / kind if speed == 'fast' and get(bid).get('card') else d / kind


def zip_path(bid, speed='fast'):
    fast = speed == 'fast' and get(bid).get('card')
    d = PACKS / bid; z = d / ('xt3-card-files-fast.zip' if fast else 'xt3-card-files.zip')
    if not z.exists():
        tmp = z.with_suffix('.tmp')
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_STORED) as f:
            f.write(card_file(bid, 'ffboot.bin', speed), 'ffboot.bin'); f.write(card_file(bid, 'ffinit.bin', speed), 'ffinit.bin')
        tmp.replace(z)
    return z


def known_builds():
    """crc -> what it is, from the build folders, their AGENTS.md row and this app's builds."""
    status = {}
    agents = L.ROOT / 'AGENTS.md'
    if agents.exists():
        for m in re.finditer(r'\| ([^|]*?) FFBOOT \(`builds/([^`]+)`\) \| `[0-9a-f]{64}` \| ([^|]*) \|', agents.read_text()):
            status[m.group(2)] = (m.group(1).strip(), m.group(3).strip())
    out = {}
    for f in sorted((L.ROOT / 'builds').glob('*/ffinit.bin')):
        d = f.read_bytes()
        if len(d) != G.FFINIT_SIZE:
            continue
        size, crc = struct.unpack_from('<2I', d, G.INIT_FIELDS)
        boot = f.with_name('ffboot.bin')
        if boot.exists() and boot.stat().st_size == size and size < SMALL:      # a small pair's check is only a sample, so it is known by its file's CRC
            crc = zlib.crc32(boot.read_bytes()) & 0xFFFFFFFF
        title, st = status.get(f.parent.name, (f.parent.name, ''))
        out[crc] = dict(name=title, folder=f.parent.name, status=st, do_not_use='DO NOT USE' in st)
    for m in all_builds():
        for key in filter(None, (m['crc'], m.get('card', {}).get('file_crc'))):
            out[key] = dict(name=m['label'], build=m['id'], status=m['camera']['status'], do_not_use=m['camera']['status'] == 'failed')
    return out


def icon_png(gvff, scale=2):
    buf = io.BytesIO(); I.render(gvff, scale).save(buf, 'PNG')
    return base64.b64encode(buf.getvalue()).decode()


def inspect(eng, info):
    """info: size, crc, word and sampled (computed in the browser), init [size, check, workspace] or None, compact (the browser put a small ffboot back
    at image addresses using ffinit's segment table), slices {address: bytes}."""
    res = dict(problems=[], rows=None, known=None, in_family=False)
    size, crc, init = info['size'], info['crc'], info.get('init')
    compact = bool(info.get('compact'))
    whole = init is not None and init[0] == size and init[1] in (crc, info.get('word'))    # the byte CRC, or test 31's word check: every byte or word counted
    sample = init is not None and init[0] == size and init[1] == info.get('sampled')       # one word in 16: the file's CRC must also be a known build's
    known = known_builds(); k = known.get(crc) or (known.get(init[1]) if whole else None); res['known'] = k
    match = whole or (sample and crc in known)
    if k and k.get('do_not_use'):
        res['problems'].append(dict(level='error', text=f"This build is marked do not use: {k['status']}"))
    if size != eng.size and not k and not compact:
        want = init[0] if init is not None and init[0] < SMALL else eng.size
        res['problems'].append(dict(level='error', text=f'ffboot.bin is {size:,} bytes, expected {want:,}. The copy may be incomplete.'))
    if init is None:
        res['problems'].append(dict(level='error', text='ffinit.bin was not found next to ffboot.bin. The camera needs both.'))
    elif sample and not match:
        res['problems'].append(dict(level='error', text='ffboot.bin is not the same as any build here. It may be damaged, so copy both files again.'))
    elif not match:
        res['problems'].append(dict(level='error', text='ffinit.bin and ffboot.bin do not belong together, or the copy is damaged. Copy both again.'))
    res['files_match'] = match
    if size == eng.size or compact:
        s = info['slices']

        def get(a, n):
            for base, d in s.items():
                if base <= a and a + n <= base + len(d):
                    return d[a - base:a - base + n]
            raise KeyError(hex(a))
        a, b = eng.code_range
        sum_word = struct.unpack_from('<I', get(eng.sum_at(), 4))[0]
        code = bytearray(get(a, b - a)); code[eng.sum_at() - a:eng.sum_at() - a + 4] = bytes(4)
        res['in_family'] = G.sha256(code) == eng.code_hash()
        if res['in_family']:
            rows = G.read_rows(eng, get)
            by = {x.get('table_sha256'): x for x in L.all_looks()}
            for r in rows:
                r.pop('lut')
                r['icon_png'] = icon_png(r.pop('icons')['list'])
                x = by.get(r['table_sha256']); r['look'] = x['slug'] if x else None; r['look_name'] = x['name'] if x else None
            res['rows'] = rows
            res['store_sum_ok'] = sum_word == G.word_sum(get(eng.store, eng.store_end - eng.store))
            if not res['store_sum_ok']:
                res['problems'].append(dict(level='error', text='The store sum is wrong. Photos would turn cyan on this card.'))
        elif not k:
            res['problems'].append(dict(level='warn', text='This is not a build this app knows. It may be stock SD files or an older test.'))
    return res


def slices(eng):
    a, b = eng.code_range
    return [[a, b - a], [eng.store, eng.store_end - eng.store], [eng.lists, eng.end - eng.lists], [eng.records, 12 * 5 * eng.rows]]
