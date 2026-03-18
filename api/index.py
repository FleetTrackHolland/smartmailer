"""
Vercel Serverless Function Entry Point.
Flask uygulamasını Vercel serverless olarak çalıştırır.

NOT: Vercel serverless ortamında bazı kısıtlamalar vardır:
- Background thread'ler çalışmaz (otomasyon döngüsü)
- SQLite kalıcı değildir (her istek temiz başlar)
- SocketIO çalışmaz (WebSocket desteği yok)

Bu nedenle Vercel'de sadece DASHBOARD GÖRÜNTÜLEME çalışır.
Tam işlevsellik için uygulama bir VPS veya Railway'de çalıştırılmalıdır.
"""
import os
import sys

# Proje kök dizinini path'e ekle
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Config override: Vercel'de test modunda çalış
os.environ.setdefault("TEST_MODE", "true")

from web.api import app

# Vercel WSGI handler
app.debug = False
