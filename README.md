# ⚡ SmartMailer Ultimate

AI-Powered Lead Discovery & Campaign Engine — Claude AI ile otomatik lead keşfi, kişiselleştirilmiş email yazımı ve akıllı kampanya yönetimi.

## 🚀 Özellikler

- **10+ Kaynaktan Lead Keşfi** — DeTelefoongids, Opendi, Telefoonboek, OpenStreetMap, Bing, DuckDuckGo, AI bilgi bankası
- **Claude AI Email Yazımı** — Her şirkete özel, kişiselleştirilmiş email içeriği
- **QC ≥90 Zorunlu** — Düşük kaliteli email gönderilmez
- **A/B Test** — 3 farklı konu başlığı, en iyi performans göstereni otomatik seçer
- **3 Aşamalı Follow-Up** — 3. gün, 7. gün, 14. gün otomatik takip
- **Duplicate Önleme** — Aynı adrese tekrar gönderim engellenir
- **9 Akıllı Agent** — Copywriter, QC, Compliance, Lead Scorer, Orchestrator, Follow-Up, Response Tracker, Lead Finder, Watchdog
- **Sonsuz Lead Toplama** — Durdurana kadar sürekli lead toplar, 20 Hollanda şehri × tüm sektörler
- **Self-Improving AI** — Agent'lar müşteri yanıtlarından ve kullanıcı feedbackinden öğrenir

## 📋 Gereksinimler

- Python 3.10+
- Anthropic API Key (Claude AI)
- Brevo API Key (email gönderimi)

## ⚡ Hızlı Başlangıç

```bash
# 1. Repoyu klonla
git clone https://github.com/KULLANICI/smartmailer-ultimate.git
cd smartmailer-ultimate

# 2. Bağımlılıkları kur
pip install -r requirements.txt

# 3. .env dosyasını oluştur
cp .env.example .env
# .env dosyasını düzenleyin: API key'leri ekleyin

# 4. Uygulamayı başlat
python main.py --web --port 5000
```

Tarayıcıda `http://localhost:5000` adresine gidin.

## 🔧 .env Yapılandırması

```env
ANTHROPIC_API_KEY=sk-ant-...
BREVO_API_KEY=xkeysib-...
SENDER_EMAIL=info@example.com
SENDER_NAME=Your Name
TEST_MODE=true
```

## 📁 Proje Yapısı

```
smartmailer-ultimate/
├── agents/           # 9 AI Agent
├── core/             # Veritabanı, email engine, şablonlar
├── web/              # Flask web dashboard
│   └── static/       # HTML, CSS, JS
├── api/              # Vercel serverless entry
├── config.py         # Yapılandırma
├── main.py           # Ana giriş noktası
└── requirements.txt  # Python bağımlılıkları
```

## ⚠️ Vercel Dağıtım Notu

Vercel'de **sadece dashboard ve API** çalışır. Otomasyon döngüsü (background thread) Vercel serverless ortamında desteklenmez. Tam işlevsellik için uygulamayı bir VPS üzerinde (veya Railway/Render) çalıştırın.

## 📄 Lisans

MIT License
