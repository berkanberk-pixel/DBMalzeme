"""Keşif birimi boşken MB52 temel birimine düşülür."""
import sqlite3
import unittest


class KesifUnitFallbackTests(unittest.TestCase):
    def _connection(self):
        c = sqlite3.connect(':memory:')
        c.row_factory = sqlite3.Row
        c.executescript('''
            CREATE TABLE depots(uy TEXT, dy TEXT, work_type TEXT);
            CREATE TABLE zmm098(uy TEXT, dy TEXT, available REAL);
            CREATE TABLE projects(uy TEXT, dy TEXT, project_id TEXT, project_name TEXT, active TEXT);
            CREATE TABLE mb52(material_code TEXT, plant TEXT, uom TEXT, valuation_type TEXT,
                              qty REAL, unrestricted_value REAL);
            CREATE TABLE kesif(dy TEXT, material_code TEXT, work_code TEXT, uom TEXT,
                               project TEXT, remaining REAL, issue INTEGER, mismatch INTEGER,
                               sheet TEXT, row_no INTEGER);
        ''')
        return c

    def test_empty_kesif_uom_inherits_mb52(self):
        from capacity_source_facts import read_facts

        c = self._connection()
        c.execute("INSERT INTO depots VALUES ('6510','Y206','K')")
        c.execute("INSERT INTO zmm098 VALUES ('6510','Y206',1000)")
        c.execute("INSERT INTO mb52 VALUES ('5100144001','6510','ADT','YENI',10,100)")
        c.execute("""INSERT INTO kesif VALUES
            ('Y206','5100144001','K','','',7,0,0,'KET_Verileri',3644)""")
        facts = read_facts(
            c,
            {'targetUY': '6510', 'targetDY': 'Y206', 'sourceUY': '6510',
             'materials': [{'materialCode': '5100144001'}]},
            [],
            {},
        )
        self.assertEqual(facts['materials']['5100144001']['uom'], 'AD')
        self.assertEqual(facts['materials']['5100144001']['discoveryRemaining'], 7.0)

    def test_conflicting_kesif_uom_still_raises(self):
        from capacity_source_facts import read_facts
        from commitment_balances import BalanceError

        c = self._connection()
        c.execute("INSERT INTO depots VALUES ('6510','Y206','K')")
        c.execute("INSERT INTO zmm098 VALUES ('6510','Y206',1000)")
        c.execute("INSERT INTO mb52 VALUES ('5100144001','6510','ADT','YENI',10,100)")
        c.execute("""INSERT INTO kesif VALUES
            ('Y206','5100144001','K','M','',7,0,0,'KET_Verileri',3644)""")
        with self.assertRaises(BalanceError) as ctx:
            read_facts(
                c,
                {'targetUY': '6510', 'targetDY': 'Y206', 'sourceUY': '6510',
                 'materials': [{'materialCode': '5100144001'}]},
                [],
                {},
            )
        self.assertIn('uyuşmuyor', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
