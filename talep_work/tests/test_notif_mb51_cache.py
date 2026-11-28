"""Hız paketi adım 2 — bildirim MB51 reconcile TTL/digest cache (her tick full değil)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'
sys.path.insert(0, str(ROOT))

import revision_runtime as rr


class BuildNotificationsMb51CacheTests(unittest.TestCase):
    def setUp(self):
        rr.reset_notification_mb51_cache()

    def test_second_tick_skips_mb51_reconcile_within_ttl(self):
        import server as srv

        csv = (
            'KontrolID,RezervasyonNo,MalzemeKodu,OnaylananMiktar,KalemKarari,IsTuru,HedefDepo,Birim\n'
            'KD-CACHE-1,1000001,5100100001,10,ONAYLA,KET,D01,AD\n'
        )
        rec = {
            'verified': True,
            'found': True,
            'status': 'MUTABIK',
            'actualQty': 10,
            'error': '',
        }
        calls = []

        def fake_reconcile(res, mat, approved, scope=None):
            calls.append((res, mat, approved))
            return dict(rec)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mat_path = root / 'KD-CACHE-1_materials.csv'
            mat_path.write_text(csv, encoding='utf-8-sig')
            with mock.patch.object(srv, 'load_record_root', return_value=root), \
                 mock.patch.object(srv, 'record_visible_paths', return_value=[mat_path]), \
                 mock.patch.object(srv, 'source_snapshot_cached', return_value=({}, {}, [])), \
                 mock.patch.object(srv, '_engine_snapshot', return_value={
                     'usable': True, 'buildId': 'b1', 'indexSourceDigest': 'idx-1',
                     'quality': {'findings': []},
                 }), \
                 mock.patch.object(srv, '_active_index_db', return_value=root / 'x.sqlite'), \
                 mock.patch.object(srv, '_mb51_reconcile', side_effect=fake_reconcile), \
                 mock.patch.object(srv, '_notif_state', return_value={'items': {}}), \
                 mock.patch.object(srv, '_save_notif_state'), \
                 mock.patch.object(srv.indexed_engine, 'connect', side_effect=AssertionError('no db')):
                srv.build_notifications(force_mb51=False)
                self.assertEqual(len(calls), 1)
                # Aynı digest + TTL içinde ikinci tick → reconcile yok
                srv.build_notifications(force_mb51=False)
                self.assertEqual(len(calls), 1)

    def test_unchanged_item_reuses_cache_when_scan_reruns(self):
        import server as srv

        csv = (
            'KontrolID,RezervasyonNo,MalzemeKodu,OnaylananMiktar,KalemKarari,IsTuru,HedefDepo,Birim\n'
            'KD-CACHE-2,1000002,5100100002,3,ONAYLA,KET,D01,AD\n'
        )
        rec = {
            'verified': True,
            'found': True,
            'status': 'MUTABIK',
            'actualQty': 3,
            'error': '',
        }
        calls = []

        def fake_reconcile(res, mat, approved, scope=None):
            calls.append((res, mat, approved))
            return dict(rec)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mat_path = root / 'KD-CACHE-2_materials.csv'
            mat_path.write_text(csv, encoding='utf-8-sig')
            engine = {
                'usable': True, 'buildId': 'b1', 'indexSourceDigest': 'idx-1',
                'quality': {'findings': []},
            }
            with mock.patch.object(srv, 'load_record_root', return_value=root), \
                 mock.patch.object(srv, 'record_visible_paths', return_value=[mat_path]), \
                 mock.patch.object(srv, 'source_snapshot_cached', return_value=({}, {}, [])), \
                 mock.patch.object(srv, '_engine_snapshot', return_value=engine), \
                 mock.patch.object(srv, '_mb51_reconcile', side_effect=fake_reconcile), \
                 mock.patch.object(srv, '_notif_state', return_value={'items': {}}), \
                 mock.patch.object(srv, '_save_notif_state'):
                srv.build_notifications(force_mb51=True)
                self.assertEqual(len(calls), 1)
                # force ile tarama tekrarlar ama item digest aynı → cache hit
                srv.build_notifications(force_mb51=True)
                self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
