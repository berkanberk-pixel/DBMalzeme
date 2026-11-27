# -*- coding: utf-8 -*-
"""Talep Kontrol - kontrollu ve atomik manifest yayini (yalnizca stdlib)."""
from __future__ import annotations
import argparse, contextlib, copy, datetime as dt, hashlib, json, os, pathlib, shutil, sys, uuid, zipfile, unicodedata

PRODUCT = 'Talep Kontrol'
REQUIRED = {'indexed_engine.py', 'AUTO_BASLAT.ps1', 'operations-experience.css', 'startup_runner.py', 'assets/brand/talep-kontrol.ico.png', 'data_architecture_v2.py', 'central_security.py', 'central_index_snapshot.py', 'mb51_reconciliation.py', 'windows_launcher.py', 'f604_summary.py', 'brand-v1.css', 'Talep Kontrol.vbs', 'export-utils.js', 'operations-work.js', 'styles.css', 'webgl-themes28l.css', 'desktop-status.js', 'form-elements.css', 'capacity_projection.py', 'help-ui.css', 'assets/brand/talep-kontrol-kurumsal.png', 'responsive.css', 'ux28j.css', 'WEBVIEW2_HAZIRLA.ps1', 'app.js', 'project_ids28r.py', 'PYTHON_BOOTSTRAP.ps1', 'commitment_balances.py', 'START_GUI.ps1', 'desktop-status.css', 'index.html', 'operations-experience.js', 'operations-tables.js', 'config.json', 'parquet_minimal.py', 'form_excel.py', 'capacity_source_facts.py', 'amount-analysis.css', 'ux28j.js', 'help-ui.js', 'kesif_drafts28q.py', 'otomatik_guncelleyici.py', 'operations-work.css', 'control_read_index.py', 'operations_aggregation.py', 'server.py', 'webgl-themes28l.js', 'source_row_diff.py'}

def digest(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda: f.read(1024*1024), b''):
            h.update(part)
    return h.hexdigest()

def validate_zip(path: pathlib.Path) -> None:
    if not path.is_file(): raise RuntimeError(f'ZIP bulunamadi: {path}')
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None: raise RuntimeError('ZIP butunluk testi basarisiz.')
        names = []
        seen=set()
        total = 0
        for info in z.infolist():
            if info.is_dir(): continue
            p = pathlib.PurePosixPath(info.filename)
            if p.is_absolute() or '..' in p.parts or len(p.parts) < 2 or p.parts[0] != PRODUCT:
                raise RuntimeError(f'ZIP icindeki yol guvenli degil: {info.filename}')
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise RuntimeError(f'Sembolik bag desteklenmiyor: {info.filename}')
            if _repair_path(info.filename,False)!=info.filename:raise RuntimeError('ZIP ürün kökü veya dosya yolu geçersiz.')
            name='/'.join(p.parts[1:])
            if name.casefold() in seen:raise RuntimeError('ZIP içinde tekrarlanan dosya adı var: '+name)
            seen.add(name.casefold())
            names.append('/'.join(p.parts[1:]))
            total += info.file_size
        if len(names) > 3000 or total > 1_000_000_000:
            raise RuntimeError('ZIP paket boyutu veya dosya sayisi siniri asildi.')
        missing = REQUIRED - set(names)
        if missing: raise RuntimeError('Gerekli dosyalar eksik: '+', '.join(sorted(missing)))
        # The published client must self-update on the next application launch.
        cfg = json.loads(z.read(PRODUCT+'/config.json').decode('utf-8-sig'))
        if cfg.get('shared_writes_enabled') is True:raise RuntimeError('Yetkilendirilmemiş merkezi yazma açan paket reddedildi.')
        if not str(cfg.get('external_root','')).startswith('\\\\'):raise RuntimeError('Ortak ağ kaynak kökü eksik.')
        if cfg.get('auto_install_updates') is not True:
            raise RuntimeError('Aday uygulamada otomatik güncelleme kapalı.')
        if not str(cfg.get('update_share','')).endswith('\\9-Uygulama\\Aktif'):
            raise RuntimeError('Aday uygulamanın güncelleme yolu 9-Uygulama\\Aktif olmalı.')
        raw = z.read(PRODUCT+'/Talep Kontrol.vbs')
        vbs = raw.decode('utf-16' if raw.startswith(b'\xff\xfe') else 'utf-8-sig')
        if 'AUTO_BASLAT.ps1' not in vbs:
            raise RuntimeError('Aday uygulamanın masaüstü başlatıcısı otomatik güncelleyiciye bağlı değil.')



