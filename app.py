import re
import json
import io
from typing import Dict, Any, List, Tuple

import streamlit as st
import pandas as pd

from pypdf import PdfReader
from docx import Document

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm


# ======================================================
# Helpers
# ======================================================
def normalize_tr(text: str) -> str:
    text = text.lower()
    repl = {"ı":"i","ş":"s","ğ":"g","ü":"u","ö":"o","ç":"c"}
    for k,v in repl.items():
        text = text.replace(k,v)
    text = re.sub(r"\s+", " ", text)
    return text

def extract_text(file) -> str:
    name = file.name.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(file)
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    elif name.endswith(".docx"):
        doc = Document(file)
        return "\n".join(p.text for p in doc.paragraphs)
    return ""

def bool_tr(v: Any) -> str:
    return "Var" if bool(v) else "Yok"

def safe_int(v: Any) -> int | None:
    try:
        return int(v)
    except:
        return None

def list_to_text(v: Any) -> str:
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)

def tests_to_text(test_map: Dict[str, Any]) -> str:
    # device testler: bool veya "manyetik/optik"
    if not isinstance(test_map, dict) or not test_map:
        return "-"
    out = []
    for k,v in test_map.items():
        if isinstance(v, bool):
            if v:
                out.append(k)
        elif isinstance(v, str):
            out.append(f"{k} ({v})")
        else:
            out.append(k)
    return ", ".join(out) if out else "-"

def req_missing_msg() -> Tuple[str,str]:
    return ("Bilgi Yok", "Şartnamede bu madde bulunamadı, lütfen manuel kontrol ediniz.")

def dev_missing_msg() -> Tuple[str,str]:
    return ("Bilgi Yok", "Cihaz kataloğunda veri yok, lütfen manuel kontrol ediniz.")


# ======================================================
# Section Extraction (Koagülasyon)
# ======================================================
def find_section(text: str, start_key: str, end_keys: List[str]) -> str:
    """
    start_key: aranan başlangıç başlığı
    end_keys: bitişi belirleyen başlıklar (bulunursa orada keser)
    """
    t = normalize_tr(text)
    s = t.find(normalize_tr(start_key))
    if s == -1:
        return ""
    e = len(t)
    for ek in end_keys:
        idx = t.find(normalize_tr(ek), s + 10)
        if idx != -1:
            e = min(e, idx)
    return t[s:e]

def split_group_blocks(coag_tech_block: str) -> Dict[str,str]:
    """
    A GRUBU / B GRUBU bloklarını ayırır.
    """
    t = coag_tech_block
    a_key = "a grubu"
    b_key = "b grubu"
    ia = t.find(a_key)
    ib = t.find(b_key)

    out = {"A": "", "B": ""}
    if ia != -1 and ib != -1:
        if ia < ib:
            out["A"] = t[ia:ib]
            out["B"] = t[ib:]
        else:
            out["B"] = t[ib:ia]
            out["A"] = t[ia:]
    elif ia != -1:
        out["A"] = t[ia:]
    elif ib != -1:
        out["B"] = t[ib:]
    return out

def parse_numbered_items(block: str) -> List[Dict[str,Any]]:
    """
    '1.' ile başlayan maddeleri yakalar.
    """
    items = []
    # satır başlarında 1. 2. vb yakala
    # DOTALL: madde metni bir sonraki numaraya kadar
    pattern = r"(?:^|\n)\s*(\d{1,3})\.\s*(.*?)(?=(?:\n\s*\d{1,3}\.\s)|$)"
    for m in re.finditer(pattern, block, flags=re.DOTALL):
        no = m.group(1).strip()
        body = m.group(2).strip()
        body = re.sub(r"\s+", " ", body)
        items.append({"no": no, "text": body})
    return items

def extract_kit_block(full_text: str) -> str:
    # 6.C - KİTLERİN ÖZELLİKLERİ
    return find_section(
        full_text,
        "6.C- KİTLERİN ÖZELLİKLERİ",
        ["6.D-", "6.D –", "6.D- ÜCRET", "6.d-"]
    )

