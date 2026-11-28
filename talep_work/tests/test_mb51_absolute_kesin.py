"""[3] MB51 mutlak otomatik kesin kayıt — Tesis hariç, farkta MB51 kazanır."""
import unittest
from pathlib import Path
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'
sys.path.insert(0, str(ROOT))

import revision_runtime as rr


class AutoFinalMb51AbsoluteWireTests(unittest.TestCase):
    def setUp(self):
        rr.reset_auto_final_done()

    def test_try_auto_final_applies_mb51_qty_and_audits(self):
        import server as srv

        header = {
            'KontrolID': 'KD-PREV-1',
            'RezervasyonNo': '1000001',
            'IsTuru': 'KET',
            'HedefUY': 'Y201',
            'HedefDepo': 'D01',
            'KaynakUY': 'Y100',
            'KaynakDepo': 'K01',
            'KayitIslemi': 'MANUEL',
        }
        materials = [
            {
                'MalzemeKodu': '5100100001',
                'KalemKarari': 'ONAYLA',
                'OnaylananMiktar': 10,
                'Miktar': 10,
                'Birim': 'AD',
            }
        ]
        rec = {
            'verified': True,
            'found': True,
            'status': 'FIILI_MIKTAR_FARKI',
            'actualQty': 7,
            'approvedQty': 10,
            'pendingQty': 0,
            'excessQty': 0,
            'state': 'PARTIAL',
            'lastDate': '2026-11-28',
            'error': '',
        }
        saved = {}

        def fake_save(payload, allow_repeat=False, expected_previous_control_id=None):
            saved['payload'] = payload
            saved['allow_repeat'] = allow_repeat
            saved['expected'] = expected_previous_control_id
            return {'controlId': 'KD-NEW-1'}

        audits = []

        with mock.patch.object(srv, 'load_config', return_value={'auto_final_record': True}), \
             mock.patch.object(srv.central_security, 'final_record_allowed_here', return_value=True), \
             mock.patch.object(srv, 'record_header_rows', return_value=[header]), \
             mock.patch.object(srv, '_control_bundle_csvs', return_value=(header, materials, [])), \
             mock.patch.object(srv, '_mb51_reconcile', return_value=rec), \
             mock.patch.object(srv, 'commitment_context', return_value={'verified': True, 'balanceDigest': 'bd1', 'items': []}), \
             mock.patch.object(srv, 'capacity_request_from_control', return_value=None), \
             mock.patch.object(srv, 'save_control_payload', side_effect=fake_save), \
             mock.patch.object(srv, 'user_context', return_value={'login': 'halit.ozdemir'}), \
             mock.patch.object(srv, '_notif_state', return_value={'items': {}}), \
             mock.patch.object(srv, '_notif_upsert'), \
             mock.patch.object(srv, '_save_notif_state'), \
             mock.patch.object(srv.DATA_ARCH_V2, 'audit', side_effect=lambda *a, **k: audits.append((a, k))):
            result = srv.try_auto_final_records(limit=5)

        self.assertTrue(result.get('ok'))
        self.assertEqual(len(result.get('written') or []), 1)
        mat = saved['payload']['materials'][0]
        self.assertEqual(mat['OnaylananMiktar'], 7)
        self.assertTrue(mat.get('MB51MutlakUygulandi'))
        self.assertEqual(saved['payload']['header']['KayitIslemi'], 'OTOMATIK_KESIN_KAYIT_MB51_MUTLAK')
        self.assertTrue(saved['allow_repeat'])
        self.assertEqual(saved['expected'], 'KD-PREV-1')
        self.assertTrue(any(a[0][1] == 'AUTO_FINAL_RECORD' for a in audits))
        auto_audit = next(a for a in audits if a[0][1] == 'AUTO_FINAL_RECORD')
        self.assertTrue(auto_audit[0][5].get('mb51Absolute'))

    def test_tesis_skipped_even_when_mb51_realized(self):
        import server as srv

        header = {
            'KontrolID': 'KD-TESIS-1',
            'RezervasyonNo': '2000002',
            'IsTuru': 'TESİS',
            'HedefUY': 'Y201',
            'HedefDepo': 'D01',
        }
        with mock.patch.object(srv, 'load_config', return_value={'auto_final_record': True}), \
             mock.patch.object(srv.central_security, 'final_record_allowed_here', return_value=True), \
             mock.patch.object(srv, 'record_header_rows', return_value=[header]), \
             mock.patch.object(srv, 'save_control_payload') as save_mock:
            result = srv.try_auto_final_records(limit=5)
        self.assertTrue(result.get('ok'))
        self.assertEqual(result.get('written'), [])
        save_mock.assert_not_called()

    def test_not_authorized_skips_write(self):
        import server as srv
        with mock.patch.object(srv, 'load_config', return_value={'auto_final_record': True}), \
             mock.patch.object(srv.central_security, 'final_record_allowed_here', return_value=False):
            result = srv.try_auto_final_records()
        self.assertFalse(result.get('ok'))
        self.assertEqual(result.get('skipped'), 'not_authorized')


if __name__ == '__main__':
    unittest.main()
