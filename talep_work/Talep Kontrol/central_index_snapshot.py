# -*- coding: utf-8 -*-
"""Merkezi salt-okunur kaynak indeks snapshot (0-Database/KAYNAK_INDEKS).

Model (Halit onay):
- Merkezde yazılabilir ortak SQLite YOK; yalnız yayımlanmış salt-okunur artifact.
- İlk boot: yerel ACTIVE yok/bozuksa merkez snapshot'tan seed.
- Kaynak değişince: yerel incremental rebuild → sonra merkezi snapshot güncelle.
- Çakışmada güncellik (built_at / source_digest) kazanır.
- Karar kayıtları bu modülde değil; COMMITTED paketleri paralel kalır.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA = 1
REL_DIR = 'KAYNAK_INDEKS'
_PUBLISH_LOCK = threading.Lock()
_SEED_ONCE_LOCK = threading.Lock()
_SEED_ONCE_DONE: Dict[str, Dict[str, Any]] = {}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception:
        return {}


def _write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.next')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def central_index_root(shared_record_root: Optional[Path], rel: str = REL_DIR) -> Optional[Path]:
    if shared_record_root is None:
        return None
    root = Path(shared_record_root)
    if not root.is_absolute():
        return None
    return root / (rel or REL_DIR)


def enabled(cfg: Optional[Dict[str, Any]]) -> bool:
    cfg = cfg or {}
    if cfg.get('central_index_snapshot') is False:
        return False
    return bool(cfg.get('enforce_shared_record_root'))


def _stamp_key(meta: Dict[str, Any]) -> tuple:
    """Higher tuple = fresher (built_at, then digest)."""
    return (str(meta.get('built_at') or ''), str(meta.get('source_digest') or ''))


def read_active_meta(index_root: Path) -> Dict[str, Any]:
    meta = _read_json(index_root / 'active.json')
    if int(meta.get('schema') or 0) != SCHEMA:
        return {}
    if not meta.get('build_id') or not meta.get('source_digest'):
        return {}
    return meta


def _build_dir(index_root: Path, build_id: str) -> Path:
    safe = str(build_id or '').replace('..', '').replace('/', '').replace('\\', '')
    return index_root / 'builds' / safe


def local_active_meta(app_dir: Path) -> Dict[str, Any]:
    import indexed_engine as ie
    try:
        build = ie.resolve_active_build(Path(app_dir))
        if not build:
            return {}
        ie.verify_build_integrity(build)
        manifest = ie.load_manifest(Path(build['manifestPath']))
        return {
            'build_id': build.get('build_id') or manifest.get('build_id') or '',
            'source_digest': build.get('source_digest') or manifest.get('digest') or '',
            'built_at': manifest.get('built_at') or build.get('created_at') or '',
            'index_sha256': build.get('index_sha256') or manifest.get('index_sha256') or '',
            'manifest_sha256': build.get('manifest_sha256') or '',
            'engine_version': manifest.get('engine_version') or '',
            'schema_version': manifest.get('schema_version') or '',
        }
    except Exception:
        return {}


def _copy_tree_files(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for path in src.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def local_needs_seed(app_dir: Path) -> bool:
    """True when local ACTIVE is missing, corrupt, or otherwise unusable for boot."""
    return not bool(local_active_meta(app_dir))


def seed_local_from_central(app_dir: Path, shared_record_root: Path, *,
                            rel: str = REL_DIR) -> Dict[str, Any]:
    """Copy central read-only snapshot into local Index when local ACTIVE missing/unusable.

    Never opens a writable shared SQLite; copies files then points local ACTIVE at them.
    Concurrent readers OK. If local is fresher or equal, no-op.
    Fast boot path: prefer this over cold UNC full rebuild when a published snapshot exists.
    """
    import indexed_engine as ie

    index_root = central_index_root(shared_record_root, rel)
    if index_root is None:
        return {'seeded': False, 'reason': 'no-central-root'}
    meta = read_active_meta(index_root)
    if not meta:
        return {'seeded': False, 'reason': 'no-central-active'}

    local = local_active_meta(app_dir)
    if local and _stamp_key(local) >= _stamp_key(meta):
        return {'seeded': False, 'reason': 'local-fresh-or-equal', 'local': local, 'central': meta}

    build_id = str(meta['build_id'])
    src = _build_dir(index_root, build_id)
    if not (src / 'talep_index.sqlite').is_file() or not (src / 'INDEX_MANIFEST.json').is_file():
        return {'seeded': False, 'reason': 'central-build-incomplete', 'build_id': build_id}

    # Verify published hashes before trust.
    if meta.get('index_sha256') and _sha256(src / 'talep_index.sqlite') != meta['index_sha256']:
        return {'seeded': False, 'reason': 'central-index-hash-mismatch'}
    if meta.get('manifest_sha256') and _sha256(src / 'INDEX_MANIFEST.json') != meta['manifest_sha256']:
        return {'seeded': False, 'reason': 'central-manifest-hash-mismatch'}

    cache = ie.storage_root(Path(app_dir))
    cache.mkdir(parents=True, exist_ok=True)
    dest_build = cache / 'builds' / build_id
    dest_pq = cache / 'parquet' / 'BUILDS' / build_id
    if dest_build.exists():
        shutil.rmtree(dest_build, ignore_errors=True)
    if dest_pq.exists():
        shutil.rmtree(dest_pq, ignore_errors=True)
    dest_build.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / 'talep_index.sqlite', dest_build / 'talep_index.sqlite')
    shutil.copy2(src / 'INDEX_MANIFEST.json', dest_build / 'INDEX_MANIFEST.json')
    src_pq = src / 'parquet'
    if src_pq.is_dir():
        _copy_tree_files(src_pq, dest_pq)
    else:
        dest_pq.mkdir(parents=True, exist_ok=True)

    pointer = {
        'build_id': build_id,
        'source_digest': meta['source_digest'],
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'index_db': str((dest_build / 'talep_index.sqlite').relative_to(cache)),
        'manifest': str((dest_build / 'INDEX_MANIFEST.json').relative_to(cache)),
        'parquet_root': str(dest_pq.relative_to(cache)),
        'index_sha256': meta.get('index_sha256') or _sha256(dest_build / 'talep_index.sqlite'),
        'manifest_sha256': meta.get('manifest_sha256') or _sha256(dest_build / 'INDEX_MANIFEST.json'),
        'ruleset_version': meta.get('ruleset_version') or '',
        'ruleset_hash': meta.get('ruleset_hash') or '',
        'seeded_from_central': True,
    }
    try:
        ie.verify_build_integrity({
            **pointer,
            'indexDb': str(dest_build / 'talep_index.sqlite'),
            'manifestPath': str(dest_build / 'INDEX_MANIFEST.json'),
            'parquetRoot': str(dest_pq),
        })
    except Exception as exc:
        shutil.rmtree(dest_build, ignore_errors=True)
        shutil.rmtree(dest_pq, ignore_errors=True)
        return {'seeded': False, 'reason': 'integrity-failed', 'error': str(exc)}

    pointer_path = ie._active_pointer(Path(app_dir))
    _write_json_atomic(pointer_path, pointer)
    return {
        'seeded': True,
        'build_id': build_id,
        'source_digest': meta['source_digest'],
        'from': str(src),
        'fast_boot': True,
        'writable_shared_sqlite': False,
    }


def ensure_seeded_once(app_dir: Path, shared_record_root: Path, *,
                      rel: str = REL_DIR, force: bool = False) -> Dict[str, Any]:
    """Idempotent seed for first paint / MISSING local Index.

    Concurrent callers share one attempt per (app_dir, shared_root, rel).
    Does not open shared SQLite for write — only copies published artifacts.
    """
    key = '|'.join([
        str(Path(app_dir).resolve()),
        str(Path(shared_record_root).resolve()) if shared_record_root else '',
        str(rel or REL_DIR),
    ])
    with _SEED_ONCE_LOCK:
        if not force and key in _SEED_ONCE_DONE:
            return dict(_SEED_ONCE_DONE[key])
        if not force and not local_needs_seed(app_dir):
            result = {'seeded': False, 'reason': 'local-already-usable', 'skipped': True}
            _SEED_ONCE_DONE[key] = result
            return dict(result)
        try:
            result = seed_local_from_central(app_dir, shared_record_root, rel=rel)
        except Exception as exc:
            result = {'seeded': False, 'reason': 'seed-exception', 'error': str(exc)}
        _SEED_ONCE_DONE[key] = result
        return dict(result)


def publish_central_snapshot(app_dir: Path, shared_record_root: Path, *,
                             rel: str = REL_DIR) -> Dict[str, Any]:
    """Publish local ACTIVE build as read-only central snapshot. Freshness wins on conflict."""
    import indexed_engine as ie

    index_root = central_index_root(shared_record_root, rel)
    if index_root is None:
        return {'published': False, 'reason': 'no-central-root'}

    local = local_active_meta(app_dir)
    if not local.get('build_id'):
        return {'published': False, 'reason': 'no-local-active'}

    with _PUBLISH_LOCK:
        remote = read_active_meta(index_root)
        if remote and _stamp_key(remote) > _stamp_key(local):
            return {'published': False, 'reason': 'remote-fresher', 'remote': remote, 'local': local}
        if remote and remote.get('source_digest') == local.get('source_digest') and remote.get('build_id') == local.get('build_id'):
            return {'published': False, 'reason': 'already-current', 'build_id': local['build_id']}

        build = ie.resolve_active_build(Path(app_dir))
        ie.verify_build_integrity(build)
        build_id = str(build.get('build_id') or local['build_id'])
        src_index = Path(build['indexDb'])
        src_manifest = Path(build['manifestPath'])
        src_pq = Path(build.get('parquetRoot') or '')

        dest = _build_dir(index_root, build_id)
        staging = index_root / 'builds' / ('.staging-' + build_id + '-' + hashlib.sha1(os.urandom(8)).hexdigest()[:8])
        try:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_index, staging / 'talep_index.sqlite')
            shutil.copy2(src_manifest, staging / 'INDEX_MANIFEST.json')
            pq_out = staging / 'parquet'
            pq_out.mkdir(parents=True, exist_ok=True)
            if src_pq.is_dir():
                for item in src_pq.iterdir():
                    if item.is_file() and item.suffix.lower() == '.parquet':
                        shutil.copy2(item, pq_out / item.name)
            index_hash = _sha256(staging / 'talep_index.sqlite')
            manifest_hash = _sha256(staging / 'INDEX_MANIFEST.json')
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            os.replace(staging, dest)
            staging = None
            meta = {
                'schema': SCHEMA,
                'product': 'Talep Kontrol',
                'kind': 'SOURCE_INDEX_SNAPSHOT',
                'read_only': True,
                'writable_shared_sqlite': False,
                'build_id': build_id,
                'source_digest': local['source_digest'],
                'built_at': local.get('built_at') or time.strftime('%Y-%m-%dT%H:%M:%S'),
                'published_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'index_sha256': index_hash,
                'manifest_sha256': manifest_hash,
                'engine_version': local.get('engine_version') or '',
                'schema_version': local.get('schema_version') or '',
                'ruleset_version': build.get('ruleset_version') or '',
                'ruleset_hash': build.get('ruleset_hash') or '',
                'path': f'builds/{build_id}',
            }
            # Re-check freshness before pointer flip (concurrent publisher).
            remote2 = read_active_meta(index_root)
            if remote2 and _stamp_key(remote2) > _stamp_key(meta):
                return {'published': False, 'reason': 'remote-fresher-after-copy', 'remote': remote2}
            _write_json_atomic(index_root / 'active.json', meta)
            # Keep a few old builds
            try:
                builds = sorted(
                    [p for p in (index_root / 'builds').iterdir() if p.is_dir() and not p.name.startswith('.')],
                    key=lambda p: p.stat().st_mtime, reverse=True)
                for old in builds[4:]:
                    if old.name != build_id:
                        shutil.rmtree(old, ignore_errors=True)
            except Exception:
                pass
            return {'published': True, 'build_id': build_id, 'source_digest': local['source_digest'], 'path': str(dest)}
        finally:
            if staging is not None and Path(staging).exists():
                shutil.rmtree(staging, ignore_errors=True)


def publish_in_background(app_dir: Path, shared_record_root: Path, *, rel: str = REL_DIR) -> None:
    def worker():
        try:
            publish_central_snapshot(app_dir, shared_record_root, rel=rel)
        except Exception:
            pass
    threading.Thread(target=worker, name='talep-central-index-publish', daemon=True).start()
