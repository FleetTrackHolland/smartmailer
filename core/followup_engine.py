"""
core/followup_engine.py — Follow-Up Sequence Engine (v5)
Gönderilen e-postalara otomatik takip zinciri — gelişmiş pazarlama.
3 aşama: Gün 3 (social proof + merak), Gün 7 (ROI + vaka çalışması), Gün 14 (urgency + FOMO).
Her aşama benzersiz pazarlama stratejileri kullanır ve önceki maillere atıfta bulunur.
"""
import json
import requests
from datetime import datetime, timedelta
from config import config
from core.logger import get_logger
from core.database import db
from core.api_guard import api_guard

log = get_logger("followup")

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"


# ═══════════════════════════════════════════════════════════════
# FOLLOW-UP PROMPT'LARI — Her aşama benzersiz pazarlama stratejisi
# ═══════════════════════════════════════════════════════════════

FOLLOWUP_PROMPTS = {
    # ─── STEP 1 (Gün 3): SOCIAL PROOF + CURIOSITY GAP ─────────
    1: """Je bent een elite B2B sales copywriter bij FleetTrack Holland (GPS fleet tracking systemen).
Je hebt {days_ago} dagen geleden een eerste e-mail gestuurd. Er is GEEN reactie gekomen.

=== CONTEXT ===
ORIGINEEL ONDERWERP: {original_subject}
BEDRIJF: {company}
SECTOR: {sector}
GESCHATTE VLOOT: {vehicles} voertuigen
{previous_emails_context}

=== STRATEGIE: SOCIAL PROOF + CURIOSITY GAP ===
Schrijf een follow-up die deze technieken gebruikt:

1. **Social Proof**: Noem dat vergelijkbare bedrijven in hun sector (zonder namen te noemen) 
   al GPS tracking gebruiken en resultaten boeken
2. **Curiosity Gap**: Stel een intrigerende vraag die ze niet kunnen negeren, bijv.
   "Wist u dat {sector}-bedrijven gemiddeld €X per voertuig per maand besparen?"
3. **Referentie**: Verwijs KORT naar je eerdere e-mail ("In mijn vorige bericht noemde ik...")
4. **Micro-commitment**: Vraag iets kleins — "Mag ik u 1 ding vragen?" of "Bent u benieuwd naar de resultaten?"

REGELS:
- Max 120 woorden, in het Nederlands
- Begin NIET met "Ik stuur deze e-mail op..." of "Beste heer/mevrouw"
- Begin met een pakkende openingszin die nieuwsgierigheid wekt
- Gebruik de naam van het bedrijf
- Eindig met een laagdrempelige vraag (geen "Zullen we bellen?")
- Voeg een P.S. toe met een verrassend feit of statistiek
- HTML opmaak: gebruik <p>, <strong>, <em> tags

Antwoord ALLEEN in geldig JSON:
{{"subject": "...", "body_html": "<p>...</p>", "body_text": "..."}}
""",

    # ─── STEP 2 (Gün 7): VALUE-ADD + ROI CASE STUDY ───────────
    2: """Je bent een elite B2B sales copywriter bij FleetTrack Holland (GPS fleet tracking systemen).
Dit is je TWEEDE follow-up. De eerste e-mail ({days_since_original} dagen geleden) en de eerste follow-up zijn onbeantwoord.

=== CONTEXT ===
ORIGINEEL ONDERWERP: {original_subject}
BEDRIJF: {company}
SECTOR: {sector}
GESCHATTE VLOOT: {vehicles} voertuigen
{previous_emails_context}

=== STRATEGIE: VALUE-ADD + ROI BEREKENING ===
Deze e-mail moet WAARDE bieden, geen verkooppraatje zijn. Gebruik:

1. **Mini Case Study**: Vertel een kort succesverhaal van een soortgelijk bedrijf:
   - "Een {sector}-bedrijf met {vehicles_similar} voertuigen bespaarde €X/maand"
   - Noem concrete cijfers: brandstofbesparing, ritoptimalisatie, gestolen voertuig teruggevonden
2. **Persoonlijke ROI**: Bereken specifiek voor HUN bedrijf:
   - "Met {vehicles} voertuigen zou dat voor {company} neerkomen op circa €X per jaar"
3. **Autoriteit**: Noem een relevante branchetrend of statistiek
4. **Referentie**: Verwijs naar je eerdere berichten ("Ik heb u eerder geschreven over...")
5. **Reciprociteit**: Bied iets GRATIS aan — een rapport, een vloot-scan, of een demonstratie

REGELS:
- Max 170 woorden, in het Nederlands
- Structureer met korte alinea's (max 2-3 zinnen per alinea)
- Gebruik bulletpoints voor de voordelen
- Maak de CTA specifiek: "Zal ik de berekening voor {company} doorsturen?"
- HTML: gebruik <p>, <strong>, <ul><li>, <em> tags
- Toon: Behulpzaam, als een adviseur, NIET als een verkoper

Antwoord ALLEEN in geldig JSON:
{{"subject": "...", "body_html": "<p>...</p>", "body_text": "..."}}
""",

    # ─── STEP 3 (Gün 14): URGENCY + FOMO + GRACEFUL CLOSE ─────
    3: """Je bent een elite B2B sales copywriter bij FleetTrack Holland (GPS fleet tracking systemen).
Dit is je DERDE en LAATSTE follow-up. Alle eerdere berichten ({days_since_original} dagen geleden begonnen) zijn onbeantwoord.

=== CONTEXT ===
ORIGINEEL ONDERWERP: {original_subject}
BEDRIJF: {company}
SECTOR: {sector}
GESCHATTE VLOOT: {vehicles} voertuigen
{previous_emails_context}

=== STRATEGIE: SCARCITY + FOMO + ELEGANTE AFSLUITING ===
Dit is de LAATSTE kans. Combineer meerdere overtuigingstechnieken:

1. **Door-in-the-face**: Begin met een statement dat dit je laatste bericht is — dit verhoogt paradoxaal de kans op actie
2. **FOMO (Fear of Missing Out)**: "Uw concurrenten in de {sector} investeren al in vlootoptimalisatie"
3. **Loss Aversion**: Focus op wat ze VERLIEZEN, niet wat ze winnen:
   - "Elke dag zonder tracking kost {company} circa €X aan onnodige kosten"
4. **Tijdsdruk**: Noem een concreet beperkt aanbod:
   - "Tot eind deze maand bieden wij een gratis vloot-analyse aan"
5. **Referentie**: Vat kort samen wat je eerder hebt aangeboden
6. **Respectvolle afsluiting**: Laat de deur open
   - "Mocht dit momenteel geen prioriteit zijn, begrijp ik dat volledig"
7. **P.S. met urgentie**: De P.S. is het meest gelezen deel — gebruik dit!

REGELS:
- Max 140 woorden, in het Nederlands
- Toon: Professioneel, respectvol, maar met onderliggende urgentie
- Gebruik contrast: "andere bedrijven doen X, terwijl..."
- Eindig met een duidelijke keuze: "Antwoord met 'ja' voor de gratis analyse, of 'nee' als dit niet relevant is"
- HTML: gebruik <p>, <strong>, <em> tags
- Voeg een P.S. toe die de belangrijkste urgentie bevat

Antwoord ALLEEN in geldig JSON:
{{"subject": "...", "body_html": "<p>...</p>", "body_text": "..."}}
""",
}


