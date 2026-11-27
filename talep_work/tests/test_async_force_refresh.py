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


if __name__ == '__main__':
    unittest.main()
