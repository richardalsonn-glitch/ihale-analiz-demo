import re
import math
import io
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# PDF text extraction
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

# Word extraction (optional)
try:
    import docx2txt
except ImportError:
    docx2txt = None


# -----------------------------
# Device Profiles (Demo v1)
# -----------------------------
DEVICE_PROFILES = {
    "Succeeder SF-8300": {
        "branch": "Koagülasyon",
        "automation": "tam",
        "system": "açık",
        "channels_total": 8,
        "channels_optic": 4,
        "channels_magnetic": 4,
        "probes": 3,
        "cap_piercing": True,
        "level_sensor": True,
        "alerts_audio": True,
        "alerts_visual": True,
        "incubation_positions": 20,
        "supports": {
            "PT": True,
            "APTT": True,
            "FIB": True,
            "DDIMER": True,
            "FACTOR": False,  # Demo: locked
        },
        "methods": {
            "PT": "manyetik",
            "APTT": "manyetik",
            "FIB": "manyetik",
            "DDIMER": "optik",
        },
    },
    "Succeeder SF-400": {
        "branch": "Koagülasyon",
        "automation": "yarı",
        "system": "açık",
        "channels_total": 4,
        "channels_optic": 0,
        "channels_magnetic": 4,
        "probes": 0,  # semi-auto; not comparable
        "cap_piercing": False,
        "level_sensor": False,
        "alerts_audio": False,
        "alerts_visual": True,
        "incubation_positions": 1,
        "supports": {
            "PT": True,
            "APTT": True,
            "FIB": True,
            "DDIMER": False,   # assume not
            "FACTOR": False,   # Demo: locked
        },
        "methods": {
            "PT": "manyetik",
            "APTT": "manyetik",
            "FIB": "manyetik",
        },
    },
}

# -----------------------------
# Rule dictionary (Demo v1)
# -----------------------------
@dataclass
class RuleResult:
    clause: str
    requirement: str
    device_value: str
    status: str  # "Uygun" | "Riskli" | "Uygun Değil"


def extract_text_from_pdf(file_bytes: bytes) -> str:
    if pdfplumber is None:
        return ""
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            text_parts.append(t)
    return "\n".join(text_parts)


def extract_text_from_docx(file_bytes: bytes) -> str:
    if docx2txt is None:
        return ""
    # docx2txt expects a file path; write to temp
    import tempfile, os
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        txt = docx2txt.process(tmp_path) or ""
    finally:
        os.unlink(tmp_path)
    return txt


def normalize_text(s: str) -> str:
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = s.replace("\r", "\n")
    s = re.sub(r"\n{2,}", "\n", s)
    return s.lower()


def detect_duration_months(text: str) -> Tuple[int, str]:
    """
    Returns (months, evidence_snippet)
    Priority: lines containing 'hizmet süresi'/'sözleşme süresi'/'ihale süresi'
    Fallback: most frequent '(\d+) ay' / '(\d+) yıl'
    """
    lines = text.splitlines()
    key_lines = [ln for ln in lines if any(k in ln for k in ["hizmet süresi", "sözleşme süresi", "ihale süresi"])]
    def scan_for_months(ln: str) -> Optional[int]:
        m = re.search(r"(\d{1,2})\s*\(?[^\)]*\)?\s*ay", ln)
        if m:
            return int(m.group(1))
        y = re.search(r"(\d{1,2})\s*yıl", ln)
        if y:
            return int(y.group(1))*12
        return None

    for ln in key_lines:
        val = scan_for_months(ln)
        if val:
            return val, ln.strip()[:200]

    # fallback: global scan
    months = []
    for m in re.finditer(r"(\d{1,2})\s*\(?[^\)]*\)?\s*ay", text):
        months.append(int(m.group(1)))
    years = []
    for y in re.finditer(r"(\d{1,2})\s*yıl", text):
        years.append(int(y.group(1))*12)
    candidates = months + years
    if candidates:
        # most common
        from collections import Counter
        c = Counter(candidates)
        val, _ = c.most_common(1)[0]
        # evidence: first occurrence
        ev = ""
        m = re.search(rf"(.{{0,40}}{val}\s*\(?[^\)]*\)?\s*ay.{{0,40}})", text)
        if m:
            ev = m.group(1)
        return val, (ev[:200] if ev else "metin içinde süre ifadesi bulundu")
    return 24, "süre tespit edilemedi, varsayılan 24 ay"