def extract_sarf_block(full_text: str) -> str:
    # 6.D- ÜCRET TALEP EDİLMEDEN VERİLECEK...
    return find_section(
        full_text,
        "6.D- ÜCRET TALEP EDİLMEDEN VERİLECEK",
        ["7.", "6.e", "6.E", "SON", "EK’li"]
    )


# ======================================================
# Requirement Extraction per item (A/B)
# ======================================================
def req_from_item(item_text: str) -> Dict[str,Any]:
    """
    Madde metninden gereksinim anahtarları çıkarır.
    """
    t = normalize_tr(item_text)
    r: Dict[str,Any] = {}

    # Kanal
    m = re.search(r"en az\s*(\d+)\s*(adet\s*)?(olcum|test|reaksiyon)?\s*kanal", t)
    if m:
        r["kanal_min"] = int(m.group(1))

    # Prob
    m = re.search(r"en az\s*(\d+)\s*\(?iki\)?\s*probl|en az\s*(\d+)\s*probl|en az\s*(\d+)\s*prob", t)
    if m:
        nums = [x for x in m.groups() if x]
        if nums:
            r["prob_min"] = int(nums[0])

    # Hız test/saat
    m = re.search(r"en az\s*(\d+)\s*test\s*/\s*saat", t)
    if m:
        r["hiz_min"] = int(m.group(1))

    # Barkod (dahili/harici)
    if "barkod" in t:
        r["barkod_genel"] = True
    if "dahili barkod" in t:
        r["barkod_dahili"] = True
    if "primer" in t and "barkod" in t:
        r["barkod_numune"] = True
    if "reaktif" in t and "barkod" in t:
        r["barkod_reaktif"] = True

    # LIS çift yön
    if "iki yonlu" in t and "veri transfer" in t:
        r["lis_cift_yon"] = True

    # QC
    if "kalite kontrol" in t or "internal kalite kontrol" in t:
        r["qc_program"] = True

    # Sonuç hafızası
    if "hafiza" in t and "sakla" in t:
        r["sonuc_hafiza"] = True

    # Seviye sensörü / detektör
    if "seviye" in t and ("detektor" in t or "detektoru" in t or "sensor" in t):
        r["seviye_sensor"] = True

    # Kapak delme
    if "kapak" in t and ("del" in t or "piercing" in t):
        r["kapak_delme"] = True

    # Okuma yöntemi: koagülometri / clotting / kromojenik / immünolojik
    if "koagulometri" in t or "clotting" in t or "clot" in t:
        r["okuma_clot"] = True
    if "kromojenik" in t:
        r["okuma_kromojenik"] = True
    if "immunolojik" in t or "immünolojik" in t:
        r["okuma_immunolojik"] = True

    # Testler
    if re.search(r"\bpt\b", t) or "protrombin" in t:
        r["test_pt"] = True
    if "aptt" in t:
        r["test_aptt"] = True
    if "fibrinojen" in t:
        r["test_fibrinojen"] = True
    if "d-dimer" in t or "ddimer" in t:
        r["test_ddimer"] = True
    if "faktor" in t or "factor" in t:
        r["test_faktor"] = True

    # Yarı otomatik / açık sistem
    if "yari otomatik" in t or "yarı otomatik" in t:
        r["otomasyon"] = "yari"
    if "tam otomatik" in t:
        r["otomasyon"] = "tam"
    if "acik sistem" in t or "açik sistem" in t or "açık sistem" in t:
        r["acik_sistem"] = True

    # Tek kullanımlık küvet
    if "tek kullanimlik" in t and "kuvet" in t:
        r["tek_kullanim_küvet"] = True

    # İnkübasyon / reaktif soğutucu
    if "inkubasyon" in t and "37" in t:
        r["inkubasyon_37c"] = True
    if "reaktif sogutucu" in t or ("reaktif" in t and "sogutucu" in t):
        r["reaktif_sogutucu"] = True

    return r


