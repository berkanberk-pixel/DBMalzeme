"""Capacity inputs read from an active index; never trust browser prices/limits."""
import re
import unicodedata

from commitment_balances import BalanceError
from mb51_reconciliation import text, unit


def project_name(value):
    value = text(value).replace('I', 'ı').replace('İ', 'i').lower()
    value = ''.join(c for c in unicodedata.normalize('NFD', value) if not unicodedata.combining(c))
    return re.sub('[^a-z0-9]+', ' ', value.replace('ı', 'i')).strip()


def stable_project_id(depot, name):
    # Same stable project ID as the desktop, including JS UTF-16 code units.
    data = (text(depot) + '|' + project_name(name)).encode('utf-16le')
    h = 2166136261
    for i in range(0, len(data), 2):
        h = ((h ^ int.from_bytes(data[i:i+2], 'little')) * 16777619) & 0xffffffff
    digits, output = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ', ''
    while h:
        h, remainder = divmod(h, 36)
        output = digits[remainder] + output
    return 'KESIF-' + text(depot) + '-' + (output or '0')


def read_facts(connection, request, exemptions, fingerprints):
    uy, dy = text(request.get('targetUY')), text(request.get('targetDY'))
    source_uy = text(request.get('sourceUY'))
    depots = connection.execute('SELECT DISTINCT uy FROM depots WHERE dy=?', (dy,)).fetchall()
    if {text(r[0]) for r in depots} != {uy}:
        raise BalanceError('Keşif deposu üretim yeri kapsamında tekil olarak doğrulanamadı.')
    guarantees = connection.execute('SELECT available FROM zmm098 WHERE uy=? AND dy=?', (uy, dy)).fetchall()
    exempt = {text(r.get('materialCode')): r for r in exemptions if r.get('active')}
    target_work={text(r[0]).upper() for r in connection.execute('SELECT work_type FROM depots WHERE uy=? AND dy=?',(uy,dy)).fetchall() if text(r[0])}
    target_tesis=bool(target_work & {'T','TESIS','TESİS'})
    known_projects=[dict(r) for r in connection.execute('SELECT project_id,project_name,active FROM projects WHERE uy=? AND dy=?',(uy,dy)).fetchall()]
    active_projects=[r for r in known_projects if not text(r.get('active')) or text(r.get('active')).upper() in ('EVET','X','1','AKTIF','TRUE')]
    output = {}
    for code in {text(r.get('materialCode')) for r in request.get('materials', [])}:
        master = connection.execute('SELECT DISTINCT uom FROM mb52 WHERE material_code=? AND plant IN (?,?)',
                                    (code, source_uy, uy)).fetchall()
        units = {unit(r[0]) for r in master if text(r[0])}
        if len(units) != 1:
            raise BalanceError(code + ': malzeme temel birimi tekil olarak doğrulanamadı.')
        material_unit = units.pop()
        # No fallback to a different plant or valuation type.
        price = connection.execute("""SELECT SUM(unrestricted_value)/SUM(qty) FROM mb52
              WHERE plant=? AND material_code=? AND upper(valuation_type) IN ('YENI','YENİ')
                AND qty>0 AND unrestricted_value IS NOT NULL""", (source_uy, code)).fetchone()[0]
        rows = [dict(r) for r in connection.execute('SELECT * FROM kesif WHERE dy=? AND material_code=?', (dy, code)).fetchall()]
        ex = exempt.get(code, {})
        work_codes = {text(r['work_code']).upper() for r in rows}
        if len(work_codes) > 1:
            raise BalanceError(code + ': aynı depo/malzemede birden fazla iş türü bulundu.')
        if target_tesis and work_codes and work_codes!={'T'}:
            raise BalanceError(code + ': depo iş türüyle keşif iş türü uyuşmuyor.')
        is_tesis = target_tesis or work_codes == {'T'}
        projects = {}
        project_ids={text(r['project_id']) for r in active_projects}
        for row in rows:
            discovery_unit = text(row.get('uom'))
            # Kurumsal keşif CSV'lerinde birim sütunu olmayabilir; boş birim
            # MB52'de doğrulanmış tekil temel birimi kullanır (indeks özetleriyle aynı).
            normalized_discovery = unit(discovery_unit)
            if not normalized_discovery:
                discovery_unit = material_unit
            elif not ex.get('discoveryExempt') and normalized_discovery != material_unit:
                stock_units = ', '.join(sorted({text(r[0]) for r in master if text(r[0])}))
                location = ' / '.join(filter(None, (text(row.get('sheet')), text(row.get('row_no')))))
                raise BalanceError(
                    f'{code}: {uy}/{dy} keşif birimi ({discovery_unit}) '
                    f'MB52 temel birimiyle ({stock_units}) uyuşmuyor.'
                    + (f' Keşif kaynak satırı: {location}.' if location else '')
                )
            if not ex.get('discoveryExempt') and (row.get('issue') or row.get('mismatch')):
                raise BalanceError(code + ': kaynak keşif miktarlarında tutarsızlık var.')
            if not is_tesis:
                continue
            name = text(row.get('project'))
            if not name:raise BalanceError(code + ': TESİS proje adı eksik.')
            matching=[p for p in known_projects if project_name(p['project_name'])==project_name(name)]
            ids={text(p['project_id']) for p in active_projects if project_name(p['project_name'])==project_name(name)}
            if matching and not ids:raise BalanceError('Proje pasif: '+name)
            if len(ids) > 1:
                raise BalanceError('Proje adı birden fazla proje kimliğine karşılık geliyor: ' + name)
            pid = ids.pop() if ids else stable_project_id(dy, name)
            project_ids.add(pid)
            if row.get('remaining') is None:projects[pid]=None
            elif pid not in projects or projects[pid] is not None:projects[pid] = projects.get(pid, 0) + float(row['remaining'])
        output[code] = {'uom': material_unit, 'unitPrice': price, 'isTesis': is_tesis,
                        'discoveryRemaining': sum(float(r['remaining']) for r in rows) if rows and all(r.get('remaining') is not None for r in rows) else None,
                        'projects': projects, 'projectIds':sorted(project_ids) if is_tesis else [],'discoveryExempt': bool(ex.get('discoveryExempt')),
                        'guaranteeExempt': bool(ex.get('guaranteeExempt'))}
    all_guarantee_exempt=bool(output) and all(r['guaranteeExempt'] for r in output.values())
    if not all_guarantee_exempt and (len(guarantees)!=1 or guarantees[0][0] is None):
        raise BalanceError('ZMM098 hedef depo kullanılabilir tutarı tekil olarak bulunamadı.')
    available=guarantees[0][0] if len(guarantees)==1 else None
    return {'materials': output, 'guaranteeAvailable': available, 'fingerprints': fingerprints}
