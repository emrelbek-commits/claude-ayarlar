"""Maliyet Analizi: Streamlit arayüzü.  Çalıştırma:  streamlit run app.py"""
import io
import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from core import db as dbm
from core import importers as imp
from core import servis
from core.engine import TOLERANS

KLASOR = Path(__file__).parent
VERI = Path(os.environ.get("MALIYET_VERI", KLASOR / "data"))
SAYFALAR = [
    "Genel Bakış", "Ay Paneli", "Kurlar", "Veri Yükleme", "Gelir Eşleme", "Çalışma Oranları",
    "Anahtarlar", "Depo Anahtarları", "Personel", "Kontroller", "Rapor", "Kâr Merkezleri",
]

st.set_page_config(page_title="Maliyet Analizi", page_icon="📊", layout="wide")


@st.cache_resource
def baglanti():
    return dbm.baglan(VERI / "maliyet.db")


conn = baglanti()


def para(x):
    return f"{x:,.2f}"


def arsivle(donem_txt, kaynak, dosya):
    hedef = VERI / "arsiv" / donem_txt
    hedef.mkdir(parents=True, exist_ok=True)
    (hedef / f"{kaynak}_{datetime.now():%Y%m%d_%H%M%S}_{dosya.name}").write_bytes(dosya.getvalue())


def km_etiketleri(sadece_hedef=False):
    df = servis.kar_merkezleri_df(conn)
    if sadece_hedef:
        df = df[(df.gider_alir == 1) & (df.aktif == 1)]
    return {r.id: f"{r.aile} · {r.ad}" for r in df.itertuples()}


# ---------------------------------------------------------------- kenar çubuğu

donemler = conn.execute("SELECT id, yil, ay FROM donem ORDER BY yil DESC, ay DESC").fetchall()
st.sidebar.title("📊 Maliyet Analizi")
if "sayfa" not in st.session_state:
    st.session_state.sayfa = "Genel Bakış"
sayfa = st.sidebar.radio("Sayfa", SAYFALAR, key="sayfa")
donem_id = None
if donemler:
    secenek = {d["id"]: f"{imp.AYLAR[d['ay'] - 1]} {d['yil']}" for d in donemler}
    donem_id = st.sidebar.selectbox("Dönem", list(secenek), format_func=secenek.get, key="donem")
else:
    st.sidebar.info("Önce Genel Bakış'tan bir dönem oluştur.")


def donem_gerekli():
    if donem_id is None:
        st.warning("Önce bir dönem oluştur (Genel Bakış).")
        st.stop()


# ---------------------------------------------------------------- sayfalar

def genel_bakis():
    st.header("Dönemler")
    satirlar = []
    for d in donemler:
        adimlar, sonuc, veri = servis.ilerleme(conn, d["id"])
        r = servis.rapor(conn, d["id"], veri, sonuc)
        top = r[r["Aile"] == "TOPLAM"].iloc[0] if not r.empty else None
        satirlar.append({
            "Dönem": f"{imp.AYLAR[d['ay'] - 1]} {d['yil']}",
            "İlerleme %": servis.ilerleme_yuzdesi(adimlar),
            "Sıradaki adım": next((a["adim"] for a in adimlar if a["durum"] != "tamam"), "—"),
            "Gelir $": top["Gelir $"] if top is not None else 0.0,
            "Gider $": top["Toplam gider $"] if top is not None else 0.0,
            "Sonuç $": top["Sonuç $"] if top is not None else 0.0,
        })
    if satirlar:
        st.dataframe(
            pd.DataFrame(satirlar), hide_index=True, width="stretch",
            column_config={"İlerleme %": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%"),
                           **{c: st.column_config.NumberColumn(format="%,.2f") for c in ("Gelir $", "Gider $", "Sonuç $")}},
        )
    st.subheader("Yeni dönem")
    c1, c2, c3 = st.columns([1, 1, 1])
    yil = c1.number_input("Yıl", 2020, 2100, datetime.now().year)
    ay = c2.selectbox("Ay", range(1, 13), index=datetime.now().month - 1, format_func=lambda a: imp.AYLAR[a - 1])
    if c3.button("Dönem oluştur", type="primary"):
        dbm.donem_getir_veya_olustur(conn, int(yil), int(ay))
        st.rerun()


