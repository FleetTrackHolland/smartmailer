"""
agents/lead_finder.py — SmartMailer Ultimate Lead Discovery (v7.0)
SmartMailer Pro v6 + FleetTrack CRM scraper birleşimi.
10+ kaynak: DeTelefoongids, Opendi, Telefoonboek, OpenStreetMap,
Bing, DuckDuckGo, Startpage, AI bulk, website crawl, email guess.
"""
import re
import json
import time
import random
import socket
import requests
from urllib.parse import urlparse, quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import config
from core.logger import get_logger
from core.database import db

log = get_logger("lead_finder")

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"

# ─── HOLLANDA ŞEHİRLERİ ──────────────────────────────────────────
DUTCH_CITIES = [
    # TOP 20 — Büyük şehirler
    "Amsterdam", "Rotterdam", "Den Haag", "Utrecht", "Eindhoven",
    "Groningen", "Tilburg", "Almere", "Breda", "Nijmegen",
    "Apeldoorn", "Haarlem", "Arnhem", "Enschede", "Amersfoort",
    "Zaanstad", "Den Bosch", "Haarlemmermeer", "Zoetermeer", "Zwolle",
    # TOP 40 — Orta şehirler
    "Maastricht", "Dordrecht", "Leiden", "Deventer", "Delft",
    "Venlo", "Alkmaar", "Leeuwarden", "Hilversum", "Heerlen",
    "Oss", "Roosendaal", "Alphen aan den Rijn", "Gouda", "Vlaardingen",
    "Lelystad", "Emmen", "Helmond", "Purmerend", "Schiedam",
    # 40-60 — Bölgesel merkezler
    "Spijkenisse", "Capelle aan den IJssel", "Kampen", "Hoogeveen",
    "Hoorn", "Veenendaal", "Zeist", "Barneveld", "Uden",
    "Amstelveen", "Rijswijk", "Nieuwegein", "Roermond", "Weert",
    "Harderwijk", "Doetinchem", "Tiel", "Middelburg", "Goes",
    # 60-85 — Kleinere steden
    "Terneuzen", "Vlissingen", "Bergen op Zoom", "Waalwijk", "Veghel",
    "Boxtel", "Elst", "Cuijk", "Wageningen", "Ede",
    "Meppel", "Steenwijk", "Assen", "Drachten", "Sneek",
    "Heerenveen", "Gorinchem", "Woerden", "IJmuiden", "Beverwijk",
    "Heerhugowaard", "Schagen", "Den Helder", "Bussum", "Naarden",
]

# ─── SEKTÖR ARAMA STRATEJİLERİ ───────────────────────────────────
SEARCH_QUERIES = {
    "transport": [
        "{city} transportbedrijf email contact",
        "{city} vrachtvervoer bedrijf contact",
        "{city} logistiek transport bedrijf telefoon",
        "transportbedrijf {city} wagenpark vloot",
        "{city} koeriersdienst contact email",
        "verhuisbedrijf {city} email",
        "koeltransport {city} contact",
    ],
    "bouw": [
        "{city} bouwbedrijf contact email",
        "{city} aannemersbedrijf contact",
        "{city} bouwbedrijf wagenpark",
        "grondverzet {city} bedrijf email",
        "installatiebedrijf {city} contact",
    ],
    "schoonmaak": [
        "{city} schoonmaakbedrijf contact email",
        "{city} glazenwasser bedrijf",
        "{city} facilitaire diensten contact",
        "schoonmaakbedrijf {city} email",
    ],
    "logistiek": [
        "{city} logistiek bedrijf email",
        "{city} warehousing transport contact",
        "{city} distributie bedrijf",
    ],
    "koerier": [
        "{city} koeriersdienst email contact",
        "{city} pakketbezorging bedrijf",
        "bezorgdienst {city} contact",
    ],
    "thuiszorg": [
        "{city} thuiszorg organisatie contact email",
        "{city} zorginstelling wagenpark",
        "thuiszorg {city} bedrijf email",
    ],
    "verhuisbedrijf": [
        "{city} verhuisbedrijf email contact",
        "{city} verhuisservice bedrijf",
    ],
    "taxi": [
        "{city} taxibedrijf email contact",
        "{city} personenvervoer bedrijf",
    ],
    "installatiebedrijf": [
        "{city} installatiebedrijf email contact",
        "{city} cv ketel installatie bedrijf",
    ],
    "catering": [
        "{city} cateringbedrijf email contact",
        "{city} horeca catering bedrijf",
    ],
    "beveiliging": [
        "{city} beveiligingsbedrijf email contact",
        "{city} security bedrijf wagenpark",
    ],
    "groenvoorziening": [
        "{city} hoveniersbedrijf email contact",
        "{city} groenvoorziening bedrijf",
    ],
    "autorijschool": [
        "{city} autorijschool email contact",
        "{city} rijschool wagenpark bedrijf",
    ],
    "autoverhuur": [
        "{city} autoverhuur bedrijf email",
        "{city} lease auto verhuur contact",
    ],
    "garage": [
        "{city} garage autogarage email contact",
        "{city} autobedrijf werkplaats",
    ],
    "vuilophaal": [
        "{city} afvalinzameling bedrijf email",
        "{city} vuilophaal container bedrijf",
    ],
    "default": [
        "{city} bedrijf wagenpark email",
        "{city} fleet contact email",
        "{city} bedrijfswagens contact",
        "{city} zakelijk bedrijf email",
    ],
}

