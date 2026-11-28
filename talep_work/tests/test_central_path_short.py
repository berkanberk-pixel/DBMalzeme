"""Merkezi kaynak kopyası kısa yol ve eski düzen uyumu."""
import hashlib
import tempfile
import unittest
from pathlib import Path


class CentralPathShortTests(unittest.TestCase):
    def test_blob_rel_uses_16_hex_not_full_sha(self):
        import server as srv

        digest = 'b0a6f5a1f0f504495228ea947b6628b6552e4caa2809fcebad8697fa84dc63b2'
        rel = srv._central_blob_rel(digest, 'MB52.csv')
        self.assertEqual(rel, Path('dosyalar') / 'b0a6f5a1f0f50449.csv')
        unc = (
            r'\\cedas.com\paylasim\GM_Planlama_Tesis_Direktorlugu'
            r'\MALZEME YÖNETİMİ MÜDÜRLÜĞÜ\3 - Müdürlük Ortak Alan'
            r'\1-Ortak Döküman Alanı\8-Talep Kontrol\0-Database'
            r'\KAYNAK_VERILERI\MB52'
        )
        full = str(Path(unc) / rel)
        tmp = str(Path(unc) / 'dosyalar' / ('a' * 16 + '.next'))
        self.assertLess(len(full), 240)
        self.assertLess(len(tmp), 240)
        legacy_tmp = str(Path(unc) / 'dosyalar' / digest / ('a' * 32 + '.next'))
        self.assertGreater(len(legacy_tmp), 260)

    def test_cache_writes_short_layout_and_reads_legacy(self):
        import server as srv

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'KAYNAK_VERILERI'
            src = Path(tmp) / 'MB52.csv'
            payload = 'a;b\n1;2\n'
            src.write_text(payload, encoding='utf-8')
            digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
            info = {
                'files': [{
                    'path': str(src),
                    'name': 'MB52.csv',
                    'role': '',
                    'sheet': '',
                    'delimiter': ';',
                    'encoding': 'utf-8',
                    'headerRow': 0,
                    'format': 'csv',
                }]
            }
            # Seed legacy long layout
            legacy = root / 'MB52' / 'dosyalar' / digest / 'MB52.csv'
            legacy.parent.mkdir(parents=True)
            legacy.write_text(payload, encoding='utf-8')
            found = srv._resolve_central_blob(root / 'MB52', digest, 'MB52.csv', len(payload.encode()))
            self.assertEqual(found, legacy)

            cached = srv._cache_central_source(root, 'MB52', info)
            short = root / 'MB52' / 'dosyalar' / f'{digest[:16]}.csv'
            self.assertTrue(short.is_file())
            self.assertEqual(Path(cached['files'][0]['path']), short)
            self.assertEqual(cached['files'][0]['sha256'], digest)

            srv._publish_central_source(root, 'MB52', cached)
            loaded = srv._central_source_info(root, 'MB52')
            self.assertIsNotNone(loaded)
            self.assertEqual(Path(loaded['files'][0]['path']), short)


if __name__ == '__main__':
    unittest.main()
