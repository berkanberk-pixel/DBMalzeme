from contextlib import redirect_stdout
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import io
import json
import os
import re
import secrets
import subprocess
import threading
import sys
import traceback
import webbrowser
import http.client
from urllib.parse import urlencode

PANEL = Path(__file__).resolve().parent
sys.path.insert(0, str(PANEL))
import yayin_yonetimi as engine
ROOT = PANEL.parent
PREP = ROOT / 'Hazırlık'
PACKAGE = PREP / 'TalepKontrol.zip'
ARCHIVE = ROOT / 'Arşiv'
ACCESS = ROOT / 'Panel-Yetkileri' / 'PANEL_YETKILERI.json'
AUDIT = PANEL / 'PANEL_ISLEM_GUNLUGU.jsonl'
ADMIN = r'CEDAS\halit.ozdemir'
USER_PATTERN = re.compile(r'[\w.-]+\\[\w.@-]+')
LOG_ROOT = Path(os.environ.get('LOCALAPPDATA', '.')) / 'TalepKontrol'
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.RLock()


def windows_account():
    tool = Path(os.environ['SystemRoot']) / 'System32' / 'whoami.exe'
    raw = subprocess.check_output([str(tool)], creationflags=subprocess.CREATE_NO_WINDOW,
                                  text=True, encoding='oem', timeout=10)
    account = raw.strip()
    if not USER_PATTERN.fullmatch(account):
        raise RuntimeError('Windows oturum hesabı doğrulanamadı.')
    return account


def users():
    records = json.loads(ACCESS.read_text(encoding='utf-8-sig')) if ACCESS.exists() else {}
    records[ADMIN.casefold()] = {'account': ADMIN, 'role': 'Yönetici', 'enabled': True, 'shared_approval': True}
    return records


def role():
    record = users().get(ACCOUNT.casefold(), {})
    return record.get('role', 'Görüntüleyici') if record.get('enabled', True) else 'Devre dışı'


def tail(path, count=20):
    if not path.is_file():
        return ''
    with path.open('rb') as handle:
        handle.seek(max(0, path.stat().st_size - 18000))
        return '\n'.join(handle.read().decode('utf-8-sig', errors='replace').splitlines()[-count:])


def snapshot():
    active = engine.load_manifest(ROOT)
    history = []
    if ARCHIVE.is_dir():
        for folder in sorted(ARCHIVE.iterdir(), reverse=True):
            manifest = folder / 'manifest.json'
            if manifest.is_file():
                try:
                    data = json.loads(manifest.read_text(encoding='utf-8-sig'))
                    engine.manifest_parts(data)
                    history.append({'archive': folder.name, **{key: data.get(key, '') for key in
                                    ('release_id', 'published_utc', 'published_by', 'sha256')}})
                except (OSError, ValueError, RuntimeError, TypeError):
                    history.append({'archive': folder.name, 'release_id': 'Manifest okunamadı'})
    records = users()
    accounts = list(records.values())
    if ACCOUNT.casefold() not in records:
        accounts.append({'account': ACCOUNT, 'role': 'Görüntüleyici',
                         'enabled': True, 'shared_approval': False, 'inherited_view': True})
    return {'account': ACCOUNT, 'role': role(), 'root': str(ROOT), 'active': active,
            'candidate': PACKAGE.is_file(), 'history': history, 'users': accounts}


def checked_package(path):
    engine.validate_zip(path)
    return {'sha256': engine.digest(path), 'size': path.stat().st_size}


SOURCE_NAMES = ('ZMM048','MB51','MB52','ZMM098','TANIMLAR','KESIFLER')
DISCOVERY_BASIS = 'ACTUAL_INCLUDED_PENDING_EXCLUDED'


def scope_target(data):
    result = [data.get(key, '') for key in ('targetUY', 'targetDY')]
    if any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,24}', v.strip()) for v in result):
        raise ValueError('Geçerli hedef üretim yeri ve depo kodu girin.')
    return [v.strip().upper() for v in result]


