"""Kaynak satır farkı: iş anahtarına göre yeni / değişen / eksilen satırlar."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def _norm_header(value: Any) -> str:
    text = str(value or '').strip().lower().replace('ı', 'i')
    text = unicodedata.normalize('NFD', text)
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    return re.sub(r'[^a-z0-9]+', '', text)


def _norm_cell(value: Any) -> str:
    return str(value or '').strip()


FIELD_ALIASES = {
    'reservation': {_norm_header(x) for x in ('Rezervasyon', 'Rezervasyon No', 'Rezervasyon Numarası')},
    'material': {_norm_header(x) for x in ('Malzeme', 'Malzeme Kodu', 'Malzeme_Kodu')},
    'material_doc': {_norm_header(x) for x in ('Malzeme belgesi', 'Malzeme Belgesi')},
    'doc_year': {_norm_header(x) for x in ('Malzeme belgesi yılı', 'Belge yılı', 'Mali yıl')},
    'doc_item': {_norm_header(x) for x in ('Malzeme belgesi kalemi', 'Belge kalemi', 'Kalem')},
    # ZMM048 rezervasyon kalemi (F-001) — 'Kalem' ile kesişir; ayrıca özel başlıklar.
    'res_item': {_norm_header(x) for x in (
        'Kalem', 'Rezervasyon kalemi', 'Rezervasyon Kalemi', 'Kalem No', 'Kalem numarası',
        'Item', 'Item No', 'Sıra', 'Sıra No',
    )},
    'movement': {_norm_header(x) for x in ('İşlem türü', 'Hareket türü')},
    'plant': {_norm_header(x) for x in ('Üretim yeri', 'UY')},
    'storage': {_norm_header(x) for x in ('Depo yeri', 'DY', 'Depo Kodu', 'Depo_Yeri')},
    'depot_code': {_norm_header(x) for x in ('Depo Kodu',)},
    'valuation_type': {_norm_header(x) for x in ('Parti', 'Değerleme türü', 'Değerleme Türü')},
    'project': {_norm_header(x) for x in ('Proje', 'Proje Adı', 'Proje_Adi')},
    'work_type': {_norm_header(x) for x in ('İş Türü', 'İş Türü Kodu', 'Is_Turu')},
    'source_uy': {_norm_header(x) for x in ('TESLİM EDEN ÜY', 'Kaynak ÜY')},
    'source_dy': {_norm_header(x) for x in ('TESLİM EDEN DY', 'Kaynak Depo')},
    'target_uy': {_norm_header(x) for x in ('TESLİM ALAN ÜY', 'Hedef ÜY')},
    'target_dy': {_norm_header(x) for x in ('Teslim alan DY', 'Hedef Depo')},
    'project_id': {_norm_header(x) for x in ('Proje ID', 'Proje_ID')},
}


# Kaynak türüne göre iş anahtarı alanları (prompt §4 + F-001 kalem).
BUSINESS_KEYS = {
    'MB51': ('material_doc', 'doc_year', 'doc_item', 'movement', 'plant', 'storage'),
    'MB52': ('plant', 'storage', 'material', 'valuation_type'),
    'ZMM048': ('reservation', 'material', 'res_item', 'source_uy', 'source_dy', 'target_uy', 'target_dy'),
    'ZMM098': ('plant', 'storage'),
    'KESIFLER': ('depot_code', 'material', 'project', 'work_type'),
    'TANIMLAR': ('plant', 'storage', 'project_id', 'material'),
}

# Anahtarlı satır delta'sı (F-003): ZMM098/MB52 DELETE+INSERT.
# ZMM048 indeks şemasında kalem kolonu yok → tablo reload (diff yine kalemli).
# MB51/KESIF/TANIMLAR → kaynak tablosu reload.
DELTA_SOURCES = frozenset({'MB52', 'ZMM098'})
# Delta anahtar listesi çok büyürse tam tablo reload'a düş.
DELTA_KEY_CAP = 50_000


def _col_index(headers: Sequence[str], group: str) -> int:
    aliases = FIELD_ALIASES.get(group, set())
    for i, header in enumerate(headers):
        if _norm_header(header) in aliases:
            return i
    return -1


def _row_payload(row: Sequence[str]) -> str:
    cells = [_norm_cell(x) for x in row]
    while cells and cells[-1] == '':
        cells.pop()
    return '\u001f'.join(cells)


def _row_digest(payload: str) -> str:
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _open_rows(path: Path, delimiter: str = ';', encoding: str = 'utf-8-sig', header_row: int = 0):
    with path.open('r', encoding=encoding, errors='replace', newline='') as handle:
        reader = csv.reader(handle, delimiter=delimiter or ';')
        headers = None
        for index, row in enumerate(reader):
            if index < header_row:
                continue
            if headers is None:
                headers = [str(x or '').strip() for x in row]
                continue
            if not any(_norm_cell(x) for x in row):
                continue
            yield headers, row


def _business_key_parts(headers: Sequence[str], row: Sequence[str], source: str, role: str = '') -> List[str]:
    source = str(source or '').upper()
    key_fields = BUSINESS_KEYS.get(source) or ()
    parts: List[str] = []
    for field in key_fields:
        idx = _col_index(headers, field)
        if field == 'depot_code' and idx < 0:
            idx = _col_index(headers, 'storage')
        if field == 'res_item' and idx < 0:
            # Kalem yoksa boş bırak; çakışmada occurrence disambiguation devreye girer.
            parts.append('')
            continue
        if field == 'work_type' and idx < 0 and role:
            parts.append(_norm_cell(role).upper())
            continue
        parts.append(_norm_cell(row[idx]) if idx >= 0 and idx < len(row) else '')
    return parts


def map_rows(path: Path, source: str, *, delimiter: str = ';', encoding: str = 'utf-8-sig',
             header_row: int = 0, role: str = '') -> Dict[str, str]:
    """İş anahtarı -> satır özeti (digest).

    Aynı anahtarda birden fazla farklı satır varsa (kalemsiz mükerrer / F-001)
    occurrence soneki (#2, #3…) ile kayıpsız tutulur. Aynı anahtar+aynı digest
    tekrarında üzerine yazılır.
    """
    source = str(source or '').upper()
    mapped: Dict[str, str] = {}
    occurrence: Dict[str, int] = {}
    file_path = Path(path)
    if not file_path.is_file():
        return mapped
    for headers, row in _open_rows(file_path, delimiter=delimiter, encoding=encoding, header_row=header_row):
        parts = _business_key_parts(headers, row, source, role=role)
        if not any(parts):
            continue
        base = '|'.join(parts)
        digest = _row_digest(_row_payload(row))
        occ = occurrence.get(base, 0) + 1
        occurrence[base] = occ
        key = base if occ == 1 else f'{base}#{occ}'
        # Aynı occurrence slot'unda yeniden yaz (nadir); çakışmada yeni slot.
        if key in mapped and mapped[key] != digest:
            occ = occurrence[base] + 1
            occurrence[base] = occ
            key = f'{base}#{occ}'
        mapped[key] = digest
    return mapped


def map_source_info(info: Optional[Dict[str, Any]], source: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not info:
        return out
    for entry in info.get('files') or []:
        path = Path(entry.get('path') or '')
        role = str(entry.get('role') or '')
        mapped = map_rows(
            path,
            source,
            delimiter=str(entry.get('delimiter') or ';'),
            encoding=str(entry.get('encoding') or 'utf-8-sig'),
            header_row=int(entry.get('headerRow') or 0),
            role=role,
        )
        # Rol ayrımı (TESİS/KET…): anahtara rol ekle ki çakışmasın.
        prefix = (role.upper() + '::') if role else ''
        for key, digest in mapped.items():
            out[prefix + key] = digest
    return out


def diff_maps(old_rows: Dict[str, str], new_rows: Dict[str, str], *,
              include_keys: bool = True, key_cap: int = DELTA_KEY_CAP) -> Dict[str, Any]:
    old_keys = set(old_rows)
    new_keys = set(new_rows)
    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    changed = sorted(k for k in (old_keys & new_keys) if old_rows[k] != new_rows[k])
    unchanged = len(old_keys & new_keys) - len(changed)
    delta_keys = len(added) + len(changed) + len(removed)
    result: Dict[str, Any] = {
        'added': len(added),
        'changed': len(changed),
        'removed': len(removed),
        'unchanged': unchanged,
        'totalOld': len(old_rows),
        'totalNew': len(new_rows),
        'hasChanges': bool(added or changed or removed),
        'sampleAdded': added[:8],
        'sampleChanged': changed[:8],
        'sampleRemoved': removed[:8],
        'deltaKeyCount': delta_keys,
        'deltaKeysCapped': bool(include_keys and delta_keys > key_cap),
    }
    if include_keys and delta_keys <= key_cap:
        result['addedKeys'] = added
        result['changedKeys'] = changed
        result['removedKeys'] = removed
    return result


def diff_source_infos(old_info: Optional[Dict[str, Any]], new_info: Optional[Dict[str, Any]],
                      source: str, *, include_keys: bool = True) -> Dict[str, Any]:
    old_map = map_source_info(old_info, source)
    new_map = map_source_info(new_info, source)
    result = diff_maps(old_map, new_map, include_keys=include_keys)
    result['source'] = str(source or '').upper()
    result['supportsRowDelta'] = (
        str(source or '').upper() in DELTA_SOURCES
        and bool(result.get('hasChanges'))
        and not result.get('deltaKeysCapped')
        and 'addedKeys' in result
    )
    return result


def write_diff_record(directory: Path, source: str, diff: Dict[str, Any], actor: str = '') -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = diff.get('acceptedAt') or ''
    # Disk kaydında tam anahtar listelerini düşür (MB51 şişkinliği); sample kalsın.
    slim = {k: v for k, v in diff.items() if k not in ('addedKeys', 'changedKeys', 'removedKeys')}
    name = f"{str(source or 'SOURCE').upper()}_{hashlib.sha256(json.dumps(slim, sort_keys=True).encode()).hexdigest()[:12]}.json"
    path = directory / name
    payload = {**slim, 'actor': actor, 'writtenAt': stamp}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def strip_delta_keys(diff: Dict[str, Any]) -> Dict[str, Any]:
    """Audit/response için anahtar listelerini çıkar (hafif payload)."""
    if not diff:
        return diff
    return {k: v for k, v in diff.items() if k not in ('addedKeys', 'changedKeys', 'removedKeys')}
