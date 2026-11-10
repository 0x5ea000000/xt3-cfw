#!/usr/bin/env python3
"""Build the X-T3 firmware card files from FujiMod's official X-T3 5.11 recovery card. Python standard library only.

Input: FujiMod's "recovery SD boot" zip for X-T3 5.11, which FujiMod's site makes from Fujifilm's own firmware. It holds the
official image (`ffboot.bin`, with FujiMod's SD-boot bytes) and FujiMod's loader (`ffinit.bin`). Both are checked by SHA-256.
Nothing of Fujifilm's or FujiMod's is in this repository: the recipes hold only our own bytes, plus steps that copy short pieces
from the user's official image and draw the row icons from its stock icon templates.

Some recipes also need Fujifilm's X-T4 firmware 2.12 (`FWUP0024.DAT`, free from Fujifilm's X-T4 download page): the cfw's Classic
Neg., Bleach Bypass, FX Blue and large-grain values, their names and icons are Fujifilm's, so the build reads them from that file
(copy steps, and two tables computed from its values) instead of the recipe holding them. The camera never sees the X-T4 file.

Output (each pinned by SHA-256, so the result is exactly the firmware tested on the camera):
  standard/ffboot.bin, standard/ffinit.bin   full image, FujiMod's loader with its three fields set; boots in about 95 s
  fast/ffboot.bin, fast/ffinit.bin           the image without its long zero runs, our fast loader; boots in about 5 s
Both need Fn1 + rear dial at power-on on a camera with official firmware. Nothing here writes to a card or the camera.

Optional, for people willing to flash: `stub` makes the flash stub DAT from Fujifilm's own X-T3 5.11 DAT (FWUP0019.DAT). Installed with
the camera's own updater, it lets a normal power-on start the card (no Fn1 + rear dial). Read docs/optional-flash-stub.md first.

Usage: python3 tools/xt3_build.py build <recovery zip> <new output dir> [--x4 FWUP0024.DAT] [--recipe firmware/recipes/firmware.json.xz]
       python3 tools/xt3_build.py stub <Fujifilm X-T3 5.11 FWUP0019.DAT> <new output dir>
       python3 tools/xt3_build.py info [--recipe ...]
"""
import argparse, base64, hashlib, json, lzma, re, struct, sys, zipfile, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECIPES = ROOT / 'firmware' / 'recipes'
FUJIMOD = {'ffboot.bin': 'f6663ddab658b9bcdff2cb43e91697e475965ed2682fe4571bab2ac3d4ed57df',
           'ffinit.bin': 'c51adc5290e776a38112e2549ff6c6928883d8557a223f210bcf48e75d4a0808'}
X3_DAT = '9f2c75fd8a16a1d71b9218f6dbd3144b1f11820bcecd3a9608c8cda9f25f95a3'   # Fujifilm X-T3 firmware 5.11, FWUP0019.DAT
STUB_AREAS = ((0x20C, 4), (0x274 + 0x8A0, 4), (0x274 + 0x7300, 408))           # global checksum, setup literal, the stub (blank flash)
X4_DAT = '853d273b5603d3a2b93493f0ebd6a762b0b4b6bdc70317777775ae5f8ed93bc5'   # Fujifilm X-T4 firmware 2.12, FWUP0024.DAT
X4_OBJECTS = {   # packed objects of the X-T4 DAT: flash offset, flash size, SHA-256 of the unpacked object
    'x4obj1': (0x1A00000, 0x340000, 'b1a6146fc89394e7c47a2bd5b0e92c07de085567da3aa8d6198bc1a32de9eec6'),     # resources (icons)
    'x4obj5': (0x260000, 0x360000, '0b5b0fb0ee5fe6b109dae9964b5cddfe18edab46b4a0c195f9da194448906eeb'),
    'x4obj6': (0x5C0000, 0x520000, 'e1ef8b30903d3078fde103cdd134fca7bfc4337d67bcaf55c3080ffd5fd93b13'),
    'x4obj7': (0xAE0000, 0x480000, '6c8d7b8b0a37df8c2b636c504c07a80318243b313d5bf435e2c39ef3f56e9f80')}
X4_CFG, X4_CFG_N, X6_BASE = 0xC0274, 0x72000, 0x1E0F000                   # parameter backup in the DAT; object 6's RAM address
INIT_FIELDS, FAST_TABLE, FAST_END = 0x4784, 0x3E10, 0x4000
MIN_RUN, PAGE, FIRST, STRIDE = 0x10000, 0x1000, 0x1000, 16


