"""planla.py testleri: python3 -m unittest -v"""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime

sys.dont_write_bytecode = True
import planla as P  # noqa: E402

KOK = os.path.dirname(os.path.abspath(__file__))
VERI = os.path.join(KOK, "test_verisi")
ETKINLIK_DOSYASI = os.path.join(VERI, "etkinlikler.json")


def oku(yol):
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


def uygula(etkinlikler, eylemler):
    """Eylemleri bellekteki takvim kopyasına uygular (sahte bağlayıcı)."""
    sonuc = copy.deepcopy(etkinlikler)
    kimlikten = {e["id"]: e for e in sonuc}
    for i, ey in enumerate(eylemler):
        p = ey["parametreler"]
        if ey["arac"] == "create_event":
            yeni = {"id": f"yeni_{len(sonuc)}_{i}"}
            if p.get("allDay"):
                yeni["start"] = {"date": p["startTime"][:10]}
                yeni["end"] = {"date": p["endTime"][:10]}
            else:
                yeni["start"] = {"dateTime": p["startTime"] + "+03:00"}
                yeni["end"] = {"dateTime": p["endTime"] + "+03:00"}
            for k in ("summary", "description", "location", "overrideReminders",
                      "useDefaultReminders"):
                if k in p:
                    yeni[k] = p[k]
            sonuc.append(yeni)
            kimlikten[yeni["id"]] = yeni
        elif ey["arac"] == "update_event":
            e = kimlikten[p["eventId"]]
            for k, v in p.items():
                if k == "startTime":
                    e["start"] = {"dateTime": v + "+03:00"}
                elif k == "endTime":
                    e["end"] = {"dateTime": v + "+03:00"}
                elif k not in ("eventId", "calendarId"):
                    e[k] = v
        elif ey["arac"] == "delete_event":
            sonuc.remove(kimlikten.pop(p["eventId"]))
        else:
            raise AssertionError(ey)
    return sonuc


def bot_mu(e):
    return P.ISARET in (e.get("description") or "")


def gym_mi(e):
    return (e.get("summary") or "").lower().startswith("gym") or e.get("calendarName") == P.GYM_TAKVIMI


class Temel(unittest.TestCase):
    def setUp(self):
        self.etkinlikler = oku(ETKINLIK_DOSYASI)["events"]
        self.dersler = oku(os.path.join(VERI, "takip", "dersler.json"))["list"]
        self.durum = oku(os.path.join(VERI, "takip", "durum.json"))["s"]

    def calistir(self, tarih, simdi, etkinlikler=None, durum=None, hafta=None):
        """planla'yı çağırır; her senaryoda hedeflerin güvenli olduğunu da doğrular."""
        etk = self.etkinlikler if etkinlikler is None else etkinlikler
        girdi_kopya = copy.deepcopy(etk)
        plan = P.planla(etk, self.dersler, self.durum if durum is None else durum, hafta,
                        date.fromisoformat(tarih), datetime.fromisoformat(simdi))
        self.assertEqual(etk, girdi_kopya, "girdi değiştirilmemeli")
        kimlikten = {e["id"]: e for e in etk}
        for ey in plan["eylemler"]:
            p = ey["parametreler"]
            if ey["arac"] == "create_event":
                self.assertIn(P.ISARET, p["description"])
                self.assertEqual(p["startTime"][:10], tarih)
                continue
            e = kimlikten[p["eventId"]]
            if P.BILDIRIM_DUZELT and not bot_mu(e) and not (gym_mi(e) and "summary" in p):
                # yalnız bildirim alanları değişebilir
                self.assertLessEqual(set(p) - {"eventId", "calendarId"},
                                     {"overrideReminders", "useDefaultReminders"})
            else:
                self.assertTrue(bot_mu(e) or gym_mi(e), f"bot/gym olmayan hedef: {e['summary']}")
                if not bot_mu(e):
                    self.assertEqual(set(p) - {"eventId", "calendarId"}, {"summary"})
            if ey["arac"] == "delete_event":
                self.assertTrue(bot_mu(e), f"bot olmayan silme: {e['summary']}")
            gun = (e["start"].get("dateTime") or e["start"].get("date"))[:10]
            self.assertEqual(gun, tarih)
        return plan

    def araclar(self, plan):
        return [ey["arac"] for ey in plan["eylemler"]]

    def saatler(self, plan):
        return [(p["baslangic"][11:16], p["bitis"][11:16]) for p in plan["pencereler"]]


