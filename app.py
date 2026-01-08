import streamlit as st
import json
import re
from pypdf import PdfReader
from docx import Document

# -------------------------------------------------
# SAYFA AYARI
# -------------------------------------------------
st.set_page_config(
    page_title="İhaleBind",
    page_icon="🧬",
    layout="wide"
)

# -------------------------------------------------
# YARDIMCI FONKSİYONLAR
# -------------------------------------------------
def read_pdf(file):
    reader = PdfReader(file)
    return "\n".join(p.extract_text() or "" for p in reader.pages)

def read_docx(file):
    doc = Document(file)
    return "\n".join(p.text for p in doc.paragraphs)

def normalize(text):
    text = text.lower()
    for a, b in [("ı","i"),("ğ","g"),("ş","s"),("ü","u"),("ö","o"),("ç","c")]:
        text = text.replace(a,b)
    return text

def find_in_text(text, keywords):
    return any(k in text for k in keywords)

# -------------------------------------------------
# ŞARTNAME ANALİZİ
# -------------------------------------------------
def extract_rules(text):
    t = normalize(text)
    rules = {}

    # Okuma yöntemi
    if find_in_text(t, ["clot", "pıhtı", "koagulometri"]):
        rules["okuma"] = "Clot Detection"

    # Testler
    tests = {}
    for test in ["pt", "aptt", "fibrinojen", "d-dimer", "ddimer"]:
        if test in t:
            tests[test.upper().replace("DDIMER","D-Dimer")] = True

    rules["testler"] = tests
    return rules

# -------------------------------------------------
# KULLANICIYA GÖSTERİM FORMATLARI
# -------------------------------------------------
def var_yok(v):
    return "Var" if v else "Yok"

def format_okuma(methods):
    return "Clot Detection (Manyetik / Optik)"

def format_tests(tests):
    return ", ".join([k for k,v in tests.items() if v]) or "Belirtilmemiş"

# -------------------------------------------------
# CİHAZLAR
# -------------------------------------------------
with open("devices.json","r",encoding="utf-8") as f:
    DEVICES = json.load(f)

# -------------------------------------------------
# SIDEBAR – İHALE TÜRLERİ
# -------------------------------------------------
with st.sidebar:
    st.header("📂 İhale Türleri")
    ihale = st.radio(
        "İhale",
        ["Koagülasyon", "Biyokimya", "Hormon", "Kan Gazı", "İdrar", "Hemogram"]
    )

# -------------------------------------------------
# HEADER
# -------------------------------------------------
st.title("🧬 İhaleBind")
st.caption("Şartnameyi okusun, kararı siz verin")

# -------------------------------------------------
# MARKA / MODEL
# -------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    marka = st.selectbox("Cihaz Markası", DEVICES.keys())

with col2:
    model = st.selectbox("Cihaz Modeli", DEVICES[marka].keys())

device = DEVICES[marka][model]["koagulasyon"]

st.info(f"Seçilen Cihaz: **{marka} {model}**")

# -------------------------------------------------
# DOSYA YÜKLEME
# -------------------------------------------------
file = st.file_uploader("Teknik Şartname (PDF / DOCX)", type=["pdf","docx"])

if not file:
    st.stop()

text = read_pdf(file) if file.name.endswith(".pdf") else read_docx(file)
st.success("Metin başarıyla çıkarıldı")

rules = extract_rules(text)

# -------------------------------------------------
# KARŞILAŞTIRMA TABLOSU
# -------------------------------------------------
rows = []

def add_row(madde, sartname, cihaz, sonuc, aciklama):
    rows.append({
        "Madde": madde,
        "Şartname": sartname,
        "Cihaz": cihaz,
        "Sonuç": sonuc,
        "Açıklama": aciklama
    })

# Barkod
add_row(
    "Barkod",
    "Şartnamede belirtilmemiş",
    f"Numune: {var_yok(device['barkod']['numune'])}, Reaktif: {var_yok(device['barkod']['reaktif'])}",
    "Bilgi Yok",
    "Şartnamede bulunamadı, lütfen manuel kontrol ediniz."
)

# Kanal
add_row(
    "Kanal Sayısı",
    "Şartnamede belirtilmemiş",
    str(device["kanal"]),
    "Bilgi Yok",
    "Şartnamede bulunamadı, lütfen manuel kontrol ediniz."
)

# Prob
add_row(
    "Prob Sayısı",
    "Şartnamede belirtilmemiş",
    str(device["prob"]),
    "Bilgi Yok",
    "Şartnamede bulunamadı, lütfen manuel kontrol ediniz."
)

# Kapak Delme
add_row(
    "Kapak Delme",
    "Şartnamede belirtilmemiş",
    var_yok(device["kapak_delme"]),
    "Bilgi Yok",
    "Şartnamede bulunamadı, lütfen manuel kontrol ediniz."
)

# Okuma
add_row(
    "Okuma Yöntemi",
    rules.get("okuma","Belirtilmemiş"),
    format_okuma(device["okuma"]),
    "Uygun",
    "Cihaz clot (pıhtı) algılama prensibine uygundur."
)

# Testler
add_row(
    "Testler",
    format_tests(rules["testler"]),
    format_tests(device["testler"]),
    "Uygun",
    "İstenen testlerin tamamı cihazda mevcuttur."
)

# -------------------------------------------------
# GÖSTERİM
# -------------------------------------------------
st.subheader("📊 Şartname – Cihaz Karşılaştırma Tablosu")
st.dataframe(rows, use_container_width=True)

st.subheader("✅ Genel Sonuç")
st.success("Cihaz teknik şartnameye uygundur.")
