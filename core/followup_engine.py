"""
core/followup_engine.py — Follow-Up Sequence Engine (v4)
Gönderilen e-postalara otomatik takip zinciri.
3 aşama: Gün 3 (meraklı), Gün 7 (değer ekleme), Gün 14 (urgency).
"""
import json
import requests
from datetime import datetime, timedelta
from config import config
from core.logger import get_logger
from core.database import db

log = get_logger("followup")

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"


# ─── FOLLOW-UP PROMPT'LARI ─────────────────────────────────────

FOLLOWUP_PROMPTS = {
    1: """Je bent een senior sales professional bij FleetTrack Holland (GPS tracking).
Je hebt eerder een cold e-mail gestuurd naar dit bedrijf. Er is GEEN reactie gekomen.

ORIGINELE E-MAIL ONDERWERP: {original_subject}
BEDRIJF: {company}
SECTOR: {sector}
AANTAL VOERTUIGEN: {vehicles}

Schrijf een KORTE follow-up e-mail (max 100 woorden) in het Nederlands.
Toon: Vriendelijk, licht nieuwsgierig, niet opdringerig.
Begin NIET met "Ik stuur deze e-mail op..." of vergelijkbare zinnen.
Suggereer subtiel dat je waarde kunt bieden.

Antwoord ALLEEN in JSON:
{{"subject": "...", "body_html": "<p>...</p>", "body_text": "..."}}
""",

    2: """Je bent een senior sales professional bij FleetTrack Holland (GPS tracking).
Dit is je TWEEDE follow-up. De eerste e-mail en eerste follow-up zijn onbeantwoord.

ORIGINELE ONDERWERP: {original_subject}
BEDRIJF: {company}
SECTOR: {sector}
VOERTUIGEN: {vehicles}

Schrijf een waardevolle follow-up (max 120 woorden) in het Nederlands.
Deel een CONCREET inzicht: een relevante case study, industriestatistiek of tip.
Bijvoorbeeld: "Transport bedrijven besparen gemiddeld 15% op brandstof met GPS tracking"
Maak het persoonlijk voor hun sector.
Eindig met een zachte CTA.

Antwoord ALLEEN in JSON:
{{"subject": "...", "body_html": "<p>...</p>", "body_text": "..."}}
""",

    3: """Je bent een senior sales professional bij FleetTrack Holland (GPS tracking).
Dit is je DERDE en LAATSTE follow-up. Alle eerdere berichten zijn onbeantwoord.

ORIGINELE ONDERWERP: {original_subject}
BEDRIJF: {company}
SECTOR: {sector}
VOERTUIGEN: {vehicles}

Schrijf een KORTE, professionele afsluit-e-mail (max 80 woorden) in het Nederlands.
Gebruik schaarste/urgentie zonder opdringerig te zijn:
- "Ik sluit mijn dossier..." of "Ik neem aan dat dit momenteel geen prioriteit is..."
- Laat de deur open voor toekomstig contact
- Eindig met respect

Antwoord ALLEEN in JSON:
{{"subject": "...", "body_html": "<p>...</p>", "body_text": "..."}}
""",
}


class FollowUpEngine:
    """3-aşamalı otomatik follow-up zinciri."""

    def __init__(self):
        self._headers = {
            "x-api-key": config.ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }

    # ─── ZAMANLANMIŞ FOLLOW-UP'LARI OLUŞTUR ────────────────────

    def schedule_followups(self, email: str, original_subject: str,
                           company: str, sector: str = "",
                           vehicles: str = "", campaign_id: str = ""):
        """İlk gönderim sonrası 3 follow-up zamanla."""
        if not config.FOLLOWUP_ENABLED:
            return

        now = datetime.now()
        steps = [
            (1, config.FOLLOWUP_DAY_1),  # Gün 3
            (2, config.FOLLOWUP_DAY_2),  # Gün 7
            (3, config.FOLLOWUP_DAY_3),  # Gün 14
        ]

        for step, days in steps:
            scheduled_at = (now + timedelta(days=days)).isoformat()
            db.schedule_followup(
                email=email,
                step=step,
                scheduled_at=scheduled_at,
                original_subject=original_subject,
                company=company,
                sector=sector,
                vehicles=vehicles,
                campaign_id=campaign_id,
            )

        log.info(f"[FOLLOWUP] 3 takip zamanlandı: {email} "
                 f"(Gün {config.FOLLOWUP_DAY_1}/{config.FOLLOWUP_DAY_2}"
                 f"/{config.FOLLOWUP_DAY_3})")

    # ─── BEKLEYEN FOLLOW-UP'LARI İŞLE ──────────────────────────

    def process_pending(self) -> list[dict]:
        """Zamanı gelen follow-up'ları üret ve gönder."""
        pending = db.get_pending_followups()
        results = []

        for fu in pending:
            email = fu["email"]
            step = fu["step"]

            # Yanıt geldiyse atla
            if db.has_response(email):
                db.update_followup_status(fu["id"], "skipped_replied")
                log.info(f"[FOLLOWUP] Atlandı (yanıt var): {email} step {step}")
                continue

            # Unsubscribe olduysa atla
            if db.is_unsubscribed(email):
                db.update_followup_status(fu["id"], "skipped_unsub")
                continue

            # E-posta açılmış ama yanıt yok → daha agresif follow-up
            has_opened = db.has_opened(email)

            try:
                draft = self._generate_followup(
                    step=step,
                    original_subject=fu.get("original_subject", ""),
                    company=fu.get("company", ""),
                    sector=fu.get("sector", ""),
                    vehicles=fu.get("vehicles", ""),
                    has_opened=has_opened,
                )
                results.append({
                    "id": fu["id"],
                    "email": email,
                    "step": step,
                    "subject": draft["subject"],
                    "body_html": draft["body_html"],
                    "body_text": draft["body_text"],
                    "has_opened": has_opened,
                })
            except Exception as e:
                log.error(f"[FOLLOWUP] Üretim hatası: {email} step {step} — {e}")
                db.update_followup_status(fu["id"], "error")

        return results

    # ─── AI FOLLOW-UP ÜRETİCİ ──────────────────────────────────

    def _generate_followup(self, step: int, original_subject: str,
                           company: str, sector: str, vehicles: str,
                           has_opened: bool = False) -> dict:
        """Claude ile follow-up e-postası üret."""

        prompt_template = FOLLOWUP_PROMPTS.get(step, FOLLOWUP_PROMPTS[1])
        user_prompt = prompt_template.format(
            original_subject=original_subject,
            company=company,
            sector=sector or "onbekend",
            vehicles=vehicles or "onbekend",
        )

        if has_opened:
            user_prompt += ("\n\nBELANGRIJK: Deze persoon heeft je eerdere "
                           "e-mail GEOPEND maar NIET gereageerd. "
                           "Verwijs hier subtiel naar.")

        payload = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": 600,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        resp = requests.post(CLAUDE_API_URL, json=payload,
                             headers=self._headers, timeout=30)
        if not resp.ok:
            raise Exception(f"Claude follow-up hatası: {resp.status_code}")

        raw = resp.json()["content"][0]["text"]

        json_str = raw
        if "```json" in raw:
            json_str = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            json_str = raw.split("```")[1].split("```")[0]

        return json.loads(json_str.strip())

    # ─── İSTATİSTİKLER ─────────────────────────────────────────

    def get_stats(self) -> dict:
        """Follow-up istatistikleri."""
        return db.get_followup_stats()

    def ping(self) -> bool:
        return True
