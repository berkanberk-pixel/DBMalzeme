"""One capacity projection shared by server validation and the decision screen.

Coverage is a backend-owned, snapshot-bound input. It must not be accepted as a
client-provided boolean. This module neither certifies snapshots nor writes SAP.
"""
from __future__ import annotations

import hashlib
import json

import commitment_balances as balances
import mb51_reconciliation as mb51


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def request_identity(request):
    """Same identity for 4+6 item rows and their material total of 10."""
    grouped, allocations = {}, {}
    for row in request.get('materials', []):
        code, uom = mb51.text(row.get('materialCode')), mb51.unit(row.get('uom'))
        key = (code, uom)
        grouped[key] = grouped.get(key, balances.number(0)) + balances.number(row.get('qty'))
    for code, rows in (request.get('allocations') or {}).items():
        if not any(key[0] == code for key in grouped):
            raise balances.BalanceError('Dağılımda talep listesinde olmayan malzeme var.')
        allocations[code] = sorted(
            [{'projectId': mb51.text(r.get('projectId')), 'qty': str(balances.number(r.get('qty')).normalize())}
             for r in rows if balances.number(r.get('qty')) > 0], key=lambda r: (r['projectId'], r['qty']))
    normalized = {k: mb51.text(request.get(k)) for k in
                  ('reservationNo', 'sourceUY', 'sourceDY', 'targetUY', 'targetDY')}
    normalized['materials'] = [{'materialCode': code, 'uom': uom, 'qty': str(qty.normalize())}
                               for (code, uom), qty in sorted(grouped.items())]
    normalized['allocations'] = {code: allocations.get(code, []) for code, _ in sorted(grouped)}
    return digest(normalized)


DISCOVERY_SCOPE_SOURCES = ('KESIFLER', 'MB51')


def _target_key(target):
    if not isinstance(target, (tuple, list)) or len(target) != 2:
        return ()
    return tuple(mb51.text(code).upper() for code in target)


def _auto_coverage(fingerprints, balance_digest, target):
    """Keşif + MB51 snapshot varsa kapsam teyidi otomatik kabul edilir.

    Kalan = Keşif − MB51 fiili (− bekleyen onay). Panel kaydı zorunlu değildir.
    """
    if not fingerprints.get('KESIFLER'):
        return None, 'Keşif kaynağı yüklenmeden kalan miktar hesaplanamaz.'
    if not fingerprints.get('MB51'):
        return None, 'MB51 kaynağı yüklenmeden fiili düşüm yapılamaz.'
    if not balance_digest:
        return None, 'Ortak onay bakiyesi doğrulanamadı.'
    if not all(_target_key(target)):
        return None, 'Hedef üretim yeri ve depo zorunludur.'
    return {
        'verified': True,
        'autoVerified': True,
        'reservations': {},
        'sourceFingerprints': fingerprints,
        'balanceDigest': balance_digest,
        'target': list(target),
        'discoveryBasis': 'ACTUAL_INCLUDED_PENDING_EXCLUDED',
        'evidenceReference': 'AUTO_MB51_KESIF',
    }, ''


def read_coverage(path, fingerprints, balance_digest, target):
    """Keşif kapsamı: MB51+Keşif varken otomatik; panel kaydı isteğe bağlı yedek."""
    unverified = {'verified': False, 'reservations': {},
                  'sourceFingerprints': fingerprints, 'balanceDigest': balance_digest,
                  'target': list(target)}
    auto, auto_reason = _auto_coverage(fingerprints, balance_digest, target)
    if auto:
        return auto

    # Kaynaklar eksikse panel kaydı da yetmez; net nedeni döndür.
    if auto_reason and (not fingerprints.get('KESIFLER') or not fingerprints.get('MB51')):
        return {**unverified, 'reason': auto_reason}

    try:
        with path.open(encoding='utf-8-sig') as stream:
            document = json.load(stream)
    except FileNotFoundError:
        return {**unverified, 'reason': auto_reason or 'Merkezi keşif kapsam kaydı bulunamadı.'}
    except (OSError, ValueError):
        return {**unverified, 'reason': 'Merkezi keşif kapsam kaydı okunamadı.'}

    records = document.get('depots') if isinstance(document, dict) else None
    if not isinstance(records, list):
        return {**unverified, 'reason': 'Keşif kapsam kaydı biçimi geçersiz.'}
    matches = [r for r in records if isinstance(r, dict) and _target_key(r.get('target')) == _target_key(target)]
    if len(matches) != 1:
        return {**unverified, 'reason': f'Hedef depo için tek bir kapsam kaydı bulunamadı ({target[0]} / {target[1]}).'}
    record = matches[0]
    recorded = record.get('sourceFingerprints')
    if not isinstance(recorded, dict) or any(
        not fingerprints.get(name) or recorded.get(name) != fingerprints[name]
        for name in DISCOVERY_SCOPE_SOURCES
    ):
        return {**unverified, 'reason': 'Keşif kapsam kaydı güncel Keşif ve MB51 kaynaklarıyla eşleşmiyor.'}
    if not balance_digest:
        return {**unverified, 'reason': 'Ortak onay bakiyesi doğrulanamadı.'}
    if record.get('discoveryBasis') != 'ACTUAL_INCLUDED_PENDING_EXCLUDED':
        return {**unverified, 'reason': 'Keşif fiili ve bekleyen hareket kapsamı doğrulanmadı.'}
    reference = record.get('evidenceReference')
    if not isinstance(reference, str) or not reference.strip():
        return {**unverified, 'reason': 'Kapsam kaydında kaynak kanıtı referansı eksik.'}
    return {**unverified, 'verified': True, 'autoVerified': False,
            'discoveryBasis': record['discoveryBasis'], 'evidenceReference': reference.strip()}