class BeklenenSonuclar(Temel):
    def test_cuma_13(self):
        plan = self.calistir("2026-11-13", "2026-11-12T20:50")
        self.assertEqual(plan["liste"], ["1 Anki", "2 ANA 1 test", "3 ANA 7 slayt", "4 HİST 1 slayt"])
        self.assertEqual(self.saatler(plan), [("07:30", "08:30"), ("15:15", "18:15")])
        self.assertEqual(sum(p["dk"] for p in plan["pencereler"]), 240)
        self.assertEqual(self.araclar(plan), ["create_event"] * 6)
        self.assertTrue(any("bütçe 140" in s for s in plan["ozet"]))
        self.assertTrue(any(s.startswith("Gym:") and "doğru" in s for s in plan["ozet"]))

    def test_cuma_13_eylem_bicimi(self):
        plan = self.calistir("2026-11-13", "2026-11-12T20:50")
        par = [ey["parametreler"] for ey in plan["eylemler"]]
        self.assertIn({"summary": "1 Anki", "startTime": "2026-11-13T00:00:00",
                       "endTime": "2026-11-14T00:00:00", "allDay": True,
                       "description": "[evolve-bot] liste",
                       "availability": "AVAILABILITY_FREE", "useDefaultReminders": False}, par)
        self.assertIn({"summary": "Çalışma", "startTime": "2026-11-13T15:15:00",
                       "endTime": "2026-11-13T18:15:00", "location": "ev",
                       "description": "[evolve-bot] calisma",
                       "overrideReminders": [{"method": "popup", "minutes": 0}]}, par)

    def test_cumartesi_14(self):
        plan = self.calistir("2026-11-14", "2026-11-13T20:50")
        self.assertEqual(plan["liste"], ["1 Anki", "2 ANA 1 test", "3 ANA 2 test", "4 ANA 3 test",
                                         "5 ANA 4 test", "6 ANA 5 test", "7 BFZ 1 slayt"])
        self.assertEqual(self.saatler(plan), [("07:30", "10:30"), ("12:30", "15:30")])
        self.assertTrue(any("bütçe 220" in s for s in plan["ozet"]))

    def test_pazartesi_16_program_yok(self):
        plan = self.calistir("2026-11-16", "2026-11-15T20:50")
        self.assertEqual(len(plan["eylemler"]), 1)
        p = plan["eylemler"][0]["parametreler"]
        self.assertEqual(plan["eylemler"][0]["arac"], "create_event")
        self.assertEqual(p["summary"], P.PROGRAM_YOK_BASLIK)
        self.assertEqual(p["description"], "[evolve-bot] not")
        self.assertTrue(p["allDay"])
        self.assertEqual(plan["liste"], [])
        self.assertEqual(plan["pencereler"], [])


