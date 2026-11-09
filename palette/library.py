"""Looks and rows on disk. library/ holds what must survive (tables, reports); data/ holds what can be regenerated."""
import json, os, re, shutil, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LIBRARY = Path(os.environ.get('PALETTE_LIBRARY', HERE / 'library'))
DATA = Path(os.environ.get('PALETTE_DATA', HERE / 'data'))
PHOTOS = Path(os.environ.get('PALETTE_PHOTOS', ROOT / 'sample_photos'))
BASE = PHOTOS / 'pro-neg-std'
FIT_DIR = ROOT / 'research' / 'claude-look-fit'
ROWS = LIBRARY / 'rows.json'


def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:40] or 'look'


def look_dir(slug):
    if not re.fullmatch(r'[a-z0-9-]+', slug):
        raise ValueError('bad look id')
    return LIBRARY / slug


def work_dir(slug):
    return DATA / 'looks' / slug


def save(look):
    d = look_dir(look['slug']); d.mkdir(parents=True, exist_ok=True)
    tmp = d / 'look.json.tmp'
    tmp.write_text(json.dumps(look, indent=1) + '\n'); tmp.replace(d / 'look.json')
    return look


def get(slug):
    p = look_dir(slug) / 'look.json'
    if not p.exists():
        raise KeyError(slug)
    return json.loads(p.read_text())


def all_looks():
    out = []
    if LIBRARY.exists():
        for p in sorted(LIBRARY.glob('*/look.json')):
            out.append(json.loads(p.read_text()))
    return sorted(out, key=lambda x: x.get('created', 0))


def exports_dir(look):
    return (ROOT / look['exports_dir']) if not Path(look['exports_dir']).is_absolute() else Path(look['exports_dir'])


def create(name, menu_name, lines, lightroom_look=None, preset=None):
    slug = base = slugify(name); n = 2
    while (LIBRARY / slug).exists():
        slug = f'{base}-{n}'; n += 1
    folder = PHOTOS / f'lightroom_{slug}'
    try:
        rel = str(folder.relative_to(ROOT))
    except ValueError:
        rel = str(folder)
    return save(dict(slug=slug, name=name, menu_name=menu_name, lines=lines, lightroom_look=lightroom_look or name, preset=preset,
                     exports_dir=rel, base='PRO Neg. Std', status='waiting-exports', fit=None, table_sha256=None,
                     created=time.time(), error=None))


def delete(slug):
    shutil.rmtree(look_dir(slug)); shutil.rmtree(work_dir(slug), ignore_errors=True)


def rows():
    if ROWS.exists():
        return json.loads(ROWS.read_text())
    return [None, None]


def set_rows(r):
    LIBRARY.mkdir(parents=True, exist_ok=True); ROWS.write_text(json.dumps(r) + '\n')


def icon_of(look):
    """The look's icon pair. Until one is chosen, the first and last characters of its camera name, so nothing is written for the user."""
    if look.get('icon'):
        return look['icon']
    chars = [c for c in look['menu_name'].upper() if c.isascii() and c.isalnum()]
    return chars[0] + chars[-1] if len(chars) > 1 else (chars[0] * 2 if chars else 'XX')


def table(slug):
    return (look_dir(slug) / 'lut16.bin').read_bytes()


def report(slug):
    p = look_dir(slug) / 'fit-report.json'
    return json.loads(p.read_text()) if p.exists() else None
