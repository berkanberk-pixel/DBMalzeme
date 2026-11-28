# Cursor ↔ Codex araştırma koordinasyonu

Kullanıcı kararı (28 Kasım 2026): Önce belirlenen sınırlar içinde araştırma ve fikir alışverişi yapılır.
Güncel kütüphane/metot seçenekleri karşılaştırılır; ortak öneri kullanıcıyla incelenir.
**Uygulama geliştirmesi ancak kullanıcı planı onayladıktan sonra ayrı görev olarak başlar.**

Bu servis yerel Cursor CLI ile Codex CLI arasında görev ve yanıt aktarır. İki ürünün açık sohbet pencerelerini birbirine bağlamaz;
mevcut hesapları kullanan yeni terminal ajan oturumları başlatır. İnsan onayı olmadan geliştirme başlatmaz.

## Tartışma akışı

1. Cursor mevcut kod ve kullanıcı kararları üzerinden seçenekleri araştırır; resmi kaynakları gösterir.
2. Codex bağımsız olarak eleştirir, uyum ve eksik kanıtları kontrol eder; alternatif önerir.
3. Cursor eleştirilere yanıt verir ve önerisini düzeltir.
4. Codex ortaklaşılan noktaları ve süren anlaşmazlıkları içeren karar dosyasını hazırlar.

Sonuç `READY_FOR_USER_REVIEW` olur. Panelde “Planı onayla” yalnız onayı kaydeder; hiçbir kod/kurulum/yayın işini tetiklemez.
Bir ajanın yanıt vermiş olması önerinin iki tarafça onaylandığı anlamına gelmez; anlaşmazlıklar saklanır.

Cursor `--mode ask`, Codex `--sandbox read-only` ile çalışır. Ask modu dosya değiştirmeden metin yanıtı üretir; önerilen uygulama planı bu metnin içinde sunulur. Ajanlar kaynak değiştirme, paket kurma, commit/push/merge/deploy yapmama talimatı alır.
Cursor `--trust` yalnız yapılandırılmış proje/araştırma dizinlerinin normal güven kaydını oluşturur; `--force`, `--yolo` veya genel komut onayı atlama kullanılmaz.
CLI'nin kendi oturum/cache dosyaları ve servisin yerel tartışma kayıtları yazılır. Bu salt-okunur araştırma, CLI sandbox/politikalarının sunduğu sınırlar içinde yürür.
Güncel bilgi için web araçları ajan politikasına bağlıdır; web erişimi engelliyse sonuçta doğrulanamadığı belirtilmelidir.
Codex'e yerel CLI'nin `--search` seçeneğiyle web araştırması açılır. Yerel dosya okuma araçları yönetilen politikada engellenebildiği için
servis ilk turda belirli karar/kaynak dosyalarından `context.md` alır ve dört turda aynı bağlamı aktarır.
Kesilmiş dosyalar ve seçilmiş kod satırları açıkça işaretlenir; bu kopya tüm deponun incelendiği anlamına gelmez.

## Kurulum

