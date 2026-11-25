# -*- coding: utf-8 -*-
"""Talep Kontrol - yayın adayı için uygulama-içi pilot kabul kayıtları.

Excel/CSV kullanılmaz. Test tanımları gömülüdür; yönetici ekranında
metinler ve sonuçlar düzenlenir. JSON yalnızca kalıcı saklama biçimidir.
Yayın onayı hem aday ZIP SHA-256 hem test kaydı özetiyle eşleştirilir.
"""
from __future__ import annotations
import contextlib
import datetime as dt
import getpass
import hashlib
import json
import os
from pathlib import Path
import uuid

DEFAULT_ITEMS = [
    ('Yayıncı erişimi', 'Yetkili yayınlama kullanıcısı paket yayımlayabilir.'),
    ('Kullanıcı erişimi', 'Kullanıcı Aktif yayınını okuyabilir ancak değiştiremez.'),
    ('ZIP doğrulaması', 'Güncelleme paketinin bütünlüğü doğrulanır.'),
    ('Windows GUI açılışı', 'Komut penceresi görünmez ve uygulama arayüzü açılır.'),
    ('Pencere kontrolleri', 'Büyütme, küçültme, taşıma ve kapatma çalışır.'),
    ('Kaynak erişimi', 'ZMM048, MB51, MB52, ZMM098 ve keşif kaynakları doğrulanır.'),
    ('SQLite indeks hazırlığı', 'İndeks oluşur ve filtreler gerçek veri üzerinde çalışır.'),
    ('TESİS sayfası', 'Gerçek tesis verileri hatasız yüklenir.'),
    ('BAKIM, KET ve LED sayfaları', 'Gerçek veriler hatasız yüklenir.'),
    ('Kontrol geçmişi', 'Kontrol geçmişi çalışır; kritik erişim hatası yaşanmaz.'),
    ('Merkezi kayıt güvenliği', 'Yetkisiz kesin kayıt işlemi engellenir.'),
    ('Kapanış', 'Yalnız uygulamanın kendi servis süreci kapanır.'),
    ('Yerel güncelleme', 'Kullanıcı pilot ortamında güncellemeyi başarıyla tamamlar.'),
    ('Ağ kesintisi', 'Ağ kesintisinde son doğrulanmış paket korunur.'),
    ('Geri alma', 'Önceki onaylı pakete dönüş pilot ortamda doğrulanır.'),
]
STATUSES = ('TEST_EDILMEDI', 'BASARILI', 'BASARISIZ')


def data_path(root: Path) -> Path:
    return root / 'Hazırlık' / 'pilot_test_kayitlari.json'


def _empty(candidate_sha: str, source: dict | None = None) -> dict:
    """Yeni adayda önceki test başlıklarını korur, sonuçları sıfırlar."""
    prior = {}
    if isinstance(source, dict):
        for row in source.get('items', []):
            if isinstance(row, dict) and type(row.get('id')) is int:
                prior[row['id']] = row
    items = []
    for no, (title, expected) in enumerate(DEFAULT_ITEMS, 1):
        previous = prior.get(no, {})
        items.append(dict(id=no, title=previous.get('title', title),
                          expected=previous.get('expected', expected), status='TEST_EDILMEDI',
                          responsible='', date='', note='', updatedAt='', updatedBy=''))
    return {'schema': 1, 'candidateSha256': candidate_sha, 'savedAt': '', 'items': items}


def _assert_sha(sha: str):
    if not isinstance(sha, str) or len(sha) != 64 or any(ch not in '0123456789abcdef' for ch in sha.lower()):
        raise ValueError('Geçersiz aday paket özeti.')


def _read(root: Path, sha: str) -> dict:
    _assert_sha(sha)
    path = data_path(root)
    if not path.exists():
        return _empty(sha)
    try:
        doc = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise RuntimeError('Pilot test kayıtları okunamadı; kayıt bozulmuş olabilir. Dosya korunmuştur.') from exc
    if not isinstance(doc, dict) or doc.get('schema') != 1:
        raise RuntimeError('Pilot test kayıt şeması geçersiz.')
    if doc.get('candidateSha256') != sha:
        return _empty(sha, doc)
    _validate_document(doc)
    return doc


def _validate_document(doc: dict):
    rows = doc.get('items')
    if not isinstance(rows, list) or len(rows) != 15 or [r.get('id') if isinstance(r, dict) else None for r in rows] != list(range(1, 16)):
        raise RuntimeError('Pilot kabul listesi tam 15 maddeden oluşmalıdır.')
    for item in rows:
        if item.get('status') not in STATUSES:
            raise RuntimeError(f"{item['id']}. madde durum değeri geçersiz.")
        for key in ('title', 'expected', 'responsible', 'date', 'note', 'updatedAt', 'updatedBy'):
            if not isinstance(item.get(key), str):
                raise RuntimeError(f"{item['id']}. madde alanı geçersiz: {key}")


