"""Üst klasör kaynak tarama ve çakışma seçimi."""
import tempfile
import time
import unittest
from pathlib import Path


MB52_CSV = "Üretim yeri;Depo yeri;Malzeme;Tahditsiz klnb.;Temel ölçü birimi\n6510;Y206;5100144001;10;ADT\n"
ZMM048_CSV = (
    "Nakil rezervasyonu;Malzeme;Kaynak ÜY;Kaynak Depo;Hedef ÜY;Hedef Depo;Miktar;Birim\n"
    "100;5100144001;6510;A01;6510;Y206;1;ADT\n"
)


class ParentSourceScanTests(unittest.TestCase):
    def test_choose_latest_prefers_newer_then_parent_lane(self):
        import server as srv

        older = {'origin': 'external', 'mtime_ns': 100, 'confidence': 90, 'size': 50,
                 'source_lane': 'corporate-parent'}
        newer_app = {'origin': 'external', 'mtime_ns': 200, 'confidence': 80, 'size': 40,
                     'source_lane': 'talep-kontrol'}
        self.assertIs(srv._choose_latest([older, newer_app]), newer_app)

        same_mtime_parent = {'origin': 'external', 'mtime_ns': 200, 'confidence': 80, 'size': 40,
                             'source_lane': 'corporate-parent'}
        same_mtime_app = {'origin': 'external', 'mtime_ns': 200, 'confidence': 80, 'size': 40,
                          'source_lane': 'talep-kontrol'}
        self.assertIs(srv._choose_latest([same_mtime_app, same_mtime_parent]), same_mtime_parent)

    def test_normalize_folder_map_accepts_both_shapes(self):
        import server as srv

        inverted = srv._normalize_folder_map(
            {'MB51': '2-MB51', 'ZMM048': '7-ZMM048'}, srv.PARENT_SOURCE_FOLDERS)
        self.assertEqual(inverted['2-MB51'], 'MB51')
        self.assertEqual(inverted['7-ZMM048'], 'ZMM048')

        direct = srv._normalize_folder_map(
            {'2-MB51': 'MB51'}, srv.PARENT_SOURCE_FOLDERS)
        self.assertEqual(direct['2-MB51'], 'MB51')

    def test_scan_picks_parent_when_newer(self):
        import server as srv

        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / '1-Ortak Belge'
            app = parent / '8-Talep Kontrol'
            (app / '3-MB52').mkdir(parents=True)
            (parent / '3-MB52').mkdir(parents=True)
            app_file = app / '3-MB52' / 'MB52.csv'
            parent_file = parent / '3-MB52' / 'MB52_parent.csv'
            app_file.write_text(MB52_CSV, encoding='utf-8')
            time.sleep(0.02)
            parent_file.write_text(MB52_CSV, encoding='utf-8')

            all_scan = []
            srv._scan_mapped_folders(all_scan, {'3-MB52': 'MB52'}, app, False, 0.5, 'talep-kontrol')
            srv._scan_mapped_folders(all_scan, {'3-MB52': 'MB52'}, parent, False, 0.5, 'corporate-parent')
            classified = [c for c in all_scan if c.get('classified') and c.get('source') == 'MB52']
            self.assertGreaterEqual(len(classified), 2)
            pick = srv._choose_latest(classified)
            self.assertEqual(pick.get('source_lane'), 'corporate-parent')
            self.assertEqual(Path(pick['path']).name, 'MB52_parent.csv')

    def test_defaults_use_cedas_unc(self):
        import server as srv

        self.assertTrue(srv.DEFAULT_EXTERNAL_ROOT.startswith('\\\\cedas.com\\'))
        self.assertTrue(srv.DEFAULT_EXTERNAL_ROOT.endswith('\\8-Talep Kontrol'))
        self.assertIn('7-ZMM048', srv.PARENT_SOURCE_FOLDERS)
        self.assertEqual(srv.PARENT_SOURCE_FOLDERS['5-ZMM98'], 'ZMM098')


if __name__ == '__main__':
    unittest.main()
