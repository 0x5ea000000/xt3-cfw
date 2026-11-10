#!/usr/bin/env python3
"""Safety checks of the data-only build path. Run with palette/.venv/bin/python -m unittest discover -s tests."""
import re, struct, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine as G
import library as L

ENG = G.Engine()
if not ENG.ffboot_path.exists():
    raise unittest.SkipTest('build the firmware first: python3 tools/xt3_build.py build <recovery zip> build')
LOOKS = [dict(name='PRO 400H F', lines=['Pro400H Frontier scan look', 'Soft contrast, pastel color', 'Use DR100, Color Chrome Off'],
              lut=bytes((i * 5 + 3) % 256 for i in range(G.TABLE_SIZE)), icon='PF'),
         dict(name='PRO 400H N', lines=['Pro400H Noritsu scan look', 'Clean contrast, soft color', 'Use DR100, Color Chrome Off'],
              lut=bytes((i * 11 + 1) % 256 for i in range(G.TABLE_SIZE)), icon='PN')]   # any two tables: the tests check structure, not colour
OTHER = bytes((i * 7) % 256 for i in range(G.TABLE_SIZE))


def rows(*r):
    r = list(r)
    return r + [None] * (ENG.rows - len(r))


class FastPair(unittest.TestCase):
    def setUp(self):
        self.im = G.apply(ENG, rows(LOOKS[0], dict(name='PORTRA 400', lines=['a', 'b', 'c'], lut=OTHER, icon='P4')))
        self.ffinit, self.small = G.make_fast(ENG, self.im)

    def test_only_data_differs_from_the_loader(self):
        G.check_fast(ENG, self.im, self.ffinit, self.small)
        self.assertLess(len(self.small), len(self.im))

    def test_same_bytes_as_the_builder(self):
        pack = sorted(L.DATA.glob('packs/004-*/ffboot.bin'))
        if not pack:
            self.skipTest('build 004 is not here')
        a, b = G.make_fast(ENG, pack[0].read_bytes())
        self.assertEqual(G.sha256(a), ENG.fast['sha256'])
        self.assertEqual(b, (L.ROOT / 'builds/46-fragments-plain/ffboot.bin').read_bytes())

    def test_code_change_refused(self):
        d = bytearray(self.ffinit); d[0x3004] ^= 1
        with self.assertRaises(G.EngineError):
            G.check_fast(ENG, self.im, bytes(d), self.small)

    def test_wrong_ffboot_refused(self):
        d = bytearray(self.small); d[64] ^= 1
        with self.assertRaises(G.EngineError):
            G.check_fast(ENG, self.im, self.ffinit, bytes(d))

    def test_unsampled_damage_refused_at_build(self):
        d = bytearray(self.small); d[4] ^= 1
        with self.assertRaises(G.EngineError):
            G.check_fast(ENG, self.im, self.ffinit, bytes(d))

    def test_table_end_required(self):
        d = bytearray(self.ffinit); d[ENG.fast['table']:G.FAST_END] = b'\xFF' * (G.FAST_END - ENG.fast['table'])
        with self.assertRaises(G.EngineError):
            G.fast_table(bytes(d), ENG)


class CardPage(unittest.TestCase):
    """A small ffboot's check is only a sample: the file's CRC must also be known."""

    def inspect(self, crc, sampled=7, init=None, size=1000):
        import builds as B
        real = B.known_builds
        B.known_builds = lambda: {123: dict(name='x', status='passed')}
        try:
            return B.inspect(ENG, dict(size=size, crc=crc, word=1, sampled=sampled, init=init or [size, sampled, 0], compact=False, slices={}))
        finally:
            B.known_builds = real

    def test_known_file_passes(self):
        self.assertTrue(self.inspect(123)['files_match'])

    def test_sample_match_with_unknown_file_fails(self):
        r = self.inspect(124)
        self.assertFalse(r['files_match'])
        self.assertIn('damaged', r['problems'][-1]['text'])


