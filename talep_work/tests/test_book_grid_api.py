"""Hız paketi adım 3 / [14]: ZMM048/MB52/ZMM098 IndexedDB book yok — indeks+/api/grid."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'
sys.path.insert(0, str(ROOT))

import indexed_engine as ie
import server as srv


def _seed_index(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.executescript('''
    CREATE TABLE zmm048(
      id INTEGER PRIMARY KEY,reservation_no TEXT,material_code TEXT,material_desc TEXT,qty REAL,uom TEXT,
      source_uy TEXT,source_dy TEXT,target_uy TEXT,target_dy TEXT
    );
    CREATE TABLE mb52(
      id INTEGER PRIMARY KEY,plant TEXT,dy TEXT,dy_desc TEXT,material_group TEXT,material_group_desc TEXT,
      material_code TEXT,material_desc TEXT,uom TEXT,qty REAL,total_value REAL,unrestricted_value REAL,
      valuation_type TEXT,depot_type TEXT,search_text TEXT
    );
    CREATE TABLE zmm098(
      id INTEGER PRIMARY KEY,uy TEXT,dy TEXT,dy_desc TEXT,main REAL,cash REAL,manual REAL,
      stock_value REAL,available REAL,search_text TEXT
    );
    ''')
    c.execute(
        'INSERT INTO zmm048(reservation_no,material_code,material_desc,qty,uom,source_uy,source_dy,target_uy,target_dy)'
        " VALUES('900001','5100100001','Mal A',12,'ADT','6510','Y100','6510','Y206')"
    )
    c.execute(
        'INSERT INTO mb52(plant,dy,dy_desc,material_group,material_group_desc,material_code,material_desc,uom,qty,'
        'total_value,unrestricted_value,valuation_type,depot_type,search_text)'
        " VALUES('6510','Y206','Depo','G1','Grup','5100100001','Mal A','ADT',5,100,100,'YENI','',"
        "'6510 y206 5100100001')"
    )
    c.execute(
        'INSERT INTO zmm098(uy,dy,dy_desc,main,cash,manual,stock_value,available,search_text)'
        " VALUES('6510','Y206','Depo',1000,0,0,50,800,'6510 y206')"
    )
    c.commit()
    c.close()


class BookGridApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / 'index.sqlite'
        _seed_index(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_decision_dataset_from_index(self):
        z48 = ie.decision_dataset(self.db, 'ZMM048')
        self.assertEqual(z48['source'], 'ZMM048')
        self.assertEqual(z48['engine'], 'SQLITE_INDEX')
        self.assertEqual(z48['total'], 1)
        self.assertEqual(z48['rows'][0]['reservationNo'], '900001')
        self.assertEqual(z48['rows'][0]['materialCode'], '5100100001')
        self.assertTrue(z48['rows'][0]['fromIndex'])

        mb52 = ie.decision_dataset(self.db, 'MB52')
        self.assertEqual(mb52['total'], 1)
        self.assertEqual(mb52['rows'][0]['unitPrice'], 20.0)

        z98 = ie.decision_dataset(self.db, 'ZMM098')
        self.assertEqual(z98['rows'][0]['available'], 800.0)
        self.assertEqual(z98['rows'][0]['availableSource'], 'INDEX')

        with self.assertRaises(ValueError):
            ie.decision_dataset(self.db, 'MB51')

    def test_grid_reservations_paged(self):
        out = ie.grid_reservations(self.db, '900001', 1, 100)
        self.assertEqual(out['source'], 'ZMM048')
        self.assertEqual(out['total'], 1)
        self.assertEqual(out['rows'][0]['recvDY'], 'Y206')

    def test_grid_snapshot_decision_and_reservations(self):
        with mock.patch.object(srv, '_engine_ready_now', return_value=True), \
             mock.patch.object(srv, '_active_index_db', return_value=self.db):
            dec = srv._grid_snapshot('decision', {'source': 'ZMM048'})
            self.assertEqual(dec['mode'], 'decision')
            self.assertEqual(dec['total'], 1)
            res = srv._grid_snapshot('reservations', {'q': '900001', 'page': '1', 'pageSize': '50'})
            self.assertEqual(res['total'], 1)
            with self.assertRaises(ValueError):
                srv._grid_snapshot('decision', {'source': 'TANIMLAR'})

    def test_api_book_deferred_for_index_sources(self):
        self.assertIn('ZMM048', srv.BOOK_DEFERRED_SOURCES)
        self.assertIn('MB52', srv.BOOK_DEFERRED_SOURCES)
        self.assertIn('ZMM098', srv.BOOK_DEFERRED_SOURCES)
        self.assertIn('ZMM048', srv.INDEX_DECISION_SOURCES)


if __name__ == '__main__':
    unittest.main()
