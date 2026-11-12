# Kararlar

Kararsız kalınan yerlerde seçilenler, her biri tek satır.

1. Altyapı: Sıfırdan sistem kurulmadı; Claude'un zamanlanmış görevi + Google Calendar bağlayıcısı + Kurul 2 Takip veritabanı kullanılıyor.
2. İş bölümü: Liste ve saat kararlarını her seferinde aynı sonucu veren `planla.py` verir; akşam açılan Claude oturumu yalnızca okur, programı çalıştırır ve çıkan eylemleri uygular (adımlar `GOREV.md`'de).
3. "Slayt en geç ertesi gün listeye girer" kuralı: Dünün dersinin slaytı bütçeden yerini testlerden ÖNCE ayırır, ama listede testlerden sonra görünür.
4. Bütçe (çalışma süresinin 2/3'ü) üst sınırdır; tek istisna "en az bir ders maddesi".
5. Anki'nin 20 dakikası bütçeden düşülür (az koymak için).
6. Sığmayan ilk maddede liste kesilir, daha küçük madde aranmaz (kararsızsan az koy).
7. HİST sırası: Listeye bir HİST slaytı girecekse, hangi dersin sırası gelmiş olursa olsun okunmamış en küçük numaralı HİST girer.
8. Testi çözülmüş ders, slayt tarihi boş olsa bile bitmiş sayılır (örn. HİST 3).
9. "En eski" = dersin işlendiği tarihe göre en eski.
10. Haftalık havuz (takip/hafta) yalnızca o haftanın pazartesi tarihini taşıyorsa kullanılır; yoksa ya da eskiyse en eski okunmamışlara bakılır.
11. Liste en fazla 9 madde (takvim 10'u 2'den önce sıraladığı için).
12. Çalışma penceresi: en az 60 dk, en çok 3 saat, günde en çok 2; 15 dakikaya yuvarlanır; tercihen 19:00'da biter (akşam serbest), hiç yer yoksa 21:00'e kadar tek pencere (en çok 2 saat).
13. Derssiz günde iki pencere arasında 2 saat ara: 07:30–10:30 ve 12:30–15:30.
14. Çalışma yeri her zaman "ev" yazılır (dershane evden 10 dk; yer `planla.py`'deki ayardan değişir).
15. Takvimde benim eklediğim bir "Çalışma" varsa araç pencere eklemez, kendi eklediklerini kaldırır.
16. Gym: Takvimdeki geçmiş gym etkinlikleri yapılmış sayılır; kaçırdığın antrenmanın etkinliğini silersen sıra kendiliğinden kayar.
17. Gym'de araç yalnızca başlığı düzeltir; saatine, süresine dokunmaz. Geçmişte hiç gym yoksa dokunmaz.
18. Hafta içi derssiz gün (resmi tatil dahil) "Program girilmemiş" notu alır; hafta sonu derssiz günde liste ve çalışma zamanı yazılır.
19. Bildirimler: Araç yalnızca kendi "Çalışma" etkinliğine (başlangıçta) bildirim koyar. Ders ve gym bildirimlerine dokunmaz, çünkü "derslere dokunma" kuralı pazarlıksız. İstenirse `BILDIRIM_DUZELT` ayarı açılır (ilk ders 50 dk, gym 20 dk, diğer dersler bildirimsiz).
20. Takvimdeki "Okula gidiş" / "Dönüş" / "Yarını planla" etkinlikleri senin; araç onlara dokunmaz, yalnızca dolu zaman sayar.
21. Bugün neyi bitirdiğini araç yalnızca Kurul 2 Takip'ten bilir; orada işaretlenmeyen madde ertesi gün yeniden listeye girebilir.
22. Görev gece yarısından sonraya kalırsa (04:00'e kadar) "yarın" yerine o günü hazırlar.
23. Bildirim/e-posta ile sonuç gönderilmez; sonuç yalnızca takvimde görünür.
