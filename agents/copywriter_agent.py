"""
agents/copywriter_agent.py — Elite B2B Sales Copywriter (v3 — Master Edition)
30 yıllık B2B satış deneyimi. Cialdini'nin 6 ikna prensibi, Kahneman'ın
Prospect Theory'si, altın oran HTML tasarım, ve self-learning mekanizmasıyla
mükemmel satış e-postaları üretir.
"""
import re
import json
import requests
from dataclasses import dataclass
from config import config
from core.logger import get_logger
from core.api_guard import api_guard

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


# ─── SEKTÖR BAĞLAMI — DERİN PAZAR BİLGİSİ ──────────────────────

SECTOR_CONTEXT = {
    "transport": {
        "pain_points": "chauffeurs die niet opnemen, klanten die bellen voor ETA, "
                       "ritregistratie bijhouden, brandstofkosten bewaken, "
                       "naleving rij- en rusttijden, privégebruik bedrijfswagens",
        "hook_hint": "ETA-calls van klanten, twee vestigingen beheren, groeiende vloot",
        "urgency": "Met een groeiende vloot worden routes complexer — elk uur telt",
        "visual_suggestion": "vrachtwagen op de snelweg met GPS-indicator, routekaart",
        "roi_example": "Een transportbedrijf met 15 vrachtwagens bespaarde €2.340/maand op brandstof",
        "psychological_angle": "authority + social_proof",
        "accent_color": "#1a73e8",
    },
    "bouw": {
        "pain_points": "diefstal van bouwvoertuigen buiten werktijd, "
                       "projectlocaties bewaken, materieel traceren, "
                       "uren op locatie vastleggen, ongeautoriseerd gebruik",
        "hook_hint": "voertuigdiefstal, nachtelijk alarm, bouwplaats beveiliging",
        "urgency": "Diefstal van bouwmaterieel steeg 23% in het afgelopen jaar",
        "visual_suggestion": "bouwvoertuig met beveiligingsschild, nachtelijke bewaking",
        "roi_example": "Een bouwbedrijf voorkwam €45.000 aan diefstal in 6 maanden",
        "psychological_angle": "loss_aversion + scarcity",
        "accent_color": "#e8a31a",
    },
    "schoonmaak": {
        "pain_points": "privégebruik van bedrijfsbusjes, routes optimaliseren, "
                       "medewerkers bijhouden op meerdere locaties, "
                       "klachten over te late aankomst",
        "hook_hint": "privégebruik busjes, routes niet efficiënt, locatiecontrole",
        "urgency": "Ongeautoriseerd gebruik kost gemiddeld €380/maand per voertuig",
        "visual_suggestion": "bedrijfsbusje met route-optimalisatie overlay",
        "roi_example": "Een schoonmaakbedrijf bespaarde 4.2 uur per dag door route-optimalisatie",
        "psychological_angle": "reciprocity + commitment",
        "accent_color": "#34a853",
    },
    "thuiszorg": {
        "pain_points": "veiligheid van zorgmedewerkers, ritregistratie voor "
                       "zorgverzekeraars, routes efficiënt plannen, "
                       "aanrijtijden verkorten bij spoed",
        "hook_hint": "medewerkersveiligheid, declaratie ritregistratie",
        "urgency": "Zorgverzekeraars eisen nauwkeurige ritregistratie — boetes bij afwijking",
        "visual_suggestion": "zorgmedewerker op pad met veiligheidsoverzicht",
        "roi_example": "Een thuiszorgorganisatie bespaarde €1.800/maand op ritdeclaraties",
        "psychological_angle": "authority + liking",
        "accent_color": "#4285f4",
    },
    "catering": {
        "pain_points": "bezorgers op tijd laten aankomen, klanten informeren "
                       "over bezorgtijd, routes optimaliseren, koude keten bewaken",
        "hook_hint": "late bezorgingen, klachten over timing, routeplanning",
        "urgency": "87% van klanten bestelt niet meer na twee late bezorgingen",
        "visual_suggestion": "bezorgwagen met live tracking indicator op kaart",
        "roi_example": "Een cateringbedrijf verhoogde klanttevredenheid met 34% door live tracking",
        "psychological_angle": "social_proof + scarcity",
        "accent_color": "#ea4335",
    },
    "logistiek": {
        "pain_points": "laad- en lostijden optimaliseren, chauffeurs aansturen, "
                       "klanten real-time informeren, brandstofkosten beheersen",
        "hook_hint": "wachttijden bij klanten, brandstofverspilling, ETA-beloftes",
        "urgency": "Elke minuut onnodig stilstaan kost €0,80 aan operationele kosten",
        "visual_suggestion": "logistiek dashboard met vlootoverzicht",
        "roi_example": "Een logistiek bedrijf verminderde wachttijden met 40%",
        "psychological_angle": "authority + commitment",
        "accent_color": "#1a73e8",
    },
    "koerier": {
        "pain_points": "bezorgtijden halen, pakketten traceren, rijgedrag bewaken, "
                       "klachten over gemiste afleveringen",
        "hook_hint": "vertraagde bezorging, klachten, ritregistratie voor fiscus",
        "urgency": "Elke mislukte bezorgpoging kost gemiddeld €4,50 aan extra kosten",
        "visual_suggestion": "koerierswagen met pakkettracking dashboard",
        "roi_example": "Een koeriersdienst verminderde mislukte bezorgingen met 62%",
        "psychological_angle": "loss_aversion + reciprocity",
        "accent_color": "#ff6d01",
    },
}