class Idempotentlik(Temel):
    def test_ikinci_calistirma_bos(self):
        for tarih, simdi in [("2026-11-13", "2026-11-12T20:50"), ("2026-11-14", "2026-11-13T20:50"),
                             ("2026-11-16", "2026-11-15T20:50")]:
            with self.subTest(tarih=tarih):
                ilk = self.calistir(tarih, simdi)
                sonra = uygula(self.etkinlikler, ilk["eylemler"])
                ikinci = self.calistir(tarih, simdi, etkinlikler=sonra)
                self.assertEqual(ikinci["eylemler"], [])
                self.assertIn("Değişiklik yok", ikinci["ozet"])
                self.assertEqual(ikinci["liste"], ilk["liste"])
                self.assertEqual(ikinci["pencereler"], ilk["pencereler"])

    def test_test_bitince_guncelleme(self):
        ilk = self.calistir("2026-11-13", "2026-11-12T20:50")
        sonra = uygula(self.etkinlikler, ilk["eylemler"])
        durum = copy.deepcopy(self.durum)
        durum["ANA1"]["t"] = "2026-11-12"
        plan = self.calistir("2026-11-13", "2026-11-12T20:50", etkinlikler=sonra, durum=durum)
        self.assertEqual(plan["liste"], ["1 Anki", "2 ANA 2 test", "3 ANA 7 slayt", "4 HİST 1 slayt"])
        self.assertEqual(self.araclar(plan), ["update_event"])
        p = plan["eylemler"][0]["parametreler"]
        eski = next(e for e in sonra if e["id"] == p["eventId"])
        self.assertEqual(eski["summary"], "2 ANA 1 test")
        self.assertEqual(p, {"eventId": p["eventId"], "summary": "2 ANA 2 test"})
        self.assertEqual(self.calistir("2026-11-13", "2026-11-12T20:50",
                                       etkinlikler=uygula(sonra, plan["eylemler"]),
                                       durum=durum)["eylemler"], [])

    def test_liste_kisalinca_yalniz_bot_silinir(self):
        ilk = self.calistir("2026-11-13", "2026-11-12T20:50")
        sonra = uygula(self.etkinlikler, ilk["eylemler"])
        # Tüm ANA testleri ve dünün dersleri bitti -> liste kısalır
        durum = copy.deepcopy(self.durum)
        for k in ("ANA1", "ANA3", "ANA3b", "ANA3c", "ANA4", "ANA6", "HIST0", "HIST1", "HIST3"):
            durum.setdefault(k, {})["t"] = "2026-11-12"
        plan = self.calistir("2026-11-13", "2026-11-12T20:50", etkinlikler=sonra, durum=durum)
        self.assertLess(len(plan["liste"]), 4 + 1)
        silinen = [ey for ey in plan["eylemler"] if ey["arac"] == "delete_event"]
        kimlikten = {e["id"]: e for e in sonra}
        for ey in silinen:
            self.assertTrue(bot_mu(kimlikten[ey["parametreler"]["eventId"]]))
        self.assertNotIn("create_event", self.araclar(plan))
        self.assertEqual(self.calistir("2026-11-13", "2026-11-12T20:50",
                                       etkinlikler=uygula(sonra, plan["eylemler"]),
                                       durum=durum)["eylemler"], [])

    def test_kullanici_penceresi_eklenince_bot_pencereleri_silinir(self):
        ilk = self.calistir("2026-11-13", "2026-11-12T20:50")
        sonra = uygula(self.etkinlikler, ilk["eylemler"])
        sonra.append({"id": "k1", "summary": "Çalışma (kütüphane)",
                      "start": {"dateTime": "2026-11-13T16:00:00+03:00"},
                      "end": {"dateTime": "2026-11-13T17:00:00+03:00"}})
        plan = self.calistir("2026-11-13", "2026-11-12T20:50", etkinlikler=sonra)
        # 60 dk -> bütçe 20: hiçbir şey sığmaz, tek madde (ilk test) yine de girer
        self.assertEqual(plan["liste"], ["1 Anki", "2 ANA 1 test"])
        self.assertEqual(self.araclar(plan), ["delete_event"] * 4)
        kimlikten = {e["id"]: e for e in sonra}
        silinen = sorted(kimlikten[ey["parametreler"]["eventId"]]["summary"] for ey in plan["eylemler"])
        self.assertEqual(silinen, ["3 ANA 7 slayt", "4 HİST 1 slayt", "Çalışma", "Çalışma"])
        self.assertEqual(self.saatler(plan), [("16:00", "17:00")])


