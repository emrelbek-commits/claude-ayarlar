"""SQLite veritabanı: şema, ilk kayıtlar ve küçük yardımcılar."""
import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS donem (
    id INTEGER PRIMARY KEY,
    yil INTEGER NOT NULL,
    ay INTEGER NOT NULL,
    uzs_usd REAL,           -- 1 USD kaç UZS
    uzs_litre REAL,         -- 1 litre mazot kaç UZS
    UNIQUE (yil, ay)
);

-- Kâr merkezleri: Maden pozları, Maden ek kalemleri (yazıldığı gibi), TSF, RC, Kiralık.
-- gider_alir = 1 olanlara gider dağıtılır; ek kalemler sadece gelir taşır.
CREATE TABLE IF NOT EXISTS kar_merkezi (
    id INTEGER PRIMARY KEY,
    ad TEXT NOT NULL,
    aile TEXT NOT NULL,
    gider_alir INTEGER NOT NULL DEFAULT 1,
    sira INTEGER NOT NULL DEFAULT 100,
    aktif INTEGER NOT NULL DEFAULT 1,
    aciklama TEXT,                  -- ör. Maden 1 için Master Data'daki iş tanımı
    UNIQUE (aile, ad)
);

-- Master Data kalemlerinin hangi kâr merkezine gittiği (aylar arası kalıcı).
CREATE TABLE IF NOT EXISTS gelir_eslesme (
    aile TEXT NOT NULL,
    kalem_adi TEXT NOT NULL,
    kar_merkezi_id INTEGER NOT NULL REFERENCES kar_merkezi(id),
    tip TEXT NOT NULL,              -- poz / kiralik / ek / aile
    m3_dahil INTEGER NOT NULL DEFAULT 0,
    onayli INTEGER NOT NULL DEFAULT 0,   -- otomatik önerildiyse 0, kullanıcı onaylayınca 1
    kisa_ad TEXT,                        -- Maden 1, TSF 2, RC 3 gibi
    PRIMARY KEY (aile, kalem_adi)
);

CREATE TABLE IF NOT EXISTS gelir (
    id INTEGER PRIMARY KEY,
    donem_id INTEGER NOT NULL REFERENCES donem(id),
    aile TEXT NOT NULL,
    kalem_adi TEXT NOT NULL,
    kdv TEXT,
    miktar REAL,
    birim_fiyat REAL,
    tutar REAL NOT NULL             -- KDV'siz USD
);

CREATE TABLE IF NOT EXISTS yukleme (
    id INTEGER PRIMARY KEY,
    donem_id INTEGER,
    kaynak TEXT NOT NULL,
    dosya_adi TEXT,
    hash TEXT,
    tarih TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    satir INTEGER
);

