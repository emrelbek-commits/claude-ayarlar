"""Hesap motoru: arayüzden ve veritabanından bağımsız, saf fonksiyonlar.

Tüm oranlar 0..1 aralığında tutulur. Para birimi çıktıları USD'dir.
Hiçbir yerde sessiz eşit dağıtım veya uydurma pay yoktur: hesaplanamayan
her tutar "dağıtılmamış" olarak nedeniyle birlikte raporlanır.
"""
from collections import defaultdict
from dataclasses import dataclass, field

TOLERANS = 1e-4  # %0,01


@dataclass
class DonemVerisi:
    hedefler: dict                      # km_id -> ad (gider alan kâr merkezleri)
    uzs_usd: float | None = None
    uzs_litre: float | None = None
    gelir: list = field(default_factory=list)          # dict: km_id, tutar, miktar, m3_dahil
    mazot: dict = field(default_factory=dict)          # ekipman_kod -> litre
    ekipman_bilgi: dict = field(default_factory=dict)  # ekipman_kod -> {tip, company, birincil}
    oranlar: dict = field(default_factory=dict)        # ekipman_kod -> {km_id: oran}
    depo: list = field(default_factory=list)           # dict: garaj_no, gider_yeri, tutar_uzs
    depo_anahtar: dict = field(default_factory=dict)   # gider_yeri -> anahtar_kod
    personel: list = field(default_factory=list)       # dict: id, gorev, birim, adet, toplam_maas, anahtar_kod
    anahtarlar: dict = field(default_factory=dict)     # kod -> {ad, tur, filtre}
    manuel_oranlar: dict = field(default_factory=dict) # anahtar_kod -> {km_id: oran}


@dataclass
class Sonuc:
    anahtar_paylari: dict = field(default_factory=dict)   # kod -> {km_id: pay}
    anahtar_hatalari: dict = field(default_factory=dict)  # kod -> mesaj
    mazot_litre: dict = field(default_factory=lambda: defaultdict(float))
    gider: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(float)))  # km -> kategori -> usd
    dagitilmamis: list = field(default_factory=list)      # dict: kategori, aciklama, usd, litre
    hatalar: list = field(default_factory=list)
    uyarilar: list = field(default_factory=list)
    toplam_kaynak: dict = field(default_factory=dict)     # kategori -> usd (dağıtım öncesi)
    toplam_litre: float = 0.0
    personel_dagilim: list = field(default_factory=list)  # grup bazında dağılım


# ---------------------------------------------------------------- yardımcılar

def _norm(metin) -> str:
    return str(metin or "").strip().upper().replace("İ", "I")


def pay_normalize(degerler: dict) -> dict | None:
    """Ağırlıkları paya çevirir. Payda 0 ise None (hesaplanamaz)."""
    toplam = sum(v for v in degerler.values() if v)
    if toplam <= 0:
        return None
    return {k: v / toplam for k, v in degerler.items() if v}


def ekipman_filtreye_uyar(bilgi: dict, filtre: dict) -> bool:
    companies = [_norm(c) for c in (filtre.get("company") or [])]
    tipler = [_norm(t) for t in (filtre.get("tipler") or [])]
    haric = [_norm(t) for t in (filtre.get("haric_tipler") or [])]
    if companies and _norm(bilgi.get("company")) not in companies:
        return False
    if tipler and _norm(bilgi.get("tip")) not in tipler:
        return False
    if haric and _norm(bilgi.get("tip")) in haric:
        return False
    if filtre.get("sadece_birincil") and not bilgi.get("birincil"):
        return False
    return True


def oran_toplami_kontrol(oranlar: dict) -> dict:
    """Ekipman bazında çalışma oranı toplamı ve durumu."""
    sonuc = {}
    for ekip, satir in oranlar.items():
        t = sum(satir.values())
        if abs(t - 1) <= TOLERANS:
            durum = "tamam"
        elif t > 1:
            durum = "fazla"
        else:
            durum = "eksik"
        sonuc[ekip] = (t, durum)
    return sonuc


# ---------------------------------------------------------------- anahtarlar

def ekipman_anahtari(veri: DonemVerisi, filtre: dict):
    """Filtreye uyan her ekipman 1 sayılır ve çalışma oranlarıyla pozlara dağılır."""
    adaylar = set(veri.mazot) | set(veri.oranlar)
    secilen = [e for e in sorted(adaylar) if ekipman_filtreye_uyar(veri.ekipman_bilgi.get(e, {}), filtre)]
    if not secilen:
        return None, "Filtreye uyan ekipman yok"
    eksik = [e for e in secilen if not veri.oranlar.get(e)]
    if eksik:
        return None, "Çalışma oranı girilmemiş ekipman: " + ", ".join(eksik[:10]) + (" …" if len(eksik) > 10 else "")
    hatali = [e for e, (_, d) in oran_toplami_kontrol({e: veri.oranlar[e] for e in secilen}).items() if d != "tamam"]
    if hatali:
        return None, "Çalışma oranı toplamı %100 olmayan ekipman: " + ", ".join(hatali[:10])
    agirlik = defaultdict(float)
    for e in secilen:
        for km, oran in veri.oranlar[e].items():
            agirlik[km] += oran
    return pay_normalize(agirlik), None


