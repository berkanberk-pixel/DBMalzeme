"""Halit revizyon politikaları — birim testleri (tur 1/2 ortak)."""
import tempfile
import time
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'
sys.path.insert(0, str(ROOT))

import revision_runtime as rr


class ScanDepthTests(unittest.TestCase):
    def test_max_depth_skips_deep_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'a.csv').write_text('x', encoding='utf-8')
            sub = root / 'sub'
            sub.mkdir()
            (sub / 'b.csv').write_text('x', encoding='utf-8')
            deep = sub / 'deep'
            deep.mkdir()
            (deep / 'c.csv').write_text('x', encoding='utf-8')

            flat = rr.iter_candidates_limited(root, False, 1)
            self.assertEqual({p.name for p in flat}, {'a.csv'})

            d1 = rr.iter_candidates_limited(root, True, 1)
            self.assertEqual({p.name for p in d1}, {'a.csv', 'b.csv'})

            d2 = rr.iter_candidates_limited(root, True, 2)
            self.assertEqual({p.name for p in d2}, {'a.csv', 'b.csv', 'c.csv'})


class MonitorStampTests(unittest.TestCase):
    def setUp(self):
        rr.reset_monitor_stamp_cache()

    def test_unchanged_within_ttl(self):
        sources = {'MB52': {'size': 10, 'lastModified': 1, 'files': [{'name': 'a.csv', 'size': 10, 'lastModified': 1, 'role': ''}]}}
        u1, s1 = rr.monitor_stamp_unchanged(sources, ttl_sec=60)
        self.assertFalse(u1)
        u2, s2 = rr.monitor_stamp_unchanged(sources, ttl_sec=60)
        self.assertTrue(u2)
        self.assertEqual(s1, s2)
        sources2 = {'MB52': {'size': 11, 'lastModified': 2, 'files': [{'name': 'a.csv', 'size': 11, 'lastModified': 2, 'role': ''}]}}
        u3, _ = rr.monitor_stamp_unchanged(sources2, ttl_sec=60)
        self.assertFalse(u3)


class DiagnosisTests(unittest.TestCase):
    def test_diagnosis_includes_engine_and_release(self):
        access = rr.diagnose_source_access(
            {'current': False, 'reason': 'Merkezi/yerel kaynak eksik: MB51', 'missing': ['MB51'], 'checkedAt': 't'},
            {'status': 'FAILED', 'usable': False, 'ready': False, 'building': False, 'lastError': 'x'},
            release_id='rel-1', app_version='1.0.4', app_build='b')
        d = access['diagnosis']
        self.assertEqual(d['reasonCode'], 'ACTIVE_MISSING')
        self.assertIn('MB51', d['missing'])
        self.assertEqual(d['releaseId'], 'rel-1')
        self.assertIn('sourceAccess', d['logLine'])


class FreshnessTests(unittest.TestCase):
    def test_warn_over_24h(self):
        health = {'sources': [
            {'source': 'MB52', 'age_hours': 30, 'health': 'WARNING'},
            {'source': 'MB51', 'age_hours': 2, 'health': 'NORMAL'},
        ]}
        warns = rr.freshness_warnings(health, 24)
        self.assertEqual(len(warns), 1)
        self.assertEqual(warns[0]['source'], 'MB52')


class SilentAcceptTests(unittest.TestCase):
    def test_skips_deferred_and_calls_accept(self):
        called = []
        def accept(logical, choice, actor):
            called.append((logical, choice, actor))
            return {'status': 'ACTIVE', 'source': logical}
        pending = [
            {'source': 'MB52', 'deferred': False},
            {'source': 'MB51', 'deferred': True},
            {'source': 'ZMM048', 'deferred': False},
        ]
        results = rr.run_silent_active_accepts(pending, accept)
        self.assertEqual(len(results), 2)
        self.assertEqual({r['source'] for r in results}, {'MB52', 'ZMM048'})
        self.assertTrue(all(r['ok'] for r in results))
        self.assertEqual(called[0][2], 'SYSTEM_AUTO_ACCEPT')


class Mb51LazyTests(unittest.TestCase):
    def setUp(self):
        rr.reset_notification_mb51_cache()

    def test_ttl_gate(self):
        self.assertTrue(rr.should_run_mb51_notification_scan(force=False, ttl_sec=100))
        self.assertFalse(rr.should_run_mb51_notification_scan(force=False, ttl_sec=100))
        self.assertTrue(rr.should_run_mb51_notification_scan(force=True, ttl_sec=100))


