#!/usr/bin/env python3
"""Yarını planla: takvim + ders takibinden deterministik gün planı üretir.

Hiçbir takvime/ağa dokunmaz; yalnızca girdi dosyalarını okur, plan yazar.
"""
import argparse
import json
import math
import os
import re
import sys
from datetime import date, datetime, timedelta
from fractions import Fraction
from zoneinfo import ZoneInfo

# ───────────── AYARLAR ─────────────
KALKIS = "06:30"                # kalkış saati
HAZIRLIK_DK = 60                # kalkıştan sonra hazırlık süresi (en erken pencere = kalkış + bu)
TERCIH_BITIS = "19:00"          # çalışmanın tercihen bittiği saat
SON_BITIS = "21:00"             # hiç pencere çıkmazsa izin verilen en geç bitiş
PENCERE_EN_AZ_DK = 60           # bir çalışma penceresi en az kaç dakika
PENCERE_EN_COK_DK = 180         # bir çalışma penceresi en çok kaç dakika
GEC_PENCERE_EN_COK_DK = 120     # SON_BITIS'e taşan tek pencere en çok kaç dakika
ARA_DK = 120                    # aynı boşlukta iki pencere arası mola
YOL_EV_OKUL_DK = 50             # ev-okul yol süresi (dersin önü ve arkası)
YOL_EV_GYM_DK = 20              # ev-gym yol süresi (gym'in önü ve arkası)
CALISMA_YERI = "ev"             # çalışma penceresinin konumu
SURE_SLAYT = 45                 # bir slayt okumanın dakikası
SURE_TEST = 30                  # bir testin dakikası
SURE_ANKI = 20                  # günlük Anki dakikası
DOLULUK = 2 / 3                 # çalışma süresinin ne kadarı listeyle doldurulur
EN_COK_MADDE = 9                # listedeki en çok madde (Anki dahil)
TAKIP_DERSLER = ["ANA", "BKY", "HİST", "TBG", "BFZ", "BİST"]  # listeye giren dersler
GYM_SIRA = ["Üst A", "Alt A", "Üst B", "Alt B"]               # gym döngüsü
ISARET = "[evolve-bot]"         # botun kendi etkinliklerine koyduğu işaret
PROGRAM_YOK_BASLIK = "Program girilmemiş - Claude'a 'haftayı gir' yaz"  # program yok notu
BILDIRIM_DUZELT = True          # True: ders/gym bildirimlerini de düzelt
DERS_TAKVIMI = "Ders"           # ders takviminin adı
GYM_TAKVIMI = "Gym"             # gym takviminin adı
# ───────────── AYARLAR SONU ─────────────

DILIM = ZoneInfo("Europe/Istanbul")
SIRALI_DERS = "HİST"  # slaytları n sırasıyla gitmesi gereken ders
YUVARLAMA_DK = 15
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
DERS_KODU = re.compile(r"^[A-ZÇĞİÖŞÜ]{2,6}(:| pratik)")
GYM_BASLIK = re.compile(r"^Gym \((.+)\)$")
BILDIRIM_ALANLARI = {"overrideReminders", "useDefaultReminders"}


class GuvenlikHatasi(Exception):
    """Eylem listesi güvenlik kurallarını çiğniyor."""


class GirdiHatasi(Exception):
    """Girdi dosyası okunamadı/bozuk."""


# ───────────── zaman yardımcıları ─────────────

def saat_coz(metin, gun):
    s, d = metin.split(":")
    return datetime(gun.year, gun.month, gun.day, int(s), int(d))


def gun_basi(gun):
    return datetime(gun.year, gun.month, gun.day)


def zaman_coz(metin):
    """ISO dateTime -> İstanbul saatiyle naive datetime."""
    if metin.endswith(("Z", "z")):
        metin = metin[:-1] + "+00:00"
    dt = datetime.fromisoformat(metin)
    if dt.tzinfo is not None:
        dt = dt.astimezone(DILIM).replace(tzinfo=None)
    return dt


def yukari_yuvarla(dt):
    taban = dt.replace(second=0, microsecond=0)
    if taban < dt:
        taban += timedelta(minutes=1)
    artan = taban.minute % YUVARLAMA_DK
    if artan:
        taban += timedelta(minutes=YUVARLAMA_DK - artan)
    return taban


def asagi_yuvarla(dt):
    taban = dt.replace(second=0, microsecond=0)
    return taban - timedelta(minutes=taban.minute % YUVARLAMA_DK)


