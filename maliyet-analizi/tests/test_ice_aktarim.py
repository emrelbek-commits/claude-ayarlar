import pytest

from core import db as dbm
from core import importers as imp
from core import servis
from ornek_veri import uret


@pytest.fixture(scope="module")
def dosyalar(tmp_path_factory):
    return uret(tmp_path_factory.mktemp("ornek"))


@pytest.fixture
def conn(tmp_path):
    return dbm.baglan(tmp_path / "test.db")


def test_sayi_turk_formati():
    assert imp.sayi("1.010.248,00") == 1010248.0
    assert imp.sayi("2.939.821,68") == pytest.approx(2939821.68)
    assert imp.sayi("UZS 566.100,00") == 566100.0
    assert imp.sayi("-") is None
    assert imp.sayi(12.5) == 12.5


def test_ay_numarasi():
    assert imp.ay_numarasi("Eylül") == 9
    assert imp.ay_numarasi("EYLÜL") == 9
    assert imp.ay_numarasi(10) == 10


def test_master_oku(dosyalar):
    df, bilgi = imp.master_oku(dosyalar["master"])
    eylul = df[(df.yil == 2026) & (df.ay == 9)]
    assert len(eylul) == 19
    assert eylul["tutar"].sum() == pytest.approx(sum(r[6] for r in __import__("ornek_veri").MASTER if r[0] == "Eylül"))
    assert bilgi["sutunlar"]["tutar"] == "KDV'siz"


def test_mazot_oku_ay_filtreli_ekipman_toplami(dosyalar):
    df, bilgi = imp.mazot_oku(dosyalar["mazot"], 2026, 9)
    satir = df.set_index("ekipman_kod").loc["11-002"]
    assert satir["litre"] == 218 + 247  # Ekim satırı dahil değil
    assert (2026, 10) in bilgi["bulunan_aylar"]


def test_depo_oku_rusca_basliklar(dosyalar):
    df, _ = imp.depo_oku(dosyalar["depo"], 2026, 9)
    assert len(df) == 8
    assert df["tutar_uzs"].sum() == pytest.approx(sum(r[7] for r in __import__("ornek_veri").DEPO))


def test_personel_oku_bos_satir_atlanir_ve_sutun_yeri_onemsiz(dosyalar):
    df, bilgi = imp.personel_oku(dosyalar["personel"])
    assert len(df) == 13
    assert bilgi["atlanan_satir"] == 1
    assert df.iloc[0]["gorev"].startswith("Burg'ulash")


def test_eksik_baslik_anlasilir_hata(tmp_path):
    from openpyxl import Workbook
    wb = Workbook(); wb.active.append(["a", "b"]); yol = tmp_path / "x.xlsx"; wb.save(yol)
    with pytest.raises(imp.IceAktarimHatasi, match="Başlık satırı bulunamadı"):
        imp.master_oku(yol)


def _hepsini_yukle(conn, dosyalar):
    d = dbm.donem_getir_veya_olustur(conn, 2026, 9)
    conn.execute("UPDATE donem SET uzs_usd=12000, uzs_litre=14000 WHERE id=?", (d,))
    m, _ = imp.master_oku(dosyalar["master"])
    servis.gelir_kaydet(conn, d, m[(m.yil == 2026) & (m.ay == 9)], "m", "h1")
    servis.ekipman_kaydet(conn, imp.ekipman_oku(dosyalar["ekipman"])[0], "e", "h2")
    servis.mazot_kaydet(conn, d, imp.mazot_oku(dosyalar["mazot"], 2026, 9)[0], "z", "h3")
    servis.depo_kaydet(conn, d, imp.depo_oku(dosyalar["depo"], 2026, 9)[0], "d", "h4")
    servis.personel_kaydet(conn, d, imp.personel_oku(dosyalar["personel"])[0], "p", "h5")
    return d


def test_gelir_eslesme_onerileri(conn, dosyalar):
    _hepsini_yukle(conn, dosyalar)
    es = {(r["aile"], r["kalem_adi"]): r for r in conn.execute(
        "SELECT e.*, k.ad, k.gider_alir FROM gelir_eslesme e JOIN kar_merkezi k ON k.id=e.kar_merkezi_id")}
    assert es[("MADEN", "Kiralık")]["ad"] == "Kiralık"
    assert es[("TSF", "Kiralık")]["ad"] == "Kiralık"
    assert es[("MADEN", "Elektrik")]["tip"] == "ek" and es[("MADEN", "Elektrik")]["gider_alir"] == 0
    assert es[("MADEN", "Yükleme-1 km'ye kadar Taşıma-Depolama")]["tip"] == "poz"
    assert es[("TSF", "Diğer")]["ad"] == "TSF"
    assert es[("RC", "RC-3 EPİROC D65")]["ad"] == "RC"
    assert es[("TSF", "TSF Faz 2 Dolgu")]["m3_dahil"] == 1


