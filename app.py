import streamlit as st
from pypdf import PdfReader
from docx import Document
import re
import json

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
