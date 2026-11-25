"""Scoped SAP transfer reconciliation. No shared writes and no guessed legs.

Only a verified source leg contributes to actual quantity. Receiving legs are
excluded so a transfer cannot be counted twice. Ambiguous source, unit, event
identity or reverse direction returns an unverified result, never a zero balance.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

MOVEMENTS = {'301': 1, '302': -1, '311': 1, '312': -1,
             '401': 1, '402': -1, '411': 1, '412': -1}
EPS = Decimal('0.0000001')


def text(value):
    return str(value if value is not None else '').strip()


def unit(value):
    value = text(value).upper()
    return {'AD': 'AD', 'ADT': 'AD', 'ADET': 'AD', 'M': 'M', 'MT': 'M', 'M.': 'M', 'MT.': 'M', 'KG.': 'KG'}.get(value, value)


def decimal(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Miktar sayısal değil.')
    if not result.is_finite():
        raise ValueError('Miktar sonlu bir sayı olmalıdır.')
    return result


def unknown(message, **extra):
    return {'found': False, 'actualQty': None, 'events': 0,
            'status': 'KONTROL_EDILEMEDI', 'state': 'UNVERIFIED',
            'pendingQty': None, 'excessQty': None, 'lastDate': '',
            'verified': False, 'error': message, **extra}


def make_scope(source_uy, source_dy, target_uy, target_dy, uom=''):
    return dict(source_uy=text(source_uy), source_dy=text(source_dy),
                target_uy=text(target_uy), target_dy=text(target_dy), uom=unit(uom))


def header_scope(header, uom=''):
    scope=make_scope(header.get('KaynakUY'), header.get('KaynakDepo'),
                      header.get('HedefUY'), header.get('HedefDepo'), uom)
    if text(header.get('KontrolID')):scope['historicalControlId']=text(header['KontrolID'])
    return scope


def scope_from_reservation(connection, reservation, material):
    rows = connection.execute('''SELECT DISTINCT source_uy,source_dy,target_uy,target_dy,uom
          FROM zmm048 WHERE reservation_no=? AND material_code=?''',
          (text(reservation), text(material))).fetchall()
    scopes = {tuple(make_scope(*tuple(row)).values()) for row in rows}
    if len(scopes) != 1:
        raise ValueError('Rezervasyon/malzeme için tek bir kaynak-hedef depo ve birim doğrulanamadı.')
    return dict(zip(('source_uy', 'source_dy', 'target_uy', 'target_dy', 'uom'), scopes.pop()))


def reconcile_rows(rows, reservation, material, approved_qty, scope):
    try:
        approved = decimal(approved_qty)
    except ValueError as exc:
        return unknown(str(exc))
    if approved < 0:
        return unknown('Onaylanan miktar negatif olamaz.')
    input_scope=dict(scope)
    scope = make_scope(*(scope.get(k) for k in
        ('source_uy', 'source_dy', 'target_uy', 'target_dy', 'uom')))
    scope.update({k:input_scope[k] for k in ('stockLedgerScopeVerified','scopeEvidence','baseUnitVerified','historicalControlId') if k in input_scope})
    source = (scope['source_uy'], scope['source_dy'])
    target = (scope['target_uy'], scope['target_dy'])
    if not all(source + target) or source == target or not scope['uom']:
        return unknown('Kaynak/hedef ÜY-depo ve ölçü birimi eksiksiz ve farklı olmalıdır.', scope=scope)
    candidates, issues, mirrors, excluded, ignored = [], [], [], 0, 0
    source_only=[]
    for raw in rows:
        row = dict(raw)
        if text(row.get('reservation')) != text(reservation) or text(row.get('material_code')) != text(material):
            continue
        move = text(row.get('movement')).upper()
        if move not in MOVEMENTS:
            ignored += 1
            continue
        stock_leg = (text(row.get('plant')), text(row.get('dy')))
        if row.get('route_layout')=='STOCK_LEDGER':
            if not scope.get('stockLedgerScopeVerified'):
                issues.append('Stok satırı biçimindeki MB51 için benzersiz rezervasyon/kayıt kaynak-hedef kapsamı doğrulanamadı.')
                continue
            if stock_leg==source:
                source_only.append(row)
                continue
            if stock_leg!=target:
                excluded+=1
                continue
            if not text(row.get('doc')):
                issues.append('MB51 malzeme belge numarası eksik.')
                continue
            if row.get('uom_layout')=='MASTER_BASE_REQUIRED' and not scope.get('baseUnitVerified'):
                issues.append('MB51 temel miktar birimi malzeme ana verisinden doğrulanamadı.')
                continue
            if unit(row.get('uom'))!=scope['uom']:
                issues.append('MB51 miktar birimi onay birimiyle uyuşmuyor.')
                continue
            try:
                signed_qty=decimal(row.get('qty'))
            except ValueError as exc:
                issues.append(str(exc))
                continue
            if signed_qty*MOVEMENTS[move]<0:
                issues.append('Hedef stok satırının miktar işareti hareket/ters kayıt yönüyle uyuşmuyor.')
                continue
            candidates.append((row,signed_qty))
            continue
        explicit_source = (text(row.get('source_plant')), text(row.get('source_dy')))
        receiver = (text(row.get('target_plant')), text(row.get('target_dy')))
        # 311/312 are same-plant transfers, so the missing target plant is known.
        if move in ('311', '312') and not receiver[0] and stock_leg[0]:
            receiver = (stock_leg[0], receiver[1])
        if stock_leg == target:
            if all(explicit_source) and explicit_source != source:
                excluded += 1
            else:
                mirrors.append(row)
            continue
        sender = explicit_source if all(explicit_source) else stock_leg
        if sender != source:
            # A fully identified different depot is outside this approval.
            if all(sender):
                excluded += 1
            else:
                issues.append('MB51 satırının teslim eden üretim yeri/deposu eksik.')
            continue
        if all(explicit_source) and all(stock_leg) and stock_leg != source:
            issues.append('MB51 stok bacağı ile teslim eden depo tutarsız.')
            continue
        if not all(receiver):
            issues.append('MB51 teslim alan üretim yeri/deposu eksik; rezervasyondan varsayılmadı.')
            continue
        if receiver != target:
            excluded += 1
            continue
        if unit(row.get('uom')) != scope['uom']:
            issues.append('MB51 ve onay ölçü birimleri uyuşmuyor veya MB51 birimi eksik.')
            continue
        if not text(row.get('doc')):
            issues.append('MB51 malzeme belge numarası eksik.')
            continue
        try:
            qty = abs(decimal(row.get('qty')))
        except ValueError as exc:
            issues.append(str(exc))
            continue
        # Match only the original source leg, including its reversal. If the
        # export stores reversals with swapped endpoints, a sample is required;
        # such a receiver-only event must never release a pending commitment.
        candidates.append((row, qty * MOVEMENTS[move]))
    if source_only and not candidates:
        issues.append('Yalnız kaynak stok satırı bulundu; hedefe fiili teslim doğrulanamadı.')
    if mirrors and not candidates:
        issues.append('Yalnız teslim alan stok bacağı bulundu; kaynak bacağı veya ters kayıt yönü doğrulanamadı.')
    if ignored and not candidates and not mirrors and not excluded:
        issues.append('Rezervasyondaki hareketler nakil mutabakatı kapsamı dışında.')
    seen, accepted, duplicates = {}, [], 0
    for row, qty in candidates:
        # Full SAP document identity permits exact duplicate elimination.
        full = all(text(row.get(k)) for k in ('doc_year', 'doc_item'))
        route = (source, target)
        if full:
            identity = (text(row['doc']), text(row['doc_year']), text(row['doc_item']),
                        text(row['movement']), text(material), route)
        else:
            identity = (text(row['doc']), text(row.get('date')), text(row.get('posting_date')),
                        text(row['movement']), text(material), route, qty, unit(row.get('uom')))
        signature = (qty, unit(row.get('uom')), text(row.get('posting_date')), text(row.get('pyp')))
        if identity in seen:
            if full and seen[identity] == signature:
                duplicates += 1
                continue
            issues.append('Tekrarlanan veya çelişen MB51 olayı; belge yılı/kalemiyle tekillik doğrulanamadı.')
            continue
        seen[identity] = signature
        accepted.append((row, qty))
    if issues:
        return unknown(' | '.join(dict.fromkeys(issues)), scope=scope,
                       excludedRows=excluded, receiverRows=len(mirrors), duplicateRows=duplicates,
                       ignoredRows=ignored)
    def mirror_key(row):
        return (text(row.get('doc')), text(row.get('doc_year')), text(row.get('doc_item')),
                text(row.get('movement')), abs(decimal(row.get('qty'))), unit(row.get('uom')))
    try:
        source_events = {mirror_key(row) for row, _ in accepted}
        if any(mirror_key(row) not in source_events for row in mirrors):
            return unknown('Teslim alan stok bacağının eşleşen kaynak olayı bulunamadı.',
                           scope=scope, receiverRows=len(mirrors), excludedRows=excluded)
    except ValueError as exc:
        return unknown(str(exc), scope=scope)
    actual = sum((qty for _, qty in accepted), Decimal(0))
    if actual < -EPS:
        return unknown('Net ters kayıt miktarı ileri hareketi aşıyor; kaynak dönem/yönü doğrulanmalı.', scope=scope)
    actual = max(actual, Decimal(0))
    if not accepted:
        state, status = 'WAITING', 'MB51_BEKLENIYOR'
    elif actual <= EPS and any(qty < 0 for _, qty in accepted):
        state, status = 'REVERSED', 'FIILI_MIKTAR_FARKI'
    elif abs(actual - approved) <= EPS:
        state, status = 'MATCHED', 'MUTABIK'
    elif actual < approved:
        state, status = 'PARTIAL', 'FIILI_MIKTAR_FARKI'
    else:
        state, status = 'EXCESS', 'FIILI_MIKTAR_FARKI'
    return dict(found=bool(accepted), actualQty=float(actual), events=len(accepted),
                status=status, state=state, verified=True, pendingQty=float(max(approved-actual, Decimal(0))),
                excessQty=float(max(actual-approved, Decimal(0))), approvedQty=float(approved), scope=scope,
                lastDate=max((text(row.get('posting_date')) for row, _ in accepted), default=''),
                excludedRows=excluded, receiverRows=len(mirrors), duplicateRows=duplicates, ignoredRows=ignored)


def reconcile_connection(connection, reservation, material, approved_qty=0, scope=None):
    try:
        scope = scope if scope is not None else scope_from_reservation(connection, reservation, material)
        # Old indexes remain readable; new metadata improves identity on rebuild.
        rows = [dict(r) for r in connection.execute('SELECT * FROM mb51 WHERE reservation=? AND material_code=?',
                                  (text(reservation), text(material))).fetchall()]
        scope=dict(scope)
        if any(r.get('route_layout')=='STOCK_LEDGER' for r in rows):
            current=connection.execute('SELECT COUNT(*) FROM zmm048 WHERE reservation_no=? AND material_code=?',(text(reservation),text(material))).fetchone()[0]
            if current:
                reference=scope_from_reservation(connection,reservation,material)
                if any(reference[k]!=scope[k] for k in ('source_uy','source_dy','target_uy','target_dy','uom')):
                    return unknown('MB51 stok satırı ile rezervasyonun kaynak/hedef/birim kapsamı uyuşmuyor.')
                scope.update(stockLedgerScopeVerified=True,scopeEvidence='UNIQUE_ZMM048_SCOPE')
            elif scope.get('historicalControlId'):
                scope.update(stockLedgerScopeVerified=True,scopeEvidence='VERIFIED_COMMITTED_RECORD_SCOPE')
            else:
                return unknown('Teslim eden depo MB51 çıktısında yok; benzersiz rezervasyon veya doğrulanmış kayıt kapsamı gerekli.')
            if any(r.get('uom_layout')=='MASTER_BASE_REQUIRED' for r in rows):
                master_units={unit(r[0]) for r in connection.execute('SELECT DISTINCT uom FROM mb52 WHERE material_code=? AND plant IN (?,?)',
                    (text(material),scope['source_uy'],scope['target_uy'])).fetchall() if text(r[0])}
                if len(master_units)!=1 or next(iter(master_units))!=scope['uom']:
                    return unknown('MB51 birimi yok; MB52 malzeme temel birimi tekil/eşleşir biçimde doğrulanamadı.')
                scope['baseUnitVerified']=True
                for r in rows:
                    if r.get('uom_layout')=='MASTER_BASE_REQUIRED':r['uom']=scope['uom']
        return reconcile_rows(rows, reservation, material, approved_qty, scope)
    except Exception as exc:
        return unknown(str(exc))


def group_control_rows(rows):
    """A reservation material is compared to its approved total, not each item."""
    groups = {}
    for row in rows:
        code = text(row.get('MalzemeKodu'))
        if not code:
            continue
        group = groups.setdefault(code, {'materialCode': code, 'approvedQty': Decimal(0),
                                        'units': set(), 'rows': []})
        group['units'].add(unit(row.get('Birim')))
        if text(row.get('KalemKarari')).upper() == 'ONAYLA':
            group['approvedQty'] += decimal(text(row.get('OnaylananMiktar') or '0').replace(',', '.'))
        group['rows'].append(row)
    for group in groups.values():
        group['approvedQty'] = float(group['approvedQty'])
        group['uom'] = next(iter(group['units'])) if len(group['units']) == 1 else ''
    return list(groups.values())


def depot_actual(connection, material, target_uy, target_dy, uom):
    """Read-only depot receipt total; reuse transfer validation for each route.

    An unresolved contributing reservation invalidates the whole total, rather
    than silently returning a partial amount. Project attribution is not inferred.
    """
    material, target_dy, target_uy = text(material), text(target_dy), text(target_uy)
    if not target_uy:
        plants = {text(r[0]) for r in connection.execute(
            "SELECT DISTINCT uy FROM depots WHERE dy=? AND TRIM(COALESCE(uy,''))<>''", (target_dy,))}
        if len(plants) != 1:
            return unknown('Hedef deponun üretim yeri tekil olarak doğrulanamadı.')
        target_uy = plants.pop()
    if not target_dy or not unit(uom):
        return unknown('Hedef depo ve keşif ölçü birimi zorunludur.')
    target = (target_uy, target_dy)
    # Keep all legs for candidate reservations: source/receiver mirrors must be
    # checked together, not independently summed with ABS(qty).
    all_rows = [dict(r) for r in connection.execute(
        'SELECT * FROM mb51 WHERE material_code=?', (material,))
        if text(r['movement']) in MOVEMENTS]
    relevant = [r for r in all_rows if
        ((text(r.get('target_dy')) == target_dy and
          text(r.get('target_plant') or (r.get('plant') if text(r.get('movement')) in ('311','312') else '')) in ('', target_uy))
         or (text(r.get('dy')) == target_dy and text(r.get('plant')) in ('',target_uy)))]
    if not relevant:
        return unknown('Bu depo/malzeme için MB51 nakil kanıtı bulunamadı.')
    total, events, routes_count = Decimal(0), 0, 0
    for reservation in {text(r.get('reservation')) for r in relevant}:
        rows = [r for r in all_rows if text(r.get('reservation')) == reservation]
        local = [r for r in relevant if text(r.get('reservation')) == reservation]
        routes = set()
        if any(r.get('route_layout') == 'STOCK_LEDGER' for r in local):
            try:
                scope = scope_from_reservation(connection, reservation, material)
            except ValueError as exc:
                return unknown(str(exc))
            if (scope['target_uy'],scope['target_dy']) == target:
                if scope['uom'] != unit(uom):
                    return unknown('MB51/rezervasyon ile keşif birimi uyuşmuyor.')
                result = reconcile_connection(connection,reservation,material,0,scope)
                if not result.get('verified') or not result.get('found'):
                    return unknown(result.get('error') or 'MB51 fiili teslim doğrulanamadı.')
                total += decimal(result['actualQty']); events += result['events']; routes_count += 1
            elif (scope['source_uy'],scope['source_dy']) != target:
                return unknown('Stok satırının rezervasyon kaynak/hedef kapsamı uyuşmuyor.')
            # Outgoing stock-only transfers do not belong to receipts.
            continue
        for row in local:
            stock = (text(row.get('plant')),text(row.get('dy')))
            receiver = (text(row.get('target_plant')),text(row.get('target_dy')))
            if text(row.get('movement')) in ('311','312') and not receiver[0]:
                receiver = (stock[0],receiver[1])
            if stock == target:
                continue  # receiving mirrors are validated against source events below
            sender = (text(row.get('source_plant')),text(row.get('source_dy')))
            if not all(sender):sender=stock
            if receiver != target or not all(sender):
                return unknown('MB51 naklinin teslim eden/alan üretim yeri-depo kapsamı eksik.')
            routes.add(sender)
        if not routes:
            # Only clearly identified outgoing rows can be safely ignored.
            if all((text(r.get('plant')),text(r.get('dy'))) == target
                   and text(r.get('target_dy')) and
                   (text(r.get('target_plant') or r.get('plant')),text(r.get('target_dy'))) != target
                   for r in local):
                continue
            return unknown('Yalnız teslim alan stok bacağı bulundu; kaynak olayı doğrulanamadı.')
        # Do not let an outgoing transfer at this depot masquerade as a receiver mirror.
        checked_rows=[r for r in rows if not (
            (text(r.get('plant')),text(r.get('dy'))) == target and
            text(r.get('target_dy')) and
            (text(r.get('target_plant') or r.get('plant')),text(r.get('target_dy'))) != target)]
        def event_key(r):
            # Quantity/unit validation remains in reconcile_rows. Document keys
            # only associate receiver mirrors with their original source route.
            return tuple(text(r.get(k)) for k in ('doc','doc_year','doc_item','movement'))
        source_keys={sender:{event_key(r) for r in checked_rows
            if ((text(r.get('source_plant')),text(r.get('source_dy'))) if
                all(text(r.get(k)) for k in ('source_plant','source_dy')) else
                (text(r.get('plant')),text(r.get('dy')))) == sender}
            for sender in routes}
        all_keys=set().union(*source_keys.values())
        if any((text(r.get('plant')),text(r.get('dy'))) == target and event_key(r) not in all_keys
               for r in checked_rows):
            return unknown('Teslim alan stok bacağının eşleşen kaynak olayı bulunamadı.')
        for sender in routes:
            scope=make_scope(*sender,*target,uom)
            route_rows=[r for r in checked_rows if
                (text(r.get('plant')),text(r.get('dy'))) != target or event_key(r) in source_keys[sender]]
            result=reconcile_rows(route_rows,reservation,material,0,scope)
            if not result.get('verified') or not result.get('found'):
                return unknown(result.get('error') or 'MB51 fiili teslim doğrulanamadı.')
            total+=decimal(result['actualQty']);events+=result['events'];routes_count+=1
    if not routes_count:
        return unknown('Bu depo için doğrulanmış gelen nakil bulunamadı.')
    return {'verified':True,'found':True,'actualQty':float(total),'events':events,
            'routes':routes_count,'error':'','scope':{'target_uy':target_uy,'target_dy':target_dy,'uom':unit(uom)}}


def report_event(connection, raw, depots, cache=None):
    """Signed contribution of one raw row to the selected depot scope.

    Raw rows remain visible. Source/receiver copies and exact duplicates have
    zero contribution only after route reconciliation succeeds. Unknown events
    remain null. cache is request-local, never shared between snapshots.
    """
    row=dict(raw);cache=cache if cache is not None else {}
    def fail(reason):
        return {'signedQty':None,'movementDirection':'YÖN DOĞRULANAMADI: '+reason,
                'movementVerified':False,'eventCounted':False}
    try:
        code,reservation=text(row.get('material_code')),text(row.get('reservation'))
        key=(reservation,code)
        if key not in cache:
            cache[key]=[dict(r) for r in connection.execute(
                'SELECT * FROM mb51 WHERE reservation=? AND material_code=?',(reservation,code))
                if text(r['movement']) in MOVEMENTS]
        rows=cache[key]
        def stock(r):return (text(r.get('plant')),text(r.get('dy')))
        def route(r):
            sender=(text(r.get('source_plant')),text(r.get('source_dy')))
            if not all(sender):sender=stock(r)
            receiver=(text(r.get('target_plant')),text(r.get('target_dy')))
            if text(r.get('movement')) in ('311','312') and not receiver[0]:receiver=(stock(r)[0],receiver[1])
            return sender,receiver
        def event(r):return tuple(text(r.get(k)) for k in ('doc','doc_year','doc_item','movement'))
        ledger=row.get('route_layout')=='STOCK_LEDGER'
        if ledger:
            scope=scope_from_reservation(connection,reservation,code)
            sender=(scope['source_uy'],scope['source_dy']);receiver=(scope['target_uy'],scope['target_dy'])
            result=reconcile_connection(connection,reservation,code,0,scope)
            accepted=[r for r in rows if stock(r)==receiver]
            mirror=stock(row)==sender
            resolved_unit=scope['uom']
        else:
            sender,receiver=route(row)
            mirror=False
            # A receiver copy often omits the route. Match its SAP event to a
            # source row rather than inventing the sender from its stock depot.
            matches={route(r) for r in rows if event(r)==event(row) and
                     all(route(r)[0]+route(r)[1]) and route(r)[0]!=route(r)[1]
                     and stock(r)==route(r)[0] and route(r)[1]==stock(row)}
            if matches:
                if len(matches)!=1:return fail('Belge olayı birden fazla kaynak/hedefe bağlı.')
                sender,receiver=matches.pop();mirror=True
            if not all(sender+receiver) or sender==receiver:
                return fail('Kaynak/hedef üretim yeri ve depo eksik veya aynı.')
            accepted=[r for r in rows if stock(r)==sender and route(r)==(sender,receiver)]
            source_events={event(r) for r in accepted}
            scoped=accepted+[r for r in rows if stock(r)==receiver and event(r) in source_events
                             and not (all(route(r)[1]) and route(r)[1]!=receiver)]
            resolved_unit=unit(row.get('uom'))
            scope=make_scope(*sender,*receiver,resolved_unit)
            result=reconcile_rows(scoped,reservation,code,0,scope)
        if not result.get('verified') or not result.get('found'):
            return fail(result.get('error') or 'Eşleşen fiili nakil bulunamadı.')
        inside_src,inside_dst=sender in depots,receiver in depots
        if not inside_src and not inside_dst:return fail('Nakil seçili üretim yeri/depo kapsamına ait değil.')
        factor=int(inside_dst)-int(inside_src)
        direction='İÇ NAKİL' if factor==0 else ('DEPOYA GİRİŞ' if factor>0 else 'DEPODAN ÇIKIŞ')
        if MOVEMENTS[text(row.get('movement'))]<0:direction+=' · TERS KAYIT'
        contribution=decimal(0);counted=False
        if mirror:
            direction+=' · KARŞI STOK BACAĞI (TEKRAR SAYILMAZ)'
        else:
            copies=[r for r in accepted if event(r)==event(row)]
            canonical=min((int(r['id']) for r in copies),default=int(row['id']))
            if int(row['id'])!=canonical:
                direction+=' · YİNELENEN KAYIT (TEKRAR SAYILMAZ)'
            else:
                counted=True
                contribution=(decimal(row.get('qty')) if ledger else
                              abs(decimal(row.get('qty')))*MOVEMENTS[text(row.get('movement'))])*factor
        return {'signedQty':float(contribution),'movementDirection':direction,'movementVerified':True,'eventCounted':counted,
                'sourcePlant':sender[0],'sourceDepot':sender[1],
                'targetPlant':receiver[0],'targetDepot':receiver[1],'unit':resolved_unit}
    except (ValueError,KeyError,TypeError) as exc:
        return fail(str(exc))
