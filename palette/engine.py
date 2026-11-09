"""Data-only engine layer: put looks into a camera-approved ffboot, and refuse anything else.

The firmware code never changes here. A build is the approved image with these replaced: the store (tables and icons), the one word that
holds the store's sum, the icon records, row text, and list terminators to choose how many rows show. check_diff() compares against the
approved image byte by byte.
"""
import hashlib, json, re, struct, sys, zlib
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'tools'))
import film_icons as I  # noqa: E402
TABLE_SIZE = 12288
INIT_FIELDS = 0x4784
FFINIT_SIZE = 40808
FAST_START, FAST_END = 0x3000, 0x4000                   # the fast loader's room in ffinit; its segment table ends the room
FAST_MIN_RUN, FAST_PAGE, FAST_FIRST, FAST_STRIDE = 0x10000, 0x1000, 0x1000, 16     # as tools/build_ffboot_compact.py and tools/build_fast_sd.py
END_KEY = 0x7FFFFFFE
UI_FIRST = 24
LIST_COUNT = 4                                          # four key tables feed the five film lists and the Q list
NAME_CHARS = re.compile(r'^[A-Za-z0-9 .+/&\'-]+$')       # characters already drawn by the menus in stock English strings


class EngineError(Exception):
    pass


def require(ok, msg):
    if not ok:
        raise EngineError(msg)


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def word_sum(d):
    return int(np.frombuffer(d, '<u4').sum(dtype=np.uint64) & 0xFFFFFFFF)


class Engine:
    def __init__(s, path=HERE / 'engine' / 'engine.json'):
        c = json.loads(Path(path).read_text()); s.config = c
        s.id, s.label, s.rows = c['id'], c['label'], c['rows']
        s.store, s.store_end = (int(a, 16) for a in c['store'])
        s.lists, s.text, s.end = (int(c[k], 16) for k in ('lists', 'text', 'data_end'))
        s.icons, s.records = int(c['icons'], 16), int(c['records'], 16)
        s.code_range = tuple(int(a, 16) for a in c['code_check'])
        s.name_max, s.line_max = c['name_max'], c['line_max']
        s.slots = (s.store_end - s.store) // TABLE_SIZE
        s.ffboot_path, s.ffinit_path = ROOT / c['ffboot'], ROOT / c['ffinit']
        s._image = None; s._sum_at = None; s._keys = None
        f = c.get('fast')                                # the camera-approved fast loader, or None for the slow pair
        s.fast = dict(path=ROOT / f['ffinit'], sha256=f['ffinit_sha256'], table=int(f['table'], 16)) if f else None
        s.name_style = c.get('name_style', 0)            # line style of the row names: 2 = stock film-name style (test 53 on)
        r = c.get('raw_list')                            # RAW CONVERSION's film list copy (test 52 on): stock keys, the rows, extra rows
        s.raw_list = dict(keys=int(r['keys'], 16), rows=int(r['rows'], 16), first=r['first'], extra=list(r['extra'])) if r else None

    def image(s):
        if s._image is None:
            require(s.ffboot_path.exists(), f'approved ffboot missing: {s.ffboot_path}')
            d = s.ffboot_path.read_bytes()
            require(sha256(d) == s.config['ffboot_sha256'], 'approved ffboot hash mismatch')
            require(len(d) == s.store_end, 'approved ffboot size mismatch')
            s._image = d
            global _template_image
            _template_image = d
        return s._image

    @property
    def size(s):
        return s.store_end

    def init_template(s):
        d = s.ffinit_path.read_bytes()
        require(sha256(d) == s.config['ffinit_sha256'] and len(d) == FFINIT_SIZE, 'approved ffinit hash mismatch')
        return d

    def fast_template(s):
        d = s.fast['path'].read_bytes()
        require(sha256(d) == s.fast['sha256'] and len(d) == FFINIT_SIZE, 'approved fast ffinit hash mismatch')
        return d

    def sum_at(s):
        """The literal holding the store's sum. Found from the image, and it must be unique."""
        if s._sum_at is None:
            im = s.image(); total = word_sum(im[s.store:s.store_end])
            a, b = s.code_range
            hits = [x for x in range(a, b, 4) if struct.unpack_from('<I', im, x)[0] == total]
            require(len(hits) == 1, f'store sum literal found {len(hits)} times')
            s._sum_at = hits[0]
        return s._sum_at

    def code_hash(s, image=None):
        """Everything in the code range except the one data word."""
        a, b = s.code_range; c = bytearray((image or s.image())[a:b])
        c[s.sum_at() - a:s.sum_at() - a + 4] = bytes(4)
        return sha256(c)

    def text_formats(s):
        im = s.image()
        out = [struct.unpack_from('<HBBI', im, s.text + 8 * i) for i in range(s.rows * 2)]
        require([x[1] for x in out] == [1, 3] * s.rows, f'unexpected text entries {out[:4]}')
        return out[0][0], out[1][0]

    def raw_list_check(s):
        """The RAW CONVERSION list copy in the approved image: keys 0..15 (stock order), first..first+rows-1, the extra keys, end."""
        if not s.raw_list:
            return None
        im, R = s.image(), s.raw_list
        n = R['first'] + s.rows + len(R['extra'])
        keys = [struct.unpack_from('<2I', im, R['keys'] + 8 * i) for i in range(n + 1)]
        require([k for k, _ in keys[R['first']:n]] == list(range(R['first'], R['first'] + s.rows)) + R['extra'] and keys[n][0] == END_KEY
                and not any(p for _, p in keys[:n]), 'RAW CONVERSION list copy not as expected')
        return n

    def key_tables(s):
        """Address of the UI 24 entry in each of the four list clones: rows entries, then the terminator."""
        if s._keys is None:
            im = s.image(); hits = []
            for a in range(s.lists, s.text, 8):
                if struct.unpack_from('<2I', im, a) == (UI_FIRST, 0):
                    keys = [struct.unpack_from('<2I', im, a + 8 * i) for i in range(s.rows + 1)]
                    if keys[:-1] == [(UI_FIRST + i, 0) for i in range(s.rows)] and keys[-1][0] == END_KEY:
                        hits.append(a)
            require(len(hits) == LIST_COUNT, f'expected {LIST_COUNT} key tables, found {len(hits)}')
            s._keys = hits
        return s._keys


