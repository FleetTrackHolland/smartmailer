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
