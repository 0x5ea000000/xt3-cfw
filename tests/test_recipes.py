"""Recipe tests that need no firmware: structure, pins, and that steps cannot overlap or run outside the image.

With XT3_RECOVERY_ZIP set to FujiMod's X-T3 5.11 recovery zip and XT3_X4_DAT to Fujifilm's X-T4 2.12 FWUP0024.DAT, also builds
everything and checks the pinned outputs.
Run: python3 -m unittest discover -s tests
"""
import base64, json, lzma, os, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import xt3_build as X  # noqa: E402

RECIPES = ROOT / 'firmware' / 'recipes'
CARD_FILES = {'standard/ffboot.bin', 'standard/ffinit.bin', 'fast/ffboot.bin', 'fast/ffinit.bin', 'fast-loader.bin'}


def load(name):
    return X.load_recipe(RECIPES / name)


def spans(r):
    out = []
    for op in r['ops']:
        n = len(base64.b64decode(op['data'])) if op['op'] == 'own' else op['n']
        out.append((op['at'], op['at'] + n, op['op']))
    return sorted(out)


class Recipes(unittest.TestCase):
    def test_firmware_recipe(self):
        r = load('firmware.json.xz')
        self.assertEqual(r['base']['sha256'], X.FUJIMOD['ffboot.bin'])
        self.assertEqual(set(r['outputs']), CARD_FILES)
        self.assertTrue((RECIPES / r['fast_loader']).exists())
        s = spans(r)
        for (a0, a1, _), (b0, _, _) in zip(s, s[1:]):
            self.assertLessEqual(a1, b0, 'steps overlap')
        self.assertTrue(all(0 <= a and b <= r['target']['size'] for a, b, _ in s))
        for op in r['ops']:
            if op['op'] == 'copy':                            # copies come from the official image itself, never past it
                self.assertLessEqual(op['src'] + op['n'], r['base']['size'])
            if op['op'] == 'x4copy':                          # Fujifilm bytes come from the user's X-T4 file, never from the recipe
                self.assertIn(op['src'], ('x4dat',) + tuple(X.X4_OBJECTS))
                self.assertEqual(len(op['sha256']), 64)
            if op['op'] == 'x4derive':
                self.assertIn(op['what'], ('grain', 'fx_T1', 'fx_T2', 'fx_T3', 'fx_T4'))
            if op['op'] == 'own' and op['at'] < r['base']['size'] and 'old' not in op:
                self.assertTrue(0x1509000 <= op['at'] < 0x1523000, f'own bytes on official code at {op["at"]:#x} without an old-bytes check')

    def test_stub_recipe(self):                              # optional flash stub: only the three stub areas, each checked
        r = load('stub-dat.json.xz')
        self.assertEqual(r['base']['sha256'], X.X3_DAT)
        self.assertEqual(r['target']['size'], r['base']['size'])
        self.assertEqual(sorted((op['at'], len(base64.b64decode(op['data']))) for op in r['ops']), sorted(X.STUB_AREAS))
        self.assertTrue(all(op['op'] == 'own' and 'old' in op for op in r['ops']))

    @unittest.skipUnless(os.environ.get('XT3_DAT'), 'set XT3_DAT to Fujifilm\'s X-T3 5.11 FWUP0019.DAT to also build the stub')
    def test_stub_build(self):
        with tempfile.TemporaryDirectory() as d:
            X.stub(os.environ['XT3_DAT'], Path(d) / 'out', RECIPES / 'stub-dat.json.xz')
            self.assertEqual(X.sha((Path(d) / 'out' / 'FWUP0019.DAT').read_bytes()), load('stub-dat.json.xz')['target']['sha256'])

    def test_loader_recipe(self):
        r = load('fast-loader.json.xz')
        self.assertEqual(r['base']['sha256'], X.FUJIMOD['ffinit.bin'])
        self.assertEqual(r['target']['size'], r['base']['size'])
        self.assertTrue(all(op['op'] == 'own' for op in r['ops']))

    def test_fast_table_fits(self):
        img = bytes(0x1000) + b'\1' * 0x1000 + bytes(0x20000) + b'\2' * 0x2000
        fi, small = X.fast_pair(bytes(40808), img)
        self.assertEqual(len(small), 0x1000 + 0x1000 + 0x2000)

    @unittest.skipUnless(os.environ.get('XT3_RECOVERY_ZIP') and os.environ.get('XT3_X4_DAT'),
                         'set XT3_RECOVERY_ZIP and XT3_X4_DAT to also build from FujiMod\'s recovery zip and the X-T4 file')
    def test_full_build(self):
        with tempfile.TemporaryDirectory() as d:
            X.build(os.environ['XT3_RECOVERY_ZIP'], Path(d) / 'out', RECIPES / 'firmware.json.xz', os.environ['XT3_X4_DAT'])
            sums = (Path(d) / 'out' / 'SHA256SUMS').read_text().split('\n')
            self.assertEqual(len([s for s in sums if s]), len(CARD_FILES))


if __name__ == '__main__':
    unittest.main()
