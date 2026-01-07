import os
import re
import json
import io
import streamlit as st
import pandas as pd
from pypdf import PdfReader
from docx import Document

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm


# ======================================================
# PATHS
# ======================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEVICE_PATH = os.path.join(BASE_DIR, "devices.json")


# ======================================================
# TEXT EXTRACTION
# ======================================================
def extract_text_from_pdf(file) -> str:
    reader = PdfReader(file)
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)

def extract_text_from_docx(file) -> str:
    doc = Document(file)
    return "\n".join(p.text for p in doc.paragraphs)


# ======================================================
# NORMALIZE
# ======================================================
def normalize_tr(text: str) -> str:
    text = text.lower()
    text = (text.replace("ı", "i")
                .replace("ş", "s")
                .replace("ğ", "g")
                .replace("ü", "u")
                .replace("ö", "o")
                .replace("ç", "c"))
    text = re.sub(r"\s+", " ", text)
    return text


# ======================================================
# HELPERS
# ======================================================
def safe_int(x):
    try:
        return int(x)
    except:
        return None

def device_get_barkod(device_koag: dict) -> dict:
    b = device_koag.get("barkod", {})
    return {
        "numune": bool(b.get("numune", False)),
        "reaktif": bool(b.get("reaktif", False)),
    }

def device_has_test(device_koag: dict, test_name: str) -> bool:
    tests = device_koag.get("testler", {})
    # test adı farklı yazılmış olabilir (Faktor/Faktör)
    if test_name in tests:
        val = tests.get(test_name)
    else:
        # küçük tolerans
        alt = {
            "Faktör": "Faktor",
            "Faktor": "Faktör",
        }.get(test_name)
        val = tests.get(alt, None)
    # True / False / "manyetik"/"optik"
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return True
    return False


# ======================================================
# TEST LIST BLOCK (optional)
# ======================================================
def extract_test_block(t: str) -> str:
    headers = [
        "istenen test", "istenilen test", "calisilacak test", "calisilacak tetkik",
        "test listesi", "testler", "koagulasyon test", "calisilacak parametre"
    ]
    for h in headers:
        idx = t.find(h)
        if idx != -1:
            return t[idx: min(len(t), idx + 1600)]
    return ""


# ======================================================
# RULE EXTRACTION (V1)
# ======================================================
def extract_rules_from_text(raw_text: str) -> dict:
    t = normalize_tr(raw_text)
    rules = {}

    # --- Kanal min
    kanal_vals = []
    kanal_patterns = [
        r"en az\s*(\d+)\s*(adet\s*)?(olcum|test|reaksiyon)?\s*kanal",
        r"(\d+)\s*(adet\s*)?(olcum|test|reaksiyon)\s*kanali",
        r"en az\s*(\d+)\s*kanal"
    ]
    for pat in kanal_patterns:
        m = re.search(pat, t)
        if m:
            kanal_vals.append(int(m.group(1)))
    if kanal_vals:
        rules["kanal_min"] = max(kanal_vals)

    # --- Prob min
    prob_vals = []
    prob_patterns = [
        r"en az\s*(\d+)\s*prob",
        r"(\d+)\s*problu"
    ]
    for pat in prob_patterns:
        m = re.search(pat, t)
        if m:
            prob_vals.append(int(m.group(1)))
    if prob_vals:
        rules["prob_min"] = max(prob_vals)

    # --- Barkod requirement (numune / reaktif)
    barkod_req = {}
    if any(k in t for k in ["numune barkod", "hasta barkod", "sample barcode", "tup barkod", "primer tup barkod"]):
        barkod_req["numune"] = True
    if any(k in t for k in ["reaktif barkod", "kit barkod", "reagent barcode", "barkod okuyucu ile kit okutulur"]):
        barkod_req["reaktif"] = True
    if barkod_req:
        rules["barkod"] = barkod_req
    elif "barkod" in t:
        # genel barkod ifadesi: en az numune olarak kabul et
        rules["barkod"] = {"numune": True}

    # --- Okuma yöntemi
    methods = set()
    if "manyetik" in t:
        methods.add("manyetik")
    if any(k in t for k in ["mekanik", "clot", "clotting", "clot detection", "pihti", "pihti olusumu"]):
        methods.add("mekanik_clot")
    if "koagulometri" in t:
        methods.add("mekanik_clot")
    if methods:
        rules["okuma_yontemi"] = sorted(list(methods))

    # --- Test listesi ve testler
    test_block = extract_test_block(t)
    scan = test_block if test_block else t

    tests = {}
    if (" pt " in f" {scan} ") or ("protrombin" in scan):
        tests["PT"] = True
    if "aptt" in scan:
        tests["APTT"] = True
    if "fibrinojen" in scan:
        tests["Fibrinojen"] = True
    if any(k in scan for k in ["d-dimer", "d dimer", "ddimer"]):
        tests["D-Dimer"] = True
    if any(k in scan for k in ["faktor", "faktör", "factor"]):
        tests["Faktör"] = True
        dis_lab = any(k in scan for k in ["dis lab", "dis laboratuvar", "referans lab", "gonderilebilir", "hizmet alimi"])
        rules["faktor_durumu"] = "opsiyonel_dis_lab" if dis_lab else "zorunlu"

    if tests:
        rules["istenen_testler"] = tests

    return rules