DEFAULT_CONTEXT = {
    "pain_points": "voertuigen bijhouden, ritregistratie, brandstof besparen, "
                   "privégebruik voorkomen, onderhoud plannen",
    "hook_hint": "efficiëntie verbeteren, kosten verlagen, overzicht behouden",
    "urgency": "Bedrijven die GPS-tracking gebruiken besparen gemiddeld 15-25% op vlootkosten",
    "visual_suggestion": "bedrijfswagen met GPS tracking interface",
    "roi_example": "Bedrijven besparen gemiddeld €200 per voertuig per maand",
    "psychological_angle": "social_proof + authority",
    "accent_color": "#e8600a",
}


# ═══════════════════════════════════════════════════════════════════
# MASTER SYSTEM PROMPT — 30 JAAR B2B SALES EXPERTISE
# ═══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Je bent Hans van der Berg — de meest succesvolle B2B cold email specialist van de Benelux.
Met 30 jaar ervaring in fleet management sales heb je voor merken als TomTom, Verizon Connect en Webfleet gewerkt.
Je bent opgeleid door Robert Cialdini persoonlijk en past zijn 6 principes dagelijks toe.
Je combineert de precisie van een Zwitsers horloge met de creativiteit van een Amsterdamse creative director.

═══ JOUW 6 PSYCHOLOGISCHE WAPENS (gebruik er MINIMAAL 2 per e-mail) ═══

1. RECIPROCITY: Geef eerst WAARDE — een gratis inzicht, een branche-statistiek, een tip
2. SOCIAL PROOF: "Vergelijkbare bedrijven in uw sector ervaren..."
3. AUTHORITY: Noem concrete cijfers, percentages, brancherapporten
4. SCARCITY: Beperkt aanbod of tijdelijke actie (subtiel, niet schreeuwerig)
5. LIKING: Persoonlijk, warm, alsof je de ondernemer al kent
6. COMMITMENT: Vraag om een KLEINE stap — niet "bel mij" maar "mag ik u één vraag stellen?"

═══ PROSPECT THEORY (Kahneman) ═══
Mensen voelen VERLIES 2x sterker dan winst. Frame altijd als:
❌ NIET: "U kunt €200/maand besparen"
✅ WEL: "Elke maand zonder tracking verliest u circa €200 aan onnodige kosten"

═══ FLEETTRACK HOLLAND — KERNINFO ═══
- GPS-tracking + voertuigbewaking — vanaf €9,99 per voertuig per maand (all-in)
- Fiscaal goedgekeurde ritregistratie (Belastingdienst-proof)
- Live tracking via app en webportaal — 24/7
- Automatische ritten- en kilometeradministratie
- Brandstofbesparing tot 25% door route-optimalisatie
- Montage op locatie door eigen technici — geen gedoe
- 30 dagen uitproberen — geen contract, opzeggen wanneer u wilt
- 300+ klanten in de Benelux vertrouwen op FleetTrack
- Offertepagina: https://www.fleettrackholland.nl/prijzen

═══ HTML E-MAIL DESIGN — BODY CONTENT ONLY ═══

BELANGRIJK: Je schrijft ALLEEN de body-content van de e-mail.
De template-engine voegt automatisch toe: header met logo, hero afbeelding,
CTA-knop, statistieken-balk, en footer met afmeldlink.

JIJ levert ALLEEN de tekst tussen de header en de CTA-knop.

