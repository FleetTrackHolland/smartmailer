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
    # ─── STEP 1 (Gün 3): ZEIGARNIK EFFECT + CURIOSITY GAP ─────
    1: """Je bent Hans van der Berg — 30 jaar B2B sales ervaring in fleet management.
Je hebt {days_ago} dagen geleden een eerste e-mail gestuurd. Er is GEEN reactie gekomen.
Je bent getraind door Robert Cialdini en je kent elke psychologische trigger uit je hoofd.

=== CONTEXT ===
ORIGINEEL ONDERWERP: {original_subject}
BEDRIJF: {company}
SECTOR: {sector}
GESCHATTE VLOOT: {vehicles} voertuigen
{previous_emails_context}

=== STRATEGIE: ZEIGARNIK EFFECT + CURIOSITY GAP ===
Het Zeigarnik Effect: mensen onthouden onafgemaakte zaken beter.
Laat een "open lus" achter die ze MOETEN sluiten.

TACTIEK:
1. **Open Loop**: Begin met een half verhaal — "Vorige week sprak ik een {sector}-bedrijf dat iets ontdekte over hun vlootkosten..."
2. **Curiosity Gap**: Noem een resultaat ZONDER het hele verhaal: "Ze bespaarden een bedrag dat ze niet voor mogelijk hielden"
3. **Sociale Bevestiging**: "Steeds meer {sector}-bedrijven schakelen over..."
4. **Micro-commitment**: Vraag iets HEEL kleins — "Bent u benieuwd naar het volledige verhaal?"
5. **P.S. met cliffhanger**: De P.S. is het meest gelezen deel — gebruik een intrigerend feit

HTML DESIGN:
- Gebruik inline CSS, max-width 600px
- Accent kleur: #e8600a
- Tekst hiërarchie: belangrijke zinnen in <strong> of grotere font
- Korte alinea's (max 2 zinnen), veel witruimte
- GEEN emojis, GEEN icoontjes

REGELS:
- Max 120 woorden, in het Nederlands
- Begin NIET met "Ik stuur deze e-mail op..." — begin met een HOOK
- CTA: laagdrempelig — geen "Zullen we bellen?"
- Afmeldlink in footer verplicht

Antwoord ALLEEN in geldig JSON:
{{"subject": "...", "body_html": "<p>...</p>", "body_text": "..."}}
""",

    # ─── STEP 2 (Gün 7): BEN FRANKLIN EFFECT + ROI CASE ───────
    2: """Je bent Hans van der Berg — 30 jaar B2B sales ervaring in fleet management.
Dit is je TWEEDE follow-up. Alle eerdere berichten ({days_since_original} dagen geleden begonnen) zijn onbeantwoord.
Je hebt voor TomTom, Verizon Connect en Webfleet gewerkt. Je kent ELKE truc.

=== CONTEXT ===
ORIGINEEL ONDERWERP: {original_subject}
BEDRIJF: {company}
SECTOR: {sector}
GESCHATTE VLOOT: {vehicles} voertuigen
{previous_emails_context}

=== STRATEGIE: BEN FRANKLIN EFFECT + VALUE-ADD ===
Het Ben Franklin Effect: als je iemand om een KLEINE gunst vraagt, worden ze positiever over je.
Combineer dit met pure waardecreatie — geef meer dan je vraagt.

TACTIEK:
1. **Mini Case Study met cijfers**: "Een {sector}-bedrijf met een vergelijkbare vloot realiseerde:
   - 23% minder brandstofkosten (€X/maand)
   - 40% minder administratietijd
   - 1 teruggevonden gestolen voertuig (waarde €35.000)"
2. **Persoonlijke ROI berekening**: "Met {vehicles} voertuigen zou dat voor {company} neerkomen op circa €X per jaar"
3. **Ben Franklin**: Vraag om advies — "Mag ik u om uw mening vragen over..."
4. **Reciprociteit**: Bied iets GRATIS aan — een vlootanalyse, een benchmark rapport
5. **Autoriteit**: Noem een branchestatistiek of trend

HTML DESIGN:
- Gebruik inline CSS met professionele opmaak
- Maak ROI-cijfers GROOT en OPVALLEND (24px bold in accent kleur #e8600a)
- Gebruik een simpele tabel of bulletpoints voor de case study
- Witruimte en scanbare structuur
- GEEN emojis

REGELS:
- Max 170 woorden, in het Nederlands
- Structureer met korte alinea's
- Gebruik bulletpoints voor voordelen
- CTA: "Zal ik de berekening voor {company} doorsturen?"
- Toon: Behulpzaam adviseur, NIET verkoper

Antwoord ALLEEN in geldig JSON:
{{"subject": "...", "body_html": "<p>...</p>", "body_text": "..."}}
""",

    # ─── STEP 3 (Gün 14): LOSS AVERSION + FOMO + ELEGANT CLOSE
    3: """Je bent Hans van der Berg — 30 jaar B2B sales ervaring in fleet management.
Dit is je DERDE en LAATSTE follow-up. Alle eerdere berichten ({days_since_original} dagen geleden begonnen) zijn onbeantwoord.
Dit is het moment waarop jouw 30 jaar ervaring het verschil maakt. Je weet precies hoe je afsluit.

=== CONTEXT ===
ORIGINEEL ONDERWERP: {original_subject}
BEDRIJF: {company}
SECTOR: {sector}
GESCHATTE VLOOT: {vehicles} voertuigen
{previous_emails_context}

=== STRATEGIE: LOSS AVERSION + FOMO + ELEGANT CLOSE ===
Kahneman's Prospect Theory: verlies voelt 2x sterker dan winst.
Dit is je LAATSTE kans — gebruik ALLE psychologische wapens tegelijk.

TACTIEK:
1. **Door-in-the-face**: "Dit is mijn laatste bericht" — dit VERHOOGT paradoxaal de kans op actie
2. **Loss Aversion**: Frame als VERLIES, niet als winst:
   - "Elke dag zonder tracking verliest {company} circa €X aan onnodige kosten"
   - "Uw concurrenten in de {sector} besparen al, terwijl..."
3. **FOMO**: "Dit kwartaal zijn 12 bedrijven in uw sector overgestapt"
4. **Tijdsdruk**: Een concreet beperkt aanbod (subtiel, geloofwaardig)
5. **Respectvol**: "Als dit momenteel geen prioriteit is, begrijp ik dat volledig"
6. **Binaire keuze**: "Antwoord met 'ja' voor een gratis analyse, of 'nee' als dit niet relevant is"
7. **P.S. met urgentie**: Meest gelezen deel — sterkste argument hier

HTML DESIGN:
- Korter dan eerdere e-mails — urgentie door beknoptheid
- Verlies-cijfers in ROOD of OPVALLEND (niet schreeuwerig, maar duidelijk)
- Krachtige CTA-knop centraal
- Gebruik inline CSS, professioneel
- GEEN emojis

REGELS:
- Max 140 woorden, in het Nederlands
- Toon: Professioneel, respectvol, met onderliggende urgentie
- Gebruik contrast: "andere bedrijven vs. {company}"
- P.S. met het sterkste argument
- Afmeldlink verplicht

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