class Baseline(unittest.TestCase):
    def test_rebuilds_camera_approved_image_byte_exact(self):
        self.assertTrue(G.self_check(ENG))

    def test_engine_pinned(self):
        self.assertEqual(G.sha256(ENG.image()), '8c4c5b931d3ccef1dd71f44bb38c2691b1e7bb502465d1ddfff2830903875b90')   # P05b, official 5.11 port

    def test_reserved_firmware_data_kept_and_summed(self):
        # P05b keeps the cfw's CN/BB names and icons in the store tail: a build must keep them, and the store sum must cover them
        lo, hi = ENG.reserved
        im = G.apply(ENG, rows(*LOOKS))
        self.assertEqual(im[lo:hi], ENG.image()[lo:hi])
        self.assertTrue(any(im[lo:hi]))
        G.check_store_sum(ENG, im)

    def test_order_round_trip(self):
        self.assertEqual(G.from_camera(G.to_camera(OTHER)), OTHER)

    def test_sixteen_rows_eighty_slots(self):
        self.assertEqual((ENG.rows, ENG.slots), (16, 80))


class Changes(unittest.TestCase):
    def test_new_looks_change_data_only(self):
        im = G.apply(ENG, rows(LOOKS[0], dict(name='PORTRA 400', lines=['a', 'b', 'c'], lut=OTHER, icon='P4')))
        self.assertGreater(G.check_diff(ENG, im), 0)
        self.assertEqual(ENG.code_hash(im), ENG.code_hash())
        G.check_store_sum(ENG, im)

    def test_store_sum_follows_tables(self):
        im = G.apply(ENG, rows(LOOKS[0]))
        self.assertNotEqual(im[ENG.sum_at():ENG.sum_at() + 4], ENG.image()[ENG.sum_at():ENG.sum_at() + 4])
        self.assertEqual(struct.unpack_from('<I', im, ENG.sum_at())[0], G.word_sum(im[ENG.store:ENG.store_end]))

    def test_read_back(self):
        im = G.apply(ENG, rows(LOOKS[0], dict(name='PORTRA 400', lines=['a', 'b', 'c'], lut=OTHER, icon='P4')))
        r = G.read_rows(ENG, lambda a, n: im[a:a + n])
        self.assertEqual(len(r), 2)
        self.assertEqual((r[1]['name'], r[1]['lines'], r[1]['table_sha256']), ('PORTRA 400', ['a', 'b', 'c'], G.sha256(OTHER)))

    def test_row_counts(self):
        for n in (1, 2, 8, 15, 16):
            looks = [dict(name=f'LOOK {i}', lines=['a', 'b', 'c'], lut=OTHER, icon='B8') for i in range(n)]
            im = G.apply(ENG, rows(*looks))
            G.check_diff(ENG, im); G.check_store_sum(ENG, im)
            self.assertEqual(len(G.read_rows(ENG, lambda a, k: im[a:a + k])), n)
            for a in ENG.key_tables():
                self.assertEqual(struct.unpack_from('<I', im, a + 8 * n)[0], G.END_KEY)
            R = ENG.raw_list
            keys = [struct.unpack_from('<I', im, R['keys'] + 8 * i)[0] for i in range(R['first'] + n + len(R['extra']) + 1)]
            self.assertEqual(keys, [0, 1, 2, 3, 4, 5, 6, 7, 9, 8, 10, 11, 13, 12, 14, 15] + list(range(16, 16 + n)) + R['extra'] + [G.END_KEY])
            base = ENG.image()
            for j in range(len(R['extra'])):     # extra rows, if an engine has any, follow the last shown row
                at, src = R['rows'] + 48 * (16 + n + j), R['rows'] + 48 * (16 + ENG.rows + j)
                self.assertEqual(im[at:at + 48], base[src:src + 48])

    def test_names_in_film_name_style(self):
        im = G.apply(ENG, rows(LOOKS[0], LOOKS[1]))
        for i in range(ENG.rows):
            name_rec = struct.unpack_from('<I', im, ENG.text + 16 * i + 4)[0]
            desc_rec = struct.unpack_from('<I', im, ENG.text + 16 * i + 12)[0]
            self.assertEqual(im[name_rec + 8], ENG.name_style)
            self.assertEqual(im[desc_rec + 8], 0)
        self.assertEqual(ENG.name_style, 2)

    def test_empty_slots_are_zero(self):
        im = G.apply(ENG, rows(LOOKS[0], LOOKS[1]))
        self.assertFalse(any(im[ENG.store + 2 * G.TABLE_SIZE:ENG.icons]))

    def test_icons_read_back(self):
        im = G.apply(ENG, rows(LOOKS[0], dict(LOOKS[1], icon='B8')))
        r = G.read_rows(ENG, lambda a, n: im[a:a + n])
        self.assertEqual(r[0]['icons'], G.icons_for('PF'))
        self.assertEqual(r[1]['icons'], G.icons_for('B8'))

    def test_icon_changes_data_only(self):
        a = G.apply(ENG, rows(LOOKS[0], LOOKS[1])); b = G.apply(ENG, rows(LOOKS[0], dict(LOOKS[1], icon='S3')))
        self.assertNotEqual(a, b)
        G.check_diff(ENG, b); G.check_store_sum(ENG, b)
        self.assertEqual(ENG.code_hash(a), ENG.code_hash(b))

    def test_hidden_rows_keep_valid_records(self):
        im = G.apply(ENG, rows(LOOKS[0]))
        first = struct.unpack_from('<I', im, ENG.records + 8)[0]
        for n in range(5, 80, 5):
            self.assertEqual(struct.unpack_from('<I', im, ENG.records + 12 * n + 8)[0], first)

    def test_sixteen_heaviest_rows_fit(self):
        looks = [dict(name=f'LOOK {i}', lines=['a', 'b', 'c'], lut=OTHER, icon='S3') for i in range(ENG.rows)]
        im = G.apply(ENG, looks)
        G.check_diff(ENG, im); G.check_store_sum(ENG, im)
        self.assertLess(max(struct.unpack_from('<I', im, ENG.records + 12 * n + 8)[0] for n in range(80)), ENG.store_end)


