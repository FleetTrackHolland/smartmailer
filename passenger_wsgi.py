import os
import sys
import traceback

# Proje dizini
sys.path.insert(0, os.path.dirname(__file__))

# ─── PASSENGER MODE FLAG ─────────────────────────────────────────
# Bu flag agent'ların lazy-load olmasını ve background thread'lerin
# başlamamasını sağlar. Passenger startup timeout'unu önler.
os.environ["PASSENGER_MODE"] = "true"

# .env yukle
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except Exception:
    pass

# ─── PASSENGER MODE ───────────────────────────────────────────
# Signal to the app that we're running under Passenger WSGI.
# This disables background threads, auto-start automation, and
# heavy module-level initialization that would cause timeouts.
os.environ["PASSENGER_MODE"] = "true"

# Flask uygulamasini yukle — hata olursa basit hata sayfasi goster
import time as _time
_start = _time.time()
try:
    from web.api import app as application
    _elapsed = _time.time() - _start
    try:
        with open(os.path.join(os.path.dirname(__file__), 'startup_timing.log'), 'w') as f:
            f.write(f"Startup OK in {_elapsed:.2f}s\n")
    except Exception:
        pass
except Exception as e:
    # Hata detaylarini logla
    error_msg = traceback.format_exc()
    try:
        with open(os.path.join(os.path.dirname(__file__), 'startup_error.log'), 'w') as f:
            f.write(error_msg)
    except Exception:
        pass

    # Basit WSGI fallback — 500 error sayfasi
    def application(environ, start_response):
        status = '500 Internal Server Error'
        output = f"""<!DOCTYPE html>
<html><head><title>SmartMailer — Hata</title>
<style>
body {{ font-family: Arial, sans-serif; background: #f5f5f5; display: flex;
       align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
.card {{ background: #fff; border-radius: 12px; padding: 40px; max-width: 600px;
         box-shadow: 0 4px 20px rgba(0,0,0,0.1); text-align: center; }}
h1 {{ color: #e8600a; }}
pre {{ text-align: left; background: #1a1a2e; color: #e0e0e0; padding: 16px;
       border-radius: 8px; overflow-x: auto; font-size: 12px; white-space: pre-wrap; }}
</style></head><body>
<div class="card">
<h1>Uygulama Baslatma Hatasi</h1>
<p>Sunucu baslatilamadi. Asagidaki hata detaylarini kontrol edin:</p>
<pre>{error_msg}</pre>
<p style="margin-top:20px;color:#666">Bu hata <code>startup_error.log</code> dosyasina da kaydedildi.</p>
</div></body></html>"""
        response_headers = [
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Content-Length', str(len(output.encode('utf-8'))))
        ]
        start_response(status, response_headers)
        return [output.encode('utf-8')]
