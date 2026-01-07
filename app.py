import streamlit as st
import json
import re
from pypdf import PdfReader
from docx import Document

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
    for a, b in [("ı","i"),("ş","s"),("ğ","g"),("ü","u"),("ö","o"),("ç","c")]:
        text = text.replace(a,b)
    return re.sub(r"\s+", " ", text)

# ======================================================
# TEST BLOĞU
# ======================================================
def extract_test_block(text):
    headers = [
        "istenen test", "calisilacak test", "test listesi",
        "testler", "calisilacak parametre"
    ]
    for h in headers:
        idx = text.find(h)
        if idx != -1:
            return text[idx:idx+1200]
    return ""

# ======================================================
# ŞARTNAME ANALİZ
# ======================================================
def extract_rules_from_text(raw_text):
    t = normalize_tr(raw_text)
    rules = {}

    # Kanal
    kanal = re.findall(r"en az\s*(\d+)\s*kanal", t)
    if kanal:
        rules["kanal_min"] = max(map(int, kanal))

    # Prob
    prob = re.findall(r"en az\s*(\d+)\s*prob", t)
    if prob:
        rules["prob_min"] = max(map(int, prob))

    # Barkod (ayrıntılı)
    barkod = {}
    if any(k in t for k in ["numune barkod", "sample barcode", "hasta barkod"]):
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
    scan = extract_test_block(t) or t
    tests = {}

    if "pt" in scan:
        tests["PT"] = True
    if "aptt" in scan:
        tests["APTT"] = True
    if "fibrinojen" in scan:
        tests["Fibrinojen"] = True
    if "d-dimer" in scan or "ddimer" in scan:
        tests["D-Dimer"] = True

    if any(k in scan for k in ["faktor", "factor"]):
        tests["Faktor"] = True
        rules["faktor_durumu"] = (
            "opsiyonel" if "dis lab" in scan else "zorunlu"
        )

    if tests:
        rules["istenen_testler"] = tests

    return rules

# ======================================================
# BARKOD DEĞERLENDİRME
# ======================================================
def evaluate_barkod(requirement, device):
    device_barkod = device.get("barkod", {})

    if requirement.get("numune") and not device_barkod.get("numune"):
        return "Uygun Değil", "Numune barkod okuyucu yok"

    if requirement.get("reaktif") and not device_barkod.get("reaktif"):
        return "Zeyil", "Reaktif barkod bulunmamaktadır"

    return "Uygun", "Barkod gereksinimleri karşılanıyor"

# ======================================================
# STREAMLIT UI
# ======================================================
st.set_page_config("İhaleBind", "🧬", layout="wide")

with open("devices.json", "r", encoding="utf-8") as f:
    devices = json.load(f)

st.title("🧬 İhaleBind")
st.caption("Şartnameyi okusun, kararı siz verin")

# Sidebar
with st.sidebar:
    st.header("📂 İhale Türleri")
    ihale_turu = st.radio(
        "",
        ["Koagülasyon", "Biyokimya", "Hormon", "Kan Gazı", "İdrar", "Hemogram"]
    )

# Marka / Model
col1, col2 = st.columns(2)
with col1:
    marka = st.selectbox("Cihaz Markası", devices.keys())
with col2:
    model = st.selectbox("Cihaz Modeli", devices[marka].keys())

device = devices[marka][model]["koagulasyon"]
st.info(f"Seçilen cihaz: **{marka} {model}**")

# Dosya
file = st.file_uploader("Teknik Şartname (PDF / Word)", ["pdf", "docx"])

if file:
    text = extract_text_from_pdf(file) if file.name.endswith(".pdf") else extract_text_from_docx(file)
    st.success("Metin başarıyla çıkarıldı")

    rules = extract_rules_from_text(text)
    st.subheader("🧠 Şartnameden Yakalanan Kurallar")
    st.json(rules)

    st.subheader("🔍 Cihaz Özeti")
    st.write("Toplam Kanal:", device.get("kanal_toplam"))
    st.write("Prob Sayısı:", device.get("prob_sayisi"))
    st.write("Numune Barkod:", device.get("barkod", {}).get("numune", False))
    st.write("Reaktif Barkod:", device.get("barkod", {}).get("reaktif", False))

    if "barkod" in rules:
        durum, aciklama = evaluate_barkod(rules["barkod"], device)
        st.subheader("🏷️ Barkod Değerlendirmesi")
        if durum == "Uygun":
            st.success(aciklama)
        elif durum == "Zeyil":
            st.warning(aciklama)
        else:
            st.error(aciklama)

    st.subheader("🧪 Çalışılabilen Testler")
    st.json(device.get("testler"))
