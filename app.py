import streamlit as st
from pypdf import PdfReader
from docx import Document
import re
import json

# ======================================================
# METİN ÇIKARMA
# ======================================================
def extract_text_from_pdf(file):
    reader = PdfReader(file)
    return "\n".join(page.extract_text() or "" for page in reader.pages)

def extract_text_from_docx(file):
    doc = Document(file)
    return "\n".join(p.text for p in doc.paragraphs)

# ======================================================
# NORMALIZE
# ======================================================
def normalize_tr(text):
    text = text.lower()
    text = (
        text.replace("ı", "i")
        .replace("ş", "s")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ç", "c")
    )
    return re.sub(r"\s+", " ", text)

# ======================================================
# TEST LİSTESİ BLOĞU
# ======================================================
def extract_test_block(text):
    headers = [
        "istenen test",
        "calisilacak test",
        "test listesi",
        "testler",
        "calisilacak parametre"
    ]
    for h in headers:
        idx = text.find(h)
        if idx != -1:
            return text[idx:idx + 1200]
    return ""

# ======================================================
# ŞARTNAME KURAL ÇIKARICI (V1)
# ======================================================
def extract_rules(raw_text):
    t = normalize_tr(raw_text)
    rules = {}

    # Kanal
    kanal = re.findall(r"en az\s*(\d+)\s*kanal", t)
    if kanal:
        rules["kanal_min"] = max(map(int, kanal))

    # Prob
    prob = re.findall(r"en az\s*(\d+)\s*prob", t)
    if prob:
        rules["prob_min"] = max(map(int, prob))

    # =========================
    # BARKOD (AYRINTILI)
    # =========================
    barkod = {}

    if any(k in t for k in [
        "numune barkod", "hasta barkod", "tup barkod", "sample barcode"
    ]):
        barkod["numune"] = True

    if any(k in t for k in [
        "reaktif barkod", "kit barkod", "reagent barcode"
    ]):
        barkod["reaktif"] = True

    if barkod:
        rules["barkod"] = barkod

    # Okuma yöntemi
    methods = []
    if "manyetik" in t:
        methods.append("manyetik")
    if any(k in t for k in ["mekanik", "clot", "pihti"]):
        methods.append("mekanik_clot")
    if methods:
        rules["okuma_yontemi"] = methods

    # =========================
    # TESTLER
    #
