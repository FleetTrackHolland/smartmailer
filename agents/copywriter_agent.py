"""
agents/copywriter_agent.py — AI Email Yazarı (v2 — Pro Marketing Edition)
Claude API'yi requests ile doğrudan çağırır (SDK bağımlılığı yok).
FleetTrack Holland için profesyonel, görsel, sektöre özel Hollandaca cold email üretir.
20 yıllık marketing deneyimiyle tasarlanmış prompt mimarisi.
"""
import re
import requests
from dataclasses import dataclass
from config import config
from core.logger import get_logger

log = get_logger("copywriter")

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"


@dataclass
class EmailDraft:
    subject_a: str
    subject_b: str
    subject_c: str
    body_html: str
    body_text: str
    chosen_subject: str = ""

    def __post_init__(self):
        if not self.chosen_subject:
            self.chosen_subject = self.subject_a


# ─── SEKTÖR BAĞLAMI ─────────────────────────────────────────────

SECTOR_CONTEXT = {
    "transport": {
        "pain_points": "chauffeurs die niet opnemen, klanten die bellen voor ETA, "
                       "ritregistratie bijhouden, brandstofkosten bewaken",
        "hook_hint": "ETA-calls van klanten, twee vestigingen beheren, groeiende vloot",
        "urgency": "Met een groeiende vloot worden routes complexer",
        "visual_suggestion": "vrachtwagen op de snelweg met GPS-indicator, routekaart",
    },
    "bouw": {
        "pain_points": "diefstal van bouwvoertuigen buiten werktijd, "
                       "projectlocaties bewaken, materieel traceren",
        "hook_hint": "voertuigdiefstal, nachtelijk alarm, bouwplaats beveiliging",
        "urgency": "Diefstal van bouwvoertuigen stijgt elk jaar",
        "visual_suggestion": "bouwvoertuig met beveiligingsschild, nachtelijke bewaking",
    },
    "schoonmaak": {
        "pain_points": "privégebruik van bedrijfsbusjes, routes optimaliseren, "
                       "medewerkers bijhouden op meerdere locaties",
        "hook_hint": "privégebruik busjes, routes niet efficiënt, locatiecontrole",
        "urgency": "Ongeautoriseerd gebruik van bedrijfswagens kost maandelijks honderden euro's",
        "visual_suggestion": "bedrijfsbusje met route-optimalisatie overlay",
    },
    "thuiszorg": {
        "pain_points": "veiligheid van zorgmedewerkers, ritregistratie voor "
                       "zorgverzekeraars, routes efficiënt plannen",
        "hook_hint": "medewerkersveiligheid, declaratie ritregistratie",
        "urgency": "Zorgverzekeraars eisen steeds vaker een nauwkeurige ritregistratie",
        "visual_suggestion": "zorgmedewerker op pad met veiligheidsoverzicht",
    },
    "catering": {
        "pain_points": "bezorgers op tijd laten aankomen, klanten informeren "
                       "over bezorgtijd, routes optimaliseren",
        "hook_hint": "late bezorgingen, klachten over timing, routeplanning",
        "urgency": "Klanten verwachten live updates over hun bezorging",
        "visual_suggestion": "bezorgwagen met live tracking indicator op kaart",
    },
    "hoveniers": {
        "pain_points": "ploegen op verschillende projectlocaties bijhouden, "
                       "materieel en gereedschap traceren",
        "hook_hint": "ploegen kwijt, meerdere projecten tegelijk",
        "urgency": "Met meerdere projecten tegelijk is overzicht essentieel",
        "visual_suggestion": "groene werkbus met projectlocatie pins op kaart",
    },
    "koeriers": {
        "pain_points": "bezorgtijden halen, pakketten traceren, rijgedrag bewaken",
        "hook_hint": "vertraagde bezorging, klachten, ritregistratie voor fiscus",
        "urgency": "Elke vertraging kost u een klant",
        "visual_suggestion": "koerierswagen met pakkettracking dashboard",
    },
}

DEFAULT_CONTEXT = {
    "pain_points": "voertuigen bijhouden, ritregistratie, brandstof besparen",
    "hook_hint": "efficiëntie verbeteren, kosten verlagen",
    "urgency": "Steeds meer bedrijven kiezen GPS-tracking",
    "visual_suggestion": "bedrijfswagen met GPS tracking interface",
}

