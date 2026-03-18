"""
Minimal passenger_wsgi.py — Sadece temel Flask test
DirectAdmin/CloudLinux/Passenger için
"""
import os
import sys

# ─── PATH SETUP ───
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# CloudLinux virtualenv — otomatik tespit
HOME = os.path.expanduser("~")
rel_path = PROJECT_ROOT.replace(HOME + "/", "")

possible_venvs = [
    os.path.join(HOME, "virtualenv", rel_path, "3.12", "lib", "python3.12", "site-packages"),
    os.path.join(HOME, "virtualenv", rel_path, "3.12", "lib64", "python3.12", "site-packages"),
    os.path.join(PROJECT_ROOT, "lib"),
]

for venv in possible_venvs:
    if os.path.isdir(venv):
        sys.path.insert(0, venv)

# .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except Exception:
    pass

# ─── FLASK APP ───
try:
    from web.api import app as flask_app

    def application(environ, start_response):
        # Passenger SCRIPT_NAME düzeltmesi
        script = environ.get('SCRIPT_NAME', '')
        path = environ.get('PATH_INFO', '')
        if script and path.startswith(script):
            environ['PATH_INFO'] = path[len(script):] or '/'
        environ['SCRIPT_NAME'] = ''
        return flask_app(environ, start_response)

    # Otomasyon
    try:
        import threading
        from web.api import _auto_start_automation
        t = threading.Thread(target=_auto_start_automation, daemon=True)
        t.start()
    except Exception:
        pass

except Exception as e:
    # Import hatası varsa, hata mesajını göster
    import traceback
    error_details = traceback.format_exc()

    def application(environ, start_response):
        status = '500 Internal Server Error'
        output = f"""
        <html><body>
        <h1>SmartMailer Startup Error</h1>
        <pre>ERROR: {str(e)}</pre>
        <h2>Traceback:</h2>
        <pre>{error_details}</pre>
        <h2>sys.path:</h2>
        <pre>{chr(10).join(sys.path)}</pre>
        <h2>PROJECT_ROOT:</h2>
        <pre>{PROJECT_ROOT}</pre>
        <h2>Files in PROJECT_ROOT:</h2>
        <pre>{chr(10).join(os.listdir(PROJECT_ROOT))}</pre>
        </body></html>
        """.encode('utf-8')
        response_headers = [('Content-type', 'text/html'),
                          ('Content-Length', str(len(output)))]
        start_response(status, response_headers)
        return [output]