def local_context(target):
    query = urlencode(dict(zip(('targetUY', 'targetDY'), target)))
    for port in range(8765, 8770):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=30)
        try:
            connection.request('GET', '/api/health')
            response = connection.getresponse()
            health = json.loads(response.read(262144))
            if response.status != 200 or health.get('app') != 'Talep Kontrol':
                continue
            connection.request('GET', '/api/commitment-context?'+query)
            response = connection.getresponse()
            context = json.loads(response.read(8*1024*1024))
        except (OSError, ValueError, http.client.HTTPException):
            continue
        finally:
            connection.close()
        if response.status != 200 or not context.get('ok'):
            raise RuntimeError(context.get('error') or 'Talep Kontrol kapsam bilgisi alınamadı.')
        if [context.get('targetUY'), context.get('targetDY')] != target or not context.get('verified'):
            raise ValueError('Hedef depo veya ortak onay zinciri doğrulanamadı.')
        scope = context.get('coverage') or {}
        fingerprints = scope.get('sourceFingerprints')
        if not isinstance(fingerprints,dict) or set(fingerprints)!=set(SOURCE_NAMES) or not all(
            isinstance(v,str) and re.fullmatch(r'[a-f0-9]{64}',v) for v in fingerprints.values()
        ):
            raise ValueError('Altı kaynağın güncel imzaları alınamadı. Talep Kontrol’da kaynakları kontrol edin.')
        return context, {name: fingerprints[name] for name in ('KESIFLER', 'MB51')}
    raise RuntimeError('Talep Kontrol yerel hizmeti bulunamadı. Güncel Talep Kontrol uygulamasını açın.')


def local_maintenance(action):
    if role() != 'Yönetici':
        raise PermissionError('Yerel veri bakımı için Yönetici hesabı gerekir.')
    for port in range(8765, 8770):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
        try:
            connection.request('GET', '/api/health')
            response = connection.getresponse()
            if response.status != 200 or json.loads(response.read(262144)).get('app') != 'Talep Kontrol':
                continue
        except (OSError, ValueError, http.client.HTTPException):
            continue
        finally:
            connection.close()
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=1800)
        try:
            connection.request('POST', '/api/local-index-maintenance', json.dumps({'action': action}),
                               {'Content-Type':'application/json','X-Talep-Maintenance':'panel'})
            response = connection.getresponse()
            result = json.loads(response.read(262144))
        finally:
            connection.close()
        if response.status != 200:
            raise RuntimeError(result.get('error') or 'Talep Kontrol veri bakımı tamamlanamadı.')
        return result
    raise RuntimeError('Talep Kontrol uygulamasını açıp yeniden deneyin.')


def scope_records(path):
    if not path.exists():
        return []
    document = json.loads(path.read_text(encoding='utf-8-sig'))
    records = document.get('depots') if isinstance(document, dict) else None
    if not isinstance(records,list) or any(
        not isinstance(r,dict) or not isinstance(r.get('target'),list) or len(r['target'])!=2 or
        not all(isinstance(code,str) for code in r['target']) for r in records
    ):
        raise ValueError('Merkezi kapsam dosyasının biçimi geçersiz.')
    if len({tuple(r['target']) for r in records})!=len(records):
        raise ValueError('Merkezi kapsam dosyasında aynı hedef depo birden fazla kayıtlı.')
    return records


