"""Light /api/files must not Path.exists()/stat UNC — avoids BOOT_TIMEOUT + false missing."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'


class LightSnapshotNoUncTests(unittest.TestCase):
    def setUp(self):
        import sys
        sys.path.insert(0, str(ROOT))
        import server as srv
        self.srv = srv
        self._tmp = tempfile.TemporaryDirectory()
        self.app = Path(self._tmp.name)
        self.shadow = self.app / 'data_v2' / '03_ACTIVE' / '_SOURCE_FILES'
        self.shadow.mkdir(parents=True)
        self.active_state = self.app / 'data_v2' / '07_AUDIT' / 'active_source_state.json'
        self.active_state.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_path_is_unc(self):
        self.assertTrue(self.srv._path_is_unc(r'\\cedas.com\share\file.csv'))
        self.assertTrue(self.srv._path_is_unc('//cedas.com/share/file.csv'))
        self.assertFalse(self.srv._path_is_unc('/tmp/local.csv'))

    def test_light_deserialize_skips_unc_exists(self):
        unc = r'\\cedas.com\paylasim\never-probe\ZMM048.csv'
        rec = {
            'files': [{
                'name': 'ZMM048.csv', 'path': unc, 'size': 100, 'lastModified': 1700000000000,
                'role': 'ZMM048',
            }],
            'acceptedDigest': 'x',
        }
        exists_calls = []

        real_exists = Path.exists

        def tracking_exists(self):
            exists_calls.append(str(self))
            if str(self).startswith('\\\\') or str(self).startswith('//'):
                raise AssertionError('UNC Path.exists() must not run on light path: ' + str(self))
            return real_exists(self)

        with mock.patch.object(Path, 'exists', tracking_exists):
            info = self.srv._deserialize_source_info('ZMM048', rec, light=True)
        self.assertIsNotNone(info)
        self.assertEqual(info['files'][0]['name'], 'ZMM048.csv')
        self.assertTrue(all(not (c.startswith('\\\\') or c.startswith('//')) for c in exists_calls))

    def test_light_prefers_local_shadow(self):
        local = self.shadow / 'TANIMLAR' / 'tanim.csv'
        local.parent.mkdir(parents=True)
        local.write_text('a;b\n1;2\n', encoding='utf-8')
        rec = {
            'files': [{
                'name': 'tanim.csv',
                'path': r'\\cedas.com\share\tanim.csv',
                'size': 1, 'lastModified': 1, 'role': 'TANIMLAR',
            }],
        }
        with mock.patch.object(self.srv, 'SOURCE_ACTIVE_SHADOW_ROOT', self.shadow):
            info = self.srv._deserialize_source_info('TANIMLAR', rec, light=True)
        self.assertIsNotNone(info)
        self.assertEqual(Path(info['files'][0]['path']), local)
        self.assertIn('shadow', info['files'][0]['origin'])

    def test_source_snapshot_cached_light_not_blocked_by_managed_lock(self):
        """Managed UNC scan must not hold _SNAPSHOT_LOCK; light returns while scan runs."""
        started = threading.Event()
        release = threading.Event()

        def slow_managed():
            started.set()
            release.wait(timeout=5)
            return ({'_light_snapshot': False}, {}, [])

        with mock.patch.object(self.srv, 'managed_source_snapshot', side_effect=slow_managed):
            with mock.patch.object(self.srv, '_active_only_light_snapshot', return_value=({'_light_snapshot': True}, {'TANIMLAR': {'name': 'x'}}, [])):
                self.srv.invalidate_source_snapshot()
                t = threading.Thread(target=lambda: self.srv.source_snapshot_cached(force=True), daemon=True)
                t.start()
                self.assertTrue(started.wait(2), 'managed scan should start')
                t0 = time.time()
                cfg, sources, missing = self.srv.source_snapshot_cached(force=False, light=True)
                elapsed = time.time() - t0
                release.set()
                t.join(timeout=3)
        self.assertLess(elapsed, 1.0, f'light blocked for {elapsed:.2f}s')
        self.assertTrue(cfg.get('_light_snapshot'))
        self.assertIn('TANIMLAR', sources)

    def test_usable_index_not_readonly_when_active_csv_missing(self):
        access = self.srv.source_access_state(
            {'_candidate_sources': {}},
            {},
            {'usable': True, 'ready': True, 'building': False, 'status': 'READY', 'buildId': 'b1'},
        )
        self.assertTrue(access['current'], access)
        self.assertIn('ACTIVE CSV meta eksik', access.get('networkNote') or '')


if __name__ == '__main__':
    unittest.main()
