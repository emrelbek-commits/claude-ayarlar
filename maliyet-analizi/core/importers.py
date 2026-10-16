"""Excel içe aktarımı.

Her kaynak için bir "profil" vardır: alan adı -> başlıkta aranacak isimler.
Başlık satırı ilk 20 satırda aranır, sütunların yeri önemli değildir.
Kaynak dosyanın formatı değişirse yalnızca PROFILLER sözlüğü güncellenir.
"""
import hashlib
import re
import unicodedata

import pandas as pd

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

PROFILLER = {
    "master": {
        "donem": ["donem"],
        "yil": ["yil", "year"],
        "aile": ["hakedissozlesme", "sozlesme"],
        "kdv": ["kdvyn"],
        "kalem": ["hakedispoz", "kalem"],
        "miktar": ["yapilanis", "miktar"],
        "tutar": ["kdvsiz"],
        "birim_fiyat": ["birimfiyat"],
    },
    "mazot": {
        "yil": ["year", "yil"],
        "ay": ["month", "ay"],
        "company": ["company", "firma"],
        "kod": ["companyno", "ekipmankodu"],
        "ad": ["equipmentno", "ekipmanadi"],
        "tip": ["equipmenttype", "ekipmantipi"],
        "litre": ["toplam", "total"],
    },
    "depo": {
        "tarih": ["дата", "tarih"],
        "malzeme": ["наименованиематериала", "malzeme"],
        "miktar": ["колво", "miktar"],
        "tutar": ["сумма", "tutar"],
        "garaj_no": ["гаражномер", "garajno"],
        "ekipman_adi": ["ekipmanadi"],
        "grup": ["grup"],
        "alt_grup": ["altgrup"],
        "gider_yeri": ["gideryeri"],
    },
    "personel": {
        "gorev": ["gorev"],
        "birim": ["birim"],
        "adet": ["adet"],
        "birim_maas": ["birimmaas"],
        "toplam_maas": ["toplammaas"],
    },
    "ekipman": {
        "kod": ["companyno", "ekipmankodu", "garajno", "kod"],
        "ad": ["equipmentno", "ekipmanadi"],
        "tip": ["equipmenttype", "ekipmantipi", "tip"],
        "company": ["company", "firma", "sirket"],
        "birincil": ["birincilekipman", "birincil"],
    },
}

ZORUNLU = {
    "master": ["donem", "yil", "aile", "kalem", "tutar"],
    "mazot": ["yil", "ay", "litre"],
    "depo": ["tutar", "garaj_no", "gider_yeri"],
    "personel": ["gorev", "adet", "toplam_maas"],
    "ekipman": ["kod", "tip", "company"],
}


class IceAktarimHatasi(Exception):
    pass


def norm(metin) -> str:
    s = str(metin or "").replace("ı", "i").replace("İ", "I").lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^0-9a-zа-я]", "", s)


def dosya_hash(icerik: bytes) -> str:
    return hashlib.sha256(icerik).hexdigest()


def sayi(deger) -> float | None:
    if deger is None or (isinstance(deger, float) and pd.isna(deger)):
        return None
    if isinstance(deger, (int, float)):
        return float(deger)
    s = str(deger).strip().replace("UZS", "").replace("$", "").replace(" ", "")
    if s in ("", "-", "—"):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def tarih_coz(deger):
    """Excel tarihi, '1.05.2026' (gün.ay.yıl) veya '2026-05-01' biçimlerini çözer."""
    if deger is None or (isinstance(deger, float) and pd.isna(deger)):
        return None
    if hasattr(deger, "year"):
        return pd.Timestamp(deger)
    s = str(deger).strip()
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}.*", s):
        return pd.to_datetime(s[:10], format="%Y-%m-%d", errors="coerce")
    return pd.to_datetime(s.replace("/", "."), format="%d.%m.%Y", errors="coerce")


def ay_numarasi(deger) -> int | None:
    if deger is None or (isinstance(deger, float) and pd.isna(deger)):
        return None
    if isinstance(deger, (int, float)):
        return int(deger) if 1 <= int(deger) <= 12 else None
    n = norm(deger)
    for i, ad in enumerate(AYLAR, start=1):
        if n == norm(ad):
            return i
    try:
        return ay_numarasi(int(n))
    except ValueError:
        return None


