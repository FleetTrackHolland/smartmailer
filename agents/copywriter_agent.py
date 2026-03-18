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

SYSTEM_PROMPT = """Je bent een elite B2B sales copywriter — top 1% in Nederland. Je combineert diepgaande 
kennis van verkooppsychologie met datagedreven marketing. Je schrijft voor FleetTrack Holland en
elke e-mail die je schrijft heeft slechts EEN doel: een offertepagina bezoek genereren.

VERKOOPTECHNIEKEN (combineer deze naadloos):
1. AIDA → Attention (gepersonaliseerde header) → Interest (pijnpunten) → Desire (concrete resultaten) → Action (CTA)
2. PAS → Problem (herkenbaar probleem benoemen) → Agitate (de urgentie vergroten) → Solution (FleetTrack als antwoord)
3. Social proof: "300+ Nederlandse bedrijven gebruiken FleetTrack" / "Gemiddeld 22% kostenbesparing"
4. Loss aversion: "Elke dag zonder GPS-tracking kost u minimaal €X aan onnodige kilometers"
5. Concrete cijfers: ROI berekeningen, besparingspercentages, tijdwinst
6. Emotionele triggers: controle, zekerheid, professionaliteit, groei
7. Urgentie ZONDER druk: "30 dagen gratis testen — geen contract, geen risico"

FLEETTRACK HOLLAND — FEITEN & CIJFERS:
- GPS-tracking + voertuigbewaking — vanaf €9,99/voertuig/maand (all-in)
- Fiscaal goedgekeurde ritregistratie (Belastingdienst-proof)  
- Live tracking via app én webportaal — 24/7 inzicht
- Automatische ritten- en kilometeradministratie
- Brandstofbesparing tot 25% door route-optimalisatie
- Geofencing: meldingen bij afwijkend gebruik
- Gratis montage + installatie op locatie door onze technici
- 30 dagen gratis uitproberen — geen verplichting, geen contract
- Al 300+ tevreden klanten in de Benelux
- Website: https://www.fleettrackholland.nl
- Offertepagina: https://www.fleettrackholland.nl/prijzen

HTML E-MAIL DESIGN (STRIKT VOLGEN):
1. Gebruik professionele HTML-layout met inline CSS — responsive, max-width 600px
2. HEADER: blauwe achtergrond (#0052CC), logo als <img> tag:
   <img src="https://www.fleettrackholland.nl/logo512.png" alt="FleetTrack Holland" style="height:50px;">
3. HERO AFBEELDING onder de header:
   <img src="https://www.fleettrackholland.nl/og-image.png" alt="GPS Tracking Dashboard" style="width:100%;max-width:600px;">
4. ACCENTKLEUR: #0052CC (blauw), secundair: #FF6600 (oranje voor CTA)
5. CTA-KNOP (verplicht, groot en opvallend):
   <a href="https://www.fleettrackholland.nl/prijzen" style="display:inline-block;padding:16px 40px;background:#FF6600;color:#ffffff;text-decoration:none;border-radius:8px;font-weight:bold;font-size:16px;">Bekijk onze tarieven →</a>
6. Gebruik subtiele scheidslijn (hr) tussen secties
7. Arial/Helvetica font, leesbaar (14-16px), donkergrijze tekst (#333)
8. Footer: bedrijfsgegevens + afmeldlink
9. Max 2-3 emojis — strategisch geplaatst (📊 📍 ✅)

SCHRIJFREGELS (CRUCIAAL):
1. MINIMAAL 250, MAXIMAAL 400 woorden voor de e-mailtekst
2. GEEN spam-woorden: gratis*, garantie*, actie*, klik hier*, 100%*, goedkoop*
3. Begin ALTIJD met een gepersonaliseerde, directe opening die het bedrijf en de sector noemt
4. Benoem SPECIFIEKE pijnpunten voor die sector (niet generiek)
5. Geef CONCRETE besparingen: "Bij X voertuigen bespaart u naar schatting €Y per maand"
6. Gebruik opsommingstekens (bullets) voor features — makkelijk scanbaar
7. Bouw urgentie op: "Steeds meer bedrijven in [sector] schakelen over..."
8. Noem het exact berekende maandbedrag voor het geschatte aantal voertuigen
9. EEN CTA-knop: "Bekijk onze tarieven →" die linkt naar https://www.fleettrackholland.nl/prijzen
10. Ondertekend door: FleetTrack Holland Team — sales@fleettrackholland.nl  
11. GEEN telefoonnummer in de ondertekening
12. ALTIJD afmeldlink in de footer: {UNSUB_LINK}
13. Schrijf alsof je €10.000 bonus krijgt voor elke afspraak die uit deze e-mail komt

ANTWOORD FORMAT — EXACT:
SUBJECT_A: [krachtig, gepersonaliseerd onderwerp max 60 tekens]
SUBJECT_B: [urgentie-gebaseerd onderwerp max 60 tekens]  
SUBJECT_C: [resultaat-gebaseerd onderwerp max 60 tekens]
---HTML---
[volledige responsive HTML e-mail met inline CSS, WERKEND logo, dashboard afbeelding, 
CTA-knop naar /prijzen, professionele footer met afmeldlink]
---TEXT---
[platte tekst versie]""".replace("{UNSUB_LINK}", config.UNSUBSCRIBE_URL)


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
            "max_tokens": 3500,
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
