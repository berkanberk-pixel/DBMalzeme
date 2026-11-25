# Talep Kontrol — Kullanıcı Kılavuzu

Bu paket uygulama dosyalarıdır; Windows kurulum EXE'si veya NSIS projesi değildir.

## Başlatma

Klasörü yerel bilgisayarınıza çıkartın. `Talep Kontrol.vbs` dosyasına çift tıklayın. Komut penceresi açılmadan açılış ekranı görünür. Windows WebView2 Runtime ve Python çalışma ortamı gereklidir; ortamda bulunmuyorsa BT desteği alın.

## Veri kaynakları

Yalnız yetkili `8-Talep Kontrol` ağ yolundaki `1-ZMM048`, `2-MB51`, `3-MB52`, `4-Keşifler` ve `5-Tanımlar` klasörleri okunur. Alt klasörler taranır. ZMM098, uygulamanın mevcut kaynak tanıma kurallarınca bulunabiliyorsa kullanılır; ayrı bir ZMM098 yolu uydurulmadı. `.csv`, `.xlsx`, `.xlsm` desteklenir; `.xls` ve `.xlsb` için Windows üzerinde Microsoft Excel gerekebilir.

Yerel SQLite indeksi `%LOCALAPPDATA%\TalepKontrol\Index` altına yazılır. **Bu indeksi ortak ağa taşımayın.** İlk çalıştırmada uygun kaynak bulunursa indeks arka planda hazırlanır. Ağ kesikse doğrulanmamış veriyi kesin sonuç olarak göstermeyin. Veri değişikliklerinin etkinleşmesi hâlâ mevcut kaynak kabul akışına bağlıdır.

## Kurumsal kayıt ve güvenlik

Merkezi kayıtların adresi `8-Talep Kontrol\0-Database` altıdır. **Kesin onay ve ortak kayıtlar güvenli merkezi yazma servisi onaylanana kadar kapalıdır.** Kaynak klasörü kilidi kaldırılmadı, hiçbir merkezi kayıt dosyası değiştirilmedi.

## Güncellemeler

Yayın klasörü `8-Talep Kontrol\9-Uygulama\Aktif` olarak tanımlıdır. Bu sürüm kurumsal paketi kendi kendine indirip sessiz kurmaz; mevcut merkezi güncelleme sistemi üzerinden yetkili yayın ve kontrollü kurulum yapılmalıdır.

## Hata halinde

- “Bağlantı kesildi”: Önce uygulama ve yerel Python servisinin açık olduğunu kontrol edin. Servis sağlık kontrolü ağır indeks taramasından ayrılmıştır.
- “SQLite indeksi hazır değil”: Kaynakların erişimini kontrol edin. İlk indeks arka planda kurulurken tam sütun filtreleri doğru veri üretmez; hazırlanmasını bekleyin ve Veri Merkezi durumunu kontrol edin.
- “Merkezi kayıt koruması etkin”: Bu bir servis hatası değildir, kesin onay yetkisi kapalıdır.
- “Kaynak bulunamadı”: BT ile UNC klasörleri ve yetkileri doğrulayın.
- Görünüm sorunları: Windows ve WebView2 Runtime ile kurumsal ortamda doğrulayın.

## Dağıtım notları

Yeni çalışanlara uygulama kaynaklarını yerel kullanıcı klasörüne dağıtın. Güncellerken `data_v2`, `kayitlar` ve kullanıcının `%LOCALAPPDATA%\TalepKontrol` klasöründeki kayıtlarını silmeyin. Veri kaynaklarını ve merkezi kayıtları ZIP'e dahil etmeyin. Kurumsal uç nokta güvenlik politikasını aşmaya çalışmayın. Uygulamayı canlı yayına almadan önce BT güvenlik onayı, kaynak ve fonksiyon testleri gerekir.
