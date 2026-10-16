import pytest

from core.engine import DonemVerisi, dagitilan_toplam, dagitilmamis_toplam, hesapla, personel_ortak_anahtari

P1, P2, TSF = 1, 2, 3
HEDEF = {P1: "Poz 1", P2: "Poz 2", TSF: "TSF"}
ANAHTARLAR = {
    "MOTORIN": {"ad": "Motorin", "tur": "motorin"},
    "KAMYON": {"ad": "Kamyon", "tur": "ekipman", "filtre": {"company": ["Pitworks"], "tipler": ["KAMYON"]}},
    "PATLAYICI": {"ad": "Patlayıcı", "tur": "manuel"},
    "PERSONEL": {"ad": "Personel", "tur": "personel"},
}


def veri(**kw):
    v = DonemVerisi(hedefler=HEDEF, uzs_usd=12000.0, uzs_litre=12000.0, anahtarlar=ANAHTARLAR)
    for k, d in kw.items():
        setattr(v, k, d)
    return v


def test_brif_mazot_ornegi():
    # Kamyon 5.000 L; Poz1 %60, Poz2 %25, TSF %15 -> 3.000 / 1.250 / 750 L
    s = hesapla(veri(mazot={"DT-01": 5000}, oranlar={"DT-01": {P1: 0.6, P2: 0.25, TSF: 0.15}}))
    assert s.mazot_litre[P1] == pytest.approx(3000)
    assert s.mazot_litre[P2] == pytest.approx(1250)
    assert s.mazot_litre[TSF] == pytest.approx(750)
    # 1 L = 12.000 UZS, 1 $ = 12.000 UZS -> 1 $/L
    assert s.gider[P1]["mazot"] == pytest.approx(3000)
    assert not s.dagitilmamis


def test_eksik_oran_dagitilmamis_kalir_esit_dagitilmaz():
    s = hesapla(veri(mazot={"A": 1000, "B": 500}, oranlar={"A": {P1: 0.8}}))
    assert s.mazot_litre[P1] == pytest.approx(800)
    assert sum(d["litre"] for d in s.dagitilmamis) == pytest.approx(200 + 500)
    assert P2 not in s.mazot_litre


def test_fazla_oran_dagitilmaz():
    s = hesapla(veri(mazot={"A": 1000}, oranlar={"A": {P1: 0.8, P2: 0.4}}))
    assert not s.mazot_litre
    assert s.dagitilmamis[0]["litre"] == pytest.approx(1000)


def test_kur_yoksa_hata():
    v = veri(mazot={"A": 100}, oranlar={"A": {P1: 1.0}})
    v.uzs_litre = None
    s = hesapla(v)
    assert s.mazot_litre[P1] == pytest.approx(100)
    assert any("UZS/L" in h for h in s.hatalar)


def test_brif_personel_ornegi_manuel_anahtar():
    # 10.000 $ grup gideri, 40/30/20/10 -> 4.000 / 3.000 / 2.000 / 1.000 (burada 3 merkez)
    v = veri(
        manuel_oranlar={"PATLAYICI": {P1: 0.4, P2: 0.4, TSF: 0.2}},
        personel=[{"id": 1, "gorev": "Patlatma", "adet": 2, "toplam_maas": 10000 * 12000, "anahtar_kod": "PATLAYICI"}],
    )
    s = hesapla(v)
    assert s.gider[P1]["personel"] == pytest.approx(4000)
    assert s.gider[TSF]["personel"] == pytest.approx(2000)


def test_ortak_personel_anahtari_adet_ile_agirliklanir():
    paylar = {"K1": {P1: 1.0}, "K2": {P1: 0.5, P2: 0.5}}
    anahtarlar = {"K1": {"tur": "manuel"}, "K2": {"tur": "manuel"}, "PERSONEL": {"tur": "personel"}}
    personel = [
        {"gorev": "A", "adet": 2, "toplam_maas": 999999, "anahtar_kod": "K1"},
        {"gorev": "B", "adet": 3, "toplam_maas": 1, "anahtar_kod": "K2"},
        {"gorev": "C", "adet": 50, "toplam_maas": 1000, "anahtar_kod": "PERSONEL"},  # kendini beslemez
    ]
    w, hata = personel_ortak_anahtari(personel, anahtarlar, paylar, {})
    assert hata is None
    # K_p1 = 2*1 + 3*0.5 = 3.5 ; K_p2 = 1.5 -> 0.7 / 0.3 (maaş tutarı etkisiz)
    assert w[P1] == pytest.approx(0.7)
    assert w[P2] == pytest.approx(0.3)


