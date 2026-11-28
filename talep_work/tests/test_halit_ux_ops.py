"""Halit UX: kesin kayıt CTA, health panel scope, ops terminal, disconnect lock, theme help."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'


class HalitUxOpsTests(unittest.TestCase):
    def test_unapproved_mb51_opens_reservation_for_final_record(self):
        py = (ROOT / 'server.py').read_text(encoding='utf-8')
        self.assertIn("'action':'OPEN_RESERVATION'", py)
        self.assertIn('Onaysız kalemde MB51', py)
        self.assertIn('Kesin kayıt:', py)
        js = (ROOT / 'app.js').read_text(encoding='utf-8')
        self.assertIn('function openReservationForFinalRecord', js)
        self.assertIn("OPEN_RESERVATION", js)
        self.assertIn('Kesin Kayıt (CSV)', js)

    def test_source_health_panel_only_on_data_center(self):
        js = (ROOT / 'app.js').read_text(encoding='utf-8')
        self.assertIn('function syncSourceHealthPanelVisibility', js)
        self.assertIn('details.hidden=!isDataCenterActive()', js)

    def test_diag_console_ctrl_q_replaces_bottom_ops_terminal(self):
        html = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('id="sourceOpsTerminal"', html)
        self.assertIn('id="diagConsole"', html)
        self.assertIn('id="diagTaskList"', html)
        self.assertIn('id="diagLog"', html)
        js = (ROOT / 'app.js').read_text(encoding='utf-8')
        self.assertIn('function logSourceOp', js)
        self.assertIn('function initDiagConsole', js)
        self.assertIn('function toggleDiagConsole', js)
        self.assertIn("toLowerCase()==='q'", js)
        self.assertIn('function buildDiagExportText', js)
        self.assertNotIn('initSourceOpsTerminal', js)
        css = (ROOT / 'styles.css').read_text(encoding='utf-8')
        self.assertIn('.diag-console', css)
        self.assertNotIn('.source-ops-terminal{', css)

    def test_service_disconnect_does_not_force_source_readonly(self):
        js = (ROOT / 'app.js').read_text(encoding='utf-8')
        self.assertNotIn("reason:'Yerel servis bağlantısı kesildi.'", js)
        desk = (ROOT / 'desktop-status.js').read_text(encoding='utf-8')
        self.assertIn('FAIL_LOCK', desk)
        self.assertIn('failCount < FAIL_LOCK', desk)

    def test_theme_help_explains_visual_only(self):
        helpj = (ROOT / 'help-content.json').read_text(encoding='utf-8')
        self.assertIn('"theme"', helpj)
        self.assertIn('Şebeke Atlası', helpj)
        self.assertIn('arayuz-temasi', helpj)
        gl = (ROOT / 'webgl-themes28l.js').read_text(encoding='utf-8')
        self.assertIn('data-help-key="theme"', gl)
        self.assertIn('Yalnızca görsel görünüm', gl)


if __name__ == '__main__':
    unittest.main()
