"""
core/send_engine.py — Brevo E-posta Gönderim Motoru (v4 — Deliverability Optimizer)
Brevo REST API (birincil) ve SMTP (yedek).
v4: Warm-up pattern, Reply-To, bounce detection, per-domain throttle.
"""
import smtplib
import ssl
import time
import requests
from collections import defaultdict
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dataclasses import dataclass, field
from config import config
from core.logger import get_logger

log = get_logger("send_engine")

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

# ─── WARM-UP SCHEDULE ─────────────────────────────────────────
# Hafta numarasına göre günlük max gönderim limiti
# Domain doğrulanmış (SPF/DKIM/DMARC) → daha agresif başlangıç
WARMUP_SCHEDULE = {
    1: 40, 2: 60, 3: 80, 4: 100,
    5: 120, 6: 150, 7: 200, 8: 300,
}


@dataclass
class EmailMessage:
    to_email: str
    to_name: str
    subject: str
    html_body: str
    text_body: str
    campaign_id: str = ""
    lead_id: str = ""


@dataclass
class SendResult:
    success: bool
    message_id: str = ""
    error: str = ""
    method: str = ""
    is_bounce: bool = False


class SendEngine:

    def __init__(self):
        # Per-domain throttle: domain → [timestamp, timestamp, ...]
        self._domain_sends: dict[str, list[float]] = defaultdict(list)
        self._max_per_domain_per_hour = 3
        # Bounce tracking
        self._bounce_count = 0
        self._total_sent = 0
        # Warm-up tracking
        self._start_date = datetime.now()
        self._daily_sent = 0
        self._last_reset_day = datetime.now().date()
        log.info("SendEngine v4 hazır (warm-up + bounce detect + domain throttle).")

    # ─── WARM-UP LİMİT KONTROLÜ ──────────────────────────────────

    def get_warmup_limit(self) -> int:
        """Mevcut haftaya göre günlük warm-up limitini hesapla."""
        days_active = (datetime.now() - self._start_date).days
        week = min((days_active // 7) + 1, 8)
        return WARMUP_SCHEDULE.get(week, 150)

    def _reset_daily_counter(self):
        """Gün değiştiyse daily counter sıfırla."""
        today = datetime.now().date()
        if today != self._last_reset_day:
            self._daily_sent = 0
            self._last_reset_day = today

    def can_send_today(self) -> tuple[bool, str]:
        """Bugün hâlâ gönderim yapılabilir mi?"""
        self._reset_daily_counter()
        warmup_limit = self.get_warmup_limit()
        effective_limit = min(warmup_limit, config.DAILY_SEND_LIMIT)
        if self._daily_sent >= effective_limit:
            return False, f"Günlük limit doldu ({self._daily_sent}/{effective_limit})"
        return True, ""

    # ─── PER-DOMAIN THROTTLE ──────────────────────────────────────

    def _check_domain_throttle(self, email: str) -> bool:
        """Aynı domain'e saat başı max N gönderim kontrolü."""
        domain = email.split("@")[-1].lower()
        now = time.time()
        one_hour_ago = now - 3600

        # Eski kayıtları temizle
        self._domain_sends[domain] = [
            t for t in self._domain_sends[domain] if t > one_hour_ago
        ]

        if len(self._domain_sends[domain]) >= self._max_per_domain_per_hour:
            log.info(f"[THROTTLE] Domain limiti: {domain} "
                     f"({len(self._domain_sends[domain])}/{self._max_per_domain_per_hour}/saat)")
            return False

        return True

    def _record_domain_send(self, email: str):
        domain = email.split("@")[-1].lower()
        self._domain_sends[domain].append(time.time())

    # ─── BOUNCE TESPİT ────────────────────────────────────────────

    @property
    def bounce_rate(self) -> float:
        if self._total_sent == 0:
            return 0.0
        return self._bounce_count / self._total_sent

    def record_bounce(self):
        self._bounce_count += 1

    def is_bounce_critical(self) -> bool:
        """Bounce rate %5'i geçtiyse kritik."""
        return self._total_sent >= 10 and self.bounce_rate > 0.05

    # ─── ANA GÖNDERIM ─────────────────────────────────────────────

    def send(self, msg: EmailMessage) -> SendResult:

        # Warm-up limit kontrolü
        can, reason = self.can_send_today()
        if not can:
            log.warning(f"[WARMUP] {reason}")
            return SendResult(False, error=reason, method="warmup_limit")

        # Per-domain throttle
        if not self._check_domain_throttle(msg.to_email):
            return SendResult(False,
                              error=f"Domain throttle: {msg.to_email.split('@')[-1]}",
                              method="domain_throttle")

        # Bounce rate kontrolü
        if self.is_bounce_critical():
            log.error(f"[BOUNCE] Kritik bounce rate: {self.bounce_rate:.1%} — gönderim durduruldu!")
            return SendResult(False, error="Bounce rate kritik (>5%)",
                              method="bounce_stop")

        # Gönder
        if config.BREVO_API_KEY:
            r = self._via_brevo_api(msg)
            if r.success:
                self._daily_sent += 1
                self._total_sent += 1
                self._record_domain_send(msg.to_email)
                return r
            if r.is_bounce:
                self.record_bounce()
            log.warning(f"Brevo API başarısız: {r.error} — SMTP'ye geçiliyor")

        result = self._via_smtp(msg)
        if result.success:
            self._daily_sent += 1
            self._total_sent += 1
            self._record_domain_send(msg.to_email)
        return result

    # ─── BREVO REST API ───────────────────────────────────────────

    def _via_brevo_api(self, msg: EmailMessage) -> SendResult:
        headers = {
            "api-key": config.BREVO_API_KEY,
            "content-type": "application/json",
            "accept": "application/json",
        }

        # Reply-To header + List-Unsubscribe (RFC 8058)
        reply_to = config.SENDER_EMAIL
        unsub_url = f"{config.UNSUBSCRIBE_URL}?email={msg.to_email}"

        payload = {
            "sender": {
                "name": config.SENDER_NAME,
                "email": config.SENDER_EMAIL,
            },
            "replyTo": {
                "name": config.SENDER_NAME,
                "email": reply_to,
            },
            "to": [{"email": msg.to_email, "name": msg.to_name}],
            "subject": msg.subject,
            "htmlContent": msg.html_body,
            "textContent": msg.text_body,
            "headers": {
                "Reply-To": f"{config.SENDER_NAME} <{reply_to}>",
                "List-Unsubscribe": f"<{unsub_url}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
            "tags": [msg.campaign_id] if msg.campaign_id else [],
        }
        # BCC — gönderilen her mailin kopyasını sales@ adresine gönder
        bcc_email = getattr(config, 'BCC_EMAIL', 'sales@fleettrackholland.nl')
        if bcc_email:
            payload["bcc"] = [{"email": bcc_email}]
        try:
            resp = requests.post(BREVO_API_URL, json=payload,
                                 headers=headers, timeout=15)
            resp.raise_for_status()
            msg_id = resp.json().get("messageId", "brevo-ok")
            log.info(f"[BREVO API ✅] → {msg.to_email} | ID: {msg_id}")
            return SendResult(True, str(msg_id), method="brevo_api")
        except requests.HTTPError as e:
            status_code = getattr(e.response, "status_code", 0)
            # Response body — Brevo'nun gerçek hata mesajını al
            resp_text = ""
            try:
                resp_text = e.response.text[:500] if e.response else ""
            except Exception:
                pass
            log.error(f"[BREVO API ❌] {msg.to_email} — HTTP {status_code} — {resp_text}")
            is_bounce = status_code in (421, 450, 550, 553)
            return SendResult(False, error=f"HTTP {status_code}: {resp_text[:200]}", method="brevo_api",
                              is_bounce=is_bounce)
        except Exception as e:
            log.error(f"[BREVO API ❌] {msg.to_email} — Exception: {e}")
            return SendResult(False, error=str(e), method="brevo_api")

    # ─── BREVO SMTP (yedek) ───────────────────────────────────────

    def _via_smtp(self, msg: EmailMessage) -> SendResult:
        if not config.BREVO_SMTP_PASS:
            return SendResult(False, error="BREVO_SMTP_PASS eksik",
                              method="brevo_smtp")
        try:
            reply_to = config.SENDER_EMAIL
            unsub_url = f"{config.UNSUBSCRIBE_URL}?email={msg.to_email}"

            mime = MIMEMultipart("alternative")
            mime["Subject"] = msg.subject
            mime["From"]    = f"{config.SENDER_NAME} <{config.SENDER_EMAIL}>"
            mime["To"]      = f"{msg.to_name} <{msg.to_email}>"
            mime["Reply-To"] = f"{config.SENDER_NAME} <{reply_to}>"
            mime["List-Unsubscribe"] = f"<{unsub_url}>"
            mime["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
            # BCC
            bcc_email = getattr(config, 'BCC_EMAIL', 'sales@fleettrackholland.nl')
            recipients = [msg.to_email]
            if bcc_email:
                mime["Bcc"] = bcc_email
                recipients.append(bcc_email)
            mime.attach(MIMEText(msg.text_body, "plain", "utf-8"))
            mime.attach(MIMEText(msg.html_body, "html", "utf-8"))

            ctx = ssl.create_default_context()
            with smtplib.SMTP(config.BREVO_SMTP_HOST,
                              config.BREVO_SMTP_PORT) as srv:
                srv.ehlo()
                srv.starttls(context=ctx)
                srv.login(config.BREVO_SMTP_USER, config.BREVO_SMTP_PASS)
                srv.sendmail(config.SENDER_EMAIL, recipients,
                             mime.as_string())

            log.info(f"[SMTP ✅] → {msg.to_email}")
            return SendResult(True, "smtp-ok", method="brevo_smtp")
        except Exception as e:
            log.error(f"[SMTP ❌] → {msg.to_email}: {e}")
            return SendResult(False, error=str(e), method="brevo_smtp")

    # ─── İSTATİSTİKLER ────────────────────────────────────────────

    def get_deliverability_stats(self) -> dict:
        """Deliverability istatistikleri."""
        return {
            "daily_sent": self._daily_sent,
            "warmup_limit": self.get_warmup_limit(),
            "effective_limit": min(self.get_warmup_limit(), config.DAILY_SEND_LIMIT),
            "total_sent": self._total_sent,
            "bounce_count": self._bounce_count,
            "bounce_rate": round(self.bounce_rate * 100, 2),
            "is_critical": self.is_bounce_critical(),
            "warmup_week": min(((datetime.now() - self._start_date).days // 7) + 1, 8),
        }

    def ping(self) -> bool:
        return True
