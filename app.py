import streamlit as st
from pypdf import PdfReader
from docx import Document
import re
import json

# =============================
# Dosyadan metin çıkarma
# =============================
def extract_text_from_pdf(uploaded_file) -> str:
    reader = PdfReader(uploaded_file)
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)

def extract_text_from_docx(uploaded_file) -> str:
    doc = Document(uploaded_file)
    return "\n".join([p.text for p in doc.paragraphs])

# =============================
# Test listesi bloğunu yakala
# =============================
def extract_test_block(t: str) -> str:
    headers = [
        "istenen test", "istenilen test", "calisilacak test",
        "calisilacak tetkik", "test listesi", "testler",
        "koagulasyon test", "calisilacak parametre"
    ]
    for h in headers:
        idx = t.find(h)
        if idx != -1:
            return t[idx: idx + 1200]
    return ""

# =============================
# Metin normalize
# =============================
def normalize_tr(text: str) -> str:
    text = text.lower()
    text = (text.replace("ı", "i")
            .replace("ş", "s")
            .replace("ğ", "g")
            .replace("ü", "u")
            .replace("ö", "o")
            .replace("ç", "c"))
    text = re.sub(r"\s+", " ", text)
    return text

# =============================
# Kural çıkarma
# =============================
def extract_rules_from_text(raw_text: str) -> dict:
    t = normalize_tr(raw_text)
    rules = {}

    # Kanal
    kanal = re.findall(r"en az\s*(\d+)\s*kanal", t)
    if kanal:
        rules["kanal_toplam_min"] = max(map(int, kanal))

    # Prob
    prob = re.findall(r"en az\s*(\d+)\s*prob", t)
    if prob:
        rules["prob_sayisi_min"] = max(map(int, prob))

    # Barkod
    if "barkod" in t:
        rules["barkod_okuma"] = True

    # Okuma yöntemi
    method = set()
    if "manyetik" in t:
        method.add("manyetik")
    if any(k in t for k in ["mekanik", "clot", "clot detection", "pihti"]):
        method.add("mekanik_clot")
    if method:
        rules["okuma_yontemi"] = list(method)

    # Test listesi
    test_block = extract_test_block(t)
    scan = test_block if test_block else t

    tests = {}
    if "pt" in scan:
        tests["PT"] = True
    if "aptt" in scan:
        tests["APTT"] = True
    if "fibrinojen" in scan:
        tests["Fibrinojen"] = True
    if "d-dimer" in scan or "ddimer" in scan:
        tests["D-Dimer"] = True

    if any(k in scan for k in ["faktor", "factor", "faktör"]):
        tests["Faktör"] = True
        rules["faktor_testi"] = (
            "opsiyonel_dis_lab"
            if any(k in scan for k in ["dis lab", "referans lab", "hizmet alimi"])
            else "zorunlu"
        )

    if tests:
        rules["istenen_testler"] = tests

    return rules

# =============================
# STREAMLIT UI
# =============================
st.set_page_config("İhaleBind", "🧬", layout="wide")

with open("devices.json", "r", encoding="utf-8") as f:
    devices = json.load(f)

st.title("🧬 İhaleBind")
st.caption("Şartnameyi okusun, kararı siz verin")

col1, col2 = st.columns(2)
with col1:
    marka = st.selectbox("Cihaz Markası", devices.keys())
with col2:
    model = st.selectbox("Cihaz Modeli", devices[marka].keys())

device = devices[marka][model]
st.info(f"Seçilen cihaz: **{marka} {model}**")

file = st.file_uploader("PDF veya Word yükleyin", ["pdf", "docx"])

if file:
    text = extract_text_from_pdf(file) if file.name.endswith("pdf") else extract_text_from_docx(file)

    if not text.strip():
        st.error("Metin çıkarılamadı (OCR gerekebilir)")
    else:
        rules = extract_rules_from_text(text)
        st.subheader("🧠 Şartnameden Yakalanan Kurallar")
        st.json(rules)