# ======================================================
# EVALUATION ENGINES
# ======================================================
def evaluate_barkod(requirement: dict, device_koag: dict):
    device_barkod = device_get_barkod(device_koag)

    if requirement.get("numune") and not device_barkod.get("numune"):
        return {"madde": "Barkod (Numune)", "durum": "Uygun Değil", "aciklama": "Numune barkod okuyucu yok.", "zeyil": False}

    if requirement.get("reaktif") and not device_barkod.get("reaktif"):
        return {"madde": "Barkod (Reaktif)", "durum": "Zeyil", "aciklama": "Reaktif barkod okuyucu yok / eşdeğer yöntem gerekir.", "zeyil": True}

    return {"madde": "Barkod", "durum": "Uygun", "aciklama": "Barkod gereksinimleri karşılanıyor.", "zeyil": False}

def evaluate_kanal(rules: dict, device_koag: dict):
    req = rules.get("kanal_min")
    if not req:
        return {"madde": "Kanal Sayısı", "durum": "Bilgi Yok", "aciklama": "Şartnamede kanal sayısı yakalanamadı.", "zeyil": False}

    dev = safe_int(device_koag.get("kanal_toplam", 0)) or 0
    if dev >= req:
        return {"madde": "Kanal Sayısı", "durum": "Uygun", "aciklama": f"Şartname en az {req} kanal, cihaz {dev} kanal.", "zeyil": False}
    return {"madde": "Kanal Sayısı", "durum": "Uygun Değil", "aciklama": f"Şartname en az {req} kanal, cihaz {dev} kanal.", "zeyil": False}

def evaluate_prob(rules: dict, device_koag: dict):
    req = rules.get("prob_min")
    if not req:
        return {"madde": "Prob Sayısı", "durum": "Bilgi Yok", "aciklama": "Şartnamede prob sayısı yakalanamadı.", "zeyil": False}

    dev = safe_int(device_koag.get("prob_sayisi", 0)) or 0
    if dev >= req:
        return {"madde": "Prob Sayısı", "durum": "Uygun", "aciklama": f"Şartname en az {req} prob, cihaz {dev} prob.", "zeyil": False}
    return {"madde": "Prob Sayısı", "durum": "Uygun Değil", "aciklama": f"Şartname en az {req} prob, cihaz {dev} prob.", "zeyil": False}