# ─── SECTOR MAP (for directories) ─────────────────────────────────
SECTOR_MAP_TELEFOONBOEK = {
    "transport": "transportbedrijven",
    "bouw": "bouwbedrijven",
    "schoonmaak": "schoonmaakbedrijven",
    "logistiek": "logistieke-bedrijven",
    "koerier": "koeriersdiensten",
    "thuiszorg": "thuiszorg",
    "verhuisbedrijf": "verhuisbedrijven",
    "taxi": "taxibedrijven",
    "installatiebedrijf": "installatiebedrijven",
    "catering": "cateringbedrijven",
    "beveiliging": "beveiligingsbedrijven",
    "groenvoorziening": "hoveniersbedrijven",
    "loodgieter": "loodgieters",
    "elektricien": "elektriciens",
    "dakdekker": "dakdekkersbedrijven",
    "schildersbedrijf": "schildersbedrijven",
    "afvalverwerking": "afvalverwerking",
    "ambulance": "ambulancediensten",
    "bezorgdienst": "bezorgdiensten",
    "autorijschool": "autorijscholen",
    "autoverhuur": "autoverhuurbedrijven",
    "garage": "garages",
    "vuilophaal": "afvalinzameling",
    "glas": "glaszetters",
    "stukadoor": "stukadoors",
    "timmerman": "timmerbedrijven",
    "metselaar": "metselaars",
}

# ─── USER AGENTS ROTATION ────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

# ─── DOMAINS TO SKIP ─────────────────────────────────────────────
SKIP_DOMAINS = {
    "duckduckgo.com", "google.com", "google.nl", "facebook.com",
    "linkedin.com", "twitter.com", "youtube.com", "wikipedia.org",
    "kvk.nl", "indeed.nl", "indeed.com", "glassdoor.nl",
    "glassdoor.com", "yelp.com", "tripadvisor.nl", "trustpilot.com",
    "maps.google.com", "instagram.com", "tiktok.com", "pinterest.com",
    "bing.com", "yahoo.com", "amazon.com", "amazon.nl",
    "werkzoeken.nl", "werk.nl", "nationalevacaturebank.nl",
    "detelefoongids.nl", "goudengids.nl", "opendi.nl",
    "bedrijvenpagina.nl", "kompas.nl", "telefoonboek.nl",
    "marktplaats.nl", "thuisbezorgd.nl", "booking.com",
    "github.com", "stackoverflow.com", "reddit.com",
    "whatsapp.com", "t.me", "telegram.org",
    "startpage.com", "cdn.startpage.com",
    "app.startpage.com", "searx.org", "ecosia.org",
    "yandex.com", "baidu.com",
}

# ─── INVALID EMAIL DOMAINS ───────────────────────────────────────
INVALID_EMAIL_PARTS = [
    "example.com", "test.com", "temp.com", "noreply",
    "no-reply", "mailer-daemon", "postmaster",
    ".png", ".jpg", ".gif", ".jpeg", ".svg", ".css", ".js",
    "wixpress.com", "sentry.io", "cloudflare.com",
    "googleapis.com", "gstatic.com", "google.com",
    "facebook.com", "twitter.com", "instagram.com",
    "squarespace.com", "wordpress.com", "mailchimp.com",
    "campaign-archive.com", "sendgrid.net",
    "startpage.com", "duckduckgo.com", "bing.com",
    "yahoo.com", "yandex.com", "baidu.com",
    "microsoft.com", "apple.com", "amazon.com",
    "github.com", "stackoverflow.com", "reddit.com",
    "w3.org", "schema.org", "jquery.com",
    "fontawesome.com", "bootstrapcdn.com",
]


