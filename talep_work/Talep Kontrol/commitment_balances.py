"""Read-only projection of effective approval revisions and outstanding quantities.

Records are evidence inputs, never edited. MB51 remains the actual source.
Coverage must be supplied by an independently verified source snapshot; a
missing coverage statement is not interpreted as either zero or included.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json

import mb51_reconciliation as mb51


class BalanceError(ValueError):
    pass


def number(value):
    # CSV output uses decimal comma, without thousands separators.
    return mb51.decimal(str(value if value not in (None, '') else '0').replace(',', '.'))


def effective_headers(headers):
    groups = {}
    seen = set()
    for raw in headers:
        h = dict(raw)
        if mb51.text(h.get('KontrolTuru')).upper() not in ('MANUEL', 'REZERVASYON'):
            continue
        cid, reservation = mb51.text(h.get('KontrolID')), mb51.text(h.get('RezervasyonNo'))
        if not cid or not reservation:
            raise BalanceError('Kayıtta kontrol kimliği veya rezervasyon numarası eksik.')
        if cid in seen:
            raise BalanceError('Tekrarlanan kontrol kimliği: ' + cid)
        h['KontrolID'], h['RezervasyonNo'] = cid, reservation
        seen.add(cid)
        groups.setdefault(reservation, []).append(h)
    latest = []
    for reservation, chain in groups.items():
        by_id = {h['KontrolID']: h for h in chain}
        children, roots = {}, []
        routes = set()
        for h in chain:
            routes.add(tuple(mb51.header_scope(h)[k] for k in
                             ('source_uy', 'source_dy', 'target_uy', 'target_dy')))
            previous = mb51.text(h.get('OncekiKontrolID'))
            if not previous:
                roots.append(h)
            else:
                if previous not in by_id:
                    raise BalanceError(reservation + ': önceki revizyon bulunamadı.')
                if previous in children:
                    raise BalanceError(reservation + ': aynı kayıttan iki revizyon dallanmış.')
                children[previous] = h
        if len(roots) != 1:
            raise BalanceError(reservation + ': tek bir başlangıç kaydı doğrulanamadı; eski mükerrer kayıtlar incelenmeli.')
        if len(routes) != 1:
            raise BalanceError(reservation + ': revizyonlar arasında kaynak/hedef depo değişmiş.')
        current, visited = roots[0], set()
        while True:
            cid = current['KontrolID']
            if cid in visited:
                raise BalanceError(reservation + ': revizyon döngüsü bulundu.')
            visited.add(cid)
            if cid not in children:
                break
            current = children[cid]
        if len(visited) != len(chain):
            raise BalanceError(reservation + ': bağlantısız revizyon zinciri bulundu.')
        latest.append(current)
    return latest


def project_pending(project_rows, material, approved, actual):
    allocations = {}
    for r in project_rows:
        if mb51.text(r.get('MalzemeKodu')) != material:
            continue
        qty = number(r.get('DagitilanMiktar'))
        if qty < 0:
            raise BalanceError('Proje dağılım miktarı negatif olamaz.')
        if not qty:
            continue
        pid = mb51.text(r.get('ProjeKodu'))
        if not pid:
            raise BalanceError('Pozitif dağılımda proje kimliği eksik.')
        allocations[pid] = allocations.get(pid, Decimal(0)) + qty
    if abs(sum(allocations.values(), Decimal(0)) - approved) > mb51.EPS:
        raise BalanceError('Proje dağılımı etkin onay miktarıyla eşleşmiyor.')
    if len(allocations) > 1 and actual > mb51.EPS:
        # A material total is not proof of which of several projects received it.
        raise BalanceError('Fiili miktar birden fazla projeye atanamıyor; MB51 PYP eşleştirmesi veya doğrulanmış yeniden dağıtım gerekli.')
    return {pid: float(max(qty - (actual if len(allocations) == 1 else 0), Decimal(0)))
            for pid, qty in allocations.items()}


def build_balances(headers, load_materials, load_projects, reconcile):
    items, errors = [], []
    for h in effective_headers(headers):
        reservation, cid = h['RezervasyonNo'], h['KontrolID']
        state = mb51.text(h.get('KayitDurumu') or 'AKTIF').upper()
        if state not in ('AKTIF', 'IPTAL_EDILDI'):
            raise BalanceError('Bilinmeyen etkin kayıt durumu: ' + state)
        groups = mb51.group_control_rows(load_materials(cid))
        if not groups:
            raise BalanceError(cid + ': malzeme satırları bulunamadı.')
        projects = load_projects(cid)
        for group in groups:
            material, approved = group['materialCode'], number(group['approvedQty'])
            if approved < 0:
                raise BalanceError('Etkin onay miktarı negatif olamaz.')
            if state == 'IPTAL_EDILDI':
                approved = Decimal(0)
            scope = mb51.header_scope(h, group['uom'])
            rec = reconcile(reservation, material, float(approved), scope)
            verified = bool(rec.get('verified'))
            actual = number(rec['actualQty']) if verified else None
            pending = max(approved - actual, Decimal(0)) if verified else None
            prices = {number(r.get('BirimFiyat')) for r in group['rows']
                      if mb51.text(r.get('KalemKarari')).upper() == 'ONAYLA'}
            price = next(iter(prices)) if len(prices) == 1 else None
            guarantee_exempt = all(mb51.text(r.get('TeminatMuaf') or r.get('TeminatDurumu')).upper() in ('EVET', 'MUAF')
                                   for r in group['rows'])
            discovery_exempt = all(mb51.text(r.get('KesifMuaf') or r.get('KesifDurumu')).upper() in ('EVET', 'MUAF')
                                   for r in group['rows'])
            error = str(rec.get('error') or 'MB51 fiili miktarı doğrulanamadı.') if not verified else ''
            project_balances = {}
            if mb51.text(h.get('IsTuru')).upper() in ('T', 'TESİS', 'TESIS') and approved > 0 and not discovery_exempt:
                if verified:
                    try:
                        project_balances = project_pending(projects, material, approved, actual)
                    except BalanceError as exc:
                        error = str(exc)
                else:
                    error = error or 'Fiili miktar doğrulanamadığı için proje bakiyesi bilinmiyor.'
            if error:
                errors.append(reservation + '/' + material + ': ' + error)
            items.append({'reservationNo': reservation, 'controlId': cid,
                          'materialCode': material, 'scope': scope, 'recordState': state,
                          'approvedQty': float(approved), 'actualQty': float(actual) if actual is not None else None,
                          'pendingQty': float(pending) if pending is not None else None,
                          'excessQty': rec.get('excessQty'), 'realizationState': rec.get('state'),
                          'quantityVerified': verified, 'projectionVerified': not bool(error), 'error': error,
                          'unitPrice': float(price) if price is not None else None,
                          'pendingValue': (0.0 if guarantee_exempt or pending == 0 else
                                           float(pending * price) if pending is not None and price is not None and price > 0 else None),
                          'guaranteeExempt': guarantee_exempt, 'discoveryExempt': discovery_exempt,
                          'projectPending': project_balances})
    digest = hashlib.sha256(json.dumps(items, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    return {'items': items, 'errors': errors, 'verified': not errors, 'balanceDigest': digest}


def project_capacity(source_remaining, pending_items, project_id=None, material=None,
                     unit=None, target=None, exclude_reservation='', includes_pending=False,
                     source_coverage_verified=False):
    """Subtract outstanding approvals once; never subtract realized movements again."""
    if not source_coverage_verified:
        raise BalanceError('Keşif kaynağının fiili/bekleyen onay kapsamı doğrulanamadı.')
    deduction = Decimal(0)
    for item in pending_items:
        if item['reservationNo'] == exclude_reservation or item.get('discoveryExempt'):
            continue
        if material and item['materialCode'] != material:
            continue
        scope = item['scope']
        if target and (scope['target_uy'], scope['target_dy']) != tuple(target):
            continue
        if unit and scope['uom'] != mb51.unit(unit):
            raise BalanceError('Bekleyen onay ile keşif ölçü birimi uyuşmuyor.')
        if not item.get('projectionVerified') or item.get('pendingQty') is None:
            raise BalanceError(item.get('error') or 'Bekleyen onay miktarı doğrulanamadı.')
        if not includes_pending:
            if project_id is None:
                deduction += number(item['pendingQty'])
            else:
                deduction += number(item.get('projectPending', {}).get(project_id, 0))
    before = number(source_remaining)
    return {'sourceRemaining': float(before), 'pendingDeduction': float(deduction),
            'available': float(before - deduction)}


def guarantee_capacity(source_available, pending_items, coverage_by_reservation,
                       current_request_value=0, current_reservation='', target=None):
    """Coverage values: INCLUDED, EXCLUDED, or absent (unknown); no timestamp guessing."""
    deduction = Decimal(0)
    for item in pending_items:
        if item['reservationNo'] == current_reservation or item.get('guaranteeExempt'):
            continue
        if target and (item['scope']['target_uy'], item['scope']['target_dy']) != tuple(target):
            continue
        if item.get('pendingQty') == 0:
            continue
        if not item.get('quantityVerified'):
            raise BalanceError('MB51 fiili miktarı doğrulanamadı; teminat bakiyesi hesaplanamadı.')
        coverage = coverage_by_reservation.get(item['reservationNo'])
        if coverage == 'INCLUDED':
            continue
        if coverage != 'EXCLUDED':
            raise BalanceError('ZMM098 açık rezervasyon kapsamı doğrulanamadı: ' + item['reservationNo'])
        if item.get('pendingValue') is None:
            raise BalanceError('Bekleyen onayın fiyatı/tutarı doğrulanamadı.')
        deduction += number(item['pendingValue'])
    request = number(current_request_value)
    if request < 0:
        raise BalanceError('Talep tutarı negatif olamaz.')
    current = Decimal(0)
    if request:
        coverage = coverage_by_reservation.get(current_reservation) if current_reservation else 'EXCLUDED'
        if coverage not in ('INCLUDED', 'EXCLUDED'):
            raise BalanceError('Mevcut talebin ZMM098 içinde olup olmadığı doğrulanamadı.')
        if coverage == 'EXCLUDED':
            current = request
    available = number(source_available) - deduction - current
    return {'sourceAvailable': float(number(source_available)), 'pendingDeduction': float(deduction),
            'currentRequestDeduction': float(current), 'available': float(available)}