class Gym(Temel):
    def test_yanlis_baslik_duzeltilir(self):
        etk = copy.deepcopy(self.etkinlikler)
        gym = next(e for e in etk if e["id"] == "e_gym13")
        gym["summary"] = "Gym (Üst B)"
        gym["calendarId"] = "gymtakvim@x"
        plan = self.calistir("2026-11-13", "2026-11-12T20:50", etkinlikler=etk)
        guncel = [ey for ey in plan["eylemler"] if ey["arac"] == "update_event"]
        self.assertEqual(guncel, [{"arac": "update_event", "parametreler": {
            "eventId": "e_gym13", "calendarId": "gymtakvim@x", "summary": "Gym (Alt A)"}}])
        self.assertEqual(self.calistir("2026-11-13", "2026-11-12T20:50",
                                       etkinlikler=uygula(etk, plan["eylemler"]))["eylemler"], [])

    def test_dongu_basa_sarar(self):
        etk = copy.deepcopy(self.etkinlikler)
        next(e for e in etk if e["id"] == "e_gym12")["summary"] = "Gym (Alt B)"
        plan = self.calistir("2026-11-13", "2026-11-12T20:50", etkinlikler=etk)
        guncel = [ey["parametreler"] for ey in plan["eylemler"] if ey["arac"] == "update_event"]
        self.assertEqual(guncel, [{"eventId": "e_gym13", "summary": "Gym (Üst A)"}])

    def test_gecmis_yoksa_dokunulmaz(self):
        etk = [e for e in self.etkinlikler if e["id"] != "e_gym12"]
        next(e for e in etk if e["id"] == "e_gym13")["summary"] = "Gym (Üst B)"
        plan = self.calistir("2026-11-13", "2026-11-12T20:50", etkinlikler=etk)
        self.assertEqual(self.araclar(plan), ["create_event"] * 6)
        self.assertTrue(any("bulunamadı" in s for s in plan["ozet"]))


class Pencereler(Temel):
    def test_kullanici_calismasi_varsa_bot_eklemez(self):
        etk = self.etkinlikler + [{"id": "k1", "summary": "Çalışma",
                                   "start": {"dateTime": "2026-11-13T15:30:00+03:00"},
                                   "end": {"dateTime": "2026-11-13T18:30:00+03:00"}}]
        plan = self.calistir("2026-11-13", "2026-11-12T20:50", etkinlikler=etk)
        for ey in plan["eylemler"]:
            self.assertNotEqual(ey["parametreler"].get("description"), "[evolve-bot] calisma")
        self.assertEqual(self.saatler(plan), [("15:30", "18:30")])
        # 180 dk -> bütçe 100: b1 iki slayt (90), test sığmaz
        self.assertEqual(plan["liste"], ["1 Anki", "2 ANA 7 slayt", "3 HİST 1 slayt"])

    def test_gec_pencere_son_bitise_kadar(self):
        etk = [{"id": "x", "summary": "Gezi",
                "start": {"dateTime": "2026-11-14T07:00:00+03:00"},
                "end": {"dateTime": "2026-11-14T18:20:00+03:00"}}]
        plan = self.calistir("2026-11-14", "2026-11-13T20:50", etkinlikler=etk)
        self.assertEqual(self.saatler(plan), [("18:30", "20:30")])

    def test_simdiden_onceki_pencere_dusurulur(self):
        plan = self.calistir("2026-11-14", "2026-11-14T08:00", etkinlikler=[])
        self.assertEqual(self.saatler(plan), [("12:30", "15:30")])

    def test_utc_saat_istanbula_cevrilir(self):
        etk = [{"id": "x", "summary": "Toplantı",
                "start": {"dateTime": "2026-11-14T04:30:00Z"},
                "end": {"dateTime": "2026-11-14T16:10:00Z"}}]  # 07:30–19:10 İstanbul
        plan = self.calistir("2026-11-14", "2026-11-13T20:50", etkinlikler=etk)
        self.assertEqual(self.saatler(plan), [("19:15", "21:00")])


