import streamlit as st
from pypdf import PdfReader
from docx import Document
import json
import re

# --------------------------------------------------
# METİN ÇIKARMA
# --------------------------------------------------
def extract_text_from_pdf(file):
    reader = PdfReader(file)
    return "\n".join(page.extract_text() or "" for page in reader.pages)

def extract_text_from_docx(file):
    doc = Document(file)
    return "\n".join(p.text for p in doc.paragraphs)

# --------------------------------------------------
# NORMALIZE
# --------------------------------------------------
def normalize(text):
    text = text.lower()
    for a, b in [("ı","i"),("ş","s"),("ğ","g"),("ü","u"),("ö","o"),("ç","c")]:
        text = text.replace(a,b)
    return re.sub(r"\s+", " ", text)

# --------------------------------------------------
# ŞARTNAME ANALİZ
# --------------------------------------------------
def extract_rules(raw_text):
    t = normalize(raw_text)
    rules = {}

    # Barkod
    barkod = {}
    if "numune barkod" in t or "sample barcode" in t:
        barkod["numune"] = True
    if "reaktif barkod" in t or "kit barkod" in t:
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
    tests = {}
    if "pt" in t: tests["PT"] = True
    if "aptt" in t: tests["APTT"] = True
    if "fibrinojen" in t: tests["Fibrinojen"] = True
    if "d-dimer" in t or "ddimer" in t: tests["D-Dimer"] = True
    if any(k in t for k in ["faktor", "factor"]):
        tests["Faktör"] = True
    if tests:
        rules["istenen_testler"] = tests

    return rules

# --------------------------------------------------
# STREAMLIT UI
# --------------------------------------------------
st.set_page_config("İhaleBind", "🧬", layout="wide")

st.title("🧬 İhaleBind")
st.caption("Şartnameyi okusun, kararı siz verin")

# --------------------------------------------------
# CİHAZ KATALOĞU
# --------------------------------------------------
with open("devices.json", "r", encoding="utf-8") as f:
    devices = json.load(f)

col1, col2 = st.columns(2)

with col1:
    marka = st.selectbox("Cihaz Markası", devices.keys())
with col2:
    model = st.selectbox("Cihaz Modeli", devices[marka].keys())

device = devices[marka][model]["koagulasyon"]

st.info(f"Seçilen Cihaz: {marka} {model}")

# --------------------------------------------------
# DOSYA YÜKLEME
# --------------------------------------------------
file = st.file_uploader("Teknik şartname yükleyin (PDF / Word)", ["pdf","docx"])

if file:
    text = extract_text_from_pdf(file) if file.name.endswith(".pdf") else extract_text_from_docx(file)
    rules = extract_rules(text)

    st.subheader("📌 Şartnameden Yakalanan Kurallar")
    st.json(rules)

    st.subheader("🔍 Cihaz Özeti")
    st.write("Toplam Kanal:", device.get("kanal_toplam"))
    st.write("Prob Sayısı:", device.get("prob_sayisi"))

    st.subheader("📦 Barkod Durumu")
    st.json(device.get("barkod", {}))

    st.subheader("🧪 Çalışılabilen Testler")
    st.json(device.get("testler", {}))