def dakika(bas, bit):
    return int((bit - bas).total_seconds() // 60)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


# ───────────── etkinlik okuma / sınıflama ─────────────

def etkinlik_coz(ham):
    """Ham Google etkinliğini iç biçime çevirir; çözülemezse None."""
    try:
        bas_h, bit_h = ham["start"], ham["end"]
        if "dateTime" in bas_h:
            tum_gun = False
            bas, bit = zaman_coz(bas_h["dateTime"]), zaman_coz(bit_h["dateTime"])
        else:
            tum_gun = True
            bas = gun_basi(date.fromisoformat(bas_h["date"]))
            bit = gun_basi(date.fromisoformat(bit_h["date"]))
        kimlik = ham["id"]
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if not kimlik or bit < bas:
        return None
    return {
        "ham": ham,
        "id": kimlik,
        "baslik": str(ham.get("summary") or ""),
        "aciklama": str(ham.get("description") or ""),
        "konum": str(ham.get("location") or ""),
        "takvim_id": ham.get("calendarId"),
        "takvim_adi": ham.get("calendarName"),
        "tum_gun": tum_gun,
        "bas": bas,
        "bit": bit,
    }


def etkinlikleri_coz(hamlar):
    """(çözülen etkinlikler, uyarılar)"""
    sonuc, uyarilar = [], []
    for ham in hamlar:
        if isinstance(ham, dict) and ham.get("status") == "cancelled":
            continue
        e = etkinlik_coz(ham) if isinstance(ham, dict) else None
        if e is None:
            ad = ham.get("summary") if isinstance(ham, dict) else ham
            uyarilar.append(f"Okunamayan etkinlik atlandı: {ad!r}")
        else:
            sonuc.append(e)
    return sonuc, uyarilar


def tur(e):
    """bot-liste / bot-calisma / bot-not / bot-diger / gym / ders / calisma / diger / tumgun"""
    if ISARET in e["aciklama"]:
        for ad in ("liste", "calisma", "not"):
            if f"{ISARET} {ad}" in e["aciklama"]:
                return "bot-" + ad
        return "bot-diger"
    if e["baslik"].lower().startswith("gym") or e["takvim_adi"] == GYM_TAKVIMI:
        return "gym"
    if e["tum_gun"]:
        return "tumgun"
    if e["takvim_adi"] == DERS_TAKVIMI or DERS_KODU.match(e["baslik"]):
        return "ders"
    if e["baslik"].startswith("Çalışma"):
        return "calisma"
    return "diger"


def basladi_mi(e, simdi):
    """Saatli ve başlamış etkinlik: geçmişe dokunulmaz."""
    return not e["tum_gun"] and e["bas"] <= simdi


def gunde_mi(e, gun):
    b, s = gun_basi(gun), gun_basi(gun) + timedelta(days=1)
    return (e["bas"] < s and e["bit"] > b) or (b <= e["bas"] < s)


# ───────────── adım 2: gym ─────────────

def gym_kontrol(tumu, gun_gymleri, gun, simdi):
    """(beklenen başlık düzeltmeleri [(etkinlik, yeni başlık)], özet satırı)"""
    if not gun_gymleri:
        return [], "Gym: o gün gym yok"
    onceki = None
    for e in sorted(tumu, key=lambda x: x["bas"]):
        if tur(e) != "gym" or e["bas"] >= gun_basi(gun) or gunde_mi(e, gun):
            continue
        m = GYM_BASLIK.match(e["baslik"].strip())
        if m and m.group(1) in GYM_SIRA:
            onceki = m.group(1)
    if onceki is None:
        return [], "Gym: önceki geçerli gym bulunamadı, başlığa dokunulmadı"
    sira = GYM_SIRA.index(onceki)
    duzeltmeler, parcalar = [], []
    for e in gun_gymleri:
        sira = (sira + 1) % len(GYM_SIRA)
        beklenen = f"Gym ({GYM_SIRA[sira]})"
        if e["baslik"] == beklenen:
            parcalar.append(f"{beklenen} doğru")
        elif basladi_mi(e, simdi):
            parcalar.append(f"'{e['baslik']}' başlamış, dokunulmadı (beklenen {beklenen})")
        else:
            duzeltmeler.append((e, beklenen))
            parcalar.append(f"'{e['baslik']}' → '{beklenen}' düzeltilecek")
    return duzeltmeler, f"Gym: önceki {onceki}; " + "; ".join(parcalar)


# ───────────── adım 3: pencereler ─────────────

def mesgul_araliklar(gun_etkinlikleri):
    araliklar = []
    for e in gun_etkinlikleri:
        t = tur(e)
        if e["tum_gun"] or t.startswith("bot"):
            continue
        pay = {"ders": YOL_EV_OKUL_DK, "gym": YOL_EV_GYM_DK}.get(t, 0)
        araliklar.append((e["bas"] - timedelta(minutes=pay), e["bit"] + timedelta(minutes=pay)))
    return araliklar


def bos_araliklar(bas, bit, mesgul):
    bos, imlec = [], bas
    for mb, ms in sorted(mesgul):
        if ms <= imlec:
            continue
        if mb >= bit:
            break
        if mb > imlec:
            bos.append((imlec, mb))
        imlec = max(imlec, ms)
    if imlec < bit:
        bos.append((imlec, bit))
    return bos


def pencere_adaylari(bos, en_cok_dk):
    adaylar = []
    en_az, en_cok = timedelta(minutes=PENCERE_EN_AZ_DK), timedelta(minutes=en_cok_dk)
    for b, s in bos:
        b, s = yukari_yuvarla(b), asagi_yuvarla(s)
        if s - b < en_az:
            continue
        ilk = (b, min(s, b + en_cok))
        adaylar.append(ilk)
        b2 = ilk[1] + timedelta(minutes=ARA_DK)
        if s - b2 >= en_az:
            adaylar.append((b2, min(s, b2 + en_cok)))
    return adaylar


def en_uzunlar(adaylar, adet):
    secilen = sorted(adaylar, key=lambda p: (-(p[1] - p[0]), p[0]))[:adet]
    return sorted(secilen)


def pencereleri_hesapla(gun_etkinlikleri, gun, simdi, donmus=()):
    mesgul = mesgul_araliklar(gun_etkinlikleri) + [(e["bas"], e["bit"]) for e in donmus]
    bas = saat_coz(KALKIS, gun) + timedelta(minutes=HAZIRLIK_DK)
    adaylar = pencere_adaylari(bos_araliklar(bas, saat_coz(TERCIH_BITIS, gun), mesgul),
                               PENCERE_EN_COK_DK)
    kalan_hak = max(0, 2 - len(donmus))  # donmuş pencereler günün 2 hakkından düşer
    if adaylar:
        secilen = en_uzunlar(adaylar, kalan_hak)
    elif donmus:
        secilen = []  # günün penceresi zaten var; geç saate taşma
    else:
        adaylar = pencere_adaylari(bos_araliklar(bas, saat_coz(SON_BITIS, gun), mesgul),
                                   GEC_PENCERE_EN_COK_DK)
        secilen = en_uzunlar(adaylar, 1)
    return [p for p in secilen if p[0] > simdi]


# ───────────── adım 4: liste ─────────────

def liste_kur(dersler, durum, hafta, gun, toplam_dk):
    """(başlıklar, bütçe). dersler: dersler.json 'list', durum: durum.json 's'."""
    oran = Fraction(DOLULUK).limit_denominator(1000)
    butce = math.floor(toplam_dk * oran) - SURE_ANKI
    dun = gun - timedelta(days=1)

    kapsam = []  # (sıra, tarih, ders)
    for i, d in enumerate(dersler):
        try:
            t = date.fromisoformat(d["d"])
        except (KeyError, TypeError, ValueError):
            continue
        if d.get("c") in TAKIP_DERSLER and t <= gun and "id" in d:
            kapsam.append((i, t, d))

    def hal(d):
        k = durum.get(d["id"]) or {}
        return "bitti" if k.get("t") else ("test" if k.get("r") else "okunmadi")

    sirala = lambda grup: [d for _, _, d in sorted(grup, key=lambda x: (x[1], x[0]))]
    okunmamis = [x for x in kapsam if hal(x[2]) == "okunmadi"]
    a = sirala([x for x in kapsam if hal(x[2]) == "test"])
    b1 = sirala([x for x in okunmamis if x[1] == dun])
    b2 = sirala([x for x in okunmamis if x[1] == gun])
    pazartesi = gun - timedelta(days=gun.weekday())
    if hafta and hafta.get("hafta") == pazartesi.isoformat():
        havuz = {h[:-2] for h in hafta.get("havuz") or [] if isinstance(h, str) and h.endswith(":r")}
        # dün/bugün dersleri zaten b1/b2 adayı; tekrar eklenmez
        c = sirala([x for x in okunmamis if x[2]["id"] in havuz and x[1] < dun])
    else:
        c = sirala([x for x in okunmamis if x[1] < dun])
    sirali_okunmamis = [d for _, _, d in sorted(
        (x for x in okunmamis if x[2]["c"] == SIRALI_DERS), key=lambda x: (x[2].get("n", 0), x[0]))]

    gruplar = {"a": a, "b1": b1, "b2": b2, "c": c}
    secilen = {k: [] for k in gruplar}
    kullanilan = set()
    kalan = butce
    sinir = EN_COK_MADDE - 1  # Anki hariç

    def coz(ad, d):
        """Adayı gerçek derse çevirir (HİST sırası); yoksa None."""
        if ad != "a" and d["c"] == SIRALI_DERS:
            d = next((h for h in sirali_okunmamis if h["id"] not in kullanilan), None)
        if d is None or (ad != "a" and d["id"] in kullanilan):
            return None
        return d

    def ekle(ad, d):
        secilen[ad].append(d)
        if ad != "a":
            kullanilan.add(d["id"])

    def adet():
        return sum(len(v) for v in secilen.values())

    def doldur(adlar):
        nonlocal kalan
        for ad in adlar:
            sure = SURE_TEST if ad == "a" else SURE_SLAYT
            for aday in gruplar[ad]:
                if adet() >= sinir:
                    return
                d = coz(ad, aday)
                if d is None:
                    continue
                if sure > kalan:
                    return  # sığmayan ilk maddede dur
                ekle(ad, d)
                kalan -= sure

    doldur(["b1"])            # dünün slaytları bütçeyi önce alır
    doldur(["a", "b2", "c"])
    if adet() == 0 and sinir > 0:  # hiçbir şey sığmadıysa yine de bir madde
        for ad in ("a", "b1", "b2", "c"):
            d = next((x for x in (coz(ad, y) for y in gruplar[ad]) if x), None)
            if d is not None:
                ekle(ad, d)
                break

    basliklar = ["1) Anki"]
    for ad in ("a", "b1", "b2", "c"):
        for d in secilen[ad]:
            ek = "test" if ad == "a" else "slayt"
            basliklar.append(f"{len(basliklar) + 1}) {d['c']} {d.get('n', '?')} {ek}")
    return basliklar, butce


# ───────────── adım 5: fark → eylemler ─────────────

def hedef(e):
    p = {"eventId": e["id"]}
    if e["takvim_id"]:
        p["calendarId"] = e["takvim_id"]
    return p


def guncelle(e, **alanlar):
    return {"arac": "update_event", "parametreler": {**hedef(e), **alanlar}}


def sil(e):
    return {"arac": "delete_event", "parametreler": hedef(e)}


def tum_gun_olustur(baslik, gun, aciklama):
    return {"arac": "create_event", "parametreler": {
        "summary": baslik,
        "startTime": iso(gun_basi(gun)),
        "endTime": iso(gun_basi(gun) + timedelta(days=1)),
        "allDay": True,
        "description": aciklama,
        "availability": "AVAILABILITY_FREE",
        "useDefaultReminders": False,
    }}


def pencere_olustur(bas, bit):
    return {"arac": "create_event", "parametreler": {
        "summary": "Çalışma",
        "startTime": iso(bas),
        "endTime": iso(bit),
        "location": CALISMA_YERI,
        "description": f"{ISARET} calisma",
        "overrideReminders": [{"method": "popup", "minutes": 0}],
    }}


def bas_numara(e):
    m = re.match(r"\s*(\d+)", e["baslik"])
    return (0, int(m.group(1))) if m else (1, 0)


def baslik_farki(mevcut, istenen, gun, aciklama):
    """Tüm gün bot etkinlikleri (liste/not) için sırayla eşleştirme."""
    eylemler = []
    for i in range(max(len(mevcut), len(istenen))):
        if i >= len(mevcut):
            eylemler.append(tum_gun_olustur(istenen[i], gun, aciklama))
        elif i >= len(istenen):
            eylemler.append(sil(mevcut[i]))
        elif mevcut[i]["baslik"] != istenen[i]:
            eylemler.append(guncelle(mevcut[i], summary=istenen[i]))
    return eylemler


def pencere_farki(mevcut, istenen):
    eylemler = []
    for i in range(max(len(mevcut), len(istenen))):
        if i >= len(mevcut):
            eylemler.append(pencere_olustur(*istenen[i]))
        elif i >= len(istenen):
            eylemler.append(sil(mevcut[i]))
        else:
            e, (bas, bit) = mevcut[i], istenen[i]
            degisen = {}
            if e["tum_gun"] or e["bas"] != bas or e["bit"] != bit:
                degisen.update(startTime=iso(bas), endTime=iso(bit))  # saatler hep birlikte
            if e["konum"] != CALISMA_YERI:
                degisen["location"] = CALISMA_YERI
            if degisen:
                eylemler.append(guncelle(e, **degisen))
    return eylemler


def mevcut_bildirim(ham):
    """(varsayılan mı, [(yöntem, dakika)])"""
    r = ham.get("reminders") if isinstance(ham.get("reminders"), dict) else {}
    varsayilan = ham.get("useDefaultReminders", r.get("useDefault", True))
    ozel = ham.get("overrideReminders", r.get("overrides")) or []
    return bool(varsayilan), sorted((o.get("method"), o.get("minutes")) for o in ozel)


def bildirim_eylemleri(dersler, gymler, simdi):
    eylemler = []
    istekler = [(e, YOL_EV_OKUL_DK if i == 0 else None) for i, e in enumerate(dersler)]
    istekler += [(e, YOL_EV_GYM_DK) for e in gymler]
    for e, dk in istekler:
        if basladi_mi(e, simdi):
            continue
        varsayilan, ozel = mevcut_bildirim(e["ham"])
        if dk is not None:
            if ozel != [("popup", dk)]:
                eylemler.append(guncelle(e, overrideReminders=[{"method": "popup", "minutes": dk}]))
        elif varsayilan or ozel:
            alanlar = {"useDefaultReminders": False}
            if ozel:
                alanlar["overrideReminders"] = []
            eylemler.append(guncelle(e, **alanlar))
    return eylemler


# ───────────── güvenlik ─────────────

def guvenlik_denetimi(eylemler, etkinlikler, gun, simdi):
    """Son eylem listesini denetler; ihlalde GuvenlikHatasi fırlatır.

    etkinlikler: ham (Google biçimi) ya da çözülmüş etkinlik listesi.
    """
    if gun < simdi.date():
        raise GuvenlikHatasi(f"Hedef gün geçmişte: {gun}")
    cozulmus = [e if "ham" in e else etkinlik_coz(e) for e in etkinlikler]
    kimlikler = {}
    for e in cozulmus:
        if e is not None:
            kimlikler.setdefault(e["id"], []).append(e)
    b, s = gun_basi(gun), gun_basi(gun) + timedelta(days=1)
    for ey in eylemler:
        arac, p = ey.get("arac"), ey.get("parametreler") or {}
        if arac == "create_event":
            try:
                bas, bit = datetime.fromisoformat(p["startTime"]), datetime.fromisoformat(p["endTime"])
            except (KeyError, ValueError, TypeError):
                raise GuvenlikHatasi(f"Oluşturma eyleminde saat yok/bozuk: {p}")
            if not (b <= bas < s and bas <= bit <= s):
                raise GuvenlikHatasi(f"Oluşturma hedef gün dışında: {p.get('summary')!r}")
            if ISARET not in str(p.get("description") or ""):
                raise GuvenlikHatasi(f"Oluşturulan etkinlikte işaret yok: {p.get('summary')!r}")
            continue
        if arac not in ("update_event", "delete_event"):
            raise GuvenlikHatasi(f"Bilinmeyen araç: {arac!r}")
        adaylar = kimlikler.get(p.get("eventId"), [])
        if len(adaylar) != 1:
            raise GuvenlikHatasi(f"Hedef etkinlik bulunamadı ya da belirsiz: {p.get('eventId')!r}")
        e = adaylar[0]
        if not gunde_mi(e, gun):
            raise GuvenlikHatasi(f"Hedef etkinlik hedef günde değil: {e['baslik']!r}")
        if basladi_mi(e, simdi):
            raise GuvenlikHatasi(f"Başlamış etkinliğe dokunulamaz: {e['baslik']!r}")
        t = tur(e)
        if t.startswith("bot"):
            continue
        if arac == "delete_event":
            raise GuvenlikHatasi(f"Bot olmayan etkinlik silinemez: {e['baslik']!r}")
        alanlar = set(p) - {"eventId", "calendarId"}
        if t == "gym" and alanlar == {"summary"}:
            continue
        if BILDIRIM_DUZELT and t in ("gym", "ders") and alanlar and alanlar <= BILDIRIM_ALANLARI:
            continue
        raise GuvenlikHatasi(f"İzinsiz güncelleme: {e['baslik']!r} alanlar={sorted(alanlar)}")


# ───────────── ana planlama ─────────────

def eylem_satiri(ey, kimlikten):
    p = ey["parametreler"]
    if ey["arac"] == "create_event":
        if p.get("allDay"):
            return f"+ oluştur: \"{p['summary']}\" (tüm gün)"
        return f"+ oluştur: \"{p['summary']}\" {p['startTime'][11:16]}–{p['endTime'][11:16]}"
    eski = kimlikten.get(p["eventId"])
    ad = eski["baslik"] if eski else p["eventId"]
    if ey["arac"] == "delete_event":
        return f"- sil: \"{ad}\""
    parcalar = []
    for k, v in p.items():
        if k in ("eventId", "calendarId"):
            continue
        if k in ("startTime", "endTime"):
            v = v[11:16]
        parcalar.append(f"{k}={json.dumps(v, ensure_ascii=False)}")
    return f"~ güncelle: \"{ad}\" → " + ", ".join(parcalar)


def planla(ham_etkinlikler, dersler, durum, hafta, gun, simdi):
    """Plan sözlüğü döndürür: tarih, liste, pencereler, eylemler (+ 'ozet' satırları)."""
    if gun < simdi.date():
        raise ValueError(f"Hedef gün ({gun}) bugünden ({simdi.date()}) önce olamaz")
    etkinlikler, uyarilar = etkinlikleri_coz(ham_etkinlikler)
    bugun = sorted((e for e in etkinlikler if gunde_mi(e, gun)), key=lambda e: e["bas"])
    turler = {}
    for e in bugun:
        turler.setdefault(tur(e), []).append(e)
    bot_liste = sorted(turler.get("bot-liste", []), key=bas_numara)
    donmus = [e for e in turler.get("bot-calisma", []) if basladi_mi(e, simdi)]  # geçmişe dokunma
    bot_pencere = [e for e in turler.get("bot-calisma", []) if not basladi_mi(e, simdi)]
    bot_not = turler.get("bot-not", [])
    gymler = turler.get("gym", [])
    ders_etk = turler.get("ders", [])
    kullanici_pencere = turler.get("calisma", [])

    eylemler, ozet = [], [f"Plan: {gun.isoformat()} ({GUNLER[gun.weekday()]})"]
    ozet += ["Uyarı: " + u for u in uyarilar]
    liste, pencereler, butce = [], [], None

    if gun.weekday() < 5 and not ders_etk:
        # Adım 1: program girilmemiş
        ozet.append("Hafta içi ama ders yok: program girilmemiş notu, liste/pencere yok")
        ozet.append("Gym: kontrol edilmedi (program girilmemiş)")
        eylemler += [sil(e) for e in bot_liste + bot_pencere]
        eylemler += baslik_farki(bot_not, [PROGRAM_YOK_BASLIK], gun, f"{ISARET} not")
    else:
        eylemler += baslik_farki(bot_not, [], gun, f"{ISARET} not")
        duzeltmeler, gym_satiri = gym_kontrol(etkinlikler, gymler, gun, simdi)
        gym_eylemleri = [guncelle(e, summary=yeni) for e, yeni in duzeltmeler]

        b, s = gun_basi(gun), gun_basi(gun) + timedelta(days=1)
        if kullanici_pencere:
            pencereler = [(max(e["bas"], b), min(e["bit"], s)) for e in kullanici_pencere]
            istenen_pencere = []
            kaynak = "senin koyduğun"
        else:
            istenen_pencere = pencereleri_hesapla(bugun, gun, simdi, donmus)
            pencereler = sorted([(max(e["bas"], b), min(e["bit"], s)) for e in donmus]
                                + istenen_pencere)
            kaynak = "bot"
        toplam = sum(dakika(x, y) for x, y in pencereler)
        liste, butce = liste_kur(dersler, durum, hafta, gun, toplam)

        ozet.append("Liste:")
        ozet += ["  " + m for m in liste]
        ozet.append(f"Pencereler ({kaynak}; toplam {toplam} dk, bütçe {butce} dk):")
        ozet += [f"  {x:%H:%M}–{y:%H:%M} ({dakika(x, y)} dk)" for x, y in pencereler] or ["  (yok)"]
        ozet.append(gym_satiri)

        eylemler += gym_eylemleri
        eylemler += pencere_farki(bot_pencere, istenen_pencere)
        eylemler += baslik_farki(bot_liste, liste, gun, f"{ISARET} liste")

    if BILDIRIM_DUZELT:
        eylemler += bildirim_eylemleri(ders_etk, gymler, simdi)

    guvenlik_denetimi(eylemler, etkinlikler, gun, simdi)

    kimlikten = {e["id"]: e for e in bugun}
    if eylemler:
        ozet.append(f"Eylemler ({len(eylemler)}):")
        ozet += ["  " + eylem_satiri(ey, kimlikten) for ey in eylemler]
    else:
        ozet.append("Değişiklik yok")
    return {
        "tarih": gun.isoformat(),
        "liste": liste,
        "pencereler": [{"baslangic": iso(x), "bitis": iso(y), "dk": dakika(x, y)}
                       for x, y in pencereler],
        "eylemler": eylemler,
        "ozet": ozet,
    }


# ───────────── komut satırı ─────────────

def json_oku(yol, zorunlu=True):
    if not os.path.exists(yol):
        if zorunlu:
            raise GirdiHatasi(f"Dosya yok: {yol}")
        return None
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as h:
        raise GirdiHatasi(f"Dosya okunamadı: {yol} ({h})")


def hedef_gun(tarih, simdi):
    if tarih:
        return date.fromisoformat(tarih)
    if simdi.hour < 4:  # gece yarısından sonra geç çalıştırma
        return simdi.date()
    return simdi.date() + timedelta(days=1)


def ana(argv=None):
    ap = argparse.ArgumentParser(description="Yarının planını üretir (takvime dokunmaz).")
    ap.add_argument("--etkinlikler", required=True, help="takvim etkinlikleri JSON dosyası")
    ap.add_argument("--db", required=True, help="takip klasörünü içeren dizin")
    ap.add_argument("--tarih", help="hedef gün YYYY-MM-DD (varsayılan: yarın)")
    ap.add_argument("--simdi", help="şimdiki zaman YYYY-MM-DDTHH:MM (varsayılan: İstanbul saati)")
    ap.add_argument("--cikti", help="plan JSON dosyası (verilmezse yazılmaz)")
    a = ap.parse_args(argv)
    try:
        simdi = zaman_coz(a.simdi) if a.simdi else datetime.now(DILIM).replace(tzinfo=None)
        gun = hedef_gun(a.tarih, simdi)
    except ValueError as h:
        print(f"Hata: tarih/saat anlaşılamadı ({h})", file=sys.stderr)
        return 2
    if gun < simdi.date():
        print(f"Reddedildi: hedef gün ({gun}) bugünden ({simdi.date()}) önce.", file=sys.stderr)
        return 2
    try:
        etk = json_oku(a.etkinlikler)
        takip = os.path.join(a.db, "takip")
        dersler = json_oku(os.path.join(takip, "dersler.json"))
        durum = json_oku(os.path.join(takip, "durum.json"))
        hafta = json_oku(os.path.join(takip, "hafta.json"), zorunlu=False)
        olaylar, ders_listesi, durumlar = etk["events"], dersler["list"], durum.get("s") or {}
        if not (isinstance(olaylar, list) and isinstance(ders_listesi, list)
                and isinstance(durumlar, dict) and isinstance(hafta, (dict, type(None)))):
            raise GirdiHatasi("beklenmeyen JSON yapısı")
    except (GirdiHatasi, KeyError, TypeError, AttributeError) as h:
        print(f"Hata: girdi okunamadı ({h!r})", file=sys.stderr)
        return 1
    try:
        plan = planla(olaylar, ders_listesi, durumlar, hafta, gun, simdi)
    except GuvenlikHatasi as h:
        print(f"Güvenlik hatası, plan üretilmedi: {h}", file=sys.stderr)
        return 3
    print("\n".join(plan.pop("ozet")))
    if a.cikti:
        with open(a.cikti, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"Plan yazıldı: {a.cikti}")
    return 0


if __name__ == "__main__":
    sys.exit(ana())