def detect_groups(text: str) -> Dict[str, Dict]:
    """
    Detect A/B group blocks using headers 'a grubu' / 'b grubu'.
    Returns dict like { 'A Grubu': {'block': '...', 'expected_automation': 'tam'}, ... }
    """
    groups = {}
    # simple split by headers
    # capture blocks starting at "a grubu" or "b grubu" until next group or end
    pattern = r"(a\s*grubu.*?)(?=b\s*grubu|$)|(b\s*grubu.*?)(?=a\s*grubu|$)"
    # Use a more stable approach: find indices of headers
    headers = []
    for m in re.finditer(r"\b(a\s*grubu|b\s*grubu)\b", text):
        headers.append((m.start(), m.group(1)))
    if not headers:
        groups["Genel"] = {"block": text, "expected_automation": None}
        return groups

    headers_sorted = sorted(headers, key=lambda x: x[0])
    for i, (idx, h) in enumerate(headers_sorted):
        end = headers_sorted[i+1][0] if i+1 < len(headers_sorted) else len(text)
        block = text[idx:end]
        name = "A Grubu" if "a" in h else "B Grubu"
        exp = None
        if "tam otomatik" in block:
            exp = "tam"
        elif "yarı otomatik" in block or "yari otomatik" in block:
            exp = "yarı"
        groups[name] = {"block": block, "expected_automation": exp}
    return groups


def extract_hospital_names(block_text: str) -> List[str]:
    """
    Extract hospital names from a block, looking for lines containing 'devlet hastanesi'.
    This is best-effort for demo.
    """
    names = set()
    for ln in block_text.splitlines():
        if "devlet hastanesi" in ln:
            # split by commas
            parts = [p.strip(" -•\t,;:") for p in re.split(r",|;|•|\u2022", ln)]
            for p in parts:
                if "devlet hastanesi" in p and len(p) > 8:
                    # restore capitalization roughly
                    names.add(p.title())
    return sorted(names)


def detect_tests_requested(text: str) -> Dict[str, bool]:
    keys = {
        "PT": r"\bpt\b|protrombin",
        "APTT": r"\baptt\b|a\.?\s*p\.?\s*t\.?\s*t",
        "FIB": r"fibrinojen|fib\b",
        "DDIMER": r"d[\-\s]?dimer|d-dimer",
        "FACTOR": r"fakt[oö]r|factor\s*(viii|ix|xi|xii|vii|x)",
    }
    found = {}
    for k, pat in keys.items():
        found[k] = re.search(pat, text) is not None
    return found


def build_compliance_table(group_name: str, group_info: Dict, device_name: str, full_text: str) -> pd.DataFrame:
    dev = DEVICE_PROFILES[device_name]
    block = group_info.get("block", full_text)
    req_auto = group_info.get("expected_automation")
    tests_req = detect_tests_requested(block)

    rows: List[RuleResult] = []

    # Automation
    if req_auto:
        status = "Uygun" if dev["automation"] == req_auto else "Uygun Değil"
        rows.append(RuleResult("Cihaz tipi", f"{'Tam otomatik' if req_auto=='tam' else 'Yarı otomatik'}", 
                               "Tam otomatik" if dev["automation"]=="tam" else "Yarı otomatik", status))

    # Channels/probes basics (demo)
    # If 'en az 4 kanal' appears in block, enforce
    if re.search(r"en az\s*4.*(kanal|ölçüm)", block):
        status = "Uygun" if dev["channels_total"] >= 4 else "Uygun Değil"
        rows.append(RuleResult("Kanal sayısı", "≥ 4", str(dev["channels_total"]), status))
    elif re.search(r"en az\s*2.*(kanal|ölçüm)", block):
        status = "Uygun" if dev["channels_total"] >= 2 else "Uygun Değil"
        rows.append(RuleResult("Kanal sayısı", "≥ 2", str(dev["channels_total"]), status))

    if re.search(r"en az\s*2\s*\(?iki\)?\s*probl", block):
        status = "Uygun" if dev.get("probes", 0) >= 2 else "Uygun Değil"
        rows.append(RuleResult("Prob sayısı", "≥ 2", str(dev.get("probes", 0)), status))

    # Reading methods if demanded
    if "manyetik" in block and "optik" in block:
        status = "Uygun" if (dev["channels_magnetic"]>0 and dev["channels_optic"]>0) else "Uygun Değil"
        rows.append(RuleResult("Okuma yöntemi", "Optik + Manyetik", 
                               f"Optik:{dev['channels_optic']} / Manyetik:{dev['channels_magnetic']}", status))

    # Tests
    for test_key, label in [("PT","PT"),("APTT","aPTT"),("FIB","Fibrinojen"),("DDIMER","D-Dimer"),("FACTOR","Faktör Testleri")]:
        if tests_req.get(test_key):
            supported = dev["supports"].get(test_key, False)
            status = "Uygun" if supported else "Uygun Değil"
            rows.append(RuleResult(f"Test kapsamı", f"{label} çalışılmalı", "Var" if supported else "Yok", status))

    # Cap piercing / level sensor if demanded
    if "kapak delme" in block or "cap piercing" in block:
        status = "Uygun" if dev.get("cap_piercing") else "Uygun Değil"
        rows.append(RuleResult("Kapak delme", "Olmalı", "Var" if dev.get("cap_piercing") else "Yok", status))

    if "seviye" in block or "level" in block:
        status = "Uygun" if dev.get("level_sensor") else "Uygun Değil"
        rows.append(RuleResult("Seviye sensörü", "Olmalı", "Var" if dev.get("level_sensor") else "Yok", status))

    df = pd.DataFrame([r.__dict__ for r in rows])
    return df


