#!/usr/bin/env python3
"""Build the X-T3 firmware card files from FujiMod's official X-T3 5.11 recovery card. Python standard library only.

Input: FujiMod's "recovery SD boot" zip for X-T3 5.11, which FujiMod's site makes from Fujifilm's own firmware. It holds the
official image (`ffboot.bin`, with FujiMod's SD-boot bytes) and FujiMod's loader (`ffinit.bin`). Both are checked by SHA-256.
Nothing of Fujifilm's or FujiMod's is in this repository: the recipes hold only our own bytes, plus steps that copy short pieces
from the user's official image and draw the row icons from its stock icon templates.

Output (each pinned by SHA-256, so the result is exactly the firmware tested on the camera):
  standard/ffboot.bin, standard/ffinit.bin   full image, FujiMod's loader with its three fields set; boots in about 95 s
  fast/ffboot.bin, fast/ffinit.bin           the image without its long zero runs, our fast loader; boots in about 5 s
Both need Fn1 + rear dial at power-on on a camera with official firmware. Nothing here writes to a card or the camera.

Usage: python3 tools/xt3_build.py build <recovery zip> <new output dir> [--recipe firmware/recipes/firmware.json.xz]
       python3 tools/xt3_build.py info [--recipe ...]
"""
import argparse, base64, hashlib, json, lzma, re, struct, sys, zipfile, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECIPES = ROOT / 'firmware' / 'recipes'
FUJIMOD = {'ffboot.bin': 'f6663ddab658b9bcdff2cb43e91697e475965ed2682fe4571bab2ac3d4ed57df',
           'ffinit.bin': 'c51adc5290e776a38112e2549ff6c6928883d8557a223f210bcf48e75d4a0808'}
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


def apply(recipe, base):
    """base (checked) + recipe -> target bytes, checked against the recipe's pinned hash."""
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


def build(zip_path, out_dir, recipe_path):
    out_dir = Path(out_dir)
    need(not out_dir.exists(), f'{out_dir} exists; give a new folder')
    boot, loader = read_inputs(zip_path)
    rec = load_recipe(recipe_path)
    image = apply(rec, boot)
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build'); b.add_argument('zip'); b.add_argument('out')
    b.add_argument('--recipe', default=str(RECIPES / 'firmware.json.xz'))
    i = sub.add_parser('info'); i.add_argument('--recipe', default=str(RECIPES / 'firmware.json.xz'))
    a = ap.parse_args(argv)
    try:
        if a.cmd == 'build':
            build(a.zip, a.out, a.recipe)
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
