"""Silent accept must queue while INDEX_BUILDING / engine lock busy — no false errors."""
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'
sys.path.insert(0, str(ROOT))


class SilentAcceptQueueTests(unittest.TestCase):
    def setUp(self):
        import server as srv
        self.srv = srv
        with srv._SILENT_ACCEPT_QUEUE_LOCK:
            srv._SILENT_ACCEPT_QUEUE.clear()
        with srv._ENGINE_BUILD_STATE_LOCK:
            srv._ENGINE_BUILD_STATE.update({
                'building': False, 'startedAt': '', 'finishedAt': '', 'error': '',
            })

    def test_auto_accept_queues_while_building(self):
        with self.srv._ENGINE_BUILD_STATE_LOCK:
            self.srv._ENGINE_BUILD_STATE['building'] = True
        out = self.srv.source_update_choice('MB51', 'accept', 'SYSTEM_AUTO_ACCEPT')
        self.assertEqual(out.get('status'), 'QUEUED')
        self.assertTrue(out.get('queued'))
        with self.srv._SILENT_ACCEPT_QUEUE_LOCK:
            self.assertIn('MB51', self.srv._SILENT_ACCEPT_QUEUE)

    def test_manual_accept_still_errors_when_lock_busy(self):
        held = threading.Event()
        release = threading.Event()

        def hold():
            self.srv._ENGINE_BUILD_LOCK.acquire()
            held.set()
            release.wait(timeout=3)
            self.srv._ENGINE_BUILD_LOCK.release()

        t = threading.Thread(target=hold, daemon=True)
        t.start()
        self.assertTrue(held.wait(2))
        with self.assertRaises(ValueError) as ctx:
            self.srv.source_update_choice('ZMM098', 'accept', 'DATA_MANAGER')
        self.assertIn('Başka bir kaynak işlemi', str(ctx.exception))
        # Auto path queues instead
        out = self.srv.source_update_choice('ZMM098', 'accept', 'SYSTEM_AUTO_ACCEPT')
        self.assertEqual(out.get('status'), 'QUEUED')
        release.set()
        t.join(timeout=3)

    def test_drain_runs_after_building_clears(self):
        called = []

        def fake_locked(logical, choice, actor):
            called.append(logical)
            return {'source': logical, 'status': 'ACTIVE'}

        with self.srv._ENGINE_BUILD_STATE_LOCK:
            self.srv._ENGINE_BUILD_STATE['building'] = True
        self.srv._enqueue_silent_accept('TESIS', 'INDEX_BUILDING')
        self.srv._enqueue_silent_accept('KET', 'INDEX_BUILDING')
        with mock.patch.object(self.srv, '_source_update_choice_locked', side_effect=fake_locked):
            with self.srv._ENGINE_BUILD_STATE_LOCK:
                self.srv._ENGINE_BUILD_STATE['building'] = False
            self.srv._schedule_silent_accept_drain(delay_sec=0.05)
            deadline = time.time() + 3
            while time.time() < deadline and set(called) != {'TESIS', 'KET'}:
                time.sleep(0.05)
        self.assertEqual(set(called), {'TESIS', 'KET'})


if __name__ == '__main__':
    unittest.main()