def _repair_path(name: str, is_dir: bool) -> str:
    """Convert a safe ZIP entry to the required product-rooted location.

    Never interpret traversal, absolute, Windows-special or ambiguous names.
    """
    raw = name[:-1] if is_dir and name.endswith('/') else name
    if (not raw or raw.startswith('/') or '\\' in raw or '\x00' in raw
            or raw.startswith('//') or any(part in ('', '.', '..') for part in raw.split('/'))):
        raise RuntimeError('Güvensiz ZIP yolu otomatik düzeltilemez: ' + repr(name))
    parts = raw.split('/')
    if any(':' in part or part.endswith((' ', '.')) or
           any(c in part for c in '<>"|?*') or
           any(ord(c) < 32 for c in part) for part in parts):
        raise RuntimeError('Windows uyumsuz ZIP yolu: ' + repr(name))
    # Windows reserved names cannot be safely extracted, even with extensions.
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {'COM'+str(i) for i in range(1, 10)} | {'LPT'+str(i) for i in range(1, 10)}
    if any(part.split('.')[0].upper() in reserved for part in parts):
        raise RuntimeError('Windows ayrılmış dosya adı: ' + repr(name))
    if parts[0] != PRODUCT:
        parts.insert(0, PRODUCT)
    fixed = '/'.join(parts) + ('/' if is_dir else '')
    return fixed


def _scan_repair_plan(z: zipfile.ZipFile):
    """Return all mapped ZIP records; raise before writing on unsafe/conflicts."""
    plan, keys, files = [], set(), set()
    total, count, relocated = 0, 0, 0
    for info in z.infolist():
        name = _repair_path(info.filename, info.is_dir())
        mode = (info.external_attr >> 16) & 0o170000
        if mode not in (0, 0o100000, 0o040000) or (mode == 0o040000 and not info.is_dir()):
            raise RuntimeError('Desteklenmeyen ZIP dosya türü: '+info.filename)
        # Windows is case-insensitive and normalizes Unicode equivalences.
        key = unicodedata.normalize('NFC', name.rstrip('/')).casefold()
        if key in keys:
            raise RuntimeError('Çakışan ZIP yolları; otomatik düzeltme durduruldu: '+name)
        keys.add(key)
        if not info.is_dir():
            count += 1
            total += info.file_size
            files.add(key)
            if total > 1_000_000_000 or count > 3000:
                raise RuntimeError('ZIP boyutu veya dosya sayısı sınırı aşıldı.')
        plan.append((info, name))
        if name != info.filename:
            relocated += 1
    # No file may be the parent of any other path.
    for _info, name in plan:
        path = unicodedata.normalize('NFC', name.rstrip('/')).casefold()
        parents = path.split('/')[:-1]
        if any('/'.join(parents[:j]) in files for j in range(1, len(parents)+1)):
            raise RuntimeError('ZIP içinde dosya/klasör çakışması: '+name)
    return plan, relocated


def repair_candidate_zip(root: pathlib.Path):
    """Explicit, administrator-approved repair of safe misplaced files.

    Retain a complete untouched original ZIP in Hazırlık/Yedekler and atomically
    install the rebuilt candidate. Does not publish or approve anything.
    """
    candidate = root / 'Hazırlık' / 'TalepKontrol.zip'
    if not candidate.is_file():
        raise RuntimeError('Hazırlık klasöründe TalepKontrol.zip bulunamadı.')
    with publication_lock(root):
        old_sha = digest(candidate)
        backup_dir = root / 'Hazırlık' / 'Yedekler'
        backup = backup_dir / ('TalepKontrol_' + old_sha[:16] + '.zip')
        tmp = candidate.with_name('.TalepKontrol_onarim_'+uuid.uuid4().hex+'.tmp')
        try:
            # Source ZIP must be closed before os.replace on Windows.
            with zipfile.ZipFile(candidate, 'r') as src:
                if src.testzip() is not None:
                    raise RuntimeError('ZIP bütünlük testi başarısız; bozuk dosya onarılamaz.')
                plan, relocated = _scan_repair_plan(src)
                if not relocated:
                    validate_zip(candidate)
                    return {'changed': False, 'relocated': 0, 'backup': '', 'sha256': old_sha}
                with zipfile.ZipFile(tmp, 'w', allowZip64=True) as dest:
                    for info, newname in plan:
                        copied = copy.copy(info)
                        copied.filename = newname
                        if info.is_dir():
                            dest.writestr(copied, b'')
                        else:
                            with src.open(info, 'r') as reader, dest.open(copied, 'w', force_zip64=True) as writer:
                                shutil.copyfileobj(reader, writer, 1024*1024)
            validate_zip(tmp)
            # Verify the previous package has not changed mid-process.
            if digest(candidate) != old_sha:
                raise RuntimeError('Hazırlık ZIP dosyası onarım sırasında değişti. İşlem iptal edildi.')
            backup_dir.mkdir(parents=True, exist_ok=True)
            if backup.exists():
                if digest(backup) != old_sha:
                    raise RuntimeError('Yedek dosya adı çakışıyor. İşlem iptal edildi.')
            else:
                shutil.copy2(candidate, backup)
                if digest(backup) != old_sha:
                    backup.unlink(missing_ok=True)
                    raise RuntimeError('Yedek SHA-256 doğrulanamadı. İşlem iptal edildi.')
            os.replace(tmp, candidate)
        finally:
            tmp.unlink(missing_ok=True)
    return {'changed': True, 'relocated': relocated, 'backup': str(backup), 'sha256': digest(candidate)}

