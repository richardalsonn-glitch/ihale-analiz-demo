import streamlit as st

# Sayfa ayarları
st.set_page_config(
    page_title="İhaleBind",
    page_icon="🧬",
    layout="wide"
)

# HEADER
st.markdown("""
# 🧬 İhaleBind
### Şartnameyi okusun, kararı siz verin
""")

st.divider()

# SIDEBAR
with st.sidebar:
    st.header("📄 Şartname Yükle")
    file = st.file_uploader(
        "PDF veya Word yükleyin",
        type=["pdf", "docx"]
    )

    st.divider()

    st.header("🧪 Cihaz Seçimi")

    cihaz_A = st.selectbox(
        "A Grubu (Tam otomatik)",
        ["Succeeder SF-8300"]
    )

    cihaz_B = st.selectbox(
        "B Grubu (Yarı otomatik)",
        ["Succeeder SF-400"]
    )

# ANA ALAN
if file is None:
    st.info("👈 Başlamak için sol menüden şartname yükleyin.")
else:
    st.success(f"✅ Yüklenen dosya: {file.name}")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📊 İhale Özeti (Demo)")
        st.metric("Toplam Test", "283.000")
        st.metric("Süre", "24 Ay")

    with col2:
        st.subheader("📌 Cihaz Bilgisi")
        st.write("**A Grubu:**", cihaz_A)
        st.write("**B Grubu:**", cihaz_B)

    st.divider()

    st.subheader("🔍 Uygunluk Analizi (Demo Veri)")

    st.table({
        "Şartname Maddesi": [
            "Kanal ≥ 4",
            "Prob ≥ 2",
            "Barkod Okuma"
        ],
        "Cihaz Özelliği": [
            "4",
            "1",
            "Var"
        ],
        "Durum": [
            "✅ Uygun",
            "❌ Uygun Değil",
            "✅ Uygun"
        ]
    })
