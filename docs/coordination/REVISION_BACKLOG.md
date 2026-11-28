# Açık revizyonlar ve kabul koşulları

Temel: `8618f5248aa66732e1b065d5be331d30ccd586d9`, 28 Kasım 2026.
Bu dokümantasyon commit'inde uygulama düzeltmesi yapılmadı. Kimlikler sonraki revizyonlarda korunmalıdır.
P1/P2 inceleme önceliğidir; mimari ve iş kararı satırları ayrı değerlendirilir.
Kaynak ve satır bağlantıları [ayrıntılı raporda](reviews/2026-11-28-8618f524.md), çıktılar [kanıt dosyasında](reviews/2026-11-28-evidence.json).

Önerilen sıra: F-001/F-002/F-004, ardından F-003/F-008; F-006/F-007/F-009. F-005 ve F-010 bağımsız mimari/iş takibi gerektirir.

## F-001 — P1 — Düzeltildi (HIZ-004 / talep-cdf67c833a014401)

Dosyalar/akış: `source_row_diff.py: BUSINESS_KEYS, map_rows`.

Gözlem: Aynı rezervasyon/malzeme/kaynak/hedefte kalem 10 qty2→9, kalem 20 qty3 sabit: toplam 5→12; map tek satıra düşüyor ve hasChanges=false.

Kabul koşulu: Kalem ve mükerrer satırlar kayıpsız tutulmalı; tek kalem değişimi yakalanmalı; ekleme/silme/sıra değişikliği ve toplamlar test edilmeli.

Kanıt: ZMM048 `res_item` + occurrence; `test_zmm048_kalem_keeps_duplicate_items`. İndeks şemasında kalem kolonu hâlâ yok (ayrı sınır).

## F-002 — P1 — Düzeltildi (HIZ-004 / talep-cdf67c833a014401)

Dosyalar/akış: `server.py: accept noRowChange; indexed_engine.py: active_build_state`.

Gözlem: Aynı veriye boş satır ekleme: kabul ACTIVE, rebuild yok; indeks STALE/sourceIndexMatch=false.

Kabul koşulu: Fiziksel ve semantik kaynak sürümleri tutarlı izlenmeli; eşdeğer kabulden sonra READY/sourceIndexMatch doğru, gerçek değişimde eski indeks kullanılmıyor olmalı.

Kanıt: `retarget_active_signature`; `test_retarget_keeps_ready_after_no_row_change`.

## F-003 — P2 — Kısmi (HIZ-004 / talep-cdf67c833a014401)

Dosyalar/akış: `indexed_engine.py: _clear_source_tables, build_engine`.

Gözlem: İki ZMM098 satırından biri değişti; incremental=true fakat tablo tamamen silindi, iki satır okundu.

Kabul koşulu: Anahtarlı ekle/güncelle/sil deltası gerçekten uygulanmalı; değişmeyen satırların yeniden işlenmediği ve etkilenen toplamların doğruluğu ölçülmeli.

Kanıt: ZMM098/MB52 keyed delta (`rowDelta`); MB51/KESIF/TANIMLAR/ZMM048 hâlâ kaynak tablosu reload.

## F-004 — P1 — Yeniden üretildi

Dosyalar/akış: `central_security.py: role_allowed; server.py: /api/user-responsibilities`.

Gözlem: role_allowed her zaman False; yönetici gibi yapılandırılmış sentetik oturumda kayıt 403/AD_ADMIN_REQUIRED.

Kabul koşulu: Yetkili ve yetkisiz gerçek Windows/AD bağlamları ayrılmalı; yetkili sorumluluk kaydı ve geri okuması geçmeli. Güvenliği bypass etmeyin. final_record_allowed_here ayrı akıştır; bütün kayıtlar kapalı sonucu çıkmaz.

## F-005 — Mimari — Hedefle farklı

Dosyalar/akış: `START_GUI.ps1; installer_src/TalepKontrol.Setup.csproj`.

Gözlem: Mevcut masaüstü WinForms + WebView2/localhost HTML; kullanıcı bağımsız web ve tamamen yerel WPF seçti.