class Refusals(unittest.TestCase):
    def tamper(self, at):
        b = bytearray(ENG.image()); b[at] ^= 1
        with self.assertRaises(G.EngineError):
            G.check_diff(ENG, bytes(b))

    def test_code_byte(self):
        self.tamper(0x1516008)

    def test_hook_outside_owned_memory(self):
        self.tamper(0xFF8288)

    def test_layout(self):
        self.tamper(0x10758A0)

    def test_byte_just_before_store(self):
        self.tamper(ENG.store - 1)

    def test_byte_just_before_text(self):
        self.tamper(ENG.text - 1)

    def test_word_next_to_the_sum(self):
        self.tamper(ENG.sum_at() - 4)

    def test_size_change(self):
        with self.assertRaises(G.EngineError):
            G.check_diff(ENG, ENG.image() + b'\0')

    def test_row1_required(self):
        with self.assertRaises(G.EngineError):
            G.apply(ENG, [None, LOOKS[1]] + [None] * (ENG.rows - 2))

    def test_gap_refused(self):
        with self.assertRaises(G.EngineError):
            G.apply(ENG, [LOOKS[0], None, LOOKS[1]] + [None] * (ENG.rows - 3))

    def test_bad_table_size(self):
        with self.assertRaises(G.EngineError):
            G.apply(ENG, rows(dict(LOOKS[0], lut=b'123')))

    def test_name_too_long(self):
        with self.assertRaises(G.EngineError):
            G.apply(ENG, rows(dict(LOOKS[0], name='X' * 13)))

    def test_name_bad_character(self):
        with self.assertRaises(G.EngineError):
            G.apply(ENG, rows(dict(LOOKS[0], name='PRO 400H\u00e9')))

    def test_line_too_long(self):
        with self.assertRaises(G.EngineError):
            G.apply(ENG, rows(dict(LOOKS[0], lines=['x' * 29, 'b', 'c'])))

    def test_byte_just_past_records(self):
        self.tamper(ENG.records + 12 * 80)

    def test_bad_icon_character(self):
        with self.assertRaises(G.EngineError):
            G.apply(ENG, rows(dict(LOOKS[0], icon='a!')))

    def test_pair_mismatch(self):
        im = G.apply(ENG, rows(LOOKS[0], dict(LOOKS[1], lut=OTHER)))
        with self.assertRaises(G.EngineError):
            G.check_pair(ENG, im, ENG.init_template())

    def test_wrong_store_sum(self):
        b = bytearray(G.apply(ENG, rows(LOOKS[0]))); b[ENG.store + 7] ^= 1
        with self.assertRaises(G.EngineError):
            G.check_store_sum(ENG, bytes(b))


