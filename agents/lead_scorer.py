"""
agents/lead_scorer.py — AI Lead Scoring & Prioritization
Claude ile lead'leri değerlendirir, filo büyüklüğü, sektör uyumu,
konum ve potansiyel değere göre 0-100 arası puanlar.
Batch scoring ile API maliyetini minimize eder.
"""
import json
import requests
from config import config
from core.logger import get_logger
from core.api_guard import api_guard

log = get_logger("lead_scorer")

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"

SCORING_PROMPT = """Je bent Pieter de Vries — 30 jaar ervaring als B2B sales director in fleet management.
Je hebt voor de grootste fleetbedrijven van Europa gewerkt en je RUIKT een goede lead op kilometers afstand.
Je hebt duizenden deals gesloten en je weet PRECIES welke signalen een hoge conversiekans voorspellen.

Beoordeel elke lead met de scherpe blik van een veteraan. Geef een score van 0-100.

SCORINGSCRITERIA (jouw 30 jaar ervaring gedistilleerd):

1. VLOOTPOTENTIEEL (40%): Grotere vloot = meer omzet, maar ook: groei-potentieel telt
   - 1-5 voertuigen: 20-40 punten (klein maar kan groeien)
   - 6-20 voertuigen: 40-60 punten (sweet spot voor instap)
   - 21-50 voertuigen: 60-80 punten (serieuze klant, langetermijnwaarde)
   - 50+: 80-100 punten (enterprise deal, account management nodig)
   - Onbekend: 35 punten (kan verrassend groot zijn)

2. SECTORFIT (30%): Jouw ervaring zegt welke sectoren het MEEST profiteren
   - Transport, logistiek, koeriers: 90-100 (perfecte fit — dit IS hun core business)
   - Bouw, installatie: 80-90 (diefstalpreventie + ritregistratie = onmisbaar)
   - Thuiszorg, schoonmaak: 70-80 (route-optimalisatie = directe ROI)
   - Catering, bezorging: 75-85 (timing is ALLES in hun business)
   - Hoveniers, groenvoorziening: 65-75 (meerdere locaties = tracking nodig)
   - Overig: 40-60 (case-by-case beoordeling)

3. LOCATIEWAARDE (15%): Jouw marktkennis zegt waar de beste deals zitten
   - Randstad (Amsterdam, Rotterdam, Den Haag, Utrecht): 90-100
   - Grote steden (Eindhoven, Groningen, Nijmegen): 70-85
   - Middelgrote steden: 50-65
   - Onbekend: 40

4. DIGITALE VOLWASSENHEID (15%): Website = professioneel bedrijf = snellere conversie
   - Professionele website: +15
   - Geen website: +5

ANTWOORD IN DIT EXACTE JSON FORMAT:
{
    "scores": [
        {
            "email": "email@bedrijf.nl",
            "score": 75,
            "reason": "Korte uitleg met jouw 30 jaar ervaring als context",
            "priority": "high"
        }
    ]
}

priority waarden: "critical" (90+), "high" (70-89), "medium" (50-69), "low" (<50)"""


class LeadScorer:

    def __init__(self):
        self._headers = {
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        log.info("LeadScorer ajani hazır.")

    def score_batch(self, leads: list[dict]) -> list[dict]:
        """
        Birden fazla lead'i tek API çağrısında puanlar.
        Maliyet optimizasyonu: max 20 lead per batch.
        Returns: [{"email": ..., "score": ..., "reason": ...}, ...]
        """
        if not leads:
            return []

        # Batch size limiti
        batch_size = 20
        all_scores = []

        for i in range(0, len(leads), batch_size):
            batch = leads[i:i + batch_size]
            scores = self._score_single_batch(batch)
            all_scores.extend(scores)

        return all_scores

    def _score_single_batch(self, leads: list[dict]) -> list[dict]:
        """Tek batch'i Claude'a gönder ve puanla."""

        leads_text = ""
        for idx, lead in enumerate(leads, 1):
            email = lead.get("Email") or lead.get("email") or "?"
            company = lead.get("Company") or lead.get("company") or "Onbekend"
            sector = lead.get("Sector") or lead.get("sector") or "onbekend"
            location = lead.get("Location") or lead.get("location") or "onbekend"
            vehicles = lead.get("Vehicles") or lead.get("vehicles") or "onbekend"
            website = lead.get("Website") or lead.get("website") or ""

            leads_text += f"""
Lead #{idx}:
- Email: {email}
- Bedrijf: {company}
- Sector: {sector}
- Locatie: {location}
- Voertuigen: {vehicles}
- Website: {website}
"""

        user_prompt = f"Beoordeel de volgende {len(leads)} leads:\n{leads_text}"

        log.info(f"[LeadScorer] {len(leads)} lead puanlanıyor...")

        payload = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": 1500,
            "system": SCORING_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        try:
            resp = api_guard.call(payload, self._headers, timeout=45)
            if not resp or not resp.ok:
                log.error(f"[LeadScorer] API hatası: {resp.status_code if resp else 'guard blocked'}")
                return self._fallback_scores(leads)

            raw = resp.json()["content"][0]["text"]

            # JSON parse
            json_str = raw
            if "```json" in raw:
                json_str = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                json_str = raw.split("```")[1].split("```")[0]

            data = json.loads(json_str.strip())
            scores = data.get("scores", [])

            for s in scores:
                priority = s.get("priority", "medium")
                log.info(f"[LeadScorer] {s['email']}: {s['score']}/100 "
                         f"({priority}) — {s.get('reason', '')[:60]}")

            return scores

        except Exception as e:
            log.warning(f"[LeadScorer] AI scoring başarısız ({e}), fallback kullanılıyor")
            return self._fallback_scores(leads)

    def _fallback_scores(self, leads: list[dict]) -> list[dict]:
        """AI ulaşılamadığında basit kural tabanlı scoring."""
        scores = []
        for lead in leads:
            email = lead.get("Email") or lead.get("email") or ""
            vehicles = lead.get("Vehicles") or lead.get("vehicles") or 0
            sector = (lead.get("Sector") or lead.get("sector") or "").lower()

            try:
                v = int(vehicles)
            except (ValueError, TypeError):
                v = 0

            score = 30  # base

            # Filo büyüklüğü
            if v > 50:
                score += 40
            elif v > 20:
                score += 30
            elif v > 5:
                score += 20
            elif v > 0:
                score += 10

            # Sektör uyumu
            high_fit = {"transport", "logistiek", "koeriers"}
            mid_fit = {"bouw", "installatie", "thuiszorg", "schoonmaak"}
            if sector in high_fit:
                score += 25
            elif sector in mid_fit:
                score += 15
            else:
                score += 10

            priority = "critical" if score >= 90 else \
                       "high" if score >= 70 else \
                       "medium" if score >= 50 else "low"

            scores.append({
                "email": email,
                "score": min(score, 100),
                "reason": "Fallback rule-based scoring",
                "priority": priority,
            })

        return scores

    def score_single(self, lead: dict) -> dict:
        """Tek lead'i puanla."""
        results = self.score_batch([lead])
        return results[0] if results else {"score": 50, "reason": "Default"}

    def ping(self) -> bool:
        return True
