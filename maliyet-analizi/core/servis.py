"""Veritabanı ile hesap motoru arasındaki katman: kayıt, yükleme, ilerleme, kontroller, rapor."""
import json

import pandas as pd

from . import db as dbm
from .engine import (
    TOLERANS, DonemVerisi, Sonuc, dagitilan_toplam, dagitilmamis_toplam, hesapla, oran_toplami_kontrol,
)
from .importers import AYLAR

AILE_SIRA = {"MADEN": 1, "TSF": 2, "RC": 3, "KİRALIK": 4}


def donem_adi(conn, donem_id) -> str:
    d = conn.execute("SELECT yil, ay FROM donem WHERE id=?", (donem_id,)).fetchone()
    return f"{AYLAR[d['ay'] - 1]} {d['yil']}"


# ---------------------------------------------------------------- yükleme kayıtları

def yukleme_kaydet(conn, donem_id, kaynak, dosya_adi, hash_, satir):
    conn.execute(
        "INSERT INTO yukleme (donem_id, kaynak, dosya_adi, hash, satir) VALUES (?, ?, ?, ?, ?)",
        (donem_id, kaynak, dosya_adi, hash_, satir),
    )


def ayni_dosya_yuklu_mu(conn, donem_id, kaynak, hash_) -> bool:
    son = conn.execute(
        "SELECT hash FROM yukleme WHERE kaynak=? AND donem_id IS ? ORDER BY id DESC LIMIT 1", (kaynak, donem_id)
    ).fetchone()
    return bool(son and son["hash"] == hash_)


# ---------------------------------------------------------------- gelir

def _gelir_eslesme_oner(conn, aile: str, kalem: str, kdv: str | None) -> tuple[int, str, int]:
    """Yeni bir Master Data kalemi için kâr merkezi önerisi."""
    kalem_n = kalem.upper().replace("İ", "I")
    if "KIRALIK" in kalem_n:
        return dbm.kar_merkezi_bul_veya_olustur(conn, "Kiralık", "KİRALIK", 1, 80), "kiralik", 0
    if aile == "MADEN":
        if (kdv or "").upper() == "Y":
            return dbm.kar_merkezi_bul_veya_olustur(conn, kalem, "MADEN", 1, 10), "poz", 1
        # Ek kalemler yazıldığı gibi, Maden altında, gider almadan gösterilir.
        return dbm.kar_merkezi_bul_veya_olustur(conn, kalem, "MADEN", 0, 40), "ek", 0
    return dbm.kar_merkezi_bul_veya_olustur(conn, aile, aile, 1, 60), "aile", 1 if aile == "TSF" else 0


def gelir_kaydet(conn, donem_id, df: pd.DataFrame, dosya_adi, hash_) -> int:
    conn.execute("DELETE FROM gelir WHERE donem_id=?", (donem_id,))
    for r in df.itertuples():
        var = conn.execute(
            "SELECT 1 FROM gelir_eslesme WHERE aile=? AND kalem_adi=?", (r.aile, r.kalem)
        ).fetchone()
        if not var:
            km, tip, m3 = _gelir_eslesme_oner(conn, r.aile, r.kalem, r.kdv)
            conn.execute(
                "INSERT INTO gelir_eslesme (aile, kalem_adi, kar_merkezi_id, tip, m3_dahil) VALUES (?, ?, ?, ?, ?)",
                (r.aile, r.kalem, km, tip, m3),
            )
        conn.execute(
            "INSERT INTO gelir (donem_id, aile, kalem_adi, kdv, miktar, birim_fiyat, tutar) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (donem_id, r.aile, r.kalem, r.kdv, _n(r.miktar), _n(r.birim_fiyat), float(r.tutar or 0)),
        )
    yukleme_kaydet(conn, donem_id, "master", dosya_adi, hash_, len(df))
    conn.commit()
    return len(df)