def load(root: Path, sha: str) -> dict:
    data = _read(root, sha)
    summary = {status: sum(i['status'] == status for i in data['items']) for status in STATUSES}
    return {**data, 'summary': {'total': 15, 'passed': summary['BASARILI'],
                                'failed': summary['BASARISIZ'], 'untested': summary['TEST_EDILMEDI']}}


def _write_atomic(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with tmp.open('w', encoding='utf-8', newline='\n') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write('\n')
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


@contextlib.contextmanager
def record_lock(root: Path):
    # Ağ paylaşımında tek yazar. Yayın işlemiyle aynı kilit kullanılır.
    lock = root / 'Yonetim' / '.yayin_kilidi'
    try:
        lock.mkdir(exist_ok=False)
    except FileExistsError as exc:
        raise RuntimeError('Yayın veya pilot kayıt işlemi devam ediyor; kısa süre sonra yeniden deneyin.') from exc
    try:
        yield
    finally:
        lock.rmdir()


def _audit(root: Path, action: str, sha: str, detail: str):
    path = root / 'Yonetim' / 'pilot_test_islem_gecmisi.jsonl'
    entry = {'time': dt.datetime.now(dt.timezone.utc).isoformat(),
             'operator': getpass.getuser(), 'candidateSha256': sha,
             'action': action, 'detail': detail}
    with path.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + '\n')


def save_item(root: Path, sha: str, number: int, fields: dict) -> dict:
    if type(number) is not int or number not in range(1, 16):
        raise ValueError('Test numarası 1-15 arasında olmalıdır.')
    limits = {'title': 150, 'expected': 600, 'status': 20, 'responsible': 120, 'date': 10, 'note': 4000}
    for name, limit in limits.items():
        if not isinstance(fields.get(name), str) or len(fields[name]) > limit:
            raise ValueError(f'{name}: Eksik veya çok uzun alan.')
    if not fields['title'].strip() or not fields['expected'].strip():
        raise ValueError('Test adı ve beklenen sonuç boş bırakılamaz.')
    if fields['status'] not in STATUSES:
        raise ValueError('Test sonucu geçersiz.')
    if fields['date']:
        try:
            if dt.date.fromisoformat(fields['date']).isoformat() != fields['date']:
                raise ValueError()
        except ValueError as exc:
            raise ValueError('Tarih YYYY-AA-GG biçiminde olmalıdır.') from exc
    if fields['status'] == 'BASARILI' and (not fields['responsible'].strip() or not fields['date']):
        raise ValueError('Başarılı testte sorumlu ve tarih zorunludur.')
    with record_lock(root):
        data = _read(root, sha)
        # Dizinde bulunan aday dosyası, ekrandaki paketle aynı olmalıdır.
        from yayin_yonetimi import digest
        candidate = root / 'Hazırlık' / 'TalepKontrol.zip'
        if not candidate.is_file() or digest(candidate) != sha:
            raise RuntimeError('Yayın adayı değişti. Test listesini yenileyip tekrar kontrol edin.')
        row = data['items'][number - 1]
        for key in limits:
            row[key] = fields[key].strip()
        row['updatedAt'] = dt.datetime.now().astimezone().isoformat(timespec='seconds')
        row['updatedBy'] = getpass.getuser()
        data['savedAt'] = row['updatedAt']
        _write_atomic(data_path(root), data)
        _audit(root, 'TEST_DUZENLENDI', sha, f"{number}: {fields['status']}")
    return load(root, sha)


def reset_results(root: Path, sha: str):
    with record_lock(root):
        from yayin_yonetimi import digest
        if digest(root / 'Hazırlık' / 'TalepKontrol.zip') != sha:
            raise RuntimeError('Yayın adayı değişti. Önce ekranı yenileyin.')
        data = _read(root, sha)
        for row in data['items']:
            row.update(status='TEST_EDILMEDI', responsible='', date='', note='', updatedAt='', updatedBy='')
        data['savedAt'] = dt.datetime.now().astimezone().isoformat(timespec='seconds')
        _write_atomic(data_path(root), data)
        _audit(root, 'TEST_SONUCLARI_SIFIRLANDI', sha, '15 test sonucu sıfırlandı; başlıklar korundu')
    return load(root, sha)


def fingerprint(doc: dict) -> str:
    """Onayın kapsadığı test verilerinin değişmez parmak izi."""
    _validate_document(doc)
    data = {'candidateSha256': doc['candidateSha256'], 'items': doc['items']}
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def validate_completed(root: Path, sha: str) -> str:
    data = _read(root, sha)
    missing = [str(row['id']) for row in data['items'] if row['status'] != 'BASARILI' or
               not row['responsible'].strip() or not row['date'] or
               not row['title'].strip() or not row['expected'].strip()]
    if missing:
        raise RuntimeError('Tüm 15 test Başarılı olmalı; tarih ve sorumlu da girilmeli. Eksik: ' + ', '.join(missing))
    return fingerprint(data)
