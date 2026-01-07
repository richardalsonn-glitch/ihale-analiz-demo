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
    for a,b in [("ı","i"),("ş","s"),("ğ","g"),("ü","u"),("ö","o"),("ç","c")]:
        text = text.replace(a,b)
    return re.sub(r"\s+", " ", text)

# ======================================================
# ŞARTNAME KURAL ÇIKARIMI
# ======================================================
def extract_rules(text):
    t = normalize(text)
    rules = {}

    # Kanal
    kanal = re.findall(r"en az\s*(\d+)\s*kanal", t)
    if kanal:
        rules["kanal"] = int(max(kanal))

    # Prob
    prob = re.findall(r"en az\s*(\d+)\s*prob", t)
    if prob:
        rules["prob"] = int(max(prob))

    # Kapak delme
    if "kapak delme" in t or "piercing" in t:
        rules["kapak_delme"] = True

    # Barkod
    barkod = {}
    if any(k in t for k in ["numune barkod", "hasta barkod"]):
        barkod["numune"] = True
    if any(k in t for k in ["reaktif barkod", "kit barkod"]):
        barkod["reaktif"] = True
    if barkod:
        rules["barkod"] = barkod

    # Okuma yöntemi
    if any(k in t for k in ["koagulometri", "clot", "pihti"]):
        rules["okuma"] = "clot_detection"

    # Testler
    tests = {}
    if re.search(r"\bpt\b|protrombin zamani", t):
        tests["PT"] = True
    if re.search(r"\ba\s*\.?\s*p\s*\.?\s*t\s*\.?\s*t\b", t):
        tests["APTT"] = True
    if "fibrinojen" in t:
        tests["Fibrinojen"] = True
    if re.search(r"d\s*[-]?\s*dimer|ddimer", t):
        tests["D-Dimer"] = True
    if re.search(r"faktor|factor", t):
        tests["Faktor"] = True
    if tests:
        rules["testler"] = tests

    return rules

# ======================================================
# KARŞILAŞTIRMA YARDIMCISI
# ======================================================
def compare_feature(feature_name, requirement_exists, condition):
    if not requirement_exists:
        return "Bilgi Yok", "Şartnamede bu madde bulunamadı, lütfen manuel kontrol ediniz."
    return condition

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
# CİHAZ ÖZETİ
# ======================================================
st.subheader("🔍 Cihaz Özeti")
st.write("Toplam Kanal:", device.get("kanal_toplam"))
st.write("Prob Sayısı:", device.get("prob_sayisi"))
st.write("Kapak Delme:", "Var" if device.get("kapak_delme") else "Yok")

b = device.get("barkod", {})
st.write("Numune Barkod:", "Var" if b.get("numune") else "Yok")
st.write("Reaktif Barkod:", "Var" if b.get("reaktif") else "Yok")

st.subheader("🧪 Çalışılabilen Testler")
st.json(device.get("testler", {}))

# ======================================================
# ŞARTNAME YÜKLEME
# ======================================================
file = st.file_uploader("Teknik Şartname (PDF / DOCX)", ["pdf","docx"])

if file:
    text = extract_text(file)
    rules = extract_rules(text)

    st.subheader("🧠 Şartnameden Yakalanan Kurallar")
    st.json(rules)

    st.subheader("📊 Şartname – Cihaz Karşılaştırma Tablosu")
    rows = []

    # Kanal
    rows.append([
        "Kanal Sayısı",
        compare_feature(
            "kanal",
            "kanal" in rules,
            (
                "Uygun" if device["kanal_toplam"] >= rules["kanal"] else "Uygun Değil",
                f"Şartname ≥ {rules['kanal']} / Cihaz {device['kanal_toplam']}"
            )
        )
    ])

    # Prob
    rows.append([
        "Prob Sayısı",
        compare_feature(
            "prob",
            "prob" in rules,
            (
                "Uygun" if device["prob_sayisi"] >= rules["prob"] else "Uygun Değil",
                f"Şartname ≥ {rules['prob']} / Cihaz {device['prob_sayisi']}"
            )
        )
    ])

    # Kapak delme
    rows.append([
        "Kapak Delme",
        compare_feature(
            "kapak_delme",
            "kapak_delme" in rules,
            (
                "Uygun" if device.get("kapak_delme") else "Uygun Değil",
                ""
            )
        )
    ])

    # Barkod
    rows.append([
        "Numune Barkod",
        compare_feature(
            "numune barkod",
            "barkod" in rules and rules["barkod"].get("numune"),
            (
                "Uygun" if b.get("numune") else "Uygun Değil",
                ""
            )
        )
    ])

    rows.append([
        "Reaktif Barkod",
        compare_feature(
            "reaktif barkod",
            "barkod" in rules and rules["barkod"].get("reaktif"),
            (
                "Uygun" if b.get("reaktif") else "Zeyil",
                "Reaktif barkod opsiyonel"
            )
        )
    ])

    # Testler
    if "testler" in rules:
        eksik = [t for t in rules["testler"] if not device["testler"].get(t)]
        rows.append([
            "Testler",
            (
                "Uygun" if not eksik else "Zeyil",
                "Eksik: " + ", ".join(eksik) if eksik else "Tüm testler mevcut"
            )
        ])
    else:
        rows.append([
            "Testler",
            ("Bilgi Yok", "Şartnamede test listesi bulunamadı, lütfen manuel kontrol ediniz.")
        ])

    st.table([[r[0], r[1][0], r[1][1]] for r in rows])

    # ======================================================
    # GENEL SONUÇ
    # ======================================================
    st.subheader("✅ Genel Sonuç")
    statuses = [r[1][0] for r in rows]
    if "Uygun Değil" in statuses:
        st.error("Uygun Değil")
    elif "Zeyil" in statuses:
        st.warning("Zeyil ile Uygun")
    else:
        st.success("Uygun")
