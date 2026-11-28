# ChatGPT / Cursor ortak proje notları

Son kayıt: 28 Kasım 2026. Bu belgeler kullanıcının “revize ettiğimiz kısımları diğer araçlar da anlayabilsin” talebiyle eklenmiştir.
Ortak yazılı bağlamdır; uygulamalar arasında otomatik sohbet belleği paylaşımı iddiası değildir. İlgili dalın güncel dosyaları okunmalıdır.

## Okuma sırası

1. [Kullanıcı kararları ve hedef](USER_DECISIONS.md)
2. [Açık revizyonlar ve kabul koşulları](REVISION_BACKLOG.md)
3. [Revizyon günlüğü](REVISION_LOG.md)
4. [38 maddelik mevcut durum incelemesi](reviews/2026-11-28-8618f524.md)
5. [Sentetik test özeti](reviews/2026-11-28-evidence.json) ve [19 alanlık kural farkı](reviews/2026-11-28-rules-diff.json)

Kök [AGENTS.md](../../AGENTS.md) ortak giriş dosyasıdır. Cursor için ayrıca `.cursor/rules/talep-kontrol-context.mdc` eklenmiştir.
Kural dosyası biçiminin kaynağı: [Cursor resmi kurallar dokümanı](https://cursor.com/docs/rules).

## İncelenen sürüm

- Depo: `berkanberk-pixel/DBMalzeme`
- Dal: `cursor/central-source-incremental-7260`; mevcut [PR #1](https://github.com/berkanberk-pixel/DBMalzeme/pull/1)
- İncelenen kod commit'i: `8618f5248aa66732e1b065d5be331d30ccd586d9`
- Config: `1.0.4` / `20261127-v1.0.4-async-force`; release `talep-3548f277c3dbf2a0`
- Daha önce paylaşılan FIX12/FIX13 ZIP'leri ayrı teslimlerdir; bu daldaki kodla eşit oldukları varsayılmamalıdır.

## Mevcut teknik durum

Merkezi kaynak kopyası `0-Database/KAYNAK_VERILERI`, merkezi indeks snapshot'ı `0-Database/KAYNAK_INDEKS`,
yerel kullanıcı indeksi ve `0-Database/KAYIT/STAGING → COMMITTED` karar paketleri kodda vardır.
Ortak yazılabilir SQLite yerine yerel indeks kullanılır. Boyut/mtime aday taraması ve SHA kontrolleri vardır.
Değişen kaynak tablosu bütünüyle yeniden işlenir; gerçek satır delta indeksi henüz doğrulanmış bir özellik değildir (F-003).

Öncelikli açıklar: satır farkında kalem kaybı (F-001), eşdeğer satır kabulünde STALE indeks (F-002),
yönetici sorumluluk kaydında 403 (F-004). Yerel WPF/bağımsız uygulamalar, il zinciri ve iş sonunda veri geçişi hedefleri eksiktir.
Dokümantasyon eklenmesi bu açıkları kapatmaz.

## Durum sözlüğü

- **Kullanıcı kararı:** sohbetten kaydedilen hedef; tamamlandığı anlamına gelmez.
- **Kodda var:** kaynak incelemesinde bulundu; gerçek kullanıcı/UNC/kurucu akışı geçilmiş sayılmaz.
- **Yeniden üretildi:** sabit commit üzerinde sentetik senaryo ile görüldü.
- **Açık karar:** eldeki konuşma/kod eşitliği kanıtlamıyor; son iş bağlamı gerekir.
- **Düzeltildi:** ancak yeni commit ve ilgili kabul testi kanıtı eklendiğinde kullanılır.

67 testten 64'ü geçti; 1 başarısızlık, 1 hata ve 1 atlama var. İki sorun Windows test fixture/temizlik ayrıntılarıyla ilgilidir.
Syntax geçti. Canlı UNC/AD/SMB, çoklu PC, kurucu, tüm UI ve dağıtım ZIP SHA256 doğrulaması yapılmadı.