def evaluate_okuma_yontemi(rules: dict, device_koag: dict):
    req_methods = rules.get("okuma_yontemi")
    if not req_methods:
        return {"madde": "Okuma Yöntemi", "durum": "Bilgi Yok", "aciklama": "Şartnamede okuma yöntemi yakalanamadı.", "zeyil": False}

    # cihazın kabiliyetini testler üzerinden çıkarıyoruz (V1)
    # SF-8300: testler string -> okuma tipi var. SF-400: bool -> bilinmiyor.
    tests = device_koag.get("testler", {})
    device_methods = set()
    for v in tests.values():
        if isinstance(v, str):
            if "manyetik" in v.lower():
                device_methods.add("manyetik")
            if "optik" in v.lower():
                device_methods.add("optik")
    # Şartname "mekanik/clot" istediğinde manyetik/clot kabulü genelde sahada zeyil ile döner.
    # Basit kural:
    # - manyetik isteniyorsa cihazda manyetik olmalı
    # - mekanik_clot isteniyorsa cihazda manyetik yoksa Uygun Değil; varsa Zeyil (yorum payı)
    req_set = set(req_methods)

    if "manyetik" in req_set and "manyetik" not in device_methods:
        return {"madde": "Okuma Yöntemi", "durum": "Uygun Değil", "aciklama": "Şartname manyetik okuma istiyor, cihazda yakalanamadı.", "zeyil": False}

    if "mekanik_clot" in req_set:
        if "manyetik" in device_methods:
            return {"madde": "Okuma Yöntemi", "durum": "Zeyil", "aciklama": "Şartname clot/mekanik ifade ediyor. Cihaz manyetik prensiple pıhtı algılaması yapıyor: zeyil/açıklama önerilir.", "zeyil": True}
        return {"madde": "Okuma Yöntemi", "durum": "Uygun Değil", "aciklama": "Şartname clot/mekanik istiyor, cihazda uygun yöntem yakalanamadı.", "zeyil": False}

    return {"madde": "Okuma Yöntemi", "durum": "Uygun", "aciklama": "Okuma yöntemi gereksinimi karşılanıyor.", "zeyil": False}

def evaluate_testler(rules: dict, device_koag: dict):
    req_tests = rules.get("istenen_testler")
    if not req_tests:
        return {"madde": "Testler", "durum": "Bilgi Yok", "aciklama": "Şartnamede istenen testler yakalanamadı.", "zeyil": False}

    missing = []
    for test_name, needed in req_tests.items():
        if not needed:
            continue
        # Faktör özel: cihaz çoğu zaman çalışmaz -> zorunluysa Uygun Değil, opsiyonelse Zeyil
        if test_name in ["Faktör", "Faktor"]:
            has_factor = device_has_test(device_koag, "Faktor") or device_has_test(device_koag, "Faktör")
            if not has_factor:
                faktor_durum = rules.get("faktor_durumu")
                if faktor_durum == "opsiyonel_dis_lab":
                    return {"madde": "Faktör Testleri", "durum": "Zeyil", "aciklama": "Faktör testleri cihazda yok; dış lab/referans lab ile karşılanması için zeyil/açıklama gerekir.", "zeyil": True}
                else:
                    return {"madde": "Faktör Testleri", "durum": "Uygun Değil", "aciklama": "Faktör testleri şartnamede zorunlu ve cihazda yok.", "zeyil": False}
        else:
            if not device_has_test(device_koag, test_name):
                missing.append(test_name)

    if missing:
        return {"madde": "Testler", "durum": "Uygun Değil", "aciklama": f"Şartnamede istenen testlerden eksik: {', '.join(missing)}", "zeyil": False}

    return {"madde": "Testler", "durum": "Uygun", "aciklama": "İstenen testler karşılanıyor (V1 yakalama).", "zeyil": False}

def aggregate_overall(results: list[dict]) -> dict:
    # Overall logic:
    # any Uygun Değil -> Uygun Değil
    # else any Zeyil -> Zeyil ile Uygun
    # else -> Uygun
    if any(r["durum"] == "Uygun Değil" for r in results):
        return {"durum": "Uygun Değil", "etiket": "🔴 Uygun Değil"}
    if any(r["durum"] == "Zeyil" for r in results):
        return {"durum": "Zeyil ile Uygun", "etiket": "🟡 Zeyil ile Uygun"}
    if all(r["durum"] in ["Uygun", "Bilgi Yok"] for r in results):
        return {"durum": "Uygun", "etiket": "🟢 Uygun"}
    return {"durum": "İnceleme Gerekli", "etiket": "⚪ İnceleme Gerekli"}


