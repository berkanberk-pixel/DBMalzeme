"""Read-only operations summaries; unknown values never become zero totals."""
import math
from collections import Counter
import mb51_reconciliation as mb51


def known_sum(values):
    values=list(values)
    if not values or any(v is None for v in values):return None
    numbers=[float(v) for v in values]
    return sum(numbers) if all(math.isfinite(v) for v in numbers) else None


def guarantee_summary(rows):
    counts=Counter((str(r.get('uy') or ''),str(r.get('dy') or '')) for r in rows)
    ambiguous=any(n>1 for n in counts.values())
    def total(fields):
        return None if ambiguous else known_sum(known_sum(r.get(k) for k in fields) for r in rows)
    return {'rows':rows,'rowCount':len(rows),'ambiguous':ambiguous,
            'total':total(('main','cash','manual')),'stockValue':total(('stockValue',)),
            'available':total(('available',))}


def resolve_scope(connection,depot='',depots_filter=None):
    selectors=[depot] if depot else depots_filter
    if selectors is None:return None
    result=set()
    for selector in selectors:
        if isinstance(selector,(list,tuple)) and len(selector)==2:
            result.add(tuple(str(x).strip() for x in selector));continue
        selector=str(selector).strip()
        if '|' in selector:
            result.add(tuple(selector.split('|',1)));continue
        pairs={(str(r[0]),str(r[1])) for r in connection.execute('SELECT DISTINCT uy,dy FROM depots WHERE dy=?',(selector,))}
        if len(pairs)!=1:raise ValueError('Operasyon filtresinde depo üretim yeri tekil değil: '+selector)
        result.update(pairs)
    return result


def consumption(rows,months):
    """One 221/Z22 positive, 222 reverse rule for all operations breakdowns."""
    rows=[dict(r) for r in rows]
    months_set=sorted({str(r.get('posting_date') or '')[:7] for r in rows if r.get('posting_date')})[-months:]
    rows=[r for r in rows if str(r.get('posting_date') or '')[:7] in months_set]
    seen={};incomplete={};normalized=[]
    for r in rows:
        amount=r.get('amount_upb');error=False
        if amount is not None:
            try:amount=abs(float(amount));error=not math.isfinite(amount)
            except (ValueError,TypeError):error=True
        else:error=True
        # Exact SAP identity permits deduplication; no approximate row deletion.
        if all(r.get(k) not in (None,'') for k in ('doc','doc_year','doc_item')):
            identity=tuple(r.get(k) for k in ('doc','doc_year','doc_item','movement','material_code','plant','dy'))
            signature=tuple(r.get(k) for k in ('qty','uom','amount_upb','posting_date','pyp'))
            if identity in seen:
                previous,previous_signature=seen[identity]
                if previous_signature==signature:continue
                previous['_amount']=None;error=True
            else:seen[identity]=(r,signature)
        else:
            identity=tuple(r.get(k) for k in ('doc','posting_date','movement','material_code','plant','dy','qty','uom','amount_upb','pyp'))
            if identity in incomplete:
                incomplete[identity]['_amount']=None;error=True
            else:incomplete[identity]=r
        r['_amount']=None if error else amount
        normalized.append(r)
    def aggregate(keys):
        groups={}
        for r in normalized:
            identity=tuple(str(r.get(k) or '')[:7] if k=='posting_date' else str(r.get(k) or '') for k in keys)
            groups.setdefault(identity,[]).append(r)
        out=[]
        for identity,items in sorted(groups.items()):
            g={('month' if k=='posting_date' else k):v for k,v in zip(keys,identity)}
            g.update(events=len(items),spendEvents=sum(r['movement'] in ('221','Z22') for r in items),
                reverseEvents=sum(r['movement']=='222' for r in items),unknownCount=sum(r['_amount'] is None for r in items))
            for field,move in [('grossSpend','221'),('reversal222','222'),('returnZ22','Z22')]:
                g[field]=known_sum(r['_amount'] for r in items if r['movement']==move) if any(r['movement']==move for r in items) else 0.0
            g['netSpend']=known_sum((None if r['_amount'] is None else r['_amount']*(-1 if r['movement']=='222' else 1)) for r in items)
            if 'material_code' in keys:
                g['materialCode']=g.pop('material_code');g['materialDesc']=next((r.get('material_desc') for r in items if r.get('material_desc')),'')
                g['uom']=g.pop('uom')
            out.append(g)
        return out
    monthly=aggregate(('posting_date',));by_depot=aggregate(('posting_date','plant','dy'))
    material=aggregate(('posting_date','plant','dy','material_code','uom'))
    pyp=[r for r in aggregate(('pyp',)) if r['pyp']]
    return monthly,by_depot,material,pyp
