#!/usr/bin/env python3
"""Kurumsal keşif başlıkları: Depo Kodu;Grup No;Grup Tanımı;Yüklenici;Proje;Malzeme Kodu;Keşif"""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'
sys.path.insert(0, str(ROOT))

import indexed_engine as ie  # noqa: E402
import server as srv  # noqa: E402


CANON = ['Depo Kodu', 'Grup No', 'Grup Tanımı', 'Yüklenici', 'Proje', 'Malzeme Kodu', 'Keşif']


class KesifCanonicalHeaderTests(unittest.TestCase):
    def test_signature_accepts_canonical_headers(self):
        headers = {_norm for _norm in (srv._norm_header(h) for h in CANON)}
        # _signature_score expects set of normalized headers from _best_header path
        header_set = {srv._norm_header(h) for h in CANON}
        sig = next(s for s in srv.SIGNATURES if s['source'] == 'KESIFLER')
        score = srv._signature_score(header_set, sig)
        self.assertGreaterEqual(score, 0.72)

    def test_insert_kesif_reads_only_kesif_qty(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'kesif.csv'
            with path.open('w', encoding='utf-8-sig', newline='') as fh:
                w = csv.writer(fh, delimiter=';')
                w.writerow(CANON + ['Verilen Malzeme Toplamı', 'Teslim Edilen - Verilen Fark'])
                w.writerow(['D1', 'G1', 'Grup', 'Firma A', 'Proje X', 'M100', '12,5', '999', '1'])
            import sqlite3
            c = sqlite3.connect(':memory:')
            ie._create_schema(c)
            n = ie._insert_kesif(c, {
                'path': str(path), 'role': 'T', 'sheet': 'Tesis_Verileri',
                'delimiter': ';', 'encoding': 'utf-8-sig', 'headerRow': 0,
            })
            self.assertEqual(n, 1)
            row = c.execute('SELECT planned, given, remaining, mismatch, contractor, project, group_no FROM kesif').fetchone()
            self.assertAlmostEqual(row[0], 12.5)
            self.assertAlmostEqual(row[1], 0.0)  # Verilen okunmaz
            self.assertAlmostEqual(row[2], 12.5)
            self.assertEqual(row[3], 0)
            self.assertEqual(row[4], 'Firma A')
            self.assertEqual(row[5], 'Proje X')
            self.assertEqual(row[6], 'G1')


if __name__ == '__main__':
    unittest.main()
