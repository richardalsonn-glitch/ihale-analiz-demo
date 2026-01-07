import streamlit as st
import json
import re
from typing import Dict, Any, Tuple, List
from pypdf import PdfReader
from docx import Document

# ======================================================
# CONFIG
# ======================================================
ALL_IHALELER = [
    "Koagülasyon",
    "Biyokimya",
    "Hormon",
    "Kan Gazı",
    "İdrar",
    "Hemogram",
]

# ======================================================
# FILE TEXT EXTRACT
# ======================================================
def extract_text(file) -> str:
    name = file.name.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(file)
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    if name.endswith(".docx"):
        doc = Document(file)
        return "\n".join(p.text for p in doc.paragraphs)
    return ""

# ======================================================
# NORMALIZE
# ======================================================
def normalize(text: str) -> str:
    text = text.lower()
    for a, b in [("ı","i"), ("ş","s"), ("ğ","g"), ("ü","u"), ("ö","o"), ("ç","c")]:
        text = text.replace(a, b)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# ======================================================
# REQUIREMENT EXTRACTION (V1)
# ======================================================
def extract_rules_from_text(raw: str) -> Dict[str, Any]:
    t = normalize(raw)
    rules: Dict[str, Any] = {}

    # --- Kanal (en az X kanal)
    kanal_vals = re.findall(r"en az\s*(\d+)\s*(adet\s*)?(olcum|test|reaksiyon)?\s*kanal", t)
    if kanal_vals:
        nums = [int(x[0]) for x in kanal_vals]
        rules["kanal_min"] = max(nums)

    # --- Prob
    prob_vals = re.findall(r"en az\s*(\d+)\s*\(?[a-z]*\)?\s*prob", t)
    if prob_vals:
        rules["prob_min"] = max(int(x) for x in prob_vals)

    # --- Kapak delme
    if any(k in t for k in ["kapak delme", "piercing", "cap piercing"]):
        rules["kapak_delme"] = True

    # --- Barkod (numune/reaktif)
    barkod: Dict[str, bool] = {}
    if any(k in t for k in ["numune barkod", "hasta barkod", "tup barkod", "sample barcode", "patient barcode"]):
        barkod["numune"] = True
    if any(k in t for k in ["reaktif barkod", "kit barkod", "reagent barcode", "reagent bar code"]):
        barkod["reaktif"] = True
    # Bazı şartnameler sadece "barkod okuyucu" yazar; bunu genel bilgi olarak saklayalım:
    if "barkod" in t and not barkod:
        barkod["genel"] = True
    if barkod:
        rules["barkod"] = barkod

    # --- Okuma yöntemi (clot/koagülometri)
    # Şartnamede "koagulometri" / "clotting" / "clot detection" / "pıhtı" geçiyorsa clot temelli kabul ediyoruz.
    if any(k in t for k in ["koagulometri", "clotting", "clot detection", "clot", "pihti", "pıhtı"]):
        rules["okuma"] = "clot_detection"
    # Ek: kromojenik / immünolojik istenebilir (şimdilik bilgi amaçlı yakala)
    if any(k in t for k in ["kromojenik", "chromogenic"]):
        rules["kromojenik"] = True
    if any(k in t for k in ["immunolojik", "immünolojik", "immunoassay"]):
        rules["immunolojik"] = True

    # --- Testler (PT / APTT / Fibrinojen / D-Dimer / Faktör)
    tests: Dict[str, bool] = {}
    if re.search(r"\bpt\b|protrombin zamani", t):
        tests["PT"] = True
    # aPTT yazım varyasyonları
    if re.search(r"\ba\s*\.?\s*p\s*\.?\s*t\s*\.?\s*t\b|\baptt\b", t):
        tests["APTT"] = True
    if "fibrinojen" in t:
        tests["Fibrinojen"] = True
    if re.search(r"d\s*[-]?\s*dimer|\bddimer\b", t):
        tests["D-Dimer"] = True
    if re.search(r"faktor|faktör|factor", t):
        tests["Faktor"] = True
        # Dış lab opsiyonu (şimdilik bilgi)
        if any(k in t for k in ["dis lab", "dis laboratuvar", "referans lab", "gonderilebilir", "hizmet alimi", "hizmet alımı"]):
            rules["faktor_durumu"] = "opsiyonel_dis_lab"
        else:
            rules["faktor_durumu"] = "zorunlu"

    if tests:
        rules["testler"] = tests

    return rules

# ======================================================
# HELPERS
# ======================================================
def bool_to_tr(x: Any) -> str:
    return "Var" if bool(x) else "Yok"

def get_device_coag_block(model_block: Dict[str, Any]) -> Dict[str, Any]:
    # İleride biyokimya vs eklenince benzer bloklar da olur.
    return model_block.get("koagulasyon", {})

def safe_compare_missing() -> Tuple[str, str]:
    return ("Bilgi Yok", "Şartnamede bu madde bulunamadı, lütfen manuel kontrol ediniz.")

def compare_numeric_min(rule_key: str, rule_label: str, device_val: Any, rules: Dict[str, Any]) -> Tuple[str, str]:
    if rule_key not in rules:
        return safe_compare_missing()
    try:
        needed = int(rules[rule_key])
        dv = int(device_val) if device_val is not None else None
    except Exception:
        return ("Bilgi Yok", "Değer okunamadı, lütfen manuel kontrol ediniz.")
    if dv is None:
        return ("Bilgi Yok", "Cihaz verisi eksik, lütfen cihaz kataloğunu kontrol ediniz.")
    if dv >= needed:
        return ("Uygun", f"Şartname ≥ {needed} / Cihaz {dv}")
    return ("Uygun Değil", f"Şartname ≥ {needed} / Cihaz {dv}")

