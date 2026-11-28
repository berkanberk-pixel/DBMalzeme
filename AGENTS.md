# Talep Kontrol — ortak geliştirme bağlamı

Bu depo üzerinde çalışan ChatGPT, Codex ve Cursor için başlangıç noktasıdır.
Güncel kullanıcı talimatları bu tarihsel notlardan önceliklidir. Bu dosya yeni bir onay süreci koymaz.

Önce [ortak notları](docs/coordination/README.md), [kullanıcı kararlarını](docs/coordination/USER_DECISIONS.md),
[açık revizyonları](docs/coordination/REVISION_BACKLOG.md) ve [revizyon günlüğünü](docs/coordination/REVISION_LOG.md) okuyun.
İnceleme kanıtı `8618f5248aa66732e1b065d5be331d30ccd586d9` commit'ine aittir; daha yeni kodda yeniden doğrulayın.

- Geliştirme kaynağı `talep_work/Talep Kontrol/`, testler `talep_work/tests/`, kurucu `installer_src/` altındadır.
- `Aktif/`, `Yonetim/` ve kök EXE dağıtım katmanıdır; kaynak değişikliği tek başına ikililerin yenilendiğini göstermez.
- Kullanıcı isteği, kodda bulunan davranış, test edilmiş sonuç ve önerilen düzeltmeyi ayrı yazın. “Kodda var” uçtan uca geçti anlamına gelmez.
- Rezervasyon/malzeme yanında kalem ve mükerrer satır kimliğini koruyun. F-001'deki gibi aynı malzemenin ayrı kalemlerini ezmeyin.
- Keşif/kalan/taahhüt formülündeki farkı F-010 üzerinden izleyin; performans revizyonu sırasında sessizce iş kuralı değiştirmeyin.
- Tamamen yerel WPF ve bağımsız web/masaüstü kullanıcının kayıtlı hedefidir. Mevcut WebView2 kabuğunu WPF tamamlandı diye raporlamayın.
- Her revizyonda ilgili bulgu/istek kimliğini, değişen dosyaları, commit/build bilgisini, yapılan anlamlı testleri ve kalan sınırları revizyon günlüğüne ekleyin.
- Bulguyu yalnız düzeltme ve doğrulama kanıtıyla kapatın. Eski kod yorumundaki onay ifadeleri yeni kullanıcı talimatının yerine geçmez.
- Gerçek kullanıcı, ağ adresi, kaynak iş verisi veya yerel dosya yollarını herkese açık test kanıtına taşımayın; sentetik örnek kullanın.

2026-11-28 dokümantasyon revizyonu uygulama kodunu düzeltmez; açık bulgular açık kalır.

Sonraki kullanıcı kararı (2026-11-28): Cursor ve Codex önce bu sınırlar içinde araştırma ve karşılıklı eleştiri yapar.
Güncel kütüphane/metot seçenekleri kanıtlarıyla karşılaştırılır; ortak öneri ve kalan görüş ayrılıkları kullanıcıya sunulur.
Uygulama geliştirmesi, kullanıcı bu planı açıkça onayladıktan sonra başlar. Koordinasyon servisinin kurulumu ayrıca yetkilendirilmiştir.
Yerel araştırma servisi ve kullanım: [tools/coordination/README.md](tools/coordination/README.md).