SYSTEM_PROMPT = """Je bent een senior B2B marketing strateeg met 20+ jaar ervaring in direct marketing, 
e-mail marketing en sales copywriting. Je werkt nu voor FleetTrack Holland.

Je combineert de volgende professionele sales-technieken in elke e-mail:

VERKOOPTECHNIEKEN:
1. AIDA-model (Attention → Interest → Desire → Action)
2. PAS-framework (Problem → Agitate → Solution)
3. Social proof (referenties, cijfers, resultaten)
4. Urgentie zonder druk (subtiel, professioneel)
5. Emotionele connectie via personalisatie
6. One clear CTA — geen keuzestress

FLEETTRACK HOLLAND PRODUCTINFO:
- GPS-tracking en voertuigbewaking — vanaf €9,99 per voertuig per maand (alles inclusief)
- Fiscaal goedgekeurde ritregistratie
- Live tracking via app én webportaal
- Gratis montage bij de klant op locatie
- 30 dagen gratis uitproberen — geen contract, geen risico
- Website: https://www.fleettrackholland.nl

DESIGN REGELS VOOR HTML E-MAIL:
1. Gebruik een professionele HTML-layout met inline CSS
2. Gebruik een strakke header met het FleetTrack Holland logo (https://www.fleettrackholland.nl/wp-content/uploads/2024/04/fleettrack-logo.png)
3. Gebruik een accentkleur: #0066CC (FleetTrack blauw)
4. Gebruik een CTA-knop met opvallende kleur (#FF6600 oranje) en afgeronde hoeken
5. Voeg een subtiele scheidslijn toe tussen secties
6. Gebruik professionele typografie — Arial of Helvetica
7. Maak de e-mail responsive (max-width: 600px)
8. Voeg een professionele footer toe met bedrijfsgegevens
9. Gebruik emojis strategisch (max 2-3) voor visuele aantrekkelijkheid
10. Voeg een afbeelding toe van de website als dat past:
    - Dashboard screenshot: https://www.fleettrackholland.nl/wp-content/uploads/2024/04/fleettrack-dashboard.png
    - Of het logo in de header

SCHRIJFREGELS:
1. Max 180 woorden voor de e-mailtekst (exclusief HTML-opmaak)
2. GEEN spam-woorden: gratis, garantie, actie, klik hier, 100%
3. Begin met een directe, persoonlijke opening
4. Noem het geschatte aantal voertuigen en de maandelijkse indicatie
5. Eindig met EEN duidelijke CTA (bellen of offerte aanvragen)
6. Ondertekend door: FleetTrack Holland Team — sales@fleettrackholland.nl
7. GEEN telefoonnummer in de ondertekening
8. ALTIJD afmeldlink in de footer

ANTWOORD FORMAT — EXACT dit formaat:
SUBJECT_A: [onderwerp variant A]
SUBJECT_B: [onderwerp variant B]  
SUBJECT_C: [onderwerp variant C]
---HTML---
[volledige HTML e-mail met inline CSS, professionele opmaak, logo, CTA-knop, footer]
---TEXT---
[platte tekst versie van de e-mail]"""


