"""Force /api/files must not block on UNC — async refresh + no poll salt-okunur."""
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'
sys.path.insert(0, str(ROOT))


class AsyncForceRefreshTests(unittest.TestCase):
    def test_async_force_helper_schedules_pipeline(self):
        import server as srv
        from unittest import mock
        scheduled = {}

        def fake_schedule(**kwargs):
            scheduled.update(kwargs)
            return True

        with mock.patch.object(srv, '_schedule_managed_snapshot_refresh', side_effect=fake_schedule):
            with mock.patch.object(srv, '_active_only_light_snapshot', return_value=(
                {'_light_snapshot': True}, {'TANIMLAR': {'name': 't'}}, []
            )):
                srv.invalidate_source_snapshot()
                cfg, sources, missing = srv._async_force_snapshot_response()
        self.assertTrue(cfg.get('_async_refresh'))
        self.assertIn('TANIMLAR', sources)
        self.assertTrue(scheduled.get('with_accepts'))
        self.assertTrue(scheduled.get('with_rebuild'))

    def test_missing_engine_with_active_rows_not_readonly(self):
        import server as srv
        cfg = {'_candidate_sources': {}}
        sources = {name: {'files': [{'path': 'x'}]} for name in srv.SOURCE_NAMES}
        engine = {'ready': False, 'building': False, 'usable': False, 'status': 'MISSING'}
        access = srv.source_access_state(cfg, sources, engine)
        self.assertTrue(access['current'], access)
        self.assertFalse(access['readOnly'])
        self.assertIn('MISSING', access.get('networkNote') or '')

    def test_app_poll_does_not_force_refresh_or_salt_on_timeout(self):
        js = (ROOT / 'app.js').read_text(encoding='utf-8')
        self.assertIn("/api/files?monitor=1&ts=", js)
        self.assertNotIn("/api/files?refresh=1&monitor=1", js)
        poll = js[js.index('async function pollSourceUpdateStatus'):js.index('async function sourceUpdateChoice')]
        self.assertNotIn("applySourceAccess({current:false,reason:'Kaynak güncelliği doğrulanamadı:", poll)
        self.assertIn('asyncRefresh', js)
        self.assertIn('syncPending', js)

    def test_api_files_force_always_async(self):
        """refresh=1 (force) must not sync-scan UNC on the HTTP thread."""
        py = (ROOT / 'server.py').read_text(encoding='utf-8')
        # Handler: any force → _async_force_snapshot_response
        self.assertIn('if force:', py)
        self.assertIn('_async_force_snapshot_response()', py)
        # Accept path must not call source_snapshot_cached(force=True) after ACTIVE
        accept = py[py.index('def _source_update_choice_locked'):py.index('def auto_accept_pending_sources')]
        self.assertNotIn('source_snapshot_cached(force=True)', accept)
        self.assertIn('source_snapshot_cached(force=False, light=True)', accept)
        self.assertIn('_schedule_managed_snapshot_refresh', accept)

    def test_light_force_schedules_background_not_managed_sync(self):
        import server as srv
        from unittest import mock
        scheduled = {}

        def fake_schedule(**kwargs):
            scheduled.update(kwargs)
            return True

        with mock.patch.object(srv, '_schedule_managed_snapshot_refresh', side_effect=fake_schedule):
            with mock.patch.object(srv, '_active_only_light_snapshot', return_value=(
                {'_light_snapshot': True}, {'TANIMLAR': {'name': 't'}}, []
            )):
                with mock.patch.object(srv, 'managed_source_snapshot') as managed:
                    srv.invalidate_source_snapshot()
                    cfg, sources, missing = srv.source_snapshot_cached(force=True, light=True)
        self.assertTrue(cfg.get('_light_snapshot'))
        self.assertTrue(scheduled.get('with_accepts'))
        managed.assert_not_called()


if __name__ == '__main__':
    unittest.main()
