"""GVFF (Fujifilm's serialized OpenVG icon files) and the TrueType reading needed to draw letters into them. Standard library only.

A path object is: float 10.0, u32 segment count, u32 coordinate bytes, the segment bytes (02 move, 04 line, 0C cubic, 00 close;
padded to 4), then float x/y pairs (y negative = down). Stock icons are a background rectangle plus one path object.
TEMPLATES are the RAM addresses (and sizes) of five stock X-T3 5.11 icons whose film-strip frame our row icons reuse; the letters
in them are replaced by Lato Bold glyphs. Nothing here holds Fujifilm data: templates are read from the user's own image.
"""
import struct
from pathlib import Path

FONT = '/usr/share/fonts/truetype/lato/Lato-Bold.ttf'
RAM_TO_FILE = 0x1800274 - 0x1E0000          # DAT offset of RAM 0x1E0000 (resources), for reading templates from a DAT


class TTF:
    def __init__(self, path):
        self.b = Path(path).read_bytes()
        n = struct.unpack_from('>H', self.b, 4)[0]
        self.t = {self.b[12 + 16 * i:16 + 16 * i].decode(): struct.unpack_from('>II', self.b, 20 + 16 * i) for i in range(n)}
        h = self.t['head'][0]
        self.upm = struct.unpack_from('>H', self.b, h + 18)[0]
        self.locfmt = struct.unpack_from('>h', self.b, h + 50)[0]

    def gid(self, ch):
        c0 = self.t['cmap'][0]
        for i in range(struct.unpack_from('>H', self.b, c0 + 2)[0]):
            pid, eid, off = struct.unpack_from('>HHI', self.b, c0 + 4 + 8 * i)
            s = c0 + off
            if struct.unpack_from('>H', self.b, s)[0] == 4:
                seg = struct.unpack_from('>H', self.b, s + 6)[0] // 2
                ends = struct.unpack_from(f'>{seg}H', self.b, s + 14)
                starts = struct.unpack_from(f'>{seg}H', self.b, s + 16 + 2 * seg)
                deltas = struct.unpack_from(f'>{seg}h', self.b, s + 16 + 4 * seg)
                ro = s + 16 + 6 * seg
                ranges = struct.unpack_from(f'>{seg}H', self.b, ro)
                for k in range(seg):
                    if starts[k] <= ord(ch) <= ends[k]:
                        if ranges[k] == 0:
                            return (ord(ch) + deltas[k]) & 0xFFFF
                        a = ro + 2 * k + ranges[k] + 2 * (ord(ch) - starts[k])
                        g = struct.unpack_from('>H', self.b, a)[0]
                        return (g + deltas[k]) & 0xFFFF if g else 0
        raise KeyError(ch)

    def contours(self, ch):
        g = self.gid(ch); lo = self.t['loca'][0]
        if self.locfmt:
            a, e = struct.unpack_from('>II', self.b, lo + 4 * g)
        else:
            a, e = (2 * x for x in struct.unpack_from('>HH', self.b, lo + 2 * g))
        p = self.t['glyf'][0] + a
        nc = struct.unpack_from('>h', self.b, p)[0]
        assert nc > 0, 'composite glyphs not supported'
        ends = struct.unpack_from(f'>{nc}H', self.b, p + 10); n = ends[-1] + 1
        q = p + 10 + 2 * nc; il = struct.unpack_from('>H', self.b, q)[0]; q += 2 + il
        flags = []
        while len(flags) < n:
            f = self.b[q]; q += 1; flags.append(f)
            if f & 8:
                r = self.b[q]; q += 1; flags += [f] * r
        def coords(short, same):
            nonlocal q
            v, out = 0, []
            for f in flags:
                if f & short:
                    d = self.b[q]; q += 1; v += d if f & same else -d
                elif not f & same:
                    v += struct.unpack_from('>h', self.b, q)[0]; q += 2
                out.append(v)
            return out
        xs = coords(2, 16); ys = coords(4, 32)
        out, s = [], 0
        for e in ends:
            out.append([(xs[i], ys[i], bool(flags[i] & 1)) for i in range(s, e + 1)]); s = e + 1
        return out


def to_cubic(contour):
    """TrueType quadratic contour -> list of ('M'|'L'|'C', points) closed path."""
    pts = contour
    if not pts[0][2]:                                    # start on an on-curve point
        k = next((i for i, p in enumerate(pts) if p[2]), None)
        if k is None:
            a, b = pts[0], pts[1]; pts = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, True)] + pts
        else:
            pts = pts[k:] + pts[:k]
    out = [('M', [pts[0][:2]])]; cur = pts[0][:2]; i = 1; n = len(pts)
    seq = pts[1:] + [pts[0]]
    j = 0
    while j < len(seq):
        p = seq[j]
        if p[2]:
            out.append(('L', [p[:2]])); cur = p[:2]; j += 1
        else:
            nxt = seq[j + 1] if j + 1 < len(seq) else pts[0]
            end = nxt[:2] if nxt[2] else ((p[0] + nxt[0]) / 2, (p[1] + nxt[1]) / 2)
            c1 = (cur[0] + 2 / 3 * (p[0] - cur[0]), cur[1] + 2 / 3 * (p[1] - cur[1]))
            c2 = (end[0] + 2 / 3 * (p[0] - end[0]), end[1] + 2 / 3 * (p[1] - end[1]))
            out.append(('C', [c1, c2, end])); cur = end
            j += 2 if nxt[2] and j + 1 < len(seq) else 1
    return out


def area(points):
    return sum(points[i][0] * points[i - 1][1] - points[i - 1][0] * points[i][1] for i in range(len(points))) / 2


