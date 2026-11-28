#!/usr/bin/env python3
"""F-002 retarget + F-003 keyed row delta (ZMM098)."""
from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'
sys.path.insert(0, str(ROOT))

import indexed_engine as ie  # noqa: E402
import source_row_diff as srd  # noqa: E402


def _write_z98(path: Path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(['Üretim yeri', 'Depo yeri', 'Güvence Teminat Tutarı'])
        for row in rows:
            w.writerow(row)


class IncrementalRowDeltaTests(unittest.TestCase):
    def test_zmm098_row_delta_does_not_reload_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            app = Path(td) / 'app'
            app.mkdir()
            (app / 'CURRENT_RULES.json').write_text('{"version":"test"}', encoding='utf-8')
            data = Path(td) / 'data'
            data.mkdir()
            first = data / 'z98_a.csv'
            second = data / 'z98_b.csv'
            _write_z98(first, [['1000', 'D1', '100'], ['1000', 'D2', '50']])
            _write_z98(second, [['1000', 'D1', '120'], ['1000', 'D2', '50']])

            def info(path):
                return {
                    'ZMM098': {
                        'files': [{
                            'path': str(path), 'name': path.name, 'role': '',
                            'delimiter': ';', 'encoding': 'utf-8-sig', 'headerRow': 0,
                        }],
                        'size': path.stat().st_size, 'lastModified': 1, 'origin': 'test',
                    },
                    'MB52': {
                        'files': [{
                            'path': str(path), 'name': path.name + '.mb52', 'role': '',
                            'delimiter': ';', 'encoding': 'utf-8-sig', 'headerRow': 0,
                        }],
                        'size': 1, 'lastModified': 1, 'origin': 'test',
                    },
                }

            # MB52 placeholder file so changed < all_sources (incremental gate).
            mb52_stub = data / 'mb52_stub.csv'
            with mb52_stub.open('w', encoding='utf-8-sig', newline='') as fh:
                w = csv.writer(fh, delimiter=';')
                w.writerow(['Üretim yeri', 'Depo yeri', 'Malzeme', 'Parti', 'Tahditsiz klnb.'])
                w.writerow(['1000', 'D1', 'M1', '', '1'])

            os.environ['TALEP_INDEX_ROOT'] = str(Path(td) / 'index')
            try:
                sources1 = {
                    'ZMM098': info(first)['ZMM098'],
                    'MB52': {
                        'files': [{
                            'path': str(mb52_stub), 'name': mb52_stub.name, 'role': '',
                            'delimiter': ';', 'encoding': 'utf-8-sig', 'headerRow': 0,
                        }],
                        'size': mb52_stub.stat().st_size, 'lastModified': 1, 'origin': 'test',
                    },
                }
                first_build = ie.build_engine(app, sources1, build_parquet=False)
                self.assertTrue(first_build.get('build_id'))

                old_info = sources1['ZMM098']
                new_z98 = {
                    'files': [{
                        'path': str(second), 'name': second.name, 'role': '',
                        'delimiter': ';', 'encoding': 'utf-8-sig', 'headerRow': 0,
                    }],
                    'size': second.stat().st_size, 'lastModified': 2, 'origin': 'test',
                }
                sources2 = {**sources1, 'ZMM098': new_z98}
                diff = srd.diff_source_infos(old_info, new_z98, 'ZMM098')
                self.assertTrue(diff.get('supportsRowDelta'), diff)

                second_build = ie.build_engine(
                    app, sources2, build_parquet=False,
                    changed_sources={'ZMM098'},
                    row_diffs={'ZMM098': diff},
                )
                self.assertTrue(second_build.get('incremental'))
                self.assertTrue(second_build.get('rowDelta'), second_build)
                delta_stat = second_build['sources'].get('_delta_ZMM098') or {}
                self.assertEqual(int(delta_stat.get('rows_indexed') or 0), 1, delta_stat)
                db = Path(second_build['index_db'])
                with ie.connect(db) as c:
                    rows = { (r[0], r[1]): r[2] for r in c.execute('SELECT uy,dy,main FROM zmm098') }
                self.assertEqual(rows[('1000', 'D1')], 120.0)
                self.assertEqual(rows[('1000', 'D2')], 50.0)
            finally:
                os.environ.pop('TALEP_INDEX_ROOT', None)

    def test_retarget_keeps_ready_after_no_row_change(self):
        """F-002: boş satır / aynı içerik → retarget → sourceIndexMatch True."""
        with tempfile.TemporaryDirectory() as td:
            app = Path(td) / 'app'
            app.mkdir()
            (app / 'CURRENT_RULES.json').write_text('{"version":"test"}', encoding='utf-8')
            data = Path(td) / 'data'
            data.mkdir()
            a = data / 'a.csv'
            b = data / 'b.csv'
            body = 'Üretim yeri;Depo yeri;Güvence Teminat Tutarı\n1000;D1;100\n'
            a.write_text(body, encoding='utf-8-sig')
            # Aynı satırlar + trailing blank line → fiziksel farklı, semantik aynı.
            b.write_text(body + '\n', encoding='utf-8-sig')

            def info(path):
                return {
                    'ZMM098': {
                        'files': [{
                            'path': str(path), 'name': path.name, 'role': '',
                            'delimiter': ';', 'encoding': 'utf-8-sig', 'headerRow': 0,
                        }],
                        'size': path.stat().st_size, 'lastModified': path.stat().st_mtime,
                        'origin': 'test',
                    }
                }

            os.environ['TALEP_INDEX_ROOT'] = str(Path(td) / 'index')
            try:
                built = ie.build_engine(app, info(a), build_parquet=False)
                self.assertTrue(built.get('build_id'))
                state_before = ie.active_build_state(app, info(b))
                # Fiziksel imza değişti → STALE olurdu
                self.assertFalse(state_before.get('sourceIndexMatch'), state_before)
                self.assertEqual(state_before.get('status'), 'STALE')

                ret = ie.retarget_active_signature(app, info(b))
                self.assertTrue(ret.get('retargeted'), ret)
                state_after = ie.active_build_state(app, info(b))
                self.assertTrue(state_after.get('sourceIndexMatch'), state_after)
                self.assertEqual(state_after.get('status'), 'READY')
                self.assertTrue(state_after.get('ready'))
            finally:
                os.environ.pop('TALEP_INDEX_ROOT', None)


if __name__ == '__main__':
    unittest.main()
