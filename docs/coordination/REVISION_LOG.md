# Revizyon günlüğü

## COORD-001 — 2026-11-28 — araştırma koordinasyon servisi

- Kullanıcı, yerel Cursor CLI ve mevcut hesabıyla bağlantıyı seçti; koordinasyon servisini kurmayı yetkilendirdi.
- Son kapsam: önce araştırma ve karşılıklı eleştiri; ortak plan kullanıcıyla incelenip onaylanmadan Talep Kontrol uygulama geliştirmesi başlamaz.
- `tools/coordination/`: yerel HTTP paneli, kalıcı kuyruk, Cursor → Codex → Cursor → Codex dört turluk aktarım, iptal/duraklatma, günlük çağrı ve süre sınırı.
- Kaynak bağlamı ilk turda sabitlenir. CLI dosya okuma engelliyse ajanlara bu açıkça işaretlenmiş bağlam aktarılır. Güncel metot önerileri için resmi kaynak istenir.
- Cursor plan modu ve Codex read-only sandbox; plan onayı yalnız kaydedilir, geliştirme süreci başlatılmaz.
- Kod/HTTP testleri: 21 test geçti; gerçek süreç iptali, eşzamanlı kuyruk, crash sonrası tekrar engeli, bağlantı olmadan görev başlatmama ve onay sınırı dahil. Python AST ve panel JavaScript syntax geçti.
- İzole tarayıcı panel testi: giriş anahtarının URL'den kaldırılması, görev oluşturma/iptal, 390px taşma ve JavaScript hata kontrolü geçti.
- Codex mevcut hesap bağlantısı çalıştı. Cursor CLI indirildi; tam canlı dört turluk tartışma, iki hesabın bağlantısı tamamlanmadan doğrulanmış sayılmaz.
- Sabit kaynak paketiyle Codex statik servis incelemesi yapıldı; süreç ağacı kapatma, tutarlı okuma, atomik dışa aktarım ve istek sıralaması iyileştirildi.
- Talep Kontrol kaynakları ve dağıtım ikilileri değiştirilmedi. Bu servis revizyonu uygulama bulgularını kapatmaz; Cursor'un HIZ revizyonlarındaki kayıtlar korunur ve ayrı doğrulanır. Kullanıcı parolası, CLI oturumu ve yerel servis anahtarı depoya eklenmez.

## HIZ-005 — 2026-11-28 — Merkez salt-okunur snapshot seed (fast boot)

- Kullanıcı isteği: hız paketi adım 5 (final); `0-Database/KAYNAK_INDEKS` → yerel Index hızlı boot.
- Önceki: snapshot publish/seed vardı ama seed gecikmeliydi; MISSING’te cold rebuild riski.
- Yeni: `ensure_seeded_once` + `_ensure_central_index_seed`; `/api/files`/`_engine_snapshot` MISSING’te seed; usable seed sonrası cold rebuild yok; Ctrl+Q `seededFromCentral`.
- Dosyalar: `central_index_snapshot.py`, `server.py`, `indexed_engine.py`, `app.js`, `test_central_index_snapshot.py`, `test_central_seed_fast_boot.py`, `test_boot_handoff.py`, Aktif `talep-f02c99deb4b4f0d0`.
- Test: `python3 -m unittest discover -s talep_work/tests` → 100 OK.
- Kilitler: ortak yazılabilir SQLite yok; sunucu yok; yalnız salt-okunur merkez artifact kopyası.
- PR #1 branch: `cursor/central-source-incremental-7260`.

## HIZ-004 — 2026-11-28 — Incremental + async forceScan

- Kullanıcı isteği: hız paketi adım 4 / [15]; `source_row_diff` + forceScan arka plan güçlendir.
- Önceki: satır diff kalemsiz ZMM048 (F-001); no-row-change STALE (F-002); incremental = tablo reload (F-003); accept sonrası `force=True` UNC.
- Yeni: ZMM048 `res_item` + occurrence; `retarget_active_signature`; ZMM098/MB52 keyed delta; `/api/files?refresh=1` ve accept yolu UNC’yi HTTP’de bekletmez.
- Dosyalar: `source_row_diff.py`, `indexed_engine.py`, `server.py`, `test_source_row_diff.py`, `test_async_force_refresh.py`, `test_incremental_row_delta.py`, `test_boot_handoff.py`, Aktif `talep-cdf67c833a014401`.
- Test: `python3 -m unittest discover -s talep_work/tests` → 94 OK.
- Kilitler: ortak yazılabilir SQLite yok; sunucu yok. ZMM048 indeks şemasında kalem kolonu hâlâ yok (diff kalemli; tablo reload).
- PR #1 branch: `cursor/central-source-incremental-7260`.

## HIZ-003 — 2026-11-28 — Book → grid/API (ZMM048/MB52/ZMM098)

- Kullanıcı isteği: hız paketi adım 3 / [14]; IndexedDB book kaldır; indeks+`/api/grid`.
- Önceki: açılışta ZMM048/MB52/ZMM098 `/api/book` + IndexedDB; grid yalnız stok/teminat/keşif.
- Yeni: bu üç kaynak lazy book; karar seti `view=decision`; rezervasyon `view=reservations`; `/api/book` deferred.
- Dosyalar: `indexed_engine.py`, `server.py`, `app.js`, `test_book_grid_api.py`, `test_boot_handoff.py`, Aktif `talep-ce0206fea6b49158`.
- Test: `python3 -m unittest discover -s talep_work/tests` → 88 OK (sentetik indeks).
- Kilitler: ortak yazılabilir SQLite yok; sunucu yok. TANIMLAR book kaldı; zmm048 indeks kalem no taşımıyor.
- PR #1 branch: `cursor/central-source-incremental-7260`.

## DOC-001 — 2026-11-28 — ortak bağlamın depoya eklenmesi

- Kullanıcı isteği: ChatGPT ve Cursor'un revize edilen kısımları ortak dosyalardan anlayabilmesi.
- Kapsam: kök AGENTS.md, Cursor proje kuralı, ortak karar/backlog/inceleme/kanıt dosyaları ve iki README bağlantısı.
- Kod temeli: `8618f5248aa66732e1b065d5be331d30ccd586d9`; uygulama/build/release değişmedi.
- README düzeltmesi: “yalnız değişen satırlar işlenir” yerine satır farkı hesaplama ile değişen kaynak tablosunun bütünüyle yeniden indekslenmesi ayrıldı (F-003).
- İstek matrisi: ilk24 + son9 + merkezi5 = 38 satır; açık bulgular F-001…F-012.
- Önceki inceleme kanıtı: 67 test;64 pass/1 fail/1 error/1 skip, Python/Node syntax geçti. Bunlar bu dokümantasyon revizyonunda yeni koşulmuş uygulama testleri değildir.
- Bu revizyon doğrulaması: UTF-8/JSON, göreli belge bağlantıları ve dokümantasyon kapsamı kontrol edilir; uygulama kodu ve dağıtım ikililerine dokunulmaz.
- Kapatılan uygulama bulgusu: yok. Yeni uygulama sürümü/ZIP/SHA teslimi: yok.

## Sonraki kayıt için şablon

Tarih / kimlik / commit / build:

Kullanıcı isteği veya bulgu kimliği:

Önceki davranış ve yeni davranış:

Değişen dosyalar:

Test komutu, ortamı ve sonucu; gerçek ortam ile sentetik test ayrımı:

Kapanan bulgular ve kanıt bağlantısı:

Kalan sınırlamalar / açık kararlar:
