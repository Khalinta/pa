import contextlib
import datetime
import io
import json
import os
import tempfile
import unittest

import aworld_cevir

GERCEK = "/tmp/claude-0/-home-user-pa/782ab594-15c7-5665-95d6-43aa73e513b4/scratchpad/aworld"
BUGUN = datetime.date.today().isoformat()

DERSLER = [
    {"id": "ANA1", "c": "ANA", "n": 1, "d": "2026-11-02", "t": "Giriş"},
    {"id": "HIST0", "c": "HIST", "n": 1, "d": "2026-11-03", "t": "Spermatogenez"},
    {"id": "BIST1", "c": "BIST", "n": 1, "d": "2026-11-04", "t": "Olasılık"},
    {"id": "BKY1", "c": "BKY", "n": 1, "d": "2026-11-05", "t": "Su"},
]


def yaz(yol, veri):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        if isinstance(veri, str):
            f.write(veri)
        else:
            json.dump(veri, f, ensure_ascii=False)


def oku(yol):
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


class Temel(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.girdi = os.path.join(self._tmp.name, "aworld")
        self.cikti = os.path.join(self._tmp.name, "cikti")

    def kur(self, dersler=DERSLER, durum=None, sorular=None, ilerleme=None, kurul=2):
        yaz(os.path.join(self.girdi, "lectures", f"k{kurul}.json"),
            {"list": dersler, "exam": "2026-12-18", "kurul": kurul})
        if durum is not None:
            yaz(os.path.join(self.girdi, "lectures", f"k{kurul}state.json"), {"s": durum})
        if sorular is None:
            sorular = {"k2-ana01-01": {"course": "ANA", "lectureNo": 1},
                       "k2-ana01-02": {"course": "ANA", "lectureNo": 1}}
        os.makedirs(os.path.join(self.girdi, "questions"), exist_ok=True)
        for k, v in sorular.items():
            yaz(os.path.join(self.girdi, "questions", k + ".json"), v)
        os.makedirs(os.path.join(self.girdi, "progress"), exist_ok=True)
        for k, v in (ilerleme or {}).items():
            yaz(os.path.join(self.girdi, "progress", k + ".json"), v)

    def calistir(self):
        cikis, hata = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(cikis), contextlib.redirect_stderr(hata):
            kod = aworld_cevir.main(["--aworld", self.girdi, "--cikti", self.cikti])
        return kod, cikis.getvalue(), hata.getvalue()

    def sonuc(self):
        kod, cikis, hata = self.calistir()
        self.assertEqual(kod, 0, hata)
        takip = os.path.join(self.cikti, "takip")
        return (oku(os.path.join(takip, "dersler.json")),
                oku(os.path.join(takip, "durum.json"))["s"], cikis)


class CevirTest(Temel):
    def test_en_yuksek_kurul_secilir(self):
        self.kur(dersler=[{"id": "ESKI1", "c": "ANA", "n": 1}], kurul=2)
        self.kur(dersler=DERSLER, durum={"ANA1": {"r": "2026-11-10"}}, kurul=10)
        # desene uymayan adlar sayılmaz
        yaz(os.path.join(self.girdi, "lectures", "k99x.json"), {"list": [{"id": "X"}]})
        yaz(os.path.join(self.girdi, "lectures", "k2state.json"), {"s": {"ANA1": {"r": "1999-01-01"}}})
        dersler, durum, _ = self.sonuc()
        self.assertEqual([d["id"] for d in dersler["list"]], [d["id"] for d in DERSLER])
        self.assertEqual(durum["ANA1"]["r"], "2026-11-10")

    def test_kod_esleme(self):
        self.kur()
        dersler, _, _ = self.sonuc()
        self.assertEqual([d["c"] for d in dersler["list"]], ["ANA", "HİST", "BİST", "BKY"])
        self.assertEqual(dersler["exam"], "2026-12-18")
        self.assertEqual(dersler["list"][1],
                         {"id": "HIST0", "c": "HİST", "n": 1, "d": "2026-11-03", "t": "Spermatogenez"})

    def test_hepsi_cozulunce_bitti(self):
        self.kur(durum={"ANA1": {"r": "2026-11-14"}},
                 ilerleme={"k2-ana01-01": {"n": 1}, "k2-ana01-02": {"n": 3}})
        _, durum, cikis = self.sonuc()
        self.assertEqual(durum, {"ANA1": {"r": "2026-11-14", "t": BUGUN}})
        self.assertIn("ANA 1: okundu, sorular 2/2 (bitti)", cikis)
        self.assertIn("4 ders, 1 okundu, 1 bitti", cikis)
        self.assertIn("2 soru, 2 çözüldü", cikis)

    def test_biri_cozulmemisse_bitmez(self):
        # n=0 çözülmüş sayılmaz; elle t de soruları ezmez
        self.kur(durum={"ANA1": {"r": True, "t": "2026-11-12"}},
                 ilerleme={"k2-ana01-01": {"n": 1}, "k2-ana01-02": {"n": 0}})
        _, durum, cikis = self.sonuc()
        self.assertEqual(durum, {"ANA1": {"r": BUGUN}})
        self.assertIn("ANA 1: okundu, sorular 1/2", cikis)
        self.assertNotIn("bitti)", cikis)

    def test_soru_yoksa_elle_t(self):
        self.kur(durum={"BKY1": {"t": "2026-11-09"}, "BIST1": {"t": True}, "HIST0": {"t": ""}})
        _, durum, _ = self.sonuc()
        self.assertEqual(durum, {"BKY1": {"t": "2026-11-09"}, "BIST1": {"t": BUGUN}})

    def test_ders_kodu_ozgun_haliyle_eslesir(self):
        # sorular HIST der, çıktı HİST olur
        self.kur(sorular={"k2-hist01-01": {"course": "HIST", "lectureNo": 1}},
                 ilerleme={"k2-hist01-01": {"n": 2}})
        _, durum, _ = self.sonuc()
        self.assertEqual(durum, {"HIST0": {"t": BUGUN}})

    def test_cikmis_sorular_sayilmaz(self):
        self.kur(sorular={"k2-ana01-01": {"course": "ANA", "lectureNo": 1},
                          "cikmis-01": {"course": "ANA", "lectureNo": 1, "past": True},
                          "cikmis-02": {"course": "BKY", "lectureNo": 1, "past": "2024"}},
                 ilerleme={"k2-ana01-01": {"n": 1}})
        _, durum, cikis = self.sonuc()
        self.assertEqual(durum, {"ANA1": {"t": BUGUN}})  # BKY1: yalnız çıkmış soru → Q boş
        self.assertIn("1 soru, 1 çözüldü", cikis)

    def test_durum_dosyasi_yok(self):
        self.kur(ilerleme={"k2-ana01-01": {"n": 1}})
        _, durum, _ = self.sonuc()
        self.assertEqual(durum, {})

    def test_hafta_silinir(self):
        self.kur()
        hafta = os.path.join(self.cikti, "takip", "hafta.json")
        yaz(hafta, {"eski": 1})
        self.sonuc()
        self.assertFalse(os.path.exists(hafta))

    def test_sarmal_belge_acilir(self):
        self.kur(sorular={"k2-ana01-01": {"data": {"course": "ANA", "lectureNo": 1}}},
                 ilerleme={"k2-ana01-01": {"fields": {"n": 1}}})
        _, durum, _ = self.sonuc()
        self.assertEqual(durum, {"ANA1": {"t": BUGUN}})


class HataTest(Temel):
    def hata_bekle(self):
        # eski hafta.json'a da dokunulmamalı
        hafta = os.path.join(self.cikti, "takip", "hafta.json")
        yaz(hafta, {"eski": 1})
        kod, cikis, hata = self.calistir()
        self.assertEqual(kod, 1)
        self.assertTrue(hata.strip())
        self.assertEqual(cikis, "")
        self.assertEqual(os.listdir(os.path.join(self.cikti, "takip")), ["hafta.json"])

    def test_ders_dosyasi_yok(self):
        self.kur()
        os.remove(os.path.join(self.girdi, "lectures", "k2.json"))
        self.hata_bekle()

    def test_liste_bos(self):
        self.kur(dersler=[])
        self.hata_bekle()

    def test_liste_eksik(self):
        self.kur()
        yaz(os.path.join(self.girdi, "lectures", "k2.json"), {"exam": "2026-12-18"})
        self.hata_bekle()

    def test_soru_klasoru_yok(self):
        self.kur(sorular={})
        os.rmdir(os.path.join(self.girdi, "questions"))
        self.hata_bekle()

    def test_soru_klasoru_bos(self):
        self.kur(sorular={})
        self.hata_bekle()

    def test_ilerleme_klasoru_yok(self):
        self.kur()
        os.rmdir(os.path.join(self.girdi, "progress"))
        self.hata_bekle()

    def test_bozuk_json(self):
        for ad in ("lectures/k2.json", "lectures/k2state.json",
                   "questions/k2-ana01-01.json", "progress/k2-ana01-01.json"):
            with self.subTest(ad):
                self.kur(durum={})
                yol = os.path.join(self.girdi, ad)
                with open(yol, encoding="utf-8") if os.path.exists(yol) else io.StringIO("") as f:
                    eski = f.read()
                yaz(yol, "{bozuk")
                self.hata_bekle()
                yaz(yol, eski) if eski else os.remove(yol)

    def test_cikti_hic_olusmaz(self):
        self.kur(dersler=[])
        kod, _, _ = self.calistir()
        self.assertEqual(kod, 1)
        self.assertFalse(os.path.exists(self.cikti))


@unittest.skipUnless(os.path.isdir(GERCEK), "gerçek örnek yok")
class GercekOrnekTest(Temel):
    def test_gercek_ornek(self):
        self.girdi = GERCEK
        dersler, durum, _ = self.sonuc()
        self.assertTrue(dersler["list"])
        self.assertIn("r", durum["ANA1"])
        self.assertIn("t", durum["ANA1"])
        self.assertEqual(list(durum["ANA3"]), ["r"])
        self.assertNotIn("t", durum.get("HIST2", {}))


if __name__ == "__main__":
    unittest.main()