class Mb51RealizedTests(unittest.TestCase):
    def test_realized_rules(self):
        self.assertFalse(rr.mb51_realized({'verified': True, 'found': True, 'status': 'KONTROL_EDILEMEDI', 'actualQty': 5}))
        self.assertFalse(rr.mb51_realized({'verified': True, 'found': False, 'status': 'OK', 'actualQty': 5}))
        self.assertTrue(rr.mb51_realized({'verified': True, 'found': True, 'status': 'ESLESTI', 'actualQty': 3}))
        self.assertTrue(rr.is_tesis_work('TESİS'))
        self.assertFalse(rr.is_tesis_work('KET'))


class Mb51AbsoluteKesinTests(unittest.TestCase):
    """[3] Tesis hariç MB51 mutlak → otomatik kesin kayıt; farkta MB51 kazanır."""

    def test_tesis_never_auto_final(self):
        rec = {'verified': True, 'found': True, 'status': 'FIILI_MIKTAR_FARKI', 'actualQty': 7}
        self.assertFalse(rr.auto_final_eligible(True, rec))
        self.assertTrue(rr.auto_final_eligible(False, rec))

    def test_mb51_wins_on_qty_diff(self):
        row = {'MalzemeKodu': 'M1', 'OnaylananMiktar': 10, 'Miktar': 10, 'KalemKarari': 'ONAYLA'}
        rec = {'verified': True, 'found': True, 'status': 'FIILI_MIKTAR_FARKI', 'actualQty': 7}
        out = rr.apply_mb51_absolute(row, rec)
        self.assertEqual(out['OnaylananMiktar'], 7)
        self.assertTrue(out.get('MB51MutlakUygulandi'))
        self.assertIn('MB51_MUTLAK', out.get('KontrolNotu') or '')
        self.assertEqual(out['MB51FiiliMiktar'], 7)
        # orijinal satır değişmez
        self.assertEqual(row['OnaylananMiktar'], 10)

    def test_no_override_when_matched(self):
        row = {'MalzemeKodu': 'M1', 'OnaylananMiktar': 5, 'KalemKarari': 'ONAYLA'}
        rec = {'verified': True, 'found': True, 'status': 'MUTABIK', 'actualQty': 5}
        out = rr.apply_mb51_absolute(row, rec)
        self.assertEqual(out['OnaylananMiktar'], 5)
        self.assertFalse(out.get('MB51MutlakUygulandi'))

    def test_not_realized_left_untouched(self):
        row = {'MalzemeKodu': 'M1', 'OnaylananMiktar': 4}
        rec = {'verified': True, 'found': False, 'status': 'MB51_BEKLENIYOR', 'actualQty': 0}
        out = rr.apply_mb51_absolute(row, rec)
        self.assertEqual(out['OnaylananMiktar'], 4)
        self.assertNotIn('MB51MutlakUygulandi', out)


class ServerWireTests(unittest.TestCase):
    def test_iter_candidates_uses_depth(self):
        import server as srv
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'top.csv').write_text('a', encoding='utf-8')
            nested = root / 'n' / 'deep'
            nested.mkdir(parents=True)
            (nested / 'deep.csv').write_text('a', encoding='utf-8')
            found = srv.iter_candidates(root, True, max_depth=1)
            names = {p.name for p in found}
            self.assertIn('top.csv', names)
            self.assertNotIn('deep.csv', names)

    def test_config_defaults_and_version(self):
        import server as srv
        cfg = srv.load_config()
        self.assertTrue(cfg.get('silent_active_accept'))
        self.assertTrue(cfg.get('auto_final_record'))
        self.assertEqual(int(cfg.get('scan_max_depth')), 1)
        self.assertEqual(srv.APP_VERSION, '1.0.4')

    def test_source_access_diagnosis_attached(self):
        import server as srv
        access = srv.source_access_state(
            {'_candidate_sources': {}},
            {},
            {'usable': False, 'ready': False, 'building': True, 'status': 'REBUILDING'},
        )
        self.assertIn('diagnosis', access)
        self.assertEqual(access['diagnosis']['reasonCode'], 'ACTIVE_MISSING')


if __name__ == '__main__':
    unittest.main()
