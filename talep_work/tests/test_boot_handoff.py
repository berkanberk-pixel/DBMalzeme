"""GUI boot: talep-ui-ready must not wait for UNC full load (Halit 5dk timeout)."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'


class BootHandoffTests(unittest.TestCase):
    def test_app_signals_ready_before_full_load(self):
        js = (ROOT / 'app.js').read_text(encoding='utf-8')
        self.assertIn('function signalUiShellReady', js)
        boot = js[js.index('(async function boot()'):js.index('})();', js.index('(async function boot()'))]
        ready_at = boot.index('signalUiShellReady()')
        load_at = boot.index('loadSources({initial:true')
        self.assertLess(ready_at, load_at, 'talep-ui-ready must precede full loadSources')

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


if __name__ == '__main__':
    unittest.main()