def test_uctan_uca_tam_dagitim_ve_uzlasma(conn, dosyalar):
    d = _hepsini_yukle(conn, dosyalar)
    hedef = {ad: i for i, ad in servis.hedefler(conn).items()}
    poz1 = hedef["Delme-Patlatma-Kazı-Yükleme-3.5 km'ye kadar Taşıma -Depolama"]
    # Her ekipman yarı Poz1, yarı TSF çalışsın
    for (kod,) in conn.execute("SELECT ekipman_kod FROM mazot WHERE donem_id=?", (d,)).fetchall():
        conn.execute("INSERT INTO calisma_orani VALUES (?, ?, ?, 0.5)", (d, kod, poz1))
        conn.execute("INSERT INTO calisma_orani VALUES (?, ?, ?, 0.5)", (d, kod, hedef["TSF"]))
    for (yer,) in conn.execute("SELECT DISTINCT gider_yeri FROM depo WHERE donem_id=?", (d,)).fetchall():
        conn.execute("INSERT INTO depo_anahtar VALUES (?, ?, 'M3')", (d, yer))
    conn.execute("UPDATE personel SET anahtar_kod='KAMYON' WHERE donem_id=? AND gorev LIKE '%Kamyon%'", (d,))
    conn.execute("UPDATE personel SET anahtar_kod='PERSONEL' WHERE donem_id=? AND anahtar_kod IS NULL", (d,))
    conn.execute("UPDATE gelir_eslesme SET onayli=1")
    conn.commit()

    adimlar, sonuc, veri = servis.ilerleme(conn, d)
    assert [a["durum"] for a in adimlar] == ["tamam"] * len(adimlar), adimlar
    assert servis.ilerleme_yuzdesi(adimlar) == 100
    assert not sonuc.dagitilmamis

    r = servis.rapor(conn, d, veri, sonuc)
    toplam = r[r["Aile"] == "TOPLAM"].iloc[0]
    toplam_gider = sum(sonuc.toplam_kaynak.values())
    assert toplam["Gelir $"] == pytest.approx(sum(g["tutar"] for g in veri.gelir))
    assert toplam["Toplam gider $"] == pytest.approx(toplam_gider)
    assert toplam["Sonuç $"] == pytest.approx(toplam["Gelir $"] - toplam_gider)
    # Personel anahtarı: tüm kaynak (Kamyon) Poz1/TSF yarı yarıya -> Personel de 0.5/0.5
    assert sonuc.anahtar_paylari["PERSONEL"] == pytest.approx({poz1: 0.5, hedef["TSF"]: 0.5})
    k = servis.kontroller(conn, d, veri, sonuc)
    assert (k["Durum"] == "✅").all(), k


def test_eksik_veride_rapor_taslak_ve_ilerleme(conn, dosyalar):
    d = _hepsini_yukle(conn, dosyalar)
    adimlar, sonuc, _ = servis.ilerleme(conn, d)
    durum = {a["adim"]: a["durum"] for a in adimlar}
    assert durum["Ekipman çalışma oranlarını gir"] == "eksik"
    assert durum["Kontrolleri geç ve sonucu kesinleştir"] == "bekliyor"
    assert sonuc.dagitilmamis
    assert 0 < servis.ilerleme_yuzdesi(adimlar) < 100


def test_ayni_ay_tekrar_yuklenince_mukerrer_olmaz(conn, dosyalar):
    d = _hepsini_yukle(conn, dosyalar)
    m, _ = imp.master_oku(dosyalar["master"])
    servis.gelir_kaydet(conn, d, m[(m.yil == 2026) & (m.ay == 9)], "m", "h1")
    assert conn.execute("SELECT COUNT(*) FROM gelir WHERE donem_id=?", (d,)).fetchone()[0] == 19
    assert servis.ayni_dosya_yuklu_mu(conn, d, "master", "h1")


def test_personel_anahtari_sonraki_aya_tasinir(conn, dosyalar):
    d = _hepsini_yukle(conn, dosyalar)
    conn.execute("UPDATE personel SET anahtar_kod='M3' WHERE donem_id=?", (d,)); conn.commit()
    d2 = dbm.donem_getir_veya_olustur(conn, 2026, 10)
    servis.personel_kaydet(conn, d2, imp.personel_oku(dosyalar["personel"])[0], "p", "h6")
    assert conn.execute("SELECT COUNT(*) FROM personel WHERE donem_id=? AND anahtar_kod='M3'", (d2,)).fetchone()[0] == 13
