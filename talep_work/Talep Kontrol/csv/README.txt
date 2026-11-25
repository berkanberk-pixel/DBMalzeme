V3.13.0 paket içi hazır CSV veri seti

Bu klasör giriş/kaynak verisidir. Uygulamanın büyük veri çalışma katmanı JSON değildir.
Akış: CSV -> Parquet + yerel SQLite indeks -> sayfalı/filtreli ekran sorgusu.

Operasyonel kaynaklar:
- ZMM048.csv
- ZMM098.csv
- MB51.csv
- MB52.csv
- Tesis_Verileri.csv
- KET_Verileri.csv
- BAKIM_Verileri.csv
- LED_Verileri.csv

Master kaynaklar:
- SITE_MALZEMELER.csv
- TB_Depo_Kodlari.csv
- SITE_PROJELER.csv
- TB_Islem_Turu.csv
- TB_Tedas_Kod.csv

Hazır Parquet dosyaları: parquet/ACTIVE
Hazır sorgu indeksi: cache/talep_index.sqlite
Kaynak CSV değişmediği sürece paket açılışında yeniden oluşturma yapılmaz.

Muafiyet ayar dosyası:
- MUAF_LISTESI.csv (Keşif / Teminat muafiyetleri; veri kaynağı taramasına dahil edilmez)
