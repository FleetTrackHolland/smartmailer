"""agents/orchestrator.py — Ana Yönetim Ajanı (v4 — Maximum Performance)
SQLite persistence, AI lead scoring, A/B test, AI QC (≥90),
follow-up sequences, response tracking, parallel pipeline.
Tüm diğer ajanları koordine eder.
"""
import csv
import os
import time
import random
from datetime import datetime
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import config
from core.logger import get_logger
from core.database import db
from core.send_engine import SendEngine, EmailMessage
from core.ab_test_engine import ABTestEngine
from core.followup_engine import FollowUpEngine
from agents.copywriter_agent import CopywriterAgent
from agents.quality_agent import QualityAgent
from agents.compliance_agent import ComplianceAgent
from agents.watchdog_agent import WatchdogAgent
from agents.lead_scorer import LeadScorer
from agents.response_tracker import ResponseTracker
from agents.lead_finder import LeadFinder

log = get_logger("orchestrator")


@dataclass
class CampaignStats:
    total_leads: int = 0
    processed: int = 0
    sent: int = 0
    skipped_compliance: int = 0
    skipped_quality: int = 0
    failed: int = 0
    already_sent: int = 0


class Orchestrator:

    def __init__(self):
        self.copywriter     = CopywriterAgent()
        self.quality        = QualityAgent()
        self.compliance     = ComplianceAgent()
        self.send_engine    = SendEngine()
        self.lead_scorer    = LeadScorer()
        self.ab_test        = ABTestEngine(test_size=12)
        self.followup       = FollowUpEngine()
        self.response_tracker = ResponseTracker()
        self.lead_finder    = LeadFinder()
        self.watchdog       = WatchdogAgent(
            agents={
                "copywriter":    self.copywriter,
                "quality":       self.quality,
                "compliance":    self.compliance,
                "lead_scorer":   self.lead_scorer,
                "followup":      self.followup,
                "response_tracker": self.response_tracker,
                "lead_finder":   self.lead_finder,
            },
            config=config,
        )
        log.info("Orchestrator v4 hazir (QC>=90 + Follow-Up + Response Tracking + Parallel).")

    # ─────────────────────────────────────────────────────────────
    # ANA KAMPANYA METODU
    # ─────────────────────────────────────────────────────────────

    def run_campaign(self, leads_file: str = None, max_send: int = None):
        """
        Kampanya yürütür. Lead'ler SQLite'dan veya CSV'den yüklenir.
        AI lead scoring ile önceliklendirilir.
        """
        limit = max_send or config.DAILY_SEND_LIMIT
        stats = CampaignStats()
        campaign_id = f"ft-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        # Watchdog başlat
        self.watchdog.start()

        # 1. Leads yükle (CSV varsa önce import et)
        if leads_file and os.path.exists(leads_file):
            db.import_leads_from_csv(leads_file)

        # 2. AI Lead Scoring
        all_leads = db.get_all_leads()
        if all_leads:
            log.info(f"🔮 {len(all_leads)} lead AI ile puanlanıyor...")
            scores = self.lead_scorer.score_batch(all_leads)
            for score_data in scores:
                db.update_lead_ai_score(
                    email=score_data["email"],
                    score=score_data.get("score", 50),
                    reason=score_data.get("reason", ""),
                )

        # 3. Öncelikli leads al (AI skoru sırasıyla)
        leads = db.get_unsent_leads(limit=limit * 2)
        stats.total_leads = len(leads)

        # Kampanya kaydı
        db.create_campaign(campaign_id, stats.total_leads, config.TEST_MODE)

        log.info(f"Kampanya başladı: {stats.total_leads} lead | "
                 f"Limit: {limit} | Test: {config.TEST_MODE} | "
                 f"ID: {campaign_id}")

        if config.TEST_MODE:
            log.info("[TEST MODU] Gerçek mail gönderilmeyecek.")

        for lead in leads:
            if stats.sent >= limit:
                log.info(f"Günlük limit ({limit}) doldu — kampanya durdu.")
                break

            if self.watchdog.should_stop_campaign:
                log.error("[WATCHDOG] Bounce rate kritik — kampanya durduruldu!")
                break

            stats.processed += 1
            self._process_lead(lead, stats, campaign_id)

            # Kampanya stats güncelle
            db.update_campaign_stats(campaign_id,
                processed=stats.processed, sent=stats.sent,
                skipped_compliance=stats.skipped_compliance,
                skipped_quality=stats.skipped_quality,
                failed=stats.failed)

            # Gönderimler arası bekleme
            if stats.sent > 0 and not config.TEST_MODE:
                wait = random.randint(config.DELAY_MIN, config.DELAY_MAX)
                log.debug(f"Bekleniyor: {wait} saniye...")
                time.sleep(wait)

        # Kampanya sonu
        self.watchdog.stop()
        db.update_campaign_stats(campaign_id, status="completed")

        # A/B test kazanan kontrolü
        variant_stats = db.get_open_rates_by_variant()
        if variant_stats:
            self.ab_test.determine_winner(variant_stats)

        self._print_summary(stats)
        return stats

    # ─────────────────────────────────────────────────────────────
    # TEK LEAD PIPELINE
    # ─────────────────────────────────────────────────────────────

    def _process_lead(self, lead: dict, stats: CampaignStats,
                      campaign_id: str):
        company = lead.get("company") or lead.get("Company") or "?"
        email   = (lead.get("email") or lead.get("Email") or "").strip()

        if not email:
            log.warning(f"[SKIP] Email yok: {company}")
            stats.skipped_compliance += 1
            return

        # 1. AVG / Uyum kontrolü
        ok, reason = self.compliance.is_ok_to_send(email)
        if not ok:
            log.info(f"[COMPLIANCE] Atlandı: {email} — {reason}")
            stats.skipped_compliance += 1
            return

        # 2. AI ile mail üret
        try:
            draft = self.copywriter.write(lead)
        except Exception as e:
            log.error(f"[COPYWRITER] Hata: {company} — {e}")
            stats.failed += 1
            return

        # 3. AI Kalite kontrolü (≥90 zorunlu, max 5 deneme)
        qc = self.quality.check(
            subject=draft.chosen_subject,
            body_text=draft.body_text,
            company_name=company,
            body_html=draft.body_html,
        )

        # QC auto-fix loop (< QC_MIN_SCORE ise yeniden yaz)
        retries = 0
        max_retries = config.QC_MAX_RETRIES  # default 5
        min_score = config.QC_MIN_SCORE      # default 90
        while qc.score < min_score and retries < max_retries:
            retries += 1
            log.info(f"[AUTO-FIX] Deneme {retries}/{max_retries} — {company} "
                     f"(skor: {qc.score}/{min_score})")
            try:
                all_issues = qc.issues + qc.warnings
                if qc.feedback:
                    all_issues.append(f"AI FEEDBACK: {qc.feedback}")
                all_issues.append(f"Minimum skor: {min_score}. Mevcut skor: {qc.score}")
                draft = self.copywriter.rewrite(draft, all_issues)
                qc = self.quality.check(
                    subject=draft.chosen_subject,
                    body_text=draft.body_text,
                    company_name=company,
                    body_html=draft.body_html,
                )
            except Exception as e:
                log.error(f"[AUTO-FIX] Hata: {e}")
                break

        if qc.score < min_score:
            log.warning(f"[QC FAIL] {company} — Skor: {qc.score}/{min_score} "
                        f"({retries} deneme sonrası) | {qc.issues}")
            stats.skipped_quality += 1
            # Yine de taslağı kaydet (düzenleme için)
            db.save_draft(email, {
                "subject_a": draft.subject_a,
                "subject_b": draft.subject_b,
                "subject_c": draft.subject_c,
                "chosen_subject": draft.chosen_subject,
                "body_html": draft.body_html,
                "body_text": draft.body_text,
                "qc_score": qc.score,
                "qc_passed": False,
                "qc_issues": qc.issues,
                "qc_method": qc.method,
                "auto_fix_retries": retries,
            })
            return

        # 4. A/B Test — konu seçimi
        variant, chosen_subject = self.ab_test.select_variant(
            draft.subject_a, draft.subject_b, draft.subject_c
        )
        draft.chosen_subject = chosen_subject

        # Taslağı SQLite'a kaydet
        db.save_draft(email, {
            "subject_a": draft.subject_a,
            "subject_b": draft.subject_b,
            "subject_c": draft.subject_c,
            "chosen_subject": chosen_subject,
            "body_html": draft.body_html,
            "body_text": draft.body_text,
            "qc_score": qc.score,
            "qc_passed": True,
            "qc_issues": qc.issues,
            "qc_method": qc.method,
            "auto_fix_retries": retries,
            "ab_variant": variant,
        })

        # 5. İnsan onayı modu
        if config.HUMAN_REVIEW:
            approved = self._human_review(lead, draft)
            if not approved:
                log.info(f"[REVIEW] Reddedildi: {company}")
                return

        # 6. Gönder
        msg = EmailMessage(
            to_email=email,
            to_name=company,
            subject=chosen_subject,
            html_body=draft.body_html,
            text_body=draft.body_text,
            campaign_id=campaign_id,
            lead_id=email,
        )

        result = self.send_engine.send(msg)

        if result.success:
            stats.sent += 1
            self.watchdog.record_send(success=True)
            sector = lead.get("sector") or lead.get("Sector") or ""
            db.log_sent(
                email=email, company=company,
                sector=sector,
                subject=chosen_subject, method=result.method,
                message_id=result.message_id,
                test_mode=config.TEST_MODE,
                campaign_id=campaign_id,
                ab_variant=variant,
            )
            # Follow-up zinciri zamanla (v4)
            if config.FOLLOWUP_ENABLED:
                try:
                    self.followup.schedule_followups(
                        email=email,
                        original_subject=chosen_subject,
                        company=company,
                        sector=sector,
                        vehicles=str(lead.get("vehicles") or lead.get("Vehicles") or ""),
                        campaign_id=campaign_id,
                    )
                except Exception as e:
                    log.warning(f"[FOLLOWUP] Zamanlama hatasi: {e}")

            log.info(f"[SENT] {company} -> {email} | "
                     f"Varyant {variant} | QC: {qc.score} ({qc.method})")
        else:
            stats.failed += 1
            self.watchdog.record_send(success=False)
            log.error(f"[FAIL] {company} -> {email} | {result.error}")

    # ─────────────────────────────────────────────────────────────
    # YARDIMCI METODLAR
    # ─────────────────────────────────────────────────────────────

    def _human_review(self, lead: dict, draft) -> bool:
        """İnsan onay modu: terminalde mail gösterir ve onay ister."""
        print("\n" + "═"*60)
        print(f"  ŞİRKET : {lead.get('company') or lead.get('Company')}")
        print(f"  EMAIL  : {lead.get('email') or lead.get('Email')}")
        print(f"  KONU A : {draft.subject_a}")
        print(f"  KONU B : {draft.subject_b}")
        print(f"  KONU C : {draft.subject_c}")
        print("─"*60)
        print(draft.body_text)
        print("═"*60)
        ans = input("Bu maili gönder? [e/h]: ").strip().lower()
        if ans == "e":
            choice = input("Konu seç [A/B/C] (varsayılan A): ").strip().upper()
            if choice == "B":
                draft.chosen_subject = draft.subject_b
            elif choice == "C":
                draft.chosen_subject = draft.subject_c
            return True
        return False

    def _print_summary(self, stats: CampaignStats):
        log.info("-" * 50)
        log.info("KAMPANYA OZETI (v4)")
        log.info(f"  Toplam lead       : {stats.total_leads}")
        log.info(f"  Islenen           : {stats.processed}")
        log.info(f"  Gonderilen        : {stats.sent}")
        log.info(f"  Compliance atlandi: {stats.skipped_compliance}")
        log.info(f"  QC atlandi        : {stats.skipped_quality}")
        log.info(f"  Basarisiz         : {stats.failed}")

        wd = self.watchdog.get_summary()
        log.info(f"  Watchdog kontrol  : {wd['checks_run']}")
        log.info(f"  Bounce            : {wd['bounce']}")

        ab = self.ab_test.get_status()
        log.info(f"  A/B Test          : {ab['phase']} | "
                 f"Kazanan: {ab['winner'] or 'henuz yok'}")

        fu = self.followup.get_stats()
        log.info(f"  Follow-up bekleyen: {fu['pending']}")
        log.info(f"  Follow-up toplam  : {fu['total']}")

        db_stats = db.get_stats()
        log.info(f"  DB Lead sayisi    : {db_stats['total_leads']}")
        log.info(f"  DB Gonderim sayisi: {db_stats['total_sent']}")
        log.info(f"  Hot leads         : {db_stats.get('hot_leads', 0)}")
        log.info("-" * 50)

    # ─────────────────────────────────────────────────────────────
    # FOLLOW-UP İŞLEME (v4)
    # ─────────────────────────────────────────────────────────────

    def process_followups(self) -> list[dict]:
        """Bekleyen follow-up'lari isle ve gonder."""
        pending = self.followup.process_pending()
        sent = []

        for fu in pending:
            try:
                msg = EmailMessage(
                    to_email=fu["email"],
                    to_name=fu.get("company", ""),
                    subject=fu["subject"],
                    html_body=fu["body_html"],
                    text_body=fu["body_text"],
                    campaign_id="followup",
                    lead_id=fu["email"],
                )
                result = self.send_engine.send(msg)
                if result.success:
                    db.update_followup_status(
                        fu["id"], "sent",
                        subject=fu["subject"],
                        body_html=fu["body_html"],
                        body_text=fu["body_text"],
                    )
                    sent.append(fu)
                    log.info(f"[FOLLOWUP SENT] Step {fu['step']} -> {fu['email']}")
                else:
                    db.update_followup_status(fu["id"], "error")
            except Exception as e:
                log.error(f"[FOLLOWUP ERROR] {fu['email']}: {e}")
                db.update_followup_status(fu["id"], "error")

        return sent

    def classify_response(self, email: str, response_text: str,
                          original_subject: str = "") -> dict:
        """Gelen yaniti siniflandir."""
        return self.response_tracker.classify_response(
            email, response_text, original_subject)