def write_json_atomic(path: pathlib.Path, data: dict):
    tmp = path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)

def manifest_parts(data):
    if data.get('product') != PRODUCT or data.get('schema') != 1:
        raise RuntimeError('Aktif manifest semasi gecersiz.')
    pkg = data.get('package', '')
    pos = pathlib.PurePosixPath(pkg)
    if pos.is_absolute() or '..' in pos.parts or len(pos.parts) != 3 or pos.parts[0] != 'Paketler' or pos.parts[2] != 'TalepKontrol.zip' or data.get('release_id') != pos.parts[1]:
        raise RuntimeError('Aktif manifest paket yolu gecersiz.')
    if not all(c.isascii() and (c.isalnum() or c in '-_') for c in pos.parts[1]) or pkg != pos.as_posix():
        raise RuntimeError('Yayın paket yolu geçersiz.')
    return pos.parts

def load_manifest(root: pathlib.Path):
    path = root/'Aktif'/'manifest.json'
    if not path.exists(): return None
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    manifest_parts(data)
    return data

def check(root):
    print('Yayin klasoru:',root)
    s = root/'Hazırlık'/'TalepKontrol.zip'
    if s.exists():
        validate_zip(s)
        print('Hazirlik: ZIP tamam;',s.stat().st_size,'bayt;',digest(s))
    else: print('Hazirlik: TalepKontrol.zip bulunmadi.')
    active = load_manifest(root)
    if not active:
        print('Aktif: onayli yayin bulunmuyor (dogru baslangic durumu).')
        return
    pkg = root/'Aktif'/pathlib.Path(*pathlib.PurePosixPath(active['package']).parts)
    if not pkg.is_file(): raise RuntimeError(f'Aktif ZIP bulunamadi: {pkg}')
    h=digest(pkg)
    if h!=active.get('sha256') or pkg.stat().st_size!=active.get('size_bytes'):
        raise RuntimeError('Aktif paket ozeti veya boyutu manifestle uyusmuyor!')
    validate_zip(pkg)
    print('Aktif: DOGRULANDI; yayin kodu:',active.get('release_id'))
    print('Paket:',pkg)

def validate_acceptance(root: pathlib.Path, sha: str | None = None) -> str:
    """Gömülü pilot kabul listesinin 15/15 tamamlandığını doğrular."""
    import pilot_kabul
    if sha is None:
        candidate = root/'Hazırlık'/'TalepKontrol.zip'
        validate_zip(candidate)
        sha = digest(candidate)
    return pilot_kabul.validate_completed(root, sha)