def ay_paneli():
    donem_gerekli()
    adimlar, sonuc, _ = servis.ilerleme(conn, donem_id)
    yuzde = servis.ilerleme_yuzdesi(adimlar)
    st.header(f"{servis.donem_adi(conn, donem_id)} · %{yuzde:.0f}")
    st.progress(yuzde / 100)
    sirada = next((a for a in adimlar if a["durum"] != "tamam"), None)
    if sirada:
        st.info(f"**Sıradaki adım:** {sirada['adim']} ({sirada['aciklama'] or servis.DURUM_ETIKET[sirada['durum']]})")
        st.button(f"{sirada['sayfa']} sayfasına git", on_click=lambda: st.session_state.update(sayfa=sirada["sayfa"]))
    else:
        st.success("Bu dönem tamamlandı. Sonuçlar kesin.")
    st.dataframe(
        pd.DataFrame([{"Adım": a["adim"], "Durum": servis.DURUM_ETIKET[a["durum"]], "Açıklama": a["aciklama"], "Sayfa": a["sayfa"]}
                      for a in adimlar]),
        hide_index=True, width="stretch",
    )


def kurlar():
    donem_gerekli()
    st.header(f"Kurlar · {servis.donem_adi(conn, donem_id)}")
    d = conn.execute("SELECT * FROM donem WHERE id=?", (donem_id,)).fetchone()
    with st.form("kur"):
        uzs_usd = st.number_input("1 USD = ? UZS", min_value=0.0, value=float(d["uzs_usd"] or 0), step=1.0, format="%.2f")
        uzs_l = st.number_input("1 litre mazot = ? UZS", min_value=0.0, value=float(d["uzs_litre"] or 0), step=1.0, format="%.2f")
        if st.form_submit_button("Kaydet", type="primary"):
            conn.execute("UPDATE donem SET uzs_usd=?, uzs_litre=? WHERE id=?", (uzs_usd or None, uzs_l or None, donem_id))
            conn.commit()
            st.success("Kaydedildi.")
    if d["uzs_usd"] and d["uzs_litre"]:
        st.caption(f"Mazot litre maliyeti: {d['uzs_litre'] / d['uzs_usd']:.4f} $/L")


def _yukleme_bolumu(kaynak, baslik, okuyucu, kaydedici, donemli=True):
    st.subheader(baslik)
    dosya = st.file_uploader(f"{baslik} Excel dosyası", type=["xlsx", "xlsm", "xls"], key=f"up_{kaynak}")
    if not dosya:
        return
    icerik = dosya.getvalue()
    h = imp.dosya_hash(icerik)
    try:
        df, bilgi = okuyucu(io.BytesIO(icerik))
    except imp.IceAktarimHatasi as e:
        st.error(str(e))
        return
    st.caption(f"Sayfa: **{bilgi['sayfa']}** · başlık satırı {bilgi['baslik_satiri']} · "
               + ", ".join(f"{k} ← '{v}'" for k, v in bilgi["sutunlar"].items()))
    for anahtar, mesaj in (("atlanan_satir", "boş/geçersiz satır atlandı"), ("donem_disi_satir", "satır başka aya ait, alınmadı"),
                           ("kodsuz_satir", "satırda ekipman kodu yok, alınmadı")):
        if bilgi.get(anahtar):
            st.warning(f"{bilgi[anahtar]} {mesaj}")
    for anahtar, mesaj in (("cakisan_kodlar", "Aynı kod birden fazla şirkette"), ("tekrar_eden_kod", "Tekrar eden kod"),
                           ("toplam_uyusmayan", "Adet × Birim Maaş ≠ Toplam Maaş")):
        if bilgi.get(anahtar):
            st.warning(f"{mesaj}: {', '.join(map(str, bilgi[anahtar][:10]))}")
    if df.empty:
        st.error("Bu dönem için satır bulunamadı." + (f" Dosyadaki aylar: {bilgi.get('bulunan_aylar')}" if bilgi.get("bulunan_aylar") else ""))
        return
    st.dataframe(df.head(200), width="stretch", hide_index=True)
    hedef = donem_id if donemli else None
    if servis.ayni_dosya_yuklu_mu(conn, hedef, kaynak, h):
        st.info("Bu dosya bu dönem için zaten yüklü. Tekrar kaydetmek veriyi değiştirmez.")
    if st.button(f"{len(df)} satırı kaydet", key=f"kaydet_{kaynak}", type="primary"):
        n = kaydedici(df, dosya.name, h)
        arsivle(servis.donem_adi(conn, donem_id) if donemli else "genel", kaynak, dosya)
        st.success(f"{n} satır kaydedildi. Bu kaynağın bu dönemdeki önceki verisi yenisiyle değiştirildi.")


