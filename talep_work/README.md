# Talep Kontrol — geliştirme kaynağı

Bu klasör, GitHub dağıtım ZIP’inden ayrılmış uygulama kaynağıdır.

## 0-Database modeli

1. Kaynak dosyalar ilk okumada `0-Database/KAYNAK_VERILERI` altına kopyalanır.
2. Ağdaki değişiklik boyut/mtime ile adaylanır; gerekirse içerik SHA doğrulanır.
3. Kabulde yalnız değişen satırlar (iş anahtarı) işlenir; fark `gecmis/` altına yazılır.
4. Kaynak değişmedikçe yerel indeks ve merkezi kopya kullanılır.
5. Kontrol/karar paketleri `0-Database/KAYIT` altındadır.

## Test

```bash
python -m unittest discover -s talep_work/tests -v
```

## Not

Kurumsal Windows UNC yolları ve gerçek kaynak Excel/CSV doğrulaması canlı ağda yapılmalıdır.