def _publish_unlocked(root, approved, *, publisher=None):
    if not approved: raise RuntimeError('Yayın için açık işlem onayı gerekir.')
    candidate = root/'Hazırlık'/'TalepKontrol.zip'
    validate_zip(candidate)
    sha=digest(candidate)
    if publisher is None:
        acceptance_sha=validate_acceptance(root, sha)
        status_path = root/'Hazırlık'/'ADAY_DURUMU.json'
        if not status_path.is_file():
            raise RuntimeError('Pilot onay kaydı bulunamadı. Yönetim Paneli üzerinden onaylayın.')
        status = json.loads(status_path.read_text(encoding='utf-8-sig'))
        if (status.get('status') != 'TEST_EDILDI' or status.get('sha256') != sha or
            status.get('acceptance_sha256') != acceptance_sha or
            not status.get('checked_by') or not status.get('approved_utc')):
            raise RuntimeError('Aday SHA-256 ile eşleşen eksiksiz pilot onayı yok.')
    prior=load_manifest(root)
    if prior and prior.get('sha256')==sha:
        print('Bu paket zaten Aktif; islem yapilmadi.');return
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    release=stamp+'-'+sha[:12]
    destdir=root/'Aktif'/'Paketler'/release
    if destdir.exists(): raise RuntimeError('Yayin hedefi zaten var; yeniden deneyin.')
    destdir.mkdir(parents=True,exist_ok=False)
    dest=destdir/'TalepKontrol.zip'
    tmp=destdir/'.TalepKontrol.tmp'
    try:
        shutil.copy2(candidate,tmp)
        if digest(tmp)!=sha: raise RuntimeError('Kopya ZIP ozeti tutmuyor.')
        os.replace(tmp,dest)
        manifest={
            'schema':1,'product':PRODUCT,'release_id':release,
            'package':'Paketler/'+release+'/TalepKontrol.zip',
            'sha256':sha,'size_bytes':dest.stat().st_size,
            'published_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'approval':'MANUEL_TEST_VE_YETKILI_ONAY' if publisher is None else 'PILOT_TESTI_YAPILMADI',
            'published_by':publisher or '',
            'notes':'Merkezi kayit guvenligi bu paketle otomatik acilmaz.'
        }
        if prior:
            archive=root/'Arşiv'/(stamp+'-onceki')
            archive.mkdir(parents=True,exist_ok=False)
            write_json_atomic(archive/'manifest.json',prior)
            (archive/'OKU.txt').write_text('Eski paketin kopyasi Aktif/Paketler altinda tutulur; geri alma araci bu manifesti kullanir.\n',encoding='utf-8')
        # Tek atomik gorunur islem: manifest guncelleme. Eski paketler saklanir.
        write_json_atomic(root/'Aktif'/'manifest.json',manifest)
        print('YAYIN AKTIF:',release,'\nPaket:',dest)
        print('Eski paketler, aktif indirme yarida kesilmesin diye otomatik silinmez.')
    finally:
        tmp.unlink(missing_ok=True)

def _rollback_unlocked(root, archive_name, approved):
    if not approved: raise RuntimeError('Geri alma icin --onay gereklidir.')
    archives=root/'Arşiv'
    name=pathlib.Path(archive_name).name
    old=archives/name/'manifest.json'
    if not old.is_file(): raise RuntimeError('Arsiv manifesti bulunamadi: '+name)
    candidate=json.loads(old.read_text(encoding='utf-8-sig'))
    pkg=root/'Aktif'/pathlib.Path(*manifest_parts(candidate))
    if not pkg.is_file() or pkg.stat().st_size != candidate.get('size_bytes') or digest(pkg)!=candidate.get('sha256'):
        raise RuntimeError('Geri alinacak paket yok ya da SHA-256 eslesmiyor; islem durduruldu.')
    current=load_manifest(root)
    if current:
        stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        a=archives/(stamp+'-geri-almadan-once');a.mkdir(parents=True,exist_ok=False)
        write_json_atomic(a/'manifest.json',current)
    write_json_atomic(root/'Aktif'/'manifest.json',candidate)
    print('GERI ALINDI:',candidate.get('release_id'))

@contextlib.contextmanager
def publication_lock(root):
    """SMB ustunde atomik mkdir ile cift yayinlamayi engelle."""
    lockdir = root/'Yonetim'/'.yayin_kilidi'
    try:
        lockdir.mkdir(exist_ok=False)
    except FileExistsError:
        raise RuntimeError('Başka yayın/geri alma işlemi çalışıyor. Yayın kilidi kontrol edilmeli.')
    try:
        yield
    finally:
        # Bir kilit kalirsa aktif islem olmadigini BT dogrulamalidir.
        lockdir.rmdir()

def publish(root, approved):
    with publication_lock(root):
        return _publish_unlocked(root, approved)

def rollback(root, archive_name, approved):
    with publication_lock(root):
        return _rollback_unlocked(root, archive_name, approved)

def main():
    p=argparse.ArgumentParser(description='Talep Kontrol yayini yonetimi')
    p.add_argument('islem',choices=['kontrol','yayinla','geri-al'])
    p.add_argument('--root',type=pathlib.Path,default=pathlib.Path(__file__).resolve().parent.parent)
    p.add_argument('--onay',action='store_true',help='Yetkili test ve yayin onayi alindi')
    p.add_argument('--arsiv',help='Geri alinacak Arsiv alt klasorunun adi')
    a=p.parse_args();root=a.root.resolve()
    if a.islem=='kontrol': check(root)
    elif a.islem=='yayinla':publish(root,a.onay)
    else:
        if not a.arsiv: raise RuntimeError('Geri alma icin --arsiv klasoradi gereklidir.')
        rollback(root,a.arsiv,a.onay)
if __name__=='__main__':
    try: main()
    except Exception as e:
        print('[ISLEM DURDURULDU]',e,file=sys.stderr);sys.exit(1)