def _basliklari_eslestir(basliklar: list, profil: dict) -> dict:
    """Önce birebir eşleşme, sonra 'ile başlar' eşleşmesi. Her sütun en fazla bir alana gider."""
    normlar = [norm(b) for b in basliklar]
    eslesme, kullanilan = {}, set()
    for kip in ("tam", "baslar"):
        for alan, adlar in profil.items():
            if alan in eslesme:
                continue
            for ad in adlar:
                for i, n in enumerate(normlar):
                    if i in kullanilan or not n:
                        continue
                    if (kip == "tam" and n == ad) or (kip == "baslar" and n.startswith(ad)):
                        eslesme[alan] = i
                        kullanilan.add(i)
                        break
                if alan in eslesme:
                    break
    return eslesme


def tablo_oku(dosya, kaynak: str) -> tuple[pd.DataFrame, dict]:
    """Excel dosyasında başlık satırını bulur, profile göre alanları içeren DataFrame döner."""
    profil, zorunlu = PROFILLER[kaynak], ZORUNLU[kaynak]
    try:
        sayfalar = pd.read_excel(dosya, sheet_name=None, header=None)
    except Exception as e:  # noqa: BLE001
        raise IceAktarimHatasi(f"Excel okunamadı: {e}") from e
    en_iyi = None
    for sayfa_adi, df in sayfalar.items():
        for satir_no in range(min(20, len(df))):
            eslesme = _basliklari_eslestir(list(df.iloc[satir_no]), profil)
            if all(z in eslesme for z in zorunlu):
                veri = df.iloc[satir_no + 1:].reset_index(drop=True)
                cikti = pd.DataFrame({alan: veri.iloc[:, i] for alan, i in eslesme.items()})
                bilgi = {
                    "sayfa": sayfa_adi,
                    "baslik_satiri": satir_no + 1,
                    "sutunlar": {alan: str(df.iloc[satir_no, i]) for alan, i in eslesme.items()},
                }
                return cikti, bilgi
            skor = sum(z in eslesme for z in zorunlu)
            if en_iyi is None or skor > en_iyi[0]:
                en_iyi = (skor, sayfa_adi, [z for z in zorunlu if z not in eslesme])
    eksik = en_iyi[2] if en_iyi else zorunlu
    raise IceAktarimHatasi(
        "Başlık satırı bulunamadı. Bulunamayan sütunlar: "
        + ", ".join(f"{z} ({' / '.join(profil[z])})" for z in eksik)
    )


# ---------------------------------------------------------------- kaynaklar

def master_oku(dosya) -> tuple[pd.DataFrame, dict]:
    df, bilgi = tablo_oku(dosya, "master")
    df = df[df["kalem"].notna() & (df["kalem"].astype(str).str.strip() != "")].copy()
    df["ay"] = df["donem"].map(ay_numarasi)
    df["yil"] = df["yil"].map(sayi)
    hatali = df[df["ay"].isna() | df["yil"].isna()]
    df = df.drop(hatali.index)
    df["yil"] = df["yil"].astype(int)
    df["ay"] = df["ay"].astype(int)
    df["aile"] = df["aile"].astype(str).str.strip().str.upper()
    df["kalem"] = df["kalem"].astype(str).str.strip()
    df["kdv"] = df["kdv"].astype(str).str.strip().str.upper() if "kdv" in df else None
    for alan in ("miktar", "tutar", "birim_fiyat"):
        df[alan] = df[alan].map(sayi) if alan in df else None
    df["tutar"] = df["tutar"].fillna(0.0)
    bilgi["atlanan_satir"] = len(hatali)
    return df.reset_index(drop=True), bilgi