def test_personel_anahtari_maasi_dagitir():
    v = veri(
        manuel_oranlar={"PATLAYICI": {P1: 1.0}},
        mazot={"A": 100}, oranlar={"A": {P2: 1.0}},
        personel=[
            {"id": 1, "gorev": "Patlatmacı", "adet": 1, "toplam_maas": 0, "anahtar_kod": "PATLAYICI"},
            {"id": 2, "gorev": "Yakıtçı", "adet": 3, "toplam_maas": 0, "anahtar_kod": "MOTORIN"},
            {"id": 3, "gorev": "Müdür", "adet": 1, "toplam_maas": 1000 * 12000, "anahtar_kod": "PERSONEL"},
        ],
    )
    s = hesapla(v)
    assert s.anahtar_paylari["PERSONEL"] == pytest.approx({P1: 0.25, P2: 0.75})
    assert s.gider[P1]["personel"] == pytest.approx(250)
    assert s.gider[P2]["personel"] == pytest.approx(750)


def test_personel_anahtari_payda_sifirsa_hata_ve_dagitilmamis():
    v = veri(personel=[{"id": 1, "gorev": "Müdür", "adet": 1, "toplam_maas": 12000, "anahtar_kod": "PERSONEL"}])
    s = hesapla(v)
    assert "PERSONEL" in s.anahtar_hatalari
    assert dagitilmamis_toplam(s, "personel") == pytest.approx(1)
    assert dagitilan_toplam(s, "personel") == 0


def test_kamyon_anahtari_filtre_ve_sayi():
    v = veri(
        mazot={"T1": 100, "T2": 900, "R1": 50, "E1": 10},
        ekipman_bilgi={
            "T1": {"company": "Pitworks", "tip": "KAMYON"},
            "T2": {"company": "Pitworks", "tip": "KAMYON"},
            "R1": {"company": "Rental", "tip": "KAMYON"},
            "E1": {"company": "Pitworks", "tip": "ESKAVATOR"},
        },
        oranlar={"T1": {P1: 1.0}, "T2": {P1: 0.5, TSF: 0.5}, "R1": {TSF: 1.0}, "E1": {P2: 1.0}},
    )
    s = hesapla(v)
    # Litreden bağımsız: her kamyon 1 sayılır -> P1 1.5/2, TSF 0.5/2
    assert s.anahtar_paylari["KAMYON"] == pytest.approx({P1: 0.75, TSF: 0.25})


def test_depo_ekipmana_bagli_ve_bagimsiz():
    v = veri(
        mazot={"T1": 100},
        oranlar={"T1": {P1: 0.5, P2: 0.5}},
        depo=[
            {"garaj_no": "T1", "gider_yeri": "KAMYON SARF", "tutar_uzs": 12000 * 10},
            {"garaj_no": "ATÖLYE", "gider_yeri": "ATÖLYE SARF", "tutar_uzs": 12000 * 20},
            {"garaj_no": "İSG", "gider_yeri": "İSG SARF", "tutar_uzs": 12000 * 5},
        ],
        depo_anahtar={"ATÖLYE SARF": "MOTORIN"},
    )
    s = hesapla(v)
    assert s.gider[P1]["depo"] == pytest.approx(5 + 10)
    assert s.gider[P2]["depo"] == pytest.approx(5 + 10)
    assert dagitilmamis_toplam(s, "depo") == pytest.approx(5)
    assert s.toplam_kaynak["depo"] == pytest.approx(35)


def test_manuel_anahtar_toplami_100_degilse_hata():
    v = veri(manuel_oranlar={"PATLAYICI": {P1: 0.5}})
    s = hesapla(v)
    assert "PATLAYICI" in s.anahtar_hatalari
