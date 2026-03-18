import os
import sys

# Proje dizini
sys.path.insert(0, os.path.dirname(__file__))

# .env yukle
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except Exception:
    pass

# Flask uygulamasi
from web.api import app as application

# Otomasyon thread - arkaplanda lead bulma ve email gonderme
try:
    import threading
    from web.api import _auto_start_automation
    t = threading.Thread(target=_auto_start_automation, daemon=True)
    t.start()
except Exception:
    pass
