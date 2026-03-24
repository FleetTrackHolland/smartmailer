"""
agents/recon_agent.py — Deep Intelligence & Reconnaissance Agent (v1)
Mail göndermeden ÖNCE hedef şirket/kişi hakkında derinlemesine araştırma yapar.

OSINT (Open Source Intelligence) Katmanları:
  1. Website Analizi      — Şirketin kendi sitesinden bilgi çekme
  2. Sosyal Medya Profili — LinkedIn, KvK, company bilgileri
  3. Sektör Analizi       — Sektöre özel zayıf noktalar ve fırsatlar
  4. Psikolojik Profil    — Karar verici profili ve ikna stratejisi

Sonuç: intelligence_report dict olarak döner → Copywriter bunu kullanır.
"""
import re
import json
import time
import requests
from urllib.parse import urlparse
from datetime import datetime
from config import config
from core.logger import get_logger
from core.api_guard import api_guard

log = get_logger("recon_agent")


class ReconAgent:
    """Hedef şirket/kişi hakkında derinlemesine istihbarat toplayan ajan."""

    def __init__(self):
        self._headers = {
            "x-api-key": config.ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        self._web_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self._cache = {}  # domain → intel_report cache (aynı oturumda tekrar sorma)
        log.info("ReconAgent v1 hazır — Deep Intelligence & OSINT aktif.")

    # ═══════════════════════════════════════════════════════════════
    # ANA ARAŞTIRMA FONKSİYONU
    # ═══════════════════════════════════════════════════════════════

    def investigate(self, lead: dict) -> dict:
        """
        Lead hakkında tam istihbarat raporu üret.
        Döner: {
            "company_intel": {...},
            "person_intel": {...},
            "psychological_profile": {...},
            "persuasion_strategy": {...},
            "email_hooks": [...],
            "raw_website_data": "..."
        }
        """
        email = lead.get("email", "")
        company = lead.get("company", "")
        sector = lead.get("sector", "")
        website = lead.get("website", "")
        vehicles = lead.get("vehicles", "")
        location = lead.get("location", "")

        # Cache kontrolü
        domain = self._extract_domain(email, website)
        if domain in self._cache:
            log.info(f"[RECON] Cache hit: {domain}")
            return self._cache[domain]

        log.info(f"[RECON] 🔍 Araştırma başlıyor: {company or email} ({domain})")

        # ─── KATMAN 1: Website Scraping ─────────────────────────
        website_data = self._scrape_website(domain, website)

        # ─── KATMAN 2: E-posta Domain Analizi ───────────────────
        domain_intel = self._analyze_domain(email, domain)

        # ─── KATMAN 3: AI ile Derinlemesine Analiz ──────────────
        intel_report = self._ai_deep_analysis(
            company=company,
            email=email,
            sector=sector,
            domain=domain,
            website_data=website_data,
            domain_intel=domain_intel,
            vehicles=vehicles,
            location=location,
        )

        # Cache'e kaydet
        self._cache[domain] = intel_report
        log.info(f"[RECON] ✅ İstihbarat tamamlandı: {company or domain}")

        return intel_report

    # ═══════════════════════════════════════════════════════════════
    # KATMAN 1: WEB SCRAPING
    # ═══════════════════════════════════════════════════════════════

    def _scrape_website(self, domain: str, website: str = "") -> str:
        """Şirketin web sitesinden bilgi çekme."""
        if not domain:
            return ""

        collected = []
        urls_to_try = []

        # URL listesi oluştur
        if website and website.startswith("http"):
            urls_to_try.append(website)
        urls_to_try.extend([
            f"https://www.{domain}",
            f"https://{domain}",
            f"http://www.{domain}",
        ])

        # Sayfaları tara
        pages_to_check = [
            ("", "HOMEPAGE"),
            ("/about", "OVER ONS"),
            ("/about-us", "OVER ONS"),
            ("/over-ons", "OVER ONS"),
            ("/team", "TEAM"),
            ("/ons-team", "TEAM"),
            ("/diensten", "DIENSTEN"),
            ("/services", "DIENSTEN"),
            ("/contact", "CONTACT"),
        ]

        base_url = ""
        for url in urls_to_try:
            try:
                resp = requests.get(url, headers=self._web_headers, timeout=8,
                                    allow_redirects=True, verify=False)
                if resp.status_code == 200:
                    base_url = url
                    text = self._extract_text(resp.text)
                    collected.append(f"=== HOMEPAGE ===\n{text[:3000]}")
                    break
            except Exception:
                continue

        # Subpagina's scrapen
        if base_url:
            for path, label in pages_to_check[1:]:
                try:
                    page_url = base_url.rstrip("/") + path
                    resp = requests.get(page_url, headers=self._web_headers,
                                        timeout=6, allow_redirects=True, verify=False)
                    if resp.status_code == 200 and len(resp.text) > 500:
                        text = self._extract_text(resp.text)
                        if text.strip() and len(text.strip()) > 100:
                            collected.append(f"=== {label} ===\n{text[:2000]}")
                except Exception:
                    continue
                time.sleep(0.5)

        return "\n\n".join(collected)[:8000] if collected else ""

    def _extract_text(self, html: str) -> str:
        """HTML'den anlamlı metin çıkar."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Gereksiz etiketleri kaldır
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)

            # Temizle
            lines = []
            for line in text.split("\n"):
                line = line.strip()
                if line and len(line) > 3:
                    lines.append(line)
            return "\n".join(lines[:200])
        except ImportError:
            # bs4 yoksa basit regex
            text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:3000]

    # ═══════════════════════════════════════════════════════════════
    # KATMAN 2: DOMAIN & EMAIL INTELLIGENCE
    # ═══════════════════════════════════════════════════════════════

    def _analyze_domain(self, email: str, domain: str) -> dict:
        """E-posta ve domain'den çıkarsama yap."""
        intel = {
            "domain": domain,
            "email_type": "generic",  # generic / personal / role-based
            "possible_name": "",
            "role_guess": "",
            "company_size_hint": "unknown",
        }

        if not email:
            return intel

        local_part = email.split("@")[0].lower()

        # E-posta türü analizi
        generic_prefixes = ["info", "contact", "admin", "office", "sales",
                            "marketing", "support", "helpdesk", "receptie",
                            "algemeen", "mail", "post", "welkom", "hello", "team"]
        role_prefixes = ["ceo", "cfo", "cto", "directeur", "directie",
                         "managing", "eigenaar", "baas", "manager",
                         "hoofd", "inkoop", "logistiek", "fleet", "wagenpark",
                         "operations", "hr", "planning", "commercieel"]

        if local_part in generic_prefixes:
            intel["email_type"] = "generic"
            intel["role_guess"] = "Algemeen contactadres"
        elif local_part in role_prefixes or any(rp in local_part for rp in role_prefixes):
            intel["email_type"] = "role-based"
            intel["role_guess"] = local_part.replace(".", " ").replace("_", " ").title()
        else:
            # Persoonlijk e-mailadres → naam afleiden
            intel["email_type"] = "personal"
            # Patronen: jan.jansen, j.jansen, janjansen, jan_jansen
            name_parts = re.split(r'[._\-]', local_part)
            if len(name_parts) >= 2:
                first = name_parts[0].capitalize()
                last = name_parts[-1].capitalize()
                intel["possible_name"] = f"{first} {last}"
            elif len(local_part) > 3:
                # Probeer voornaam te extraheren
                intel["possible_name"] = local_part.capitalize()
            intel["role_guess"] = "Contactpersoon / Beslisser"

        return intel

    # ═══════════════════════════════════════════════════════════════
    # KATMAN 3: AI DEEP ANALYSIS — PSIKOLOJIK & SOSYOLOJIK PROFİL
    # ═══════════════════════════════════════════════════════════════

    def _ai_deep_analysis(self, company: str, email: str, sector: str,
                          domain: str, website_data: str, domain_intel: dict,
                          vehicles: str, location: str) -> dict:
        """Claude AI ile derinlemesine analiz — psikolojik profil, ikna stratejisi."""

        analysis_prompt = f"""Je bent een elite business intelligence analist en gedragspsycholoog gespecialiseerd in B2B sales strategie.

Je onderzoekt een potentiële klant voor FleetTrack Holland (GPS fleet tracking). 
Analyseer ALLE beschikbare informatie en genereer een gedetailleerd profiel.

═══ BESCHIKBARE INFORMATIE ═══

BEDRIJFSGEGEVENS:
- Bedrijfsnaam: {company or 'onbekend'}
- E-mailadres: {email}
- E-mailtype: {domain_intel.get('email_type', 'unknown')} 
- Mogelijke naam contactpersoon: {domain_intel.get('possible_name', 'onbekend')}
- Geschatte rol: {domain_intel.get('role_guess', 'onbekend')}
- Sector: {sector or 'onbekend'}
- Locatie: {location or 'Nederland'}
- Geschatte vloot: {vehicles or 'onbekend'} voertuigen
- Website domein: {domain}

WEBSITE INHOUD:
{website_data[:5000] if website_data else '(niet beschikbaar)'}

═══ ANALYSE INSTRUCTIES ═══

Genereer een uitgebreid intelligence-rapport met deze secties:

1. **BEDRIJFSPROFIEL** (company_profile):
   - Exacte bedrijfsnaam en wat ze doen
   - Geschatte bedrijfsgrootte (MKB/groot/ZZP)
   - Kernactiviteiten en diensten
   - Klanten/doelgroep van het bedrijf
   - Concurrentiepositie

2. **CONTACTPERSOON PROFIEL** (contact_profile):
   - Naam (indien gevonden of afgeleid)
   - Geschatte functie/beslissingsniveau
   - Communicatiestijl inschatting (formeel/informeel)
   - Waarschijnlijke prioriteiten in hun rol

3. **PSYCHOLOGISCH PROFIEL** (psychological_profile):
   Welk type beslisser is dit waarschijnlijk?
   - Analytisch (data-gedreven, wil ROI zien)
   - Driver (resultaat-gericht, wil snelle actie)
   - Amiable (relatie-gericht, wil vertrouwen)
   - Expressive (visie-gericht, wil innovatie)
   Beslis op basis van sector, bedrijfsgrootte, en websitetoon.

4. **PIJNPUNTEN & KANSEN** (pain_points):
   Top 5 SPECIFIEKE pijnpunten die dit bedrijf waarschijnlijk ervaart.
   Baseer op sector + website-informatie + bedrijfsgrootte.
   Wees CONCREET en HERKENBAAR — geen algemeenheden.

5. **OVERTUIGINGSSTRATEGIE** (persuasion_strategy):
   Gebruik deze psychologische principes en kies de BESTE combinatie:
   
   - **Cialdini's 6 principes**: Welke zijn het effectiefst?
     • Wederkerigheid (iets gratis aanbieden)
     • Commitment/consistentie (kleine stap eerst)
     • Social proof (vergelijkbare bedrijven)
     • Autoriteit (expertise tonen)
     • Schaarste (beperkt aanbod)
     • Sympathie (gemeenschappelijke grond)
   
   - **Kahneman's System 1/2**: 
     • System 1 triggers (emotie, urgentie, verlies-aversie)
     • System 2 triggers (data, logica, ROI-berekening)
   
   - **Maslow's behoeftenhiërarchie**:
     • Veiligheid (voertuigdiefstal, compliance)
     • Sociaal (teamcoördinatie, klanttevredenheid)
     • Waardering (marktleiderschap, innovatie)
     • Zelfactualisatie (duurzaamheid, groei)
   
   - **Nudging technieken**:
     • Default effect (gratis proef als standaard)
     • Anchoring (vergelijk kosten met/zonder tracking)
     • Framing (besparing vs. kosten)
     • Loss aversion (wat ze VERLIEZEN zonder tracking)

6. **GEPERSONALISEERDE HOOKS** (email_hooks):
   Schrijf 5 specifieke opening hooks voor de e-mail.
   Elke hook moet:
   - Direct relevant zijn voor DIT specifieke bedrijf
   - Een emotionele OF logische trigger bevatten
   - Nieuwsgierigheid wekken
   - NIET klinken als spam of marketing

7. **TONE OF VOICE ADVIES** (tone_advice):
   - Welke toon moet de e-mail hebben?
   - Welke woorden VERMIJDEN?
   - Welke trigger-woorden GEBRUIKEN?
   - Formeel of informeel?
   - Direct of subtiel?

8. **SOCIAL ENGINEERING INZICHTEN** (social_insights):
   - Beste tijdstip om te mailen (op basis van sector)
   - Beste dag van de week
   - Subject line strategie
   - Welke CTA werkt het best?
   - Follow-up timing advies

═══ OUTPUT FORMAT ═══

Antwoord ALLEEN in geldig JSON:
{{
  "company_profile": {{
    "name": "...",
    "description": "...",
    "size": "MKB/groot/ZZP",
    "core_activities": ["..."],
    "target_customers": "...",
    "competitive_position": "..."
  }},
  "contact_profile": {{
    "name": "...",
    "title": "...",
    "decision_level": "hoog/midden/laag",
    "communication_style": "formeel/informeel",
    "priorities": ["..."]
  }},
  "psychological_profile": {{
    "type": "analytisch/driver/amiable/expressive",
    "system_thinking": "system1/system2/gemengd",
    "maslow_level": "veiligheid/sociaal/waardering/zelfactualisatie",
    "key_motivator": "...",
    "decision_style": "..."
  }},
  "pain_points": [
    {{"point": "...", "severity": "hoog/midden", "emotional_trigger": "..."}},
  ],
  "persuasion_strategy": {{
    "primary_cialdini": "...",
    "secondary_cialdini": "...",
    "nudge_technique": "...",
    "framing": "...",
    "key_argument": "...",
    "avoid": "..."
  }},
  "email_hooks": [
    "...",
  ],
  "tone_advice": {{
    "tone": "...",
    "formality": "formeel/informeel/zakelijk-warm",
    "trigger_words": ["..."],
    "avoid_words": ["..."],
    "approach": "..."
  }},
  "social_insights": {{
    "best_time": "...",
    "best_day": "...",
    "subject_strategy": "...",
    "cta_type": "...",
    "followup_timing": "..."
  }}
}}"""

        payload = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": 2500,
            "messages": [{"role": "user", "content": analysis_prompt}],
        }

        try:
            resp = api_guard.call(payload, self._headers, timeout=60)
            if resp and resp.ok:
                raw = resp.json()["content"][0]["text"]

                # JSON parse
                json_str = raw
                if "```json" in raw:
                    json_str = raw.split("```json")[1].split("```")[0]
                elif "```" in raw:
                    json_str = raw.split("```")[1].split("```")[0]
                elif "{" in raw:
                    # İlk { ile son } arasını al
                    start = raw.index("{")
                    end = raw.rindex("}") + 1
                    json_str = raw[start:end]

                report = json.loads(json_str.strip())
                report["raw_website_data"] = website_data[:2000] if website_data else ""
                report["domain_intel"] = domain_intel
                report["investigation_timestamp"] = datetime.now().isoformat()

                log.info(f"[RECON] ✅ AI analiz tamamlandı: "
                         f"profil={report.get('psychological_profile', {}).get('type', '?')}, "
                         f"strateji={report.get('persuasion_strategy', {}).get('primary_cialdini', '?')}")
                return report

        except json.JSONDecodeError as e:
            log.warning(f"[RECON] JSON parse hatası: {e}")
        except Exception as e:
            log.error(f"[RECON] AI analiz hatası: {e}")

        # Fallback — temel rapor
        return self._generate_fallback_report(company, sector, domain_intel, vehicles, location)

    # ═══════════════════════════════════════════════════════════════
    # FALLBACK RAPOR (AI başarısız olursa)
    # ═══════════════════════════════════════════════════════════════

    def _generate_fallback_report(self, company: str, sector: str,
                                  domain_intel: dict, vehicles: str,
                                  location: str) -> dict:
        """AI başarısız olursa temel profil dön."""
        sector_profiles = {
            "transport": {"type": "driver", "cialdini": "social_proof", "pain": "brandstofkosten en ritregistratie"},
            "bouw": {"type": "driver", "cialdini": "autoriteit", "pain": "voertuigdiefstal en materieel traceren"},
            "schoonmaak": {"type": "amiable", "cialdini": "wederkerigheid", "pain": "privégebruik en routeplanning"},
            "logistiek": {"type": "analytisch", "cialdini": "social_proof", "pain": "leverbetrouwbaarheid en kosten"},
            "thuiszorg": {"type": "amiable", "cialdini": "autoriteit", "pain": "veiligheid en ritregistratie"},
            "catering": {"type": "expressive", "cialdini": "schaarste", "pain": "bezorgtijden en klachten"},
        }

        sp = sector_profiles.get(sector, {"type": "analytisch", "cialdini": "social_proof", "pain": "vlootbeheer"})

        return {
            "company_profile": {
                "name": company or "onbekend",
                "description": f"{sector} bedrijf in {location or 'Nederland'}",
                "size": "MKB",
                "core_activities": [sector or "bedrijfsdiensten"],
                "target_customers": "zakelijke markt",
                "competitive_position": "actief in de markt",
            },
            "contact_profile": domain_intel,
            "psychological_profile": {
                "type": sp["type"],
                "system_thinking": "gemengd",
                "maslow_level": "veiligheid",
                "key_motivator": "kostenbesparing",
                "decision_style": "pragmatisch",
            },
            "pain_points": [
                {"point": sp["pain"], "severity": "hoog", "emotional_trigger": "frustratie"},
            ],
            "persuasion_strategy": {
                "primary_cialdini": sp["cialdini"],
                "secondary_cialdini": "wederkerigheid",
                "nudge_technique": "default_effect",
                "framing": "besparing",
                "key_argument": f"Vergelijkbare {sector}-bedrijven besparen al met GPS tracking",
                "avoid": "te agressief, te veel marketing-taal",
            },
            "email_hooks": [
                f"Hoe houdt {company or 'uw bedrijf'} overzicht over alle voertuigen?",
            ],
            "tone_advice": {
                "tone": "zakelijk-warm",
                "formality": "zakelijk-warm",
                "trigger_words": ["besparen", "overzicht", "inzicht"],
                "avoid_words": ["gratis", "aanbieding", "actie"],
                "approach": "adviseur rol",
            },
            "social_insights": {
                "best_time": "09:00-11:00",
                "best_day": "dinsdag of woensdag",
                "subject_strategy": "vraag-gebaseerd",
                "cta_type": "zachte uitnodiging",
                "followup_timing": "3 dagen",
            },
            "raw_website_data": "",
            "domain_intel": domain_intel,
            "investigation_timestamp": datetime.now().isoformat(),
        }

    # ═══════════════════════════════════════════════════════════════
    # HELPER: INTEL → COPYWRITER CONTEXT
    # ═══════════════════════════════════════════════════════════════

    def format_for_copywriter(self, intel: dict) -> str:
        """Intel raporu → Copywriter prompt'una eklenecek bağlam."""
        parts = []

        # Company profil
        cp = intel.get("company_profile", {})
        if cp.get("description"):
            parts.append(f"BEDRIJFSPROFIEL: {cp['description']}")
        if cp.get("core_activities"):
            acts = ", ".join(cp["core_activities"][:5]) if isinstance(cp["core_activities"], list) else str(cp["core_activities"])
            parts.append(f"KERNACTIVITEITEN: {acts}")

        # Contact profil
        contact = intel.get("contact_profile", {})
        if isinstance(contact, dict):
            name = contact.get("name") or contact.get("possible_name", "")
            if name and name != "onbekend":
                parts.append(f"CONTACTPERSOON: {name}")
            title = contact.get("title") or contact.get("role_guess", "")
            if title:
                parts.append(f"FUNCTIE: {title}")
            style = contact.get("communication_style", "")
            if style:
                parts.append(f"COMMUNICATIESTIJL: {style}")

        # Psychologisch profiel
        pp = intel.get("psychological_profile", {})
        if pp:
            parts.append(f"\nPSYCHOLOGISCH PROFIEL:")
            parts.append(f"  Type: {pp.get('type', '?')}")
            parts.append(f"  Denksysteem: {pp.get('system_thinking', '?')}")
            parts.append(f"  Motivator: {pp.get('key_motivator', '?')}")

        # Pijnpunten
        pains = intel.get("pain_points", [])
        if pains:
            parts.append(f"\nSPECIFIEKE PIJNPUNTEN:")
            for p in pains[:5]:
                if isinstance(p, dict):
                    parts.append(f"  - {p.get('point', '')}")
                else:
                    parts.append(f"  - {p}")

        # Overtuigingsstrategie
        ps = intel.get("persuasion_strategy", {})
        if ps:
            parts.append(f"\nOVERTUIGINGSSTRATEGIE:")
            parts.append(f"  Primair: {ps.get('primary_cialdini', '?')}")
            parts.append(f"  Framing: {ps.get('framing', '?')}")
            parts.append(f"  Kernargument: {ps.get('key_argument', '?')}")
            if ps.get("avoid"):
                parts.append(f"  Vermijd: {ps.get('avoid')}")

        # E-mail hooks
        hooks = intel.get("email_hooks", [])
        if hooks:
            parts.append(f"\nGEPERSONALISEERDE HOOKS (kies 1):")
            for h in hooks[:5]:
                parts.append(f"  • {h}")

        # Toon advies
        ta = intel.get("tone_advice", {})
        if ta:
            parts.append(f"\nTOON:")
            parts.append(f"  Stijl: {ta.get('tone', '?')}")
            if ta.get("trigger_words"):
                tw = ", ".join(ta["trigger_words"][:6]) if isinstance(ta["trigger_words"], list) else str(ta["trigger_words"])
                parts.append(f"  Trigger-woorden: {tw}")
            if ta.get("avoid_words"):
                aw = ", ".join(ta["avoid_words"][:6]) if isinstance(ta["avoid_words"], list) else str(ta["avoid_words"])
                parts.append(f"  Vermijd: {aw}")

        return "\n".join(parts) if parts else ""

    # ═══════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════

    def _extract_domain(self, email: str, website: str = "") -> str:
        """E-posta veya website'den domain çıkar."""
        if website:
            try:
                parsed = urlparse(website if "://" in website else f"https://{website}")
                domain = parsed.netloc or parsed.path
                domain = domain.replace("www.", "").strip("/")
                if domain:
                    return domain
            except Exception:
                pass

        if email and "@" in email:
            domain = email.split("@")[1].lower()
            # Genel e-posta sağlayıcıları filtrele
            generic = ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com",
                        "live.nl", "ziggo.nl", "kpnmail.nl", "xs4all.nl",
                        "hetnet.nl", "planet.nl", "upcmail.nl", "home.nl",
                        "casema.nl", "chello.nl", "online.nl", "tele2.nl"]
            if domain not in generic:
                return domain

        return ""

    def ping(self) -> bool:
        return True


# Singleton
recon_agent = ReconAgent()