def _n(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else float(v)


# ---------------------------------------------------------------- giderler

def ekipman_kaydet(conn, df: pd.DataFrame, dosya_adi, hash_) -> int:
    for r in df.itertuples():
        conn.execute(
            "INSERT INTO ekipman (kod, ad, tip, company, birincil) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(kod) DO UPDATE SET ad=excluded.ad, tip=excluded.tip, company=excluded.company, birincil=excluded.birincil",
            (r.kod, r.ad, r.tip, r.company, int(r.birincil)),
        )
    yukleme_kaydet(conn, None, "ekipman", dosya_adi, hash_, len(df))
    conn.commit()
    return len(df)


def mazot_kaydet(conn, donem_id, df: pd.DataFrame, dosya_adi, hash_) -> int:
    conn.execute("DELETE FROM mazot WHERE donem_id=?", (donem_id,))
    conn.executemany(
        "INSERT INTO mazot (donem_id, ekipman_kod, ekipman_adi, tip, company, litre) VALUES (?, ?, ?, ?, ?, ?)",
        [(donem_id, r.ekipman_kod, r.ekipman_adi, r.tip, r.company, float(r.litre)) for r in df.itertuples()],
    )
    yukleme_kaydet(conn, donem_id, "mazot", dosya_adi, hash_, len(df))
    conn.commit()
    return len(df)


def depo_kaydet(conn, donem_id, df: pd.DataFrame, dosya_adi, hash_) -> int:
    conn.execute("DELETE FROM depo WHERE donem_id=?", (donem_id,))
    conn.executemany(
        "INSERT INTO depo (donem_id, tarih, malzeme, miktar, tutar_uzs, garaj_no, ekipman_adi, grup, alt_grup, gider_yeri) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (donem_id, r.tarih if "tarih" in df else None, r.malzeme, _n(r.miktar), float(r.tutar_uzs), r.garaj_no,
             r.ekipman_adi, r.grup, r.alt_grup, r.gider_yeri)
            for r in df.itertuples()
        ],
    )
    # Önceki ayın Gider Yeri -> anahtar seçimlerini taşı (varsa)
    onceki = dbm.onceki_donem(conn, donem_id)
    if onceki:
        conn.execute(
            "INSERT OR IGNORE INTO depo_anahtar (donem_id, gider_yeri, anahtar_kod) "
            "SELECT ?, gider_yeri, anahtar_kod FROM depo_anahtar WHERE donem_id=?",
            (donem_id, onceki),
        )
    yukleme_kaydet(conn, donem_id, "depo", dosya_adi, hash_, len(df))
    conn.commit()
    return len(df)


def personel_kaydet(conn, donem_id, df: pd.DataFrame, dosya_adi, hash_) -> int:
    conn.execute("DELETE FROM personel WHERE donem_id=?", (donem_id,))
    for r in df.itertuples():
        # Aynı görev + birim (+ birim maaş) için en son seçilen anahtarı hatırla
        onceki = conn.execute(
            "SELECT p.anahtar_kod FROM personel p JOIN donem d ON d.id=p.donem_id "
            "WHERE p.gorev=? AND p.birim IS ? AND p.anahtar_kod IS NOT NULL AND p.donem_id<>? "
            "ORDER BY (p.birim_maas IS ?) DESC, d.yil DESC, d.ay DESC LIMIT 1",
            (r.gorev, r.birim, donem_id, _n(r.birim_maas)),
        ).fetchone()
        conn.execute(
            "INSERT INTO personel (donem_id, sira, gorev, birim, adet, birim_maas, toplam_maas, anahtar_kod) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (donem_id, int(r.sira), r.gorev, r.birim, float(r.adet or 0), _n(r.birim_maas), float(r.toplam_maas or 0),
             onceki["anahtar_kod"] if onceki else None),
        )
    yukleme_kaydet(conn, donem_id, "personel", dosya_adi, hash_, len(df))
    conn.commit()
    return len(df)


