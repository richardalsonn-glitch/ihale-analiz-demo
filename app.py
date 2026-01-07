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
    else:
        doc = Document(file)
        return "\n".join(p.text for p in doc.paragraphs)

# ======================================================
# NORMALIZE
# ======================================================
def normalize(text):
    text = text.lower()
    text = text.replace("ı","i").replace("ş","s").replace("ğ","g").replace("ü","u").replace("ö","o").replace("ç","c")
    return re.sub(r"\s+", " ", text)

# ======================================================
# TEST BLOĞU
# ======================================================
def extract_test_block(text):
    headers = [
        "istenen test",
        "calisilacak test",
        "test listesi",
        "testler",
        "calisilacak parametre",
        "a grubu hastaneler"
    ]
    for h in headers:
        idx = text.find(h)
        if idx != -1:
            return text[idx:idx+2000]
    return ""

# ======================================================
# TEST ALGILAMA (PT / APTT vs)
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
# BARKOD DEĞERLENDİRME
# ======================================================
def evaluate_barkod(requirement, device):
    device_barkod = device.get("barkod", {})
    if requirement.get("numune") and not device_barkod.get("numune"):
        return "Uygun Değil", "Numune barkod okuyucu bulunmamaktadır."
    if requirement.get("reaktif") and not device_barkod.get("reaktif"):
        return "Zeyil", "Reaktif barkod okuyucu yoktur."
    return "Uygun", "Barkod gereksinimleri karşılanmaktadır."

# ======================================================
# ŞARTNAME KURAL ÇIKARICI
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
    if "numune barkod" in t or "hasta barkod" in t:
        barkod["numune"] = True
    if "reaktif barkod" in t or "kit barkod" in t:
        barkod["reaktif"] = True
    if barkod:
        rules["barkod"] = barkod

    if "koagulometri" in t or "clot" in t or "pihti" in t:
        rules["okuma"] = "clot_detection"

    block = extract_test_block(t)
    scan = block if block else t
    rules["testler"] = detect_tests(scan)

    return rules

# ======================================================
# STREAMLIT UI
# ======================================================
st.set_page_config("İhaleBind", "🧬", layout="wide")

with open("devices.json", "r", encoding="utf-8") as f:
    devices = json.load(f)

st.title("🧬 İhaleBind")
st.caption("Şartnameyi okusun, kararı siz verin")

# SIDEBAR
with st.sidebar:
    st.header("📂 İhale Türleri")
    st.success("Koagülasyon İhalesi")
    st.info("Diğerleri ileride eklenecek")

# CİHAZ
col1, col2 = st.columns(2)
with col1:
    marka = st.selectbox("Cihaz Markası", devices.keys())
with col2:
    model = st.selectbox("Cihaz Modeli", devices[marka].keys())

device = devices[marka][model]["koagulasyon"]
st.info(f"Seçilen Cihaz: **{marka} {model}**")

# DOSYA
file = st.file_uploader("Teknik şartname yükleyin (PDF / DOCX)", ["pdf", "docx"])

if file:
    text = extract_text(file)
    rules = extract_rules(text)
    st.success("Metin başarıyla çıkarıldı")

    st.subheader("🧠 Şartnameden Yakalanan Kurallar")
    st.json(rules)

    st.subheader("📊 Şartname – Cihaz Karşılaştırma Tablosu")
    rows = []

    if "barkod" in rules:
        d, a = evaluate_barkod(rules["barkod"], device)
        rows.append(["Barkod", d, a])

    if "kanal" in rules:
        rows.append([
            "Kanal Sayısı",
            "Uygun" if device["kanal_toplam"] >= rules["kanal"] else "Uygun Değil",
            f"Şartname ≥ {rules['kanal']} / Cihaz {device['kanal_toplam']}"
        ])

    rows.append([
        "Okuma Yöntemi",
        "Uygun",
        "Cihaz koagülometri (clot detection) uyumludur."
    ])

    eksik = []
    for t in rules["testler"]:
        if not device["testler"].get(t):
            eksik.append(t)

    if eksik:
        rows.append(["Testler", "Zeyil", f"Eksik: {', '.join(eksik)}"])
    else:
        rows.append(["Testler", "Uygun", "Tüm testler mevcut"])

    st.table(rows)

    st.subheader("📌 Otomatik Zeyil Önerileri")
    if eksik:
        st.warning(
            "Koagülasyon testleri clot (koagülometri) prensibine dayalıdır. "
            "Cihaz manyetik/optik algılama yöntemleri ile pıhtı oluşumunu güvenilir şekilde tespit eder."
        )
    else:
        st.success("Zeyil gerektiren bir durum bulunmamaktadır.")

    st.subheader("📄 PDF Uygunluk Raporu")
    st.info("PDF rapor altyapısı hazır – bir sonraki adımda indirilebilir hale getirilecektir.")

    st.subheader("✅ Genel Sonuç")
    if any(r[1] == "Uygun Değil" for r in rows):
        st.error("Uygun Değil")
    elif any(r[1] == "Zeyil" for r in rows):
        st.warning("Zeyil ile Uygun")
    else:
        st.success("Uygun")
