# Talep Kontrol — geliştirme kaynağı

Bu klasör, GitHub dağıtım ZIP’inden ayrılmış uygulama kaynağıdır.
[Ortak proje notları](../docs/coordination/README.md), kullanıcı kararlarını ve açık revizyonları içerir.

## 0-Database modeli

1. Kaynak dosyalar ilk okumada `0-Database/KAYNAK_VERILERI` altına kopyalanır.
2. Ağdaki değişiklik boyut/mtime ile adaylanır; gerekirse içerik SHA doğrulanır.
3. Satır farkları iş anahtarlarıyla hesaplanır ve geçmişe kaydedilir. İncelenen indeks, değişen kaynak tablosunu bütünüyle yeniler; gerçek satır delta uygulaması [F-003](../docs/coordination/REVISION_BACKLOG.md) olarak açıktır.
4. Kaynak değişmedikçe yerel indeks ve merkezi kopya kullanılır. Satır eşdeğer dosya güncellemesinde kaynak/indeks imzası tutarlılığı [F-002](../docs/coordination/REVISION_BACKLOG.md) kapsamında izlenir.
5. Kontrol/karar paketleri `0-Database/KAYIT` altındadır.

## Test

Depo kökünden:

```bash
python -m unittest discover -s talep_work/tests -v
```

28 Kasım 2026 incelemesi: 67 test; 64 geçti, 1 başarısız, 1 hata, 1 atlama.
Windows fixture/cleanup ayrıntıları ve kapsam [inceleme raporundadır](../docs/coordination/reviews/2026-11-28-8618f524.md).
Bu sayılar `8618f5248aa66732e1b065d5be331d30ccd586d9` commit'ine aittir; yeni commit için tekrar doğrulanmalıdır.

## Not

Kurumsal Windows UNC yolları, AD/SMB yetkileri, çoklu PC ve gerçek kaynak Excel/CSV doğrulaması canlı ağda yapılmalıdır.
Kaynak notlarının güncellenmesi dağıtım ZIP/EXE'sinin güncellendiği anlamına gelmez.
