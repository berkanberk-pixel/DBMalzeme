# Kullanıcının teyit ettiği hedefler

Kaynak: “Veri Arşivleme 2” devamındaki bu geliştirme konuşması ve sonraki doğrudan kullanıcı düzeltmeleri.
Bu liste talep kaydıdır. Tamamlanma durumu [inceleme matrisindedir](reviews/2026-11-28-8618f524.md).
Yeni doğrudan kullanıcı kararları bu kaydı güncelleyebilir; kodun mevcut olması tek başına yeni karar kanıtı değildir.

## Mimari ve arayüz

- İlk temel paket FIX11; önceki çalışan özellikleri koruma ve FIX12 ZIP/SHA256/test teslimi istenmişti.
- Daha sonra web ve masaüstü **birbirinden bağımsız uygulamalar** olarak istendi.
- Kullanıcı “Tamamen yerel WPF arayüzü; ekranlar yeniden yazılır” seçeneğini açıkça seçti. Gömülü HTML/WebView2 hedefin karşılığı değildir.
- Adminuiux referansı masaüstü görünümü içindir. Web ilk formatında kalmalı; masaüstü tasarımı web'e taşınmamalı.
- C# framework/kütüphaneleri kullanılabilir. Bu izin WPF kararını geri almaz.
- Paylaşılan Talep Kontrol logosu uygulama içi ve kısayolda kullanılmalı; uygulama içinde hafif hareket eklenebilir.
- Grafik görsel tasarımı sonradan planlanacak; mevcut basit grafik yeterli. Stok devir hızı, ortalama stok, stokta kalma günü kapsam dışı.

## İlk 24 isteğin kaydı

| Kimlik | İstenen davranış |
|---|---|
| İlk-1 | Kalem Kararı malzeme/keşif tablosundan çıkarılır; Karar Destek Sonucu'nda satır bazlı Onayla/Onaylama/Beklet modalı olur. |
| İlk-2 | BAKIM/KET&YB/LED/TESİS keşfi malzeme bazlı gösterir. |
| İlk-3 | Aylık Harcamalar ay adları ve malzeme bazında; 221/222/Z22 hesapta kullanılır, Hareket/Hareket Türü sütunları görünmez. |
| İlk-4 | Her operasyon modülünde Excel ve PDF dışa aktarım olur. |
| İlk-5 | Depo filtresi Depo Kodu – Depo Yeri Tanımı – Sözleşme Adı gösterir. |
| İlk-6 | Tablodaki depo koduna tıklamak aktif depoyu değiştirir; bütün kart/tablo/veri yenilenir. |
| İlk-7 | Operasyon kartları alt alta düzenlenir. |
| İlk-8 | Teminat alanı daha ayrıntılı olur. |
| İlk-9 | Ara alanı canlı/dinamik filtreler. |
| İlk-10 | TESİS Yeni Proje Ekle ekranında keşif zorunludur; proje/keşif ekleme ve değişiklikleri bildirim üretir. |
| İlk-11 | Sağdan açılan Bildirim Merkezi; Kritik/İşlem Bekleyen/Bilgi seviyeleri, filtre, aksiyon, geçmiş ve derin bağlantı içerir. Eksik/hatalı/değişen veri, keşif/proje/dağılım, onaysız MB51, miktar farkı vb. kapsanır. |
| İlk-12 | Seçili depoya ait Yüklenici Kartı gösterilir. |
| İlk-13 | TESİS proje filtresinde depo seçiliyse tekrarlanmaz; seçili değilse Depo Kodu – Depo Adı – Sözleşme Adı – Proje bağlamı gösterilir. |
| İlk-14 | Onayla ve Kaydet sonrası güncel MB51 ile Rezervasyon No + Malzeme mutabakatı; miktar farkı durumları; TESİS dağılımında kullanıcı onayı; onaysız kalemde hareket bildirimi olur. Ayrı kalemlerin kimliği korunur. |
| İlk-15 | Kaynak Sağlığı yalnız Veri Merkezi'nde; Eski Veriyle Devam Et / Yeni Veriye Güncelle / Değişiklikleri Gör akışı korunur. |
| İlk-16 | Windows DOMAIN\user, bilgisayar, oturum zamanı, uygulama sürümü ve mümkünse IP AUDIT'e yazılır; ortak PC'de kullanıcı kimliği esastır; fallback gerekir. |
| İlk-17 | Veri Merkezi'nde Kullanıcı & Yetki Yönetimi, Kullanıcı Sorumlulukları, Oturum & İşlem Geçmişi; rol, birincil/yedek iller, mümkünse iş türü/depo; kişisel varsayılan filtre/bildirim olur. |
| İlk-18 | Sağ üst kullanıcı kartında Windows kullanıcısı ve sorumlu iller gösterilir. |
| İlk-19 | Başarılı Kontrol Et ve Kaydet sonrası çalışma ekranının temizlenmesi korunur. |
| İlk-20 | Stok devir/ortalama stok/stokta kalma günü kapsam dışıdır. |
| İlk-21 | Teminat Bilgileri, Stok Hareketleri, Stok Bilgileri ayrı ana menü sayfaları olarak kalır. |
| İlk-22 | Operasyon İzleme yalnız BAKIM/KET&YB/LED/TESİS ayrı sayfalarıdır. |
| İlk-23 | Veri Arşivi/AUDIT bildirim, kullanıcı, proje, keşif ve karar olaylarını saklar. |
| İlk-24 | Basit grafik yeterli; nihai grafik tasarımı karara bağlanmaz. |