def mazot_oku(dosya, yil: int, ay: int) -> tuple[pd.DataFrame, dict]:
    df, bilgi = tablo_oku(dosya, "mazot")
    df["yil_n"] = df["yil"].map(sayi)
    df["ay_n"] = df["ay"].map(ay_numarasi)
    bilgi["bulunan_aylar"] = sorted(
        {(int(y), int(a)) for y, a in zip(df["yil_n"], df["ay_n"]) if y is not None and a is not None and not pd.isna(y)}
    )
    df = df[(df["yil_n"] == yil) & (df["ay_n"] == ay)].copy()
    df["litre"] = df["litre"].map(sayi).fillna(0.0)
    for alan in ("company", "kod", "ad", "tip"):
        if alan not in df:
            df[alan] = None
        df[alan] = df[alan].map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip())
    df["ekipman_kod"] = df["kod"].where(df["kod"] != "", df["ad"])
    bos = df[df["ekipman_kod"] == ""]
    df = df[df["ekipman_kod"] != ""]
    ozet = (
        df.groupby("ekipman_kod", as_index=False)
        .agg(litre=("litre", "sum"), ekipman_adi=("ad", "first"), tip=("tip", "first"), company=("company", "first"),
             company_sayisi=("company", "nunique"))
    )
    bilgi["kodsuz_satir"] = len(bos)
    bilgi["kodsuz_litre"] = float(bos["litre"].sum())
    bilgi["cakisan_kodlar"] = ozet.loc[ozet["company_sayisi"] > 1, "ekipman_kod"].tolist()
    return ozet.drop(columns="company_sayisi"), bilgi


def depo_oku(dosya, yil: int, ay: int) -> tuple[pd.DataFrame, dict]:
    df, bilgi = tablo_oku(dosya, "depo")
    df["tutar_uzs"] = df["tutar"].map(sayi).fillna(0.0)
    df = df[df["garaj_no"].notna() | (df["tutar_uzs"] != 0)].copy()
    if "tarih" in df:
        tarihler = pd.to_datetime(df["tarih"].map(tarih_coz), errors="coerce")
        df["tarih"] = tarihler.dt.strftime("%Y-%m-%d")
        ayda = (tarihler.dt.year == yil) & (tarihler.dt.month == ay)
        bilgi["donem_disi_satir"] = int((~ayda & tarihler.notna()).sum())
        df = df[ayda | tarihler.isna()]
    for alan in ("malzeme", "garaj_no", "ekipman_adi", "grup", "alt_grup", "gider_yeri"):
        if alan not in df:
            df[alan] = None
        df[alan] = df[alan].map(lambda v: None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip())
    df["miktar"] = df["miktar"].map(sayi) if "miktar" in df else None
    return df.reset_index(drop=True), bilgi


def personel_oku(dosya) -> tuple[pd.DataFrame, dict]:
    df, bilgi = tablo_oku(dosya, "personel")
    for alan in ("adet", "birim_maas", "toplam_maas"):
        df[alan] = df[alan].map(sayi) if alan in df else None
    df["gorev"] = df["gorev"].map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip())
    if "birim" not in df:
        df["birim"] = None
    df["birim"] = df["birim"].map(lambda v: None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip())
    bos = (df["gorev"].isin(["", "0"])) | ((df["adet"].fillna(0) == 0) & (df["toplam_maas"].fillna(0) == 0))
    bilgi["atlanan_satir"] = int(bos.sum())
    df = df[~bos].copy()
    df["toplam_maas"] = df["toplam_maas"].fillna(df["adet"] * df["birim_maas"])
    hesap = df["adet"] * df["birim_maas"]
    fark = df[(hesap.notna()) & ((hesap - df["toplam_maas"]).abs() > 1)]
    bilgi["toplam_uyusmayan"] = fark["gorev"].tolist()
    df["sira"] = range(1, len(df) + 1)
    return df.reset_index(drop=True), bilgi


def ekipman_oku(dosya) -> tuple[pd.DataFrame, dict]:
    df, bilgi = tablo_oku(dosya, "ekipman")
    for alan in ("kod", "ad", "tip", "company"):
        if alan not in df:
            df[alan] = None
        df[alan] = df[alan].map(lambda v: None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip())
    df = df[df["kod"].notna() & (df["kod"] != "")].copy()
    if "birincil" in df:
        df["birincil"] = df["birincil"].map(lambda v: 1 if norm(v) in ("evet", "e", "yes", "y", "1", "true", "x") else 0)
    else:
        df["birincil"] = 0
    bilgi["tekrar_eden_kod"] = df.loc[df["kod"].duplicated(), "kod"].tolist()
    return df.drop_duplicates("kod", keep="last").reset_index(drop=True), bilgi