CREATE TABLE IF NOT EXISTS ekipman (
    kod TEXT PRIMARY KEY,
    ad TEXT,
    tip TEXT,
    company TEXT,
    birincil INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS mazot (
    donem_id INTEGER NOT NULL REFERENCES donem(id),
    ekipman_kod TEXT NOT NULL,
    ekipman_adi TEXT,
    tip TEXT,
    company TEXT,
    litre REAL NOT NULL,
    PRIMARY KEY (donem_id, ekipman_kod)
);

CREATE TABLE IF NOT EXISTS calisma_orani (
    donem_id INTEGER NOT NULL REFERENCES donem(id),
    ekipman_kod TEXT NOT NULL,
    kar_merkezi_id INTEGER NOT NULL REFERENCES kar_merkezi(id),
    oran REAL NOT NULL,             -- 0..1
    PRIMARY KEY (donem_id, ekipman_kod, kar_merkezi_id)
);

CREATE TABLE IF NOT EXISTS depo (
    id INTEGER PRIMARY KEY,
    donem_id INTEGER NOT NULL REFERENCES donem(id),
    tarih TEXT,
    malzeme TEXT,
    miktar REAL,
    tutar_uzs REAL NOT NULL,
    garaj_no TEXT,
    ekipman_adi TEXT,
    grup TEXT,
    alt_grup TEXT,
    gider_yeri TEXT
);

-- Ekipmandan bağımsız depo satırları için Gider Yeri -> anahtar (aylık).
CREATE TABLE IF NOT EXISTS depo_anahtar (
    donem_id INTEGER NOT NULL REFERENCES donem(id),
    gider_yeri TEXT NOT NULL,
    anahtar_kod TEXT REFERENCES anahtar(kod),
    PRIMARY KEY (donem_id, gider_yeri)
);

CREATE TABLE IF NOT EXISTS personel (
    id INTEGER PRIMARY KEY,
    donem_id INTEGER NOT NULL REFERENCES donem(id),
    sira INTEGER NOT NULL,
    gorev TEXT NOT NULL,
    birim TEXT,
    adet REAL NOT NULL,
    birim_maas REAL,
    toplam_maas REAL NOT NULL,      -- UZS
    anahtar_kod TEXT REFERENCES anahtar(kod)
);

-- tur: motorin / ekipman / m3 / manuel / personel
CREATE TABLE IF NOT EXISTS anahtar (
    kod TEXT PRIMARY KEY,
    ad TEXT NOT NULL,
    tur TEXT NOT NULL,
    filtre TEXT,                    -- ekipman anahtarları için JSON
    sistem INTEGER NOT NULL DEFAULT 0
);

-- Elle girilen anahtar payları (ör. Patlayıcı), aylık.
CREATE TABLE IF NOT EXISTS anahtar_oran (
    donem_id INTEGER NOT NULL REFERENCES donem(id),
    anahtar_kod TEXT NOT NULL REFERENCES anahtar(kod),
    kar_merkezi_id INTEGER NOT NULL REFERENCES kar_merkezi(id),
    oran REAL NOT NULL,
    PRIMARY KEY (donem_id, anahtar_kod, kar_merkezi_id)
);
"""

VARSAYILAN_KAR_MERKEZLERI = [
    # ad, aile, gider_alir, sira
    ("TSF", "TSF", 1, 60),
    ("RC", "RC", 1, 70),
    ("Kiralık", "KİRALIK", 1, 80),
]

VARSAYILAN_ANAHTARLAR = [
    ("MOTORIN", "Motorin", "motorin", None),
    ("KAMYON", "Kamyon", "ekipman", {"company": ["Pitworks"], "tipler": ["KAMYON"], "sadece_birincil": False}),
    ("EKIPMAN", "Ekipman (delici dahil)", "ekipman", {"company": ["Pitworks"], "tipler": [], "sadece_birincil": True}),
    ("EKIPMAN_DH", "Ekipman (delici hariç)", "ekipman",
     {"company": ["Pitworks"], "tipler": [], "haric_tipler": ["DELICI", "RC"], "sadece_birincil": True}),
    ("M3", "m³", "m3", None),
    ("PATLAYICI", "Patlayıcı", "manuel", None),
    ("PERSONEL", "Personel", "personel", None),
]


def baglan(yol) -> sqlite3.Connection:
    Path(yol).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(yol, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    kur(conn)
    return conn


def kur(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM kar_merkezi").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO kar_merkezi (ad, aile, gider_alir, sira) VALUES (?, ?, ?, ?)",
            VARSAYILAN_KAR_MERKEZLERI,
        )
    _sutun_ekle(conn, "kar_merkezi", "aciklama", "TEXT")
    _sutun_ekle(conn, "gelir_eslesme", "kisa_ad", "TEXT")
    conn.execute("UPDATE anahtar SET ad='Ekipman (delici dahil)' WHERE kod='EKIPMAN' AND ad='Ekipman'")
    conn.executemany(
        "INSERT OR IGNORE INTO anahtar (kod, ad, tur, filtre, sistem) VALUES (?, ?, ?, ?, 1)",
        [(k, a, t, json.dumps(f, ensure_ascii=False) if f else None) for k, a, t, f in VARSAYILAN_ANAHTARLAR],
    )
    conn.commit()


def _sutun_ekle(conn, tablo, sutun, tur):
    """Eski veritabanlarına yeni sütun ekler (veri kaybı olmadan)."""
    if sutun not in {r[1] for r in conn.execute(f"PRAGMA table_info({tablo})")}:
        conn.execute(f"ALTER TABLE {tablo} ADD COLUMN {sutun} {tur}")


def donem_getir_veya_olustur(conn, yil: int, ay: int) -> int:
    satir = conn.execute("SELECT id FROM donem WHERE yil=? AND ay=?", (yil, ay)).fetchone()
    if satir:
        return satir["id"]
    cur = conn.execute("INSERT INTO donem (yil, ay) VALUES (?, ?)", (yil, ay))
    conn.commit()
    return cur.lastrowid


def onceki_donem(conn, donem_id: int):
    d = conn.execute("SELECT yil, ay FROM donem WHERE id=?", (donem_id,)).fetchone()
    satir = conn.execute(
        "SELECT id FROM donem WHERE (yil*12+ay) < (?*12+?) ORDER BY yil DESC, ay DESC LIMIT 1",
        (d["yil"], d["ay"]),
    ).fetchone()
    return satir["id"] if satir else None


def kar_merkezi_bul_veya_olustur(conn, ad: str, aile: str, gider_alir: int = 1, sira: int = 10, aciklama=None) -> int:
    satir = conn.execute("SELECT id FROM kar_merkezi WHERE aile=? AND ad=?", (aile, ad)).fetchone()
    if satir:
        return satir["id"]
    cur = conn.execute(
        "INSERT INTO kar_merkezi (ad, aile, gider_alir, sira, aciklama) VALUES (?, ?, ?, ?, ?)",
        (ad, aile, gider_alir, sira, aciklama),
    )
    return cur.lastrowid