## Son 9 düzeltme — önceki taslağı değiştiren kararlar

| Kimlik | İstenen davranış |
|---|---|
| Son-1 | Bildirim temizleme olmalı. Geçmiş/AUDIT isteği de sürer; temizleme ile kalıcı kayıt silme aynı sayılmamalıdır. Açık kritiklerin temizleme politikası kullanıcı tarafından ayrıntılandırılmadı. |
| Son-2 | Sürekli güncellik uyarısı yerine ertele veya arka planda çalıştır seçeneği; açık iş eski veriyle devam eder, yenisi arka planda hazırlanır, iş sonunda güncellenir ve farklar uyarılır. Sabit bir erteleme süresi seçilmedi. |
| Son-3 | Dört operasyonun yüklenici kartları üstte, diğer kartlardan farklı görünümde olur. |
| Son-4 | Stok Hareketleri/Stok Bilgileri kullanıcı başlıklarında MB51/MB52 yazıları olmaz. Teknik kaynak/audit kimlikleri ayrı bağlamdır. |
| Son-5 | Gönderilen logo kısayol ve uygulamada kullanılır; hafif hareket isteğe bağlıdır. |
| Son-6 | Referans UI masaüstü içindir; sonraki açık seçim tamamen yerel WPF'tir. |
| Son-7 | Depo filtrelerinde il olur; ile bağlı üretim yeri ve alt depolar otomatik daralır. |
| Son-8 | Web ilk formatında kalır; yeni masaüstü istekleri web tasarımına karıştırılmaz. |
| Son-9 | Web ve masaüstü bağımsız oluşturulur. |

## Merkezi veri yönü ve açık iş kuralı

Kullanıcı, Cursor dalındaki `0-Database` merkezi kopyası ve yalnız değişen satırları işleme yaklaşımının incelenmesini istedi.
Mevcut uygulama kaynak bazında yeniden indeksler; hedefle fark F-003'tedir. Aktif veriyle işlem sürerken yeni sürümün hazırlanması Son-2 ile birlikte ele alınmalıdır.

FIX13 ile daldaki keşif/verilen/kalan hesapları arasında 19 alan farkı var (F-010).
Önceki: Teslim Edilen − Verilen Malzeme Toplamı. İncelenen dal: Keşif − (MB51 fiili + ara/kesin taahhüt).
Daha yeni bir iş onayı bu konuşmada görülmedi. Bu belge iki formülden birini kendiliğinden onaylamaz veya geri almaz;
uygulayıcı son kullanıcı bağlamını kontrol etmeli ve formül değişikliğini ayrı, izlenebilir revizyon olarak kaydetmelidir.

İlk teslimde temiz klasöre çıkarılmış ZIP üzerinden syntax, duplicate ID, build eşleşmesi, start/health,
Engine READY/sourceIndexMatch, kaynak akışı, kısmi karar, bildirim, Windows fallback, sorumluluk yönetimi,
operasyon API'leri, TESİS proje ekleme ve mutabakat testleri istenmiştir. Mevcut dal incelemesi bu tam kabulün yerine geçmez.
