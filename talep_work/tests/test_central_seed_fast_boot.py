"""Hız paketi adım 5: 0-Database/KAYNAK_INDEKS seed → local Index usable without cold rebuild."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'
sys.path.insert(0, str(ROOT))

import central_index_snapshot as cis  # noqa: E402
import indexed_engine as ie  # noqa: E402
import test_central_index_snapshot as base  # noqa: E402


class CentralSeedFastBootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = self.root / 'app'
        self.app.mkdir()
        self.shared = self.root / '0-Database'
        self.shared.mkdir()
        os.environ['TALEP_INDEX_ROOT'] = str(self.root / 'IndexA')
        cis._SEED_ONCE_DONE.clear()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop('TALEP_INDEX_ROOT', None)
        cis._SEED_ONCE_DONE.clear()

    def test_seed_yields_usable_engine_state(self):
        base._make_local_build(self.app, built_at='2026-11-28T15:00:00',
                               digest='c' * 64)
        self.assertTrue(cis.publish_central_snapshot(self.app, self.shared).get('published'))

        os.environ['TALEP_INDEX_ROOT'] = str(self.root / 'IndexB')
        app2 = self.root / 'app2'
        app2.mkdir()
        seed = cis.ensure_seeded_once(app2, self.shared)
        self.assertTrue(seed.get('seeded'), seed)

        # Empty sources → STALE but usable (fast boot); no need for UNC rebuild.
        state = ie.active_build_state(app2, {})
        self.assertTrue(state.get('usable'), state)
        self.assertTrue(state.get('seededFromCentral'), state)
        self.assertIn(state.get('status'), ('READY', 'STALE'))

    def test_server_skips_rebuild_when_seeded_usable(self):
        py = (ROOT / 'server.py').read_text(encoding='utf-8')
        prepare = py[py.index('def _initial_engine_prepare'):py.index('def _integrity_scheduler')]
        # Order: seed before sleep; usable → return (no cold rebuild).
        seed_at = prepare.index('_ensure_central_index_seed()')
        sleep_at = prepare.index('time.sleep(0.8)')
        usable_at = prepare.index("if engine.get('usable'):")
        self.assertLess(seed_at, sleep_at)
        self.assertLess(sleep_at, usable_at)
        rebuild_at = prepare.index('_start_engine_rebuild_background')
        self.assertLess(usable_at, rebuild_at)

    def test_no_shared_writable_sqlite_in_module_contract(self):
        mod = (ROOT / 'central_index_snapshot.py').read_text(encoding='utf-8')
        self.assertIn('yazılabilir ortak SQLite YOK', mod)
        self.assertIn("'writable_shared_sqlite': False", mod)
        self.assertIn('fast_boot', mod)
        self.assertIn('ensure_seeded_once', mod)


if __name__ == '__main__':
    unittest.main()