class Liste(Temel):
    def test_hist_sirasi(self):
        # Dünün dersi HIST3 (n=4) ama HIST0 (n=1) okunmamış -> "HİST 1 slayt"
        plan = self.calistir("2026-11-13", "2026-11-12T20:50")
        self.assertIn("4 HİST 1 slayt", plan["liste"])
        self.assertFalse(any("HİST 4" in m for m in plan["liste"]))

    def test_hist_tekrarsiz_ve_sirali(self):
        # Testler bitmiş, bütçe geniş: HİST slaytları 1,2,4 sırasıyla ve birer kez
        durum = copy.deepcopy(self.durum)
        for k in ("ANA1", "ANA3", "ANA3b", "ANA3c", "ANA4"):
            durum[k]["t"] = "2026-11-12"
        dersler = [d for d in self.dersler if d["c"] in ("HİST", "ANA")]
        self.dersler = dersler
        etk = [{"id": "k1", "summary": "Çalışma",
                "start": {"dateTime": "2026-11-14T08:00:00+03:00"},
                "end": {"dateTime": "2026-11-14T20:00:00+03:00"}}]
        plan = self.calistir("2026-11-14", "2026-11-13T20:50", etkinlikler=etk, durum=durum)
        self.assertEqual(plan["liste"], ["1 Anki", "2 HİST 1 slayt", "3 HİST 2 slayt",
                                         "4 ANA 7 slayt", "5 HİST 4 slayt"])

    def _testsiz_durum(self):
        durum = copy.deepcopy(self.durum)
        for k in ("ANA1", "ANA3", "ANA3b", "ANA3c", "ANA4"):
            durum[k]["t"] = "2026-11-12"
        return durum

    def test_hafta_havuzu_gecerliyse_kullanilir(self):
        hafta = {"hafta": "2026-11-09", "havuz": ["TBG5:r", "HIST3:r", "ANA3:t"]}
        plan = self.calistir("2026-11-14", "2026-11-13T20:50", durum=self._testsiz_durum(), hafta=hafta)
        self.assertEqual(plan["liste"], ["1 Anki", "2 BFZ 1 slayt", "3 TBG 6 slayt", "4 HİST 1 slayt"])

    def test_hafta_havuzu_eskiyse_yok_sayilir(self):
        hafta = {"hafta": "2026-11-02", "havuz": ["TBG5:r", "HIST3:r", "ANA3:t"]}
        beklenen = ["1 Anki", "2 BFZ 1 slayt", "3 HİST 1 slayt", "4 TBG 2 slayt", "5 TBG 4 slayt"]
        plan = self.calistir("2026-11-14", "2026-11-13T20:50", durum=self._testsiz_durum(), hafta=hafta)
        self.assertEqual(plan["liste"], beklenen)
        yok = self.calistir("2026-11-14", "2026-11-13T20:50", durum=self._testsiz_durum())
        self.assertEqual(yok["liste"], beklenen)

    def test_en_cok_madde(self):
        etk = [{"id": "k1", "summary": "Çalışma",
                "start": {"dateTime": "2026-11-14T07:00:00+03:00"},
                "end": {"dateTime": "2026-11-14T23:00:00+03:00"}}]
        plan = self.calistir("2026-11-14", "2026-11-13T20:50", etkinlikler=etk)
        self.assertEqual(len(plan["liste"]), P.EN_COK_MADDE)
        self.assertEqual(plan["liste"][0], "1 Anki")


