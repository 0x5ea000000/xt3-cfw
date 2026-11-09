"""Check a folder of Lightroom exports before fitting. These checks exist because a wrong batch looks fine until the score is bad."""
import hashlib, re
from pathlib import Path
from PIL import Image
import library as L

SLIDERS = (('Exposure2012', 0.0), ('Contrast2012', 0.0), ('Highlights2012', 0.0), ('Shadows2012', 0.0), ('Whites2012', 0.0), ('Blacks2012', 0.0))
JPEG = ('.jpg', '.jpeg')


def stems():
    return sorted(p.stem for p in L.PHOTOS.glob('*.RAF'))


def parse_preset(data):
    """Read name and type from a Lightroom .xmp preset or look."""
    s = data.decode('utf8', 'replace')
    m = re.search(r'<crs:Name>.*?<rdf:li[^>]*>([^<]*)', s, re.S) or re.search(r'crs:Name="([^"]*)"', s)
    if not m or 'crs:' not in s:
        raise ValueError('This does not look like a Lightroom preset file.')
    g = re.search(r'<crs:Group>.*?<rdf:li[^>]*>([^<]*)', s, re.S)
    t = re.search(r'crs:PresetType="([^"]*)"', s)
    return dict(name=m.group(1).strip(), group=g.group(1).strip() if g else None, type=t.group(1) if t else 'Preset',
                has_table='crs:RGBTable' in s)


def read_meta(path):
    im = Image.open(path)
    x = im.info.get('xmp') or b''
    s = x.decode('utf8', 'replace') if isinstance(x, (bytes, bytearray)) else x
    meta = dict(size=im.size, format=im.format, has_xmp=bool(s))
    block = re.search(r'<crs:Look[^>]*>.*?</crs:Look>', s, re.S)
    if block:
        b = block.group(0)
        n = re.search(r'crs:Name="([^"]*)"', b) or re.search(r'<crs:Name>.*?<rdf:li[^>]*>([^<]*)', b, re.S)
        a = re.search(r'crs:Amount="([^"]*)"', b)
        meta['look'] = n.group(1) if n else None
        meta['amount'] = float(a.group(1)) if a else None
    else:
        meta['look'] = meta['amount'] = None
    for k in ('CameraProfile', 'WhiteBalance', 'LensProfileEnable', 'GrainAmount', 'PostCropVignetteAmount', 'HasCrop'):
        m = re.search(rf'crs:{k}="([^"]*)"', s)
        meta[k] = m.group(1) if m else None
    meta['sliders'] = {}
    for k, _ in SLIDERS:
        m = re.search(rf'crs:{k}="([^"]*)"', s)
        meta['sliders'][k] = float(m.group(1)) if m else None
    return meta


def first_hash(folder):
    fs = sorted(p for p in folder.glob('*') if p.suffix.lower() in JPEG)
    return hashlib.sha256(fs[0].read_bytes()).hexdigest() if fs else None


def check(look, others=()):
    folder = L.exports_dir(look)
    want = stems()
    res = dict(folder=str(folder), expected=len(want), found=0, ok=False, problems=[], frames=[])
    def problem(level, text, frames=()):
        res['problems'].append(dict(level=level, text=text, frames=list(frames)[:8], count=len(frames)))
    if not want:
        problem('error', f'No RAF files in {L.PHOTOS}.')
        return res
    if not folder.is_dir():
        problem('info', 'No exports here yet.')
        return res
    have = {p.stem: p for p in folder.glob('*') if p.suffix.lower() in JPEG}
    res['found'] = len(have)
    missing = [n for n in want if n not in have]
    extra = [n for n in have if n not in want]
    if missing:
        problem('error', f'{len(missing)} photo{"s are" if len(missing) != 1 else " is"} missing. Filenames must match the RAFs.', missing)
    if extra:
        problem('warn', f'{len(extra)} extra file{"s" if len(extra) != 1 else ""} will be ignored.', extra)
    wrong = dict(look=[], amount=[], profile=[], sliders=[], wb=[], lens=[], effects=[], crop=[], small=[], nometa=[], bad=[])
    for n in want:
        if n not in have:
            continue
        try:
            m = read_meta(have[n])
        except Exception:
            wrong['bad'].append(n); continue
        if m['format'] != 'JPEG':
            wrong['bad'].append(n); continue
        if max(m['size']) < 1800:
            wrong['small'].append(n)
        if not m['has_xmp']:
            wrong['nometa'].append(n); continue
        if look.get('lightroom_look') and m['look'] != look['lightroom_look']:
            wrong['look'].append(n)
        if m['amount'] is not None and abs(m['amount'] - 1) > 1e-6:
            wrong['amount'].append(n)
        if m['CameraProfile'] not in (None, 'Adobe Standard v2'):
            wrong['profile'].append(n)
        if any(v not in (None, 0.0) for v in m['sliders'].values()):
            wrong['sliders'].append(n)
        if m['WhiteBalance'] not in (None, 'As Shot'):
            wrong['wb'].append(n)
        if m['LensProfileEnable'] not in (None, '0'):
            wrong['lens'].append(n)
        if m['GrainAmount'] not in (None, '0') or m['PostCropVignetteAmount'] not in (None, '0'):
            wrong['effects'].append(n)
        if m['HasCrop'] not in (None, 'False'):
            wrong['crop'].append(n)
    msgs = (('bad', 'error', 'File{s} could not be read as JPEG.'),
            ('look', 'error', f"Look is not \"{look.get('lightroom_look')}\" on {{n}} photo{{s}}."),
            ('amount', 'error', 'Look Amount is not 100 on {n} photo{s}.'),
            ('profile', 'error', 'Profile is not Adobe Standard v2 on {n} photo{s}.'),
            ('sliders', 'error', 'Exposure or tone sliders are not at 0 on {n} photo{s}.'),
            ('wb', 'error', 'White balance is not As Shot on {n} photo{s}.'),
            ('crop', 'error', '{n} photo{s} are cropped.'),
            ('lens', 'warn', 'Lens corrections are on for {n} photo{s}. The base renders have them off.'),
            ('effects', 'warn', 'Grain or vignette is on for {n} photo{s}. A table cannot reproduce these.'),
            ('small', 'warn', '{n} photo{s} are under 1800 pixels. Use a long edge of 3240.'),
            ('nometa', 'warn', '{n} photo{s} have no Lightroom metadata, so settings could not be checked. Set Metadata to All in the export dialog.'))
    for k, level, msg in msgs:
        if wrong[k]:
            n = len(wrong[k])
            problem(level, msg.format(n=n, s='' if n == 1 else 's'), wrong[k])
    fh = first_hash(folder)
    for o in others:
        if o['slug'] != look['slug'] and L.exports_dir(o).is_dir() and first_hash(L.exports_dir(o)) == fh and fh:
            problem('error', f"These are the same files as {o['name']}'s exports.")
    res['ok'] = res['found'] > 0 and not missing and not any(p['level'] == 'error' for p in res['problems'])
    return res


def check_base():
    want = stems(); have = {p.stem for p in L.BASE.glob('*') if p.suffix.lower() in JPEG} if L.BASE.is_dir() else set()
    return dict(folder=str(L.BASE), expected=len(want), found=len(have & set(want)), ok=bool(want) and set(want) <= have)