def to_camera(lut):
    """lut16.bin (R, G, B nested, R slowest) to camera order, field 0 = red, red index fastest."""
    a = np.frombuffer(lut, np.uint8).reshape(16, 16, 16, 3)
    i = np.arange(4096)
    return a[i & 15, (i >> 4) & 15, i >> 8].tobytes()


def from_camera(tbl):
    a = np.frombuffer(tbl, np.uint8).reshape(4096, 3)
    i = np.arange(4096)
    out = np.zeros((16, 16, 16, 3), np.uint8)
    out[i & 15, (i >> 4) & 15, i >> 8] = a
    return out.tobytes()


def check_text(eng, name, lines):
    require(len(lines) == 3, 'three description lines needed')
    require(1 <= len(name) <= eng.name_max, f'name must be 1 to {eng.name_max} characters')
    require(NAME_CHARS.match(name), 'name uses a character the camera may not draw')
    for t in lines:
        require(1 <= len(t) <= eng.line_max, f'each description line must be 1 to {eng.line_max} characters')
        require(NAME_CHARS.match(t) or re.match(r"^[A-Za-z0-9 .,+/&'-]+$", t), 'description uses a character the camera may not draw')


_templates, _font, _made = None, None, {}
_template_image = None                               # the approved image: its stock icon templates (no DAT needed)


def icons_for(pair):
    """The five GVFF files for a big and a small character. Cached: a build asks for the same pairs again."""
    global _templates, _font
    if pair not in _made:
        require(len(pair) == 2, 'an icon is one big and one small character')
        if _templates is None:
            _templates = I.load_templates_image(_template_image) if _template_image is not None else I.load_templates()
            _font = I.TTF(I.font_path())
        try:
            _made[pair] = I.make_icons(pair[0], pair[1], _templates, _font)
        except I.IconError as e:
            raise EngineError(str(e))
    return _made[pair]