def anahtarlari_hesapla(veri: DonemVerisi, sonuc: Sonuc) -> None:
    """Personel dışındaki anahtarlar. Motorin anahtarı mazot dağıtımından sonra çağrılmalı."""
    for kod, a in veri.anahtarlar.items():
        tur = a["tur"]
        paylar, hata = None, None
        if tur == "motorin":
            paylar = pay_normalize(dict(sonuc.mazot_litre))
            if paylar is None:
                hata = "Dağıtılmış mazot litresi yok"
        elif tur == "ekipman":
            paylar, hata = ekipman_anahtari(veri, a.get("filtre") or {})
        elif tur == "m3":
            agirlik = defaultdict(float)
            for g in veri.gelir:
                if g.get("m3_dahil") and g["km_id"] in veri.hedefler:
                    agirlik[g["km_id"]] += g.get("miktar") or 0
            paylar = pay_normalize(agirlik)
            if paylar is None:
                hata = "m³ anahtarına dahil kalemlerde miktar yok"
        elif tur == "manuel":
            girilen = veri.manuel_oranlar.get(kod) or {}
            t = sum(girilen.values())
            if not girilen or t <= 0:
                hata = "Paylar girilmemiş"
            elif abs(t - 1) > TOLERANS:
                hata = f"Payların toplamı %{t * 100:.2f}, %100 olmalı"
            else:
                paylar = {k: v for k, v in girilen.items() if v}
        elif tur == "personel":
            continue
        else:
            hata = f"Bilinmeyen anahtar türü: {tur}"
        if paylar is not None:
            disarida = [k for k in paylar if k not in veri.hedefler]
            if disarida:
                paylar, hata = None, "Gider almayan kâr merkezine pay verilmiş"
        if hata:
            sonuc.anahtar_hatalari[kod] = hata
        else:
            sonuc.anahtar_paylari[kod] = paylar


def personel_ortak_anahtari(personel: list, anahtarlar: dict, paylar: dict, hatalar: dict):
    """Ortak Personel anahtarı.

    K_p = Σ(Personel anahtarlı olmayan gruplar) adet × anahtar payı_p
    w_p = K_p / Σ K_p
    Ağırlık personel ADEDİDİR; maaş tutarı burada kullanılmaz.
    Personel anahtarlı gruplar hem paydan hem paydadan dışlanır (döngü yok).
    """
    personel_kodlari = {k for k, a in anahtarlar.items() if a["tur"] == "personel"}
    K = defaultdict(float)
    eksik = []
    for g in personel:
        kod = g.get("anahtar_kod")
        if not kod or kod in personel_kodlari:
            continue
        if kod not in paylar:
            eksik.append(f"{g['gorev']} ({anahtarlar.get(kod, {}).get('ad', kod)}: {hatalar.get(kod, 'hesaplanamadı')})")
            continue
        for km, w in paylar[kod].items():
            K[km] += (g.get("adet") or 0) * w
    if eksik:
        return None, "Kaynak grupların anahtarı hesaplanamadı: " + "; ".join(eksik[:5])
    sonuc = pay_normalize(K)
    if sonuc is None:
        return None, "Personel dışı anahtar seçilmiş grup yok veya adetleri 0 (payda 0)"
    return sonuc, None


# ---------------------------------------------------------------- dağıtımlar

def _usd(uzs, kur):
    return uzs / kur if kur else None


def mazot_dagit(veri: DonemVerisi, sonuc: Sonuc) -> None:
    litre_usd = (veri.uzs_litre / veri.uzs_usd) if veri.uzs_litre and veri.uzs_usd else None
    if litre_usd is None:
        sonuc.hatalar.append("Mazot maliyeti hesaplanamaz: UZS/USD ve UZS/L girilmeli")
    sonuc.toplam_litre = sum(veri.mazot.values())
    sonuc.toplam_kaynak["mazot"] = sonuc.toplam_litre * litre_usd if litre_usd else 0.0
    for ekip, litre in veri.mazot.items():
        if not litre:
            continue
        oranlar = veri.oranlar.get(ekip) or {}
        toplam = sum(oranlar.values())
        if not oranlar:
            _dagitilmamis(sonuc, "mazot", f"{ekip}: çalışma oranı yok", litre, litre_usd)
            continue
        if toplam > 1 + TOLERANS:
            _dagitilmamis(sonuc, "mazot", f"{ekip}: çalışma oranı toplamı %{toplam * 100:.2f} (>%100)", litre, litre_usd)
            continue
        for km, oran in oranlar.items():
            if km not in veri.hedefler:
                _dagitilmamis(sonuc, "mazot", f"{ekip}: gider almayan merkeze oran", litre * oran, litre_usd)
                continue
            sonuc.mazot_litre[km] += litre * oran
            if litre_usd:
                sonuc.gider[km]["mazot"] += litre * oran * litre_usd
        if toplam < 1 - TOLERANS:
            _dagitilmamis(sonuc, "mazot", f"{ekip}: atanmamış pay %{(1 - toplam) * 100:.2f}", litre * (1 - toplam), litre_usd)