class ProgramYok(Temel):
    def test_not_mevcut_bot_listesinin_yerini_alir(self):
        etk = self.etkinlikler + [
            {"id": "b1", "summary": "1 Anki", "description": "[evolve-bot] liste",
             "start": {"date": "2026-11-16"}, "end": {"date": "2026-11-17"}},
            {"id": "b2", "summary": "2 ANA 1 test", "description": "[evolve-bot] liste",
             "start": {"date": "2026-11-16"}, "end": {"date": "2026-11-17"}},
            {"id": "b3", "summary": "Çalışma", "description": "[evolve-bot] calisma", "location": "ev",
             "start": {"dateTime": "2026-11-16T07:30:00+03:00"},
             "end": {"dateTime": "2026-11-16T10:30:00+03:00"}},
            {"id": "g16", "summary": "Gym (Alt B)",
             "start": {"dateTime": "2026-11-16T17:00:00+03:00"},
             "end": {"dateTime": "2026-11-16T18:30:00+03:00"}},
        ]
        plan = self.calistir("2026-11-16", "2026-11-15T20:50", etkinlikler=etk)
        silinen = sorted(ey["parametreler"]["eventId"] for ey in plan["eylemler"]
                         if ey["arac"] == "delete_event")
        self.assertEqual(silinen, ["b1", "b2", "b3"])
        olusan = [ey["parametreler"]["summary"] for ey in plan["eylemler"] if ey["arac"] == "create_event"]
        self.assertEqual(olusan, [P.PROGRAM_YOK_BASLIK])
        self.assertEqual(len(plan["eylemler"]), 4)  # gym'e dokunulmaz
        sonra = uygula(etk, plan["eylemler"])
        self.assertEqual(self.calistir("2026-11-16", "2026-11-15T20:50", etkinlikler=sonra)["eylemler"], [])

    def test_ders_girilince_not_silinir(self):
        ilk = self.calistir("2026-11-16", "2026-11-15T20:50")
        sonra = uygula(self.etkinlikler, ilk["eylemler"])
        sonra.append({"id": "d16", "summary": "Sinir sistemi", "calendarName": "Ders",
                      "start": {"dateTime": "2026-11-16T08:30:00+03:00"},
                      "end": {"dateTime": "2026-11-16T10:15:00+03:00"}})
        plan = self.calistir("2026-11-16", "2026-11-15T20:50", etkinlikler=sonra)
        self.assertEqual(self.araclar(plan).count("delete_event"), 1)
        self.assertGreater(len(plan["liste"]), 1)


class Guvenlik(Temel):
    T = date(2026, 11, 13)
    SIMDI = datetime(2026, 11, 12, 20, 50)

    def reddet(self, eylem, etkinlikler=None, gun=None):
        with self.assertRaises(P.GuvenlikHatasi):
            P.guvenlik_denetimi([eylem], etkinlikler or self.etkinlikler, gun or self.T, self.SIMDI)

    def test_bot_olmayan_silinemez(self):
        self.reddet({"arac": "delete_event", "parametreler": {"eventId": "e_bfz13"}})
        self.reddet({"arac": "delete_event", "parametreler": {"eventId": "e_gym13"}})

    def test_bot_olmayan_guncellenemez(self):
        self.reddet({"arac": "update_event", "parametreler": {"eventId": "e_bfz13", "summary": "x"}})
        self.reddet({"arac": "update_event",
                     "parametreler": {"eventId": "e_gym13", "summary": "Gym (Alt A)", "location": "x"}})
        self.reddet({"arac": "update_event", "parametreler": {
            "eventId": "e_bfz13", "overrideReminders": [{"method": "popup", "minutes": 50}]}})

    def test_baska_gun_ve_gecmis(self):
        self.reddet({"arac": "update_event", "parametreler": {"eventId": "e_gym12", "summary": "Gym (Alt A)"}})
        self.reddet({"arac": "delete_event", "parametreler": {"eventId": "yok"}})
        self.reddet({"arac": "update_event", "parametreler": {"eventId": "e_gym12", "summary": "x"}},
                    gun=date(2026, 11, 11))

    def test_olusturma_kurallari(self):
        iyi = P.tum_gun_olustur("1 Anki", self.T, "[evolve-bot] liste")
        P.guvenlik_denetimi([iyi], self.etkinlikler, self.T, self.SIMDI)
        isaretsiz = copy.deepcopy(iyi)
        isaretsiz["parametreler"]["description"] = "liste"
        self.reddet(isaretsiz)
        self.reddet(P.tum_gun_olustur("1 Anki", date(2026, 11, 14), "[evolve-bot] liste"))

    def test_izinli_olanlar_gecer(self):
        P.guvenlik_denetimi(
            [{"arac": "update_event", "parametreler": {"eventId": "e_gym13", "summary": "Gym (Alt A)"}}],
            self.etkinlikler, self.T, self.SIMDI)


