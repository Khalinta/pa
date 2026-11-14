#!/usr/bin/env python3
"""AWorld dışa aktarımını planla.py'nin okuduğu eski takip biçimine çevirir.

Kullanım: python3 aworld_cevir.py --aworld DISA_AKTARIM --cikti CIKTI
Yazdıkları: CIKTI/takip/dersler.json ve CIKTI/takip/durum.json
"""
import argparse
import datetime
import json
import os
import re
import sys

KOD_ESLEME = {"HIST": "HİST", "BIST": "BİST"}
SARMAL_ANAHTARLAR = ("data", "fields", "doc", "document", "value")
KURUL_DESENI = re.compile(r"^k(\d+)\.json$")


class CevirHatasi(Exception):
    pass


def json_oku(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as h:
        raise CevirHatasi(f"Dosya okunamadı: {yol} ({h})")


def sarmali_ac(belge, beklenen):
    """Belge bir sarmal anahtarın altındaysa içini döndürür."""
    for _ in range(3):
        if not isinstance(belge, dict) or any(k in belge for k in beklenen):
            break
        ic = [belge[k] for k in SARMAL_ANAHTARLAR if isinstance(belge.get(k), dict)]
        if len(ic) != 1:
            break
        belge = ic[0]
    return belge


def klasor_oku(klasor, beklenen):
    """{dosya adı (uzantısız): belge}"""
    sonuc = {}
    for ad in sorted(os.listdir(klasor)):
        if ad.endswith(".json"):
            sonuc[ad[:-5]] = sarmali_ac(json_oku(os.path.join(klasor, ad)), beklenen)
    return sonuc


def kurul_bul(ders_klasoru):
    """En yüksek N'li k<N>.json için N; yoksa None."""
    if not os.path.isdir(ders_klasoru):
        return None
    nolar = [int(m.group(1)) for m in map(KURUL_DESENI.match, os.listdir(ders_klasoru)) if m]
    return max(nolar) if nolar else None


def no_anahtari(deger):
    """Ders numarasını karşılaştırılabilir yapar (1, 1.0 ve "1" aynı)."""
    try:
        return int(str(deger).strip())
    except (TypeError, ValueError):
        return deger


def cozuldu_mu(ilerleme):
    n = ilerleme.get("n") if isinstance(ilerleme, dict) else None
    return isinstance(n, (int, float)) and not isinstance(n, bool) and n > 0


def cevir(aworld, bugun=None):
    """Dışa aktarımı okur; (dersler, durum, özet satırları) döndürür. Hiçbir şey yazmaz."""
    bugun = bugun or datetime.date.today().isoformat()
    ders_klasoru = os.path.join(aworld, "lectures")
    soru_klasoru = os.path.join(aworld, "questions")
    ilerleme_klasoru = os.path.join(aworld, "progress")

    kurul = kurul_bul(ders_klasoru)
    if kurul is None:
        raise CevirHatasi(f"Ders listesi yok: {ders_klasoru}/k<N>.json")
    ders_yolu = os.path.join(ders_klasoru, f"k{kurul}.json")
    ders_belgesi = sarmali_ac(json_oku(ders_yolu), ("list",))
    liste = ders_belgesi.get("list") if isinstance(ders_belgesi, dict) else None
    if not isinstance(liste, list) or not liste:
        raise CevirHatasi(f"Ders listesi boş ya da eksik: {ders_yolu}")
    if not all(isinstance(d, dict) and "id" in d for d in liste):
        raise CevirHatasi(f"Ders listesinde geçersiz kayıt: {ders_yolu}")

    # durum dosyası olmayabilir
    durum_yolu = os.path.join(ders_klasoru, f"k{kurul}state.json")
    eski_durum = {}
    if os.path.exists(durum_yolu):
        belge = sarmali_ac(json_oku(durum_yolu), ("s",))
        s = belge.get("s") if isinstance(belge, dict) else None
        if s is not None and not isinstance(s, dict):
            raise CevirHatasi(f"Durum dosyası geçersiz: {durum_yolu}")
        eski_durum = s or {}

    if not os.path.isdir(soru_klasoru):
        raise CevirHatasi(f"Soru klasörü yok: {soru_klasoru}")
    if not os.path.isdir(ilerleme_klasoru):
        raise CevirHatasi(f"İlerleme klasörü yok: {ilerleme_klasoru}")
    sorular = klasor_oku(soru_klasoru, ("course", "lectureNo"))
    if not sorular:
        raise CevirHatasi(f"Soru klasöründe .json yok: {soru_klasoru}")
    ilerleme = klasor_oku(ilerleme_klasoru, ("n",))

    # çıkmış sorular sayılmaz
    gruplar = {}
    for kimlik, soru in sorular.items():
        if not isinstance(soru, dict):
            raise CevirHatasi(f"Soru belgesi geçersiz: {kimlik}.json")
        if soru.get("past"):
            continue
        anahtar = (soru.get("course"), no_anahtari(soru.get("lectureNo")))
        gruplar.setdefault(anahtar, []).append(kimlik)
    cozulen = {k for k, v in ilerleme.items() if cozuldu_mu(v)}

    yeni_liste, durum, satirlar = [], {}, []
    okunan = biten = 0
    for ders in liste:
        yeni = dict(ders)
        yeni["c"] = KOD_ESLEME.get(ders.get("c"), ders.get("c"))
        yeni_liste.append(yeni)

        d = eski_durum.get(ders["id"])
        d = d if isinstance(d, dict) else {}
        q = gruplar.get((ders.get("c"), no_anahtari(ders.get("n"))), [])
        cozulmus = sum(1 for k in q if k in cozulen)
        bitti = (cozulmus == len(q)) if q else bool(d.get("t"))

        kayit = {}
        if d.get("r"):
            kayit["r"] = d["r"] if isinstance(d["r"], str) else bugun
            okunan += 1
        if bitti:
            kayit["t"] = d["t"] if isinstance(d.get("t"), str) and d["t"] else bugun
            biten += 1
        if kayit:
            durum[ders["id"]] = kayit
            parcalar = []
            if "r" in kayit:
                parcalar.append("okundu")
            parcalar.append(f"sorular {cozulmus}/{len(q)}" if q else "soru yok")
            satir = f"{ders.get('c')} {ders.get('n')}: " + ", ".join(parcalar)
            if bitti:
                satir += " (bitti)" if q else " (elle bitti)"
            satirlar.append(satir)

    sayilan = [k for v in gruplar.values() for k in v]
    ozet = [
        f"Kurul {kurul}: {len(liste)} ders, {okunan} okundu, {biten} bitti",
        f"Sorular: {len(sayilan)} soru, {sum(1 for k in sayilan if k in cozulen)} çözüldü",
    ] + satirlar
    dersler = dict(ders_belgesi)
    dersler["list"] = yeni_liste
    return dersler, {"s": durum}, ozet


def json_yaz(yol, veri):
    gecici = yol + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(gecici, yol)


def yaz(cikti, dersler, durum):
    takip = os.path.join(cikti, "takip")
    os.makedirs(takip, exist_ok=True)
    json_yaz(os.path.join(takip, "dersler.json"), dersler)
    json_yaz(os.path.join(takip, "durum.json"), durum)
    # haftalık havuz artık yok; eskisi kullanılmasın
    hafta = os.path.join(takip, "hafta.json")
    if os.path.exists(hafta):
        os.remove(hafta)


def main(argv=None):
    ap = argparse.ArgumentParser(description="AWorld dışa aktarımını eski takip biçimine çevirir.")
    ap.add_argument("--aworld", required=True, help="AWorld dışa aktarım klasörü")
    ap.add_argument("--cikti", required=True, help="takip klasörünün yazılacağı dizin")
    a = ap.parse_args(argv)
    try:
        dersler, durum, ozet = cevir(a.aworld)
        yaz(a.cikti, dersler, durum)
    except (CevirHatasi, OSError) as h:
        print(f"Hata: {h}", file=sys.stderr)
        return 1
    print("\n".join(ozet))
    return 0


if __name__ == "__main__":
    sys.exit(main())
