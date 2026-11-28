# Revizyon günlüğü

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