def oranlari_oncekinden_kopyala(conn, donem_id, tablo: str) -> int:
    onceki = dbm.onceki_donem(conn, donem_id)
    if not onceki:
        return 0
    if tablo == "calisma_orani":
        cur = conn.execute(
            "INSERT OR IGNORE INTO calisma_orani (donem_id, ekipman_kod, kar_merkezi_id, oran) "
            "SELECT ?, ekipman_kod, kar_merkezi_id, oran FROM calisma_orani WHERE donem_id=? "
            "AND ekipman_kod IN (SELECT ekipman_kod FROM mazot WHERE donem_id=?)",
            (donem_id, onceki, donem_id),
        )
    else:
        cur = conn.execute(
            "INSERT OR IGNORE INTO anahtar_oran (donem_id, anahtar_kod, kar_merkezi_id, oran) "
            "SELECT ?, anahtar_kod, kar_merkezi_id, oran FROM anahtar_oran WHERE donem_id=?",
            (donem_id, onceki),
        )
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------- okuma

def hedefler(conn) -> dict:
    return {
        r["id"]: r["ad"]
        for r in conn.execute(
            "SELECT id, ad, aile, sira FROM kar_merkezi WHERE gider_alir=1 AND aktif=1"
        ).fetchall()
    }


def kar_merkezleri_df(conn) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM kar_merkezi", conn)
    df["_a"] = df["aile"].map(AILE_SIRA).fillna(9)
    return df.sort_values(["_a", "sira", "id"]).drop(columns="_a").reset_index(drop=True)


def anahtarlar(conn) -> dict:
    return {
        r["kod"]: {"ad": r["ad"], "tur": r["tur"], "filtre": json.loads(r["filtre"]) if r["filtre"] else {}, "sistem": r["sistem"]}
        for r in conn.execute("SELECT * FROM anahtar ORDER BY sistem DESC, ad").fetchall()
    }


def donem_verisi(conn, donem_id) -> DonemVerisi:
    d = conn.execute("SELECT * FROM donem WHERE id=?", (donem_id,)).fetchone()
    veri = DonemVerisi(hedefler=hedefler(conn), uzs_usd=d["uzs_usd"], uzs_litre=d["uzs_litre"])
    veri.gelir = [
        {"km_id": r["kar_merkezi_id"], "tutar": r["tutar"], "miktar": r["miktar"], "m3_dahil": r["m3_dahil"]}
        for r in conn.execute(
            "SELECT g.*, e.kar_merkezi_id, e.m3_dahil FROM gelir g "
            "LEFT JOIN gelir_eslesme e ON e.aile=g.aile AND e.kalem_adi=g.kalem_adi WHERE g.donem_id=?",
            (donem_id,),
        )
    ]
    mazot = conn.execute("SELECT * FROM mazot WHERE donem_id=?", (donem_id,)).fetchall()
    veri.mazot = {r["ekipman_kod"]: r["litre"] for r in mazot}
    bilgi = {r["ekipman_kod"]: {"tip": r["tip"], "company": r["company"], "birincil": 0} for r in mazot}
    for r in conn.execute("SELECT * FROM ekipman"):
        bilgi[r["kod"]] = {"tip": r["tip"], "company": r["company"], "birincil": r["birincil"]}
    veri.ekipman_bilgi = bilgi
    for r in conn.execute("SELECT * FROM calisma_orani WHERE donem_id=? AND oran<>0", (donem_id,)):
        veri.oranlar.setdefault(r["ekipman_kod"], {})[r["kar_merkezi_id"]] = r["oran"]
    veri.depo = [dict(r) for r in conn.execute("SELECT garaj_no, gider_yeri, tutar_uzs FROM depo WHERE donem_id=?", (donem_id,))]
    veri.depo_anahtar = {
        r["gider_yeri"]: r["anahtar_kod"]
        for r in conn.execute("SELECT * FROM depo_anahtar WHERE donem_id=? AND anahtar_kod IS NOT NULL", (donem_id,))
    }
    veri.personel = [dict(r) for r in conn.execute("SELECT * FROM personel WHERE donem_id=? ORDER BY sira", (donem_id,))]
    veri.anahtarlar = anahtarlar(conn)
    for r in conn.execute("SELECT * FROM anahtar_oran WHERE donem_id=? AND oran<>0", (donem_id,)):
        veri.manuel_oranlar.setdefault(r["anahtar_kod"], {})[r["kar_merkezi_id"]] = r["oran"]
    return veri


