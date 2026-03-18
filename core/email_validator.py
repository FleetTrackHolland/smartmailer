"""
core/email_validator.py — Email Doğrulama Motoru (SmartMailer Ultimate)
DNS MX record kontrolü + SMTP doğrulama + disposable domain tespiti.
Bulunan email adreslerinin gerçek olup olmadığını doğrular.
"""
import re
import socket
import smtplib
from functools import lru_cache
from core.logger import get_logger

log = get_logger("email_validator")

# Disposable / geçici email domain'leri
DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "tempmail.com", "throwaway.email",
    "yopmail.com", "trashmail.com", "sharklasers.com", "guerrillamailblock.com",
    "grr.la", "dispostable.com", "mailnesia.com", "maildrop.cc",
    "10minutemail.com", "temp-mail.org", "fakeinbox.com",
}

# Catch-all olarak bilinen büyük sağlayıcılar (doğrulama yanıltıcı olabilir)
KNOWN_CATCHALL_PROVIDERS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
}


class EmailValidator:
    """DNS MX ve SMTP ile email doğrulama."""

    def __init__(self, verify_mx: bool = True, verify_smtp: bool = False):
        self._verify_mx = verify_mx
        self._verify_smtp = verify_smtp
        self._mx_cache: dict[str, bool] = {}
        self._stats = {
            "checked": 0,
            "valid_format": 0,
            "valid_mx": 0,
            "valid_smtp": 0,
            "invalid": 0,
            "disposable": 0,
        }

    def get_stats(self) -> dict:
        return dict(self._stats)

    def validate(self, email: str) -> tuple[bool, str]:
        """
        Email adresini doğrula.
        Returns: (is_valid, reason)
        """
        self._stats["checked"] += 1
        email = email.strip().lower()

        # 1. Format kontrolü
        if not self._check_format(email):
            self._stats["invalid"] += 1
            return False, "Geçersiz format"

        self._stats["valid_format"] += 1
        domain = email.split("@")[-1]

        # 2. Disposable domain kontrolü
        if domain in DISPOSABLE_DOMAINS:
            self._stats["disposable"] += 1
            return False, f"Disposable domain: {domain}"

        # 3. MX record kontrolü
        if self._verify_mx:
            has_mx = self._check_mx(domain)
            if not has_mx:
                self._stats["invalid"] += 1
                return False, f"MX kaydı bulunamadı: {domain}"
            self._stats["valid_mx"] += 1

        # 4. SMTP doğrulama (opsiyonel — agresif)
        if self._verify_smtp and domain not in KNOWN_CATCHALL_PROVIDERS:
            smtp_ok = self._check_smtp(email, domain)
            if smtp_ok:
                self._stats["valid_smtp"] += 1
            # SMTP başarısız olsa bile MX geçerliyse kabul et

        return True, "OK"

    def validate_batch(self, emails: list[str]) -> list[dict]:
        """Toplu email doğrulama."""
        results = []
        for email in emails:
            valid, reason = self.validate(email)
            results.append({"email": email, "valid": valid, "reason": reason})
        return results

    @staticmethod
    def _check_format(email: str) -> bool:
        """Temel format kontrolü."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def _check_mx(self, domain: str) -> bool:
        """DNS MX kaydı kontrolü (cached)."""
        if domain in self._mx_cache:
            return self._mx_cache[domain]

        try:
            import dns.resolver
            answers = dns.resolver.resolve(domain, 'MX')
            has_mx = len(answers) > 0
            self._mx_cache[domain] = has_mx
            return has_mx
        except ImportError:
            # dnspython yüklü değilse socket ile dene
            try:
                socket.getaddrinfo(domain, 25)
                self._mx_cache[domain] = True
                return True
            except socket.gaierror:
                self._mx_cache[domain] = False
                return False
        except Exception:
            # DNS hatası — domain muhtemelen geçersiz
            self._mx_cache[domain] = False
            return False

    def _check_smtp(self, email: str, domain: str) -> bool:
        """SMTP RCPT TO ile doğrulama (agresif — dikkatli kullan)."""
        try:
            import dns.resolver
            mx_records = dns.resolver.resolve(domain, 'MX')
            mx_host = str(sorted(mx_records, key=lambda r: r.preference)[0].exchange)

            with smtplib.SMTP(mx_host, 25, timeout=10) as smtp:
                smtp.ehlo("fleettrackholland.nl")
                smtp.mail("verify@fleettrackholland.nl")
                code, _ = smtp.rcpt(email)
                return code == 250
        except Exception:
            return False  # SMTP başarısız — MX kontrolüne güven

    def ping(self) -> bool:
        return True
