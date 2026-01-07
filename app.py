import streamlit as st
import json
import re
from pypdf import PdfReader
from docx import Document

# ======================================================
# METİN OKUMA
# ======================================================
def extract_text(file):
    if file.name.lower().endswith(".pdf"):
        reader = PdfReader(file)
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    doc = Document(file)
    return "\n".join(p.text for p in doc.paragraphs)

# ======================================================
# NORMALIZE
# ======================================================
def normalize(text):
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
        "testler", "calisilacak parametre", "a grubu"
    ]
    for h in headers:
        i = text.find(h)
        if i != -1:
            return text[i:i+2000]
    return ""

# ======================================================
# TEST ALGILAMA
# ======================================================
def detect_tests(text):
    tests = {}
    if re.search(r"\bpt\b|protrombin zamani", text):
        tests["PT"] = True
    if re.search(r"\ba\s*\.?\s*p\s*\.?\s*t\s*\.?\s*t\b", text):
        tests["APTT"] = True
    if "fibrinojen" in text:
        tests["Fibrinojen"] = True
    if re.search(r"d\s*[-]?\s*dimer|ddimer", text):
        tests["D-Dimer"] = True
    if re.search(r"faktor|factor", text):
        tests["Faktor"] = True
    return tests

# ======================================================
# ŞARTNAME KURAL ÇIKARIMI
# ======================================================
def extract_rules(text):
    t = normalize(text)
    rules = {}

    kanal = re.findall(r"en az\s*(\d+)\s*kanal", t)
    if kanal:
        rules["kanal"] = int(max(kanal))

    prob = re.findall(r"en az\s*(\d+)\s*prob", t)
    if prob:
        rules["prob"] = int(max(prob))

    barkod = {}
    if any(k in t for k in ["numune barkod", "hasta barkod"]):
        barkod["numune"] = True
    if any(k in t for k in ["reaktif barkod", "kit barkod"]):
        barkod["reaktif"] = True
    if barkod:
        rules["barkod"] = barkod

    if any(k in t for k in ["koagulometri", "clot", "pihti"]):
        rules["okuma"] = "clot_detection"

    block = extract_test_block(t)
    rules["testler"] = detect_tests(block if block else t)

    return rules

# ======================================================
# BARKOD DEĞERLENDİRME
# ======================================================
def evaluate_barkod(req, dev):
    if req.get("numune") and not dev.get("numune"):
        return "Uygun Değil", "Numune barkod yok"
    if req.get("reaktif") and not dev.get("reaktif"):
        return "Zeyil", "Reaktif barkod yok"
    return "Uygun", "Barkod uygun"

# ======================================================
# STREAMLIT UI
# ======================================================
st.set_page_config("İhaleBind", "🧬", layout="wide")

with open("devices.json", "r", encoding="utf-8") as f:
    devices = json.load(f)

st.title("🧬 İhaleBind")
st.caption("Şartnameyi okusun, kararı siz verin")

with st.sidebar:
    st.header("📂 İhale Türleri")
    st.success("Koagülasyon İhalesi")
    st.info("Diğerleri ileride")

col1, col2 = st.columns(2)
with col1:
    marka = st.selectbox("Cihaz Markası", devices.keys())
with col2:
    model = st.selectbox("Cihaz Modeli", devices[marka].keys())

device = devices[marka][model]["koagulasyon"]
st.info(f"Seçilen Cihaz: **{marka} {model}**")

# ======================================================
# CİHAZ ÖZETİ (EKSİKSİZ)
# ======================================================
st.subheader("🔍 Cihaz Özeti")
st.write("Toplam Kanal:", device.get("kanal_toplam"))
st.write("Optik Kanal:", device.get("kanal_optik"))
st.write("Manyetik Kanal:", device.get("kanal_manyetik"))
st.write("Prob Sayısı:", device.get("prob_sayisi"))
st.write("Kapak Delme:", "Var" if device.get("kapak_delme") else "Yok")

b = device.get("barkod", {})
st.write("Numune Barkod:", "Var" if b.get("numune") else "Yok")
st.write("Reaktif Barkod:", "Var" if b.get("reaktif") else "Yok")

st.write("İnkübasyon Sayısı:", device.get("inkubasyon_sayisi"))
st.write("Sesli Uyarı:", "Var" if device.get("sesli_uyari") else "Yok")
st.write("Görsel Uyarı:", "Var" if device.get("gorsel_uyari") else "Yok")

st.subheader("🧪 Çalışılabilen Testler")
st.json(device.get("testler", {}))

# ======================================================
# ŞARTNAME
# ======================================================
file = st.file_uploader("Teknik şartname (PDF / DOCX)", ["pdf","docx"])

if file:
    text = extract_text(file)
    rules = extract_rules(text)

    st.subheader("🧠 Şartnameden Yakalanan Kurallar")
    st.json(rules)

    st.subheader("📊 Şartname – Cihaz Karşılaştırması")
    rows = []

    if "barkod" in rules:
        d,a = evaluate_barkod(rules["barkod"], device["barkod"])
        rows.append(["Barkod", d, a])

    if "kanal" in rules:
        rows.append(["Kanal", "Uygun" if device["kanal_toplam"]>=rules["kanal"] else "Uygun Değil",
                     f"Şartname ≥ {rules['kanal']} / Cihaz {device['kanal_toplam']}"])

    if "prob" in rules:
        rows.append(["Prob", "Uygun" if device["prob_sayisi"]>=rules["prob"] else "Uygun Değil",
                     f"Şartname ≥ {rules['prob']} / Cihaz {device['prob_sayisi']}"])

    rows.append(["Kapak Delme", "Uygun" if device.get("kapak_delme") else "Uygun Değil",""])

    eksik = [t for t in rules["testler"] if not device["testler"].get(t)]
    rows.append(["Testler", "Uygun" if not eksik else "Zeyil",
                 "Eksik: "+", ".join(eksik) if eksik else "Tümü mevcut"])

    st.table(rows)

    st.subheader("📌 Genel Sonuç")
    if any(r[1]=="Uygun Değil" for r in rows):
        st.error("Uygun Değil")
    elif any(r[1]=="Zeyil" for r in rows):
        st.warning("Zeyil ile Uygun")
    else:
        st.success("Uygun")