# ======================================================
# Evaluate a single requirement against device
# ======================================================
def eval_req(req: Dict[str,Any], device: Dict[str,Any]) -> Tuple[str,str]:
    """
    Returns (Sonuç, Açıklama) with:
    - Uygun
    - Zeyil
    - Uygun Değil
    - Bilgi Yok
    """
    # if requirement empty -> bilgi yok
    if not req:
        return req_missing_msg()

    # otomasyon
    if "otomasyon" in req:
        dev_auto = device.get("otomasyon")
        if dev_auto is None:
            return dev_missing_msg()
        if req["otomasyon"] == dev_auto:
            return ("Uygun", f"Otomasyon: şartname {req['otomasyon']} / cihaz {dev_auto}")
        # yarı vs tam mismatch => uygun değil
        return ("Uygun Değil", f"Otomasyon uyuşmuyor: şartname {req['otomasyon']} / cihaz {dev_auto}")

    # kanal
    if "kanal_min" in req:
        dv = safe_int(device.get("kanal_toplam"))
        if dv is None:
            return dev_missing_msg()
        if dv >= req["kanal_min"]:
            return ("Uygun", f"Kanal: şartname ≥{req['kanal_min']} / cihaz {dv}")
        return ("Uygun Değil", f"Kanal: şartname ≥{req['kanal_min']} / cihaz {dv}")

    # prob
    if "prob_min" in req:
        dv = safe_int(device.get("prob_sayisi"))
        if dv is None:
            return dev_missing_msg()
        if dv >= req["prob_min"]:
            return ("Uygun", f"Prob: şartname ≥{req['prob_min']} / cihaz {dv}")
        return ("Uygun Değil", f"Prob: şartname ≥{req['prob_min']} / cihaz {dv}")

    # hız
    if "hiz_min" in req:
        dv = safe_int(device.get("hiz_test_saat"))
        if dv is None or dv == 0:
            return dev_missing_msg()
        if dv >= req["hiz_min"]:
            return ("Uygun", f"Hız: şartname ≥{req['hiz_min']} test/saat / cihaz {dv}")
        return ("Uygun Değil", f"Hız: şartname ≥{req['hiz_min']} test/saat / cihaz {dv}")

    # barkod
    if req.get("barkod_numune") or req.get("barkod_genel") or req.get("barkod_dahili") or req.get("barkod_reaktif"):
        dev_b = device.get("barkod", {})
        if not isinstance(dev_b, dict):
            return dev_missing_msg()

        # numune barkod yoksa -> uygun değil
        if req.get("barkod_numune") or req.get("barkod_genel") or req.get("barkod_dahili"):
            if not dev_b.get("numune", False):
                return ("Uygun Değil", "Numune barkod okuyucu yok.")
        # reaktif barkod isteniyorsa -> yoksa zeyil
        if req.get("barkod_reaktif"):
            if not dev_b.get("reaktif", False):
                return ("Zeyil", "Reaktif barkod yok (zeyil/açıklama önerilir).")
        # dahili isteniyorsa -> yoksa zeyil
        if req.get("barkod_dahili"):
            if not dev_b.get("dahili", False):
                return ("Zeyil", "Dahili barkod şartı için eşdeğer çözüm/zeyil önerilir.")
        return ("Uygun", "Barkod gereksinimi karşılanıyor.")

    # lis
    if req.get("lis_cift_yon"):
        dv = device.get("lis_cift_yon")
        if dv is None:
            return dev_missing_msg()
        return ("Uygun", "LIS çift yön destekli.") if dv else ("Uygun Değil", "LIS çift yön yok.")

    # qc
    if req.get("qc_program"):
        dv = device.get("qc_program")
        if dv is None:
            return dev_missing_msg()
        return ("Uygun", "QC programı var.") if dv else ("Zeyil", "QC programı yok / eşdeğer yöntem açıklaması gerekebilir.")

    # hafıza
    if req.get("sonuc_hafiza"):
        dv = device.get("sonuc_hafiza")
        if dv is None:
            return dev_missing_msg()
        return ("Uygun", "Sonuç hafızası var.") if dv else ("Zeyil", "Sonuç hafızası için zeyil/açıklama gerekebilir.")

    # seviye sensörü
    if req.get("seviye_sensor"):
        dv = device.get("seviye_sensor")
        if dv is None:
            return dev_missing_msg()
        return ("Uygun", "Seviye sensörü var.") if dv else ("Zeyil", "Seviye sensörü için zeyil/açıklama gerekebilir.")

    # kapak delme
    if req.get("kapak_delme"):
        dv = device.get("kapak_delme")
        if dv is None:
            return dev_missing_msg()
        return ("Uygun", "Kapak delme var.") if dv else ("Uygun Değil", "Kapak delme yok.")

    # inkübasyon
    if req.get("inkubasyon_37c"):
        dv = device.get("inkubasyon_37c")
        if dv is None:
            return dev_missing_msg()
        return ("Uygun", "37°C inkübasyon mevcut.") if dv else ("Uygun Değil", "37°C inkübasyon yok.")

    if req.get("reaktif_sogutucu"):
        dv = device.get("reaktif_sogutucu")
        if dv is None:
            return dev_missing_msg()
        return ("Uygun", "Reaktif soğutucu var.") if dv else ("Uygun Değil", "Reaktif soğutucu yok.")

    # testler
    # (tek maddede)
    if any(k in req for k in ["test_pt","test_aptt","test_fibrinojen","test_ddimer","test_faktor"]):
        dev_tests = device.get("testler", {})
        if not isinstance(dev_tests, dict):
            return dev_missing_msg()

        missing_tests = []
        if req.get("test_pt") and (dev_tests.get("PT") in [False, None]):
            missing_tests.append("PT")
        if req.get("test_aptt") and (dev_tests.get("APTT") in [False, None]):
            missing_tests.append("APTT")
        if req.get("test_fibrinojen") and (dev_tests.get("Fibrinojen") in [False, None]):
            missing_tests.append("Fibrinojen")
        if req.get("test_ddimer") and (dev_tests.get("D-Dimer") in [False, None]):
            missing_tests.append("D-Dimer")
        if req.get("test_faktor") and (dev_tests.get("Faktor") in [False, None]):
            # faktör çoğu zaman dış lab -> zeyil
            return ("Zeyil", "Faktör testleri için dış lab/referans lab açıklaması önerilir.")

        if missing_tests:
            return ("Uygun Değil", "Eksik test: " + ", ".join(missing_tests))
        return ("Uygun", "İstenen testler karşılanıyor.")

    # okuma yöntemi - clot detection
    if req.get("okuma_clot"):
        # cihaz manyetik/optik kanalı varsa clot kabul
        if device.get("kanal_manyetik") or device.get("kanal_optik"):
            return ("Uygun", "Koagülometri/clot detection şartı cihazda sağlanır (manyetik/optik).")
        return ("Bilgi Yok", "Cihaz okuma kanalı verisi eksik, manuel kontrol ediniz.")

    # hiçbir anahtar eşleşmediyse
    return req_missing_msg()


