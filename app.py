import streamlit as st
from pypdf import PdfReader
from docx import Document
import re
import json
import os

# ======================================================
# DOSYA YOLU (Cloud + Local uyumlu)
# ======================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEVICE_PATH = os.path.join(BASE_DIR, "devices.json")

# ======================================================
# METİN ÇIKARMA
# ======================================================
def extract_text_from_pdf(file):
    reader = PdfReader(file)
    return "\n".join(page.extract_text() or "" for page in reader.pages)

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
# ŞARTNAME KURAL YAKALAYICI (V1)
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

    # Barkod detay
    barkod = {}
    if any(k in t for k in ["numune barkod", "sample barcode", "hasta barkod", "tup barkod"]):
        barkod["numune"] = True
    if any(k in t for k in ["reaktif barkod", "kit barkod", "reagent barcode"]):
        barkod["reaktif"] = True
    if barkod:
        rules["barkod"] = barkod

    # Okuma yöntemi
    methods = []
    if "manyetik" in t:
        methods.append("manyetik")
    if any(k in t for k in ["mekanik", "clot", "pihti"]):
        methods.append("mekanik_clot")
    if methods:
        rules["okuma_yontemi"] = methods

    # Testler
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
        rules["faktor_durumu"] = (
            "opsiyonel_dis_lab"
            if any(k in scan for k in ["dis lab", "referans lab", "gonderilebilir"])
            else "zorunlu"
        )

    if tests:
        rules["istenen_testler"] = tests

    return rules

# ======================================================
# STREAMLIT UI
# ======================================================
st.set_page_config(page_title="İhaleBind", page_icon="🧬", layout="wide")

# ======================================================
# CİHAZ KATALOĞU
# ======================================================
with open(DEVICE_PATH, "r", encoding="utf-8") as f:
    devices = json.load(f)

# ======================================================
# HEADER
# ======================================================
st.markdown("""
# 🧬 İhaleBind
### Şartnameyi okusun, kararı siz verin
""")

st.divider()

# ======================================================
# ÜST BAR – MARKA / MODEL
# ======================================================
col1, col2 = st.columns(2)

with col1:
    marka = st.selectbox("Cihaz Markası", list(devices.keys()))

with col2:
    model = st.selectbox("Cihaz Modeli", list(devices[marka].keys()))

selected_device = devices[marka][model]
st.info(f"Seçilen Cihaz: **{marka} {model}**")

# ======================================================
# SOL MENÜ – İHALE TÜRLERİ
# ======================================================
with st.sidebar:
    st.header("📂 İhale Türleri")
    for ihale in ["Koagülasyon", "Biyokimya", "Hormon", "Kan Gazı", "İdrar", "Hemogram"]:
        if ihale in selected_device["ihale_turleri"]:
            st.success(f"{ihale} İhalesi")
        else:
            st.error(f"{ihale} İhalesi")

# ======================================================
# DOSYA YÜKLEME
# ======================================================
st.subheader("📄 Teknik Şartname")

file = st.file_uploader("PDF veya Word yükleyin", type=["pdf", "docx"])

if file:
    text = extract_text_from_pdf(file) if file.name.endswith(".pdf") else extract_text_from_docx(file)

    if not text.strip():
        st.error("Metin çıkarılamadı (OCR gerekebilir)")
    else:
        st.success("Metin başarıyla çıkarıldı")

        rules = extract_rules(text)
        st.subheader("🧠 Şartnameden Yakalanan Kurallar")
        st.json(rules)

        # ======================================================
        # CİHAZ ÖZETİ
        # ======================================================
        st.subheader("🔍 Cihaz Özeti")
        koag = selected_device.get("koagulasyon", {})

        st.write("Toplam Kanal:", koag.get("kanal_toplam"))
        st.write("Prob Sayısı:", koag.get("prob_sayisi"))
        st.write("Kapak Delme:", "Var" if koag.get("kapak_delme") else "Yok")

        barkod = koag.get("barkod", {})
        st.write("Numune Barkod:", "Var" if barkod.get("numune") else "Yok")
        st.write("Reaktif Barkod:", "Var" if barkod.get("reaktif") else "Yok")

        st.subheader("🧪 Çalışılabilen Testler")
        st.json(koag.get("testler", {}))