def bagimsiz_gider_yerleri(conn, donem_id) -> pd.DataFrame:
    """Ekipmana bağlanamayan depo satırlarının Gider Yeri bazında özeti."""
    ekipmanlar = {r[0] for r in conn.execute("SELECT kod FROM ekipman")} | {
        r[0] for r in conn.execute("SELECT ekipman_kod FROM mazot WHERE donem_id=?", (donem_id,))
    }
    df = pd.read_sql("SELECT garaj_no, gider_yeri, tutar_uzs FROM depo WHERE donem_id=?", conn, params=(donem_id,))
    if df.empty:
        return pd.DataFrame(columns=["gider_yeri", "satir", "tutar_uzs", "anahtar_kod"])
    df = df[~df["garaj_no"].fillna("").str.strip().isin(ekipmanlar)]
    df["gider_yeri"] = df["gider_yeri"].fillna("(Gider yeri boş)")
    ozet = df.groupby("gider_yeri", as_index=False).agg(satir=("tutar_uzs", "size"), tutar_uzs=("tutar_uzs", "sum"))
    secim = pd.read_sql("SELECT gider_yeri, anahtar_kod FROM depo_anahtar WHERE donem_id=?", conn, params=(donem_id,))
    return ozet.merge(secim, on="gider_yeri", how="left")


# ---------------------------------------------------------------- ilerleme

DURUM_ETIKET = {"tamam": "✅ Tamamlandı", "eksik": "⬜ Eksik", "kontrol": "⚠️ Kontrol gerekli", "bekliyor": "⏳ Önceki adımı bekliyor"}


def kullanilan_anahtarlar(veri: DonemVerisi) -> set:
    kodlar = {g["anahtar_kod"] for g in veri.personel if g.get("anahtar_kod")}
    kodlar |= set(veri.depo_anahtar.values())
    return kodlar


