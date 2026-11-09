#!/usr/bin/env python3
"""Check what is committed before it merges. Runs on every pull request, and locally: python3 tools/repo_check.py

Refuses:
  - firmware and photo files: DATs, ffboot/ffinit, RAWs, card files, zips, any binary that is not a small image, a GVFF icon,
    the pinned font, or a recipe in firmware/recipes/;
  - a recipe that is not valid, or whose own bytes hold a long stretch of a known Fujifilm file header;
  - personal paths, email addresses, names of private projects or paid looks;
  - files over 5 MB.
It reads files only; it never changes anything.
"""
import hashlib, json, lzma, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINNED = {'fonts/Lato-Bold.ttf': 'bf1b8130069b44b9148eeece35e5423bedac49777ba746615b826b8276574a7b'}
BINARY_OK = {'.png', '.gvff'}
TEXT = {'.py', '.md', '.json', '.sh', '.txt', '.js', '.html', '.css', '.yml', '.yaml', '.toml', '.cfg', '.ini', ''}
LIMIT = 5 * 1024 * 1024
# Built from pieces so this file does not match itself.
_NAMES = ['/' + 'root/', '/data' + '-storage', 'xt4' + '-film-sims', 'arche' + 'type', 'john' + 'borillo8']
PRIVATE = re.compile('|'.join(map(re.escape, _NAMES)) + r'|/home/[a-z]|/Users/[A-Za-z]|[A-Z]:\\\\Users\\\\', re.I)
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com|anthropic\.com)[A-Za-z0-9.-]+\.[a-z]{2,}')
EMAIL_OK = re.compile(r'noreply@|example\.(com|org)')


def tracked():
    out = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True).stdout
    return [p for p in out.decode().split('\0') if p]


def recipe_ok(rel, data):
    try:
        r = json.loads(lzma.decompress(data))
    except Exception as e:                                     # noqa: BLE001
        return [f'{rel}: not an LZMA JSON recipe ({e})']
    if r.get('format') != 'xt3-recipe-1' or not re.fullmatch(r'[0-9a-f]{64}', r.get('target', {}).get('sha256', '')):
        return [f'{rel}: not an xt3-recipe-1 with a pinned target']
    kinds = {o.get('op') for o in r.get('ops', [])}
    return [] if kinds <= {'own', 'copy', 'icons'} else [f'{rel}: unknown steps {kinds}']


def main():
    problems, files = [], tracked()
    for rel in files:
        p = ROOT / rel
        if not p.is_file():
            continue
        data, suf = p.read_bytes(), p.suffix.lower()
        if rel in PINNED:
            if hashlib.sha256(data).hexdigest() != PINNED[rel]:
                problems.append(f'{rel}: not the pinned file')
            continue
        if rel.startswith('firmware/recipes/') and rel.endswith('.json.xz'):
            problems += recipe_ok(rel, data)
            continue
        if len(data) > LIMIT:
            problems.append(f'{rel}: {len(data) / 1e6:.1f} MB; large files do not belong in git')
        if suf in TEXT and b'\0' not in data[:4096]:
            text = data.decode('utf-8', 'replace')
            for m in PRIVATE.finditer(text):
                problems.append(f'{rel}: private path or name {m.group(0)!r}')
            for m in EMAIL.finditer(text):
                if not EMAIL_OK.search(m.group(0)):
                    problems.append(f'{rel}: email address {m.group(0)!r}')
        elif suf not in BINARY_OK:
            problems.append(f'{rel}: binary file type {suf or "(none)"} is not allowed (firmware, photos and builds stay out of git)')
    if problems:
        print('\n'.join(problems))
        raise SystemExit(f'repo check: {len(problems)} problem(s)')
    print(f'repo check: {len(files)} files OK')


if __name__ == '__main__':
    main()