def manage_scope(action, data):
    path = ACCESS.with_name('KAYNAK_KAPSAMI.json')
    if action=='scope-list':
        return {'records': scope_records(path)}
    target = scope_target(data)
    _, fingerprints = local_context(target)
    if action=='scope-preview':
        records = scope_records(path)
        matching = next((r for r in records if [code.strip().upper() for code in r['target']]==target), None)
        return {'target':target,'fingerprints':fingerprints,'record':matching,
                'current':bool(matching and isinstance(matching.get('sourceFingerprints'), dict) and
                               all(matching['sourceFingerprints'].get(name)==value
                                   for name,value in fingerprints.items()))}
    if role()!='Yönetici':
        raise PermissionError('Kapsamı değiştirmek için Yönetici rolü gerekir.')
    if data.get('fingerprints')!=fingerprints:
        raise ValueError('İnceleme sonrasında kaynaklar değişti. Kapsamı yeniden yükleyin.')
    reference=data.get('evidenceReference')
    if data.get('confirmed') is not True or not isinstance(reference,str) or not reference.strip() or len(reference)>500:
        raise ValueError('Keşif kapsam teyidi ve SAP kanıt referansı zorunludur.')
    with engine.publication_lock(ROOT):
        records=scope_records(path)
        records=[r for r in records if [code.strip().upper() for code in r['target']]!=target]
        records.append({'target':target,'sourceFingerprints':fingerprints,'discoveryBasis':DISCOVERY_BASIS,
                        'evidenceReference':reference.strip(),
                        'changed_by':ACCOUNT,'changed_utc':datetime.now(timezone.utc).isoformat()})
        path.parent.mkdir(exist_ok=True)
        engine.write_json_atomic(path,{'depots':records})
    return {'message':f"{'/'.join(target)} keşif kapsamı kaydedildi."}


def search_windows_users(data):
    if role()!='Yönetici':
        raise PermissionError('Hesap araması için Yönetici rolü gerekir.')
    query=data.get('query')
    if not isinstance(query,str) or not re.fullmatch(r"[\w .@'-]{2,48}",query.strip()):
        raise ValueError('Arama için en az iki harf veya rakam girin.')
    tool=Path(os.environ['SystemRoot'])/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'
    command=r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