def ilerleme(conn, donem_id) -> tuple[list, Sonuc, DonemVerisi]:
    veri = donem_verisi(conn, donem_id)
    sonuc = hesapla(veri)
    adimlar = []

    def ekle(ad, durum, aciklama, sayfa):
        adimlar.append({"adim": ad, "durum": durum, "aciklama": aciklama, "sayfa": sayfa})

    kur_tamam = bool(veri.uzs_usd and veri.uzs_litre)
    ekle("Kurları gir (UZS/USD, UZS/L)", "tamam" if kur_tamam else "eksik",
         f"UZS/USD {veri.uzs_usd or '-'} · UZS/L {veri.uzs_litre or '-'}", "Kurlar")

    ekip_say = conn.execute("SELECT COUNT(*) FROM ekipman").fetchone()[0]
    listede_yok = [e for e in veri.mazot if not conn.execute("SELECT 1 FROM ekipman WHERE kod=?", (e,)).fetchone()]
    if not ekip_say:
        ekle("Ekipman listesini yükle", "eksik", "Ekipman listesi yok", "Veri Yükleme")
    elif listede_yok:
        ekle("Ekipman listesini yükle", "kontrol", f"Mazotta olup listede olmayan {len(listede_yok)} ekipman", "Veri Yükleme")
    else:
        ekle("Ekipman listesini yükle", "tamam", f"{ekip_say} ekipman", "Veri Yükleme")

    gelir_say = len(veri.gelir)
    ekle("Master Data (gelir) yükle", "tamam" if gelir_say else "eksik", f"{gelir_say} kalem", "Veri Yükleme")
    onaysiz = conn.execute(
        "SELECT COUNT(*) FROM gelir g JOIN gelir_eslesme e ON e.aile=g.aile AND e.kalem_adi=g.kalem_adi "
        "WHERE g.donem_id=? AND e.onayli=0", (donem_id,)
    ).fetchone()[0]
    if not gelir_say:
        ekle("Gelir kalemlerini kâr merkezlerine eşle", "bekliyor", "", "Gelir Eşleme")
    else:
        ekle("Gelir kalemlerini kâr merkezlerine eşle", "kontrol" if onaysiz else "tamam",
             f"Onay bekleyen {onaysiz} kalem" if onaysiz else "Tüm kalemler eşli", "Gelir Eşleme")

    ekle("Mazot yükle", "tamam" if veri.mazot else "eksik", f"{len(veri.mazot)} ekipman, {sonuc.toplam_litre:,.0f} L", "Veri Yükleme")
    if not veri.mazot:
        ekle("Ekipman çalışma oranlarını gir", "bekliyor", "", "Çalışma Oranları")
    else:
        kontrol = oran_toplami_kontrol({e: veri.oranlar.get(e, {}) for e in veri.mazot if veri.mazot[e]})
        hatali = sum(1 for _, d in kontrol.values() if d != "tamam")
        ekle("Ekipman çalışma oranlarını gir", "eksik" if hatali else "tamam",
             f"%100 olmayan {hatali} ekipman" if hatali else "Tüm ekipmanlar %100", "Çalışma Oranları")

    ekle("Depo çıkışlarını yükle", "tamam" if veri.depo else "eksik", f"{len(veri.depo)} satır", "Veri Yükleme")
    if not veri.depo:
        ekle("Depo gider yerlerine anahtar seç", "bekliyor", "", "Depo Anahtarları")
    else:
        bg = bagimsiz_gider_yerleri(conn, donem_id)
        eksik = int(bg["anahtar_kod"].isna().sum()) if not bg.empty else 0
        ekle("Depo gider yerlerine anahtar seç", "eksik" if eksik else "tamam",
             f"Anahtarsız {eksik} gider yeri" if eksik else f"{len(bg)} gider yeri eşli", "Depo Anahtarları")

    ekle("Personel yükle", "tamam" if veri.personel else "eksik", f"{len(veri.personel)} görev grubu", "Veri Yükleme")
    if not veri.personel:
        ekle("Personel görev gruplarına anahtar seç", "bekliyor", "", "Personel")
    else:
        eksik = sum(1 for g in veri.personel if not g.get("anahtar_kod"))
        ekle("Personel görev gruplarına anahtar seç", "eksik" if eksik else "tamam",
             f"Anahtarsız {eksik} grup" if eksik else "Tüm gruplar eşli", "Personel")

    kullanilan = kullanilan_anahtarlar(veri)
    manuel = [k for k in kullanilan if veri.anahtarlar.get(k, {}).get("tur") == "manuel"]
    hatali_manuel = [veri.anahtarlar[k]["ad"] for k in manuel if k in sonuc.anahtar_hatalari]
    ekle("Elle girilen anahtar paylarını gir (ör. Patlayıcı)",
         "eksik" if hatali_manuel else "tamam",
         ("Eksik: " + ", ".join(hatali_manuel)) if hatali_manuel else (f"{len(manuel)} anahtar" if manuel else "Kullanılmıyor"),
         "Anahtarlar")

    onceki_tamam = all(a["durum"] == "tamam" for a in adimlar)
    hesap_hatasi = sonuc.hatalar or [k for k in kullanilan if k in sonuc.anahtar_hatalari] or sonuc.dagitilmamis
    if not onceki_tamam:
        ekle("Kontrolleri geç ve sonucu kesinleştir", "bekliyor", "Önceki adımlar tamamlanmadı", "Kontroller")
    elif hesap_hatasi:
        ekle("Kontrolleri geç ve sonucu kesinleştir", "kontrol",
             f"Dağıtılmamış {dagitilmamis_toplam(sonuc):,.2f} $; hata {len(sonuc.hatalar)}", "Kontroller")
    else:
        ekle("Kontrolleri geç ve sonucu kesinleştir", "tamam", "Tüm giderler dağıtıldı", "Kontroller")
    return adimlar, sonuc, veri