def veri_yukleme():
    donem_gerekli()
    d = conn.execute("SELECT yil, ay FROM donem WHERE id=?", (donem_id,)).fetchone()
    st.header(f"Veri yükleme · {servis.donem_adi(conn, donem_id)}")
    st.caption("Kaynak Excel dosyaları değiştirilmez; bir kopyası data/arsiv klasöründe saklanır. "
               "Aynı kaynağı aynı dönem için tekrar yüklemek eskisinin yerine geçer (mükerrer kayıt oluşmaz).")
    sekmeler = st.tabs(["Master Data (gelir)", "Mazot", "Depo", "Personel", "Ekipman listesi"])
    with sekmeler[0]:
        st.subheader("Master Data")
        dosya = st.file_uploader("Master Data Excel dosyası", type=["xlsx", "xlsm", "xls"], key="up_master")
        if dosya:
            icerik = dosya.getvalue()
            try:
                df, bilgi = imp.master_oku(io.BytesIO(icerik))
            except imp.IceAktarimHatasi as e:
                st.error(str(e))
            else:
                aylar = sorted({(int(y), int(a)) for y, a in zip(df.yil, df.ay)})
                st.caption(f"Dosyadaki aylar: {', '.join(f'{imp.AYLAR[a - 1]} {y}' for y, a in aylar)}")
                tum = st.checkbox("Dosyadaki tüm ayları yükle (her ay kendi dönemine)")
                secilen = aylar if tum else [(d["yil"], d["ay"])]
                parca = df[[(y, a) in secilen for y, a in zip(df.yil, df.ay)]]
                if parca.empty:
                    st.error("Seçili dönem dosyada yok.")
                else:
                    st.dataframe(parca[["donem", "yil", "aile", "kdv", "kalem", "miktar", "birim_fiyat", "tutar"]],
                                 hide_index=True, width="stretch")
                    st.metric("KDV'siz toplam $", para(parca["tutar"].sum()))
                    h = imp.dosya_hash(icerik)
                    if st.button(f"{len(parca)} satırı kaydet", type="primary", key="kaydet_master"):
                        for y, a in secilen:
                            did = dbm.donem_getir_veya_olustur(conn, y, a)
                            servis.gelir_kaydet(conn, did, parca[(parca.yil == y) & (parca.ay == a)], dosya.name, h)
                            arsivle(servis.donem_adi(conn, did), "master", dosya)
                        st.success("Kaydedildi. Yeni kalemler için Gelir Eşleme sayfasını kontrol et.")
    with sekmeler[1]:
        _yukleme_bolumu("mazot", "Mazot", lambda f: imp.mazot_oku(f, d["yil"], d["ay"]),
                        lambda df, ad, h: servis.mazot_kaydet(conn, donem_id, df, ad, h))
    with sekmeler[2]:
        _yukleme_bolumu("depo", "Depo çıkışları", lambda f: imp.depo_oku(f, d["yil"], d["ay"]),
                        lambda df, ad, h: servis.depo_kaydet(conn, donem_id, df, ad, h))
    with sekmeler[3]:
        st.caption("Maaşlar UZS olarak okunur.")
        _yukleme_bolumu("personel", "Personel", imp.personel_oku,
                        lambda df, ad, h: servis.personel_kaydet(conn, donem_id, df, ad, h))
    with sekmeler[4]:
        st.caption("Ekipman listesi tüm dönemler için ortaktır; aynı kod tekrar gelirse güncellenir.")
        _yukleme_bolumu("ekipman", "Ekipman listesi", imp.ekipman_oku,
                        lambda df, ad, h: servis.ekipman_kaydet(conn, df, ad, h), donemli=False)
        mevcut = pd.read_sql("SELECT * FROM ekipman ORDER BY company, tip, kod", conn)
        if not mevcut.empty:
            st.markdown(f"**Kayıtlı ekipman: {len(mevcut)}**")
            st.dataframe(mevcut, hide_index=True, width="stretch")


