import streamlit as st
import json
import re
from pypdf import PdfReader
from docx import Document
from typing import Dict, Any

# ======================================================
# CONFIG
# ======================================================
ALL_IHALELER = [
    "Koagülasyon",
    "Biyokimya",
    "Hormon",
    "Kan Gazı",
    "İdrar",
    "Hemogram",
]

# ======================================================
# FILE TEXT EXTRACT
# ======================================================
def extract_text(file) -> str:
    name = file.name.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(file)
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    if name.endswith(".docx"):
        doc = Document(file)
        return "\n".join(p.text for p in doc.paragraphs)
    return ""

# ======================================================
# NORMALIZE
# ======================================================
def normalize(text: str) -> str:
    text = text.lower()
    for a, b in [("ı","i"), ("ş","s"), ("ğ","g"), ("ü","u"), ("ö","o"), ("ç","c")]:
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip()

# ======================================================
# RULE EXTRACTION
# ======================================================
def extract_rules_from_text(raw: str) -> Dict[str, Any]:
    t = normalize(raw)
    rules: Dict[str, Any] = {}

    # Kanal
    kanal = re.findall(r"en az\s*(\d+)\s*kanal", t)
    if kanal:
        rules["kanal_min"] = max(map(int, kanal))

    # Prob
    prob = re.findall(r"en az\s*(\d+)\s*prob", t)
    if prob:
        rules["prob_min"] = max(map(int, prob))

    # Kapak delme
    if "kapak delme" in t or "piercing" in t:
        rules["kapak_delme"] = True

    # Barkod
    barkod = {}
    if any(k in t for k in ["numune barkod", "hasta barkod", "tup barkod"]):
        barkod["numune"] = True
    if any(k in t for k in ["reaktif barkod", "kit barkod"]):
        barkod["reaktif"] = True
    if barkod:
        rules["barkod"] = barkod

    # Okuma yöntemi (clot)
    if any(k in t for k in ["koagulometri", "clot", "clotting", "pıhtı"]):
        rules["okuma"] = "clot_detection"

    # Testler
    tests = {}
    if re.search(r"\bpt\b|protrombin", t):
        tests["PT"] = True
    if re.search(r"\baptt\b|a\s*p\s*t\s*t", t):
        tests["APTT"] = True
    if "fibrinojen" in t:
        tests["Fibrinojen"] = True
    if re.search(r"d[- ]?dimer|ddimer", t):
        tests["D-Dimer"] = True
    if re.search(r"faktor|faktör|factor", t):
        tests["Faktor"] = True

    if tests:
        rules["testler"] = tests

    return rules

# ======================================================
# EVALUATION HELPERS
# ======================================================
def missing():
    return "Bilgi Yok", "Şartnamede bulunamadı, lütfen manuel kontrol ediniz."

def evaluate_barkod(req, dev):
    if not req:
        return missing()
    if req.get("numune") and not dev.get("numune"):
        return "Uygun Değil", "Numune barkod okuyucu yok."
    if req.get("reaktif") and not dev.get("reaktif"):
        return "Zeyil", "Reaktif barkod yok (zeyil önerilir)."
    return "Uygun", "Barkod gereksinimleri karşılanıyor."

def evaluate_okuma(device, rules):
    if "okuma" not in rules:
        return missing()
    # manyetik / optik kanallar clot algılamaya uygundur
    if device.get("kanal_manyetik") or device.get("kanal_optik"):
        return "Uygun", "Cihaz clot (pıhtı) algılamasına uygundur."
    return "Bilgi Yok", "Okuma yöntemi cihazdan doğrulanamadı."

def evaluate_tests(device_tests, rules):
    if "testler" not in rules:
        return missing()
    missing_tests = []
    for t in rules["testler"]:
        if not device_tests.get(t):
            missing_tests.append(t)
    if not missing_tests:
        return "Uygun", "Tüm istenen testler mevcut."
    return "Zeyil", f"Eksik testler: {', '.join(missing_tests)}"

# ======================================================
# UI
# ======================================================
st.set_page_config("İhaleBind", "🧬", layout="wide")
st.title("🧬 İhaleBind")
st.caption("Şartnameyi okusun, kararı siz verin")

with open("devices.json", "r", encoding="utf-8") as f:
    DEVICES = json.load(f)

# Sidebar
with st.sidebar:
    st.header("📂 İhale Türleri")
    ihale = st.radio("İhale", ALL_IHALELER, index=0)

# Filtre
filtered = {}
for brand, models in DEVICES.items():
    kept = {m:v for m,v in models.items() if ihale in v.get("ihale_turleri", [])}
    if kept:
        filtered[brand] = kept

if not filtered:
    st.warning("Bu ihale için cihaz tanımlı değil.")
    st.stop()

c1, c2 = st.columns(2)
with c1:
    marka = st.selectbox("Cihaz Markası", filtered.keys())
with c2:
    model = st.selectbox("Cihaz Modeli", filtered[marka].keys())

device = filtered[marka][model]["koagulasyon"]

st.info(f"Seçilen Cihaz: **{marka} {model}**")

# Upload
file = st.file_uploader("Teknik Şartname (PDF / DOCX)", ["pdf", "docx"])

if file:
    text = extract_text(file)
    st.success("Metin başarıyla çıkarıldı")

    rules = extract_rules_from_text(text)

    st.subheader("🧠 Şartnameden Yakalanan Kurallar")
    st.json(rules)

    rows = []

    # Kanal
    if "kanal_min" in rules:
        res = "Uygun" if device.get("kanal_toplam",0) >= rules["kanal_min"] else "Uygun Değil"
        rows.append(("Kanal Sayısı", f"≥ {rules['kanal_min']}", device.get("kanal_toplam"), res, ""))

    # Prob
    if "prob_min" in rules:
        res = "Uygun" if device.get("prob_sayisi",0) >= rules["prob_min"] else "Uygun Değil"
        rows.append(("Prob Sayısı", f"≥ {rules['prob_min']}", device.get("prob_sayisi"), res, ""))

    # Kapak delme
    if "kapak_delme" in rules:
        res = "Uygun" if device.get("kapak_delme") else "Uygun Değil"
        rows.append(("Kapak Delme", "Var", device.get("kapak_delme"), res, ""))

    # Barkod
    b_res, b_exp = evaluate_barkod(rules.get("barkod"), device.get("barkod", {}))
    rows.append(("Barkod", rules.get("barkod"), device.get("barkod"), b_res, b_exp))

    # Okuma
    o_res, o_exp = evaluate_okuma(device, rules)
    rows.append(("Okuma Yöntemi", rules.get("okuma"), "Manyetik/Optik", o_res, o_exp))

    # Testler
    t_res, t_exp = evaluate_tests(device.get("testler", {}), rules)
    rows.append(("Testler", rules.get("testler"), device.get("testler"), t_res, t_exp))

    st.subheader("📊 Şartname – Cihaz Karşılaştırma Tablosu")
    st.table(rows)

    final = "Uygun"
    if any(r[3] == "Uygun Değil" for r in rows):
        final = "Uygun Değil"
    elif any(r[3] == "Zeyil" for r in rows):
        final = "Zeyil ile Uygun"

    st.subheader("✅ Genel Sonuç")
    st.success(final)
