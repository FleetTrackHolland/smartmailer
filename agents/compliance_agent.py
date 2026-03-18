"""
agents/compliance_agent.py — AVG / GDPR Uyum Kontrolü
Email validator yerine regex kullanır (bağımlılık yok).
"""
import csv
import os
import re
from config import config
from core.logger import get_logger

log = get_logger("compliance")

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

PERSONAL_DOMAINS = {
    "gmail.com", "hotmail.com", "yahoo.com", "outlook.com",
    "live.com", "icloud.com", "me.com", "msn.com",
    "ziggo.nl", "kpnmail.nl", "home.nl", "hetnet.nl", "planet.nl",
    "upcmail.nl", "chello.nl", "tele2.nl",
}


class ComplianceAgent:

    def __init__(self):
        self._unsubscribe = self._load_unsubscribe()
        log.info(f"Compliance ajani hazır. Opt-out: {len(self._unsubscribe)} adres.")

    def _load_unsubscribe(self) -> set:
        path = config.UNSUBSCRIBE_FILE
        if not os.path.exists(path):
            return set()
        emails = set()
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("email"):
                    emails.add(row["email"].strip().lower())
        return emails

    def is_ok_to_send(self, email: str) -> tuple[bool, str]:
        email = email.strip().lower()

        if not EMAIL_RE.match(email):
            return False, f"Geçersiz format: {email}"

        if email in self._unsubscribe:
            return False, f"Opt-out listesinde: {email}"

        domain = email.split("@")[-1]
        if domain in PERSONAL_DOMAINS:
            return False, f"Kişisel adres (B2B değil): {email}"

        return True, ""

    def add_unsubscribe(self, email: str, reason: str = "user_request"):
        email = email.strip().lower()
        self._unsubscribe.add(email)
        path = config.UNSUBSCRIBE_FILE
        exists = os.path.exists(path)
        with open(path, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["email", "reason", "date"])
            if not exists:
                w.writeheader()
            from datetime import datetime
            w.writerow({"email": email, "reason": reason,
                        "date": datetime.now().isoformat()})
        log.info(f"Opt-out kaydedildi: {email}")

    def ping(self) -> bool:
        return True