def gelir_esleme():
    st.header("Gelir eşleme")
    st.caption("Master Data kalemlerinin hangi kâr merkezine yazılacağı. Yeni kalemler otomatik önerilir; kontrol edip "
               "'Onaylı' kutusunu işaretle. Maden ek kalemleri (Diğer, Elektrik, Yemek…) yazıldığı gibi, gider almadan gösterilir.")
    etiket = km_etiketleri()
    df = pd.read_sql("SELECT aile, kalem_adi, kar_merkezi_id, tip, m3_dahil, onayli FROM gelir_eslesme ORDER BY aile, kalem_adi", conn)
    if df.empty:
        st.info("Henüz Master Data yüklenmedi.")
        return
    df["Kâr merkezi"] = df["kar_merkezi_id"].map(etiket)
    df["m3_dahil"] = df["m3_dahil"].astype(bool)
    df["onayli"] = df["onayli"].astype(bool)
    duzen = st.data_editor(
        df.drop(columns="kar_merkezi_id"), hide_index=True, width="stretch", disabled=["aile", "kalem_adi"],
        column_config={
            "aile": "Aile", "kalem_adi": "Master Data kalemi",
            "Kâr merkezi": st.column_config.SelectboxColumn(options=list(etiket.values()), required=True),
            "tip": st.column_config.SelectboxColumn("Tip", options=["poz", "ek", "aile", "kiralik"], required=True),
            "m3_dahil": st.column_config.CheckboxColumn("m³ anahtarına dahil"),
            "onayli": st.column_config.CheckboxColumn("Onaylı"),
        },
    )
    c1, c2 = st.columns(2)
    if c1.button("Kaydet", type="primary"):
        geri = {v: k for k, v in etiket.items()}
        for _, r in duzen.iterrows():
            conn.execute(
                "UPDATE gelir_eslesme SET kar_merkezi_id=?, tip=?, m3_dahil=?, onayli=? WHERE aile=? AND kalem_adi=?",
                (geri[r["Kâr merkezi"]], r["tip"], int(r["m3_dahil"]), int(r["onayli"]), r["aile"], r["kalem_adi"]),
            )
        conn.commit()
        st.success("Kaydedildi.")
    if c2.button("Hepsini onayla"):
        conn.execute("UPDATE gelir_eslesme SET onayli=1")
        conn.commit()
        st.rerun()
    st.caption("Kâr merkezi eklemek veya yeniden adlandırmak için 'Kâr Merkezleri' sayfasını kullan.")


def kar_merkezleri():
    st.header("Kâr merkezleri")
    st.caption("Maden pozları ayrı, TSF / RC / Kiralık toplu. 'Gider alır' işaretli olanlara gider dağıtılır. "
               "Ad değiştirmek geçmiş dönemleri bozmaz (kayıtlar kimlik numarasıyla bağlı).")
    df = servis.kar_merkezleri_df(conn)
    df["gider_alir"] = df["gider_alir"].astype(bool)
    df["aktif"] = df["aktif"].astype(bool)
    duzen = st.data_editor(
        df, hide_index=True, width="stretch", num_rows="dynamic", disabled=["id"],
        column_config={"id": "No", "ad": "Ad", "aile": st.column_config.SelectboxColumn("Aile", options=["MADEN", "TSF", "RC", "KİRALIK"]),
                       "gider_alir": "Gider alır", "sira": "Sıra", "aktif": "Aktif"},
    )
    if st.button("Kaydet", type="primary"):
        for r in duzen.itertuples():
            if not r.ad or not r.aile:
                continue
            if pd.isna(r.id):
                conn.execute("INSERT INTO kar_merkezi (ad, aile, gider_alir, sira, aktif) VALUES (?, ?, ?, ?, ?)",
                             (r.ad, r.aile, int(bool(r.gider_alir)), int(r.sira if not pd.isna(r.sira) else 100), int(bool(r.aktif))))
            else:
                conn.execute("UPDATE kar_merkezi SET ad=?, aile=?, gider_alir=?, sira=?, aktif=? WHERE id=?",
                             (r.ad, r.aile, int(bool(r.gider_alir)), int(r.sira), int(bool(r.aktif)), int(r.id)))
        conn.commit()
        st.success("Kaydedildi.")