class Bildirim(Temel):
    def setUp(self):
        super().setUp()
        self._eski = P.BILDIRIM_DUZELT
        P.BILDIRIM_DUZELT = True

    def tearDown(self):
        P.BILDIRIM_DUZELT = self._eski

    def test_bildirimler_duzeltilir_ve_tekrarlanmaz(self):
        plan = self.calistir("2026-11-13", "2026-11-12T20:50")
        guncel = {ey["parametreler"]["eventId"]: ey["parametreler"]
                  for ey in plan["eylemler"] if ey["arac"] == "update_event"}
        self.assertEqual(guncel, {
            "e_anap13": {"eventId": "e_anap13", "overrideReminders": [{"method": "popup", "minutes": 50}]},
            "e_bfz13": {"eventId": "e_bfz13", "useDefaultReminders": False},
            "e_gym13": {"eventId": "e_gym13", "overrideReminders": [{"method": "popup", "minutes": 20}]},
        })
        sonra = uygula(self.etkinlikler, plan["eylemler"])
        self.assertEqual(self.calistir("2026-11-13", "2026-11-12T20:50", etkinlikler=sonra)["eylemler"], [])

    def test_kapaliyken_derse_dokunulmaz(self):
        P.BILDIRIM_DUZELT = False
        plan = self.calistir("2026-11-13", "2026-11-12T20:50")
        self.assertEqual(self.araclar(plan), ["create_event"] * 6)


class KomutSatiri(unittest.TestCase):
    def kos(self, *arg):
        cikti, hata = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(cikti), contextlib.redirect_stderr(hata):
            kod = P.ana(["--etkinlikler", ETKINLIK_DOSYASI, "--db", VERI, *arg])
        return kod, cikti.getvalue(), hata.getvalue()

    def test_gecmis_gun_reddedilir(self):
        kod, cikti, hata = self.kos("--tarih", "2026-11-11", "--simdi", "2026-11-12T20:50")
        self.assertEqual(kod, 2)
        self.assertIn("Reddedildi", hata)
        self.assertEqual(cikti, "")

    def test_varsayilan_tarih_yarin(self):
        kod, cikti, _ = self.kos("--simdi", "2026-11-12T20:50")
        self.assertEqual(kod, 0)
        self.assertIn("Plan: 2026-11-13 (Cuma)", cikti)
        self.assertIn("4 HİST 1 slayt", cikti)

    def test_gece_gec_calistirma_ayni_gun(self):
        kod, cikti, _ = self.kos("--simdi", "2026-11-13T01:30")
        self.assertEqual(kod, 0)
        self.assertIn("Plan: 2026-11-13 (Cuma)", cikti)

    def test_cikti_dosyasi(self):
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "plan.json")
            kod, _, _ = self.kos("--tarih", "2026-11-13", "--simdi", "2026-11-12T20:50", "--cikti", yol)
            self.assertEqual(kod, 0)
            plan = oku(yol)
        self.assertEqual(sorted(plan), ["eylemler", "liste", "pencereler", "tarih"])
        self.assertEqual(plan["tarih"], "2026-11-13")
        self.assertEqual(plan["pencereler"][0],
                         {"baslangic": "2026-11-13T07:30:00", "bitis": "2026-11-13T08:30:00", "dk": 60})
        self.assertEqual(len(plan["eylemler"]), 6)

    def test_degisiklik_yok_satiri(self):
        etk = oku(ETKINLIK_DOSYASI)["events"]
        ilk = P.planla(etk, oku(os.path.join(VERI, "takip", "dersler.json"))["list"],
                       oku(os.path.join(VERI, "takip", "durum.json"))["s"], None,
                       date(2026, 11, 13), datetime(2026, 11, 12, 20, 50))
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "etk.json")
            with open(yol, "w", encoding="utf-8") as f:
                json.dump({"events": uygula(etk, ilk["eylemler"])}, f, ensure_ascii=False)
            cikti = io.StringIO()
            with contextlib.redirect_stdout(cikti):
                kod = P.ana(["--etkinlikler", yol, "--db", VERI,
                             "--tarih", "2026-11-13", "--simdi", "2026-11-12T20:50"])
        self.assertEqual(kod, 0)
        self.assertIn("Değişiklik yok", cikti.getvalue().splitlines())


if __name__ == "__main__":
    unittest.main()
