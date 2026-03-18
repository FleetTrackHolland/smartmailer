"""
passenger_wsgi.py — DirectAdmin / CloudLinux / Passenger WSGI Entry Point
"""
import os
import sys

# Proje kök dizini
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# CloudLinux virtualenv path
VENV_PATH = os.path.join(
    os.path.expanduser("~"),
    "virtualenv",
    PROJECT_ROOT.replace(os.path.expanduser("~") + "/", ""),
    "3.12",
    "lib",
    "python3.12",
    "site-packages"
)

# Virtualenv site-packages ekle
if os.path.isdir(VENV_PATH):
    sys.path.insert(0, VENV_PATH)

# Proje kökünü PATH'e ekle
sys.path.insert(0, PROJECT_ROOT)

# lib klasörü varsa (pip --target ile kurulmuş)
LIB_PATH = os.path.join(PROJECT_ROOT, "lib")
if os.path.isdir(LIB_PATH):
    sys.path.insert(0, LIB_PATH)

# .env dosyasını yükle
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except ImportError:
    pass

# Flask uygulamasını import et
from web.api import app

# Passenger URL prefix düzeltmesi
# DirectAdmin /smartmailer prefix'ini Flask'e doğru iletmek için
class PassengerPathFix:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # SCRIPT_NAME'den PATH_INFO'yu düzelt
        script_name = environ.get('SCRIPT_NAME', '')
        path_info = environ.get('PATH_INFO', '')
        if script_name and path_info.startswith(script_name):
            environ['PATH_INFO'] = path_info[len(script_name):]
        if not environ.get('PATH_INFO'):
            environ['PATH_INFO'] = '/'
        return self.app(environ, start_response)

# Otomasyon thread'ini başlat
try:
    import threading
    from web.api import _auto_start_automation
    auto_thread = threading.Thread(target=_auto_start_automation, daemon=True)
    auto_thread.start()
except Exception as e:
    print(f"Auto-start hatasi: {e}", file=sys.stderr)

# Passenger WSGI callable
application = PassengerPathFix(app)