def compare_kapak_delme(device: Dict[str, Any], rules: Dict[str, Any]) -> Tuple[str, str]:
    if "kapak_delme" not in rules:
        return safe_compare_missing()
    return ("Uygun", "Kapak delme mevcut.") if device.get("kapak_delme") else ("Uygun Değil", "Kapak delme yok.")

def evaluate_barkod(requirement: Dict[str, Any], device_barkod: Dict[str, Any]) -> Tuple[str, str]:
    """
    requirement: {'numune': True, 'reaktif': True}  veya {'genel': True}
    device_barkod: {'numune': True, 'reaktif': False}
    """
    if not requirement:
        return safe_compare_missing()

    # Şartname sadece "barkod okuyucu" diyorsa:
    if requirement.get("genel") and not (requirement.get("numune") or requirement.get("reaktif")):
        # Cihazda herhangi barkod var mı?
        if device_barkod.get("numune") or device_barkod.get("reaktif"):
            return ("Uygun", "Barkod okuyucu mevcut (numune/reaktif).")
        return ("Uygun Değil", "Barkod okuyucu bulunmuyor.")

    # Numune barkod zorunlu kabul
    if requirement.get("numune"):
        if not device_barkod.get("numune"):
            return ("Uygun Değil", "Şartname numune barkod okuyucu istemektedir.")

    # Reaktif barkod çoğu ihalede zeyil ihtimali — ama şartnamede özellikle istendiyse kontrol edelim:
    if requirement.get("reaktif"):
        if not device_barkod.get("reaktif"):
            return ("Zeyil", "Reaktif barkod okuyucu bulunmamaktadır (zeyil önerilir).")

    return ("Uygun", "Barkod gereksinimleri karşılanmaktadır.")

def compare_okuma_yontemi(device: Dict[str, Any], rules: Dict[str, Any]) -> Tuple[str, str]:
    if "okuma" not in rules:
        return safe_compare_missing()

    # Şartname clot/koagülometri istiyor.
    # Cihaz tarafında "manyetik/optik kanal" varsa bu clot algılama prensibinde ölçüm yapılabildiğini varsayıyoruz.
    # (SF-8300 manyetik/optik kanallar => clot detection prensibi)
    has_any_channel = any(device.get(k) for k in ["kanal_manyetik", "kanal_optik", "kanal_toplam"])
    if has_any_channel:
        return ("Uygun", "Şartname clot/koagülometri istiyor. Cihaz manyetik/optik kanallarda pıhtı oluşumu (clot) temelli ölçüm yapar.")
    return ("Bilgi Yok", "Cihaz okuma yöntemi verisi eksik, manuel kontrol ediniz.")

def compare_tests(device_tests: Dict[str, Any], rules: Dict[str, Any]) -> Tuple[str, str]:
    if "testler" not in rules or not isinstance(rules["testler"], dict) or len(rules["testler"]) == 0:
        return safe_compare_missing()

    required = [k for k, v in rules["testler"].items() if v]
    if not required:
        return safe_compare_missing()

    missing: List[str] = []
    for test in required:
        dv = device_tests.get(test)
        # cihaz test mapping'i string de olabilir (manyetik/optik) veya bool
        if dv is False or dv is None:
            missing.append(test)

    if not missing:
        return ("Uygun", "Şartnamede yakalanan testler cihazda mevcut.")
    return ("Zeyil", "Eksik/uyumsuz görünen testler: " + ", ".join(missing))

# ======================================================
# STREAMLIT UI
# ======================================================
st.set_page_config(page_title="İhaleBind", page_icon="🧬", layout="wide")

# ---- load devices.json
with open("devices.json", "r", encoding="utf-8") as f:
    DEVICES = json.load(f)

st.title("🧬 İhaleBind")
st.caption("Şartnameyi okusun, kararı siz verin")

# ======================================================
# SIDEBAR - İhale seçimi
# ======================================================
with st.sidebar:
    st.header("📂 İhale Türleri")
    selected_ihale = st.radio(
        "İhale seçiniz",
        ALL_IHALELER,
        index=0,
        label_visibility="collapsed"
    )

# ======================================================
# Filter brands/models by selected ihale
# ======================================================
def device_supports_ihale(model_block: Dict[str, Any], ihale_name: str) -> bool:
    return ihale_name in (model_block.get("ihale_turleri", []) or [])

filtered_brands = {}
for brand, models in DEVICES.items():
    kept_models = {m: mb for m, mb in models.items() if device_supports_ihale(mb, selected_ihale)}
    if kept_models:
        filtered_brands[brand] = kept_models

if not filtered_brands:
    st.warning(f"'{selected_ihale}' ihalesini destekleyen cihaz henüz ekli değil. devices.json içine bu ihale türünü destekleyen cihazları ekleyince otomatik görünecek.")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    marka = st.selectbox("Cihaz Markası", list(filtered_brands.keys()))
with col2:
    model = st.selectbox("Cihaz Modeli", list(filtered_brands[marka