# ======================================================
# Zeyil generator
# ======================================================
def zeyil_template(item_no: str, item_text: str, reason: str) -> str:
    return (
        f"Zeyil Önerisi (Madde {item_no}):\n"
        f"{item_text}\n\n"
        f"Açıklama/Zeyil:\n{reason}\n"
    )

# ======================================================
# PDF report generator
# ======================================================
def pdf_report(title: str, device_name: str, overall: str, df: pd.DataFrame, zeyils: List[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    x = 18*mm
    y = h - 18*mm

    def line(txt, bold=False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        for t in txt.split("\n"):
            if y < 20*mm:
                c.showPage()
                y = h - 18*mm
            c.drawString(x, y, t[:120])
            y -= 14

    line("İhaleBind - Uygunluk Raporu", bold=True)
    line(f"Rapor: {title}")
    line(f"Cihaz: {device_name}")
    line(f"Genel Sonuç: {overall}", bold=True)
    y -= 10

    line("Karşılaştırma Tablosu", bold=True)
    for _, r in df.iterrows():
        line(f"Madde {r['Madde No']} | Sonuç: {r['Sonuç']} | {r['Açıklama']}")
        line(f"Şartname: {r['Şartname']}")
        line(f"Cihaz: {r['Cihaz']}")
        y -= 6

    if zeyils:
        line("Zeyil Önerileri", bold=True)
        for z in zeyils:
            line(z)
            y -= 8

    c.save()
    out = buf.getvalue()
    buf.close()
    return out


# ======================================================
# UI
# ======================================================
st.set_page_config(page_title="İhaleBind", page_icon="🧬", layout="wide")

with open("devices.json", "r", encoding="utf-8") as f:
    DEV = json.load(f)

st.title("🧬 İhaleBind")
st.caption("Şartnameyi okusun, kararı siz verin")

# Sidebar: ihale seçimi
with st.sidebar:
    st.header("📂 İhale Türleri")
    ihale = st.radio("İhale", ALL_IHALELER, index=0)

# Cihaz filtreleme
filtered_brands = {}
for brand, models in DEV.items():
    kept = {m:mb for m,mb in models.items() if ihale in (mb.get("ihale_turleri", []) or [])}
    if kept:
        filtered_brands[brand] = kept

if not filtered_brands:
    st.warning(f"'{ihale}' ihalesi için cihaz kataloğu tanımlı değil. devices.json'e bu ihale türünü ekleyince otomatik gelir.")
    st.stop()

c1, c2 = st.columns(2)
with c1:
    brand = st.selectbox("Cihaz Markası", list(filtered_brands.keys()))
with c2:
    model = st.selectbox("Cihaz Modeli", list(filtered_brands[brand].keys()))

model_block = filtered_brands[brand][model]
device = model_block.get("koagulasyon", {})

st.info(f"Seçilen Cihaz: **{brand} {model}**")

# Upload
file = st.file_uploader("Teknik Şartname (PDF / DOCX)", type=["pdf","docx"])

if not file:
    st.stop()

raw = extract_text(file)
if not raw.strip():
    st.error("Metin çıkarılamadı (OCR gerekebilir).")
    st.stop()

st.success("Metin başarıyla çıkarıldı ✅")

# ===== Koagülasyon teknik bölümü bul
# sadece KOAGÜLASYON + "KİT İLE BİRLİKTE VERİLECEK CİHAZLARIN TEKNİK ÖZELLİKLERİ" altı
coag_root = find_section(
    raw,
    "SONUÇ KARŞILIĞI KOAGÜLASYON TESTLERİ HİZMET ALIMI TEKNİK ŞARTNAMESİ",
    ["SONUÇ KARŞILIĞI", "2-", "3-", "1-"]
)

tech_block = find_section(
    coag_root if coag_root else raw,
    "KİT İLE BİRLİKTE VERİLECEK CİHAZLARIN TEKNİK ÖZELLİKLERİ",
    ["6.C-", "6.D-", "KİTLERİN ÖZELLİKLERİ", "ÜCRET TALEP"]
)

groups = split_group_blocks(normalize_tr(tech_block)) if tech_block else {"A":"", "B":""}

items_A = parse_numbered_items(groups.get("A",""))
items_B = parse_numbered_items(groups.get("B",""))

kit_block = extract_kit_block(raw)
sarf_block = extract_sarf_block(raw)

# Tabs
tabA, tabB, tabK, tabS, tabR = st.tabs([
    "A Grubu Cihaz Teknik",
    "B Grubu Cihaz Teknik",
    "6.C Kit Özellikleri",
    "6.D Sarf & Hizmet",
    "Rapor"
])

def build_table(items: List[Dict[str,Any]], device: Dict[str,Any]) -> Tuple[pd.DataFrame, List[str], str]:
    rows = []
    zeyils = []
    statuses = []

    for it in items:
        req = req_from_item(it["text"])
        sonuc, aciklama = eval_req(req, device)

        # Kullanıcı dostu cihaz değeri
        # (madde içinden anlaşılan anahtarlar üzerinden)
        dev_view = "-"
        if "kanal_min" in req:
            dev_view = str(device.get("kanal_toplam", "-"))
        elif "prob_min" in req:
            dev_view = str(device.get("prob_sayisi", "-"))
        elif "hiz_min" in req:
            dev_view = str(device.get("hiz_test_saat", "-"))
        elif req.get("kapak_delme"):
            dev_view = bool_tr(device.get("kapak_delme"))
        elif req.get("barkod_genel") or req.get("barkod_numune") or req.get("barkod_reaktif") or req.get("barkod_dahili"):
            b = device.get("barkod", {})
            dev_view = f"Numune: {bool_tr(b.get('numune'))}, Reaktif: {bool_tr(b.get('reaktif'))}, Dahili: {bool_tr(b.get('dahili'))}"
        elif req.get("lis_cift_yon"):
            dev_view = bool_tr(device.get("lis_cift_yon"))
        elif req.get("qc_program"):
            dev_view = bool_tr(device.get("qc_program"))
        elif req.get("seviye_sensor"):
            dev_view = bool_tr(device.get("seviye_sensor"))
        elif req.get("inkubasyon_37c"):
            dev_view = bool_tr(device.get("inkubasyon_37c"))
        elif req.get("reaktif_sogutucu"):
            dev_view = bool_tr(device.get("reaktif_sogutucu"))
        elif any(k in req for k in ["test_pt","test_aptt","test_fibrinojen","test_ddimer","test_faktor"]):
            dev_view = tests_to_text(device.get("testler", {}))

        req_view = it["text"]

        rows.append({
            "Madde No": it["no"],
            "Şartname": req_view,
            "Cihaz": dev_view,
            "Sonuç": sonuc,
            "Açıklama": aciklama
        })
        statuses.append(sonuc)

        if sonuc == "Zeyil":
            zeyils.append(zeyil_template(it["no"], it["text"], aciklama))

    # overall
    if "Uygun Değil" in statuses:
        overall = "🔴 Uygun Değil"
    elif "Zeyil" in statuses:
        overall = "🟡 Zeyil ile Uygun"
    else:
        overall = "🟢 Uygun"

    return pd.DataFrame(rows), zeyils, overall

with tabA:
    st.subheader("A Grubu – Cihaz Teknik Maddeleri (Madde bazlı)")
    if not items_A:
        st.info("A Grubu maddeleri bu şartnamede bulunamadı. Başlıklar farklı olabilir.")
    dfA, zA, overallA = build_table(items_A, device)
    st.dataframe(dfA, use_container_width=True)
    st.markdown(f"### Genel Sonuç: {overallA}")
    if zA:
        st.markdown("### Otomatik Zeyil Önerileri")
        for i, z in enumerate(zA, 1):
            st.text_area(f"Zeyil #{i}", z, height=160)

with tabB:
    st.subheader("B Grubu – Cihaz Teknik Maddeleri (Madde bazlı)")
    if not items_B:
        st.info("B Grubu maddeleri bu şartnamede bulunamadı. Başlıklar farklı olabilir.")
    dfB, zB, overallB = build_table(items_B, device)
    st.dataframe(dfB, use_container_width=True)
    st.markdown(f"### Genel Sonuç: {overallB}")
    if zB:
        st.markdown("### Otomatik Zeyil Önerileri")
        for i, z in enumerate(zB, 1):
            st.text_area(f"Zeyil #{i}", z, height=160)

with tabK:
    st.subheader("6.C – Kitlerin Özellikleri (metin)")
    if kit_block:
        st.text_area("Kit Bölümü", kit_block, height=400)
    else:
        st.info("6.C Kit bölümü bulunamadı.")

with tabS:
    st.subheader("6.D – Sarf & Hizmet Maddeleri (metin)")
    if sarf_block:
        st.text_area("Sarf Bölümü", sarf_block, height=400)
    else:
        st.info("6.D Sarf bölümü bulunamadı.")

