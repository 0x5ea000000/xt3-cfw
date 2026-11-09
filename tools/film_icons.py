#!/usr/bin/env python3
"""Make a custom row's five film icons from a big and a small character.

Templates are Fujifilm's own canister icons, read from the user's official image (tools/gvff.py). Only the letters change;
header, paints, background, canister and perforations stay byte for byte.

  kind     size    template  letters replaced    used by
  list     36x36   FF00073B  big 3, small 5      film list
  q        80x48   FF0007AF  big 5, small 0      Q menu
  caption  150x42  FF0008FA  big 2, small 0      I.Q. menu film row
  pb36     36x36   FF00073B  big 3, small 5      playback, shooting screens
  pb60     60x30   FF000671  big 2, small 0      playback, shooting info tile

Every letter is written as one straight-line contour. A counter is joined to the outline by a zero-width cut, because the menu-row renderer
draws an outline plus a separate counter as a blob (test 20). B and 8 have two counters and get two cuts.
GVFF rule from test 23: 1..4 pad bytes after the segment list, never 0. check_gvff() walks every file against it.

Usage: film_icons.py <big><small> [...] <sheet.png>      writes a preview sheet for the given pairs
"""
import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gvff import TEMPLATES, NPTS, area, bbox, flatten, glyph_paths, path_object, rebuild_inplace, split, FONT, RAM_TO_FILE, TTF  # noqa: E402

KINDS = ('list', 'q', 'caption', 'pb36', 'pb60')
SLOTS = {'list': ('list', 3, 5), 'q': ('q', 5, 0), 'caption': ('caption', 2, 0), 'pb36': ('pb36v2', 3, 5), 'pb60': ('pb60', 2, 0)}
SIZES = {'list': (36, 36), 'q': (80, 48), 'caption': (150, 42), 'pb36': (36, 36), 'pb60': (60, 30)}
ALLOWED = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
CURVE_LINES = 4                                    # straight lines per curve: enough at these sizes, and keeps paths near stock icons


class IconError(Exception):
    pass


def require(ok, msg):
    if not ok:
        raise IconError(msg)


def load_templates_image(image):
    """The same five stock templates, read from a RAM image (ffboot.bin) at their RAM addresses. Official 5.11's image holds
    them byte-identical to the DATs above, so a build from official firmware needs no DAT."""
    out = {}
    for name, (ram, w, h) in TEMPLATES.items():
        b = image[ram:ram + 0x4000]
        require(b[:4] == b'GVFF' and struct.unpack_from('<ff', b, 0x30) == (w, -h), f'template {name} not in this image')
        out[name] = bytes(b[:b.find(b'GVFF', 4)])
    return out


def font_path():
    """Lato Bold (SIL Open Font Licence): a bundled copy next to the repo's tools if present, else the system's. Pinned by hash."""
    for p in (Path(__file__).resolve().parent.parent / 'fonts' / 'Lato-Bold.ttf', Path(FONT)):
        if p.exists():
            require(hashlib.sha256(p.read_bytes()).hexdigest() == FONT_SHA256, f'{p} is not the pinned Lato Bold')
            return str(p)
    raise IconError('Lato Bold not found: put Lato-Bold.ttf in fonts/')


FONT_SHA256 = 'bf1b8130069b44b9148eeece35e5423bedac49777ba746615b826b8276574a7b'




def default_templates():
    """From the built official image if there is one (tools/xt3_build.py), which needs no DAT."""
    img = Path(__file__).resolve().parent.parent / 'build' / 'standard' / 'ffboot.bin'
    if img.exists():
        return load_templates_image(img.read_bytes())
    raise IconError('Build the firmware first (python3 tools/xt3_build.py build ...): icons are drawn from its image')


def polygons(contours):
    """Line contours to point lists, without the repeated closing point."""
    out = []
    for c in contours:
        require(all(op in 'ML' for op, _ in c), 'contour is not straight lines')
        p = [q for _, ps in c for q in ps]
        out.append(p[:-1] if p[0] == p[-1] else p)
    return out


def one_contour(contours, sign):
    """Outline in direction sign, each counter opposite, spliced in by a zero-width cut. Returned already oriented."""
    polys = sorted(polygons(contours), key=lambda c: -abs(area(c)))
    outer = polys[0]
    if area(outer) * sign < 0:
        outer = outer[::-1]
    for inner in polys[1:]:
        require(abs(area(inner)) < abs(area(polys[0])), 'glyph has two outlines')
        if area(inner) * sign > 0:
            inner = inner[::-1]
        i, j = min(((a, b) for a in range(len(outer)) for b in range(len(inner))),
                   key=lambda ab: (outer[ab[0]][0] - inner[ab[1]][0]) ** 2 + (outer[ab[0]][1] - inner[ab[1]][1]) ** 2)
        outer = outer[:i + 1] + inner[j:] + inner[:j + 1] + outer[i:]
    return [[('M', [outer[0]])] + [('L', [p]) for p in outer[1:]]]


