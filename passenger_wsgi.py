"""
passenger_wsgi.py — DirectAdmin / Passenger WSGI Entry Point
FleetTrack Holland sunucusu için SmartMailer Ultimate giriş noktası.
"""
import os
import sys
import threading

# Proje kök dizinini hesapla ve PATH'e ekle
INTERP = os.path.expanduser("~/smartmailer/venv/bin/python3")
if sys.executable != INTERP:
    try:
        os.execl(INTERP, INTERP, *sys.argv)
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# .env dosyasını yükle
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# Flask uygulamasını import et
from web.api import app, _auto_start_automation

# Otomasyon thread'ini başlat (sonsuz lead toplama)
auto_thread = threading.Thread(target=_auto_start_automation, daemon=True)
auto_thread.start()

# Passenger WSGI callable — bu isim "application" olmalı
application = app