class BuildError(Exception):
    pass


def need(ok, what):
    if not ok:
        raise BuildError(what)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def read_inputs(zip_path):
    """-> (ffboot, ffinit) from FujiMod's recovery zip, each checked."""
    with zipfile.ZipFile(zip_path) as z:
        names = {Path(n).name: n for n in z.namelist()}
        out = []
        for f, want in FUJIMOD.items():
            need(f in names, f'{zip_path}: no {f}; is this FujiMod\'s X-T3 5.11 recovery SD boot zip?')
            d = z.read(names[f])
            need(sha(d) == want, f'{f} in {zip_path} is not the official X-T3 5.11 recovery file (SHA-256 {sha(d)})')
            out.append(d)
    return out


def decode_packed(raw, start, end):
    """Fujifilm's packed objects (method 4: literal runs and back references in 16 KiB input blocks). Bytes are stored inverted."""
    buf = raw[start:end].translate(bytes(255 - i for i in range(256)))
    dlen, clen, count, block, method = struct.unpack_from('<5I', buf)
    need(method == 4 and block == 0x4000 and 20 <= clen <= len(buf) and count == (clen + block - 1) // block, 'packed object header')
    out, c = bytearray(), 20
    while c < clen:
        t = buf[c]; c += 1
        if t < 128:
            need(t and c + t <= clen, 'packed object literal'); out += buf[c:c + t]; c += t
        else:
            w = (t & 127) << 8 | buf[c]; c += 1
            n, d = w & 15, w >> 4
            need(n and 0 < d <= len(out), 'packed object reference')
            if d >= n:
                out += out[-d:len(out) - d + n]
            else:
                for _ in range(n):
                    out.append(out[-d])
    need(len(out) == dlen, 'packed object size')
    return bytes(out)


class X4:
    """Fujifilm's X-T4 2.12 firmware file, read only: the plain file and its packed objects, unpacked when a step needs them."""
    def __init__(s, path):
        raw = Path(path).read_bytes()
        need(sha(raw) == X4_DAT, f'{path} is not Fujifilm\'s X-T4 firmware 2.12 (FWUP0024.DAT); SHA-256 {sha(raw)}')
        s.raw, s._src = raw, {}

    def src(s, name):
        if name not in s._src:
            if name == 'x4dat':
                s._src[name] = s.raw.translate(bytes(255 - i for i in range(256)))
            else:
                f, n, want = X4_OBJECTS[name]
                d = decode_packed(s.raw, f + 0x274, f + 0x274 + n)
                need(sha(d) == want, f'X-T4 object {name} unpacked wrong')
                s._src[name] = d
        return s._src[name]

    def cfg(s):
        return s.src('x4dat')[X4_CFG:X4_CFG + X4_CFG_N]


def x4_derive(x4, what):
    """Two tables the cfw computes from X-T4 values: the large-grain values, and the FX Blue builders' four tables."""
    cfg, x6 = x4.cfg(), x4.src('x4obj6')
    word = lambda a, i: struct.unpack_from('<I', x6, a - X6_BASE + 4 * i)[0]
    if what == 'grain':
        vals = [cfg[word(0x25B2850, i)] for i in range(60)]
        return struct.pack('<60h', *[v - 256 if v >= 128 else v for v in vals])
    if what == 'fx_T2':
        return x6[0x25ADFA0 - X6_BASE:0x25ADFA0 - X6_BASE + 9]

    def rd(kind, o):
        need(0 <= o < X4_CFG_N - 1, f'X-T4 table offset {o:#x}')
        if kind == 'b':
            return cfg[o]
        u = cfg[o] | cfg[o + 1] << 8
        return u if kind == 'u16' else ((u - 0x10000) if u & 0x8000 else u) & 0xFFFFFFFF
    a, recs, words, kind = {'fx_T1': (0x25ADFBC, 8, 12, lambda i: 's16'), 'fx_T3': (0x25AE3EC, 9, 66, lambda i: 'b' if i % 11 < 3 else 's16'),
                            'fx_T4': (0x25AE13C, 4, 6, lambda i: 'u16')}[what]
    out = [word(a, r * words + i) if r == 0 else rd(kind(i), word(a, r * words + i)) for r in range(recs) for i in range(words)]
    return struct.pack(f'<{len(out)}I', *out)


def load_recipe(path):
    r = json.loads(lzma.decompress(Path(path).read_bytes()))
    need(r.get('format') == 'xt3-recipe-1', f'{path}: unknown recipe format')
    return r


def icons_blob(image, pairs):
    """The row icons, drawn from the stock templates in this image: five GVFF files a row, each padded to 16 bytes."""
    sys.path.insert(0, str(ROOT / 'tools'))
    import film_icons as I
    tpl, font = I.load_templates_image(image), I.TTF(I.font_path())
    blob = bytearray()
    for pair in pairs:
        ic = I.make_icons(pair[0], pair[1], tpl, font)
        for k in I.KINDS:
            blob += ic[k] + bytes(-len(ic[k]) % 16)
    return bytes(blob)


def apply(recipe, base, x4=None):
    """base (checked) + recipe -> target bytes, checked against the recipe's pinned hash. x4: X4, for recipes that need it."""
    need(x4 is not None or not recipe.get('x4'), 'this firmware needs Fujifilm\'s X-T4 firmware 2.12 file: add --x4 FWUP0024.DAT')
    need(sha(base) == recipe['base']['sha256'] and len(base) == recipe['base']['size'], 'base is not the recipe\'s base')
    out = bytearray(base) + bytes(recipe['target']['size'] - len(base))
    for op in recipe['ops']:
        at = op['at']
        if op['op'] == 'own':
            d = base64.b64decode(op['data'])
            if 'old' in op:                                   # our bytes on official code: the official bytes must be there
                need(sha(base[at:at + len(d)]) == op['old'], f'official bytes at {at:#x} are not the expected ones')
            out[at:at + len(d)] = d
        elif op['op'] == 'copy':                              # a piece of the user's official image, at a new address
            src, n = op['src'], op['n']
            need(sha(base[src:src + n]) == op['sha256'], f'official bytes at {src:#x} are not the expected ones')
            out[at:at + n] = base[src:src + n]
        elif op['op'] == 'x4copy':                            # a piece of the user's X-T4 file
            d = x4.src(op['src'])[op['off']:op['off'] + op['n']]
            need(sha(d) == op['sha256'], f'X-T4 bytes {op["src"]}:{op["off"]:#x} are not the expected ones')
            out[at:at + len(d)] = d
        elif op['op'] == 'x4derive':                          # a table computed from the X-T4 file's values
            d = x4_derive(x4, op['what'])
            need(sha(d) == op['sha256'] and len(d) == op['n'], f'X-T4 table {op["what"]} does not match')
            out[at:at + len(d)] = d
        elif op['op'] == 'icons':
            d = icons_blob(base, op['pairs'])
            need(sha(d) == op['sha256'] and len(d) == op['n'], 'icons do not match: check the font (fonts/Lato-Bold.ttf)')
            out[at:at + len(d)] = d
        else:
            raise BuildError(f'unknown op {op["op"]}')
    out = bytes(out)
    need(sha(out) == recipe['target']['sha256'], 'result does not match the tested firmware; nothing written')
    return out


def standard_loader(loader, image):
    t = bytearray(loader)
    struct.pack_into('<3I', t, INIT_FIELDS, len(image), zlib.crc32(image) & 0xFFFFFFFF, (len(image) + 0xFFFF) & ~0xFFFF)
    return bytes(t)


def segments(img):
    gaps = []
    for m in re.finditer(rb'\x00{%d,}' % MIN_RUN, img):
        a = (m.start() + PAGE - 1) & ~(PAGE - 1); b = m.end() & ~(PAGE - 1)
        if b - a >= MIN_RUN:
            gaps.append((a, b))
    segs, at = [], 0
    for a, b in gaps:
        segs.append((at, a)); at = b
    if at < len(img):
        segs.append((at, len(img)))
    segs = [s for s in segs if s[1] > s[0]]
    return [(0, FIRST), (FIRST, segs[0][1])] + segs[1:]


def fast_pair(fast_template, img):
    segs = segments(img)
    small = b''.join(img[a:b] for a, b in segs)
    table = b''.join(struct.pack('<2I', a, b - a) for a, b in segs) + struct.pack('<2I', len(img), 0)
    need(len(table) <= FAST_END - FAST_TABLE, 'too many segments')
    r = 0
    for i in range(0, len(small), 4 * STRIDE):
        r = (struct.unpack_from('<I', small, i)[0] + (((r << 1) | (r >> 31)) & 0xFFFFFFFF)) & 0xFFFFFFFF
    t = bytearray(fast_template)
    t[FAST_TABLE:FAST_END] = table + bytes(FAST_END - FAST_TABLE - len(table))
    struct.pack_into('<2I', t, INIT_FIELDS, len(small), r)
    return bytes(t), small


def build(zip_path, out_dir, recipe_path, x4_path=None):
    out_dir = Path(out_dir)
    need(not out_dir.exists(), f'{out_dir} exists; give a new folder')
    boot, loader = read_inputs(zip_path)
    rec = load_recipe(recipe_path)
    need(not rec.get('x4') or x4_path, 'this firmware needs Fujifilm\'s X-T4 firmware 2.12 file: add --x4 FWUP0024.DAT '
                                       '(download it from Fujifilm\'s X-T4 firmware page; see README)')
    image = apply(rec, boot, X4(x4_path) if rec.get('x4') else None)
    std = standard_loader(loader, image)
    fast_tpl = apply(load_recipe(Path(recipe_path).parent / rec['fast_loader']), loader)
    fi, small = fast_pair(fast_tpl, image)
    pins = rec['outputs']
    got = {'standard/ffboot.bin': image, 'standard/ffinit.bin': std, 'fast/ffboot.bin': small, 'fast/ffinit.bin': fi,
           'fast-loader.bin': fast_tpl}                      # for Palette: the fast loader before its data fields are filled
    for k, d in got.items():
        need(sha(d) == pins[k], f'{k} does not match the tested file; nothing written')
    for k, d in got.items():
        p = out_dir / k; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(d)
    (out_dir / 'SHA256SUMS').write_text(''.join(f'{sha(d)}  {k}\n' for k, d in got.items()))
    print(f'{rec["name"]}: built and checked')
    for k, d in got.items():
        print(f'  {k:22s} {len(d):>10,d} bytes  {sha(d)}')
    print('Copy ffboot.bin first, then ffinit.bin, from fast/ (or standard/) to the top folder of an empty card.')


def dat_checksum(raw):
    return (sum(raw[0x210:]) + 0x06CBBFF5) & 0xFFFFFFFF


def stub(dat_path, out_dir, recipe_path):
    """Official X-T3 5.11 DAT + our stub -> the tested stub DAT. Only the three stub areas may change; the result is pinned."""
    out_dir = Path(out_dir)
    need(not out_dir.exists(), f'{out_dir} exists; give a new folder')
    raw = Path(dat_path).read_bytes()
    need(sha(raw) == X3_DAT, f'{dat_path} is not Fujifilm\'s official X-T3 firmware 5.11 (FWUP0019.DAT); SHA-256 {sha(raw)}')
    rec = load_recipe(recipe_path)
    out = apply(rec, raw)
    keep = bytearray(len(raw))
    for a, n in STUB_AREAS:
        keep[a:a + n] = b'\1' * n
    need(all(x == y or k for x, y, k in zip(raw, out, keep)), 'the stub recipe changes bytes outside the stub areas')
    need(struct.unpack_from('<I', out, 0x20C)[0] == dat_checksum(out), 'global checksum')
    out_dir.mkdir(parents=True)
    (out_dir / 'FWUP0019.DAT').write_bytes(out)
    (out_dir / 'SHA256SUMS').write_text(f'{sha(out)}  FWUP0019.DAT\n')
    print(f'{rec["name"]}: built and checked')
    print(f'  FWUP0019.DAT {len(out):>12,d} bytes  {sha(out)}')
    print('This file is installed with the camera\'s firmware updater. Read docs/optional-flash-stub.md before you use it.')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build'); b.add_argument('zip'); b.add_argument('out'); b.add_argument('--x4', help='Fujifilm X-T4 2.12 FWUP0024.DAT')
    b.add_argument('--recipe', default=str(RECIPES / 'firmware.json.xz'))
    i = sub.add_parser('info'); i.add_argument('--recipe', default=str(RECIPES / 'firmware.json.xz'))
    t = sub.add_parser('stub'); t.add_argument('dat'); t.add_argument('out'); t.add_argument('--recipe', default=str(RECIPES / 'stub-dat.json.xz'))
    a = ap.parse_args(argv)
    try:
        if a.cmd == 'build':
            build(a.zip, a.out, a.recipe, a.x4)
        elif a.cmd == 'stub':
            stub(a.dat, a.out, a.recipe)
        else:
            r = load_recipe(a.recipe)
            kinds = {}
            for op in r['ops']:
                n = len(base64.b64decode(op['data'])) if op['op'] == 'own' else op['n']
                kinds[op['op']] = kinds.get(op['op'], 0) + n
            print(json.dumps(dict(name=r['name'], target=r['target'], bytes_by_op=kinds, outputs=r['outputs']), indent=1))
    except BuildError as e:
        raise SystemExit(f'refused: {e}')


if __name__ == '__main__':
    main()
