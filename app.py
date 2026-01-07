import streamlit as st
from pypdf import PdfReader
from docx import Document
import re
import json

# ======================================================
# METİN ÇIKARMA
# ======================================================
def extract_text_from_pdf(file):
    reader = PdfReader(file)
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)

def extract_text_from_docx(file):
    doc = Document(file)
    return "\n".join(p.text for p in doc.paragraphs)

# ======================================================
# NORMALIZE
# ======================================================
def normalize_tr(text):
    text = text.lower()
    text = (
        text.replace("ı", "i")
        .replace("ş", "s")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ç", "c")
    )
    return re.sub(r"\s+", " ", text)

# ======================================================
# TEST LİSTESİ BLOĞU
# ======================================================
def extract_test_block(text):
    headers = [
        "istenen test",
        "calisilacak test",
        "test listesi",
        "testler",
        "calisilacak parametre"
    ]
    for h in headers:
        idx = text.find(h)
        if idx != -1:
            return text[idx:idx + 1200]
    return ""

# ======================================================
# ŞARTNAME KURAL ÇIKARICI (V1)
# ======================================================
def extract_rules(text):
    t = normalize_tr(text)
    rules = {}

    # Kanal
    kanal = re.findall(r"en az\s*(\d+)\s*kanal", t)
    if kanal:
        rules["kanal_min"] = max(map(int, kanal))

    # Prob
    prob = re.findall(r"en az\s*(\d+)\s*prob", t)
    if prob:
        rules["prob_min"] = max(map(int, prob))

    # Barkod
    if "barkod" in t:
        rules["barkod"] = True

    # Okuma yöntemi
    methods = []
    if "manyetik" in t:
        methods.append("manyetik")
    if any(k in t for k in ["mekanik", "clot", "pıhtı"]):
        methods.append("mekanik_clot")
    if methods:
        rules["okuma_yontemi"] = methods

    # Test listesi
    block = extract_test_block(t)
    scan = block if block else t

    tests = {}
    if "pt" in scan or "protrombin" in scan:
        tests["PT"] = True
    if "aptt" in scan:
        tests["APTT"] = True
    if "fibrinojen" in scan:
        tests["Fibrinojen"] = True
    if "d-dimer" in scan or "ddimer" in scan:
        tests["D-Dimer"] = True

    if any(k in scan for k in ["faktor", "factor"]):
        tests["Faktör"] = True
        if any(k in scan for k in ["dis lab", "referans lab", "gonderilebilir"]):
            rules["faktor_durumu"] = "opsiyonel"
        else:
            rules["faktor_durumu"] = "zorunlu"

    if tests:
        rules["istenen_testler"] = tests

    return rules

# ======================================================
# STREAMLIT UI
# ======================================================
st.set_page_config(
    page_title="İhaleBind",
    page_icon="🧬",
    layout="wide"
)

# ------------------------------------------------------
# CİHAZ KATALOĞU
# ------------------------------------------------------
with open("devices.json", "r", encoding="utf-8") as f:
    devices = json.load(f)

# ------------------------------------------------------
# HEADER
# ------------------------------------------------------
st.markdown("""
# 🧬 İhaleBind
### Şartnameyi okusun, kararı siz verin
""")

st.divider()

# ------------------------------------------------------
# MARKA / MODEL
# ------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    marka = st.selectbox("Cihaz Markası", list(devices.keys()))

with col2:
    model = st.selectbox("Cihaz Modeli", list(devices[marka].keys()))

selected_device = devices[marka][model]

st.info(f"Seçilen Cihaz: **{marka} {model}**")

# ------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------
with st.sidebar:
    st.header("📂 İhale Türleri")

    for ihale in [
        "Koagülasyon",
        "Biyokimya",
        "Hormon",
        "Kan Gazı",
        "İdrar",
        "Hemogram"
    ]:
        if ihale in selected_device["ihale_turleri"]:
            st.success(f"{ihale} İhalesi")
        else:
            st.error(f"{ihale} İhalesi")

# ------------------------------------------------------
# DOSYA YÜKLEME
# ------------------------------------------------------
st.subheader("📄 Teknik Şartname")

file = st.file_uploader("PDF veya Word yükleyin", type=["pdf", "docx"])

if file:
    if file.name.endswith(".pdf"):
        text = extract_text_from_pdf(file)
    else:
        text = extract_text_from_docx(file)

    if not text.strip():
        st.error("Metin çıkarılamadı (OCR gerekebilir)")
    else:
        st.success("Metin başarıyla çıkarıldı")

        rules = extract_rules(text)

        st.subheader("🧠 Şartnameden Yakalanan Kurallar")
        st.json(rules)

        st.subheader("🔍 Cihaz Özeti")
        koag = selected_device.get("koagulasyon", {})
        st.write("Toplam Kanal:", koag.get("kanal_toplam"))
        st.write("Prob Sayısı:", koag.get("prob_sayisi"))
        st.write("Barkod:", "Var" if koag.get("barkod") else "Yok")
        st.subheader("🧪 Çalışılabilen Testler")
        st.json(koag.get("testler", {}))