class LeadFinder:
    """SmartMailer Ultimate Lead Discovery — 10+ kaynak, paralel arama."""

    def __init__(self):
        self._headers = {
            "x-api-key": config.ANTHROPIC_API_KEY,
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        })
        self._scanned_domains: set[str] = set()
        self._found_emails: set[str] = set()
        self._mx_cache: dict[str, bool] = {}
        self._stats = {
            "pages_scanned": 0, "urls_analyzed": 0,
            "leads_found": 0, "leads_saved": 0,
            "leads_duplicate": 0, "emails_extracted": 0,
            "directories_scraped": 0, "ai_calls": 0,
            "errors": 0, "cities_searched": 0,
            "mx_verified": 0, "telefoonboek_found": 0,
            "openstreetmap_found": 0,
        }
        log.info("LeadFinder v7.0 hazır (SmartMailer Ultimate — 10+ kaynak).")

    def get_discovery_stats(self) -> dict:
        return dict(self._stats)

    def reset_stats(self):
        for k in self._stats:
            self._stats[k] = 0

    def ping(self) -> bool:
        return True

    # ══════════════════════════════════════════════════════════════
    # ANA KEŞİF METODU
    # ══════════════════════════════════════════════════════════════

    def discover_leads(self, sector: str = "transport",
                       location: str = "Nederland") -> list[dict]:
        """
        Tüm kaynakları kullanarak lead keşfet.
        10+ kaynak: dizinler, web arama, AI, OpenStreetMap, Telefoonboek.
        """
        self.reset_stats()
        log.info(f"[DISCOVER] ═══ ULTIMATE ARAMA: {sector} / {location} ═══")

        all_results: list[dict] = []
        max_leads = config.MAX_LEADS_PER_SEARCH

        # ── PHASE 1: Endüstri dizinleri (DeTelefoongids + Opendi) ──
        log.info("[DISCOVER] PHASE 1: Endüstri dizinleri...")
        dir_leads = self._scrape_detelefoongids(sector)
        dir_leads.extend(self._scrape_opendi(sector))
        all_results.extend(dir_leads)
        log.info(f"[DISCOVER] Phase 1: {len(dir_leads)} lead (dizinler)")

        # ── PHASE 2: Telefoonboek.nl (FleetTrack CRM'den) ──
        if config.TELEFOONBOEK_ENABLED:
            log.info("[DISCOVER] PHASE 2: Telefoonboek.nl...")
            tb_leads = self._scrape_telefoonboek(sector, location)
            all_results.extend(tb_leads)
            self._stats["telefoonboek_found"] = len(tb_leads)
            log.info(f"[DISCOVER] Phase 2: {len(tb_leads)} lead (Telefoonboek)")

        # ── PHASE 2B: Goudengids.nl ──
        log.info("[DISCOVER] PHASE 2B: Goudengids.nl...")
        gg_leads = self._scrape_goudengids(sector)
        all_results.extend(gg_leads)
        log.info(f"[DISCOVER] Phase 2B: {len(gg_leads)} lead (Goudengids)")

        # ── PHASE 2C: Bedrijvenpagina.nl ──
        log.info("[DISCOVER] PHASE 2C: Bedrijvenpagina.nl...")
        bp_leads = self._scrape_bedrijvenpagina(sector)
        all_results.extend(bp_leads)
        log.info(f"[DISCOVER] Phase 2C: {len(bp_leads)} lead (Bedrijvenpagina)")

        # ── PHASE 3: OpenStreetMap / Nominatim (FleetTrack CRM'den) ──
        if config.OPENSTREETMAP_ENABLED:
            log.info("[DISCOVER] PHASE 3: OpenStreetMap...")
            osm_leads = self._search_openstreetmap(sector, location)
            all_results.extend(osm_leads)
            self._stats["openstreetmap_found"] = len(osm_leads)
            log.info(f"[DISCOVER] Phase 3: {len(osm_leads)} lead (OpenStreetMap)")

        # ── PHASE 3B: OpenKVK — Kamer van Koophandel ──
        log.info("[DISCOVER] PHASE 3B: OpenKVK...")
        kvk_leads = self._scrape_openkvk(sector)
        all_results.extend(kvk_leads)
        log.info(f"[DISCOVER] Phase 3B: {len(kvk_leads)} lead (OpenKVK)")

        # ── PHASE 4: AI bilgi bankası (Claude) ──
        log.info("[DISCOVER] PHASE 4: AI bilgi bankası...")
        ai_leads = self._ai_bulk_lead_search(sector)
        all_results.extend(ai_leads)
        log.info(f"[DISCOVER] Phase 4: {len(ai_leads)} lead (AI)")

        # ── PHASE 5: Şehir bazlı web araması (shared hosting koruması) ──
        log.info("[DISCOVER] PHASE 5: Şehir bazlı web araması...")
        cities = random.sample(DUTCH_CITIES, min(5, len(DUTCH_CITIES)))  # Max 5 şehir
        self._stats["cities_searched"] = len(cities)

        # Shared hosting: sıralı arama, paralel değil
        for city in cities:
            if len(all_results) >= max_leads:
                break
            try:
                city_leads = self._search_city(sector, city)
                all_results.extend(city_leads)
                if city_leads:
                    log.info(f"[DISCOVER] {city}: {len(city_leads)} lead")
            except Exception as e:
                log.debug(f"[DISCOVER] {city} hatası: {e}")
            time.sleep(3)  # Şehirler arası bekleme

        log.info(f"[DISCOVER] Phase 5: toplam {len(all_results)} lead")

        # ── PHASE 6: MX Doğrulama ──
        if config.EMAIL_VERIFY_MX:
            log.info("[DISCOVER] PHASE 6: MX doğrulama...")
            verified = []
            for lead in all_results:
                email = lead.get("email", "")
                if email and self._verify_mx(email):
                    verified.append(lead)
                    self._stats["mx_verified"] += 1
                elif email:
                    lead["score"] = max(lead.get("score", 0) - 15, 0)
                    verified.append(lead)  # Yine de tut ama skoru düşür
            all_results = verified

        # ── PHASE 7: AI toplu doğrulama ──
        unscored = [l for l in all_results if not l.get("score") or l.get("score", 0) < 40]
        if unscored and len(unscored) <= 50:
            log.info(f"[DISCOVER] PHASE 7: {len(unscored)} lead AI doğrulama...")
            self._batch_validate_with_ai(unscored)

        # ── Veritabanına kaydet ──
        saved = 0
        for lead in all_results:
            email = lead.get("email", "")
            if email:
                try:
                    db.add_discovered_lead(
                        email=email,
                        company=lead.get("company_name", ""),
                        sector=lead.get("sector", sector),
                        location=lead.get("location", location),
                        vehicles=str(lead.get("estimated_vehicles", "")),
                        website=lead.get("website", ""),
                        phone=lead.get("phone", ""),
                        contact_person=lead.get("contact_person", ""),
                        discovery_score=lead.get("score", 60),
                        source=lead.get("source", "web_discovery"),
                        icebreaker=lead.get("icebreaker", ""),
                    )
                    saved += 1
                except Exception as e:
                    log.debug(f"[DISCOVER] DB kayıt hatası: {email} — {e}")

        self._stats["leads_saved"] = saved
        self._stats["leads_found"] = len(all_results)

        log.info(f"[DISCOVER] ═══ TAMAMLANDI ═══")
        log.info(f"[DISCOVER] Bulunan: {len(all_results)} | Kaydedilen: {saved} | "
                 f"Dizin: {self._stats['directories_scraped']} | "
                 f"Telefoonboek: {self._stats['telefoonboek_found']} | "
                 f"OSM: {self._stats['openstreetmap_found']} | "
                 f"MX OK: {self._stats['mx_verified']} | "
                 f"AI: {self._stats['ai_calls']} | "
                 f"Hata: {self._stats['errors']}")

        return all_results

    # ══════════════════════════════════════════════════════════════
    # PHASE 1: DeTelefoongids + Opendi
    # ══════════════════════════════════════════════════════════════

    def _scrape_detelefoongids(self, sector: str) -> list[dict]:
        results = []
        search_term = SECTOR_MAP_TELEFOONBOEK.get(sector, sector)
        cities = ["rotterdam", "amsterdam", "den-haag", "utrecht", "eindhoven",
                  "groningen", "tilburg", "breda", "nijmegen", "arnhem",
                  "almere", "haarlem", "enschede", "zwolle", "maastricht"]

        for city in cities:
            try:
                url = f"https://www.detelefoongids.nl/{search_term}/{city}/"
                resp = self._safe_get(url, timeout=12)
                if not resp or not resp.ok:
                    continue

                self._stats["directories_scraped"] += 1
                companies = self._extract_directory_listings(resp.text, url)
                for comp in companies:
                    if comp.get("email") and comp["email"] not in self._found_emails:
                        if not db.lead_exists(comp["email"]):
                            self._found_emails.add(comp["email"])
                            comp["sector"] = sector
                            comp["location"] = city.replace("-", " ").title()
                            comp["source"] = "detelefoongids"
                            comp["score"] = 65
                            results.append(comp)
                time.sleep(0.8)
            except Exception as e:
                self._stats["errors"] += 1
                log.debug(f"[DTGIDS] Hata: {city}/{sector} — {e}")

        log.info(f"[DTGIDS] {len(results)} lead bulundu")
        return results

    def _scrape_opendi(self, sector: str) -> list[dict]:
        results = []
        cities = ["Rotterdam", "Amsterdam", "Utrecht", "Eindhoven", "Den+Haag",
                  "Groningen", "Tilburg", "Breda", "Nijmegen"]

        for city in cities:
            try:
                url = f"https://www.opendi.nl/{sector.replace(' ', '+')}+{city}/"
                resp = self._safe_get(url, timeout=12)
                if not resp or not resp.ok:
                    continue

                self._stats["directories_scraped"] += 1
                companies = self._extract_directory_listings(resp.text, url)
                for comp in companies:
                    if comp.get("email") and comp["email"] not in self._found_emails:
                        if not db.lead_exists(comp["email"]):
                            self._found_emails.add(comp["email"])
                            comp["sector"] = sector
                            comp["source"] = "opendi"
                            comp["score"] = 60
                            results.append(comp)
                time.sleep(0.8)
            except Exception as e:
                self._stats["errors"] += 1
                log.debug(f"[OPENDI] Hata: {city}/{sector} — {e}")

        log.info(f"[OPENDI] {len(results)} lead bulundu")
        return results

    # ══════════════════════════════════════════════════════════════
    # PHASE 2B: Goudengids.nl
    # ══════════════════════════════════════════════════════════════

    def _scrape_goudengids(self, sector: str) -> list[dict]:
        """Goudengids.nl — Altın Rehber scraping."""
        results = []
        search_term = SECTOR_MAP_TELEFOONBOEK.get(sector, sector)
        cities = ["rotterdam", "amsterdam", "den-haag", "utrecht", "eindhoven",
                  "groningen", "tilburg", "breda", "nijmegen", "arnhem",
                  "almere", "haarlem", "enschede", "zwolle", "maastricht"]

        for city in cities:
            try:
                url = f"https://www.goudengids.nl/{search_term}/{city}/"
                resp = self._safe_get(url, timeout=12)
                if not resp or not resp.ok:
                    continue

                self._stats["directories_scraped"] += 1
                companies = self._extract_directory_listings(resp.text, url)
                for comp in companies:
                    if comp.get("email") and comp["email"] not in self._found_emails:
                        if not db.lead_exists(comp["email"]):
                            self._found_emails.add(comp["email"])
                            comp["sector"] = sector
                            comp["location"] = city.replace("-", " ").title()
                            comp["source"] = "goudengids"
                            comp["score"] = 65
                            results.append(comp)
                time.sleep(0.8)
            except Exception as e:
                self._stats["errors"] += 1
                log.debug(f"[GOUDENGIDS] Hata: {city}/{sector} — {e}")

        log.info(f"[GOUDENGIDS] {len(results)} lead bulundu")
        return results

    # ══════════════════════════════════════════════════════════════
    # PHASE 2C: Bedrijvenpagina.nl
    # ══════════════════════════════════════════════════════════════

    def _scrape_bedrijvenpagina(self, sector: str) -> list[dict]:
        """Bedrijvenpagina.nl — Bedrijven dizini scraping."""
        results = []
        search_term = SECTOR_MAP_TELEFOONBOEK.get(sector, sector)
        cities = ["rotterdam", "amsterdam", "utrecht", "eindhoven", "den-haag",
                  "groningen", "tilburg", "breda", "nijmegen", "arnhem"]

        for city in cities:
            try:
                url = f"https://www.bedrijvenpagina.nl/zoek/{search_term}/{city}/"
                resp = self._safe_get(url, timeout=12)
                if not resp or not resp.ok:
                    continue

                self._stats["directories_scraped"] += 1
                companies = self._extract_directory_listings(resp.text, url)
                for comp in companies:
                    if comp.get("email") and comp["email"] not in self._found_emails:
                        if not db.lead_exists(comp["email"]):
                            self._found_emails.add(comp["email"])
                            comp["sector"] = sector
                            comp["location"] = city.replace("-", " ").title()
                            comp["source"] = "bedrijvenpagina"
                            comp["score"] = 60
                            results.append(comp)
                time.sleep(0.8)
            except Exception as e:
                self._stats["errors"] += 1
                log.debug(f"[BEDRIJVENPAGINA] Hata: {city}/{sector} — {e}")

        log.info(f"[BEDRIJVENPAGINA] {len(results)} lead bulundu")
        return results

    # ══════════════════════════════════════════════════════════════
    # PHASE 3B: OpenKVK — Kamer van Koophandel
    # ══════════════════════════════════════════════════════════════

    def _scrape_openkvk(self, sector: str) -> list[dict]:
        """OpenKVK.nl/Overheid — Kamer van Koophandel açık veri."""
        results = []
        sector_nl = SECTOR_MAP_TELEFOONBOEK.get(sector, sector)

        # Meerdere bronnen proberen
        search_urls = [
            f"https://openkvk.nl/zoeken/{sector_nl}",
            f"https://www.kvk.nl/zoeken/?source=all&q={sector_nl}&start=0&site=kvk2014",
        ]

        for search_url in search_urls:
            try:
                resp = self._safe_get(search_url, timeout=15)
                if not resp or not resp.ok:
                    continue

                self._stats["directories_scraped"] += 1

                # Extract bedrijfsnamen en websites
                companies = self._extract_directory_listings(resp.text, search_url)
                for comp in companies:
                    if comp.get("email") and comp["email"] not in self._found_emails:
                        if not db.lead_exists(comp["email"]):
                            self._found_emails.add(comp["email"])
                            comp["sector"] = sector
                            comp["source"] = "kvk"
                            comp["score"] = 70
                            results.append(comp)

                # Ook bedrijfsnamen + .nl domain proberen
                names = re.findall(r'(?:class="[^"]*name[^"]*"|data-name=)["\s]*([A-Z][a-zA-Z\s&-]{3,40})', resp.text)
                for name in names[:30]:
                    clean = re.sub(r'[^a-z0-9]', '', name.strip().lower())
                    if clean and len(clean) > 3:
                        guessed = f"info@{clean}.nl"
                        if guessed not in self._found_emails and not db.lead_exists(guessed):
                            self._found_emails.add(guessed)
                            results.append({
                                "company_name": name.strip(),
                                "email": guessed,
                                "phone": "",
                                "website": f"https://www.{clean}.nl",
                                "sector": sector,
                                "location": "Nederland",
                                "source": "kvk",
                                "score": 50,
                                "is_good_lead": True,
                            })

                time.sleep(1)
            except Exception as e:
                self._stats["errors"] += 1
                log.debug(f"[KVK] Hata: {sector} — {e}")

        log.info(f"[KVK] {len(results)} lead bulundu")
        return results
    # ══════════════════════════════════════════════════════════════

    def _scrape_telefoonboek(self, sector: str, location: str) -> list[dict]:
        """Telefoonboek.nl'den BeautifulSoup ile profesyonel scraping."""
        results = []
        clean_location = location.lower().replace(" ", "-")
        search_term = SECTOR_MAP_TELEFOONBOEK.get(sector, sector)

        cities_to_search = [clean_location] if clean_location != "nederland" else [
            "rotterdam", "amsterdam", "den-haag", "utrecht", "eindhoven",
            "groningen", "tilburg", "breda", "nijmegen", "arnhem",
            "almere", "haarlem", "apeldoorn", "enschede", "amersfoort",
        ]

        for city in cities_to_search:
            try:
                url = f"https://www.telefoonboek.nl/zoeken/{search_term}/{city}/"
                resp = self._safe_get(url, timeout=12)
                if not resp or not resp.ok:
                    continue

                self._stats["directories_scraped"] += 1

                # HTML parsing (BeautifulSoup veya regex)
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "lxml")

                    for item in soup.select(".result-item, .listing, article, .business-card"):
                        name_el = item.select_one(".name, h2, h3, .company-name")
                        phone_el = item.select_one(".phone, .tel, .phone-number")
                        website_el = item.select_one("a[href*='http']")

                        name = name_el.get_text(strip=True) if name_el else ""
                        phone = phone_el.get_text(strip=True) if phone_el else ""
                        website = ""
                        if website_el:
                            href = website_el.get("href", "")
                            if href and "telefoonboek.nl" not in href and not href.startswith("mailto:"):
                                website = href

                        if name and len(name) > 2 and "telefoonboek" not in name.lower():
                            # Website'den email çıkarmayı dene
                            email = ""
                            if website:
                                contacts = self._extract_contacts_from_website(website)
                                email = contacts.get("email", "")
                                if not phone and contacts.get("phone"):
                                    phone = contacts["phone"]

                            if not email and website:
                                domain = urlparse(website).netloc.replace("www.", "")
                                if domain:
                                    email = f"info@{domain}"

                            if email and email not in self._found_emails and not db.lead_exists(email):
                                self._found_emails.add(email)
                                results.append({
                                    "company_name": name,
                                    "email": email.lower(),
                                    "phone": phone,
                                    "website": website,
                                    "sector": sector,
                                    "location": city.replace("-", " ").title(),
                                    "source": "telefoonboek",
                                    "score": 70,
                                    "is_good_lead": True,
                                })

                except ImportError:
                    # BS4 yoksa regex ile
                    companies = self._extract_directory_listings(resp.text, url)
                    for comp in companies:
                        if comp.get("email") and comp["email"] not in self._found_emails:
                            if not db.lead_exists(comp["email"]):
                                self._found_emails.add(comp["email"])
                                comp["source"] = "telefoonboek"
                                comp["sector"] = sector
                                comp["location"] = city.replace("-", " ").title()
                                comp["score"] = 70
                                results.append(comp)

                time.sleep(1)
            except Exception as e:
                self._stats["errors"] += 1
                log.debug(f"[TELEFOONBOEK] Hata: {city}/{sector} — {e}")

        log.info(f"[TELEFOONBOEK] {len(results)} lead bulundu")
        return results

    # ══════════════════════════════════════════════════════════════
    # PHASE 3: OpenStreetMap / Nominatim
    # ══════════════════════════════════════════════════════════════

    def _search_openstreetmap(self, sector: str, location: str) -> list[dict]:
        """OpenStreetMap Nominatim ile coğrafi iş araması."""
        results = []
        sector_nl = SECTOR_MAP_TELEFOONBOEK.get(sector, sector)

        cities = DUTCH_CITIES[:15]
        for city in cities:
            try:
                query = f"{sector_nl} {city}"
                osm_url = (f"https://nominatim.openstreetmap.org/search?"
                           f"q={quote_plus(query)}&format=json&limit=15&addressdetails=1")

                resp = self._session.get(osm_url, headers={
                    "User-Agent": "SmartMailerUltimate/1.0 (contact@fleettrackholland.nl)"
                }, timeout=10)

                if not resp.ok:
                    continue

                data = resp.json()
                for place in data:
                    name = (place.get("display_name") or "").split(",")[0].strip()
                    if not name or len(name) < 3:
                        continue

                    place_city = (place.get("address", {}).get("city") or
                                  place.get("address", {}).get("town") or city)

                    # İsimden domain tahmin et
                    clean_name = re.sub(r'[^a-z0-9]', '', name.lower())
                    if clean_name:
                        guessed_email = f"info@{clean_name}.nl"

                        if (guessed_email not in self._found_emails and
                                not db.lead_exists(guessed_email)):
                            self._found_emails.add(guessed_email)
                            results.append({
                                "company_name": name,
                                "email": guessed_email,
                                "phone": "",
                                "website": "",
                                "sector": sector,
                                "location": place_city,
                                "source": "openstreetmap",
                                "score": 45,  # Düşük — tahmin bazlı
                                "is_good_lead": True,
                                "estimated_vehicles": "",
                            })

                time.sleep(1.2)  # Nominatim rate limit: 1 req/sec
            except Exception as e:
                self._stats["errors"] += 1
                log.debug(f"[OSM] Hata: {city}/{sector} — {e}")

        log.info(f"[OSM] {len(results)} lead bulundu")
        return results

    # ══════════════════════════════════════════════════════════════
    # PHASE 4: AI BULK LEAD SEARCH
    # ══════════════════════════════════════════════════════════════

    def _ai_bulk_lead_search(self, sector: str) -> list[dict]:
        """Claude'a sektör bilgisi vererek bilinen şirketlerin listesini iste."""
        results = []
        sector_nl = {
            "transport": "transport en vrachtvervoer",
            "bouw": "bouw en constructie",
            "schoonmaak": "schoonmaak en facilitair",
            "logistiek": "logistiek en warehousing",
            "koerier": "koeriers en pakketdiensten",
            "thuiszorg": "thuiszorg en wijkverpleging",
            "taxi": "taxi en personenvervoer",
            "installatiebedrijf": "installatie en techniek",
            "catering": "catering en horeca",
            "beveiliging": "beveiliging en security",
            "groenvoorziening": "groenvoorziening en hoveniers",
            "loodgieter": "loodgieters en sanitair",
            "elektricien": "elektriciens en elektrotechniek",
        }.get(sector, sector)

        prompt = f"""Je bent een B2B sales researcher voor FleetTrack Holland (GPS fleet tracking).
Genereer een lijst van ECHTE Nederlandse bedrijven in de sector: {sector_nl}

BELANGRIJK: Geef ALLEEN echte bedrijven die daadwerkelijk bestaan in Nederland.
Voor elk bedrijf, geef:
- Bedrijfsnaam
- Vermoedelijke website (format: bedrijfsnaam.nl)
- Vermoedelijk e-mailadres (meestal info@bedrijfsnaam.nl)
- Stad
- Geschatte vlootgrootte

Geef minimaal 25 bedrijven, maximaal 50.

Antwoord ALLEEN als JSON array:
[
  {{"company_name": "...", "email": "info@...nl", "website": "www...nl", "city": "...", "estimated_vehicles": 10, "phone": ""}},
  ...
]"""

        try:
            payload = {
                "model": config.CLAUDE_MODEL,
                "max_tokens": 4000,
                "messages": [{"role": "user", "content": prompt}],
            }
            resp = requests.post(CLAUDE_API_URL, json=payload,
                                 headers=self._headers, timeout=60)
            self._stats["ai_calls"] += 1

            if not resp.ok:
                log.warning(f"[AI-BULK] API hata: {resp.status_code}")
                return results

            raw = resp.json()["content"][0]["text"]
            json_str = raw
            if "```json" in raw:
                json_str = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                json_str = raw.split("```")[1].split("```")[0]

            companies = json.loads(json_str.strip())
            if not isinstance(companies, list):
                return results

            for comp in companies:
                email = (comp.get("email") or "").strip().lower()
                if not email or not self._is_valid_email(email):
                    continue
                if email in self._found_emails or db.lead_exists(email):
                    self._stats["leads_duplicate"] += 1
                    continue

                self._found_emails.add(email)
                results.append({
                    "company_name": comp.get("company_name", ""),
                    "email": email,
                    "phone": comp.get("phone", ""),
                    "website": comp.get("website", ""),
                    "estimated_vehicles": comp.get("estimated_vehicles", ""),
                    "sector": sector,
                    "location": comp.get("city", "Nederland"),
                    "score": 55,
                    "is_good_lead": True,
                    "source": "ai_knowledge",
                    "contact_person": comp.get("contact_person", ""),
                })

            log.info(f"[AI-BULK] {len(results)} lead AI bilgi bankasından bulundu ({sector})")

        except json.JSONDecodeError:
            log.warning("[AI-BULK] JSON decode hatası")
        except Exception as e:
            self._stats["errors"] += 1
            log.error(f"[AI-BULK] Hata: {e}")

        return results

    # ══════════════════════════════════════════════════════════════
    # PHASE 5: ŞEHİR BAZLI WEB ARAMASI
    # ══════════════════════════════════════════════════════════════

    def _search_city(self, sector: str, city: str) -> list[dict]:
        results = []
        queries = SEARCH_QUERIES.get(sector, SEARCH_QUERIES["default"])
        selected_queries = random.sample(queries, min(3, len(queries)))

        for query_template in selected_queries:
            query = query_template.format(city=city)
            try:
                urls = self._search_web(query)
                self._stats["pages_scanned"] += 1

                for url in urls[:10]:
                    domain = urlparse(url).netloc.lower()
                    if domain in self._scanned_domains:
                        continue
                    self._scanned_domains.add(domain)
                    self._stats["urls_analyzed"] += 1

                    lead = self._extract_lead_from_website(url, sector, city)
                    if lead and lead.get("email"):
                        email = lead["email"]
                        if email not in self._found_emails and not db.lead_exists(email):
                            self._found_emails.add(email)
                            results.append(lead)
                            log.info(f"[CITY] ✅ {city}: {lead.get('company_name')} — {email}")

                time.sleep(0.8)
            except Exception as e:
                self._stats["errors"] += 1
                log.debug(f"[CITY] Hata: {city}/{query} — {e}")

        return results

    def _search_web(self, query: str) -> list[str]:
        all_urls = []
        all_urls.extend(self._search_bing(query))
        if len(all_urls) < 5:
            all_urls.extend(self._search_duckduckgo(query))
        if len(all_urls) < 5:
            all_urls.extend(self._search_startpage(query))

        seen = set()
        unique = []
        for url in all_urls:
            domain = urlparse(url).netloc.lower()
            if domain not in seen and not any(s in domain for s in SKIP_DOMAINS):
                seen.add(domain)
                unique.append(url)
        return unique

    def _search_bing(self, query: str) -> list[str]:
        urls = []
        try:
            self._session.headers["User-Agent"] = random.choice(USER_AGENTS)
            resp = self._session.get("https://www.bing.com/search",
                                      params={"q": query, "setlang": "nl", "count": "30"},
                                      timeout=12)
            if resp.ok:
                found = re.findall(r'<a[^>]*href="(https?://[^"]+)"[^>]*>', resp.text)
                for u in found:
                    domain = urlparse(u).netloc.lower()
                    if not any(s in domain for s in SKIP_DOMAINS):
                        urls.append(u)
        except Exception as e:
            log.debug(f"[BING] Hata: {e}")
        return urls

    def _search_duckduckgo(self, query: str) -> list[str]:
        urls = []
        try:
            self._session.headers["User-Agent"] = random.choice(USER_AGENTS)
            resp = self._session.get("https://lite.duckduckgo.com/lite/",
                                      params={"q": query}, timeout=12)
            if resp.ok:
                found = re.findall(r'href="(https?://[^"]+)"', resp.text)
                for u in found:
                    domain = urlparse(u).netloc.lower()
                    if not any(s in domain for s in SKIP_DOMAINS):
                        urls.append(u)
        except Exception as e:
            log.debug(f"[DDG] Hata: {e}")
        return urls

    def _search_startpage(self, query: str) -> list[str]:
        urls = []
        try:
            self._session.headers["User-Agent"] = random.choice(USER_AGENTS)
            resp = self._session.post("https://www.startpage.com/sp/search",
                                       data={"query": query, "cat": "web", "language": "dutch"},
                                       timeout=12)
            if resp.ok:
                found = re.findall(r'href="(https?://[^"]+)"', resp.text)
                for u in found:
                    domain = urlparse(u).netloc.lower()
                    if not any(s in domain for s in SKIP_DOMAINS):
                        urls.append(u)
        except Exception as e:
            log.debug(f"[STARTPAGE] Hata: {e}")
        return urls

    # ══════════════════════════════════════════════════════════════
    # WEBSITE'DEN LEAD ÇIKARMA
    # ══════════════════════════════════════════════════════════════

    def _extract_contacts_from_website(self, url: str) -> dict:
        """Website'den email ve telefon bilgisi çıkar (FleetTrack CRM tarzı)."""
        if not url or url == "—" or not url.startswith("http"):
            return {"email": "", "phone": ""}
        try:
            resp = self._safe_get(url, timeout=8)
            if not resp or not resp.ok:
                return {"email": "", "phone": ""}
            email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', resp.text)
            phone_match = re.search(r'(?:\+31|0)(?:\s?\d){9}', resp.text)
            return {
                "email": email_match.group(0).lower() if email_match else "",
                "phone": phone_match.group(0) if phone_match else "",
            }
        except Exception:
            return {"email": "", "phone": ""}

    def _extract_lead_from_website(self, url: str, sector: str = "",
                                    city: str = "") -> dict | None:
        try:
            resp = self._safe_get(url, timeout=10)
            if not resp or not resp.ok:
                return None

            html = resp.text
            domain = urlparse(url).netloc.lower()

            emails = self._extract_emails_from_html(html)
            if not emails:
                contact_emails = self._scrape_contact_page(url, html)
                emails.extend(contact_emails)
            if not emails:
                guessed = self._guess_email_from_domain(domain)
                if guessed:
                    emails.append(guessed)
            if not emails:
                return None

            best_email = self._pick_best_email(emails, domain)
            if not best_email:
                return None

            self._stats["emails_extracted"] += 1
            company_name = self._extract_company_name(html, domain)
            phones = re.findall(r'(?:\+31|0)\s*[\d\s.-]{8,12}', html)
            phone = phones[0].strip() if phones else ""
            vehicles = self._estimate_vehicles(html)

            return {
                "company_name": company_name,
                "email": best_email,
                "phone": phone,
                "website": url,
                "estimated_vehicles": vehicles,
                "sector": sector,
                "location": city,
                "score": 70,
                "is_good_lead": True,
                "source": "web_scrape",
                "contact_person": "",
            }
        except Exception as e:
            self._stats["errors"] += 1
            return None

    def _extract_emails_from_html(self, html: str) -> list[str]:
        emails = set()
        found = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
        emails.update(found)

        mailto = re.findall(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', html)
        emails.update(mailto)

        # HTML entity deobfuscation
        try:
            entity_pattern = re.findall(r'((?:&#\d+;){5,})', html)
            for entity in entity_pattern:
                decoded = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), entity)
                decoded_emails = re.findall(
                    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', decoded)
                emails.update(decoded_emails)
        except Exception:
            pass

        return [e.lower() for e in emails if self._is_valid_email(e)]

    def _scrape_contact_page(self, base_url: str, main_html: str) -> list[str]:
        emails = []
        parsed = urlparse(base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        contact_patterns = re.findall(
            r'href="([^"]*(?:contact|over-ons|about|impressum|bedrijf)[^"]*)"',
            main_html, re.IGNORECASE
        )
        common_paths = ["/contact", "/contact/", "/over-ons", "/over-ons/"]

        all_urls = []
        for path in contact_patterns[:3]:
            if path.startswith("http"):
                all_urls.append(path)
            elif path.startswith("/"):
                all_urls.append(f"{base}{path}")
        for path in common_paths[:2]:
            all_urls.append(f"{base}{path}")

        seen = set()
        for contact_url in all_urls:
            if contact_url in seen:
                continue
            seen.add(contact_url)
            try:
                resp = self._safe_get(contact_url, timeout=8)
                if resp and resp.ok:
                    contact_emails = self._extract_emails_from_html(resp.text)
                    emails.extend(contact_emails)
                    self._stats["pages_scanned"] += 1
            except Exception:
                pass
        return emails

    def _guess_email_from_domain(self, domain: str) -> str | None:
        clean_domain = domain.replace("www.", "")
        if not clean_domain or "." not in clean_domain:
            return None
        for prefix in ["info", "contact"]:
            email = f"{prefix}@{clean_domain}"
            if self._is_valid_email(email):
                return email
        return None

    # ══════════════════════════════════════════════════════════════
    # DIRECTORY HTML EXTRACTION
    # ══════════════════════════════════════════════════════════════

    def _extract_directory_listings(self, html: str, base_url: str) -> list[dict]:
        results = []
        emails = set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html))
        phones = re.findall(r'(?:\+31|0)\s*(?:[\d][\s.-]*){8,9}', html)
        website_links = re.findall(r'href="(https?://(?:www\.)?[a-zA-Z0-9.-]+\.nl[^"]*)"', html)

        for email in emails:
            if not self._is_valid_email(email):
                continue
            domain = email.split("@")[-1]
            company_name = domain.split(".")[0].replace("-", " ").title()
            phone = phones[0] if phones else ""

            results.append({
                "email": email.lower(),
                "company_name": company_name,
                "phone": phone.strip() if phone else "",
                "website": f"https://www.{domain}" if "." in domain else "",
                "is_good_lead": True,
            })
        return results

    # ══════════════════════════════════════════════════════════════
    # MX DOĞRULAMA
    # ══════════════════════════════════════════════════════════════

    def _verify_mx(self, email: str) -> bool:
        """Email domain'inin MX kaydı var mı kontrol et."""
        domain = email.split("@")[-1].lower()
        if domain in self._mx_cache:
            return self._mx_cache[domain]

        try:
            import dns.resolver
            answers = dns.resolver.resolve(domain, 'MX')
            has_mx = len(answers) > 0
            self._mx_cache[domain] = has_mx
            return has_mx
        except ImportError:
            try:
                socket.getaddrinfo(domain, 25)
                self._mx_cache[domain] = True
                return True
            except Exception:
                self._mx_cache[domain] = False
                return False
        except Exception:
            self._mx_cache[domain] = False
            return False

    # ══════════════════════════════════════════════════════════════
    # AI DOĞRULAMA
    # ══════════════════════════════════════════════════════════════

    def _batch_validate_with_ai(self, leads: list[dict]):
        batch = leads[:20]
        companies_text = "\n".join([
            f"- {l.get('company_name', '?')}: {l.get('email', '?')} ({l.get('website', '?')})"
            for l in batch
        ])

        prompt = f"""Deze bedrijven zijn gevonden als potentiële leads voor GPS fleet tracking (FleetTrack Holland).
Beoordeel elk bedrijf kort: hebben ze waarschijnlijk voertuigen? Score 1-100.

{companies_text}

Antwoord als JSON array:
[{{"email": "...", "score": 75, "estimated_vehicles": "10"}}]"""

        try:
            payload = {"model": config.CLAUDE_MODEL, "max_tokens": 2000,
                       "messages": [{"role": "user", "content": prompt}]}
            resp = requests.post(CLAUDE_API_URL, json=payload,
                                 headers=self._headers, timeout=30)
            self._stats["ai_calls"] += 1

            if resp.ok:
                raw = resp.json()["content"][0]["text"]
                json_str = raw
                if "```json" in raw:
                    json_str = raw.split("```json")[1].split("```")[0]
                elif "```" in raw:
                    json_str = raw.split("```")[1].split("```")[0]

                validations = json.loads(json_str.strip())
                if isinstance(validations, list):
                    v_map = {v.get("email", ""): v for v in validations}
                    for lead in batch:
                        email = lead.get("email", "")
                        if email in v_map:
                            lead["score"] = v_map[email].get("score", lead.get("score", 60))
                            if v_map[email].get("estimated_vehicles"):
                                lead["estimated_vehicles"] = str(v_map[email]["estimated_vehicles"])
        except Exception as e:
            log.debug(f"[AI-VALIDATE] Hata: {e}")

    # ══════════════════════════════════════════════════════════════
    # YARDIMCI METODLAR
    # ══════════════════════════════════════════════════════════════

    def _safe_get(self, url: str, timeout: int = 10) -> requests.Response | None:
        try:
            self._session.headers["User-Agent"] = random.choice(USER_AGENTS)
            return self._session.get(url, timeout=timeout, allow_redirects=True)
        except Exception:
            return None

    def _pick_best_email(self, emails: list[str], domain: str = "") -> str | None:
        if not emails:
            return None
        priority = ["info@", "contact@", "sales@", "verkoop@", "office@",
                     "mail@", "hello@", "hallo@", "service@", "admin@",
                     "directie@", "management@"]

        domain_emails = [e for e in emails if domain.replace("www.", "") in e]
        other_emails = [e for e in emails if e not in domain_emails]

        for candidates in [domain_emails, other_emails]:
            for prefix in priority:
                for email in candidates:
                    if email.startswith(prefix):
                        return email
        return domain_emails[0] if domain_emails else (emails[0] if emails else None)

    def _extract_company_name(self, html: str, domain: str) -> str:
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html,
                                flags=re.DOTALL | re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()
            title = re.split(r'\s*[|–—-]\s*', title)[0].strip()
            if 3 < len(title) < 80:
                return title

        og_match = re.search(
            r'<meta[^>]*property=["\']og:(?:site_name|title)["\'][^>]*content=["\']([^"\']+)["\']',
            html, re.IGNORECASE)
        if og_match:
            return og_match.group(1).strip()

        clean = domain.replace("www.", "").split(".")[0]
        return clean.replace("-", " ").title()

    def _estimate_vehicles(self, html: str) -> str:
        patterns = [
            r'(\d+)\s*(?:voertuigen|vrachtwagens|bestelwagens|busjes|auto\'?s)',
            r'(?:vloot|wagenpark|fleet)\s*(?:van|met|of)?\s*(\d+)',
            r'(\d+)\s*(?:trucks|vans|vehicles)',
        ]
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                num = int(match.group(1))
                if 1 <= num <= 1000:
                    return str(num)
        return ""

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        if not email or "@" not in email:
            return False
        email = email.lower().strip()
        if len(email) < 5 or len(email) > 100:
            return False
        if any(inv in email for inv in INVALID_EMAIL_PARTS):
            return False
        domain = email.split("@")[-1]
        valid_tlds = [".nl", ".com", ".eu", ".be", ".de", ".org", ".net", ".co", ".io"]
        if not any(domain.endswith(tld) for tld in valid_tlds):
            return False
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return False
        return True