def compute_materials(total_tests: int, rules: Dict[str, float]) -> Dict[str, int]:
    """
    rules:
      tube_ratio, needle_ratio, cuvette_per_tests, bead_per_test, bead_bottle_size
    """
    tube = math.ceil(total_tests * rules.get("tube_ratio", 0.0))
    needle = math.ceil(total_tests * rules.get("needle_ratio", 0.0))
    cuvette = math.ceil(total_tests / rules.get("cuvette_pack_tests", 1000))
    beads = math.ceil(total_tests * rules.get("bead_per_test", 0))
    bead_bottles = math.ceil(beads / rules.get("bead_bottle_size", 1000)) if beads else 0
    return {
        "Sitratlı Tüp (13x75, %3.2)": tube,
        "Emniyetli İğne Ucu": needle,
        f"Küvet (1 kutu = {rules.get('cuvette_pack_tests',1000)} test)": cuvette,
        "Bilye (1 test = 1 bilye)": beads,
        f"Bilye Şişesi (1 şişe = {rules.get('bead_bottle_size',1000)} adet)": bead_bottles
    }


# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="İhale Analiz Demo", layout="wide")

st.title("İhale Analiz Demo (Koagülasyon)")

with st.sidebar:
    st.header("1) Şartname Yükle")
    uploaded = st.file_uploader("PDF / DOCX yükle", type=["pdf","docx"])
    st.header("2) Cihaz Seçimi")
    device_A = st.selectbox("A Grubu (Tam otomatik) cihaz", list(DEVICE_PROFILES.keys()), index=0)
    device_B = st.selectbox("B Grubu (Yarı otomatik) cihaz", list(DEVICE_PROFILES.keys()), index=1 if len(DEVICE_PROFILES)>1 else 0)
    st.header("3) Sarf Kuralı")
    tube_ratio = st.number_input("Tüp oranı (örn 0.6667)", min_value=0.0, max_value=2.0, value=0.6667, step=0.01, format="%.4f")
    needle_ratio = st.number_input("İğne oranı (örn 0.15)", min_value=0.0, max_value=1.0, value=0.15, step=0.01, format="%.2f")
    cuvette_pack_tests = st.number_input("Küvet kutusu kaç testlik?", min_value=1, max_value=5000, value=1000, step=10)
    bead_per_test = st.number_input("Bilye (test başına)", min_value=0.0, max_value=5.0, value=1.0, step=0.5)
    bead_bottle_size = st.number_input("Bilye şişesi kaç adet?", min_value=1, max_value=10000, value=1000, step=100)

rules = {
    "tube_ratio": tube_ratio,
    "needle_ratio": needle_ratio,
    "cuvette_pack_tests": int(cuvette_pack_tests),
    "bead_per_test": float(bead_per_test),
    "bead_bottle_size": int(bead_bottle_size)
}

if not uploaded:
    st.info("Başlamak için sol menüden bir şartname dosyası yükleyin (PDF/DOCX).")
    st.stop()

file_bytes = uploaded.read()

raw_text = ""
if uploaded.name.lower().endswith(".pdf"):
    raw_text = extract_text_from_pdf(file_bytes)
elif uploaded.name.lower().endswith(".docx"):
    raw_text = extract_text_from_docx(file_bytes)

if not raw_text.strip():
    st.error("Metin çıkarılamadı. PDF metin tabanlı değilse (tarama) OCR gerekebilir. Demo v1 OCR içermez.")
    st.stop()