Add-Type -AssemblyName System.DirectoryServices
$domain=[System.DirectoryServices.ActiveDirectory.Domain]::GetComputerDomain()
$root=$domain.GetDirectoryEntry()
$search=New-Object System.DirectoryServices.DirectorySearcher($root)
try {
    $q=$env:TALEP_ACCOUNT_SEARCH
    $search.Filter="(&(objectCategory=person)(objectClass=user)(!(userAccountControl:1.2.840.113556.1.4.803:=2))(|(sAMAccountName=$q*)(displayName=$q*)))"
    $search.SizeLimit=20
    [void]$search.PropertiesToLoad.Add('samaccountname')
    [void]$search.PropertiesToLoad.Add('displayname')
    [void]$search.PropertiesToLoad.Add('objectsid')
    $found=$search.FindAll()
    try {
        $rows=@(foreach($row in $found){
            $props=$row.Properties
            if(!$props['objectsid'].Count){continue}
            try {
                $sid=[System.Security.Principal.SecurityIdentifier]::new([byte[]]$props['objectsid'][0],0)
                $account=$sid.Translate([System.Security.Principal.NTAccount]).Value
                [pscustomobject]@{account=$account; displayName=[string]($props['displayname']|Select-Object -First 1)}
            }catch{}
        })
        ConvertTo-Json -InputObject $rows -Compress
    } finally {$found.Dispose()}
} finally {$search.Dispose();$root.Dispose();$domain.Dispose()}
"""
    env={**os.environ,'TALEP_ACCOUNT_SEARCH':query.strip()}
    try:
        result=subprocess.run([str(tool),'-NoProfile','-NonInteractive','-Command',command],
                              env=env,encoding='utf-8',errors='replace',capture_output=True,
                              creationflags=subprocess.CREATE_NO_WINDOW,timeout=20,check=True)
        accounts=json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise RuntimeError('Windows etki alanı aranamadı. Ağ bağlantısını kontrol edin veya hesabı elle girin.') from exc
    return {'accounts':[item for item in accounts if USER_PATTERN.fullmatch(item.get('account',''))]}


def manage_permissions(action,data):
    if role()!='Yönetici':
        raise PermissionError('Windows izin ekranı için Yönetici rolü gerekir.')
    folders={'policy':ACCESS.parent,'records':ROOT.parent/'0-Database',
             'panel':PANEL,'active':ROOT/'Aktif','staging':PREP,'archive':ARCHIVE}
    path=folders.get(data.get('folder'))
    if path is None or not path.is_dir():
        raise ValueError('İstenen ortak klasör bulunamadı veya erişilemiyor.')
    if action=='permissions-open':
        import ctypes
        shell=ctypes.windll.shell32.ShellExecuteW
        shell.restype=ctypes.c_void_p
        result=shell(None,'properties',str(path),None,None,1)
        if not result or result<=32:
            raise RuntimeError('Windows klasör özellikleri açılamadı.')
        return {'message':'Windows Özellikler → Güvenlik sekmesinde izinleri görüntüleyin veya düzenleyin.'}
    tool=Path(os.environ['SystemRoot'])/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'
    command=("Get-Acl -LiteralPath $env:TALEP_PANEL_ACL_FOLDER -ErrorAction Stop | "
             "Select-Object Path,Owner,AccessToString | ConvertTo-Json -Compress")
    env={**os.environ,'TALEP_PANEL_ACL_FOLDER':str(path)}
    result=subprocess.run([str(tool),'-NoProfile','-NonInteractive','-Command',
                           '[Console]::OutputEncoding=[Text.Encoding]::UTF8; '+command],
                          env=env,encoding='utf-8',errors='replace',capture_output=True,
                          creationflags=subprocess.CREATE_NO_WINDOW,timeout=20,check=True)
    acl=json.loads(result.stdout)
    return {'message':acl['AccessToString'], 'path':str(path),'owner':acl['Owner']}


def perform(action, data):
    if action == 'check':
        results = []
        active = engine.load_manifest(ROOT)
        paths = [('Hazırlık', PACKAGE, None)]
        if active:
            paths.append(('Aktif', ROOT / 'Aktif' / Path(*engine.manifest_parts(active)), active))
        for name, path, manifest in paths:
            try:
                checked = checked_package(path)
                if manifest and (manifest['sha256'] != checked['sha256'] or manifest['size_bytes'] != checked['size']):
                    raise RuntimeError('Boyut veya SHA-256 manifest ile uyuşmuyor.')
                results.append(f"{name}: ZIP ve gerekli dosyalar doğrulandı. {checked['size']} bayt. SHA-256 {checked['sha256']}")
            except Exception as exc:
                results.append(f'{name}: {exc}')
        return '\n'.join(results)
    if action == 'diagnostics':
        temp = Path(os.environ['TEMP'])
        logs = [LOG_ROOT / 'Guncelleme' / 'baslatma.log', temp / 'YEDAS_TalepKontrol_STARTUP.log',
                temp / 'YEDAS_TalepKontrol_PYTHON_INSTALL.log', AUDIT]
        return '\n'.join([f'Yayın kökü: {ROOT}', f'Windows oturumu: {ACCOUNT}',
                          f'Ortak kayıt klasörü görünüyor: {(ROOT.parent / "0-Database").is_dir()}'] +
                         [f'\n{path}\n{tail(path) or "Günlük yok veya boş."}' for path in logs])
    if action == 'user':
        if role() != 'Yönetici':
            raise PermissionError('Kullanıcı yönetimi için Yönetici rolü gerekir.')
        account = data.get('account', '').strip()
        selected_role = data.get('role')
        display_name = data.get('displayName', '')
        if not isinstance(display_name,str) or len(display_name)>120:
            raise ValueError('Görünen ad geçersiz.')
        if (not USER_PATTERN.fullmatch(account) or account.casefold() == ADMIN.casefold()
                or selected_role not in ('Görüntüleyici', 'Yayın Sorumlusu', 'Yönetici')
                or type(data.get('enabled')) is not bool
                or type(data.get('shared_approval', False)) is not bool):
            raise ValueError('Geçerli bir Windows hesabı ve rol seçin. Birincil yönetici düzenlenemez.')
        with engine.publication_lock(ROOT):
            current = users()
            current.pop(ADMIN.casefold(), None)
            current[account.casefold()] = {'account': account, 'displayName': display_name.strip(), 'role': selected_role,
                                         'enabled': data['enabled'],
                                         'shared_approval': data.get('shared_approval', False),
                                         'changed_by': ACCOUNT,
                                         'changed_utc': datetime.now(timezone.utc).isoformat()}
            ACCESS.parent.mkdir(exist_ok=True)
            engine.write_json_atomic(ACCESS, current)
        return f"{account} kaydedildi. Ortak onay: {'açık' if data['enabled'] and data.get('shared_approval') else 'kapalı'}."
    if action not in ('repair', 'publish', 'rollback'):
        raise ValueError('İşlem bulunamadı.')
    if role() not in ('Yönetici', 'Yayın Sorumlusu'):
        raise PermissionError('Bu işlem için yayın yetkisi gerekir.')
    if data.get('confirmed') is not True:
        raise ValueError('İşlem onayı eksik.')
    if action == 'repair':
        result = engine.repair_candidate_zip(ROOT)
        return f"{result['relocated']} girdi düzeltildi. Yedek: {result['backup'] or 'Gerekmedi'}"
    # Redirect only this handler's synchronous operation while holding LOCK.
    output = io.StringIO()
    with redirect_stdout(output), engine.publication_lock(ROOT):
        if action == 'publish':
            engine._publish_unlocked(ROOT, True, publisher=ACCOUNT)
        else:
            target = data.get('archive', '')
            if not target or Path(target).name != target or target in ('.', '..'):
                raise ValueError('Arşiv kaydı seçin.')
            engine._rollback_unlocked(ROOT, target, True)
    return output.getvalue().strip()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def valid_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def respond(self, code, body, content_type='application/json; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def result(self, code, data):
        self.respond(code, json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        if not self.valid_host() or self.path != '/' + TOKEN:
            self.result(404, {'error': 'Sayfa bulunamadı.'})
            return
        self.respond(200, (PANEL / 'Panel.html').read_bytes(), 'text/html; charset=utf-8')

    def do_POST(self):
        base = f'http://127.0.0.1:{self.server.server_port}'
        if not (self.valid_host() and self.path == '/api' and self.headers.get('Origin') == base
                and secrets.compare_digest(self.headers.get('X-Talep-Panel', ''), TOKEN)):
            self.result(403, {'error': 'Panel oturumu geçersiz.'})
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 262144:
                raise ValueError('İstek boyutu geçersiz.')
            data = json.loads(self.rfile.read(size))
            action = data.get('action')
            with LOCK:
                if role() == 'Devre dışı':
                    raise PermissionError('Panel erişiminiz devre dışı.')
                if action == 'state':
                    self.result(200, snapshot())
                    return
                if action in ('scope-preview','scope-save','scope-list'):
                    payload = manage_scope(action,data)
                elif action in ('maintenance-preview', 'maintenance-clean', 'maintenance-reset'):
                    payload = local_maintenance(action.removeprefix('maintenance-'))
                elif action == 'account-search':
                    payload = search_windows_users(data)
                elif action in ('permissions-view','permissions-open'):
                    payload = manage_permissions(action,data)
                else:
                    payload = {'message':perform(action, data)}
                message = payload.get('message','')
                if action in ('user', 'repair', 'publish', 'rollback','scope-save','permissions-open','maintenance-clean','maintenance-reset'):
                    try:
                        with AUDIT.open('a', encoding='utf-8') as handle:
                            handle.write(json.dumps({'time': datetime.now(timezone.utc).isoformat(),
                                          'actor': ACCOUNT, 'action': action, 'detail': message},
                                          ensure_ascii=False) + '\n')
                    except OSError as exc:
                        message += f'\nİşlem kaydedildi. İşlem günlüğüne yazılamadı: {exc}'
            if message:payload['message']=message
            self.result(200, payload)
        except Exception as exc:
            self.result(400, {'error': str(exc)})


def main():
    global ACCOUNT
    ACCOUNT = windows_account()
    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        idle = threading.Timer(4 * 3600, server.shutdown)
        idle.daemon = True
        idle.start()
        webbrowser.open(f'http://127.0.0.1:{server.server_port}/{TOKEN}')
        try:
            server.serve_forever()
        finally:
            idle.cancel()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        import ctypes
        try:
            LOG_ROOT.mkdir(parents=True, exist_ok=True)
            (LOG_ROOT / 'panel_baslatma.log').write_text(traceback.format_exc(), encoding='utf-8')
        finally:
            ctypes.windll.user32.MessageBoxW(None, str(error), 'Talep Kontrol', 16)
