"""GUI boot: progressive [1] + native splash navigationReady (Halit)."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'


class BootHandoffTests(unittest.TestCase):
    def test_app_signals_ready_before_source_load(self):
        js = (ROOT / 'app.js').read_text(encoding='utf-8')
        self.assertIn('function signalUiShellReady', js)
        boot = js[js.index('(async function boot()'):js.index('})();', js.index('(async function boot()'))]
        ready_at = boot.index('signalUiShellReady()')
        load_at = boot.index('loadSources({initial:true')
        self.assertLess(ready_at, load_at, 'talep-ui-ready must precede loadSources')

    def test_boot_is_progressive_not_literal_full_load(self):
        js = (ROOT / 'app.js').read_text(encoding='utf-8')
        boot = js[js.index('(async function boot()'):js.index('})();', js.index('(async function boot()'))]
        self.assertIn('forceScan:false', boot)
        self.assertNotIn('forceScan:true', boot)
        self.assertIn('Progressive', boot)
        self.assertIn('scheduleBackgroundSourceSync', js)
        self.assertIn("qs.push('light=1')", js)
        self.assertIn('BOOT_PRIORITY_SOURCES', js)
        self.assertIn('LAZY_BOOK_SOURCES', js)

    def test_show_loading_issue_not_fatal_after_handoff(self):
        js = (ROOT / 'app.js').read_text(encoding='utf-8')
        fn = js[js.index('function showLoadingIssue'):js.index('function hideLoading')]
        self.assertIn('if(!uiShellReadyPosted)', fn)
        self.assertIn('talep-ui-boot-error', fn)

    def test_launcher_timeout_at_least_15_minutes(self):
        ps1 = (ROOT / 'START_GUI.ps1').read_text(encoding='utf-8')
        m = re.search(r'TotalMinutes\s*-gt\s*(\d+)', ps1)
        self.assertIsNotNone(m)
        self.assertGreaterEqual(int(m.group(1)), 15)

    def test_workspace_opens_on_navigation_without_boot_page_ready(self):
        """Native splash must not wait for talep-ui-ready / source sync."""
        ps1 = (ROOT / 'START_GUI.ps1').read_text(encoding='utf-8')
        open_fn = ps1[ps1.index('function Open-TalepWorkspace'):ps1.index('$window.Add_Shown({$window.Width')]
        self.assertIn('!$script:navigationReady', open_fn)
        self.assertNotIn('!$script:bootPageReady', open_fn)
        self.assertIn('NavigationCompleted', ps1)

    def test_api_files_supports_light(self):
        py = (ROOT / 'server.py').read_text(encoding='utf-8')
        files_block = py[py.index("if route == '/api/files'"):py.index("if route == '/api/file'")]
        self.assertIn("light=str((q.get('light')", files_block)
        self.assertIn('source_versions={} if light else', files_block)
        self.assertIn('_active_only_light_snapshot', py)
        self.assertIn('source_snapshot_cached(force=force, light=light)', files_block)

    def test_boot_snapshot_has_timeout_and_fallback(self):
        js = (ROOT / 'app.js').read_text(encoding='utf-8')
        self.assertIn('function emptyBootSnapshot', js)
        self.assertIn('light?12000', js)
        self.assertIn('Boot snapshot fallback', js)
        # Regression: duplicate const diag crashed the whole script (0% hang).
        self.assertIn("const diagEl=$('#diagnostics')", js)
        start = js.index('function renderCommon()')
        end = js.index('\nfunction ', start + 10)
        render = js[start:end]
        self.assertEqual(render.count('const diag='), 1)
        self.assertIn('const diagEl=', render)

    def test_light_snapshot_skips_unc_scan(self):
        import server as srv
        cfg, sources, missing = srv._active_only_light_snapshot()
        self.assertTrue(cfg.get('_light_snapshot'))
        self.assertIsInstance(sources, dict)
        self.assertEqual(cfg.get('_candidate_sources'), {})


if __name__ == '__main__':
    unittest.main()