Kabul koşulu: Yerel WPF ekranları ve bağımsız web teslimi istenen fonksiyonlarla doğrulanmalı; EXE/kurucu varlığı WPF kanıtı sayılmamalı.

## F-006 — P2 — Kısmi / eksik

Dosyalar/akış: `app.js operasyon filtreleri, user_context ve sorumluluk ekranları`.

Gözlem: İl→ÜY→depo zincirinde il yok; TESİS üstte ÜY de yok. Rol/il modeli var ama kişiselleştirme yalnız tek tercihli depoya kadar.

Kabul koşulu: Birincil/yedek iller ve iş/depo sınırlarıyla varsayılan filtre ve bildirim kapsamı doğrulanmalı; il değişince bağlı filtreler geçersiz seçimi temizlemeli.

## F-007 — P2 — Yeniden üretildi

Dosyalar/akış: `app.js: workOpsProjectLabel`.

Gözlem: Depo seçili/seçili değil iki çağrı da yalnız Proje A döndürüyor; depSelected kullanılmıyor.

Kabul koşulu: Depo yokken kod/ad/sözleşme/proje; depo varken tekrarsız proje adı test edilmeli.

## F-008 — P1 — İş akışı eksik

Dosyalar/akış: `server.py: auto_accept_pending_sources; silent_active_accept`.

Gözlem: Asenkron kabul var ama açık işi eski sürümde sabitleme ve iş sonunda yeni sürüme geçiş protokolü bulunmadı.

Kabul koşulu: Ertele/arka planda hazırla seçenekleri; açık işte sabit sürüm; yeni kaynak READY olduktan ve iş bittikten sonra geçiş; fark uyarısı ve hata/iptal senaryosu test edilmeli. Sabit snooze süresi kullanıcı kararı değildir.

## F-009 — P2 — Kodda doğrulandı

Dosyalar/akış: `app.js: HISTORY; bildirim temizleme/audit`.

Gözlem: SAFE temizleme açık CRITICAL/WARNING kayıtları koruyor; CLEARED saklanıyor ama HISTORY filtresinde gösterilmiyor.

Kabul koşulu: Temizlenen kayıtlar geçmişte bulunabilmeli, derin bağlantı/audit korunmalı; temizleme kapsamı açık olmalı. Mevcut SAFE politikası bağlayıcı yeni kullanıcı kararı değildir.

## F-010 — İş kuralı — Açık karar / fark doğrulandı

Dosyalar/akış: `CURRENT_RULES.json ve önceki harici FIX13 teslimi`.

Gözlem: 19 alan farkı; kaynak verilen/kalan sütunlarından MB51 fiili+taahhüt hesabına geçilmiş. Karar sonuçları değişebilir.

Kabul koşulu: Son kullanıcı iş bağlamı doğrulanmalı; seçilen formül sürümlenmeli ve aynı veride önce/sonra karar farkları açıklanmalı. Otomatik geri alma veya yeni formülü onaylama yapılmamalı.

## F-011 — Test — Windows test sorunları

Dosyalar/akış: `talep_work/tests`.

Gözlem: 67 test:64 geçti/1 fail/1 error/1 skip. CRLF fixture 8 yerine10 bayt; SQLite cleanup WinError32; EXE yokluğu skip.

Kabul koşulu: Fixture gerçek bayt boyutunu esas almalı; bağlantılar kapanmalı; Windows koşumu tekrar yapılmalı. Cleanup hatası iş kuralı assert hatası değildir.

## F-012 — Kabul — Canlı doğrulama eksik

Dosyalar/akış: `Dağıtım ve çoklu istemci çalışma ortamı`.

Gözlem: Config/manifest release ve ZIP boyutu eşleşti; gerçek ZIP SHA/içerik, kurucu, UNC/AD/SMB, tüm UI ve çoklu PC test edilmedi.

Kabul koşulu: Temiz çıkarılmış ZIP hash/build/start/health/READY, karar/mutabakat/proje/bildirim/kimlik testleri; gerçek ACL ve eşzamanlı yayın senaryoları tamamlanmalı. Process-içi kilit gözlemi tek başına kanıtlanmış yarış hatası değildir.