class CopywriterAgent:

    def __init__(self):
        self._headers = {
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        log.debug("Copywriter ajani hazır (v2 — Pro Marketing Edition).")

    def write(self, lead: dict) -> EmailDraft:
        company  = lead.get("Company", lead.get("company", "uw bedrijf"))
        sector   = (lead.get("Sector") or lead.get("sector") or "transport").lower()
        location = lead.get("Location", lead.get("location", "Nederland"))
        vehicles = lead.get("Vehicles", lead.get("vehicles", 0))

        ctx = SECTOR_CONTEXT.get(sector, DEFAULT_CONTEXT)

        try:
            v_count = int(vehicles)
        except (ValueError, TypeError):
            v_count = 0

        if v_count > 0:
            price_hint = (f"Bij {v_count} voertuigen: "
                          f"€{v_count * 9.99:.2f}/maand — alles inclusief.")
        else:
            price_hint = "Vanaf €9,99 per voertuig per maand — alles inclusief."

        user_prompt = f"""Schrijf een professionele, visueel aantrekkelijke koude e-mail voor:

Bedrijf: {company}
Sector: {sector}
Locatie: {location}
Voertuigen: {v_count if v_count > 0 else 'onbekend'}

Pijnpunten: {ctx['pain_points']}
Hooks: {ctx['hook_hint']}
Urgentie: {ctx['urgency']}
Prijs: {price_hint}
Visuele suggestie: {ctx.get('visual_suggestion', '')}

Contactgegevens (voor ondertekening):
FleetTrack Holland Team
sales@fleettrackholland.nl
https://www.fleettrackholland.nl

Afmeldlink (verplicht in footer):
Wilt u geen e-mails meer? Klik hier: {config.UNSUBSCRIBE_URL}

BELANGRIJK:
- Gebruik GEEN telefoonnummer
- E-mailadres is: sales@fleettrackholland.nl
- Prijs: vanaf €9,99 per voertuig per maand
- Maak een professionele HTML-email met logo, CTA-knop en mooie opmaak
- Denk als een 20-jarige marketing professional: elk woord telt"""

        log.info(f"[Copywriter v2] Üretiliyor → {company} ({sector}, {location})")

        payload = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": 2000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        resp = requests.post(CLAUDE_API_URL, json=payload,
                             headers=self._headers, timeout=60)
        if not resp.ok:
            raise Exception(
                f"Claude API hatası {resp.status_code}: {resp.text[:300]}"
            )
        raw = resp.json()["content"][0]["text"]
        return self._parse(raw, company)

    def rewrite(self, draft: EmailDraft, feedback: list[str]) -> EmailDraft:
        """QC feedback'e göre taslağı yeniden yazar."""
        feedback_text = "\n".join(f"- {f}" for f in feedback)

        prompt = f"""De volgende e-mail heeft de kwaliteitscontrole NIET gehaald.
Herschrijf de e-mail zodat alle problemen zijn opgelost.

PROBLEMEN:
{feedback_text}

HUIDIGE ONDERWERP: {draft.chosen_subject}

HUIDIGE TEKST:
{draft.body_text}

Geef het antwoord in EXACT hetzelfde formaat:
SUBJECT_A: [onderwerp]
SUBJECT_B: [onderwerp]
SUBJECT_C: [onderwerp]
---HTML---
[verbeterde HTML e-mail]
---TEXT---
[verbeterde platte tekst]"""

        log.info(f"[Copywriter v2] Yeniden yazılıyor — QC sorunları: {feedback}")

        payload = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": 2000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }

        resp = requests.post(CLAUDE_API_URL, json=payload,
                             headers=self._headers, timeout=60)
        if not resp.ok:
            raise Exception(f"Claude API rewrite hatası: {resp.status_code}")

        raw = resp.json()["content"][0]["text"]
        company = draft.chosen_subject.split("—")[0].strip() if "—" in draft.chosen_subject else ""
        return self._parse(raw, company)

    def _parse(self, raw: str, company: str) -> EmailDraft:
        lines = raw.strip().splitlines()
        subject_a = subject_b = subject_c = ""
        html_lines = []
        text_lines = []
        mode = "header"  # header → html → text

        for line in lines:
            if line.startswith("SUBJECT_A:"):
                subject_a = line.replace("SUBJECT_A:", "").strip()
            elif line.startswith("SUBJECT_B:"):
                subject_b = line.replace("SUBJECT_B:", "").strip()
            elif line.startswith("SUBJECT_C:"):
                subject_c = line.replace("SUBJECT_C:", "").strip()
            elif line.strip() == "---HTML---":
                mode = "html"
            elif line.strip() == "---TEXT---":
                mode = "text"
            elif line.strip() == "---":
                if mode == "header":
                    mode = "html"  # Backward compat
            elif mode == "html":
                html_lines.append(line)
            elif mode == "text":
                text_lines.append(line)

        body_html = "\n".join(html_lines).strip()
        body_text = "\n".join(text_lines).strip()

        # Fallback: if no HTML section, use plain text and convert
        if not body_html and body_text:
            body_html = self._to_html(body_text)
        elif not body_html and not body_text:
            # Old format fallback
            body_text = raw.strip()
            body_html = self._to_html(body_text)

        if not body_text and body_html:
            # Strip HTML tags for plain text version
            import re
            body_text = re.sub(r'<[^>]+>', '', body_html)
            body_text = re.sub(r'\s+', ' ', body_text).strip()

        subject_a = subject_a or f"GPS tracking voor {company}"
        subject_b = subject_b or f"{company} — altijd weten waar uw voertuigen zijn"
        subject_c = subject_c or f"Ritregistratie voor {company}"

        return EmailDraft(
            subject_a=subject_a,
            subject_b=subject_b,
            subject_c=subject_c,
            body_text=body_text,
            body_html=body_html,
        )

    def _to_html(self, text: str) -> str:
        """Fallback: plain text → basic styled HTML."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        html_p = "".join(
            f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs
        )
        return f"""<!DOCTYPE html>
<html lang="nl"><head><meta charset="UTF-8">
<style>
body {{
    font-family: Arial, Helvetica, sans-serif;
    font-size: 14px;
    color: #333;
    line-height: 1.7;
    max-width: 600px;
    margin: 0 auto;
    background: #f8f9fa;
}}
.container {{
    background: #ffffff;
    border-radius: 8px;
    padding: 32px;
    margin: 20px auto;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}}
p {{ margin: 0 0 16px; }}
.cta-btn {{
    display: inline-block;
    background: #FF6600;
    color: #fff !important;
    padding: 12px 28px;
    border-radius: 6px;
    text-decoration: none;
    font-weight: bold;
    margin: 16px 0;
}}
.footer {{
    font-size: 12px;
    color: #999;
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid #eee;
}}
</style>
</head><body>
<div class="container">
    <img src="https://www.fleettrackholland.nl/wp-content/uploads/2024/04/fleettrack-logo.png" alt="FleetTrack Holland" style="max-width:180px;margin-bottom:16px">
    {html_p}
    <div class="footer">
        FleetTrack Holland | sales@fleettrackholland.nl<br>
        <a href="{config.UNSUBSCRIBE_URL}">Afmelden</a>
    </div>
</div>
</body></html>"""

    def ping(self) -> bool:
        return True
