#!/usr/bin/env python3
"""MB51 tarih filtresi daralınca önceki satırların korunması."""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'
sys.path.insert(0, str(ROOT))

import indexed_engine as ie  # noqa: E402


HDR = ['Malzeme belgesi', 'Malzeme belgesi yılı', 'Malzeme belgesi kalemi', 'İşlem türü',
       'Üretim yeri', 'Depo yeri', 'Malzeme', 'Miktar', 'Belge tarihi']


def _write_csv(path: Path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(HDR)
        for row in rows:
            w.writerow(row)


class Mb51HistoryRetainTests(unittest.TestCase):
    def test_narrower_extract_keeps_previous_document(self):
        with tempfile.TemporaryDirectory() as td:
            app = Path(td) / 'app'
            app.mkdir()
            (app / 'CURRENT_RULES.json').write_text('{"version":"test"}', encoding='utf-8')
            data = Path(td) / 'data'
            data.mkdir()
            first = data / 'mb51_a.csv'
            second = data / 'mb51_b.csv'
            _write_csv(first, [
                ['DOC1', '2024', '1', '311', '1000', 'D1', 'M1', '5', '01.01.2024'],
                ['DOC2', '2024', '1', '311', '1000', 'D1', 'M2', '3', '02.01.2024'],
            ])
            # İkinci özet yalnız DOC2 içeriyor (tarih filtresi daralmış gibi).
            _write_csv(second, [
                ['DOC2', '2024', '1', '311', '1000', 'D1', 'M2', '3', '02.01.2024'],
            ])

            def info(path):
                return {
                    'MB51': {
                        'files': [{
                            'path': str(path), 'name': path.name, 'role': 'MB51',
                            'delimiter': ';', 'encoding': 'utf-8-sig', 'headerRow': 0,
                        }],
                        'size': path.stat().st_size, 'lastModified': 1, 'origin': 'test',
                    }
                }

            import os
            os.environ['TALEP_INDEX_ROOT'] = str(Path(td) / 'index')
            try:
                first_build = ie.build_engine(app, info(first), build_parquet=False)
                self.assertTrue(first_build.get('build_id'))
                second_build = ie.build_engine(
                    app, info(second), build_parquet=False,
                    changed_sources={'MB51'},
                    row_diffs={'MB51': {'added': 0, 'changed': 0, 'removed': 1, 'hasChanges': True}},
                )
                self.assertTrue(second_build.get('incremental'))
                self.assertGreaterEqual(int(second_build.get('retainedMb51') or 0), 1)
                db = Path(second_build['index_db'])
                with ie.connect(db) as c:
                    docs = {r[0] for r in c.execute('SELECT DISTINCT doc FROM mb51')}
                self.assertEqual(docs, {'DOC1', 'DOC2'})
            finally:
                os.environ.pop('TALEP_INDEX_ROOT', None)


if __name__ == '__main__':
    unittest.main()
