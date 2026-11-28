"""Halit revizyon politikaları — tarama derinliği, teşhis, sessiz accept, 24s uyarı, lazy bildirim.

Ortak yazılabilir SQLite yoktur; kesin kayıt COMMITTED bundle ile kalır.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

# [10] Güvenli varsayılan: düz klasör + en fazla 1 alt seviye.
DEFAULT_SCAN_MAX_DEPTH = 1
# [2] 24 saat → uyarı (sert kilit değil).
SOURCE_FRESHNESS_WARN_HOURS = 24
# [16] MB51 bildirim tarama TTL (saniye).
NOTIFICATION_MB51_TTL_SEC = 300
# Monitor stamp cache.
_MONITOR_STAMP_CACHE: Dict[str, Any] = {'stamp': '', 'at': 0.0}
_NOTIF_MB51_CACHE: Dict[str, Any] = {'at': 0.0, 'ran': False}
_AUTO_ACCEPT_LOCK = threading.RLock()
_AUTO_FINAL_LOCK = threading.RLock()
_AUTO_FINAL_DONE: set = set()


def scan_max_depth(cfg: Optional[dict] = None) -> int:
    cfg = cfg or {}
    try:
        depth = int(cfg.get('scan_max_depth', DEFAULT_SCAN_MAX_DEPTH))
    except (TypeError, ValueError):
        depth = DEFAULT_SCAN_MAX_DEPTH
    return max(0, min(depth, 3))


def iter_candidates_limited(root: Path, recursive: bool, max_depth: int = DEFAULT_SCAN_MAX_DEPTH):
    """CSV/Excel adayları. recursive=True olsa bile max_depth ile sınırlanır ([10])."""
    if not root.exists() or not root.is_dir():
        return []
    blocked = {'kontrol_baslik', 'kontrol_malzeme', 'kontrol_proje', 'kayitlar', '0-database',
               '9-uygulama', '9-testsap', 'panel-yetkileri', 'kaynak_verileri'}
    out = []
    try:
        if not recursive or max_depth <= 0:
            items = list(root.iterdir())
            for p in items:
                if not p.is_file():
                    continue
                if p.name.startswith('~$') or p.suffix.lower() not in ('.csv', '.xlsx', '.xlsm', '.xls', '.xlsb'):
                    continue
                if p.name.lower() == 'muaf_listesi.csv':
                    continue
                if any(part.lower() in blocked for part in p.parts):
                    continue
                out.append(p)
            return out
        # max_depth >= 1: kök + en fazla N alt klasör seviyesi
        root_resolved = root.resolve()
        for p in root.rglob('*'):
            if not p.is_file():
                continue
            try:
                rel = p.relative_to(root_resolved)
            except ValueError:
                continue
            # dosya derinliği = ebeveyn klasör sayısı
            depth = len(rel.parts) - 1
            if depth > max_depth:
                continue
            if p.name.startswith('~$') or p.suffix.lower() not in ('.csv', '.xlsx', '.xlsm', '.xls', '.xlsb'):
                continue
            if p.name.lower() == 'muaf_listesi.csv':
                continue
            if any(part.lower() in blocked for part in p.parts):
                continue
            out.append(p)
        return out
    except Exception:
        return []


def sources_monitor_stamp(sources: Optional[dict]) -> str:
    """Aktif kaynakların boyut/mtime damgası — monitor full UNC yerine ([9])."""
    rows = []
    for name in sorted((sources or {}).keys()):
        info = (sources or {}).get(name) or {}
        files = info.get('files') or []
        file_bits = []
        for f in files:
            file_bits.append(f"{f.get('name')}:{f.get('size')}:{f.get('lastModified')}:{f.get('role')}")
        rows.append(f"{name}|{info.get('size')}|{info.get('lastModified')}|{','.join(file_bits)}")
    return hashlib.sha256('\n'.join(rows).encode('utf-8')).hexdigest()


def monitor_stamp_unchanged(sources: Optional[dict], ttl_sec: float = 55.0) -> Tuple[bool, str]:
    stamp = sources_monitor_stamp(sources)
    now = time.time()
    prev = _MONITOR_STAMP_CACHE.get('stamp') or ''
    at = float(_MONITOR_STAMP_CACHE.get('at') or 0)
    if prev == stamp and (now - at) < ttl_sec:
        return True, stamp
    _MONITOR_STAMP_CACHE['stamp'] = stamp
    _MONITOR_STAMP_CACHE['at'] = now
    return False, stamp


def reset_monitor_stamp_cache():
    _MONITOR_STAMP_CACHE['stamp'] = ''
    _MONITOR_STAMP_CACHE['at'] = 0.0


def diagnose_source_access(access: dict, engine: dict, cfg: Optional[dict] = None,
                           release_id: str = '', app_version: str = '', app_build: str = '') -> dict:
    """[6] Salt-okunur teşhis paketi — reason + missing + dataEngine + release."""
    access = dict(access or {})
    engine = engine or {}
    cfg = cfg or {}
    reason = str(access.get('reason') or '')
    code = 'OK'
    if not access.get('current'):
        if 'bütünlük' in reason.lower() or engine.get('status') == 'CORRUPT':
            code = 'INDEX_CORRUPT'
        elif access.get('missing'):
            code = 'ACTIVE_MISSING'
        elif engine.get('building'):
            code = 'INDEX_BUILDING'
        elif str(engine.get('status') or '') == 'FAILED':
            code = 'INDEX_FAILED'
        elif not engine.get('usable'):
            code = 'INDEX_UNUSABLE'
        elif 'servis' in reason.lower():
            code = 'SERVICE_DOWN'
        else:
            code = 'READONLY'
    diagnosis = {
        'reasonCode': code,
        'reason': reason,
        'missing': list(access.get('missing') or []),
        'candidateMissing': list(access.get('candidateMissing') or []),
        'networkNote': access.get('networkNote') or '',
        'dataEngine': {
            'status': engine.get('status'),
            'usable': bool(engine.get('usable')),
            'ready': bool(engine.get('ready')),
            'building': bool(engine.get('building')),
            'buildId': engine.get('buildId') or '',
            'lastError': engine.get('lastError') or engine.get('error') or '',
        },
        'releaseId': release_id or str(cfg.get('release_id') or ''),
        'appVersion': app_version or str(cfg.get('app_version') or ''),
        'appBuild': app_build or str(cfg.get('build') or ''),
        'checkedAt': access.get('checkedAt') or datetime.now().astimezone().isoformat(),
        'logLine': (
            f"[sourceAccess] current={bool(access.get('current'))} code={code} "
            f"missing={','.join(access.get('missing') or []) or '-'} "
            f"engine={engine.get('status')}/usable={bool(engine.get('usable'))}/"
            f"building={bool(engine.get('building'))} "
            f"release={release_id or cfg.get('release_id') or '-'} "
            f"reason={reason or '-'}"
        ),
    }
    access['diagnosis'] = diagnosis
    return access


def freshness_warnings(source_health: Optional[dict], warn_hours: float = SOURCE_FRESHNESS_WARN_HOURS) -> List[dict]:
    """[2] 24s+ yaş → uyarı listesi (salt-okunur kilidi yok)."""
    out = []
    for item in (source_health or {}).get('sources') or []:
        age = item.get('age_hours')
        if age is None:
            continue
        try:
            age_f = float(age)
        except (TypeError, ValueError):
            continue
        if age_f >= float(warn_hours):
            out.append({
                'source': item.get('source'),
                'ageHours': round(age_f, 1),
                'limitHours': warn_hours,
                'health': item.get('health'),
                'message': f"{item.get('source')}: veri yaşı {age_f:.1f} sa (eşik {warn_hours:g} sa).",
            })
    return out


def should_run_mb51_notification_scan(force: bool = False, ttl_sec: float = NOTIFICATION_MB51_TTL_SEC) -> bool:
    """[16] Bildirim MB51 reconcile lazy TTL."""
    now = time.time()
    if force:
        _NOTIF_MB51_CACHE['at'] = now
        _NOTIF_MB51_CACHE['ran'] = True
        return True
    if (now - float(_NOTIF_MB51_CACHE.get('at') or 0)) >= ttl_sec:
        _NOTIF_MB51_CACHE['at'] = now
        _NOTIF_MB51_CACHE['ran'] = True
        return True
    return False


def reset_notification_mb51_cache():
    _NOTIF_MB51_CACHE['at'] = 0.0
    _NOTIF_MB51_CACHE['ran'] = False


def is_tesis_work(value: Any) -> bool:
    return str(value or '').strip().upper() in ('TESIS', 'TESİS', 'T')


def mb51_realized(rec: Optional[dict]) -> bool:
    """Net MB51 gerçekleşme: verified + found + KONTROL_EDILEMEDI değil."""
    if not isinstance(rec, dict):
        return False
    if not rec.get('verified'):
        return False
    if str(rec.get('status') or '').upper() == 'KONTROL_EDILEMEDI':
        return False
    if not rec.get('found'):
        return False
    try:
        return float(rec.get('actualQty') or 0) > 0
    except (TypeError, ValueError):
        return False


def auto_final_eligible(is_tesis: bool, rec: Optional[dict]) -> bool:
    """[3] Tesis hariç: MB51 fiili gerçekleşmişse otomatik kesin kayıt adayı (fark dahil)."""
    if is_tesis:
        return False
    return mb51_realized(rec)


def apply_mb51_absolute(row: Optional[dict], rec: Optional[dict]) -> dict:
    """MB51 mutlak veri: farkta fiili miktar kazanır → OnaylananMiktar = actualQty.

    Tesis dışı otomatik kesin kayıtta kullanılır. Ortak yazılabilir SQLite yok.
    """
    out = dict(row or {})
    if not mb51_realized(rec):
        return out
    try:
        actual = float((rec or {}).get('actualQty') or 0)
    except (TypeError, ValueError):
        return out
    try:
        approved = float(out.get('OnaylananMiktar') or out.get('Miktar') or 0)
    except (TypeError, ValueError):
        approved = 0.0
    out['MB51FiiliMiktar'] = actual
    out['MB51MutabakatDurumu'] = (rec or {}).get('status')
    if abs(actual - approved) > 1e-9:
        out['OnaylananMiktar'] = actual
        note = str(out.get('KontrolNotu') or '')
        marker = f'MB51_MUTLAK onceki={approved:g} fiili={actual:g}'
        if 'MB51_MUTLAK' not in note:
            out['KontrolNotu'] = (note + ' ' + marker).strip()
        out['MB51MutlakUygulandi'] = True
    else:
        out['MB51MutlakUygulandi'] = False
    return out


def pending_auto_accept_enabled(cfg: Optional[dict] = None) -> bool:
    cfg = cfg or {}
    if 'silent_active_accept' in cfg:
        return bool(cfg.get('silent_active_accept'))
    return True  # Halit kilit [5]


def auto_final_record_enabled(cfg: Optional[dict] = None) -> bool:
    cfg = cfg or {}
    if 'auto_final_record' in cfg:
        return bool(cfg.get('auto_final_record'))
    return True  # Halit kilit [3]


def run_silent_active_accepts(
    pending_items: Iterable[dict],
    accept_fn: Callable[[str, str, str], dict],
    actor: str = 'SYSTEM_AUTO_ACCEPT',
) -> List[dict]:
    """[5] Bekleyen adayları sessiz ACTIVE accept. Deferred atlanır."""
    results = []
    with _AUTO_ACCEPT_LOCK:
        for item in pending_items or []:
            if item.get('deferred'):
                continue
            logical = str(item.get('source') or '').upper()
            if not logical:
                continue
            try:
                result = accept_fn(logical, 'accept', actor)
                results.append({'source': logical, 'ok': True, 'result': result})
            except Exception as exc:
                results.append({'source': logical, 'ok': False, 'error': str(exc)})
    return results


def mark_auto_final_done(key: str):
    _AUTO_FINAL_DONE.add(key)


def auto_final_already_done(key: str) -> bool:
    return key in _AUTO_FINAL_DONE


def reset_auto_final_done():
    _AUTO_FINAL_DONE.clear()


def build_auto_final_key(reservation_no: str, control_id: str, material_digest: str) -> str:
    return f"{reservation_no}|{control_id}|{material_digest}"


# [11] / hız paketi adım 1 — büyük MB51/MB52 pending taramasında seyrek SHA.
PENDING_SPARSE_SOURCES = frozenset({'MB51', 'MB52'})
PENDING_SPARSE_MIN_BYTES = 8 * 1024 * 1024  # 8 MiB
PENDING_SPARSE_BLOCK = 1024 * 1024  # 1 MiB head/mid/tail


def use_pending_sparse_sha(logical: str, total_size: int) -> bool:
    """Büyük MB51/MB52 için pending taramasında tam hash yerine örneklemeli SHA."""
    return str(logical or '').upper() in PENDING_SPARSE_SOURCES and int(total_size or 0) >= PENDING_SPARSE_MIN_BYTES


def sparse_file_sha256(path: Path, block: int = PENDING_SPARSE_BLOCK) -> str:
    """Örneklemeli içerik özeti: boyut + baş + orta + son (publish/full SHA değil).

    Ortak yazılabilir SQLite yok; yalnız yerel/aday dosya okuması.
    """
    path = Path(path)
    size = path.stat().st_size
    h = hashlib.sha256()
    h.update(b'sparse-v1|')
    h.update(str(size).encode('ascii'))
    with path.open('rb') as stream:
        head = stream.read(block)
        h.update(head)
        if size > block * 2:
            mid = max(0, (size // 2) - (block // 2))
            stream.seek(mid)
            h.update(stream.read(block))
        if size > block:
            stream.seek(max(0, size - block))
            h.update(stream.read(block))
    return h.hexdigest()
