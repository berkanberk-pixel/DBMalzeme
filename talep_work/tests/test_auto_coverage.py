# -*- coding: utf-8 -*-
"""MB51 + Keşif varken kapsam teyidi otomatik olmalı."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'
sys.path.insert(0, str(ROOT))

import capacity_projection as cp  # noqa: E402


class AutoCoverageTests(unittest.TestCase):
    def test_auto_verified_when_kesif_and_mb51_present(self):
        fps = {'KESIFLER': 'aaa', 'MB51': 'bbb', 'ZMM098': 'ccc'}
        cov = cp.read_coverage(Path('/tmp/missing-kapsam.json'), fps, 'digest1', ('1000', 'Y201'))
        self.assertTrue(cov['verified'])
        self.assertTrue(cov.get('autoVerified'))
        self.assertEqual(cov['evidenceReference'], 'AUTO_MB51_KESIF')
        self.assertEqual(cov['discoveryBasis'], 'ACTUAL_INCLUDED_PENDING_EXCLUDED')

    def test_missing_mb51_blocks_auto(self):
        fps = {'KESIFLER': 'aaa', 'MB51': '', 'ZMM098': 'ccc'}
        cov = cp.read_coverage(Path('/tmp/missing-kapsam.json'), fps, 'digest1', ('1000', 'Y201'))
        self.assertFalse(cov['verified'])
        self.assertIn('MB51', cov.get('reason', ''))

    def test_missing_kesif_blocks_auto(self):
        fps = {'KESIFLER': '', 'MB51': 'bbb', 'ZMM098': 'ccc'}
        cov = cp.read_coverage(Path('/tmp/missing-kapsam.json'), fps, 'digest1', ('1000', 'Y201'))
        self.assertFalse(cov['verified'])
        self.assertIn('Keşif', cov.get('reason', ''))

    def test_require_coverage_accepts_auto(self):
        fps = {'KESIFLER': 'aaa', 'MB51': 'bbb'}
        cov = cp.read_coverage(Path('nope'), fps, 'd1', ('1000', 'D1'))
        cp.require_coverage(cov, fps, 'd1', ('1000', 'D1'))


if __name__ == '__main__':
    unittest.main()