def calisma_oranlari():
    donem_gerekli()
    st.header(f"Ekipman çalışma oranları · {servis.donem_adi(conn, donem_id)}")
    st.caption("Her ekipmanın bu ay hangi işte yüzde kaç çalıştığı. Her satırın toplamı %100 olmalı; eksik kalan pay "
               "'dağıtılmamış' olarak raporlanır, kendiliğinden eşit dağıtılmaz.")
    hedef = km_etiketleri(sadece_hedef=True)
    mazot = pd.read_sql("SELECT ekipman_kod, ekipman_adi, tip, company, litre FROM mazot WHERE donem_id=? ORDER BY company, tip, ekipman_kod",
                        conn, params=(donem_id,))
    if mazot.empty:
        st.info("Önce bu dönemin mazot dosyasını yükle.")
        return
    if st.button("Önceki ayın oranlarını kopyala (boş olanlara)"):
        n = servis.oranlari_oncekinden_kopyala(conn, donem_id, "calisma_orani")
        st.success(f"{n} oran kopyalandı.")
    oran = pd.read_sql("SELECT ekipman_kod, kar_merkezi_id, oran FROM calisma_orani WHERE donem_id=?", conn, params=(donem_id,))
    tablo = mazot.copy()
    for km_id, ad in hedef.items():
        sec = oran[oran.kar_merkezi_id == km_id].set_index("ekipman_kod")["oran"]
        tablo[ad] = tablo["ekipman_kod"].map(sec).fillna(0.0) * 100
    tablo["Toplam %"] = tablo[list(hedef.values())].sum(axis=1)
    filtre = st.multiselect("Şirket", sorted(tablo.company.dropna().unique()), default=None)
    if filtre:
        tablo = tablo[tablo.company.isin(filtre)]
    duzen = st.data_editor(
        tablo, hide_index=True, width="stretch",
        disabled=["ekipman_kod", "ekipman_adi", "tip", "company", "litre", "Toplam %"],
        column_config={"ekipman_kod": "Kod", "ekipman_adi": "Ekipman", "tip": "Tip", "company": "Şirket",
                       "litre": st.column_config.NumberColumn("Litre", format="%,.0f"),
                       "Toplam %": st.column_config.NumberColumn(format="%.2f"),
                       **{ad: st.column_config.NumberColumn(ad, min_value=0.0, max_value=100.0, format="%.2f") for ad in hedef.values()}},
    )
    toplamlar = duzen[list(hedef.values())].sum(axis=1)
    hatali = duzen[(toplamlar - 100).abs() > TOLERANS * 100]
    if not hatali.empty:
        st.warning(f"%100 olmayan {len(hatali)} ekipman: " + ", ".join(hatali.ekipman_kod.head(15)))
    if st.button("Kaydet", type="primary"):
        for _, r in duzen.iterrows():
            for km_id, ad in hedef.items():
                deger = float(r[ad] or 0) / 100
                if deger:
                    conn.execute("INSERT OR REPLACE INTO calisma_orani VALUES (?, ?, ?, ?)", (donem_id, r["ekipman_kod"], km_id, deger))
                else:
                    conn.execute("DELETE FROM calisma_orani WHERE donem_id=? AND ekipman_kod=? AND kar_merkezi_id=?",
                                 (donem_id, r["ekipman_kod"], km_id))
        conn.commit()
        st.success("Kaydedildi.")
        st.rerun()


