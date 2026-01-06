import streamlit as st
from pypdf import PdfReader
from docx import Document
import re
import json

# -----------------------------
# Dosyadan metin çıkarma
# -----------------------------
def extract_text_from_pdf(uploaded_file) -> str:
    reader = PdfReader(uploaded_file)
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)

def extract_text_from_docx(uploaded_file) -> str:
    doc = Document(uploaded_file)
    return "\n".join([p.text for p in doc.paragraphs])

# -----------------------------
# Metin normalize + kural çıkar
# -----------------------------
def normalize_tr(text: str) -> str:
    text = text.lower()
    text = (text.replace("ı", "i")
                .replace("İ", "i")
                .replace("ş", "s")
                .replace("ğ", "g")
                .replace("ü", "u")
                .replace("ö", "o")
                .replace("ç", "c"))
    text = re.sub(r"\s+", " ", text)
    return text

def extract_rules_from_text(raw_text: str) -> dict:
    t = normalize_tr(raw_text)
    rules = {}

    kanal_patterns = [
        r"en az\s*(\d+)\s*(adet\s*)?(olcum|test|reaksiyon)?\s*kanal",
        r"(\d+)\s*(adet\s*)?(olcum|test|reaksiyon)\s*kanali",
        r"en az\s*(\d+)\s*kanal"
    ]
    kanal_vals = []
    for pat in kanal_patterns:
        m = re.search(pat, t)
        if m:
            kanal_vals.append(int(m.group(1)))
    if kanal_vals:
        rules["kanal_toplam_min"] = max(kanal_vals)

    prob_patterns = [
        r"en az\s*(\d+)\s*\(?[a-z]*\)?\s*prob",
        r"(\d+)\s*problu"
    ]
    prob_vals = []
    for pat in prob_patterns:
        m = re.search(pat, t)
        if m:
            prob_vals.append(int(m.group(1)))
    if prob_vals:
        rules["prob_sayisi_min"] = max(prob_vals)

    if "barkod" in t:
        rules["barkod_okuma_gerekli"] = True

    method_hits = set()
    if any(k in t for k in ["manyetik", "manyetik prensip"]):
        method_hits.add("manyetik")
    if any(k in t for k in ["mekanik", "clot", "clotting", "clot detection", "pihti olusumu", "pihti"]):
        method_hits.add("mekanik_clot")
    if "koagulometri" in t:
        method_hits.add("mekanik_clot")
    if method_hits:
        rules["okuma_yontemi"] = sorted(method_hits)

    faktor_var = ("faktor" in t) or ("factor" in t)
    if faktor_var:
        dis_lab = any(k in t for k in ["dis lab", "dis laboratuvar", "referans lab", "baska laboratuvar", "diger hastanede", "gonderilebilir"])
        rules["faktor_testi"] = "opsiyonel_dis_lab" if dis_lab else "zorunlu"

    tests = {}
    if " pt " in f" {t} " or "protrombin" in t:
        tests["PT"] = True
    if "aptt" in t:
        tests["APTT"] = True
    if "fibrinojen" in t:
        tests["Fibrinojen"] = True
    if any(k in t for k in ["d-dimer", "d dimer", "ddimer"]):
        tests["D-Dimer"] = True
    if tests:
        rules["testler"] = tests

    return rules

# Sayfa ayarları
st.set_page_config(
    page_title="İhaleBind",
    page_icon="🧬",
    layout="wide"
)

# ===== CİHAZ KATALOĞUNU OKU =====
with open("devices.json", "r", encoding="utf-8") as f:
    devices = json.load(f)

# ===== HEADER =====
st.markdown("""
# 🧬 İhaleBind
### Şartnameyi okusun, kararı siz verin
""")

st.divider()

# ===== ÜST BAR: MARKA / MODEL =====
col_brand, col_model = st.columns(2)

with col_brand:
    marka = st.selectbox(
        "Cihaz Markası",
        list(devices.keys())
    )

with col_model:
    model = st.selectbox(
        "Cihaz Modeli",
        list(devices[marka].keys())
    )

selected_device = devices[marka][model]

st.info(f"Seçilen Cihaz: **{marka} {model}**")

# ===== SOL MENÜ: İHALE TÜRLERİ =====
with st.sidebar:
    st.header("📂 İhale Türleri")

    for ihale in [
        "Koagülasyon İhalesi",
        "Biyokimya İhalesi",
        "Hormon İhalesi",
        "Kan Gazı İhalesi",
        "İdrar İhalesi",
        "Hemogram İhalesi"
    ]:
        destek = ihale.replace(" İhalesi", "") in selected_device.get("ihale_turleri", [])

        if destek:
            st.success(ihale)
        else:
            st.caption(f"❌ {ihale}")

# ===== ANA ALAN =====
st.subheader("📄 Teknik Şartname")

file = st.file_uploader(
    if file:
    # metin çıkar
    if file.name.lower().endswith(".pdf"):
        text = extract_text_from_pdf(file)
    elif file.name.lower().endswith(".docx"):
        text = extract_text_from_docx(file)
    else:
        text = ""

    if not text.strip():
        st.error("Metin çıkarılamadı. PDF tarama olabilir (OCR gerekebilir).")
    else:
        st.success("Metin çıkarıldı ✅")

        rules = extract_rules_from_text(text)

        st.subheader("🧠 Şartnameden Yakalanan Kurallar (V1)")
        st.json(rules)
    "PDF veya Word yükleyin",
    type=["pdf", "docx"]
)

if file:
    st.success(f"Yüklenen dosya: {file.name}")

    st.subheader("🔍 Cihaz Özeti")

    if "koagulasyon" in selected_device:
        koag = selected_device["koagulasyon"]

        st.write("**Toplam Kanal:**", koag.get("kanal_toplam"))
        st.write("**Prob Sayısı:**", koag.get("prob_sayisi"))
        st.write("**Kapak Delme:**", "Var" if koag.get("kapak_delme") else "Yok")
        st.write("**Barkod Okuma:**", "Var" if koag.get("barkod_okuma") else "Yok")

        st.subheader("🧪 Çalışılabilen Testler")
        st.json(koag.get("testler"))