def require_coverage(coverage, fingerprints, balance_digest, target):
    if not isinstance(coverage, dict) or coverage.get('verified') is not True:
        reason = coverage.get('reason') if isinstance(coverage, dict) else ''
        raise balances.BalanceError(reason or 'Keşif kaynak kapsamı henüz doğrulanmadı.')
    if coverage.get('sourceFingerprints') != fingerprints:
        raise balances.BalanceError('Kapsam doğrulamasından sonra kaynak snapshotları değişti.')
    if coverage.get('balanceDigest') != balance_digest:
        raise balances.BalanceError('Kapsam doğrulamasından sonra ortak onay bakiyesi değişti.')
    if _target_key(coverage.get('target')) != _target_key(target):
        raise balances.BalanceError('Kaynak kapsamı farklı bir üretim yeri/depo için doğrulanmış.')
    if coverage.get('discoveryBasis') != 'ACTUAL_INCLUDED_PENDING_EXCLUDED':
        raise balances.BalanceError('Keşif kaynağının fiili/bekleyen miktar tanımı uygun değil.')


def evaluate(request, ledger, source, coverage, reconcile):
    """All source prices, source capacities and coverage come from the backend.

    request: reservationNo, sourceUY/DY, targetUY/DY, materials and allocations.
    source: fingerprints, guaranteeAvailable, materials keyed by material code.
    A source material carries unit, unitPrice, discoveryRemaining, projects,
    guaranteeExempt and discoveryExempt. projects maps ID to remaining quantity.
    """
    if not ledger.get('verified'):
        raise balances.BalanceError('Ortak onay zinciri doğrulanamadı.')
    target = (mb51.text(request.get('targetUY')), mb51.text(request.get('targetDY')))
    if not all(target):
        raise balances.BalanceError('Hedef üretim yeri ve depo zorunludur.')
    require_coverage(coverage, source.get('fingerprints'), ledger.get('balanceDigest'), target)
    reservation = mb51.text(request.get('reservationNo'))
    if not reservation:
        raise balances.BalanceError('Teminat kontrolü için SAP rezervasyon numarası zorunludur.')
    input_rows = request.get('materials')
    if not isinstance(input_rows, list) or not input_rows:
        raise balances.BalanceError('Kontrol edilecek malzeme listesi boş.')
    groups = {}
    for r in input_rows:
        code = mb51.text(r.get('materialCode'))
        qty = balances.number(r.get('qty'))
        if not code or qty <= 0:
            raise balances.BalanceError('Malzeme kodu ve pozitif talep miktarı zorunludur.')
        uom = mb51.unit(r.get('uom'))
        group = groups.setdefault(code, {'qty': balances.number(0), 'uom': uom})
        if not uom or group['uom'] != uom:
            raise balances.BalanceError('Aynı malzemenin talep birimleri uyuşmuyor.')
        group['qty'] += qty
    # Active balances for this reservation are replaced by this request, never
    # added to it. The current net actual still belongs to this reservation.
    materials = {}
    for code, group in groups.items():
        fact = (source.get('materials') or {}).get(code)
        if not fact or mb51.unit(fact.get('uom')) != group['uom']:
            raise balances.BalanceError(code + ': malzeme ana birimi doğrulanamadı.')
        qty = group['qty']
        scope = mb51.make_scope(request.get('sourceUY'), request.get('sourceDY'), *target, group['uom'])
        rec = reconcile(reservation, code, float(qty), scope)
        if not rec.get('verified'):
            raise balances.BalanceError(code + ': güncel MB51 gerçekleşmesi doğrulanamadı.')
        actual = balances.number(rec.get('actualQty'))
        if actual < 0:
            raise balances.BalanceError('Net fiili miktar negatif olamaz.')
        pending = max(qty - actual, balances.number(0))
        price = balances.number(fact.get('unitPrice'))
        item = {'requestedQty': float(qty), 'actualQty': float(actual), 'requestPendingQty': float(pending),
                'uom': group['uom'], 'unitPrice': float(price), 'projects': {}}
        if not fact.get('discoveryExempt'):
            if fact.get('discoveryRemaining') is None:
                raise balances.BalanceError(code + ': keşif kalan miktarı eksik; sıfır varsayılmadı.')
            cap = balances.project_capacity(fact.get('discoveryRemaining'), ledger.get('items', []),
                 material=code, unit=group['uom'], target=target, exclude_reservation=reservation,
                 source_coverage_verified=True)
            item.update(cap)
            item['afterRequest'] = float(balances.number(cap['available']) - pending)
        if fact.get('isTesis'):
            allocations = (request.get('allocations') or {}).get(code, [])
            positive=[a for a in allocations if balances.number(a.get('qty'))>0]
            identifiers=[mb51.text(a.get('projectId')) for a in positive]
            if len(identifiers)!=len(set(identifiers)):
                raise balances.BalanceError(code + ': aynı proje dağılımda tekrar ediyor.')
            project_rows = [{'MalzemeKodu': code, 'ProjeKodu': a.get('projectId'),
                             'DagitilanMiktar': a.get('qty')} for a in allocations]
            # A discovery exemption removes quantity caps, not the required gross
            # allocation total, active project identity or unique-project rule.
            project_pending = balances.project_pending(project_rows, code, qty,
                balances.number(0) if fact.get('discoveryExempt') else actual)
            allowed=set(fact.get('projectIds') or (fact.get('projects') or {}).keys())
            for project_id, requested_pending in project_pending.items():
                if project_id not in allowed:
                    raise balances.BalanceError(code + ': aktif proje kimliği doğrulanamadı: ' + project_id)
                if fact.get('discoveryExempt'):
                    item['projects'][project_id]={'exempt':True,'available':None,
                        'requestPendingQty':None,'afterRequest':None}
                    continue
                project_remaining = (fact.get('projects') or {}).get(project_id)
                if project_remaining is None:
                    raise balances.BalanceError(code + ': proje keşif kapasitesi bulunamadı: ' + project_id)
                pc = balances.project_capacity(project_remaining, ledger.get('items', []),
                     project_id=project_id, material=code, unit=group['uom'], target=target,
                     exclude_reservation=reservation, source_coverage_verified=True)
                item['projects'][project_id] = {**pc, 'exempt':False,'requestPendingQty': requested_pending,
                    'afterRequest': float(balances.number(pc['available']) - balances.number(requested_pending))}
        materials[code] = item
    all_guarantee_exempt=all((source['materials'][code]).get('guaranteeExempt') for code in groups)
    if all_guarantee_exempt:
        guarantee={'exempt':True,'evaluated':False,'sourceAvailable':source.get('guaranteeAvailable'),
            'available':source.get('guaranteeAvailable'),'pendingDeduction':None,'currentRequestDeduction':0.0}
    else:
        if source.get('guaranteeAvailable') is None:
            raise balances.BalanceError('ZMM098 kullanılabilir tutarı eksik; sıfır varsayılmadı.')
        available = float(balances.number(source['guaranteeAvailable']))
        guarantee = {'sourceAvailable': available,'available': available,'pendingDeduction': 0.0,
                     'currentRequestDeduction': 0.0,'exempt': False,'evaluated': True}
    eligible = (guarantee.get('exempt') or guarantee['available'] >= 0) and all(
        item.get('afterRequest', 0) >= 0 and all(p.get('exempt') or p['afterRequest'] >= 0 for p in item['projects'].values())
        and item['actualQty'] <= item['requestedQty']
        for item in materials.values())
    return {'verified': True, 'eligible': eligible, 'materials': materials, 'guarantee': guarantee,
            'requestDigest': request_identity(request), 'balanceDigest': ledger['balanceDigest'],
            'sourceFingerprints': source['fingerprints'], 'coverageDigest': digest(coverage)}