class FollowUpEngine:
    """3-aşamalı otomatik follow-up zinciri — gelişmiş pazarlama stratejileri."""

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

    # ─── ÖNCEKİ E-POSTALARI TOPLA (REFERANS İÇİN) ─────────────

    def _get_previous_emails_context(self, email: str, current_step: int) -> str:
        """Önceki e-postaların özetini döner — AI'ın atıfta bulunması için."""
        context_parts = []

        # Orijinal gönderilen e-postayı al
        try:
            sent = db.get_sent_email_content(email)
            if sent and sent.get("subject"):
                context_parts.append(
                    f"--- ILKE-MAIL (orijineel) ---\n"
                    f"Onderwerp: {sent.get('subject', '')}\n"
                    f"Verzonden op: {sent.get('sent_at', 'onbekend')}\n"
                    f"Samenvatting: E-mail over GPS tracking oplossingen voor hun vloot."
                )
        except Exception:
            pass

        # Önceki follow-up'ları al
        try:
            all_followups = db.get_followups_for_email(email)
            for fu in all_followups:
                if fu.get("step", 0) < current_step and fu.get("status") == "sent":
                    fu_subject = fu.get("subject", "")
                    fu_body = fu.get("body_text", "") or ""
                    # Sadece ilk 100 karakter
                    summary = fu_body[:150].replace("\n", " ").strip()
                    context_parts.append(
                        f"--- FOLLOW-UP {fu['step']} ---\n"
                        f"Onderwerp: {fu_subject}\n"
                        f"Samenvatting: {summary}..."
                    )
        except Exception:
            pass

        if context_parts:
            return "\n\nEERDER VERZONDEN E-MAILS (verwijs hier subtiel naar):\n" + "\n\n".join(context_parts)
        return "\n\n(Dit is de eerste follow-up, verwijs naar je originele e-mail.)"

    # ─── BEKLEYEN FOLLOW-UP'LARI İŞLE VE GÖNDER ────────────────

    def process_pending(self) -> list[dict]:
        """Zamanı gelen follow-up'ları üret, Brevo ile gönder ve DB güncelle."""
        from core.send_engine import SendEngine

        pending = db.get_pending_followups()
        results = []
        sender = SendEngine()

        log.info(f"[FOLLOWUP] {len(pending)} bekleyen follow-up işleniyor...")

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
                log.info(f"[FOLLOWUP] Atlandı (unsub): {email} step {step}")
                continue

            # E-posta açılmış ama yanıt yok → daha agresif follow-up
            has_opened = db.has_opened(email)

            try:
                # 1. AI ile follow-up e-postası üret
                draft = self._generate_followup(
                    email=email,
                    step=step,
                    original_subject=fu.get("original_subject", ""),
                    company=fu.get("company", ""),
                    sector=fu.get("sector", ""),
                    vehicles=fu.get("vehicles", ""),
                    has_opened=has_opened,
                )

                # 2. Brevo ile gönder
                from core.send_engine import EmailMessage
                msg = EmailMessage(
                    to_email=email,
                    to_name=fu.get("company", ""),
                    subject=draft["subject"],
                    html_body=draft["body_html"],
                    text_body=draft.get("body_text", ""),
                )
                send_result = sender.send(msg)

                if send_result.success:
                    # 3. DB güncelle — sent olarak işaretle
                    db.update_followup_status(
                        fu["id"], "sent",
                        subject=draft["subject"],
                        body_html=draft["body_html"],
                        body_text=draft.get("body_text", ""),
                    )
                    # 4. Sent log'a kaydet (follow-up olarak)
                    db.log_sent(
                        email=email,
                        company=fu.get("company", ""),
                        sector=fu.get("sector", ""),
                        subject=draft["subject"],
                        method=f"followup_step_{step}",
                        message_id=send_result.message_id or "",
                    )
                    log.info(f"[FOLLOWUP] ✅ Gönderildi: {email} step {step} — {draft['subject']}")
                    results.append({
                        "id": fu["id"],
                        "email": email,
                        "step": step,
                        "subject": draft["subject"],
                        "status": "sent",
                        "has_opened": has_opened,
                    })
                else:
                    error_msg = send_result.error or "Bilinmeyen hata"
                    log.error(f"[FOLLOWUP] ❌ Gönderilemedi: {email} — {error_msg}")
                    db.update_followup_status(fu["id"], "error")
                    results.append({
                        "id": fu["id"],
                        "email": email,
                        "step": step,
                        "status": "error",
                        "error": error_msg,
                    })

            except Exception as e:
                log.error(f"[FOLLOWUP] Üretim/gönderim hatası: {email} step {step} — {e}")
                db.update_followup_status(fu["id"], "error")

        log.info(f"[FOLLOWUP] İşlem tamamlandı: {len(results)} follow-up işlendi")
        return results

    # ─── AI FOLLOW-UP ÜRETİCİ (GELİŞMİŞ) ─────────────────────

    def _generate_followup(self, email: str, step: int, original_subject: str,
                           company: str, sector: str, vehicles: str,
                           has_opened: bool = False) -> dict:
        """Claude ile gelişmiş follow-up e-postası üret — önceki maillere atıfta bulunur."""

        # Önceki e-posta bağlamını al
        previous_context = self._get_previous_emails_context(email, step)

        # Gün hesapla
        days_map = {1: config.FOLLOWUP_DAY_1, 2: config.FOLLOWUP_DAY_2, 3: config.FOLLOWUP_DAY_3}
        days_ago = days_map.get(step, 3)
        days_since_original = days_ago

        # Benzer vloot büyüklüğü hesapla (case study için)
        try:
            veh_count = int(vehicles) if vehicles and str(vehicles).isdigit() else 30
        except (ValueError, TypeError):
            veh_count = 30
        vehicles_similar = max(10, veh_count + (-10 if veh_count > 30 else 5))

        prompt_template = FOLLOWUP_PROMPTS.get(step, FOLLOWUP_PROMPTS[1])
        user_prompt = prompt_template.format(
            original_subject=original_subject or "GPS tracking voor uw vloot",
            company=company or "uw bedrijf",
            sector=sector or "zakelijke dienstverlening",
            vehicles=vehicles or "meerdere",
            days_ago=days_ago,
            days_since_original=days_since_original,
            vehicles_similar=vehicles_similar,
            previous_emails_context=previous_context,
        )

        # E-posta açılmış ama yanıt yok — ekstra bilgi ekle
        if has_opened:
            user_prompt += (
                "\n\n🔔 BELANGRIJK: Deze persoon heeft je eerdere e-mail GEOPEND maar NIET gereageerd. "
                "Dit betekent dat er INTERESSE is. Verwijs hier subtiel naar, bijvoorbeeld: "
                "'Ik zag dat u mijn vorige bericht heeft bekeken...' of "
                "'Ik begrijp dat het druk is, maar uw interesse geeft aan dat...'"
            )

        payload = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": 800,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        resp = api_guard.call(payload, self._headers, timeout=30)
        if not resp or not resp.ok:
            raise Exception(f"Claude follow-up hatası: {resp.status_code if resp else 'guard blocked'}")

        raw = resp.json()["content"][0]["text"]

        json_str = raw
        if "```json" in raw:
            json_str = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            json_str = raw.split("```")[1].split("```")[0]

        result = json.loads(json_str.strip())

        # Unsubscribe footer ekle (her follow-up'a)
        unsub_url = config.UNSUBSCRIBE_URL
        footer_html = (
            f'<br><hr style="border:none;border-top:1px solid #eee;margin:20px 0">'
            f'<p style="font-size:11px;color:#999;line-height:1.4">'
            f'{config.COMPANY_NAME}<br>'
            f'<a href="{unsub_url}" style="color:#999">Uitschrijven</a></p>'
        )
        result["body_html"] = result.get("body_html", "") + footer_html

        return result

    # ─── İSTATİSTİKLER ─────────────────────────────────────────

    def get_stats(self) -> dict:
        """Follow-up istatistikleri."""
        return db.get_followup_stats()

    def ping(self) -> bool:
        return True