P04 = G.HERE / 'engine' / 'engine-p04.json'


@unittest.skipUnless(P04.exists() and (G.ROOT / 'builds/p04-official-cn-bb-grain/ffboot.bin').exists(), 'P04 build not here')
class BaseFilm(unittest.TestCase):
    """P04 on: a base film per row (PRO Neg. Std, Classic Neg., Bleach Bypass) and the photo code of a plain film row, as data."""
    @classmethod
    def setUpClass(cls):
        cls.eng = G.Engine(P04); im = cls.eng.image()
        cls.rows = G.read_rows(cls.eng, lambda a, n: im[a:a + n])

    def test_rebuilds_p04_byte_exact(self):
        self.assertTrue(G.self_check(self.eng))
        self.assertEqual([(r['base'], r['plain']) for r in self.rows[14:]], [('Classic Neg.', True), ('Bleach Bypass', True)])

    def test_look_on_classic_neg_is_data_only(self):
        r = list(self.rows); r[2] = dict(r[2], base='Classic Neg.', plain=False)
        im = G.apply(self.eng, r)
        self.assertEqual(G.check_diff(self.eng, im), 1)
        back = G.read_rows(self.eng, lambda a, n: im[a:a + n])
        self.assertEqual((back[2]['base'], back[2]['plain']), ('Classic Neg.', False))

    def test_plain_needs_film_base_and_identity(self):
        for i, change in ((0, dict(plain=True)), (2, dict(plain=True, base='Classic Neg.'))):
            r = list(self.rows); r[i] = dict(r[i], **change)
            with self.assertRaises(G.EngineError):
                G.apply(self.eng, r)

    def test_hidden_rows_get_no_base(self):
        im = G.apply(self.eng, self.rows[14:] + [None] * 14)
        fb = self.eng.film_base
        self.assertEqual(im[fb['bases'] + 1:fb['bases'] + 3], bytes([10, 11]))
        self.assertFalse(any(im[fb['bases'] + 3:fb['bases'] + 17]))
        self.assertEqual(struct.unpack_from('<3H', im, fb['fmodes']), (0x500, 0x800, 0x900))

    def test_unknown_base_refused(self):
        r = list(self.rows); r[0] = dict(r[0], base='Velvia')
        with self.assertRaises(G.EngineError):
            G.apply(self.eng, r)

    def test_builtin_films(self):
        for slug, base in (('film-classic-neg', 'Classic Neg.'), ('film-bleach-bypass', 'Bleach Bypass')):
            k = L.get(slug)
            self.assertEqual((k['base'], k['plain'], k['table_sha256']), (base, True, G.sha256(G.identity_table())))
            self.assertEqual(L.table(slug), G.identity_table())
            G.check_text(self.eng, k['menu_name'], k['lines'])
            with self.assertRaises(ValueError):
                L.save(k)


class NoBaseOnP03(unittest.TestCase):
    def test_base_refused_without_film_base(self):
        r = [dict(name='A', lines=['a', 'b', 'c'], lut=OTHER, icon='AA', base='Classic Neg.')]
        with self.assertRaises(G.EngineError):
            G.apply(ENG, rows(*r))


class NoDat(unittest.TestCase):
    def test_app_has_no_dat_or_card_write_path(self):
        src = ''.join(p.read_text() for p in L.HERE.glob('*.py'))
        self.assertIsNone(re.search(r'FWUP|\.DAT\b|\.dat\b|/media/usb|/dev/sd|mkfs', src))


if __name__ == '__main__':
    unittest.main()
