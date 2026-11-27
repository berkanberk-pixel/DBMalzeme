"""Central read-only KAYNAK_INDEKS snapshot: seed + publish + fresher-wins."""
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1] / 'Talep Kontrol'
sys.path.insert(0, str(ROOT))

import central_index_snapshot as cis  # noqa: E402
import indexed_engine as ie  # noqa: E402


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _make_local_build(app_dir: Path, *, build_id='IDX-TEST-aaaaaaaaaa-bbbbbbbbbbbb',
                      digest='d' * 64, built_at='2026-11-27T10:00:00'):
    cache = ie.storage_root(app_dir)
    build = cache / 'builds' / build_id
    pq = cache / 'parquet' / 'BUILDS' / build_id
    build.mkdir(parents=True, exist_ok=True)
    pq.mkdir(parents=True, exist_ok=True)
    db = build / 'talep_index.sqlite'
    c = sqlite3.connect(db)
    c.execute('CREATE TABLE meta(key TEXT, value TEXT)')
    c.execute('INSERT INTO meta VALUES(?,?)', ('source_digest', digest))
    c.commit()
    c.close()
    manifest = {
        'build_id': build_id,
        'digest': digest,
        'built_at': built_at,
        'engine_version': ie.ENGINE_VERSION,
        'schema_version': ie.INDEX_SCHEMA_VERSION,
        'index_sha256': '',
        'parquet': {},
        'files': [],
    }
    man = build / 'INDEX_MANIFEST.json'
    index_hash = _sha(db)
    manifest['index_sha256'] = index_hash
    man.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    pointer = {
        'build_id': build_id,
        'source_digest': digest,
        'created_at': built_at,
        'index_db': str(db.relative_to(cache)),
        'manifest': str(man.relative_to(cache)),
        'parquet_root': str(pq.relative_to(cache)),
        'index_sha256': index_hash,
        'manifest_sha256': _sha(man),
        'ruleset_version': 'test',
        'ruleset_hash': '0' * 64,
    }
    cis._write_json_atomic(ie._active_pointer(app_dir), pointer)
    return pointer


class CentralIndexSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = self.root / 'app'
        self.app.mkdir()
        self.shared = self.root / '0-Database'
        self.shared.mkdir()
        self.index_root = self.shared / 'KAYNAK_INDEKS'
        os.environ['TALEP_INDEX_ROOT'] = str(self.root / 'Index')

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop('TALEP_INDEX_ROOT', None)

    def test_publish_then_seed_on_fresh_client(self):
        _make_local_build(self.app, built_at='2026-11-27T12:00:00')
        pub = cis.publish_central_snapshot(self.app, self.shared)
        self.assertTrue(pub.get('published'), pub)
        meta = cis.read_active_meta(self.index_root)
        self.assertEqual(meta.get('schema'), 1)
        self.assertTrue(meta.get('read_only'))
        self.assertFalse(meta.get('writable_shared_sqlite'))

        # New client: empty local index root
        os.environ['TALEP_INDEX_ROOT'] = str(self.root / 'IndexB')
        app2 = self.root / 'app2'
        app2.mkdir()
        seed = cis.seed_local_from_central(app2, self.shared)
        self.assertTrue(seed.get('seeded'), seed)
        local = cis.local_active_meta(app2)
        self.assertEqual(local.get('source_digest'), meta.get('source_digest'))

    def test_fresher_wins_on_conflict(self):
        _make_local_build(self.app, digest='a' * 64, built_at='2026-11-27T10:00:00',
                          build_id='IDX-OLD-aaaaaaaaaa-bbbbbbbbbbbb')
        self.assertTrue(cis.publish_central_snapshot(self.app, self.shared).get('published'))

        # Older publish attempt must not overwrite
        older_app = self.root / 'older'
        older_app.mkdir()
        os.environ['TALEP_INDEX_ROOT'] = str(self.root / 'IndexOld')
        _make_local_build(older_app, digest='b' * 64, built_at='2026-11-27T09:00:00',
                          build_id='IDX-OLDER-aaaaaaaaaa-bbbbbbbbbbbb')
        again = cis.publish_central_snapshot(older_app, self.shared)
        self.assertFalse(again.get('published'), again)
        self.assertEqual(again.get('reason'), 'remote-fresher')

    def test_enabled_flag(self):
        self.assertTrue(cis.enabled({'enforce_shared_record_root': True}))
        self.assertFalse(cis.enabled({'enforce_shared_record_root': True, 'central_index_snapshot': False}))
        self.assertFalse(cis.enabled({'enforce_shared_record_root': False}))


if __name__ == '__main__':
    unittest.main()