# ======================================================
# ZEYİL METNİ ÜRETİCİ
# ======================================================
def build_zeyil_text(item: dict, rules: dict, device_name: str, device_koag: dict) -> str:
    madde = item.get("madde", "Madde")
    aciklama = item.get("aciklama", "")

    # Basit ama ihale diline yakın zeyil şablonları
    if "Barkod (Reaktif)" in madde or ("Barkod" in madde and "Reaktif" in aciklama):
        return (
            "Zeyil Önerisi (Reaktif Barkod):\n"
            "Cihazda reaktif/kit tanımlama işlemleri, cihazın dahili/harici barkod okuyucusu ile ve/veya "
            "kullanıcının manuel reaktif tanımlaması yapabilmesine olanak sağlayacak şekilde gerçekleştirilebilir. "
            "Reaktiflerin cihazda güvenli şekilde tanımlanması ve izlenebilirliği sağlanacaktır."
        )

    if "Okuma Yöntemi" in madde:
        return (
            "Zeyil Önerisi (Okuma Yöntemi):\n"
            "Koagülasyon testleri pıhtı oluşumu (clot detection) prensibine dayalı olarak yürütülmekte olup; "
            "pıhtı algılama, cihazın manyetik/mekanik algılama prensipleri ile gerçekleştirilebilir. "
            "Cihaz, ilgili testlerde pıhtı oluşumunu güvenilir şekilde tespit ederek sonuç üretir."
        )

    if "Faktör" in madde:
        return (
            "Zeyil Önerisi (Faktör Testleri):\n"
            "Faktör testleri, laboratuvar sorumlusunun onayı doğrultusunda referans/dış laboratuvar hizmeti ile "
            "karşılanabilir. Bu kapsamda sonuçların sürekliliği ve hasta hizmetinin aksamaması için gerekli süreç firma tarafından yönetilecektir."
        )

    # Genel fallback
    return (
        f"Zeyil Önerisi ({madde}):\n"
        f"{aciklama}\n"
        "İlgili gereksinim, eşdeğer yöntem/uygulama ile karşılanabilecektir."
    )


# ======================================================
# PDF REPORT
# ======================================================
def generate_pdf_report(report_title: str, device_label: str, overall_label: str, df: pd.DataFrame, zeyil_texts: list[str]) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    x_margin = 18 * mm
    y = height - 18 * mm

    def draw_line(text, font="Helvetica", size=10, leading=14):
        nonlocal y
        c.setFont(font, size)
        for line in text.split("\n"):
            if y < 18 * mm:
                c.showPage()
                y = height - 18 * mm
                c.setFont(font, size)
            c.drawString(x_margin, y, line[:120])
            y -= leading

    # Header
    draw_line("İhaleBind - Uygunluk Raporu", font="Helvetica-Bold", size=14, leading=18)
    draw_line(f"Rapor: {report_title}", font="Helvetica", size=10)
    draw_line(f"Cihaz: {device_label}", font="Helvetica", size=10)
    draw_line(f"Genel Sonuç: {overall_label}", font="Helvetica-Bold", size=11)
    y -= 6

    # Table header
    draw_line("Karşılaştırma Tablosu:", font="Helvetica-Bold", size=12, leading=16)

    # Render table text-style (basit & stabil)
    for _, row in df.iterrows():
        draw_line(f"- {row['Madde']} | Şartname: {row['Şartname']} | Cihaz: {row['Cihaz']} | Sonuç: {row['Sonuç']}")
        if row.get("Açıklama"):
            draw_line(f"  Açıklama: {row['Açıklama']}")
        y -= 2

    # Zeyil section
    if zeyil_texts:
        y -= 10
        draw_line("Zeyil Önerileri:", font="Helvetica-Bold", size=12, leading=16)
        for z in zeyil_texts:
            draw_line(z, font="Helvetica", size=10, leading=14)
            y -= 6

    c.save()
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


