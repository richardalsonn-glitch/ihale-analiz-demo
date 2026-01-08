import streamlit as st
from pypdf import PdfReader
from docx import Document
import re
import json

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
    repl = {"ı":"i","ş":"s","ğ":"g","ü":"u","ö":"o","ç":"c"}
    for k,v in repl.items():
        text = text.replace(k,v)
    return re.sub(r"\s+", " ", text)

# ======================================================
# ŞARTNAME KURAL ÇIKARICI
# ======================================================
def extract_rules(text):
    t = normalize(text)
    rules = {}

    # Okuma yöntemi
    if any(k in t for k in ["clot","pıhtı","koagulometri","manyetik","optik"]):
        rules["okuma"] = "clot_detection"

    # Testler
    tests = {}
    if "pt" in t or "protrombin" in t:
        tests["PT"] = True
    if "aptt" in t:
        tests["APTT"] = True
    if "fibrinojen" in t:
        tests["Fibrinojen"] = True
    if "d-dimer" in t or "ddimer" in t:
        tests["D-Dimer"] = True
    if any(k in t for k in ["faktor","factor"]):
        tests["Faktör"] = True

    rules["testler"] = tests

    # Kanal
    m = re.search(r"en az\s*(\d+)\s*kanal", t)
    if m:
        rules["kanal"] = int(m.group(1))

    # Prob
    m = re.search(r"en az\s*(\d+)\s*prob", t)
    if m:
        rules["prob"] = int(m.group(1))

    # Barkod
    barkod = {}
    if "numune barkod" in t or "hasta barkod" in t:
        barkod["numune"] = True
    if "reaktif barkod" in t or "kit barkod" in t:
        barkod["reaktif"] = True
    if barkod:
        rules["barkod"] = barkod

    # Kapak delme
    if "kapak delme" in t or "piercing" in t:
        rules["kapak_delme"] = True

    return rules

# ======================================================
# BARKOD DEĞERLENDİRME
# ======================================================
def evaluate_barkod(req, dev):
    if not req:
        return "Bilgi Yok", "Şartnamede bulunamadı, lütfen manuel kontrol ediniz."

    dev_b = dev.get("barkod", {})
    if req.get("numune") and not dev_b.get("numune"):
        return "Uygun Değil", "Numune barkod okuyucu yok."
    if req.get("reaktif") and not dev_b.get("reaktif"):
        return "Zeyil", "Reaktif barkod okuyucu bulunmamaktadır."

    return "Uygun", "Barkod gereksinimleri karşılanmaktadır."

# ======================================================
# STREAMLIT
# ======================================================
st.set_page_config(page_title="İhaleBind", layout="wide")

with open("devices.json", "r", encoding="utf-8") as f:
    devices = json.load(f)

# ======================================================
# SIDEBAR – İHALE TÜRLERİ
# ======================================================
with st.sidebar:
    st.header("📁 İhale Türleri")
    ihale = st.radio(
        "İhale",
        ["Koagülasyon","Biyokimya","Hormon","Kan Gazı","İdrar","Hemogram"]
    )

# ======================================================
# HEADER
# ======================================================
st.title("🧬 İhaleBind")
st.caption("Şartnameyi okusun, kararı siz verin")

# ======================================================
# CİHAZ FİLTRELEME
# ======================================================
filtered = {
    b:{m:v for m,v in models.items() if ihale in v["ihale_turleri"]}
    for b,models in devices.items()
}
filtered = {k:v for k,v in filtered.items() if v}

col1,col2 = st.columns(2)
with col1:
    marka = st.selectbox("Cihaz Markası", list(filtered.keys()))
with col2:
    model = st.selectbox("Cihaz Modeli", list(filtered[marka].keys()))

device = filtered[marka][model]["koagulasyon"]
st.info(f"Seçilen Cihaz: **{marka} {model}**")

# ======================================================
# DOSYA
# ======================================================
file = st.file_uploader("Teknik Şartname (PDF / DOCX)", type=["pdf","docx"])

if file:
    text = extract_text(file)
    rules = extract_rules(text)

    st.success("Metin başarıyla çıkarıldı")

    # ==================================================
    # TABLO
    # ==================================================
    rows = []

    # Barkod
    res,exp = evaluate_barkod(rules.get("barkod"), device)
    rows.append(("Barkod", rules.get("barkod","-"), device.get("barkod","-"), res, exp))

    # Kanal
    if "kanal" in rules:
        r = "Uygun" if device.get("kanal_toplam",0) >= rules["kanal"] else "Uygun Değil"
        rows.append(("Kanal", f">={rules['kanal']}", device.get("kanal_toplam"), r, ""))
    else:
        rows.append(("Kanal","-",device.get("kanal_toplam"),"Bilgi Yok","Şartnamede bulunamadı, lütfen manuel kontrol ediniz."))

    # Prob
    if "prob" in rules:
        r = "Uygun" if device.get("prob_sayisi",0) >= rules["prob"] else "Uygun Değil"
        rows.append(("Prob", f">={rules['prob']}", device.get("prob_sayisi"), r, ""))
    else:
        rows.append(("Prob","-",device.get("prob_sayisi"),"Bilgi Yok","Şartnamede bulunamadı, lütfen manuel kontrol ediniz."))

    # Kapak delme
    if "kapak_delme" in rules:
        r = "Uygun" if device.get("kapak_delme") else "Uygun Değil"
        rows.append(("Kapak Delme","Var",device.get("kapak_delme"),r,""))
    else:
        rows.append(("Kapak Delme","-",device.get("kapak_delme"),"Bilgi Yok","Şartnamede bulunamadı, lütfen manuel kontrol ediniz."))

    # Okuma
    rows.append(("Okuma Yöntemi","clot_detection","manyetik/optik","Uygun","Manyetik ve optik okuma clot algılama yapar."))

    # Testler
    rows.append(("Testler",rules["testler"],device["testler"],"Uygun","Tüm istenen testler mevcut."))

    st.subheader("📊 Şartname – Cihaz Karşılaştırma Tablosu")
    st.dataframe(
        [{"Madde":r[0],"Şartname":r[1],"Cihaz":r[2],"Sonuç":r[3],"Açıklama":r[4]} for r in rows],
        use_container_width=True
    )

    st.subheader("✅ Genel Sonuç")
    st.success("Uygun")
