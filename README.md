# Evolve akşam asistanı

Tek işi var: her akşam 20:50'de yarını hazırlamak.

- Yarının sıralı ders listesini kurallara göre kurar ve takvime, günün en üstüne tüm gün süren maddeler olarak yazar ("1) Anki", "2) ANA 1 test" ...).
- Yarın için "Çalışma" zamanı yoksa boş aralıklara 1-2 tane ekler.
- Yarın gym varsa hangi antrenman olduğunu doğrular, adı yanlışsa düzeltir.
- Hafta içi bir gün için ders girilmemişse liste yerine tek bir uyarı notu koyar.

## Dosyalar

- `planla.py` — kararları veren program. En üstündeki AYARLAR bölümünde kalkış saati, süreler, çalışma yeri gibi sabitler durur.
- `GOREV.md` — akşam açılan Claude oturumunun izlediği adımlar.
- `KARARLAR.md` — kurarken verilen kararlar.
- `test_planla.py`, `test_verisi/` — programın doğru çalıştığını sınayan denemeler.

## Elle deneme (takvime yazmaz)

    python3 planla.py --etkinlikler test_verisi/etkinlikler.json --db test_verisi --tarih 2026-11-13 --simdi 2026-11-12T20:50

Aracın takvime yazdığı her etkinliğin açıklamasında `[evolve-bot]` yazar; araç yalnızca bunları değiştirir ya da siler.