def gvff_end(d):
    """Strict walk: every path object carries 1..4 pad bytes. Returns the offset just past the last path (test 23)."""
    o, paths_seen = 0x38, 0
    npath = struct.unpack_from('<I', d, 0x14)[0]
    while paths_seen < npath:
        while d[o:o + 4] != struct.pack('<f', 10.0):
            o += 4
            require(o < len(d), 'GVFF path marker missing')
        nseg, nco = struct.unpack_from('<II', d, o + 4)
        segs = d[o + 12:o + 12 + nseg]
        require(all((s & ~1) in NPTS for s in segs) and sum(NPTS[s & ~1] for s in segs) * 8 == nco, 'GVFF segment list')
        require(nseg % 4 or not any(d[o + 12 + nseg:o + 16 + nseg]), 'GVFF pad block is not zero')
        o += 12 + ((nseg + 4) & ~3) + nco
        paths_seen += 1
    return o


def check_gvff(d):
    require(gvff_end(d) == len(d), 'GVFF length: coordinates do not end the file')


def make_icons(big, small, templates, font=None):
    """-> {kind: GVFF bytes}"""
    require(big in ALLOWED and small in ALLOWED and len(big) == 1 and len(small) == 1, 'icons use one capital letter or digit each')
    font = font or TTF(font_path())
    out = {}
    for kind in KINDS:
        name, big_at, small_at = SLOTS[kind]
        t = templates[name]
        subs = split(*path_object(t)[1:])
        repl = {}
        for at, ch in ((big_at, big), (small_at, small)):
            sign = 1 if area(subs[at][1]) > 0 else -1
            repl[at] = one_contour(flatten(glyph_paths(font, ch, bbox(subs[at][1])), CURVE_LINES), sign)
        out[kind] = rebuild_inplace(t, repl)
        check_gvff(out[kind])
    return out


def paths(d):
    """Path objects of a GVFF file, walked with the pad rule. Each is (segment bytes, flat coordinates)."""
    o, out = 0x38, []
    for _ in range(struct.unpack_from('<I', d, 0x14)[0]):
        while d[o:o + 4] != struct.pack('<f', 10.0):
            o += 4
            require(o < len(d), 'GVFF path marker missing')
        nseg, nco = struct.unpack_from('<II', d, o + 4)
        co = o + 12 + ((nseg + 4) & ~3)
        require(co + nco <= len(d), 'GVFF path runs past the file')
        out.append((d[o + 12:o + 12 + nseg], struct.unpack_from(f'<{nco // 4}f', d, co)))
        o = co + nco
    return out


def render(d, scale=4, on=(245, 245, 245), off=(70, 70, 70)):
    """Draw a GVFF icon as a PIL image: the first path is the background, the rest are even-odd filled."""
    from PIL import Image, ImageChops, ImageDraw
    w, h = struct.unpack_from('<ff', d, 0x30); w, h = int(w), int(-h)
    img = Image.new('RGB', (w * scale, h * scale), off)
    for segs, c in paths(d)[1:]:
        mask = Image.new('1', img.size, 0); poly = []; k = 0; pos = (0, 0)

        def close():
            nonlocal mask, poly
            if len(poly) > 2:
                m = Image.new('1', img.size, 0)
                ImageDraw.Draw(m).polygon([(x * scale, -y * scale) for x, y in poly], fill=1)
                mask = ImageChops.logical_xor(mask, m)
            poly = []
        for s in segs:
            t = s & ~1
            if t == 0:
                close()
            elif t in (2, 4):
                if t == 2:
                    close()
                pos = (c[k], c[k + 1]); poly.append(pos); k += 2
            else:
                p0, p1, p2, p3 = pos, (c[k], c[k + 1]), (c[k + 2], c[k + 3]), (c[k + 4], c[k + 5]); k += 6
                for i in range(1, 9):
                    u = i / 8; v = 1 - u
                    poly.append(tuple(v ** 3 * a + 3 * v * v * u * b + 3 * v * u * u * e + u ** 3 * f for a, b, e, f in zip(p0, p1, p2, p3)))
                pos = p3
        close()
        img.paste(on, mask=mask)
    return img


def sheet(pairs, path):
    from PIL import Image, ImageDraw
    tpl = default_templates(); font = TTF(font_path())
    rows = []
    for p in pairs:
        ic = make_icons(p[0], p[1], tpl, font)
        n = max(len(segs) for k in KINDS for segs, _ in paths(ic[k]))
        rows.append((p, [render(ic[k], 3 if k != 'caption' else 2) for k in KINDS], sum(len(v) for v in ic.values()), n))
    W = 8 + max(sum(t.width + 8 for t in r[1]) for r in rows) + 90; H = max(t.height for t in rows[0][1]) + 8
    s = Image.new('RGB', (W, H * len(rows) + 8), (30, 30, 30)); d = ImageDraw.Draw(s)
    for i, (p, tiles, n, m) in enumerate(rows):
        x = 8
        for t in tiles:
            s.paste(t, (x, 8 + i * H)); x += t.width + 8
        d.text((x, 12 + i * H), f'{p} {n}B, {m} segs', fill=(255, 255, 255))
    s.save(path); print(s.size, 'largest row', max(r[2] for r in rows), 'bytes, most segments', max(r[3] for r in rows))


if __name__ == '__main__':
    sheet(sys.argv[1:-1], sys.argv[-1])