def anahtarlar():
    donem_gerekli()
    st.header(f"Dağıtım anahtarları · {servis.donem_adi(conn, donem_id)}")
    _, sonuc, veri = servis.ilerleme(conn, donem_id)
    hedef = km_etiketleri(sadece_hedef=True)
    tum = servis.anahtarlar(conn)
    aciklama = {"motorin": "Dağıtılan mazot litresinden", "ekipman": "Filtreye uyan ekipman sayısı × çalışma oranı",
                "m3": "Master Data miktarlarından (m³ anahtarına dahil kalemler)", "manuel": "Her ay elle girilir",
                "personel": "Personel dışı grupların adet × anahtar payından (ortak)"}
    satirlar = []
    for kod, a in tum.items():
        s = {"Anahtar": a["ad"], "Kaynak": aciklama.get(a["tur"], a["tur"])}
        paylar = sonuc.anahtar_paylari.get(kod)
        for km_id, ad in hedef.items():
            s[ad] = (paylar or {}).get(km_id, 0.0) * 100 if paylar else None
        s["Durum"] = "✅" if paylar else f"❌ {sonuc.anahtar_hatalari.get(kod, '')}"
        satirlar.append(s)
    st.dataframe(pd.DataFrame(satirlar), hide_index=True, width="stretch",
                 column_config={ad: st.column_config.NumberColumn(format="%.2f%%") for ad in hedef.values()})

    manuel = {k: a for k, a in tum.items() if a["tur"] == "manuel"}
    if manuel:
        st.subheader("Elle girilen paylar")
        if st.button("Önceki ayın paylarını kopyala (boş olanlara)"):
            servis.oranlari_oncekinden_kopyala(conn, donem_id, "anahtar_oran")
            st.rerun()
        mevcut = pd.read_sql("SELECT * FROM anahtar_oran WHERE donem_id=?", conn, params=(donem_id,))
        tablo = pd.DataFrame({"Kâr merkezi": list(hedef.values())})
        for kod, a in manuel.items():
            sec = mevcut[mevcut.anahtar_kod == kod].set_index("kar_merkezi_id")["oran"]
            tablo[a["ad"]] = [sec.get(km_id, 0.0) * 100 for km_id in hedef]
        duzen = st.data_editor(tablo, hide_index=True, width="stretch", disabled=["Kâr merkezi"],
                               column_config={a["ad"]: st.column_config.NumberColumn(min_value=0.0, max_value=100.0, format="%.2f")
                                              for a in manuel.values()})
        for a in manuel.values():
            t = duzen[a["ad"]].sum()
            if t and abs(t - 100) > 0.01:
                st.warning(f"{a['ad']}: toplam %{t:.2f}, %100 olmalı.")
        if st.button("Payları kaydet", type="primary"):
            for kod, a in manuel.items():
                conn.execute("DELETE FROM anahtar_oran WHERE donem_id=? AND anahtar_kod=?", (donem_id, kod))
                for km_id, deger in zip(hedef, duzen[a["ad"]]):
                    if deger:
                        conn.execute("INSERT INTO anahtar_oran VALUES (?, ?, ?, ?)", (donem_id, kod, km_id, float(deger) / 100))
            conn.commit()
            st.rerun()

    with st.expander("Yeni anahtar tanımla"):
        st.caption("Ör. 'İş Makinası (delici dahil)': Pitworks, birincil ekipman, KAMYON hariç.")
        ad = st.text_input("Anahtar adı")
        tur = st.radio("Tür", ["ekipman", "manuel"], format_func={"ekipman": "Ekipman sayısı (filtreli)", "manuel": "Elle girilen pay"}.get,
                       horizontal=True)
        filtre = {}
        if tur == "ekipman":
            tipler = sorted({r[0] for r in conn.execute("SELECT DISTINCT tip FROM ekipman WHERE tip IS NOT NULL UNION SELECT DISTINCT tip FROM mazot WHERE tip IS NOT NULL")})
            sirketler = sorted({r[0] for r in conn.execute("SELECT DISTINCT company FROM ekipman WHERE company IS NOT NULL UNION SELECT DISTINCT company FROM mazot WHERE company IS NOT NULL")})
            filtre = {
                "company": st.multiselect("Şirket (boş = hepsi)", sirketler, default=[s for s in sirketler if s == "Pitworks"]),
                "tipler": st.multiselect("Sadece bu tipler (boş = hepsi)", tipler),
                "haric_tipler": st.multiselect("Hariç tutulacak tipler", tipler),
                "sadece_birincil": st.checkbox("Sadece birincil ekipman", value=True),
            }
        if st.button("Anahtarı ekle") and ad:
            kod = imp.norm(ad).upper()[:30] or f"A{len(tum) + 1}"
            if kod in tum or any(a["ad"] == ad for a in tum.values()):
                st.error("Bu adla bir anahtar zaten var.")
            else:
                conn.execute("INSERT INTO anahtar (kod, ad, tur, filtre) VALUES (?, ?, ?, ?)",
                             (kod, ad, tur, json.dumps(filtre, ensure_ascii=False) if filtre else None))
                conn.commit()
                st.rerun()
    with st.expander("Ekipman anahtarlarının filtreleri"):
        for kod, a in tum.items():
            if a["tur"] == "ekipman":
                st.write(f"**{a['ad']}**: {json.dumps(a['filtre'], ensure_ascii=False)}")


def depo_anahtarlari():
    donem_gerekli()
    st.header(f"Depo · {servis.donem_adi(conn, donem_id)}")
    tum = servis.anahtarlar(conn)
    ad_kod = {a["ad"]: k for k, a in tum.items() if a["tur"] != "personel"}
    st.caption("Garaj no'su bir ekipman koduna eşleşen satırlar o ekipmanın çalışma oranlarıyla dağıtılır. "
               "Eşleşmeyenler (ATÖLYE, İSG…) için Gider Yeri bazında anahtar seç.")
    bg = servis.bagimsiz_gider_yerleri(conn, donem_id)
    if bg.empty:
        st.info("Ekipmandan bağımsız depo satırı yok (veya depo yüklenmedi).")
        return
    kur = conn.execute("SELECT uzs_usd FROM donem WHERE id=?", (donem_id,)).fetchone()[0]
    bg["Tutar $"] = bg["tutar_uzs"] / kur if kur else None
    bg["Anahtar"] = bg["anahtar_kod"].map(lambda k: tum.get(k, {}).get("ad") if k else None)
    duzen = st.data_editor(
        bg.drop(columns="anahtar_kod"), hide_index=True, width="stretch",
        disabled=["gider_yeri", "satir", "tutar_uzs", "Tutar $"],
        column_config={"gider_yeri": "Gider yeri", "satir": "Satır", "tutar_uzs": st.column_config.NumberColumn("Tutar UZS", format="%,.0f"),
                       "Tutar $": st.column_config.NumberColumn(format="%,.2f"),
                       "Anahtar": st.column_config.SelectboxColumn(options=list(ad_kod))},
    )
    if st.button("Kaydet", type="primary"):
        for r in duzen.itertuples():
            conn.execute("INSERT OR REPLACE INTO depo_anahtar VALUES (?, ?, ?)",
                         (donem_id, r.gider_yeri, ad_kod.get(r.Anahtar) if isinstance(r.Anahtar, str) else None))
        conn.commit()
        st.success("Kaydedildi.")


