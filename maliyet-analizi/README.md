# Maliyet Analizi

Açık ocak madencilik hakedişlerinin aylık kâr/zarar analizi. Gelir Master Data'dan okunur; mazot, depo ve personel
giderleri dağıtım anahtarlarıyla Maden pozlarına, TSF, RC ve Kiralık'a dağıtılır.

Tek kullanıcılı, kendi bilgisayarında çalışır. Veriler `data/maliyet.db` dosyasında tutulur (yedek almak için bu klasörü kopyala).

## Kurulum ve çalıştırma (Windows)

1. Bu klasörü bilgisayarına indir (GitHub'da **Code → Download ZIP**, sonra zip'i aç).
2. `maliyet-analizi` klasöründeki **`baslat.bat`** dosyasına çift tıkla.

`baslat.bat` her şeyi kendisi yapar:
- Bilgisayarda Python yoksa **Python 3.12'yi kendisi kurar** (önce winget ile, olmazsa python.org'dan indirerek). Yönetici izni gerekmez, sadece senin kullanıcına kurulur.
- İlk açılışta uygulamanın paketlerini `.venv` klasörüne kurar (birkaç dakika).
- Sonraki açılışlarda doğrudan uygulamayı tarayıcıda açar.

Windows "Bilinmeyen yayıncı" uyarısı verirse **Ek bilgi → Yine de çalıştır** de. Kurulum yarıda kalırsa
Python'u [python.org](https://www.python.org/downloads/)'dan elle kur ("Add Python to PATH" kutusunu işaretle) ve `baslat.bat`'ı tekrar çalıştır.

Denemek için örnek dosyalar: `python ornek_veri.py` komutu `ornek/` klasörüne ekran görüntülerindeki formatta 5 Excel üretir.

## Aylık akış

**Ay Paneli** her ay için ilerleme yüzdesini ve sıradaki adımı gösterir.

1. **Kurlar**: 1 USD kaç UZS, 1 litre mazot kaç UZS
2. **Veri Yükleme**: Ekipman listesi (bir kez, değiştikçe), Master Data, Mazot, Depo, Personel
3. **Gelir Eşleme**: Yeni Master Data kalemlerinin kâr merkezini onayla
4. **Çalışma Oranları**: Her ekipmanın pozlardaki çalışma yüzdesi (satır toplamı %100)
5. **Anahtarlar**: Elle girilen paylar (ör. Patlayıcı)
6. **Depo Anahtarları**: Ekipmana bağlı olmayan gider yerleri için anahtar
7. **Personel**: Her görev grubu için anahtar
8. **Kontroller** ve **Rapor**: uzlaştırmalar, kâr/zarar, dönem karşılaştırma, Excel'e aktarım

## Hesap kuralları

| Konu | Kural |
|---|---|
| Gelir | Master Data'daki **KDV'siz** tutar. Hakediş yeniden hesaplanmaz; miktar/fiyat boş olabilir |
| Maden | Her poz ayrı kâr merkezi. Diğer, Elektrik, Yemek, Prim, Yakıt Farkı gibi kalemler yazıldığı gibi Maden altında, gider almadan gösterilir |
| TSF, RC | Toplu tek kâr merkezi |
| Kiralık | Tüm ailelerdeki Kiralık satırları tek Kiralık kâr merkezinde toplanır |
| Mazot | Ekipman litresi × çalışma oranı. Maliyet = litre × UZS/L ÷ UZS/USD |
| Depo | Garaj no ekipman koduysa ekipmanın çalışma oranlarıyla; değilse Gider Yeri için seçilen anahtarla. UZS ÷ UZS/USD |
| Personel | Görev grubunun toplam maaşı (UZS ÷ UZS/USD) × seçilen anahtarın payı |
| Kamyon anahtarı | Pitworks'teki her KAMYON 1 sayılır, çalışma oranlarıyla pozlara dağılır |
| Ekipman anahtarı | Pitworks'te birincil ekipman = Evet olanlar, aynı yöntem |
| m³ anahtarı | Master Data miktarları (Maden pozları + TSF; Gelir Eşleme'de "m³ anahtarına dahil") |
| Motorin anahtarı | Pozlara dağıtılan mazot litresi |
| Patlayıcı | Her ay elle girilen yüzdeler |
| Personel anahtarı | Personel dışı anahtar seçilmiş grupların **adet** × anahtar payı toplamı; Personel grupları hesaba girmez (döngü yok). Dağıtılan tutar toplam maaştır |

Hiçbir tutar sessizce eşit dağıtılmaz. Oranı eksik ekipman, anahtarı seçilmemiş grup ya da hesaplanamayan anahtar
**Dağıtılmamış gider** satırında nedeniyle görünür ve rapor **TASLAK** olarak işaretlenir.

Yeni anahtar (ör. "İş Makinası delici dahil/hariç") **Anahtarlar → Yeni anahtar tanımla** ile şirket, tip ve birincil
filtresiyle eklenir.

## Excel formatı değişirse

Sütunlar başlık adlarıyla bulunur, yerleri önemli değildir. Bir başlık adı değişirse `core/importers.py` içindeki
`PROFILLER` sözlüğüne yeni adı eklemek yeterlidir.

## Geliştirici

```
python -m pytest        # hesap motoru, içe aktarım ve tüm ekranların testleri
```

- `core/engine.py`: saf hesap motoru (veritabanı ve arayüzden bağımsız)
- `core/importers.py`: Excel okuma profilleri
- `core/servis.py`: veritabanı, ilerleme, kontroller, rapor
- `app.py`: Streamlit ekranları