STRUCTUUR VAN JOUW OUTPUT (alleen body HTML):
Gebruik INLINE CSS op elk element. Geen <html>, <head>, <body> tags nodig.

1. AANHEF:
   <p style="margin:0 0 16px;font-size:15px;color:#333;line-height:1.7;">
   Dag [bedrijfsnaam],</p>

2. PIJNPUNT PARAGRAAF (1-2 zinnen, italic):
   <p style="margin:0 0 16px;font-size:15px;color:#555;font-style:italic;line-height:1.7;">
   [Herkenbaar pijnpunt benoemen]</p>

3. OPLOSSING + BEWIJS (2-3 alinea's):
   <p style="margin:0 0 16px;font-size:15px;color:#333;line-height:1.7;">
   [Tekst met inline <strong> voor nadruk]</p>

4. BELANGRIJKE CIJFERS (groot en opvallend):
   <p style="margin:0 0 16px;font-size:15px;color:#333;line-height:1.7;">
   Resultaat: <span style="font-size:24px;font-weight:700;color:ACCENT_COLOR;">€X.XXX</span> /maand besparing</p>

5. OPSOMMINGEN (met accent-kleur bullets):
   <p style="margin:0 0 8px;font-size:14px;color:#333;line-height:1.6;">
   <span style="color:ACCENT_COLOR;font-weight:bold;">▸</span> Punt een</p>
   <p style="margin:0 0 8px;font-size:14px;color:#333;line-height:1.6;">
   <span style="color:ACCENT_COLOR;font-weight:bold;">▸</span> Punt twee</p>

6. AFSLUITING + HANDTEKENING:
   <p style="margin:24px 0 0;font-size:15px;color:#333;line-height:1.7;">
   Met vriendelijke groet,<br>
   <strong>FleetTrack Holland Team</strong><br>
   <span style="font-size:13px;color:#888;">sales@fleettrackholland.nl</span></p>

═══ SCHRIJFREGELS — NIET ONDERHANDELBAAR ═══
1. 150-300 woorden (exclusief HTML tags)
2. Begin met "Dag [bedrijfsnaam]," — direct en persoonlijk
3. GEEN emojis, GEEN icoontjes — nergens
4. GEEN "gratis", "garantie", "actie", "klik hier", "100%", "!!!"
5. Eerste zin na aanhef moet ONMIDDELLIJK relevant zijn — geen inleiding
6. Benoem de berekende maandprijs als voertuigaantal bekend is
7. Gebruik "▸" als bullet — geen andere bullets
8. GEEN CTA-knop genereren — de template doet dit automatisch
9. Ondertekening: "Met vriendelijke groet," + "FleetTrack Holland Team" + sales@fleettrackholland.nl
10. GEEN telefoonnummer
11. GEEN footer of afmeldlink — de template doet dit
12. Alles in het Nederlands
13. Gebruik INLINE CSS op elk HTML element
14. GEEN <html>, <head>, <body>, <!DOCTYPE> tags — alleen body-inhoud

ACCENT_COLOR PER SECTOR:
- transport/logistiek/koerier: #1a5fa0
- bouw: #e8a31a
- schoonmaak/thuiszorg/catering: #22a85a
- default: #e8600a

ANTWOORD FORMAT — EXACT DIT:
SUBJECT_A: [zakelijk, kort, max 55 tekens, curiosity gap]
SUBJECT_B: [pijnpunt-gebaseerd, loss aversion frame, max 55 tekens]
SUBJECT_C: [social proof of resultaat, max 55 tekens]
---HTML---
[ALLEEN body-content HTML met inline CSS — GEEN volledige pagina]
---TEXT---
[platte tekst versie — ZONDER emojis]"""


class CopywriterAgent:

    def __init__(self):
        self._headers = {
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        self._winning_style_cache = None
        self._cache_time = 0
        log.info("Copywriter ajani hazır (v3 — Master Edition, 30yr expertise).")

    # ─── SELF-LEARNING: KAZANAN STİLDEN ÖĞREN ──────────────────

    def _get_winning_style(self) -> str:
        """DB'den yanıt gelen maillerin stilini analiz eder — self-learning."""
        import time
        # Cache 30 dakika
        if self._winning_style_cache and (time.time() - self._cache_time) < 1800:
            return self._winning_style_cache

        try:
            from core.database import db
            # Cevap gelen mailleri çek (interested + question)
            interested = []
            try:
                with db._conn() as conn:
                    rows = conn.execute("""
                        SELECT s.subject, s.ab_variant, r.classification,
                               d.body_text, l.sector
                        FROM responses r
                        JOIN sent_log s ON r.email = s.email
                        LEFT JOIN drafts d ON r.email = d.email
                        LEFT JOIN leads l ON r.email = l.email
                        WHERE r.classification IN ('interested', 'question')
                        ORDER BY r.classified_at DESC LIMIT 10
                    """).fetchall()
                    interested = [dict(r) for r in rows]
            except Exception:
                pass

            if not interested:
                self._winning_style_cache = ""
                self._cache_time = time.time()
                return ""

            # Kazanan tarzı özetle
            subjects = [r.get("subject", "") for r in interested if r.get("subject")]
            variants = [r.get("ab_variant", "") for r in interested if r.get("ab_variant")]
            sectors = [r.get("sector", "") for r in interested if r.get("sector")]

            style_info = f"""
═══ SELF-LEARNING DATA (succesvolle e-mails die reactie opleveren) ═══
Aantal succesvolle e-mails: {len(interested)}
Winnende onderwerplijnen: {'; '.join(subjects[:5])}
Winnende A/B varianten: {', '.join(variants)}
Sectoren met respons: {', '.join(set(sectors))}
INSTRUCTIE: Leer van deze succesvolle patronen. Gebruik vergelijkbare toon,
lengte en onderwerpstijl. Pas je aan op basis van wat WERKT.
═══════════════════════════════════════════════════════════════════════"""

            self._winning_style_cache = style_info
            self._cache_time = time.time()
            log.info(f"[Copywriter] Self-learning: {len(interested)} succesvolle e-mails geanalyseerd")
            return style_info

        except Exception as e:
            log.warning(f"[Copywriter] Self-learning data fout: {e}")
            return ""

    # ─── ANA YAZIM METODU ───────────────────────────────────────

    def write(self, lead: dict, intel_context: str = "") -> EmailDraft:
        company  = lead.get("Company", lead.get("company", "uw bedrijf"))
        sector   = (lead.get("Sector") or lead.get("sector") or "transport").lower()
        location = lead.get("Location", lead.get("location", "Nederland"))
        vehicles = lead.get("Vehicles", lead.get("vehicles", 0))

        ctx = SECTOR_CONTEXT.get(sector, DEFAULT_CONTEXT)
        accent_color = ctx.get("accent_color", "#e8600a")

        try:
            v_count = int(vehicles)
        except (ValueError, TypeError):
            v_count = 0

        if v_count > 0:
            monthly = v_count * 9.99
            price_hint = (f"Bij {v_count} voertuigen: €{monthly:.2f}/maand — all-in. "
                          f"Dat is slechts €{9.99:.2f} per voertuig.")
        else:
            price_hint = "Vanaf €9,99 per voertuig per maand — alles inclusief."

        # Self-learning data
        winning_style = self._get_winning_style()

        # Churn analyst insights — unsubscribe paternlerinden öğrenilenler
        churn_context = ""
        try:
            from agents.churn_analyst import ChurnAnalyst
            churn = ChurnAnalyst()
            churn_context = churn.get_copywriter_context(sector=sector)
        except Exception as e:
            log.debug(f"[Copywriter] Churn context alınamadı: {e}")

        # Intel context
        intel_section = ""
        if intel_context:
            intel_section = f"""

═══ DEEP INTELLIGENCE (ReconAgent rapport — GEBRUIK DIT!) ═══
{intel_context}
═══════════════════════════════════════════════════════════════

⚠️ CRUCIAAL: Gebruik deze intelligence voor EXTREME personalisatie.
"""

        user_prompt = f"""Schrijf een PREMIUM koude e-mail voor:

═══ LEAD DATA ═══
Bedrijf: {company}
Sector: {sector}
Locatie: {location}
Voertuigen: {v_count if v_count > 0 else 'onbekend'}
Accent kleur voor dit bedrijf: {accent_color}

═══ SECTORKENNIS ═══
Pijnpunten: {ctx['pain_points']}
Hooks: {ctx['hook_hint']}
Urgentie: {ctx['urgency']}
ROI voorbeeld: {ctx.get('roi_example', 'Gemiddeld 15-25% besparing')}
Aanbevolen psychologie: {ctx.get('psychological_angle', 'social_proof + authority')}
Prijs: {price_hint}
{intel_section}
{winning_style}
{churn_context}

═══ TECHNISCHE EISEN ═══
- Accent kleur in CTA-knop en highlights: {accent_color}
- FleetTrack Holland logo: <img src="https://www.fleettrackholland.nl/logo512.png" alt="FleetTrack Holland" style="height:32px;">
- CTA link: https://www.fleettrackholland.nl/prijzen
- Afmeldlink (verplicht): {config.UNSUBSCRIBE_URL}
- Ondertekening: FleetTrack Holland Team / sales@fleettrackholland.nl
- GEEN telefoonnummer

═══ PSYCHOLOGISCHE STRATEGIE ═══
Gebruik MINIMAAL 2 van Cialdini's principes:
1. Reciprocity — geef een gratis inzicht of tip
2. Social Proof — noem vergelijkbare bedrijven
3. Authority — gebruik concrete cijfers
4. Scarcity — beperkt aanbod (subtiel!)
5. Liking — persoonlijk en warm
6. Commitment — vraag een kleine stap

Frame verliezen sterker dan winst (Prospect Theory).
Maak belangrijke cijfers GROOT en OPVALLEND in de HTML."""

        log.info(f"[Copywriter v3] Elite e-mail → {company} ({sector}, {location})")

        payload = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": 4000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        resp = api_guard.call(payload, self._headers, timeout=60)
        if not resp or not resp.ok:
            status = resp.status_code if resp else 'guard blocked'
            raise Exception(f"Claude API hatası {status}")
        raw = resp.json()["content"][0]["text"]
        return self._parse(raw, company)

    def rewrite(self, draft: EmailDraft, feedback: list[str]) -> EmailDraft:
        """QC feedback'e göre taslağı yeniden yazar."""
        feedback_text = "\n".join(f"- {f}" for f in feedback)

        prompt = f"""De volgende e-mail heeft de kwaliteitscontrole NIET gehaald.
Herschrijf de e-mail als een 30-jarige marketing veteraan.
Los ALLE problemen op en maak de e-mail BETER dan het origineel.

PROBLEMEN:
{feedback_text}

HUIDIGE ONDERWERP: {draft.chosen_subject}

HUIDIGE TEKST:
{draft.body_text}

Geef het antwoord in EXACT hetzelfde formaat:
SUBJECT_A: [onderwerp — curiosity gap]
SUBJECT_B: [onderwerp — loss aversion]
SUBJECT_C: [onderwerp — social proof]
---HTML---
[verbeterde premium HTML e-mail met golden ratio layout]
---TEXT---
[verbeterde platte tekst]"""

        log.info(f"[Copywriter v3] Rewrite — QC sorunları: {feedback}")

        payload = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": 4000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }

        resp = api_guard.call(payload, self._headers, timeout=60)
        if not resp or not resp.ok:
            raise Exception(f"Claude API rewrite hatası: {resp.status_code if resp else 'guard blocked'}")

        raw = resp.json()["content"][0]["text"]
        company = draft.chosen_subject.split("—")[0].strip() if "—" in draft.chosen_subject else ""
        return self._parse(raw, company)

    def _parse(self, raw: str, company: str) -> EmailDraft:
        lines = raw.strip().splitlines()
        subject_a = subject_b = subject_c = ""
        html_lines = []
        text_lines = []
        mode = "header"

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
                    mode = "html"
            elif mode == "html":
                html_lines.append(line)
            elif mode == "text":
                text_lines.append(line)

        body_html = "\n".join(html_lines).strip()
        body_text = "\n".join(text_lines).strip()

        # Strip non-HTML content before actual HTML
        if body_html:
            html_start = re.search(r'<(!DOCTYPE|html|head|body|div|table)', body_html, re.IGNORECASE)
            if html_start:
                body_html = body_html[html_start.start():]

        # Fallback
        if not body_html and body_text:
            body_html = self._to_html(body_text)
        elif not body_html and not body_text:
            body_text = raw.strip()
            body_html = self._to_html(body_text)

        if not body_text and body_html:
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
        """Fallback: plain text → styled body-only HTML (template wraps it)."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        html_parts = []
        for p in paragraphs:
            lines = p.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if line.startswith(("▸", "-", "•")):
                    clean = line.lstrip("▸-• ").strip()
                    html_parts.append(
                        f'<p style="margin:0 0 8px;font-size:14px;color:#333;line-height:1.6;">'
                        f'<span style="color:#e8600a;font-weight:bold;">▸</span> {clean}</p>'
                    )
                else:
                    html_parts.append(
                        f'<p style="margin:0 0 16px;font-size:15px;color:#333;line-height:1.7;">{line}</p>'
                    )
        return "\n".join(html_parts)

    def ping(self) -> bool:
        return True