# ======================================================
# UI
# ======================================================
st.set_page_config(page_title="İhaleBind", page_icon="🧬", layout="wide")

# Load devices
with open(DEVICE_PATH, "r", encoding="utf-8") as f:
    DEVICES = json.load(f)

st.markdown("# 🧬 İhaleBind\n### Şartnameyi okusun, kararı siz verin")
st.divider()

# Top selection
colA, colB = st.columns([1, 1])

with colA:
    brand = st.selectbox("Cihaz Markası", list(DEVICES.keys()))

models = list(DEVICES[brand].keys())

with colB:
    mode = st.selectbox(
        "Mod",
        ["Tek Cihaz Analizi", "Çoklu Cihaz Karşılaştırma"]
    )

# Sidebar - tender types (future)
with st.sidebar:
    st.header("📂 İhale Türleri")
    st.caption("Demo: Koagülasyon odaklı. Diğerleri ileride aktifleşecek.")
    st.success("Koagülasyon İhalesi")
    st.caption("Biyokimya İhalesi")
    st.caption("Hormon İhalesi")
    st.caption("Kan Gazı İhalesi")
    st.caption("İdrar İhalesi")
    st.caption("Hemogram İhalesi")

st.subheader("📄 Teknik Şartname")
uploaded = st.file_uploader("PDF veya Word yükleyin", type=["pdf", "docx"])

