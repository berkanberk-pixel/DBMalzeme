#!/usr/bin/env python3
"""Satır farkı ve iş anahtarı testleri."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'
sys.path.insert(0, str(ROOT))

import source_row_diff as srd  # noqa: E402


class SourceRowDiffTests(unittest.TestCase):
    def _write(self, path: Path, text: str):
        path.write_text(text, encoding='utf-8-sig')

    def test_kesif_detects_added_changed_removed(self):
        with tempfile.TemporaryDirectory() as td:
            old = Path(td) / 'old.csv'
            new = Path(td) / 'new.csv'
            self._write(old, 'Depo Kodu;Malzeme Kodu;Proje;Teslim Edilen;Verilen Malzeme Toplamı;Teslim Edilen - Verilen Fark\n'
                             'D1;M1;P1;10;2;8\n'
                             'D1;M2;P1;5;0;5\n')
            self._write(new, 'Depo Kodu;Malzeme Kodu;Proje;Teslim Edilen;Verilen Malzeme Toplamı;Teslim Edilen - Verilen Fark\n'
                             'D1;M1;P1;12;2;10\n'
                             'D1;M3;P1;1;0;1\n')
            old_info = {'files': [{'path': str(old), 'delimiter': ';', 'encoding': 'utf-8-sig', 'headerRow': 0, 'role': 'T'}]}
            new_info = {'files': [{'path': str(new), 'delimiter': ';', 'encoding': 'utf-8-sig', 'headerRow': 0, 'role': 'T'}]}
            diff = srd.diff_source_infos(old_info, new_info, 'KESIFLER')
            self.assertTrue(diff['hasChanges'])
            self.assertEqual(diff['added'], 1)
            self.assertEqual(diff['changed'], 1)
            self.assertEqual(diff['removed'], 1)
            self.assertEqual(diff['unchanged'], 0)

    def test_identical_content_no_changes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'a.csv'
            self._write(path, 'Üretim yeri;Depo yeri;Güvence Teminat Tutarı\n1000;D1;100\n')
            info = {'files': [{'path': str(path), 'delimiter': ';', 'encoding': 'utf-8-sig', 'headerRow': 0}]}
            diff = srd.diff_source_infos(info, info, 'ZMM098')
            self.assertFalse(diff['hasChanges'])
            self.assertEqual(diff['unchanged'], 1)

    def test_mb51_business_key_includes_document_identity(self):
        with tempfile.TemporaryDirectory() as td:
            old = Path(td) / 'old.csv'
            new = Path(td) / 'new.csv'
            hdr = 'Malzeme belgesi;Malzeme belgesi yılı;Malzeme belgesi kalemi;İşlem türü;Üretim yeri;Depo yeri;Malzeme;Miktar'
            self._write(old, hdr + '\nA;2024;1;311;1000;D1;M1;5\n')
            self._write(new, hdr + '\nA;2024;1;311;1000;D1;M1;5\nB;2024;1;311;1000;D1;M1;2\n')
            old_info = {'files': [{'path': str(old), 'delimiter': ';', 'encoding': 'utf-8-sig', 'headerRow': 0}]}
            new_info = {'files': [{'path': str(new), 'delimiter': ';', 'encoding': 'utf-8-sig', 'headerRow': 0}]}
            diff = srd.diff_source_infos(old_info, new_info, 'MB51')
            self.assertEqual(diff['added'], 1)
            self.assertEqual(diff['removed'], 0)
            self.assertEqual(diff['changed'], 0)


class SourceAccessStateTests(unittest.TestCase):
    def test_active_copy_keeps_app_writable_when_candidate_missing(self):
        sys.path.insert(0, str(ROOT))
        import server as srv

        cfg = {'_candidate_sources': {'ZMM048': {'files': [1]}, 'MB51': {'files': [1]}, 'MB52': {'files': [1]},
                                      'ZMM098': {'files': [1]}, 'TANIMLAR': {'files': [1]}}}
        # KESIFLER ağda yok ama merkezi aktif kopya var
        sources = {name: {'files': [{'path': 'x'}], 'origin': 'central-source-cache'} for name in srv.SOURCE_NAMES}
        engine = {'ready': True, 'building': False, 'usable': True, 'status': 'READY', 'buildId': 'B1', 'indexSourceDigest': 'd'}
        access = srv.source_access_state(cfg, sources, engine)
        self.assertTrue(access['current'])
        self.assertFalse(access['readOnly'])
        self.assertEqual(access['missing'], [])
        self.assertIn('KESIFLER', access['candidateMissing'])
        self.assertTrue(access['networkNote'])

    def test_missing_active_kesif_with_usable_index_stays_writable(self):
        """Usable local/central index must not flip salt-okunur for partial ACTIVE CSV meta."""
        import server as srv

        cfg = {'_candidate_sources': {}}
        sources = {name: {'files': [{'path': 'x'}]} for name in srv.SOURCE_NAMES if name != 'KESIFLER'}
        engine = {'ready': True, 'building': False, 'usable': True, 'status': 'READY',
                  'buildId': 'B1', 'indexSourceDigest': 'd'}
        access = srv.source_access_state(cfg, sources, engine)
        self.assertTrue(access['current'], access)
        self.assertFalse(access['readOnly'])
        self.assertEqual(access['missing'], ['KESIFLER'])
        self.assertIn('ACTIVE CSV meta eksik', access.get('networkNote') or '')

    def test_missing_active_without_usable_index_is_readonly(self):
        import server as srv

        cfg = {'_candidate_sources': {}}
        sources = {name: {'files': [{'path': 'x'}]} for name in srv.SOURCE_NAMES if name != 'KESIFLER'}
        engine = {'ready': False, 'building': False, 'usable': False, 'status': 'MISSING'}
        access = srv.source_access_state(cfg, sources, engine)
        self.assertFalse(access['current'])
        self.assertTrue(access['readOnly'])
        self.assertEqual(access['missing'], ['KESIFLER'])
        self.assertIn('Merkezi/yerel kaynak eksik', access['reason'])

    def test_stale_usable_index_keeps_app_writable(self):
        import server as srv

        cfg = {'_candidate_sources': {name: {'files': [1]} for name in srv.SOURCE_NAMES}}
        sources = {name: {'files': [{'path': 'x'}], 'origin': 'active'} for name in srv.SOURCE_NAMES}
        engine = {'ready': False, 'building': False, 'usable': True, 'status': 'STALE',
                  'buildId': 'B2', 'indexSourceDigest': 'old'}
        access = srv.source_access_state(cfg, sources, engine)
        self.assertTrue(access['current'])
        self.assertFalse(access['readOnly'])
        self.assertIn('önceki kaynaklarla', access.get('networkNote', ''))

    def test_first_index_building_with_active_rows_not_readonly(self):
        """Halit: light OK + INDEX_BUILDING → sahte salt-okunur yok."""
        import server as srv

        cfg = {'_candidate_sources': {}}
        sources = {name: {'files': [{'path': 'x'}]} for name in srv.SOURCE_NAMES}
        engine = {'ready': False, 'building': True, 'usable': False, 'status': 'REBUILDING'}
        access = srv.source_access_state(cfg, sources, engine)
        self.assertTrue(access['current'], access)
        self.assertFalse(access['readOnly'])
        self.assertEqual(access['reason'], '')
        self.assertIn('ilk kez hazırlanıyor', access.get('networkNote') or '')

    def test_building_without_sources_still_readonly(self):
        import server as srv

        cfg = {'_candidate_sources': {}}
        sources = {name: None for name in srv.SOURCE_NAMES}
        engine = {'ready': False, 'building': True, 'usable': False, 'status': 'REBUILDING'}
        access = srv.source_access_state(cfg, sources, engine)
        self.assertFalse(access['current'])
        self.assertTrue(access['readOnly'])
        self.assertIn('ilk kez hazırlanıyor', access['reason'])

    def test_building_with_usable_index_stays_writable(self):
        import server as srv

        cfg = {'_candidate_sources': {}}
        sources = {name: {'files': [{'path': 'x'}]} for name in srv.SOURCE_NAMES}
        engine = {'ready': False, 'building': True, 'usable': True, 'status': 'REBUILDING',
                  'buildId': 'B3', 'indexSourceDigest': 'd'}
        access = srv.source_access_state(cfg, sources, engine)
        self.assertTrue(access['current'])
        self.assertFalse(access['readOnly'])
        self.assertEqual(access['reason'], '')
        self.assertIn('arka planda güncelleniyor', access.get('networkNote', ''))


if __name__ == '__main__':
    unittest.main()