def icon_region(eng, rows):
    """-> (packed GVFF files for the store, records). A hidden row keeps valid records, pointing at row 1's icons."""
    blob, recs, first = bytearray(), [], None
    for r in rows:
        if r is None:
            recs += first; continue
        ic = r.get('icons') or icons_for(r['icon'])
        mine = []
        for k in I.KINDS:
            d = ic[k]; w, h = I.SIZES[k]
            mine.append(struct.pack('<HHBBBBI', w, h, 1, 0, 0, 0, eng.icons + len(blob)))
            blob += d + bytes(-len(d) % 16)
        first = first or mine
        recs += mine
    require(eng.icons + len(blob) <= eng.store_end, 'icons do not fit the store')
    return bytes(blob), b''.join(recs)


def text_blob(eng, rows):
    """Same layout as tools/build_lut27_test.py: two entries a row, four line records a row, then UTF-16 strings."""
    name_fmt, desc_fmt = eng.text_formats()
    recs_at = eng.text + 8 * 2 * eng.rows; strs_at = recs_at + 12 * 4 * eng.rows
    entries, recs, strings = bytearray(), bytearray(), bytearray()
    for r in rows:
        for fmt, lines, style in ((name_fmt, [r['name']], eng.name_style), (desc_fmt, list(r['lines']), 0)):
            entries += struct.pack('<HBBI', fmt, len(lines), 0, recs_at + len(recs))
            for t in lines:
                recs += struct.pack('<IHHBBBB', strs_at + len(strings), 100, 100, style, 0, 0, 0)
                strings += t.encode('utf-16-le') + b'\0\0'
                strings += bytes((-len(strings)) % 4)
    b = bytes(entries + recs + strings)
    require(eng.text + len(b) <= eng.end, 'row text too long')
    return b


def apply(eng, rows):
    """rows: one entry per row, {name, lines, lut} or None. Looks fill from row 1 with no gaps; row 1 is what a stored PRO Neg. Std boots into."""
    require(len(rows) == eng.rows and rows[0] is not None, 'row 1 needs a look')
    shown = sum(1 for r in rows if r is not None)
    require(all(r is not None for r in rows[:shown]), 'rows must be filled from the top with no gaps')
    for r in rows[:shown]:
        check_text(eng, r['name'], r['lines'])
        require(len(r['lut']) == TABLE_SIZE, 'table must be 12,288 bytes')
    image = bytearray(eng.image())
    store = bytearray(eng.store_end - eng.store)
    for i, r in enumerate(rows[:shown]):
        store[i * TABLE_SIZE:(i + 1) * TABLE_SIZE] = to_camera(r['lut'])
    blob, recs = icon_region(eng, rows)
    store[eng.icons - eng.store:eng.icons - eng.store + len(blob)] = blob
    image[eng.store:eng.store_end] = store
    struct.pack_into('<I', image, eng.sum_at(), word_sum(store))
    require(len(recs) == 12 * 5 * eng.rows, 'icon record count')
    image[eng.records:eng.records + len(recs)] = recs
    blob = text_blob(eng, [r or rows[0] for r in rows])     # hidden rows keep valid entries, unreachable from the menus
    image[eng.text:eng.end] = bytes(eng.end - eng.text)
    image[eng.text:eng.text + len(blob)] = blob
    if shown < eng.rows:
        for a in eng.key_tables():
            term = image[a + 8 * eng.rows:a + 8 * eng.rows + 8]
            image[a + 8 * shown:a + 8 * eng.rows + 8] = term + bytes(8 * (eng.rows - shown))
        if eng.raw_list:                                 # RAW CONVERSION: keys and rows sit in step, so the extra rows move up
            R, n = eng.raw_list, eng.raw_list_check()
            k0 = R['keys'] + 8 * R['first']; r0 = R['rows'] + 48 * R['first']
            extra_rows = [image[r0 + 48 * (eng.rows + j):r0 + 48 * (eng.rows + j + 1)] for j in range(len(R['extra']))]
            keys = b''.join(struct.pack('<2I', R['first'] + i, 0) for i in range(shown))
            keys += b''.join(struct.pack('<2I', k, 0) for k in R['extra']) + image[R['keys'] + 8 * n:R['keys'] + 8 * n + 8]
            image[k0:R['keys'] + 8 * n + 8] = keys + bytes(R['keys'] + 8 * n + 8 - k0 - len(keys))
            for j, row in enumerate(extra_rows):
                image[r0 + 48 * (shown + j):r0 + 48 * (shown + j + 1)] = row
    return bytes(image)


