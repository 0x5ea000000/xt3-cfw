#!/usr/bin/env python3
"""Download choice: fast SD boot (small image, fast loader) or standard SD boot (full image, original loader)."""
import sys, tempfile, unittest, zipfile
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import builds as B


class Speed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); packs = Path(self.tmp.name)
        for bid in ('a', 'b'):
            d = packs / bid; d.mkdir()
            (d / 'ffboot.bin').write_bytes(b'full ' + bid.encode()); (d / 'ffinit.bin').write_bytes(b'slow ' + bid.encode())
        (packs / 'a' / 'card').mkdir()
        (packs / 'a' / 'card' / 'ffboot.bin').write_bytes(b'small a'); (packs / 'a' / 'card' / 'ffinit.bin').write_bytes(b'fast a')
        meta = {'a': {'id': 'a', 'card': {'size': 7}}, 'b': {'id': 'b'}}
        self.p = [mock.patch.object(B, 'PACKS', packs), mock.patch.object(B, 'get', lambda bid: meta[bid])]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()

    def zipped(self, bid, speed):
        with zipfile.ZipFile(B.zip_path(bid, speed)) as z:
            return z.read('ffboot.bin'), z.read('ffinit.bin')

    def test_fast_is_the_default(self):
        self.assertEqual(B.card_file('a', 'ffinit.bin').read_bytes(), b'fast a')

    def test_both_speeds_for_a_fast_build(self):
        self.assertEqual(self.zipped('a', 'fast'), (b'small a', b'fast a'))
        self.assertEqual(self.zipped('a', 'standard'), (b'full a', b'slow a'))

    def test_build_without_fast_files_gives_standard(self):
        self.assertEqual(self.zipped('b', 'fast'), (b'full b', b'slow b'))

    def test_unknown_speed_refused(self):
        with self.assertRaises(Exception):
            B.card_file('a', 'ffinit.bin', 'turbo')


if __name__ == '__main__':
    unittest.main()