text = normalize_text(raw_text)

months, evidence = detect_duration_months(text)
groups = detect_groups(text)

# Header summary
col1, col2, col3, col4 = st.columns(4)
col1.metric("İhale Süresi", f"{months} Ay")
col2.metric("Grup Sayısı", str(len(groups)))
# Hospital count (best-effort)
all_h = []
for g in groups.values():
    all_h.extend(extract_hospital_names(g.get("block","")))
all_h = sorted(set(all_h))
col3.metric("Tespit Edilen Hastane", str(len(all_h)))
col4.metric("Branş", "Koagülasyon")

st.caption(f"**Süre kanıtı:** {evidence}")

st.divider()

# Group cards
st.subheader("Algılanan Gruplar ve Hastaneler")
for gname, ginfo in groups.items():
    with st.expander(f"{gname} (beklenen: {('Tam otomatik' if ginfo.get('expected_automation')=='tam' else 'Yarı otomatik' if ginfo.get('expected_automation')=='yarı' else '—')})", expanded=True):
        hs = extract_hospital_names(ginfo.get("block",""))
        if hs:
            st.write("**Hastaneler:**")
            st.write("\n".join([f"- {h}" for h in hs]))
        else:
            st.write("Hastane listesi bu bloktan net çıkarılamadı (demo sınırlaması).")

st.divider()

# Test counts input per group
st.subheader("Test Sayıları (Süreye bağlı toplam)")
st.write("Demo v1: Hastane bazlı zorunlu değil; grup bazlı toplam test girilebilir.")
cols = st.columns(2)
a_tests = cols[0].number_input("A Grubu toplam test", min_value=0, value=0, step=1000)
b_tests = cols[1].number_input("B Grubu toplam test", min_value=0, value=0, step=1000)

st.divider()

# Compliance tables
st.subheader("Uygunluk Analizi")

for gname, ginfo in groups.items():
    device = device_A if gname == "A Grubu" else device_B if gname == "B Grubu" else device_A
    df = build_compliance_table(gname, ginfo, device, text)
    st.markdown(f"### {gname} → **{device}**")
    if df.empty:
        st.info("Bu grup için analiz edilecek kural yakalanamadı (demo sınırlaması).")
    else:
        # Add colored status
        def status_emoji(s):
            return {"Uygun":"🟢 Uygun","Riskli":"🟡 Riskli","Uygun Değil":"🔴 Uygun Değil"}.get(s,s)
        out = df.copy()
        out["status"] = out["status"].map(status_emoji)
        out = out.rename(columns={"clause":"Şartname Maddesi", "requirement":"Gereklilik", "device_value":"Cihaz", "status":"Sonuç"})
        st.dataframe(out, use_container_width=True, hide_index=True)

st.divider()

# Materials
st.subheader("Malzeme & Sarf Hesapları")
mat_cols = st.columns(2)

if a_tests > 0:
    mats_a = compute_materials(int(a_tests), rules)
    mat_cols[0].markdown("### A Grubu Sarf")
    mat_cols[0].dataframe(pd.DataFrame(list(mats_a.items()), columns=["Malzeme","Adet"]), use_container_width=True, hide_index=True)
else:
    mat_cols[0].info("A Grubu için test sayısı girin.")

if b_tests > 0:
    mats_b = compute_materials(int(b_tests), rules)
    mat_cols[1].markdown("### B Grubu Sarf")
    mat_cols[1].dataframe(pd.DataFrame(list(mats_b.items()), columns=["Malzeme","Adet"]), use_container_width=True, hide_index=True)
else:
    mat_cols[1].info("B Grubu için test sayısı girin.")

# Combined export
st.divider()
st.subheader("Excel İndir")
combined = []
if a_tests > 0:
    for k,v in compute_materials(int(a_tests), rules).items():
        combined.append(["A Grubu", k, v])
if b_tests > 0:
    for k,v in compute_materials(int(b_tests), rules).items():
        combined.append(["B Grubu", k, v])

if combined:
    df_x = pd.DataFrame(combined, columns=["Grup","Malzeme","Adet"])
    towrite = io.BytesIO()
    with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
        df_x.to_excel(writer, index=False, sheet_name="Sarf Listesi")
    st.download_button("Excel indir (Sarf Listesi)", data=towrite.getvalue(), file_name="sarf_listesi.xlsx")
else:
    st.info("Excel indir için en az bir grup test sayısı girin.")
