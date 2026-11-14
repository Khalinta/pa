# Akşam görevi: yarını hazırla

Bu dosya, her akşam 20:50'de (Europe/Istanbul) kendiliğinden açılan Claude oturumunun izleyeceği adımlardır.
Kimseye soru sorma, onay bekleme. Bir adım başarısız olursa takvime HİÇBİR ŞEY yazma, nedenini tek cümleyle bildir ve dur.

## Pazarlıksız kurallar

- Yalnızca `planla.py`'nin ürettiği eylemleri, verdiği parametrelerle AYNEN uygula. Kendi kafandan etkinlik ekleme, silme, değiştirme.
- Geçmişteki etkinliklere dokunma. Açıklamasında `[evolve-bot]` olmayan etkinliklere dokunma (tek istisna: planla.py'nin istediği Gym başlık düzeltmesi).
- Anki'ye, e-postaya, Evolve / Ders / Gym dışındaki takvimlere dokunma. AWorld sayfasına ASLA yazma, yalnızca oku.
- Liste kurallarını kendin yorumlama; karar planla.py'nindir.

## Adımlar

1. **Tarih.** `TZ=Europe/Istanbul date +%Y-%m-%dT%H:%M` çalıştır. Hedef gün T = yarın (saat 04:00'ten önceyse bugün).

2. **Takvimler.** `list_calendars` çağır. "Evolve" birincil takvimdir. Adı tam olarak "Ders" ya da "Gym" olan takvim varsa onları da kullan; başka takvimlere bakma.

3. **Etkinlikleri oku** (Google Calendar bağlayıcısı, `list_events`, `orderBy: startTime`, `pageSize: 250`; sayfa varsa hepsini al). Kullandığın her takvim için:
   - T günü: `startTime` = T 00:00:00, `endTime` = T+1 00:00:00.
   - Gym geçmişi: `fullText: "Gym"`, `startTime` = T−30 gün, `endTime` = T 00:00:00.

   Hepsini tek dosyaya yaz: `/tmp/evolve/etkinlikler.json`, biçim `{"events": [...]}`. Her etkinlik için yalnızca şu alanları, değerleri DEĞİŞTİRMEDEN kopyala: `id`, `summary`, `description`, `location`, `start`, `end`, `useDefaultReminders`, `overrideReminders`. Evolve dışındaki takvimden gelen etkinliğe `calendarId` ve `calendarName` ("Ders" / "Gym") ekle. Hiçbir etkinliği atlama (T günündeki tüm gün süren etkinlikler dahil).

4. **Ders takibini oku** (yalnızca OKU; AWorld'e hiçbir şey yazma, silme, değiştirme). Ders takibi "AWorld" sayfasında: `https://claude.ai/artifact/6VrgWKhxAviKSLqUStArwN`.
   - Önce `rm -rf /tmp/evolve/aworld /tmp/evolve/db` çalıştır (eski veri kalmasın).
   - `ArtifactData`, `action: list`, `out_dir: /tmp/evolve/aworld`, `query: {"limit": 1000}` ile üç koleksiyonu ayrı ayrı oku: `lectures`, `questions`, `progress`. Sonuçta `next_cursor` varsa aynı koleksiyonu o imleçle okumaya devam et, bitene kadar.
   - Çevir: `python3 aworld_cevir.py --aworld /tmp/evolve/aworld --cikti /tmp/evolve/db`
   - Okuma ya da çevirme hata verirse dur (takvime hiçbir şey yazma).

5. **Planla.**
   `python3 planla.py --etkinlikler /tmp/evolve/etkinlikler.json --db /tmp/evolve/db --cikti /tmp/evolve/plan.json`
   Hata verirse dur.

6. **Uygula.** `plan.json` içindeki `eylemler` dizisini sırayla uygula: `arac` alanı bağlayıcı aracının adı (`create_event` / `update_event` / `delete_event`), `parametreler` aynen gönderilecek değerlerdir. Dizi boşsa hiçbir şey yapma.

7. **Doğrula.** 3. adımı T günü için yeniden yap, 5. adımı yeniden çalıştır. Çıktıda `Değişiklik yok` yazmalı. Yazmıyorsa çıkan eylemleri bir kez daha uygula ve yeniden doğrula; hâlâ olmuyorsa dur ve bildir.

8. **Bitir.** En fazla 5 satır Türkçe özet: yarının listesi, çalışma zamanları, gym. Başka bir şey yazma.