def glyph_paths(font, ch, box, condense_min=0.78):
    """Fit glyph into box (x0, y0, x1, y1) in GVFF space; return cubic contours (y up = less negative)."""
    cs = [to_cubic(c) for c in font.contours(ch)]
    allp = [p for c in cs for _, ps in c for p in ps]
    gx0, gx1 = min(p[0] for p in allp), max(p[0] for p in allp)
    gy0, gy1 = min(p[1] for p in allp), max(p[1] for p in allp)
    x0, y0, x1, y1 = box
    sy = (y1 - y0) / (gy1 - gy0); sx = sy
    if (gx1 - gx0) * sx > (x1 - x0):                     # condense horizontally, then shrink if still too wide
        sx = max((x1 - x0) / (gx1 - gx0), sy * condense_min)
        if (gx1 - gx0) * sx > (x1 - x0):
            k = (x1 - x0) / ((gx1 - gx0) * sx); sx *= k; sy *= k
    w, h = (gx1 - gx0) * sx, (gy1 - gy0) * sy
    ox, oy = x0 + ((x1 - x0) - w) / 2, y0 + ((y1 - y0) - h) / 2
    tf = lambda p: (ox + (p[0] - gx0) * sx, oy + (p[1] - gy0) * sy)
    return [[(op, [tf(p) for p in ps]) for op, ps in c] for c in cs]


NPTS = {0: 0, 2: 1, 4: 1, 12: 3}


TEMPLATES = {'list': (0x2EC598, 36, 36), 'q': (0x4EBF28, 80, 48), 'caption': (0x604634, 150, 42),   # 73B, 7AF, 8FA
             'pb36v2': (0x2EC598, 36, 36), 'pb60': (0x34887C, 60, 30)}                              # 73B, 671


def path_object(b):
    """(offset of nseg, segs, points) of the single path object after the background rectangle."""
    found, o = [], 0x38
    while o + 8 <= len(b):
        nseg, nco = struct.unpack_from('<II', b, o)
        if 0 < nseg < 4000 and 0 < nco < 0x10000 and nco % 8 == 0:
            segs = b[o + 8:o + 8 + nseg]
            if all((s & ~1) in NPTS for s in segs) and segs[0] == 2 and sum(NPTS[s & ~1] for s in segs) * 8 == nco:
                co = o + 8 + ((nseg + 3) & ~3)
                pts = struct.unpack_from(f'<{nco // 4}f', b, co)
                found.append((o, bytes(segs), [(pts[i], pts[i + 1]) for i in range(0, len(pts), 2)], co + nco))
                o = co + nco; continue
        o += 4
    assert len(found) == 2 and len(found[0][1]) == 5, 'expected background + one path'
    assert found[1][3] == len(b), 'path object must end the file'
    return found[1][:3]


def split(segs, pts):
    subs, k = [], 0
    for s in segs:
        t = s & ~1
        if t == 2:
            subs.append([[], []])
        subs[-1][0].append(s); subs[-1][1] += pts[k:k + NPTS[t]]; k += NPTS[t]
    return subs


def bbox(pts):
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def emit(contours, sign):
    """contours: [[(op, [pts])]] -> segs, pts with the outer contour's direction = sign (inner opposite)."""
    segs, pts = [], []
    areas = [area([p for _, ps in c for p in ps]) for c in contours]
    big = max(range(len(contours)), key=lambda i: abs(areas[i]))
    for i, c in enumerate(contours):
        want = sign if i == big else -sign
        if areas[i] * want < 0:
            rev = [('M', [c[-1][1][-1]])]
            for j in range(len(c) - 1, 0, -1):
                op, ps = c[j]; start = c[j - 1][1][-1]
                rev.append(('L', [start]) if op == 'L' else ('C', [ps[1], ps[0], start]))
            c = rev
        for op, ps in c:
            segs.append({'M': 2, 'L': 4, 'C': 12}[op]); pts += ps
        segs.append(0)
    return segs, pts


def raw(contours):
    """Emit contours as given (already oriented)."""
    segs, pts = [], []
    for c in contours:
        for op, ps in c:
            segs.append({'M': 2, 'L': 4, 'C': 12}[op]); pts += ps
        segs.append(0)
    return segs, pts


def flatten(contours, n=8):
    """Replace every cubic by n straight lines (same end points)."""
    out = []
    for c in contours:
        cur, new = None, []
        for op, ps in c:
            if op == 'C':
                p0, (p1, p2, p3) = cur, ps
                for i in range(1, n + 1):
                    t = i / n; u = 1 - t
                    new.append(('L', [tuple(u**3*a + 3*u*u*t*b + 3*u*t*t*c_ + t**3*d for a, b, c_, d in zip(p0, p1, p2, p3))]))
                new[-1] = ('L', [p3])
            else:
                new.append((op, ps))
            cur = ps[-1]
        out.append(new)
    return out


def rebuild_inplace(template, repl):
    """Replace subpaths by index, keeping the template's subpath order. repl[i]: (contours, sign) or oriented contours."""
    at, segs, pts = path_object(template)
    subs = split(segs, pts)
    new_segs, new_pts = [], []
    for i, sp in enumerate(subs):
        if i in repl:
            s, p = emit(*repl[i]) if isinstance(repl[i], tuple) else raw(repl[i])
            new_segs += s; new_pts += p
        else:
            new_segs += sp[0]; new_pts += sp[1]
    body = struct.pack('<II', len(new_segs), len(new_pts) * 8) + bytes(new_segs) + bytes(4 - len(new_segs) % 4) + \
        b''.join(struct.pack('<ff', *p) for p in new_pts)
    return template[:at] + body
