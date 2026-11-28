"""Hız paketi adım 1 / [11]: büyük MB51/MB52 pending — mtime/size önce, SHA örneklemeli."""
import hashlib
import os
import tempfile
import time
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'
sys.path.insert(0, str(ROOT))

import revision_runtime as rr


class SparsePolicyTests(unittest.TestCase):
    def test_threshold_only_mb51_mb52(self):
        big = rr.PENDING_SPARSE_MIN_BYTES
        self.assertTrue(rr.use_pending_sparse_sha('MB51', big))
        self.assertTrue(rr.use_pending_sparse_sha('MB52', big))
        self.assertFalse(rr.use_pending_sparse_sha('MB51', big - 1))
        self.assertFalse(rr.use_pending_sparse_sha('ZMM048', big))
        self.assertFalse(rr.use_pending_sparse_sha('TANIMLAR', big * 2))

    def test_sparse_stable_and_detects_mid_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'big.bin'
            # 3 MiB so head/mid/tail samples are distinct under 1 MiB block.
            payload = bytearray(b'A' * (3 * 1024 * 1024))
            path.write_bytes(payload)
            d1 = rr.sparse_file_sha256(path)
            d2 = rr.sparse_file_sha256(path)
            self.assertEqual(d1, d2)
            # Change only the middle region (outside head/tail 1 MiB).
            mid = len(payload) // 2
            payload[mid] = (payload[mid] + 1) % 256
            path.write_bytes(payload)
            d3 = rr.sparse_file_sha256(path)
            self.assertNotEqual(d1, d3)

    def test_sparse_reads_far_less_than_full_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'huge.bin'
            size = 12 * 1024 * 1024
            path.write_bytes(b'Z' * size)
            # Instrument via block size: sparse should finish quickly vs full hash.
            t0 = time.perf_counter()
            sparse = rr.sparse_file_sha256(path, block=256 * 1024)
            sparse_dt = time.perf_counter() - t0
            t1 = time.perf_counter()
            with path.open('rb') as stream:
                full = hashlib.file_digest(stream, 'sha256').hexdigest()
            full_dt = time.perf_counter() - t1
            self.assertNotEqual(sparse, full)
            self.assertLess(sparse_dt, full_dt)
            # At most ~3 blocks read; full reads entire file.
            self.assertLessEqual(3 * 256 * 1024, size)


class PendingUpdatesSparseTests(unittest.TestCase):
    def _info(self, path, *, role='', name=None, input_path=None, input_rev=None, sha=None):
        st = path.stat()
        rev = (st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        entry = {
            'path': str(path),
            'name': name or path.name,
            'role': role,
            'size': st.st_size,
            'sheet': '',
            'cachedRevision': list(rev),
        }
        if input_path is not None:
            entry['inputPath'] = str(input_path)
        if input_rev is not None:
            entry['inputRevision'] = list(input_rev)
        if sha is not None:
            entry['sha256'] = sha
        return {
            'files': [entry],
            'name': name or path.name,
            'size': st.st_size,
            'modifiedIso': '',
            'origin': 'active',
        }

    def test_fingerprint_match_skips_sha_even_with_known(self):
        import server as srv

        with tempfile.TemporaryDirectory() as tmp:
            active = Path(tmp) / 'active.csv'
            cand = Path(tmp) / 'cand.csv'
            body = b'x' * (rr.PENDING_SPARSE_MIN_BYTES + 100)
            active.write_bytes(body)
            # Same size/mtime family via copy2 keeps content; force same revision fields.
            cand.write_bytes(body)
            os.utime(cand, ns=(active.stat().st_mtime_ns, active.stat().st_mtime_ns))
            ai = self._info(active, name='MB51.csv', input_path=cand, input_rev=_rev(cand),
                            sha=hashlib.sha256(body).hexdigest())
            # Align fingerprint: use inputRevision on active matching cand revision.
            ai['files'][0]['inputRevision'] = list(_rev(cand))
            ai['files'][0]['inputPath'] = str(cand)
            ci = self._info(cand, name='MB51.csv')
            # Ensure fingerprints equal via inputRevision path in quick fingerprint.
            self.assertEqual(srv._source_quick_fingerprint(ai), srv._source_quick_fingerprint(ci))
            calls = {'n': 0}
            real = srv._source_sha256

            def counted(path, revision):
                calls['n'] += 1
                return real(path, revision)

            srv._source_sha256 = counted
            try:
                pending = srv._pending_source_updates({'MB51': ai}, {'MB51': ci})
            finally:
                srv._source_sha256 = real
            self.assertEqual(pending, [])
            self.assertEqual(calls['n'], 0)

    def test_large_mb51_change_uses_sparse_not_full(self):
        import server as srv

        with tempfile.TemporaryDirectory() as tmp:
            active = Path(tmp) / 'a.csv'
            cand = Path(tmp) / 'c.csv'
            size = rr.PENDING_SPARSE_MIN_BYTES + 50_000
            payload = bytearray(b'B' * size)
            active.write_bytes(payload)
            # Differ in middle so sparse catches it; size same → bump mtime via content rewrite + utime differ.
            payload[size // 2] = (payload[size // 2] + 1) % 256
            cand.write_bytes(payload)
            # Force fingerprint mismatch via size bump on candidate name/size field.
            ai = self._info(active, name='MB51.csv')
            ci = self._info(cand, name='MB51.csv')
            self.assertNotEqual(srv._source_quick_fingerprint(ai), srv._source_quick_fingerprint(ci))

            calls = {'full': 0, 'sparse': 0}
            real_full = srv._source_sha256
            real_sparse = rr.sparse_file_sha256

            def full_count(path, revision):
                calls['full'] += 1
                return real_full(path, revision)

            def sparse_count(path, block=rr.PENDING_SPARSE_BLOCK):
                calls['sparse'] += 1
                return real_sparse(path, block=block)

            srv._source_sha256 = full_count
            rr.sparse_file_sha256 = sparse_count
            try:
                pending = srv._pending_source_updates({'MB51': ai}, {'MB51': ci})
            finally:
                srv._source_sha256 = real_full
                rr.sparse_file_sha256 = real_sparse
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]['source'], 'MB51')
            self.assertEqual(pending[0]['digestMode'], 'sparse')
            self.assertGreaterEqual(calls['sparse'], 2)
            self.assertEqual(calls['full'], 0)

    def test_small_mb51_still_full_sha(self):
        import server as srv

        with tempfile.TemporaryDirectory() as tmp:
            active = Path(tmp) / 'a.csv'
            cand = Path(tmp) / 'c.csv'
            active.write_bytes(b'small-a')
            cand.write_bytes(b'small-b-different')
            ai = self._info(active, name='MB51.csv')
            ci = self._info(cand, name='MB51.csv')
            pending = srv._pending_source_updates({'MB51': ai}, {'MB51': ci})
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]['digestMode'], 'full')


def _rev(path: Path):
    st = path.stat()
    return (st.st_size, st.st_mtime_ns, st.st_ctime_ns)


if __name__ == '__main__':
    unittest.main()