def allowed_ranges(eng):
    r = [(eng.store, eng.store_end), (eng.text, eng.end), (eng.sum_at(), eng.sum_at() + 4), (eng.records, eng.records + 12 * 5 * eng.rows)]
    r += [(a, a + 8 * (eng.rows + 1)) for a in eng.key_tables()]
    if eng.raw_list:
        R, n = eng.raw_list, eng.raw_list_check()
        r += [(R['keys'] + 8 * R['first'], R['keys'] + 8 * (n + 1)), (R['rows'] + 48 * R['first'], R['rows'] + 48 * n)]
    return r


def check_diff(eng, new):
    """Every changed byte must sit inside a data range. Returns the changed byte count."""
    old = eng.image()
    require(len(new) == len(old), 'image size changed')
    a, b = np.frombuffer(old, np.uint8), np.frombuffer(new, np.uint8)
    changed = np.flatnonzero(a != b)
    mask = np.zeros(len(changed), bool)
    for lo, hi in allowed_ranges(eng):
        mask |= (changed >= lo) & (changed < hi)
    if not mask.all():
        raise EngineError(f'{int((~mask).sum())} bytes changed outside look data, first at {int(changed[~mask][0]):#x}')
    return int(len(changed))


def check_store_sum(eng, image):
    """The check that runs on every shot must pass, or every photo turns cyan."""
    require(struct.unpack_from('<I', image, eng.sum_at())[0] == word_sum(image[eng.store:eng.store_end]), 'store sum does not match the store')


def init_fields(payload):
    return len(payload), zlib.crc32(payload) & 0xFFFFFFFF, (len(payload) + 0xFFFF) & ~0xFFFF


def make_ffinit(eng, payload):
    t = bytearray(eng.init_template())
    struct.pack_into('<3I', t, INIT_FIELDS, *init_fields(payload))
    return bytes(t)


def check_pair(eng, ffboot, ffinit):
    t = eng.init_template()
    require(len(ffinit) == FFINIT_SIZE, 'ffinit size')
    require(ffinit[:INIT_FIELDS] == t[:INIT_FIELDS] and ffinit[INIT_FIELDS + 12:] == t[INIT_FIELDS + 12:], 'ffinit changed outside its three fields')
    require(struct.unpack_from('<3I', ffinit, INIT_FIELDS) == init_fields(ffboot), 'ffinit does not match ffboot')


def fast_segments(image):
    """The non-zero runs kept in the small ffboot. The first 4 KiB is its own segment, because the ROM reads it and the loader streams the rest."""
    gaps = []
    for m in re.finditer(rb'\x00{%d,}' % FAST_MIN_RUN, image):
        a = (m.start() + FAST_PAGE - 1) & ~(FAST_PAGE - 1); b = m.end() & ~(FAST_PAGE - 1)
        if b - a >= FAST_MIN_RUN:
            gaps.append((a, b))
    segs, at = [], 0
    for a, b in gaps:
        segs.append((at, a)); at = b
    if at < len(image):
        segs.append((at, len(image)))
    segs = [s for s in segs if s[1] > s[0]]
    require(segs[0][0] == 0 and segs[0][1] > FAST_FIRST, 'first segment')
    return [(0, FAST_FIRST), (FAST_FIRST, segs[0][1])] + segs[1:]


def fast_check(small):
    """The loader's sampled sum: one word in 16 of the small file, r = word + rotl(r, 1)."""
    r = 0
    for w in np.frombuffer(small, '<u4')[::FAST_STRIDE].tolist():
        r = (w + (((r << 1) | (r >> 31)) & 0xFFFFFFFF)) & 0xFFFFFFFF
    return r


