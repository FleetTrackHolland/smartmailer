"""
agents/response_tracker.py — AI Response Classification Agent (v4)
Gelen yanıtları Claude AI ile sınıflandırır ve otomatik aksiyon alır.
Sınıflar: interested, not_interested, question, out_of_office, bounce.
"""
import json
import requests
from datetime import datetime
from config import config
from core.logger import get_logger
from core.database import db

log = get_logger("response_tracker")

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"

CLASSIFY_PROMPT = """Je bent een sales intelligence AI voor FleetTrack Holland (GPS fleet tracking).
Classificeer het volgende e-mail antwoord van een lead.

CLASSIFICATIES:
- "interested": Lead toont interesse, vraagt om meer info, wil een demo, noemt een afspraak
- "not_interested": Expliciet geen interesse, vraagt om geen contact meer
- "question": Stelt een vraag over prijs, functionaliteit, of implementatie
- "out_of_office": Automatisch out-of-office antwoord
- "bounce": Onbestelbaar, e-mail niet ontvangen
- "unsubscribe": Wil van de mailinglijst af

Geef ook een sentiment score (0-100) en een samenvatting.

Antwoord ALLEEN in JSON:
{
    "classification": "interested|not_interested|question|out_of_office|bounce|unsubscribe",
    "confidence": 0.0-1.0,
    "sentiment": 0-100,
    "summary": "korte samenvatting",
    "suggested_action": "beschrijving van aanbevolen actie",
    "auto_reply_needed": true|false,
    "auto_reply_text": "optioneel: tekst voor automatisch antwoord"
}
"""

REPLY_PROMPT = """Je bent een professionele sales medewerker bij FleetTrack Holland (GPS fleet tracking).
Een lead heeft gereageerd op je cold e-mail met een VRAAG.

OORSPRONKELIJK ONDERWERP: {original_subject}
BEDRIJF: {company}
SECTOR: {sector}

HUN VRAAG/BERICHT:
{response_text}

Schrijf een professioneel, behulpzaam antwoord in het Nederlands (max 150 woorden).
- Beantwoord hun vraag specifiek
- Verwijs naar FleetTrack Holland GPS tracking voordelen
- Prijs: vanaf EUR 9,99/voertuig/maand
- Website: www.fleettrackholland.nl
- Bied een vrijblijvende demo of gesprek aan
- Toon: Warm, professioneel, niet opdringerig

Antwoord ALLEEN in JSON:
{{"subject": "Re: ...", "body_html": "<p>...</p>", "body_text": "..."}}
"""


class ResponseTracker:
    """AI-powered response classification and auto-reply."""

    def __init__(self):
        self._headers = {
            "x-api-key": config.ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        log.info("ResponseTracker agent hazır.")

    def classify_response(self, email: str, response_text: str,
                          original_subject: str = "") -> dict:
        """Yanıtı AI ile sınıflandır."""
        payload = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": 500,
            "system": CLASSIFY_PROMPT,
            "messages": [{"role": "user", "content": f"""
                E-MAIL VAN: {email}
                OORSPRONKELIJK ONDERWERP: {original_subject}
                
                ANTWOORD:
                {response_text}
            """}],
        }

        try:
            resp = requests.post(CLAUDE_API_URL, json=payload,
                                 headers=self._headers, timeout=20)
            if not resp.ok:
                raise Exception(f"Claude API: {resp.status_code}")

            raw = resp.json()["content"][0]["text"]
            json_str = raw
            if "```json" in raw:
                json_str = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                json_str = raw.split("```")[1].split("```")[0]

            result = json.loads(json_str.strip())
            result["email"] = email
            result["classified_at"] = datetime.now().isoformat()

            # Veritabanına kaydet
            db.save_response(
                email=email,
                classification=result["classification"],
                confidence=result.get("confidence", 0.5),
                sentiment=result.get("sentiment", 50),
                summary=result.get("summary", ""),
                response_text=response_text,
                original_subject=original_subject,
            )

            # Otomatik aksiyonlar
            self._handle_classification(result, email)

            log.info(f"[RESPONSE] {email} → {result['classification']} "
                     f"(confidence: {result.get('confidence', 0):.0%})")
            return result

        except Exception as e:
            log.error(f"[RESPONSE] Sınıflandırma hatası: {email} — {e}")
            return self._fallback_classify(response_text, email)

    def _handle_classification(self, result: dict, email: str):
        """Sınıflandırmaya göre otomatik aksiyon al."""
        cls = result["classification"]

        if cls == "not_interested" or cls == "unsubscribe":
            db.add_opt_out(email)
            db.cancel_pending_followups(email)
            log.info(f"[RESPONSE] Opt-out: {email}")

        elif cls == "interested":
            db.cancel_pending_followups(email)
            db.flag_lead_hot(email)
            log.info(f"[RESPONSE] 🔥 HOT LEAD: {email}")

        elif cls == "out_of_office":
            db.postpone_followups(email, days=3)
            log.info(f"[RESPONSE] OOO — follow-up 3 gün ertelendi: {email}")

        elif cls == "bounce":
            db.mark_lead_invalid(email)
            db.cancel_pending_followups(email)
            log.info(f"[RESPONSE] Bounce — geçersiz: {email}")

    def generate_auto_reply(self, email: str, response_text: str,
                            original_subject: str = "",
                            company: str = "", sector: str = "") -> dict:
        """Sorulara otomatik yanıt üret."""
        user_prompt = REPLY_PROMPT.format(
            original_subject=original_subject,
            company=company,
            sector=sector or "onbekend",
            response_text=response_text,
        )

        payload = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": 500,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        resp = requests.post(CLAUDE_API_URL, json=payload,
                             headers=self._headers, timeout=30)
        if not resp.ok:
            raise Exception(f"Claude reply hatası: {resp.status_code}")

        raw = resp.json()["content"][0]["text"]
        json_str = raw
        if "```json" in raw:
            json_str = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            json_str = raw.split("```")[1].split("```")[0]

        return json.loads(json_str.strip())

    def _fallback_classify(self, text: str, email: str) -> dict:
        """AI ulaşılamadığında basit kural tabanlı sınıflandırma."""
        text_lower = text.lower()

        if any(w in text_lower for w in ["out of office", "afwezig",
                                          "vakantie", "not available"]):
            return {"classification": "out_of_office", "confidence": 0.8,
                    "sentiment": 50, "email": email}

        if any(w in text_lower for w in ["geen interesse", "not interested",
                                          "uitschrijven", "afmelden",
                                          "verwijder", "stop"]):
            return {"classification": "not_interested", "confidence": 0.7,
                    "sentiment": 20, "email": email}

        if any(w in text_lower for w in ["interesse", "demo", "prijs",
                                          "offerte", "bellen", "afspraak",
                                          "meer informatie"]):
            return {"classification": "interested", "confidence": 0.6,
                    "sentiment": 75, "email": email}

        if "?" in text:
            return {"classification": "question", "confidence": 0.5,
                    "sentiment": 50, "email": email}

        return {"classification": "not_interested", "confidence": 0.3,
                "sentiment": 40, "email": email}

    def get_response_stats(self) -> dict:
        """Yanıt istatistikleri."""
        return db.get_response_stats()

    def ping(self) -> bool:
        return True
