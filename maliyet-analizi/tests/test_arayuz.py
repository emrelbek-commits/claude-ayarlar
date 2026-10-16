"""Her sayfanın örnek verilerle hatasız açıldığını doğrular (Streamlit AppTest)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from core import db as dbm
from core import importers as imp
from core import servis
from ornek_veri import uret

APP = str(Path(__file__).parent.parent / "app.py")
SAYFALAR = ["Genel Bakış", "Ay Paneli", "Kurlar", "Veri Yükleme", "Gelir Eşleme", "Çalışma Oranları", "Anahtarlar",
            "Depo Anahtarları", "Personel", "Kontroller", "Rapor", "Kâr Merkezleri"]


@pytest.fixture(scope="module")
def veri_klasoru(tmp_path_factory):
    kok = tmp_path_factory.mktemp("veri")
    dosyalar = uret(kok / "ornek")
    conn = dbm.baglan(kok / "maliyet.db")
    d = dbm.donem_getir_veya_olustur(conn, 2026, 9)
    conn.execute("UPDATE donem SET uzs_usd=12000, uzs_litre=14000 WHERE id=?", (d,))
    m, _ = imp.master_oku(dosyalar["master"])
    servis.gelir_kaydet(conn, d, m[m.ay == 9], "m", "1")
    servis.ekipman_kaydet(conn, imp.ekipman_oku(dosyalar["ekipman"])[0], "e", "2")
    servis.mazot_kaydet(conn, d, imp.mazot_oku(dosyalar["mazot"], 2026, 9)[0], "z", "3")
    servis.depo_kaydet(conn, d, imp.depo_oku(dosyalar["depo"], 2026, 9)[0], "d", "4")
    servis.personel_kaydet(conn, d, imp.personel_oku(dosyalar["personel"])[0], "p", "5")
    conn.close()
    return kok


@pytest.mark.parametrize("sayfa", SAYFALAR)
def test_sayfa_acilir(sayfa, veri_klasoru, monkeypatch):
    monkeypatch.setenv("MALIYET_VERI", str(veri_klasoru))
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["sayfa"] = sayfa
    at.run()
    assert not at.exception, [e.message for e in at.exception]