def personel():
    donem_gerekli()
    st.header(f"Personel · {servis.donem_adi(conn, donem_id)}")
    st.caption("Görev grubu bazında anahtar seç (isim bazında değil). 'Personel' anahtarı, Personel dışı anahtar seçilmiş "
               "grupların ADET × anahtar payından hesaplanan ortak paydır; dağıtılan tutar TOPLAM MAAŞTIR.")
    tum = servis.anahtarlar(conn)
    ad_kod = {a["ad"]: k for k, a in tum.items()}
    df = pd.read_sql("SELECT id, sira, gorev, birim, adet, birim_maas, toplam_maas, anahtar_kod FROM personel WHERE donem_id=? ORDER BY sira",
                     conn, params=(donem_id,))
    if df.empty:
        st.info("Önce personel dosyasını yükle.")
        return
    df["Anahtar"] = df["anahtar_kod"].map(lambda k: tum.get(k, {}).get("ad") if k else None)
    birimler = st.multiselect("Birim filtresi", sorted(df.birim.dropna().unique()))
    goster = df[df.birim.isin(birimler)] if birimler else df
    duzen = st.data_editor(
        goster.drop(columns="anahtar_kod"), hide_index=True, width="stretch",
        disabled=["id", "sira", "gorev", "birim", "adet", "birim_maas", "toplam_maas"],
        column_config={"id": None, "sira": "No", "gorev": "Görev", "birim": "Birim", "adet": "Adet",
                       "birim_maas": st.column_config.NumberColumn("Birim maaş UZS", format="%,.0f"),
                       "toplam_maas": st.column_config.NumberColumn("Toplam maaş UZS", format="%,.0f"),
                       "Anahtar": st.column_config.SelectboxColumn(options=list(ad_kod))},
    )
    c1, c2 = st.columns([1, 2])
    if c1.button("Kaydet", type="primary"):
        for r in duzen.itertuples():
            conn.execute("UPDATE personel SET anahtar_kod=? WHERE id=?",
                         (ad_kod.get(r.Anahtar) if isinstance(r.Anahtar, str) else None, int(r.id)))
        conn.commit()
        st.rerun()
    toplu = c2.selectbox("Anahtarı boş olan tüm gruplara uygula", ["—"] + list(ad_kod))
    if toplu != "—" and c2.button("Uygula"):
        conn.execute("UPDATE personel SET anahtar_kod=? WHERE donem_id=? AND anahtar_kod IS NULL", (ad_kod[toplu], donem_id))
        conn.commit()
        st.rerun()

    _, sonuc, _ = servis.ilerleme(conn, donem_id)
    hedef = km_etiketleri(sadece_hedef=True)
    st.subheader("Ortak Personel anahtarı")
    pk = next((k for k, a in tum.items() if a["tur"] == "personel"), None)
    if pk in sonuc.anahtar_paylari:
        st.dataframe(pd.DataFrame([{hedef[k]: v * 100 for k, v in sonuc.anahtar_paylari[pk].items()}]), hide_index=True,
                     column_config={ad: st.column_config.NumberColumn(format="%.2f%%") for ad in hedef.values()})
    else:
        st.error(sonuc.anahtar_hatalari.get(pk, "Hesaplanamadı"))
    st.subheader("Grup bazında dağılım ($)")
    if sonuc.personel_dagilim:
        tablo = pd.DataFrame([{"Görev": g["gorev"], "Birim": g["birim"], "Anahtar": tum.get(g["anahtar"], {}).get("ad"),
                               "Toplam $": g["usd"], **{hedef[k]: v for k, v in g["paylar"].items() if k in hedef}}
                              for g in sonuc.personel_dagilim]).fillna(0.0)
        st.dataframe(tablo, hide_index=True, width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="%,.2f") for c in tablo.columns if c not in ("Görev", "Birim", "Anahtar")})


