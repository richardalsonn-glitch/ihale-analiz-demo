# İhale Analiz Demo (Koagülasyon) - Streamlit

## Kurulum
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Çalıştırma
```bash
streamlit run app.py
```

## Hosting (kolay)
- Streamlit Community Cloud (ücretsiz demo için uygun)
- Render (web service olarak)
- Kendi VPS (Nginx + systemd)

## Demo v1 Notları
- PDF metin tabanlı olmalı. Tarama PDF ise OCR gerekir (demo v1’de yok).
- Grup algılama A/B anahtar kelimelerine dayanır.
- Test sayıları demo’da grup bazlı girilir (hastane bazlı geliştirme faz 2).