if uploaded:
    raw_text = extract_text_from_pdf(uploaded) if uploaded.name.lower().endswith(".pdf") else extract_text_from_docx(uploaded)

    if not raw_text.strip():
        st.error("Metin çıkarılamadı. PDF tarama olabilir (OCR gerekebilir).")
        st.stop()

    st.success("Metin çıkarıldı ✅")
    rules = extract_rules_from_text(raw_text)

    with st.expander("🧠 Şartnameden Yakalanan Kurallar (Debug)", expanded=False):
        st.json(rules)

    def run_full_evaluation(device_label: str, device_koag: dict):
        results = []
        # Barkod
        if "barkod" in rules:
            results.append(evaluate_barkod(rules["barkod"], device_koag))
        else:
            results.append({"madde": "Barkod", "durum": "Bilgi Yok", "aciklama": "Şartnamede barkod gereksinimi yakalanamadı.", "zeyil": False})

        # Kanal
        results.append(evaluate_kanal(rules, device_koag))
        # Prob
        results.append(evaluate_prob(rules, device_koag))
        # Okuma yöntemi
        results.append(evaluate_okuma_yontemi(rules, device_koag))
        # Testler
        results.append(evaluate_testler(rules, device_koag))

        overall = aggregate_overall(results)

        # Build table dataframe
        rows = []
        for r in results:
            madde = r["madde"]
            sonuc = r["durum"]
            aciklama = r.get("aciklama", "")

            # Şartname alanı (kısa)
            if madde == "Kanal Sayısı":
                s_req = f"min {rules.get('kanal_min','?')}"
                c_val = str(device_koag.get("kanal_toplam", "?"))
            elif madde == "Prob Sayısı":
                s_req = f"min {rules.get('prob_min','?')}"
                c_val = str(device_koag.get("prob_sayisi", "?"))
            elif madde.startswith("Barkod"):
                s_req = json.dumps(rules.get("barkod", {}), ensure_ascii=False)
                c_val = json.dumps(device_get_barkod(device_koag), ensure_ascii=False)
            elif madde == "Okuma Yöntemi":
                s_req = ", ".join(rules.get("okuma_yontemi", [])) or "?"
                # cihaz yöntemleri: testlerden çıkarıyoruz
                c_val = "manyetik/optik (test bazlı)" if any(isinstance(v, str) for v in device_koag.get("testler", {}).values()) else "bilinmiyor"
            elif madde in ["Testler", "Faktör Testleri"]:
                s_req = ", ".join([k for k, v in rules.get("istenen_testler", {}).items() if v]) or "?"
                c_val = ", ".join([k for k, v in device_koag.get("testler", {}).items() if (v is True or isinstance(v, str))]) or "?"
            else:
                s_req = "-"
                c_val = "-"

            rows.append({
                "Madde": madde,
                "Şartname": s_req,
                "Cihaz": c_val,
                "Sonuç": sonuc,
                "Açıklama": aciklama
            })

        df = pd.DataFrame(rows)

        # Zeyil texts
        zeyil_texts = []
        for r in results:
            if r["durum"] == "Zeyil":
                zeyil_texts.append(build_zeyil_text(r, rules, device_label, device_koag))

        return overall, df, zeyil_texts

    if mode == "Tek Cihaz Analizi":
        model = st.selectbox("Cihaz Modeli", models)
        selected = DEVICES[brand][model]
        device_koag = selected.get("koagulasyon", {})

        st.info(f"Seçilen Cihaz: **{brand} {model}**")

        overall, df, zeyil_texts = run_full_evaluation(f"{brand} {model}", device_koag)

        # 1) Genel Sonuç Motoru
        st.subheader("✅ Genel Sonuç")
        if overall["durum"] == "Uygun":
            st.success(overall["etiket"])
        elif overall["durum"] == "Zeyil ile Uygun":
            st.warning(overall["etiket"])
        else:
            st.error(overall["etiket"])

        # 2) Karşılaştırma Tablosu
        st.subheader("📊 Şartname - Cihaz Karşılaştırma Tablosu")
        st.dataframe(df, use_container_width=True)

        # 3) Otomatik Zeyil Metinleri
        st.subheader("📝 Otomatik Zeyil Önerileri")
        if zeyil_texts:
            for i, z in enumerate(zeyil_texts, start=1):
                st.text_area(f"Zeyil Önerisi #{i}", z, height=140)
        else:
            st.caption("Zeyil gerektiren bir madde yakalanmadı.")

        # 4) PDF Rapor
        st.subheader("📄 PDF Uygunluk Raporu")
        report_name = st.text_input("Rapor Adı", value=f"{brand} {model} - İhale Uygunluk Raporu")
        pdf_bytes = generate_pdf_report(
            report_title=report_name,
            device_label=f"{brand} {model}",
            overall_label=overall["etiket"],
            df=df,
            zeyil_texts=zeyil_texts
        )
        st.download_button(
            "📥 PDF Raporu İndir",
            data=pdf_bytes,
            file_name=f"{brand}_{model}_ihalebind_rapor.pdf".replace(" ", "_"),
            mime="application/pdf"
        )

    else:
        # Çoklu cihaz karşılaştırma
        selected_models = st.multiselect("Karşılaştırılacak Modeller", models, default=models[:2])

        if not selected_models:
            st.warning("En az 1 model seçmelisin.")
            st.stop()

        st.subheader("📊 Çoklu Cihaz Karşılaştırma")
        summary_rows = []
        detail_blocks = {}

        for m in selected_models:
            device_koag = DEVICES[brand][m].get("koagulasyon", {})
            overall, df, zeyil_texts = run_full_evaluation(f"{brand} {m}", device_koag)

            summary_rows.append({
                "Cihaz": f"{brand} {m}",
                "Genel Sonuç": overall["etiket"],
                "Zeyil Sayısı": sum(1 for x in df["Sonuç"].tolist() if x == "Zeyil"),
                "Uygun Değil Sayısı": sum(1 for x in df["Sonuç"].tolist() if x == "Uygun Değil"),
            })

            detail_blocks[m] = (overall, df, zeyil_texts)

        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

        with st.expander("Detayları göster", expanded=True):
            for m in selected_models:
                overall, df, zeyil_texts = detail_blocks[m]
                st.markdown(f"### {brand} {m} — {overall['etiket']}")
                st.dataframe(df, use_container_width=True)
                if zeyil_texts:
                    st.markdown("**Zeyil Önerileri:**")
                    for z in zeyil_texts:
                        st.code(z)
                st.divider()