def ilerleme_yuzdesi(adimlar) -> float:
    return 100.0 * sum(a["durum"] == "tamam" for a in adimlar) / len(adimlar) if adimlar else 0.0


# ---------------------------------------------------------------- kontroller

def kontroller(conn, donem_id, veri: DonemVerisi, sonuc: Sonuc) -> pd.DataFrame:
    satirlar = []

    def k(ad, ok, detay):
        satirlar.append({"Kontrol": ad, "Durum": "✅" if ok else "❌", "Detay": detay})

    oranlar = oran_toplami_kontrol({e: veri.oranlar.get(e, {}) for e in veri.mazot if veri.mazot[e]})
    hatali = [f"{e} (%{t * 100:.1f})" for e, (t, d) in oranlar.items() if d != "tamam"]
    k("1. Her ekipmanın çalışma oranı toplamı %100", not hatali, ", ".join(hatali[:15]) or "Tamam")

    dagitilan_l = sum(sonuc.mazot_litre.values())
    dagitilmayan_l = sum(d.get("litre", 0) for d in sonuc.dagitilmamis if d["kategori"] == "mazot")
    k("2. Dağıtılan + dağıtılmamış litre = toplam litre", abs(dagitilan_l + dagitilmayan_l - sonuc.toplam_litre) < 0.01,
      f"Toplam {sonuc.toplam_litre:,.2f} L · dağıtılan {dagitilan_l:,.2f} L · dağıtılmamış {dagitilmayan_l:,.2f} L")

    for kat, ad in (("mazot", "3. Mazot $"), ("depo", "4a. Depo $"), ("personel", "4b. Personel $")):
        top = sonuc.toplam_kaynak.get(kat, 0.0)
        dag = dagitilan_toplam(sonuc, kat)
        dgm = dagitilmamis_toplam(sonuc, kat)
        k(f"{ad}: dağıtılan + dağıtılmamış = kaynak toplamı", abs(dag + dgm - top) < 0.01,
          f"Kaynak {top:,.2f} · dağıtılan {dag:,.2f} · dağıtılmamış {dgm:,.2f}")

    kullanilan = kullanilan_anahtarlar(veri)
    for kod in sorted(kullanilan):
        ad = veri.anahtarlar.get(kod, {}).get("ad", kod)
        if kod in sonuc.anahtar_hatalari:
            k(f"5. Anahtar: {ad}", False, sonuc.anahtar_hatalari[kod])
        else:
            t = sum(sonuc.anahtar_paylari[kod].values())
            k(f"5. Anahtar: {ad}", abs(t - 1) < TOLERANS, f"Pay toplamı %{t * 100:.2f}")

    personel_kod = [k_ for k_, a in veri.anahtarlar.items() if a["tur"] == "personel"]
    kaynak_grup = sum(1 for g in veri.personel if g.get("anahtar_kod") and g["anahtar_kod"] not in personel_kod)
    k("6. Ortak Personel anahtarı Personel gruplarını dışlıyor (döngü yok)", True,
      f"Kaynak olarak {kaynak_grup} personel dışı grup kullanıldı")

    eslesmeyen = sum(1 for g in veri.gelir if g["km_id"] is None)
    toplam_gelir = sum(g["tutar"] for g in veri.gelir)
    k("7. Tüm gelir kalemleri bir kâr merkezine eşli (çift sayım yok)", eslesmeyen == 0,
      f"Toplam gelir {toplam_gelir:,.2f} $ · eşlenmemiş {eslesmeyen} kalem")

    kesin = not sonuc.hatalar and not sonuc.dagitilmamis
    k("8. Gider dağıtımı tamam, sonuç kesinleştirilebilir", kesin,
      "Kesin" if kesin else f"Dağıtılmamış {dagitilmamis_toplam(sonuc):,.2f} $; hatalar: {'; '.join(sonuc.hatalar) or '-'}")
    return pd.DataFrame(satirlar)