def _dagitilmamis(sonuc, kategori, aciklama, litre, litre_usd):
    sonuc.dagitilmamis.append(
        {"kategori": kategori, "aciklama": aciklama, "litre": litre, "usd": litre * litre_usd if litre_usd else 0.0}
    )


def depo_dagit(veri: DonemVerisi, sonuc: Sonuc) -> None:
    ekipmanlar = set(veri.ekipman_bilgi) | set(veri.mazot)
    toplam = 0.0
    for satir in veri.depo:
        usd = _usd(satir.get("tutar_uzs") or 0, veri.uzs_usd)
        if usd is None:
            sonuc.hatalar.append("Depo giderleri USD'ye çevrilemez: UZS/USD girilmeli")
            sonuc.toplam_kaynak["depo"] = 0.0
            return
        toplam += usd
        if not usd:
            continue
        garaj = str(satir.get("garaj_no") or "").strip()
        if garaj in ekipmanlar:
            oranlar = veri.oranlar.get(garaj) or {}
            t = sum(oranlar.values())
            if not oranlar or t > 1 + TOLERANS:
                sonuc.dagitilmamis.append({"kategori": "depo", "aciklama": f"{garaj}: çalışma oranı yok/hatalı", "usd": usd})
                continue
            for km, oran in oranlar.items():
                sonuc.gider[km]["depo"] += usd * oran
            if t < 1 - TOLERANS:
                sonuc.dagitilmamis.append({"kategori": "depo", "aciklama": f"{garaj}: atanmamış pay", "usd": usd * (1 - t)})
            continue
        yer = satir.get("gider_yeri") or "(Gider yeri boş)"
        kod = veri.depo_anahtar.get(yer)
        if not kod:
            sonuc.dagitilmamis.append({"kategori": "depo", "aciklama": f"{yer}: anahtar seçilmemiş", "usd": usd})
            continue
        paylar = sonuc.anahtar_paylari.get(kod)
        if paylar is None:
            sonuc.dagitilmamis.append({"kategori": "depo", "aciklama": f"{yer}: {kod} anahtarı hesaplanamadı", "usd": usd})
            continue
        for km, pay in paylar.items():
            sonuc.gider[km]["depo"] += usd * pay
    sonuc.toplam_kaynak["depo"] = toplam


def personel_dagit(veri: DonemVerisi, sonuc: Sonuc) -> None:
    if veri.personel and not veri.uzs_usd:
        sonuc.hatalar.append("Personel giderleri USD'ye çevrilemez: UZS/USD girilmeli")
        sonuc.toplam_kaynak["personel"] = 0.0
        return
    toplam = 0.0
    for g in veri.personel:
        usd = _usd(g.get("toplam_maas") or 0, veri.uzs_usd) or 0.0
        toplam += usd
        kod = g.get("anahtar_kod")
        satir = {"id": g.get("id"), "gorev": g["gorev"], "birim": g.get("birim"), "usd": usd, "anahtar": kod, "paylar": {}}
        sonuc.personel_dagilim.append(satir)
        if not usd:
            continue
        if not kod:
            sonuc.dagitilmamis.append({"kategori": "personel", "aciklama": f"{g['gorev']}: anahtar seçilmemiş", "usd": usd})
            continue
        paylar = sonuc.anahtar_paylari.get(kod)
        if paylar is None:
            sonuc.dagitilmamis.append(
                {"kategori": "personel", "aciklama": f"{g['gorev']}: {kod} anahtarı hesaplanamadı", "usd": usd}
            )
            continue
        for km, pay in paylar.items():
            sonuc.gider[km]["personel"] += usd * pay
            satir["paylar"][km] = usd * pay
    sonuc.toplam_kaynak["personel"] = toplam


# ---------------------------------------------------------------- ana akış

def hesapla(veri: DonemVerisi) -> Sonuc:
    """Brifteki sıra: mazot → baz anahtarlar → depo → ortak Personel anahtarı → personel."""
    sonuc = Sonuc()
    mazot_dagit(veri, sonuc)
    anahtarlari_hesapla(veri, sonuc)
    for kod, a in veri.anahtarlar.items():
        if a["tur"] == "personel":
            paylar, hata = personel_ortak_anahtari(veri.personel, veri.anahtarlar, sonuc.anahtar_paylari, sonuc.anahtar_hatalari)
            if hata:
                sonuc.anahtar_hatalari[kod] = hata
            else:
                sonuc.anahtar_paylari[kod] = paylar
    depo_dagit(veri, sonuc)
    personel_dagit(veri, sonuc)
    return sonuc


def dagitilan_toplam(sonuc: Sonuc, kategori: str) -> float:
    return sum(k.get(kategori, 0.0) for k in sonuc.gider.values())


def dagitilmamis_toplam(sonuc: Sonuc, kategori: str | None = None) -> float:
    return sum(d["usd"] for d in sonuc.dagitilmamis if kategori is None or d["kategori"] == kategori)