def kontroller_sayfasi():
    donem_gerekli()
    st.header(f"Kontroller · {servis.donem_adi(conn, donem_id)}")
    _, sonuc, veri = servis.ilerleme(conn, donem_id)
    st.dataframe(servis.kontroller(conn, donem_id, veri, sonuc), hide_index=True, width="stretch")
    for h in sonuc.hatalar:
        st.error(h)
    if sonuc.dagitilmamis:
        st.subheader("Dağıtılmamış giderler")
        df = pd.DataFrame(sonuc.dagitilmamis).fillna(0.0)
        st.dataframe(df.rename(columns={"kategori": "Kategori", "aciklama": "Neden", "litre": "Litre", "usd": "$"}),
                     hide_index=True, width="stretch")


def rapor_sayfasi():
    donem_gerekli()
    adimlar, sonuc, veri = servis.ilerleme(conn, donem_id)
    kesin = all(a["durum"] == "tamam" for a in adimlar)
    st.header(f"Kâr / zarar · {servis.donem_adi(conn, donem_id)}")
    if not kesin:
        st.warning("**TASLAK**: Bu dönemin adımları tamamlanmadı; sonuçlar kesin değildir. Dağıtılmamış giderler ayrı satırda.")
    r = servis.rapor(conn, donem_id, veri, sonuc)
    if r.empty:
        st.info("Bu dönem için veri yok.")
        return
    para_kol = {c: st.column_config.NumberColumn(format="%,.2f") for c in r.columns if c.endswith("$") or c.endswith("L")}
    sekme = st.tabs(["Kâr merkezi", "Aile özeti", "Dönem karşılaştırma"])
    with sekme[0]:
        st.dataframe(r, hide_index=True, width="stretch", column_config=para_kol)
        govde = r[~r["Aile"].isin(["TOPLAM", "-"])]
        st.bar_chart(govde.set_index("Kâr merkezi")["Sonuç $"])
    with sekme[1]:
        st.dataframe(servis.aile_ozeti(r), hide_index=True, width="stretch", column_config=para_kol)
    with sekme[2]:
        yillar = [y[0] for y in conn.execute("SELECT DISTINCT yil FROM donem ORDER BY yil DESC")]
        c1, c2 = st.columns(2)
        yil = c1.selectbox("Yıl", [None] + yillar, format_func=lambda y: "Tüm yıllar" if y is None else str(y))
        metrik = c2.selectbox("Değer", ["Sonuç $", "Gelir $", "Toplam gider $", "Mazot $", "Depo $", "Personel $", "Mazot L"])
        kars = servis.donem_karsilastirma(conn, yil, metrik)
        st.dataframe(kars, hide_index=True, width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="%,.2f") for c in kars.columns if c not in ("Aile", "Kâr merkezi")})

    tampon = io.BytesIO()
    with pd.ExcelWriter(tampon, engine="openpyxl") as w:
        r.to_excel(w, sheet_name="Kâr merkezi", index=False)
        servis.aile_ozeti(r).to_excel(w, sheet_name="Aile özeti", index=False)
        servis.kontroller(conn, donem_id, veri, sonuc).to_excel(w, sheet_name="Kontroller", index=False)
        if sonuc.dagitilmamis:
            pd.DataFrame(sonuc.dagitilmamis).to_excel(w, sheet_name="Dağıtılmamış", index=False)
        hedef = km_etiketleri(sadece_hedef=True)
        pd.DataFrame({veri.anahtarlar[k]["ad"]: {hedef.get(km, km): p for km, p in v.items()} for k, v in sonuc.anahtar_paylari.items()}) \
            .to_excel(w, sheet_name="Anahtar payları")
    st.download_button("Excel'e aktar", tampon.getvalue(),
                       file_name=f"Maliyet_Analizi_{servis.donem_adi(conn, donem_id).replace(' ', '_')}{'' if kesin else '_TASLAK'}.xlsx")


{
    "Genel Bakış": genel_bakis, "Ay Paneli": ay_paneli, "Kurlar": kurlar, "Veri Yükleme": veri_yukleme,
    "Gelir Eşleme": gelir_esleme, "Kâr Merkezleri": kar_merkezleri, "Çalışma Oranları": calisma_oranlari,
    "Anahtarlar": anahtarlar, "Depo Anahtarları": depo_anahtarlari, "Personel": personel,
    "Kontroller": kontroller_sayfasi, "Rapor": rapor_sayfasi,
}[sayfa]()