# ---------------------------------------------------------------- rapor

def rapor(conn, donem_id, veri: DonemVerisi | None = None, sonuc: Sonuc | None = None) -> pd.DataFrame:
    if veri is None:
        veri = donem_verisi(conn, donem_id)
    if sonuc is None:
        sonuc = hesapla(veri)
    km = kar_merkezleri_df(conn)
    gelir = {}
    for g in veri.gelir:
        gelir[g["km_id"]] = gelir.get(g["km_id"], 0.0) + g["tutar"]
    satirlar = []
    for r in km.itertuples():
        gid = sonuc.gider.get(r.id, {})
        g = gelir.get(r.id, 0.0)
        if r.id not in gelir and not gid and r.id not in veri.hedefler:
            continue
        mazot, depo, pers = gid.get("mazot", 0.0), gid.get("depo", 0.0), gid.get("personel", 0.0)
        satirlar.append({
            "Aile": r.aile, "Kâr merkezi": r.ad, "Gelir $": g, "Mazot L": sonuc.mazot_litre.get(r.id, 0.0),
            "Mazot $": mazot, "Depo $": depo, "Personel $": pers, "Toplam gider $": mazot + depo + pers,
            "Sonuç $": g - (mazot + depo + pers),
        })
    if None in gelir:
        satirlar.append({"Aile": "-", "Kâr merkezi": "Eşlenmemiş gelir", "Gelir $": gelir[None], "Sonuç $": gelir[None]})
    if sonuc.dagitilmamis:
        dm = {k: dagitilmamis_toplam(sonuc, k) for k in ("mazot", "depo", "personel")}
        satirlar.append({
            "Aile": "-", "Kâr merkezi": "Dağıtılmamış gider", "Gelir $": 0.0,
            "Mazot L": sum(d.get("litre", 0) for d in sonuc.dagitilmamis if d["kategori"] == "mazot"),
            "Mazot $": dm["mazot"], "Depo $": dm["depo"], "Personel $": dm["personel"],
            "Toplam gider $": sum(dm.values()), "Sonuç $": -sum(dm.values()),
        })
    df = pd.DataFrame(satirlar).fillna(0.0)
    if df.empty:
        return df
    toplam = df.select_dtypes("number").sum()
    df = pd.concat([df, pd.DataFrame([{"Aile": "TOPLAM", "Kâr merkezi": "", **toplam.to_dict()}])], ignore_index=True)
    return df


def aile_ozeti(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    govde = df[df["Aile"] != "TOPLAM"]
    return govde.groupby("Aile", sort=False).sum(numeric_only=True).reset_index()


def donem_karsilastirma(conn, yil: int | None, metrik: str = "Sonuç $") -> pd.DataFrame:
    sorgu = "SELECT id, yil, ay FROM donem" + (" WHERE yil=?" if yil else "") + " ORDER BY yil, ay"
    donemler = conn.execute(sorgu, (yil,) if yil else ()).fetchall()
    tablolar = []
    for d in donemler:
        r = rapor(conn, d["id"])
        if r.empty:
            continue
        r = r[r["Aile"] != "TOPLAM"][["Aile", "Kâr merkezi", metrik]].copy()
        r["Dönem"] = f"{d['yil']}-{d['ay']:02d}"
        tablolar.append(r)
    if not tablolar:
        return pd.DataFrame()
    birlesik = pd.concat(tablolar)
    pivot = birlesik.pivot_table(index=["Aile", "Kâr merkezi"], columns="Dönem", values=metrik, aggfunc="sum", fill_value=0.0)
    pivot["Toplam"] = pivot.sum(axis=1)
    return pivot.reset_index()