def make_fast(eng, image):
    """-> (ffinit, small ffboot). Only data is filled in: the size, the check and the segment table."""
    require(len(image) == eng.size, 'image size')
    segs = fast_segments(image)
    small = b''.join(image[a:b] for a, b in segs)
    table = b''.join(struct.pack('<2I', a, b - a) for a, b in segs) + struct.pack('<2I', len(image), 0)
    room = FAST_END - eng.fast['table']
    require(len(table) <= room, f'too many segments: {len(segs)}')
    t = bytearray(eng.fast_template())
    t[eng.fast['table']:FAST_END] = table + bytes(room - len(table))
    struct.pack_into('<2I', t, INIT_FIELDS, len(small), fast_check(small))
    return bytes(t), small


def check_fast(eng, image, ffinit, small):
    t = eng.fast_template(); at = eng.fast['table']
    require(len(ffinit) == FFINIT_SIZE, 'ffinit size')
    require(ffinit[:at] == t[:at] and ffinit[FAST_END:INIT_FIELDS] == t[FAST_END:INIT_FIELDS] and ffinit[INIT_FIELDS + 8:] == t[INIT_FIELDS + 8:], 'fast ffinit changed outside its data')
    require(struct.unpack_from('<2I', ffinit, INIT_FIELDS) == (len(small), fast_check(small)), 'fast ffinit does not match its ffboot')
    rebuilt = bytearray(len(image)); pos = 0
    for a, n in fast_table(ffinit, eng):
        rebuilt[a:a + n] = small[pos:pos + n]; pos += n
    require(pos == len(small) and bytes(rebuilt) == image, 'segments do not rebuild the image')


def fast_table(ffinit, eng):
    out = []
    for at in range(eng.fast['table'], FAST_END, 8):
        a, n = struct.unpack_from('<2I', ffinit, at)
        if n == 0:
            return out
        out.append((a, n))
    raise EngineError('segment table has no end')


def read_rows(eng, get):
    """get(address, size) -> bytes from a candidate ffboot. Reads the shown rows back out of a build."""
    blob = get(eng.text, eng.end - eng.text)
    keys = get(eng.lists, eng.text - eng.lists)
    recs = get(eng.records, 12 * 5 * eng.rows)
    first = eng.key_tables()[0] - eng.lists
    shown = 0
    while shown < eng.rows and struct.unpack_from('<I', keys, first + 8 * shown)[0] == UI_FIRST + shown:
        shown += 1

    def s_at(addr):
        o = addr - eng.text; out = []
        while o + 2 <= len(blob):
            c = struct.unpack_from('<H', blob, o)[0]; o += 2
            if c == 0:
                break
            out.append(chr(c))
        return ''.join(out)
    rows = []
    for i in range(shown):
        lines = []
        for k in (0, 1):
            _, n, _, rec = struct.unpack_from('<HBBI', blob, (i * 2 + k) * 8)
            for j in range(n):
                lines.append(s_at(struct.unpack_from('<I', blob, rec - eng.text + j * 12)[0]))
        tbl = get(eng.store + i * TABLE_SIZE, TABLE_SIZE)
        icons = {}
        for j, k in enumerate(I.KINDS):
            at = struct.unpack_from('<I', recs, 12 * (5 * i + j) + 8)[0]
            require(eng.icons <= at < eng.store_end, 'icon record points outside the store')
            d = get(at, min(0x8000, eng.store_end - at))
            icons[k] = bytes(d[:I.gvff_end(d)])
        rows.append({'name': lines[0], 'lines': lines[1:], 'lut': from_camera(tbl), 'table_sha256': sha256(from_camera(tbl)), 'icons': icons})
    return rows


def self_check(eng):
    """Rule 3: rebuild the approved image from its own rows and require byte equality."""
    im = eng.image()
    rows = read_rows(eng, lambda a, n: im[a:a + n])
    require(len(rows) == eng.rows, f'approved image shows {len(rows)} rows')
    built = apply(eng, rows)
    if built != im:
        n = int(np.count_nonzero(np.frombuffer(built, np.uint8) != np.frombuffer(im, np.uint8)))
        raise EngineError(f'baseline rebuild differs from the approved image in {n} bytes')
    check_store_sum(eng, built)
    require(make_ffinit(eng, built) == eng.init_template(), 'baseline ffinit rebuild differs')
    return True