Python 3.10+, Cursor CLI ve Codex CLI gerekir; Python üçüncü taraf bağımlılığı yoktur.
CLI'lerin kendi resmi giriş akışları kullanılır; parola/API anahtarı bu depoya yazılmaz.
Cursor CLI: [resmi kurulum ve kullanım](https://cursor.com/docs/cli/headless).
Codex: `codex exec --help` ile kurulu sürümün desteklediği seçenekler kontrol edilmelidir.

1. `config.example.json` dosyasını repo dışında `config.local.json` olarak kopyalayın ve mutlak yerel yolları ayarlayın.
2. Cursor'a aynı `CURSOR_CONFIG_DIR` ile `node <cursor-index.js> login` komutundan giriş yapın.
3. `codex login status` ile mevcut ChatGPT oturumunu doğrulayın.
   Uygulama içi tarayıcı indirme sayfasına yönlendiriyorsa Cursor girişini gerçek Windows terminalinde başlatın:

```powershell
./tools/coordination/Connect-Cursor.ps1 -Config C:/PATH/coordination/config.local.json
```

Bu komut kurulu CLI'yi kullanır ve sistemin normal tarayıcısını açar; Cursor masaüstünü yeniden kurmaz.

4. Servisi başlatın:

```powershell
./tools/coordination/Start.ps1 -Config C:/PATH/coordination/config.local.json
./tools/coordination/Open.ps1 -Config C:/PATH/coordination/config.local.json
```

Durdurmak için:

```powershell
./tools/coordination/Stop.ps1 -Config C:/PATH/coordination/config.local.json
```

Servis `127.0.0.1:8765` üzerinde çalışır. Open.ps1 yerel anahtarla paneli açar; anahtar terminale basılmaz.
Duraklatma yeni tur başlamasını engeller; mevcut tur tamamlanır. İptal mevcut ajan sürecini de sonlandırır.
Bilgisayar/app kapanınca bu servis bulutta devam etmez. Windows açılışına otomatik başlatma eklenmez; Start.ps1 tekrar çalıştırılabilir.

## Sınırlar ve kayıtlar

- Aynı anda 1 ajan; tartışma başına en fazla 4 çağrı, kuyrukta en fazla 10 tartışma.
- Varsayılan 24 saatte en fazla 12 ajan çağrısı ve çağrı başına 600 saniye. Bunlar parasal ücret garantisi değildir; sağlayıcının kullanım kotası geçerlidir.
- Oturum/hata/zaman aşımı durumunda otomatik yeniden deneme yapılmaz. Servis çöküp açılırsa yarım iş `INTERRUPTED` kalır.
- Önceki bütün yanıtlar sıradaki ajana iletilir. Uzun yanıtlar sessizce kırpılmaz; 24000 karakteri aşarsa görev hatayla durur.
- Yerel SQLite, `service.token`, CLI oturumları ve `discussions/<id>/` kayıtları **state_dir** altındadır; depoya eklenmez.
- Cursor proje geçmişi/güven işaretleri **cursor_data_dir** altındadır (belirtilmezse `state_dir/cursor-data`); global Cursor veri alanına yazılmaz. Windows'ta kısa bir yerel yol tercih edin.
- Her tartışma için okunabilir `discussion.md` ve tur çıktıları üretilir. Yayınlanacak özet, sır/kişisel yol/iş verisi açısından gözden geçirilmelidir.
- API yerel bearer anahtarı ister, yabancı Origin/Host isteklerini reddeder. Sağlık yanıtı yalnız servis durumunu gösterir.
- Otomatik GitHub paylaşımı yapılmaz; yerel araştırma, kullanıcı incelemesinden sonra seçilen özet/plan olarak depoya taşınabilir.

## API

`GET /health`; diğer uçlar `Authorization: Bearer <yerel-token>` ister:

- `GET /api/state`, `GET /api/jobs/<id>`
- `POST /api/jobs` → `{"title":"...","prompt":"..."}`
- `POST /api/pause` → `{"paused":true}`
- `POST /api/jobs/<id>/cancel` → `{}`
- `POST /api/jobs/<id>/approve` → `{}` (yalnız kayıt, kod çalıştırmaz)
- `POST /api/jobs/<id>/export` → `{}` (SQLite kaydından Markdown'ı yeniden üretir)
- `POST /api/shutdown` → `{}`
- `GET /api/connections`, `POST /api/cursor/login` → `{}` (yerel panelden resmi Cursor giriş akışı)

## Test

Depo kökünden:

```powershell
python -m unittest discover -s tools/coordination/tests -v
```

Kuyruk yarışları, dört turluk aktarım, iptal sonrası geç yanıt, crash sonrası tekrar engeli, günlük limit,
duraklatma, onayın geliştirme başlatmaması ve hata durumları sentetik testlerle doğrulanır.
Gerçek Cursor/Codex oturumları ayrıca bağlantı ve tartışma testiyle sınanmalıdır.

Her iki CLI hesabı da bağlı olmadan kuyruktaki işler başlatılmaz. Bağlantılar tamamlandığında, kuyruk duraklatılmamışsa araştırma otomatik başlar.
Panelden başlatılan hesap girişinde onay için 30 dakika beklenir; bu süre ajan araştırma turunun 600 saniyelik sınırından ayrıdır.
