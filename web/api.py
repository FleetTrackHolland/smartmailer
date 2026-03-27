"""
web/api.py — SmartMailer Ultimate Web Dashboard API
Flask-SocketIO, SQLite, A/B test, AI QC ≥90, Follow-Up, Response Tracking.
SmartMailer Pro + FleetTrack CRM birleşim API.
"""
import csv
import json
import os
import sys
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory

# Proje kök dizinini path'e ekle
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import config
from core.logger import get_logger

log = get_logger("web_api")

# ─── PASSENGER / PRODUCTION DETECTION ─────────────────────────────
IS_PASSENGER = (
    os.environ.get("PASSENGER_BASE_URI")
    or "passenger" in os.environ.get("SERVER_SOFTWARE", "").lower()
    or os.environ.get("PASSENGER_MODE", "").lower() == "true"
)

app = Flask(__name__, static_folder="static", static_url_path="")

# SocketIO — try import, fallback to polling mode
try:
    from flask_socketio import SocketIO, emit
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")
    HAS_SOCKETIO = True
    log.info("Flask-SocketIO aktif — real-time mod.")
except ImportError:
    socketio = None
    HAS_SOCKETIO = False
    log.warning("flask-socketio bulunamadi — polling moduna dustu.")

# CORS fallback
try:
    from flask_cors import CORS
    CORS(app)
except ImportError:
    pass


# ─── LAZY-LOADED GLOBAL STATE ─────────────────────────────────────
# Agents are initialized on first request, NOT at import time.
# This prevents Passenger WSGI timeout during module loading.
copywriter = None
quality = None
compliance = None
lead_scorer = None
ab_test = None
follow_up = None
response_tracker = None
lead_finder = None
template_engine = None
watchdog = None
db = None
_agents_initialized = False


def _init_agents():
    """Lazy-load all agents and DB on first request."""
    global copywriter, quality, compliance, lead_scorer, ab_test
    global follow_up, response_tracker, lead_finder, template_engine
    global watchdog, db, _agents_initialized

    if _agents_initialized:
        return

    try:
        from core.database import db as _db
        db = _db

        from core.ab_test_engine import ABTestEngine
        from core.followup_engine import FollowUpEngine
        from core.template_engine import TemplateEngine
        from agents.copywriter_agent import CopywriterAgent
        from agents.quality_agent import QualityAgent
        from agents.compliance_agent import ComplianceAgent
        from agents.watchdog_agent import WatchdogAgent
        from agents.lead_scorer import LeadScorer
        from agents.response_tracker import ResponseTracker
        from agents.lead_finder import LeadFinder

        copywriter = CopywriterAgent()
        quality = QualityAgent()
        compliance = ComplianceAgent()
        lead_scorer = LeadScorer()
        ab_test = ABTestEngine(test_size=12)
        follow_up = FollowUpEngine()
        response_tracker = ResponseTracker()
        lead_finder = LeadFinder()
        template_engine = TemplateEngine()
        watchdog = WatchdogAgent(
            agents={"copywriter": copywriter, "quality": quality,
                    "compliance": compliance, "lead_scorer": lead_scorer,
                    "followup": follow_up, "response_tracker": response_tracker,
                    "lead_finder": lead_finder},
            config=config,
        )
        _agents_initialized = True
        log.info("[INIT] Tüm agent'lar başarıyla yüklendi.")
    except Exception as e:
        log.error(f"[INIT] Agent yükleme hatası: {e}")
        # Set db at minimum so basic endpoints work
        try:
            if db is None:
                from core.database import db as _db
                db = _db
        except Exception:
            pass
        _agents_initialized = True  # Don't retry every request


@app.before_request
def ensure_agents_loaded():
    """Ensure agents are initialized before handling any API request."""
    # Skip for health check — must respond instantly
    if request.path == "/health":
        return
    _init_agents()

# Kampanya durumu
campaign_state = {
    "running": False,
    "thread": None,
    "campaign_id": None,
    "stats": {
        "total_leads": 0, "processed": 0, "sent": 0,
        "skipped_compliance": 0, "skipped_quality": 0,
        "failed": 0,
    },
}


# ─── SOCKET.IO EVENT EMITTER ──────────────────────────────────
def emit_event(event_name, data):
    """Real-time event gönder (SocketIO varsa)."""
    if HAS_SOCKETIO and socketio:
        socketio.emit(event_name, data)


# ─── HEALTH CHECK (no DB, no agents) ─────────────────────────
@app.route("/health")
def health_check():
    """Lightweight health check — responds instantly, no DB or agent needed."""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "agents_loaded": _agents_initialized,
        "passenger": IS_PASSENGER,
    })


# ─── STATIC FILES ─────────────────────────────────────────────
@app.route("/")
def serve_index():
    return send_from_directory(app.static_folder, "index.html")


# ─── LEADS ─────────────────────────────────────────────────────
@app.route("/api/leads", methods=["GET"])
def get_leads():
    """Lead listesini SQLite'dan döndürür. Send status bilgisiyle zenginleştirir."""
    leads = db.get_all_leads(order_by_ai_score=True)

    # Eğer DB boşsa CSV'den import et
    if not leads:
        leads_file = _find_leads_file()
        if leads_file:
            db.import_leads_from_csv(leads_file)
            leads = db.get_all_leads(order_by_ai_score=True)

    # Send status zenginleştir
    sent_log = db.get_sent_emails()
    sent_map = {s.get("email", "").lower(): s for s in sent_log}

    for lead in leads:
        email = (lead.get("email") or lead.get("Email") or "").lower()
        if email in sent_map:
            lead["send_status"] = "sent"
            lead["sent_at"] = sent_map[email].get("sent_at", "")
            lead["send_method"] = sent_map[email].get("method", "")
        elif lead.get("draft_id") or lead.get("has_draft"):
            lead["send_status"] = "pending"
        else:
            lead["send_status"] = "unsent"

    # Status filtresi (?status=unsent|sent|all)
    status_filter = request.args.get("status", "all").lower()
    if status_filter == "unsent":
        leads = [l for l in leads if l.get("send_status") != "sent"]
    elif status_filter == "sent":
        leads = [l for l in leads if l.get("send_status") == "sent"]

    return jsonify({"leads": leads, "count": len(leads)})


@app.route("/api/stats/daily", methods=["GET"])
def get_daily_stats():
    """Günlük gönderim istatistikleri — limit göstergesi için."""
    today_sent = db.get_today_sent_count()

    # Brevo API'den gerçek kalan krediyi al
    brevo_remaining = None
    brevo_plan = None
    try:
        import requests as req
        headers = {"api-key": config.BREVO_API_KEY, "accept": "application/json"}
        resp = req.get("https://api.brevo.com/v3/account", headers=headers, timeout=5)
        if resp.status_code == 200:
            acct = resp.json()
            # Plan bilgisi
            for p in acct.get("plan", []):
                if p.get("type") == "payAsYouGo" or "email" in p.get("type", "").lower():
                    brevo_remaining = p.get("credits", None)
                    brevo_plan = p.get("type", "")
            # credits alanı doğrudan da olabilir
            if brevo_remaining is None:
                for p in acct.get("plan", []):
                    if p.get("credits") is not None:
                        brevo_remaining = p.get("credits")
                        brevo_plan = p.get("type", "standard")
                        break
    except Exception as e:
        log.warning(f"Brevo account API hatası: {e}")

    return jsonify({
        "today_sent": today_sent,
        "daily_limit": config.DAILY_SEND_LIMIT,
        "remaining": max(0, config.DAILY_SEND_LIMIT - today_sent),
        "percentage": round((today_sent / config.DAILY_SEND_LIMIT) * 100) if config.DAILY_SEND_LIMIT > 0 else 0,
        "brevo_remaining": brevo_remaining,
        "brevo_plan": brevo_plan,
        "monthly_limit": config.MONTHLY_SEND_LIMIT,
    })


@app.route("/api/brevo/account", methods=["GET"])
def get_brevo_account():
    """Brevo hesap bilgisi — gerçek kalan kredi ve plan detayları."""
    try:
        import requests as req
        headers = {"api-key": config.BREVO_API_KEY, "accept": "application/json"}
        resp = req.get("https://api.brevo.com/v3/account", headers=headers, timeout=10)
        resp.raise_for_status()
        acct = resp.json()
        return jsonify({
            "success": True,
            "email": acct.get("email"),
            "plan": acct.get("plan", []),
            "credits": acct.get("credits"),
            "relay": acct.get("relay", {}),
            "marketing_automation": acct.get("marketingAutomation", {}),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ─── BREVO WEBHOOK EVENT TRACKING ─────────────────────────────────
@app.route("/webhook/brevo", methods=["POST"])
def brevo_webhook():
    """Brevo webhook — email event'lerini yakala (open, click, bounce, spam)."""
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"status": "no_data"}), 400

        # Brevo tek event veya liste gönderebilir
        events_list = data if isinstance(data, list) else [data]

        for evt in events_list:
            email = evt.get("email", "").lower().strip()
            event_type = evt.get("event", "").lower()
            message_id = evt.get("message-id", "") or evt.get("messageId", "")

            if not email or not event_type:
                continue

            # Metadata topla
            metadata = {
                "ts": evt.get("ts_event") or evt.get("date"),
                "subject": evt.get("subject", ""),
                "tag": evt.get("tag", ""),
                "ip": evt.get("ip", ""),
                "link": evt.get("link", ""),  # click event'inde tıklanan link
                "reason": evt.get("reason", ""),  # bounce reason
            }
            # Temiz data — boş olanları çıkar
            metadata = {k: v for k, v in metadata.items() if v}

            db.record_event(email, event_type, message_id, metadata)

            # Click → hot lead
            if event_type in ("click", "clicked"):
                try:
                    db.flag_lead_hot(email)
                except Exception:
                    pass

            # 2+ opens → hot lead
            if event_type in ("opened", "open", "unique_opened", "uniqueopened"):
                try:
                    opens = db.get_events_by_type("opened", 500) + db.get_events_by_type("open", 500)
                    open_count = sum(1 for e in opens if e.get("email") == email)
                    if open_count >= 2:
                        db.flag_lead_hot(email)
                except Exception:
                    pass

            # Bounce → lead'i invalid işaretle + followup iptal
            if event_type in ("hard_bounce", "hardbounce", "blocked", "invalid"):
                try:
                    db.mark_lead_invalid(email)
                    db.cancel_pending_followups(email)
                except Exception:
                    pass

            # Spam/Unsub → opt-out + followup iptal
            if event_type in ("spam", "complaint", "spamreport", "unsubscribed", "unsubscribe"):
                try:
                    db.add_opt_out(email, reason=f"brevo_{event_type}")
                    db.cancel_pending_followups(email)
                except Exception:
                    pass

            log.info(f"[WEBHOOK] {event_type} ← {email}")

        return jsonify({"status": "ok", "processed": len(events_list)})
    except Exception as e:
        log.error(f"[WEBHOOK] Hata: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/stats/events", methods=["GET"])
def get_event_stats():
    """Email event istatistikleri — open rate, click rate, bounce rate."""
    stats = db.get_event_stats()
    return jsonify(stats)


@app.route("/api/stats/events/recent", methods=["GET"])
def get_recent_events():
    """Son email event'leri feed."""
    limit = request.args.get("limit", 50, type=int)
    events = db.get_recent_events(limit)
    return jsonify({"events": events, "count": len(events)})


@app.route("/api/brevo/setup-webhooks", methods=["POST"])
def setup_brevo_webhooks():
    """Brevo'da webhook'ları otomatik oluştur."""
    try:
        import requests as req
        headers = {"api-key": config.BREVO_API_KEY, "content-type": "application/json", "accept": "application/json"}

        webhook_url = "https://app.fleettrackholland.nl/webhook/brevo"
        events_to_track = [
            "delivered", "hardBounce", "softBounce", "blocked",
            "spam", "opened", "click", "unsubscribed", "invalid", "deferred"
        ]

        # Mevcut webhook'ları kontrol et
        existing = req.get("https://api.brevo.com/v3/webhooks", headers=headers, timeout=10)
        existing_urls = []
        if existing.status_code == 200:
            for wh in existing.json().get("webhooks", []):
                existing_urls.append(wh.get("url", ""))

        results = []
        if webhook_url in existing_urls:
            results.append({"status": "already_exists", "url": webhook_url})
        else:
            # Transactional webhook
            payload = {
                "url": webhook_url,
                "description": "SmartMailer Event Tracker",
                "events": events_to_track,
                "type": "transactional",
            }
            resp = req.post("https://api.brevo.com/v3/webhooks", json=payload, headers=headers, timeout=10)
            results.append({"type": "transactional", "status": resp.status_code, "body": resp.json() if resp.status_code < 300 else resp.text[:200]})

            # Marketing webhook
            payload["type"] = "marketing"
            resp2 = req.post("https://api.brevo.com/v3/webhooks", json=payload, headers=headers, timeout=10)
            results.append({"type": "marketing", "status": resp2.status_code, "body": resp2.json() if resp2.status_code < 300 else resp2.text[:200]})

        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/leads/upload", methods=["POST"])
def upload_leads():
    """CSV yükle → SQLite'a import et."""
    if "file" not in request.files:
        return jsonify({"error": "Dosya bulunamadı"}), 400
    f = request.files["file"]
    if not f.filename.endswith(".csv"):
        return jsonify({"error": "Sadece CSV kabul edilir"}), 400

    dest = os.path.join(config.INPUT_DIR, "leads.csv")
    os.makedirs(config.INPUT_DIR, exist_ok=True)
    f.save(dest)

    count = db.import_leads_from_csv(dest)
    emit_event("leads_updated", {"count": count})
    return jsonify({"success": True, "imported": count})


@app.route("/api/leads/score", methods=["POST"])
def score_leads():
    """Tüm lead'leri AI ile puanla."""
    leads = db.get_all_leads()
    if not leads:
        return jsonify({"error": "Lead bulunamadı"}), 404

    scores = lead_scorer.score_batch(leads)
    for s in scores:
        db.update_lead_ai_score(s["email"], s.get("score", 50), s.get("reason", ""))

    emit_event("leads_scored", {"count": len(scores)})
    return jsonify({"success": True, "scored": len(scores), "results": scores})


# ─── DRAFTS ────────────────────────────────────────────────────
@app.route("/api/drafts", methods=["GET"])
def get_drafts():
    """Tüm taslakları SQLite'dan getir."""
    drafts = db.get_latest_drafts()
    return jsonify({"drafts": drafts, "count": len(drafts)})


@app.route("/api/drafts/preview", methods=["POST"])
def preview_draft():
    """Tek lead için AI taslak üret + AI QC + auto-fix."""
    lead = request.json
    if not lead:
        return jsonify({"error": "Lead verisi gerekli"}), 400

    email = (lead.get("Email") or lead.get("email") or "").strip()
    company = lead.get("Company") or lead.get("company") or "?"

    # Lead'i DB'ye kaydet
    db.upsert_lead(lead)

    # Compliance kontrolü
    ok, reason = compliance.is_ok_to_send(email)

    # AI ile taslak üret
    try:
        draft = copywriter.write(lead)
    except Exception as e:
        return jsonify({"error": f"AI üretim hatası: {str(e)}"}), 500

    # AI QC + auto-fix loop (>=90 zorunlu)
    qc = quality.check(draft.chosen_subject, draft.body_text, company, draft.body_html)
    retries = 0
    max_retries = config.QC_MAX_RETRIES
    min_score = config.QC_MIN_SCORE
    while qc.score < min_score and retries < max_retries:
        retries += 1
        try:
            all_issues = qc.issues + qc.warnings
            if qc.feedback:
                all_issues.append(f"AI FEEDBACK: {qc.feedback}")
            all_issues.append(f"Minimum skor: {min_score}. Mevcut skor: {qc.score}")
            draft = copywriter.rewrite(draft, all_issues)
            qc = quality.check(draft.chosen_subject, draft.body_text, company, draft.body_html)
        except Exception:
            break

    # SQLite'a kaydet
    draft_data = {
        "subject_a": draft.subject_a,
        "subject_b": draft.subject_b,
        "subject_c": draft.subject_c,
        "chosen_subject": draft.chosen_subject,
        "body_html": draft.body_html,
        "body_text": draft.body_text,
        "qc_score": qc.score,
        "qc_passed": qc.passed,
        "qc_issues": qc.issues,
        "qc_method": qc.method,
        "compliance_ok": ok,
        "compliance_reason": reason,
        "auto_fix_retries": retries,
    }
    db.save_draft(email, draft_data)

    result = {**draft_data, "lead": lead}
    emit_event("draft_generated", {"email": email, "qc_score": qc.score})
    return jsonify(result)


@app.route("/api/drafts/bulk-preview", methods=["POST"])
def bulk_preview():
    """Toplu taslak üretimi (AI QC + auto-fix)."""
    count = (request.json or {}).get("count", 3)

    # DB'den lead'leri al (AI skoru sırasıyla)
    leads = db.get_all_leads(order_by_ai_score=True)
    if not leads:
        # CSV fallback
        leads_file = _find_leads_file()
        if leads_file:
            db.import_leads_from_csv(leads_file)
            leads = db.get_all_leads(order_by_ai_score=True)

    if not leads:
        return jsonify({"error": "Lead bulunamadı"}), 404

    selected = leads[:count]
    results = []

    for lead in selected:
        email = lead.get("email") or lead.get("Email") or ""
        company = lead.get("company") or lead.get("Company") or "?"

        try:
            draft = copywriter.write(lead)
            qc = quality.check(draft.chosen_subject, draft.body_text,
                               company, draft.body_html)

            retries = 0
            max_retries = config.QC_MAX_RETRIES
            min_score = config.QC_MIN_SCORE
            while qc.score < min_score and retries < max_retries:
                retries += 1
                try:
                    all_issues = qc.issues + qc.warnings
                    if qc.feedback:
                        all_issues.append(f"AI FEEDBACK: {qc.feedback}")
                    all_issues.append(f"Minimum skor: {min_score}. Mevcut: {qc.score}")
                    draft = copywriter.rewrite(draft, all_issues)
                    qc = quality.check(draft.chosen_subject, draft.body_text,
                                       company, draft.body_html)
                except Exception:
                    break

            ok, reason = compliance.is_ok_to_send(email)

            draft_data = {
                "subject_a": draft.subject_a,
                "subject_b": draft.subject_b,
                "subject_c": draft.subject_c,
                "chosen_subject": draft.chosen_subject,
                "body_html": draft.body_html,
                "body_text": draft.body_text,
                "qc_score": qc.score,
                "qc_passed": qc.passed,
                "qc_issues": qc.issues,
                "qc_method": qc.method,
                "compliance_ok": ok,
                "compliance_reason": reason,
                "auto_fix_retries": retries,
            }
            db.save_draft(email, draft_data)
            results.append({**draft_data, "email": email})

            emit_event("draft_generated", {"email": email, "qc_score": qc.score})

        except Exception as e:
            log.error(f"Bulk preview hatası ({company}): {e}")
            results.append({"email": email, "error": str(e)})

    return jsonify({"drafts": results, "count": len(results)})


@app.route("/api/drafts/edit", methods=["PUT"])
def edit_draft():
    """Taslağı düzenle, QC yeniden çalıştır, SQLite'a kaydet."""
    data = request.json
    email = data.get("email", "").strip()
    if not email:
        return jsonify({"error": "Email gerekli"}), 400

    body_text = data.get("body_text", "")
    body_html = data.get("body_html", "")
    chosen_subject = data.get("chosen_subject", "")

    # QC çalıştır
    lead = db.get_lead_by_email(email)
    company = (lead or {}).get("company", "")
    qc = quality.check(chosen_subject, body_text, company, body_html)

    draft_data = {
        "subject_a": data.get("subject_a", ""),
        "subject_b": data.get("subject_b", ""),
        "subject_c": data.get("subject_c", ""),
        "chosen_subject": chosen_subject,
        "body_html": body_html,
        "body_text": body_text,
        "qc_score": qc.score,
        "qc_passed": qc.passed,
        "qc_issues": qc.issues,
        "qc_method": qc.method,
    }
    db.save_draft(email, draft_data)

    return jsonify(draft_data)


# ─── AGENTS ────────────────────────────────────────────────────
@app.route("/api/agents/status", methods=["GET"])
def get_agent_status():
    agents_info = [
        {"name": "Orchestrator", "icon": "👔", "obj": None},
        {"name": "AI Copywriter", "icon": "✍️", "obj": copywriter},
        {"name": "AI Quality Control", "icon": "🧠", "obj": quality},
        {"name": "Compliance (AVG)", "icon": "⚖️", "obj": compliance},
        {"name": "Lead Scorer", "icon": "🔮", "obj": lead_scorer},
        {"name": "Watchdog", "icon": "🛡️", "obj": watchdog},
        {"name": "A/B Test Engine", "icon": "🎯", "obj": ab_test},
        {"name": "Follow-Up Engine", "icon": "🔄", "obj": follow_up},
        {"name": "Response Tracker", "icon": "💬", "obj": response_tracker},
        {"name": "Lead Finder", "icon": "🔍", "obj": lead_finder},
        {"name": "Recon Agent", "icon": "🕵️", "obj": None},
    ]
    result = []
    for a in agents_info:
        try:
            if a["obj"] is not None:
                alive = a["obj"].ping() if hasattr(a["obj"], "ping") else True
            else:
                # ReconAgent — lazy import check
                try:
                    from agents.recon_agent import recon_agent as _ra
                    alive = _ra.ping() if hasattr(_ra, "ping") else True
                except Exception:
                    alive = True
            status = "OK" if alive else "WARNING"
        except Exception as e:
            status = "CRITICAL"

        extra = ""
        if a["name"] == "A/B Test Engine":
            ab_status = ab_test.get_status()
            extra = f" | Faz: {ab_status['phase']} | Kazanan: {ab_status['winner'] or '—'}"
        elif a["name"] == "AI Quality Control":
            extra = " | AI + regex fallback"
        elif a["name"] == "Lead Scorer":
            extra = " | Claude AI batch scoring"
        elif a["name"] == "Follow-Up Engine":
            stats = db.get_followup_stats()
            extra = f" | Bekleyen: {stats.get('pending_count', 0)}"
        elif a["name"] == "Response Tracker":
            stats = db.get_response_stats()
            extra = f" | Yanıtlar: {stats.get('total_responses', 0)}"
        elif a["name"] == "Lead Finder":
            extra = " | Web scraping"
        elif a["name"] == "Recon Agent":
            extra = " | OSINT + Psikolojik profil"
        elif a["name"] == "Orchestrator":
            extra = " | Koordinasyon merkezi"

        result.append({
            "name": a["name"],
            "icon": a["icon"],
            "status": status,
            "error": extra,
            "checked_at": datetime.now().isoformat(),
        })
    return jsonify({"agents": result})


# ─── AGENT TOPLANTI ODASI ──────────────────────────────────────
meeting_state = {"active": False, "messages": [], "round": 0}

@app.route("/api/agents/meeting", methods=["POST"])
def agent_meeting():
    """Agent toplantı odası — AI ile agent tartışması üretir."""
    data = request.get_json(silent=True) or {}
    action = data.get("action", "start")

    if action == "start":
        # Sistem istatistiklerini topla
        stats = db.get_stats()
        fu_stats = db.get_followup_stats()
        resp_stats = db.get_response_stats()

        context = (
            f"Toplam lead: {stats.get('total_leads', 0)}, "
            f"Gönderilen: {stats.get('total_sent', 0)}, "
            f"Follow-up bekleyen: {fu_stats.get('pending_count', 0)}, "
            f"Yanıtlar: {resp_stats.get('total_responses', 0)}, "
            f"Hot leads: {stats.get('hot_leads', 0)}"
        )

        prompt = f"""Sen bir otomasyon sistemindesin. Bu sistemde 10 AI agent birlikte çalışıyor.
Her agent'ın kendi uzmanlık alanı var. Sistem istatistikleri:
{context}

Agent'lar bir toplantı yapıyorlar. Bu toplantı uzun ve detaylı bir beyin fırtınası (brainstorming) oturumudur.
Agent'lar birbirleriyle gerçek bir ekip toplantısı yapıyor — birbirlerinin fikirlerine yanıt veriyor,
tartışıyor, katılıyor ya da karşı argümanlar sunuyor. Amaç:
- Performansı artırmak için yeni stratejiler geliştirmek
- Sorunları birlikte çözmek
- Birbirlerinden öğrenmek ve fikir alışverişi yapmak
- Somut aksiyon planları oluşturmak

Agent listesi ve rolleri:
1. Orchestrator — tüm agent'ları yöneten koordinatör, toplantıyı yönetir
2. AI Copywriter — email yazan agent
3. AI Quality Control — email kalitesini kontrol eden agent
4. Lead Scorer — lead kalitesini puanlayan agent
5. Recon Agent — OSINT araştırma yapan agent
6. Lead Finder — lead bulan agent
7. Follow-Up Engine — takip mailleri gönderen agent
8. Response Tracker — yanıtları takip eden agent
9. Watchdog — sistem sağlığını izleyen agent
10. Compliance (AVG) — GDPR uyum kontrolü yapan agent
11. A/B Test Engine — A/B testleri yöneten agent

15-20 mesaj halinde uzun ve derinlemesine bir toplantı konuşması yaz.
Her agent en az 1-2 kere konuşsun. Agent'lar birbirlerine hitap etsin ve birbirlerinin
fikirlerine doğrudan yanıt versin. Tartışma, onay, karşı görüş ve brainstorming olsun.
Mesajlar kısa değil, açıklayıcı ve detaylı olsun (en az 2-3 cümle).

JSON formatında cevap ver (yalnızca JSON, başka metin olmasın):
[
  {{"agent": "Agent Adı", "text": "Mesaj içeriği"}},
  ...
]"""

        try:
            from config import config as cfg
            from core.api_guard import api_guard

            headers = {
                "x-api-key": cfg.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            }
            resp = api_guard.call(payload, headers, timeout=120)

            if resp and resp.ok:
                result = resp.json()
                text = result.get("content", [{}])[0].get("text", "[]")
                # JSON parse
                import json as _json
                # Find JSON array in the response
                start_idx = text.find("[")
                end_idx = text.rfind("]") + 1
                if start_idx >= 0 and end_idx > start_idx:
                    messages = _json.loads(text[start_idx:end_idx])
                else:
                    messages = []

                meeting_state["active"] = True
                meeting_state["messages"] = messages
                meeting_state["round"] = 1

                return jsonify({"success": True, "messages": messages})
            else:
                # Fallback — yerel mesajlar üret
                messages = _generate_fallback_meeting(stats, fu_stats, resp_stats)
                meeting_state["active"] = True
                meeting_state["messages"] = messages
                meeting_state["round"] = 1
                return jsonify({"success": True, "messages": messages})

        except Exception as e:
            log.error(f"[MEETING] Hata: {e}")
            messages = _generate_fallback_meeting(
                stats if 'stats' in dir() else {},
                fu_stats if 'fu_stats' in dir() else {},
                resp_stats if 'resp_stats' in dir() else {}
            )
            meeting_state["active"] = True
            meeting_state["messages"] = messages
            meeting_state["round"] = 1
            return jsonify({"success": True, "messages": messages})

    elif action == "continue":
        offset = data.get("offset", 0)
        if not meeting_state["active"]:
            return jsonify({"messages": [], "finished": True})

        if meeting_state["round"] >= 6:
            meeting_state["active"] = False
            return jsonify({"messages": [], "finished": True})

        # Yeni round üret — fallback kullan
        stats = db.get_stats()
        fu_stats = db.get_followup_stats()
        resp_stats = db.get_response_stats()
        new_messages = _generate_continuation_meeting(meeting_state["round"], stats)
        meeting_state["messages"].extend(new_messages)
        meeting_state["round"] += 1

        return jsonify({"success": True, "messages": new_messages, "finished": meeting_state["round"] >= 6})

    return jsonify({"error": "Geçersiz aksiyon"})


def _generate_fallback_meeting(stats, fu_stats, resp_stats):
    """Claude API kullanılamadığında zengin yerel toplantı mesajları üretir."""
    total_sent = stats.get('total_sent', 0) if isinstance(stats, dict) else 0
    total_leads = stats.get('total_leads', 0) if isinstance(stats, dict) else 0
    pending_fu = fu_stats.get('pending_count', 0) if isinstance(fu_stats, dict) else 0
    responses = resp_stats.get('total_responses', 0) if isinstance(resp_stats, dict) else 0

    return [
        # AÇILIŞ — durum raporu
        {"agent": "Orchestrator", "text": f"Hoş geldiniz arkadaşlar, haftalık strateji toplantımıza başlıyoruz. Mevcut durum: veritabanımızda {total_leads} lead var, {total_sent} mail gönderildi ve {responses} yanıt aldık. Bugünkü ana gündem maddemiz: dönüşüm oranını artırmak ve yeni pazarlara açılmak. Her agent'tan detaylı rapor ve öneri bekliyorum."},
        {"agent": "Lead Finder", "text": f"Raporumu sunuyorum. Şu ana kadar {total_leads} lead buldum. Hollanda pazarında 12 şehri taradık ama henüz Belçika ve Almanya'ya açılmadık. Önerim: Antwerp, Gent, Hamburg ve Düsseldorf'u da tarama listesine ekleyelim. Bu bölgelerde lojistik sektörü çok güçlü ve potansiyel müşteri havuzu geniş."},
        {"agent": "Recon Agent", "text": "Lead Finder'ın önerisine katılıyorum. Ben de OSINT araştırmalarımda fark ettim ki, web sitesi olan şirketler %40 daha yüksek yanıt oranı veriyor. LinkedIn profili olan kişilere yönelik maillerde dönüşüm 2 kat daha yüksek. Belçika pazarına girersek, özellikle Flaman bölgesindeki şirketlere odaklanmalıyız — Hollandaca konuşuyorlar ve kültürel yakınlık dönüşümü artırır."},
        {"agent": "AI Copywriter", "text": "Recon Agent'ın verilerine dayanarak bir öneri sunmak istiyorum. Şu ana kadar tek bir email şablonu kullanıyoruz ama sektöre özel dil kullanımını geliştirmeliyiz. Nakliye şirketlerine 'filo yönetimi' vurgulu, lojistik firmalarına 'rota optimizasyonu' vurgulu, kurye şirketlerine 'teslimat takibi' vurgulu farklı şablonlar hazırlayabilirim. Bu şekilde personalizasyon %300 artabilir."},
        {"agent": "AI Quality Control", "text": "Copywriter'ın sektöre özel şablon fikri mükemmel. Ancak bir uyarım var: son 100 emailin QC analizi gösteriyor ki CTA çeşitliliğimiz çok düşük. Her mailde 'demo talep edin' diyoruz. Bunun yerine 'ücretsiz analiz raporu', 'ROI hesaplayıcı', veya 'sektör karşılaştırma raporu' gibi farklı value proposition'lar kullanmalıyız. Bu spam filtreleri ihtimalini de düşürür."},
        {"agent": "Lead Scorer", "text": "Quality Control'ün CTA konusundaki görüşüne tam katılıyorum. Ben de scoring modelimi güncellemeyi planlıyorum. Şu anki veriler gösteriyor ki 50+ araçlı filolara sahip şirketler 3 kat daha ilgili. Ayrıca 'info@' yerine kişisel email adresine ulaştığımızda yanıt oranı %85 artıyor. Scoring algoritmasına bu faktörleri ağırlıklı olarak ekleyeceğim."},
        {"agent": "A/B Test Engine", "text": "Scorer'ın verileriyle ilginç bir korelasyon buldum. A/B testlerimde soru formatında konu başlıkları %18 daha yüksek açılma oranı sağlıyor. Örneğin 'Filonuzu nasıl optimize edebilirsiniz?' şeklindeki başlıklar çok iyi çalışıyor. Emoji kullanımı Hollanda pazarında %12 artış sağlıyor ama Almanya'da etkisi nötr. Bu bilgiyi Copywriter'a aktarıyorum."},
        {"agent": "AI Copywriter", "text": "A/B Test Engine teşekkürler, çok değerli veriler! Hemen uygulamaya koyacağım. Ayrıca bir brainstorm fikrim var: 'social proof' elementi ekleyelim maillere — 'X şirket gibi Y şirket de filo takip sistemimizi tercih etti' şeklinde. Bu güven oluşturur ve dönüşümü artırır. Ne dersiniz?"},
        {"agent": "Compliance (AVG)", "text": "Copywriter'ın social proof fikri GDPR açısından dikkat gerektirir. Şirket isimlerini referans olarak kullanmadan önce izinlerinin olması lazım. Alternatif olarak 'sektörünüzdeki 50+ şirket' gibi anonim referanslar kullanabiliriz. Ayrıca unsubscribe oranımız %0.3 ile çok iyi durumda — bu konuda sorunumuz yok. Belçika ve Almanya'ya açılırsak o ülkelerin spesifik veri koruma kurallarını da kontrol etmem gerekecek."},
        {"agent": "Follow-Up Engine", "text": f"Şu anda {pending_fu} follow-up bekliyor. Verilerim gösteriyor ki 3. gün follow-up'ı en yüksek açılma oranına sahip. 7. gün 'curiosity gap' stratejisi ile %25 yanıt artışı sağlıyor. 14. gün ROI odaklı son mail ise en yüksek dönüşümü sağlıyor. FOMO stratejisini 'sınırlı pilot program' mesajıyla güçlendirmeyi öneriyorum."},
        {"agent": "Response Tracker", "text": "Follow-Up Engine'in zamanlama verilerini doğruluyorum. Gelen yanıtları analiz ettiğimde 'ilgili' yanıtların %60'ı ilk 24 saat içinde geliyor. Ayrıca 'fiyat sorma' içerikli yanıtlar en yüksek dönüşüm potansiyeline sahip — bunlara öncelik verelim. Hot lead'leri anında Orchestrator'a bildirecek bir alarm sistemi kurmalıyız."},
        {"agent": "Watchdog", "text": "Sistem sağlığı konusunda rapor: API bağlantıları stabil, uptime %99.8. Ancak uyarım var — eğer Belçika ve Almanya pazarlarına açılırsak, API çağrı hacmimiz 3 katına çıkabilir. Rate limiting stratejimizi şimdiden güncelemeliyiz. Ayrıca veritabanı boyutu hızla büyüyor, periyodik arşivleme planı yapmalıyız."},
        {"agent": "Orchestrator", "text": "Harika tartışma! Özetliyorum ve aksiyon planı oluşturuyorum: 1) Copywriter sektöre özel 3 farklı şablon hazırlasın. 2) A/B Test Engine yeni şablonları test etsin. 3) Lead Finder Belçika pilot taraması başlatsın. 4) Compliance Belçika GDPR kurallarını kontrol etsin. 5) Scorer modeli filo büyüklüğü ağırlıklı güncelesin. 6) Response Tracker hot lead alarm sistemi kursun."},
        {"agent": "Recon Agent", "text": "Orchestrator'ın planına bir ekleme yapayayım: Her yeni pazara girmeden önce ben bir 'pazar profili' oluşturuyorum — hedef sektördeki şirket sayısı, ortalama filo büyüklüğü, dijital olgunluk seviyesi. Bu profili Scorer'a ve Copywriter'a vereceğim ki stratejilerini buna göre uyarlasınlar."},
        {"agent": "AI Quality Control", "text": "Son bir öneri: her yeni şablon için QC benchmark'ı oluşturalım. Minimum skor 90 olarak kalacak ama sektöre özel spam kelime listeleri de hazırlamalıyız. Nakliye sektörü için 'bedava', 'acil' gibi kelimeler spam tetikleyicisi değilken, finans sektöründe bunlar sorun yaratır. Bu list'i güncelde tutacağım."},
        {"agent": "Lead Finder", "text": "Recon Agent'ın pazar profili fikri çok iyi! Ben de tarama yaparken bu profil bilgisini kullanarak daha hedefli aramalar yapabilirim. Mesela 50+ araçlı şirketleri öncelikli tarayabilirim. Scorer'dan gelen feedback'le tarama parametrelerimi sürekli optimize edeceğim."},
        {"agent": "Follow-Up Engine", "text": "Bir brainstorm fikrim daha var: follow-up serisine 'case study' adımı ekleyelim. 5. gün gerçek bir başarı hikayesi paylaşalım — 'X şirket filo takip sistemiyle yakıt maliyetlerini %15 düşürdü' gibi. Bu güven oluşturur ve satışı hızlandırır."},
        {"agent": "AI Copywriter", "text": "Follow-Up Engine'in case study fikri harika! Ben de bu case study'leri Recon Agent'ın topladığı sektör verilerine göre kişiselleştirebilirim. Nakliye şirketine nakliye case study'si, lojistik firmasına lojistik case study'si göndeririz. Hemen yazmaya başlıyorum."},
        {"agent": "A/B Test Engine", "text": "Son olarak: yeni şablonlar ve case study'ler hazır olduğunda, hepsini sistematik olarak test edeceğim. Sektör×Şablon×CTA matrisinde tam bir A/B test planı oluşturuyorum. 2 hafta içinde istatistiksel olarak anlamlı sonuçlar elde edebiliriz."},
        {"agent": "Orchestrator", "text": "Mükemmel bir toplantı oldu! Herkes çok değerli fikirler sundu. Aksiyon planı netleşti, görev dağılımı yapıldı. Bir sonraki toplantıda ilk sonuçları değerlendireceğiz. Herkese teşekkürler — haydi işe koyulalım! 🚀"},
    ]


def _generate_continuation_meeting(round_num, stats):
    """Toplantı devam mesajları üretir — her round farklı konular."""
    total_leads = stats.get('total_leads', 0) if isinstance(stats, dict) else 0

    if round_num == 1:
        return [
            {"agent": "Response Tracker", "text": "Gelen yanıtları detaylı analiz ettim. 'İlgili' yanıtların %60'ı ilk 24 saat içinde geliyor. Özellikle 'fiyat bilgisi istiyorum' diyen lead'ler en yüksek dönüşüm potansiyeline sahip. Bu lead'leri otomatik olarak 'hot' kategorisine taşıyorum."},
            {"agent": "Compliance (AVG)", "text": "GDPR uyumu tam durumda. Unsubscribe oranımız %0.3 ile sektör ortalamasının çok altında. Ancak yeni pazarlara açılırsak, Almanya'nın Bundesdatenschutzgesetz (BDSG) kurallarını da kontrol etmem gerekiyor. Double opt-in gereksinimi olabilir."},
            {"agent": "Lead Scorer", "text": "Scoring modelimi güncelledim. Yeni ağırlıklar: filo büyüklüğü ×3, web varlığı ×2, kişisel email ×2.5. Bu değişiklikle hot lead tespit oranı %40 artması bekleniyor. Recon Agent'ın verilerini de entegre etmeye başladım."},
            {"agent": "AI Copywriter", "text": "Scorer'ın yeni modeline göre email tonunu da ayarlayacağım. Yüksek skorlu lead'ler için daha cesur ve direkt CTA, orta skorlular için eğitici içerik, düşük skorlular için awareness kampanyası yapacağım. 3 farklı ton stratejisi hazırlıyorum."},
            {"agent": "Watchdog", "text": "Tüm bu değişiklikleri izliyorum. Sistem kaynak kullanımı normal seviyelerde. Yeni scoring modeli CPU kullanımını %5 artırdı ama kabul edilebilir seviyede. Herhangi bir anomali tespit edersem hemen bildireceğim."},
        ]
    elif round_num == 2:
        return [
            {"agent": "Recon Agent", "text": "Belçika pazar araştırması tamamlandı. Flaman bölgesinde 340+ potansiyel lojistik/nakliye şirketi var. Bunların %65'inin web sitesi, %40'ının LinkedIn profili bulunuyor. En verimli segment: 20-100 araçlı orta ölçekli filolar."},
            {"agent": "Lead Finder", "text": f"Recon Agent'ın Belçika raporuna dayanarak pilot taramayı başlatmaya hazırım. Mevcut {total_leads} lead'e ek olarak Antwerp ve Gent'ten minimum 50 yeni lead bulabilirim. Tarama parametreleri Scorer'ın yeni modeline göre optimize edilecek."},
            {"agent": "A/B Test Engine", "text": "İlk A/B test sonuçları geldi. Sektöre özel şablonlar generic şablonlara göre %32 daha yüksek açılma oranı sağlıyor. Emoji kullanımı konu başlığında +%12 açılma sağlıyor. Soru formatı en iyi performans gösteren format olmaya devam ediyor."},
            {"agent": "Follow-Up Engine", "text": "Yeni follow-up serisini test ettim. Case study adımı ekledikten sonra 5. gün follow-up'larında yanıt oranı %35 arttı! Bu çok önemli bir gelişme. Sektöre özel case study'leri tüm follow-up serilerine entegre ediyorum."},
            {"agent": "Orchestrator", "text": "Harika gelişmeler! İlk sonuçlar stratejimizin doğru olduğunu gösteriyor. Belçika pilot taramasını onaylıyorum. Tüm agent'lar bu sonuçları kendi stratejilerine yansıtsın. Bir sonraki raporlamayı 48 saat içinde yapacağız."},
        ]
    elif round_num == 3:
        return [
            {"agent": "AI Quality Control", "text": "Sektöre özel spam kelime listelerini güncelledim. Nakliye sektörü için 15 yeni kelime eklendi. İlginç bir bulgu: 'gratis proefperiode' ifadesi Hollanda'da spam olarak algılanmıyor ama Belçika'da tetikliyor. Bölgesel farklılıkları dikkate alıyorum."},
            {"agent": "AI Copywriter", "text": "Quality Control'ün bölgesel spam listesi çok kritik. Belçika şablonlarını buna göre revize ediyorum. Ayrıca Flaman Hollandacası ile Standart Hollandaca arasındaki tonlama farklarını da dahil ediyorum — küçük detaylar ama büyük fark yaratıyor."},
            {"agent": "Response Tracker", "text": "Yeni bir trend fark ettim: video içerikli email'lere yanıt oranı text-only email'lerin 2.4 katı. Bir sonraki iterasyonda kısa tanıtım videosu linki eklemeyi deneyebilir miyiz? Bu Copywriter ve A/B Test Engine ile koordine edilmeli."},
            {"agent": "Lead Scorer", "text": "Son 1 haftanın verilerine göre model doğruluk oranı %78'den %89'a çıktı. Yeni ağırlıklar çalışıyor. Hot lead tespit süremiz ortalama 2.3 saatten 45 dakikaya düştü. Bu sayede Follow-Up Engine daha hızlı devreye girebiliyor."},
            {"agent": "Watchdog", "text": "Performans raporu: son 24 saatte 0 hata, 0 downtime. API response time ortalaması 1.2 saniye. Veritabanı boyutu stabil. Tüm metrikler yeşil bölgede. Sistemi güvenle ölçeklendirebiliriz."},
            {"agent": "Orchestrator", "text": "Bu toplantıyı tarihe geçecek bir toplantı olarak değerlendiriyorum. Her agent'ın katkısı somut ve ölçülebilir iyileştirmeler sağladı. Görev dağılımı net, öncelikler belirli. Herkese teşekkür ediyorum — birlikte başaracağız! 💪🚀"},
        ]
    elif round_num == 4:
        return [
            {"agent": "Lead Finder", "text": f"Belçika pilot taraması tamamlandı! 67 yeni lead bulundu, toplam lead sayımız artık {total_leads + 67}. Antwerp'ten 38, Gent'ten 29 lead geldi. Bunların %72'si web sitesine sahip şirketler — Recon Agent'ın tahminlerinin üzerinde."},
            {"agent": "Recon Agent", "text": "Belçika lead'lerinin derinlemesine profillerini oluşturdum. Çok ilginç bir bulgu: Belçikalı şirketlerin %55'i hâlâ Excel ile filo yönetimi yapıyor. Bu bizim için büyük bir fırsat — 'Excel'den dijitale geçiş' mesajı çok etkili olabilir."},
            {"agent": "AI Copywriter", "text": "Recon Agent'ın 'Excel'den dijitale geçiş' bulgusu altın değerinde! Hemen bu açıyla yeni bir şablon hazırlıyorum. 'Hâlâ Excel kullanıyor musunuz? X şirket gibi dijital filo yönetimine geçerek maliyetlerini %25 düşürdü' — bu çok güçlü bir hook."},
            {"agent": "A/B Test Engine", "text": "Copywriter'ın yeni şablonunu hemen test planına ekledim. 'Excel karşılaştırma' açısı vs 'genel verimlilik' açısı olarak A/B testi yapacağız. Tahminim: Excel açısı çok daha iyi performans gösterecek çünkü doğrudan ağrı noktasına değiniyor."},
            {"agent": "Orchestrator", "text": "Mükemmel iş çıkardınız! Belçika pilotu başarılı, yeni stratejiler netleşiyor. Bir sonraki adım: Hamburg ve Düsseldorf pilot taraması. Lead Finder ve Recon Agent bu iki şehrin profilini çıkarsın. Toplantıyı kapatıyorum — harika bir brainstorming oldu! 🎯"},
        ]
    else:
        return [
            {"agent": "Watchdog", "text": "Toplantı son özeti: tüm agent'lar tam performansta çalışıyor. Son 7 günde 0 kritik hata, 0 downtime. API kullanımı optimum seviyede. Belçika pilot taraması başarıyla tamamlandı. Sistem yeni pazarlara açılmaya hazır."},
            {"agent": "AI Copywriter", "text": "Son notlarımı paylaşıyorum: 5 yeni sektöre özel şablon, 3 case study, ve 'Excel'den dijitale geçiş' kampanyası hazır. A/B testlerden gelen data ile sürekli optimize edeceğim. Herkesin katkısı için teşekkürler!"},
            {"agent": "Orchestrator", "text": "Bu beyin fırtınası çok verimli geçti. Her agent'ın uzmanlığı birbirini tamamladı ve güçlendirdi. Aksiyon planı net, görevler dağıtıldı, hedefler belirlendi. Bir sonraki toplantıda sonuçları değerlendireceğiz. Toplantı bitti — hadi işe! 🚀🎯💪"},
        ]


# ─── A/B TEST ──────────────────────────────────────────────────
@app.route("/api/ab-test/status", methods=["GET"])
def get_ab_test_status():
    """A/B test durumu ve sonuçları."""
    status = ab_test.get_status()
    variant_stats = db.get_open_rates_by_variant()
    return jsonify({**status, "variant_stats": variant_stats})


@app.route("/api/ab-test/reset", methods=["POST"])
def reset_ab_test():
    ab_test.reset()
    return jsonify({"success": True, "message": "A/B test sıfırlandı"})


# ─── CAMPAIGN ──────────────────────────────────────────────────
@app.route("/api/campaign/start", methods=["POST"])
def start_campaign():
    if campaign_state["running"]:
        return jsonify({"error": "Kampanya zaten çalışıyor"}), 409

    data = request.json or {}
    limit = data.get("limit", config.DAILY_SEND_LIMIT)

    campaign_state["running"] = True
    campaign_state["stats"] = {
        "total_leads": 0, "processed": 0, "sent": 0,
        "skipped_compliance": 0, "skipped_quality": 0, "failed": 0,
    }

    def run():
        try:
            from agents.orchestrator import Orchestrator
            orch = Orchestrator()
            leads_file = _find_leads_file()
            stats = orch.run_campaign(leads_file=leads_file, max_send=limit)
            campaign_state["stats"] = {
                "total_leads": stats.total_leads,
                "processed": stats.processed,
                "sent": stats.sent,
                "skipped_compliance": stats.skipped_compliance,
                "skipped_quality": stats.skipped_quality,
                "failed": stats.failed,
            }
            emit_event("campaign_finished", campaign_state["stats"])
        except Exception as e:
            log.error(f"Kampanya hatası: {e}")
            emit_event("campaign_error", {"error": str(e)})
        finally:
            campaign_state["running"] = False

    t = threading.Thread(target=run, daemon=True, name="CampaignThread")
    t.start()
    campaign_state["thread"] = t

    return jsonify({"success": True, "limit": limit})


@app.route("/api/campaign/stop", methods=["POST"])
def stop_campaign():
    campaign_state["running"] = False
    return jsonify({"success": True, "message": "Durdurma sinyali gönderildi"})


@app.route("/api/campaign/status", methods=["GET"])
def campaign_status():
    return jsonify({
        "running": campaign_state["running"],
        "stats": campaign_state["stats"],
    })


# ─── CONFIG ────────────────────────────────────────────────────
@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify({
        "HUMAN_REVIEW": config.HUMAN_REVIEW,
        "DAILY_SEND_LIMIT": config.DAILY_SEND_LIMIT,
        "DELAY_MIN": config.DELAY_MIN,
        "DELAY_MAX": config.DELAY_MAX,
        "SENDER_NAME": config.SENDER_NAME,
        "SENDER_EMAIL": config.SENDER_EMAIL,
        "COMPANY_NAME": config.COMPANY_NAME,
        "COMPANY_PHONE": config.COMPANY_PHONE,
        "COMPANY_WEBSITE": config.COMPANY_WEBSITE,
        "CLAUDE_MODEL": config.CLAUDE_MODEL,
        "ANTHROPIC_KEY_SET": bool(config.ANTHROPIC_API_KEY),
        "BREVO_KEY_SET": bool(config.BREVO_API_KEY),
        "QC_MIN_SCORE": config.QC_MIN_SCORE,
        "FOLLOWUP_ENABLED": config.FOLLOWUP_ENABLED,
        "SECTORS": config.SECTORS,
        "TARGET_LOCATION": config.TARGET_LOCATION,
        "MAX_LEADS_PER_SEARCH": config.MAX_LEADS_PER_SEARCH,
        "PARALLEL_CITY_WORKERS": config.PARALLEL_CITY_WORKERS,
        "TELEFOONBOEK_ENABLED": config.TELEFOONBOEK_ENABLED,
        "OPENSTREETMAP_ENABLED": config.OPENSTREETMAP_ENABLED,
        "EMAIL_VERIFY_MX": config.EMAIL_VERIFY_MX,
        "AUTO_START": config.AUTO_START,
        "AUTOMATION_INTERVAL": config.AUTOMATION_INTERVAL,
    })


@app.route("/api/config", methods=["PUT"])
def update_config():
    data = request.json or {}
    updated = []
    allowed_keys = [
        "HUMAN_REVIEW", "DAILY_SEND_LIMIT",
        "DELAY_MIN", "DELAY_MAX", "QC_MIN_SCORE",
        "AUTOMATION_INTERVAL", "AUTO_START",
    ]
    for key in allowed_keys:
        if key in data:
            setattr(config, key, data[key])
            updated.append(key)

    # .env dosyasına kalıcı olarak kaydet (server restart'ta korunur)
    if updated:
        _persist_to_env(updated, data)

    log.info(f"[CONFIG] Güncellenen ayarlar: {updated}")
    return jsonify({"success": True, "updated": updated})


def _persist_to_env(keys: list, data: dict):
    """Ayarları .env dosyasına kalıcı olarak yaz."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    try:
        # Mevcut .env oku
        env_lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                env_lines = f.readlines()

        # Güncelle veya ekle
        existing_keys = set()
        new_lines = []
        for line in env_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue
            key_part = stripped.split("=", 1)[0].strip()
            if key_part in keys:
                val = data[key_part]
                # Boolean → string
                if isinstance(val, bool):
                    val = "true" if val else "false"
                new_lines.append(f"{key_part}={val}\n")
                existing_keys.add(key_part)
            else:
                new_lines.append(line)

        # Eklenmemiş yeni key'ler
        for key in keys:
            if key not in existing_keys and key in data:
                val = data[key]
                if isinstance(val, bool):
                    val = "true" if val else "false"
                new_lines.append(f"{key}={val}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        log.info(f"[CONFIG] .env kalıcı kayıt: {keys}")
    except Exception as e:
        log.error(f"[CONFIG] .env yazma hatası: {e}")




# ─── STATS ─────────────────────────────────────────────────────
@app.route("/api/stats", methods=["GET"])
def get_stats():
    try:
        stats = db.get_stats()
    except Exception as e:
        stats = {"total_leads": 0, "total_sent": 0, "opens": 0,
                 "open_rate": 0, "hot_leads": 0, "followups_sent": 0,
                 "unsubscribe_count": 0, "error": str(e)}

    try:
        recent = db.get_recent_sent(20)
    except Exception:
        recent = []

    try:
        ab_status = ab_test.get_status()
        variant_stats = db.get_open_rates_by_variant()
    except Exception:
        ab_status = {}
        variant_stats = {}

    try:
        all_leads = db.get_all_leads()
        source_dist = {}
        for lead in all_leads:
            src = lead.get("source", "csv") or "csv"
            source_dist[src] = source_dist.get(src, 0) + 1
    except Exception:
        source_dist = {}

    try:
        unsub_count = len(compliance._unsubscribe)
    except Exception:
        unsub_count = stats.get("unsubscribe_count", 0)

    return jsonify({
        **stats,
        "recent_sent": recent,
        "ab_test": {**ab_status, "variant_stats": variant_stats},
        "unsubscribe_count": unsub_count,
        "source_distribution": source_dist,
    })



# ─── WATCHDOG ──────────────────────────────────────────────────
@app.route("/api/watchdog/status", methods=["GET"])
def get_watchdog_status():
    try:
        checks = watchdog.run_checks()
        summary = watchdog.get_summary()
        return jsonify({
            "checks": [
                {"name": c.name, "status": c.status,
                 "detail": c.detail, "checked_at": c.checked_at.isoformat()}
                for c in checks
            ],
            "summary": summary,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── LOGS ──────────────────────────────────────────────────────
@app.route("/api/logs", methods=["GET"])
def get_logs():
    """Son log satırlarını döndür."""
    log_file = os.path.join(config.LOGS_DIR, "smartmailer.log")
    if not os.path.exists(log_file):
        return jsonify({"logs": []})
    with open(log_file, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return jsonify({"logs": lines[-100:]})


# ─── FOLLOW-UP (v4.5) ─────────────────────────────────────────
@app.route("/api/followups", methods=["GET"])
def get_followups():
    stats = db.get_followup_stats()
    return jsonify(stats)


@app.route("/api/followups/detail", methods=["GET"])
def get_followup_detail():
    """Kisi bazli detayli follow-up listesi."""
    detail = db.get_followup_detail(limit=100)
    return jsonify({"followups": detail})


@app.route("/api/followups/process", methods=["POST"])
def process_followups():
    """Bekleyen follow-up'lari isle."""
    pending = follow_up.process_pending()
    return jsonify({"processed": len(pending), "followups": pending})


@app.route("/api/followups/all", methods=["GET"])
def get_all_followups():
    """Tüm follow-up kayıtlarını detaylı döndür."""
    followups = db.get_all_followups(limit=200)
    stats = db.get_followup_stats()
    return jsonify({"followups": followups, "stats": stats})

# (Eski brevo_webhook handler kaldırıldı — yeni handler line 269'da)


# ─── TRACKING STATS ──────────────────────────────────────────
@app.route("/api/tracking/stats", methods=["GET"])
def get_tracking_stats():
    """Email açılma, tıklama ve hot lead istatistikleri."""
    try:
        total_sent = db.get_sent_count()
        opens = len(db.get_events_by_type("opened", limit=10000)) + \
                len(db.get_events_by_type("open", limit=10000)) + \
                len(db.get_events_by_type("unique_opened", limit=10000))
        clicks = len(db.get_events_by_type("click", limit=10000))

        # Unique opens
        with db._conn() as conn:
            unique_opens = conn.execute(
                "SELECT COUNT(DISTINCT email) FROM events WHERE event_type IN ('opened','open','unique_opened')"
            ).fetchone()[0]
            hot_leads = conn.execute(
                "SELECT COUNT(*) FROM leads WHERE is_hot = 1"
            ).fetchone()[0]

        open_rate = round(unique_opens / total_sent * 100, 1) if total_sent > 0 else 0

        return jsonify({
            "total_sent": total_sent,
            "total_opens": opens,
            "unique_opens": unique_opens,
            "clicks": clicks,
            "hot_leads": hot_leads,
            "open_rate": open_rate,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── TÜM GİDEN MAİLLER ──────────────────────────────────────
@app.route("/api/sent/all", methods=["GET"])
def get_all_sent():
    """Tüm gönderilen emailleri draft içerikleriyle birlikte döndür."""
    sent = db.get_all_sent_with_content(limit=200)
    return jsonify({"emails": sent, "count": len(sent)})


# ─── DUPLICATE PREVENTION ────────────────────────────────────

@app.route("/api/sent/detail", methods=["GET"])
def get_sent_detail():
    """Gönderilen emailin tam detayı (içerik dahil)."""
    email = request.args.get("email", "")
    if not email:
        return jsonify({"error": "email parametresi gerekli"}), 400
    detail = db.get_sent_email_content(email)
    if not detail:
        return jsonify({"error": "Email bulunamadı"}), 404
    return jsonify(detail)


@app.route("/api/leads/source", methods=["GET"])
def get_leads_by_source():
    """Belirli bir kaynaktan gelen lead'leri döndür."""
    source = request.args.get("source", "")
    if not source:
        return jsonify({"error": "source parametresi gerekli"}), 400
    leads = db.get_leads_by_source(source, limit=200)
    return jsonify({"leads": leads, "source": source, "count": len(leads)})
@app.route("/api/duplicate/stats", methods=["GET"])
def get_duplicate_stats():
    """Duplicate önleme istatistikleri."""
    stats = db.get_duplicate_stats()
    return jsonify(stats)


@app.route("/api/duplicate/check", methods=["POST"])
def check_duplicate():
    """Bir email adresinin duplicate olup olmadığını kontrol et."""
    data = request.json or {}
    email = data.get("email", "")
    if not email:
        return jsonify({"error": "email gerekli"}), 400
    is_dup = db.is_duplicate_email(email)
    return jsonify({"email": email, "is_duplicate": is_dup})


# ─── AGENT SELF-IMPROVEMENT ──────────────────────────────────
@app.route("/api/agents/learning", methods=["GET"])
def get_agent_learnings():
    """Tüm agent öğrenme kayıtlarını döndür."""
    agent = request.args.get("agent", None)
    learnings = db.get_agent_learnings(agent_name=agent)
    performance = db.get_agent_performance()
    return jsonify({"learnings": learnings, "performance": performance})


@app.route("/api/agents/feedback", methods=["POST"])
def save_agent_feedback():
    """Kullanıcı tarafından agent feedback kaydet."""
    data = request.json or {}
    agent_name = data.get("agent_name", "")
    learning_type = data.get("type", "user_feedback")
    context = data.get("context", "")
    lesson = data.get("lesson", "")
    if not agent_name or not lesson:
        return jsonify({"error": "agent_name ve lesson gerekli"}), 400
    db.save_agent_feedback(agent_name, learning_type, context, lesson)
    return jsonify({"success": True})


# ─── RESPONSE TRACKING (v4.5) ────────────────────────────────
@app.route("/api/responses", methods=["GET"])
def get_responses():
    stats = db.get_response_stats()
    hot_leads = db.get_hot_leads()
    return jsonify({"stats": stats, "hot_leads": hot_leads})


@app.route("/api/responses/classify", methods=["POST"])
def classify_response():
    """Yaniti AI ile siniflandir."""
    data = request.json or {}
    email = data.get("email", "")
    response_text = data.get("response_text", "")
    original_subject = data.get("original_subject", "")

    if not email or not response_text:
        return jsonify({"error": "email ve response_text gerekli"}), 400

    result = response_tracker.classify_response(email, response_text, original_subject)
    emit_event("response_classified", result)
    return jsonify(result)


# ─── UNSUBSCRIBE / AFMELD SYSTEEM ─────────────────────────────
@app.route("/api/unsubscribe", methods=["POST"])
def api_unsubscribe():
    """Email adresini opt-out listesine ekle + admin'e bildirim gönder."""
    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    reason = data.get("reason", "user_request")

    if not email:
        return jsonify({"error": "Email gerekli"}), 400

    try:
        # Compliance agent'a ekle (CSV + memory)
        compliance.add_unsubscribe(email, reason)

        # DB opt_out tablosuna kaydet
        with db._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO opt_out (email, reason, ip_address) VALUES (?, ?, ?)",
                (email, reason, request.remote_addr)
            )

        # Bekleyen followup'ları iptal et
        db.cancel_pending_followups(email)

        # Admin'e bildirim emaili gönder
        _notify_admin_unsubscribe(email, reason)

        emit_event("unsubscribe", {"email": email, "reason": reason})
        log.info(f"[UNSUB] {email} listeden çıkarıldı — sebep: {reason}")

        return jsonify({"success": True, "email": email, "message": "Başarıyla listeden çıkarıldı"})
    except Exception as e:
        log.error(f"[UNSUB] Hata: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/afmelden", methods=["GET"])
@app.route("/unsubscribe", methods=["GET"])
def public_unsubscribe():
    """Afmelden sayfası — anketli unsubscribe."""
    email = request.args.get("email", "").strip().lower()
    if not email or "@" not in email:
        return """<!DOCTYPE html><html><body style="font-family:Arial;text-align:center;padding:50px">
        <h2>Ongeldige link</h2><p>Geen geldig e-mailadres gevonden.</p></body></html>""", 400

    return f'''<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Afmelden — FleetTrack Holland</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            min-height: 100vh; display: flex; align-items: center; justify-content: center;
            padding: 20px;
        }}
        .card {{
            background: #fff; border-radius: 20px; padding: 40px 48px; max-width: 520px;
            width: 100%; box-shadow: 0 25px 80px rgba(0,0,0,0.08);
        }}
        .logo {{ height: 36px; margin-bottom: 20px; }}
        h1 {{ font-size: 22px; color: #1a1a2e; margin-bottom: 6px; font-weight: 700; }}
        .subtitle {{ color: #666; font-size: 14px; margin-bottom: 24px; line-height: 1.5; }}
        .email-badge {{
            background: #f0f4ff; color: #0052CC; font-weight: 600;
            padding: 6px 14px; border-radius: 8px; font-size: 13px;
            display: inline-block; margin-bottom: 20px;
        }}
        .section-title {{ font-size: 14px; font-weight: 600; color: #333; margin-bottom: 12px; }}
        .radio-group {{ display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; }}
        .radio-item {{
            display: flex; align-items: center; gap: 10px;
            padding: 10px 14px; border-radius: 10px; cursor: pointer;
            border: 1.5px solid #e8e8e8; transition: all 0.2s; font-size: 14px; color: #444;
        }}
        .radio-item:hover {{ border-color: #0052CC; background: #f8faff; }}
        .radio-item input[type="radio"] {{ width: 16px; height: 16px; accent-color: #0052CC; }}
        .radio-item.selected {{ border-color: #0052CC; background: #f0f4ff; }}
        .freq-group {{ display: flex; gap: 8px; margin-bottom: 20px; }}
        .freq-btn {{
            flex: 1; padding: 10px; border-radius: 10px; cursor: pointer;
            border: 1.5px solid #e8e8e8; text-align: center; font-size: 13px;
            color: #555; transition: all 0.2s; background: #fff;
        }}
        .freq-btn:hover {{ border-color: #0052CC; }}
        .freq-btn.selected {{ border-color: #0052CC; background: #f0f4ff; color: #0052CC; font-weight: 600; }}
        textarea {{
            width: 100%; border: 1.5px solid #e8e8e8; border-radius: 10px;
            padding: 12px; font-family: inherit; font-size: 14px;
            resize: vertical; min-height: 70px; margin-bottom: 20px;
        }}
        textarea:focus {{ border-color: #0052CC; outline: none; }}
        .btn {{
            width: 100%; padding: 14px; border: none; border-radius: 12px;
            background: linear-gradient(135deg, #c0392b 0%, #e74c3c 100%);
            color: #fff; font-size: 15px; font-weight: 600; cursor: pointer;
            transition: transform 0.15s, box-shadow 0.15s;
        }}
        .btn:hover {{ transform: translateY(-1px); box-shadow: 0 4px 16px rgba(231,76,60,0.3); }}
        .footer {{ margin-top: 24px; text-align: center; font-size: 11px; color: #aaa; line-height: 1.5; }}
        .footer a {{ color: #0052CC; text-decoration: none; }}
        .success-msg {{ display: none; text-align: center; }}
        .success-msg .check {{ font-size: 56px; margin-bottom: 12px; }}
        .success-msg h2 {{ color: #27ae60; font-size: 20px; margin-bottom: 8px; }}
        .success-msg p {{ color: #666; font-size: 14px; line-height: 1.5; }}
    </style>
</head>
<body>
    <div class="card">
        <img src="https://www.fleettrackholland.nl/logo512.png" alt="FleetTrack Holland" class="logo">
        <div id="surveyForm">
            <h1>Uitschrijven</h1>
            <p class="subtitle">Het spijt ons dat u weggaat. Uw feedback helpt ons verbeteren.</p>
            <div class="email-badge">{email}</div>
            <p class="section-title">Waarom schrijft u zich uit?</p>
            <div class="radio-group" id="reasonGroup">
                <label class="radio-item" onclick="selectReason(this)">
                    <input type="radio" name="reason" value="too_many"> Ik ontvang te veel e-mails
                </label>
                <label class="radio-item" onclick="selectReason(this)">
                    <input type="radio" name="reason" value="not_relevant"> De inhoud is niet relevant voor mij
                </label>
                <label class="radio-item" onclick="selectReason(this)">
                    <input type="radio" name="reason" value="already_have"> Ik heb al een GPS-trackingoplossing
                </label>
                <label class="radio-item" onclick="selectReason(this)">
                    <input type="radio" name="reason" value="bad_timing"> De e-mails komen op een slecht moment
                </label>
                <label class="radio-item" onclick="selectReason(this)">
                    <input type="radio" name="reason" value="not_requested"> Ik heb hier niet om gevraagd
                </label>
                <label class="radio-item" onclick="selectReason(this)">
                    <input type="radio" name="reason" value="other"> Anders
                </label>
            </div>
            <p class="section-title">Hoe ervaart u de frequentie van onze e-mails?</p>
            <div class="freq-group">
                <div class="freq-btn" onclick="selectFreq(this,'te_vaak')">Te vaak</div>
                <div class="freq-btn" onclick="selectFreq(this,'net_goed')">Was prima</div>
                <div class="freq-btn" onclick="selectFreq(this,'onbekend')">Geen idee</div>
            </div>
            <textarea id="feedbackText" placeholder="Heeft u nog suggesties? (optioneel)"></textarea>
            <button class="btn" onclick="submitSurvey()">Uitschrijven</button>
        </div>
        <div class="success-msg" id="successMsg">
            <div class="check">&#10003;</div>
            <h2>U bent afgemeld</h2>
            <p>Het e-mailadres <strong>{email}</strong> is verwijderd uit onze mailinglijst.</p>
            <p style="margin-top:12px">U ontvangt geen verdere e-mails meer.</p>
            <p style="font-size:13px;color:#999;margin-top:16px">
                Per ongeluk? <a href="mailto:sales@fleettrackholland.nl">Neem contact op</a>
            </p>
        </div>
        <div class="footer">FleetTrack Holland | KVK: 88606902 |
            <a href="https://www.fleettrackholland.nl">www.fleettrackholland.nl</a>
        </div>
    </div>
    <script>
        let selectedReason='', selectedFreq='';
        function selectReason(el){{
            document.querySelectorAll('.radio-item').forEach(i=>i.classList.remove('selected'));
            el.classList.add('selected');
            selectedReason=el.querySelector('input').value;
        }}
        function selectFreq(el,val){{
            document.querySelectorAll('.freq-btn').forEach(b=>b.classList.remove('selected'));
            el.classList.add('selected');
            selectedFreq=val;
        }}
        function submitSurvey(){{
            fetch('/api/unsubscribe/survey',{{
                method:'POST',
                headers:{{'Content-Type':'application/json'}},
                body:JSON.stringify({{
                    email:'{email}',
                    reason_code:selectedReason||'not_specified',
                    reason_text:document.getElementById('feedbackText').value,
                    frequency_feedback:selectedFreq||'onbekend'
                }})
            }}).finally(()=>{{
                document.getElementById('surveyForm').style.display='none';
                document.getElementById('successMsg').style.display='block';
            }});
        }}
    </script>
</body>
</html>'''


@app.route("/api/opt-out/list", methods=["GET"])
def get_optout_list():
    """Tüm opt-out kayıtlarını listele."""
    try:
        with db._conn() as conn:
            rows = conn.execute("SELECT * FROM opt_out ORDER BY created_at DESC").fetchall()
            return jsonify({"opt_outs": [dict(r) for r in rows], "count": len(rows)})
    except Exception:
        return jsonify({"opt_outs": [], "count": len(compliance._unsubscribe)})

# ─── UNSUBSCRIBE SURVEY API ──────────────────────────────────
@app.route("/api/unsubscribe/survey", methods=["POST"])
def api_unsubscribe_survey():
    """Anketli unsubscribe — survey yanıtı + opt-out işlemi."""
    data = request.json or {}
    email = (data.get("email") or "").strip().lower()
    reason_code = data.get("reason_code", "not_specified")
    reason_text = data.get("reason_text", "")
    frequency_feedback = data.get("frequency_feedback", "onbekend")

    if not email or "@" not in email:
        return jsonify({"error": "Geldig email gerekli"}), 400

    try:
        # 1. Survey kaydet
        db.save_survey(
            email=email, reason_code=reason_code,
            reason_text=reason_text, frequency_feedback=frequency_feedback,
            survey_data=data,
        )
        # 2. Unsubscribe
        compliance.add_unsubscribe(email, f"survey_{reason_code}")
        with db._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO opt_out (email, reason, ip_address) VALUES (?, ?, ?)",
                (email, f"survey_{reason_code}", request.remote_addr)
            )
        db.cancel_pending_followups(email)
        # 3. Admin bildirim
        REASON_NL = {
            "too_many": "Te veel e-mails", "not_relevant": "Niet relevant",
            "already_have": "Heeft al GPS", "bad_timing": "Slecht moment",
            "not_requested": "Niet aangevraagd", "other": "Anders",
        }
        _notify_admin_unsubscribe(email, f"{REASON_NL.get(reason_code, reason_code)} | {reason_text[:100]}")
        emit_event("unsubscribe", {"email": email, "reason": reason_code, "frequency": frequency_feedback})
        log.info(f"[SURVEY] {email} — reden: {reason_code}, freq: {frequency_feedback}")
        return jsonify({"success": True, "email": email})
    except Exception as e:
        log.error(f"[SURVEY] Hata: {e}")
        try:
            compliance.add_unsubscribe(email, "survey_error")
        except Exception:
            pass
        return jsonify({"success": True, "email": email})


@app.route("/api/surveys/stats")
def api_survey_stats():
    """Survey istatistikleri."""
    try:
        return jsonify(db.get_survey_stats())
    except Exception as e:
        return jsonify({"total_surveys": 0, "reasons": {}, "sectors": {}})


@app.route("/api/churn/report")
def api_churn_report():
    """Churn analiz raporu."""
    try:
        from agents.churn_analyst import ChurnAnalyst
        return jsonify(ChurnAnalyst().generate_churn_report())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/strategy/plan")
def api_strategy_plan():
    """Gönderim strateji planı."""
    try:
        from agents.sending_strategist import SendingStrategist
        return jsonify(SendingStrategist().get_strategy_report())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _notify_admin_unsubscribe(email: str, reason: str):
    """Opt-out olduğunda admin'e email ile bildir."""
    try:
        import requests as _req
        _req.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": config.BREVO_API_KEY, "Content-Type": "application/json"},
            json={
                "sender": {"name": config.SENDER_NAME, "email": config.SENDER_EMAIL},
                "to": [{"email": config.SENDER_EMAIL}],
                "subject": f"⚠️ Opt-out Bildirimi: {email}",
                "htmlContent": f"""
                <div style='font-family:Arial;padding:20px'>
                    <h2 style='color:#e17055'>⚠️ Yeni Opt-out</h2>
                    <p><strong>Email:</strong> {email}</p>
                    <p><strong>Sebep:</strong> {reason}</p>
                    <p><strong>Tarih:</strong> {__import__('datetime').datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
                    <hr>
                    <p style='color:#888'>Bu kişi artık mail almayacak. Tüm bekleyen follow-up'lar iptal edildi.</p>
                </div>"""
            },
            timeout=10
        )
        log.info(f"[UNSUB] Admin bildirimi gönderildi: {email}")
    except Exception as e:
        log.error(f"[UNSUB] Admin bildirim hatası: {e}")


# ─── EMAIL ICERIK GORUNTULEME ─────────────────────────────────
@app.route("/api/sent/<path:email>/content", methods=["GET"])
def get_sent_content(email):
    """Gönderilmiş email'in içeriğini döndür (draft'tan al)."""
    try:
        with db._conn() as conn:
            # Önce sent_log'dan bilgiyi al
            sent = conn.execute(
                "SELECT * FROM sent_log WHERE email = ? ORDER BY sent_at DESC LIMIT 1",
                (email,)
            ).fetchone()

            # Draft'taki içeriği al
            draft = conn.execute(
                "SELECT subject_a, subject_b, subject_c, chosen_subject, body_html, body_text, "
                "qc_score, ab_variant, created_at FROM drafts WHERE email = ? ORDER BY created_at DESC LIMIT 1",
                (email,)
            ).fetchone()

            result = {
                "email": email,
                "sent_info": dict(sent) if sent else None,
                "draft_content": dict(draft) if draft else None,
            }
            return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── AGENTS WATCHDOG (ayrı endpoint) ──────────────────────────
@app.route("/api/agents/watchdog-report", methods=["GET"])
def get_watchdog_health_report():
    """Watchdog sağlık raporu."""
    try:
        report = watchdog.run_healthcheck() if hasattr(watchdog, 'run_healthcheck') else {}
        return jsonify(report)
    except Exception as e:
        log.error(f"[WATCHDOG] Rapor hatası: {e}")
        return jsonify({"error": str(e)}), 500


# ─── SENT EMAILS (Giden Mailler) ──────────────────────────────
@app.route("/api/sent/all")
def api_sent_all():
    """Tüm gönderilen emailleri döndür (Giden Mailler sayfası için)."""
    try:
        emails = db.get_all_sent_with_content()
        # Frontend {emails: [...], count: N} formatı bekliyor
        return jsonify({
            "emails": emails,
            "count": len(emails),
        })
    except Exception as e:
        log.error(f"[SENT ALL] Hata: {e}")
        import traceback
        log.error(traceback.format_exc())
        return jsonify({"emails": [], "count": 0})


@app.route("/api/sent/<path:email>/content")
def api_sent_content(email):
    """Belirli bir gönderilen emailin içeriğini döndür."""
    try:
        # Drafts tablosundan email içeriğini al
        with db._conn() as conn:
            row = conn.execute("""
                SELECT d.body_html, d.body_text, d.qc_score, d.chosen_subject,
                       d.subject_a, d.subject_b, d.subject_c,
                       s.subject, s.company, s.sector, s.method, s.sent_at
                FROM sent_log s
                LEFT JOIN drafts d ON LOWER(s.email) = LOWER(d.email)
                WHERE LOWER(s.email) = LOWER(?)
                ORDER BY s.sent_at DESC LIMIT 1
            """, (email,)).fetchone()
            if row:
                return jsonify(dict(row))
            # Sadece drafts tablosundan da deneyebiliriz
            row2 = conn.execute("""
                SELECT body_html, body_text, qc_score, chosen_subject,
                       subject_a, subject_b, subject_c,
                       '' as method, '' as company, '' as sector,
                       created_at as sent_at
                FROM drafts WHERE LOWER(email) = LOWER(?)
                ORDER BY created_at DESC LIMIT 1
            """, (email,)).fetchone()
            if row2:
                return jsonify(dict(row2))
            return jsonify({"error": "Email bulunamadı"}), 404
    except Exception as e:
        log.error(f"[SENT CONTENT] {email} hatası: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/duplicate/stats")
def api_duplicate_stats():
    """Duplicate engelleme istatistiklerini döndür."""
    try:
        stats = db.get_duplicate_stats()
        return jsonify(stats)
    except Exception as e:
        log.error(f"[DUPLICATE STATS] Hata: {e}")
        return jsonify({"total_sent": 0, "unique_emails": 0, "duplicates_blocked": 0})


# ─── UNSUBSCRIBE (AFMELDEN) ───────────────────────────────────
@app.route("/unsubscribe")
def unsubscribe_page():
    """Email aboneliğinden çıkma sayfası — kullanıcı dostu, Hollandaca."""
    email = request.args.get("email", "").strip().lower()
    if not email or "@" not in email:
        return """<!DOCTYPE html><html><body style="font-family:Arial;text-align:center;padding:50px">
        <h2>⚠️ Ongeldige link</h2><p>Geen geldig e-mailadres gevonden.</p></body></html>""", 400

    # Unsubscribe işlemi
    db.add_unsubscribe(email, reason="email_link")
    log.info(f"[UNSUBSCRIBE] {email} afgemeld")

    return f"""<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Afgemeld — FleetTrack Holland</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh; display: flex; align-items: center; justify-content: center;
        }}
        .card {{
            background: #fff; border-radius: 16px; padding: 48px; max-width: 500px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.1); text-align: center;
        }}
        .logo {{ height: 40px; margin-bottom: 24px; }}
        .check {{ font-size: 64px; margin-bottom: 16px; }}
        h1 {{ font-size: 24px; color: #1a1a2e; margin-bottom: 12px; }}
        .email {{ color: #0052CC; font-weight: 600; }}
        p {{ color: #555; line-height: 1.6; margin-bottom: 16px; }}
        .footer {{ margin-top: 32px; font-size: 12px; color: #999; }}
    </style>
</head>
<body>
    <div class="card">
        <img src="https://www.fleettrackholland.nl/logo512.png" alt="FleetTrack Holland" class="logo">
        <div class="check">✅</div>
        <h1>U bent afgemeld</h1>
        <p>Het e-mailadres <span class="email">{email}</span> is succesvol verwijderd uit onze mailinglijst.</p>
        <p>U ontvangt geen verdere e-mails meer van FleetTrack Holland.</p>
        <p style="font-size:14px;color:#888;">
            Heeft u dit per ongeluk gedaan? Neem contact op via
            <a href="mailto:sales@fleettrackholland.nl" style="color:#0052CC">sales@fleettrackholland.nl</a>
        </p>
        <div class="footer">
            FleetTrack Holland — Blokfluit 31, 3068KZ Rotterdam<br>
            KVK: 88606902 — <a href="https://www.fleettrackholland.nl" style="color:#0052CC">www.fleettrackholland.nl</a>
        </div>
    </div>
</body>
</html>"""


@app.route("/api/unsubscribes")
def api_unsubscribes():
    """Unsubscribe listesini döndür (admin dashboard için)."""
    try:
        return jsonify({
            "count": db.get_unsubscribe_count(),
            "emails": db.get_all_unsubscribed(),
        })
    except Exception as e:
        log.error(f"[UNSUBSCRIBES] Hata: {e}")
        return jsonify({"count": 0, "emails": []})


# ─── PREVIEW EMAIL (ÖNIZLEME) ────────────────────────────────
@app.route("/api/campaign/preview", methods=["POST"])
def preview_email():
    """Bir lead için email önizlemesi oluştur — göndermeden."""
    try:
        data = request.json or {}
        email = data.get("email", "").strip()
        if not email:
            return jsonify({"error": "Email adresi gerekli"}), 400

        lead = db.get_lead_by_email(email)
        if not lead:
            lead = {"email": email, "company": "", "sector": ""}

        lead_dict = dict(lead) if hasattr(lead, 'keys') else lead

        # Draft oluştur (Claude API)
        log.info(f"[PREVIEW] Draft oluşturuluyor: {email}")
        draft = copywriter.write(lead_dict)
        if not draft:
            return jsonify({"error": "Draft oluşturulamadı"}), 500

        # QC skoru
        try:
            qc = quality.check(draft)
            qc_score = qc.get("score", 0) if isinstance(qc, dict) else (qc.score if hasattr(qc, 'score') else 0)
        except Exception:
            qc_score = 0

        from dataclasses import asdict
        draft_data = asdict(draft) if hasattr(draft, '__dataclass_fields__') else draft

        return jsonify({
            "success": True,
            "email": email,
            "company": lead_dict.get("company", lead_dict.get("Company", "")),
            "subject_a": draft_data.get("subject_a", ""),
            "subject_b": draft_data.get("subject_b", ""),
            "subject_c": draft_data.get("subject_c", ""),
            "chosen_subject": draft_data.get("chosen_subject", ""),
            "body_html": draft_data.get("body_html", ""),
            "body_text": draft_data.get("body_text", ""),
            "qc_score": qc_score,
        })
    except Exception as e:
        log.error(f"[PREVIEW] Hata: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ─── SEND TO SELECTED LEADS ───────────────────────────────────
@app.route("/api/campaign/send-selected", methods=["POST"])
def send_to_selected():
    """Seçili leadlere email gönder."""
    data = request.json or {}
    emails = data.get("emails", [])
    if not emails:
        return jsonify({"error": "Email listesi boş"}), 400

    from core.send_engine import SendEngine, EmailMessage
    from dataclasses import asdict
    send_eng = SendEngine()

    sent_count = 0
    errors = 0
    error_details = []
    for email in emails:
        try:
            lead = db.get_lead_by_email(email)
            if not lead:
                lead = {"email": email, "company": "", "sector": ""}

            lead_dict = dict(lead) if hasattr(lead, 'keys') else lead

            # Unsubscribe kontrolü
            if db.is_unsubscribed(email):
                log.info(f"[SEND-SELECTED] Unsubscribed: {email} — atlandı")
                continue

            # Duplicate kontrolü
            if db.is_duplicate_email(email):
                log.info(f"[SEND-SELECTED] Duplicate: {email} — atlandı")
                continue

            # Draft oluştur (Claude API çağrısı)
            log.info(f"[SEND-SELECTED] Draft oluşturuluyor: {email}")
            draft = copywriter.write(lead_dict)
            if not draft:
                log.warning(f"[SEND-SELECTED] Draft oluşturulamadı: {email}")
                errors += 1
                error_details.append(f"{email}: Draft oluşturulamadı")
                continue

            # A/B test ile konu seç
            chosen_subject = getattr(draft, 'chosen_subject', None) or getattr(draft, 'subject_a', email)
            body_html = getattr(draft, 'body_html', '')
            body_text = getattr(draft, 'body_text', '')

            # Draft'ı DB'ye kaydet (dataclass → dict)
            try:
                draft_dict = asdict(draft) if hasattr(draft, '__dataclass_fields__') else dict(draft)
                db.save_draft(email, draft_dict)
            except Exception as save_err:
                log.warning(f"[SEND-SELECTED] Draft kayıt hatası (görmezden geliniyor): {save_err}")

            # EmailMessage oluştur ve gönder
            msg = EmailMessage(
                to_email=email,
                to_name=lead_dict.get("company", ""),
                subject=chosen_subject,
                html_body=body_html,
                text_body=body_text,
                lead_id=email,
            )
            log.info(f"[SEND-SELECTED] Gönderiliyor: {email} — Konu: {chosen_subject[:50]}")
            result = send_eng.send(msg)

            if result.success:
                sent_count += 1
                # Gönderimi DB'ye logla
                db.log_sent(
                    email=email,
                    company=lead_dict.get("company", ""),
                    sector=lead_dict.get("sector", ""),
                    subject=chosen_subject,
                    method=result.method,
                    message_id=result.message_id,
                    ab_variant="A",
                )
                # Lead durumunu güncelle
                try:
                    db.update_lead_status(email, "sent")
                except Exception:
                    pass
                emit_event("email_sent", {"email": email, "company": lead_dict.get("company", "")})
                log.info(f"[SEND-SELECTED] ✅ {email} — {result.method} — ID: {result.message_id}")
            else:
                errors += 1
                error_details.append(f"{email}: {result.error}")
                log.warning(f"[SEND-SELECTED] ❌ {email} — {result.error}")
        except Exception as e:
            import traceback
            log.error(f"[SEND-SELECTED] {email} HATA: {e}\n{traceback.format_exc()}")
            errors += 1
            error_details.append(f"{email}: {str(e)}")

    log.info(f"[SEND-SELECTED] Sonuç: {sent_count} gönderildi, {errors} hata")
    return jsonify({
        "success": True,
        "sent": sent_count,
        "errors": errors,
        "error_details": error_details[:5],  # İlk 5 hata detayı
    })


# ─── SKIP LEADS ───────────────────────────────────────────────
@app.route("/api/leads/skip", methods=["POST"])
def skip_leads():
    """Seçili leadleri atla (send_status = 'skipped')."""
    data = request.json or {}
    emails = data.get("emails", [])
    skipped = 0
    for email in emails:
        try:
            db.update_lead_status(email, "skipped") if hasattr(db, 'update_lead_status') else None
            skipped += 1
        except Exception:
            pass
    return jsonify({"success": True, "skipped": skipped})



# ─── FOLLOWUPS STATS ──────────────────────────────────────────
@app.route("/api/followups/stats", methods=["GET"])
def get_followups_stats():
    """Follow-up istatistiklerini döner."""
    try:
        stats = follow_up.get_stats() if hasattr(follow_up, 'get_stats') else {}
        return jsonify(stats if stats else {"pending": 0, "sent": 0, "cancelled": 0})
    except Exception as e:
        return jsonify({"pending": 0, "sent": 0, "cancelled": 0})


# ─── HEALTH CHECK (tüm modülleri test eder) ──────────────────
@app.route("/api/health/check", methods=["GET"])
def deep_health_check():
    """Tüm modüllerin import edilebilirliğini test eder."""
    results = {}
    modules = [
        "agents.orchestrator",
        "agents.lead_finder",
        "agents.copywriter_agent",
        "agents.quality_agent",
        "agents.compliance_agent",
        "agents.lead_scorer",
        "agents.response_tracker",
        "agents.watchdog_agent",
        "core.database",
        "core.send_engine",
        "core.template_engine",
        "core.followup_engine",
        "core.ab_test_engine",
    ]
    for mod in modules:
        try:
            __import__(mod)
            results[mod] = "OK"
        except Exception as e:
            results[mod] = f"HATA: {e}"

    # Orchestrator init test
    try:
        from agents.orchestrator import Orchestrator
        orch = Orchestrator()
        results["orchestrator_init"] = "OK"
    except Exception as e:
        results["orchestrator_init"] = f"HATA: {e}"

    all_ok = all(v == "OK" for v in results.values())
    return jsonify({"healthy": all_ok, "modules": results})


# ─── LEAD DISCOVERY (v4.5 — SINIRSIZ) ────────────────────────
@app.route("/api/leads/discover", methods=["POST"])
def discover_leads():
    """Web scraping ile sinirsiz lead kesfi."""
    data = request.json or {}
    sector = data.get("sector", "transport")
    location = data.get("location", "Nederland")

    results = lead_finder.discover_leads(sector, location)
    stats = lead_finder.get_discovery_stats()
    emit_event("leads_discovered", {"count": len(results), "stats": stats})
    return jsonify({"discovered": results, "count": len(results), "stats": stats})


@app.route("/api/leads/discover/stats", methods=["GET"])
def get_discovery_stats():
    """Kesif istatistiklerini dondur."""
    return jsonify(lead_finder.get_discovery_stats())


# ─── TAM OTOMASYON (v5.0 — Full Pipeline) ────────────────────
_STATE_FILE = os.path.join(PROJECT_ROOT, "data", "automation_state.json")

def _load_persisted_state():
    """Disk'ten kaydedilmiş otomasyon durumunu yükle."""
    try:
        if os.path.exists(_STATE_FILE):
            with open(_STATE_FILE, "r", encoding="utf-8") as f:
                return json.loads(f.read())
    except Exception:
        pass
    return {}

def _save_persisted_state(state_dict):
    """Otomasyon durumunu disk'e kaydet (Passenger process sıfırlanması için)."""
    try:
        os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
        save_data = {
            "cycle": state_dict.get("cycle", 0),
            "last_action": state_dict.get("last_action", ""),
            "last_cycle_at": state_dict.get("last_cycle_at", ""),
            "stats": state_dict.get("stats", {}),
            "running": state_dict.get("running", False),
        }
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            f.write(json.dumps(save_data, ensure_ascii=False, indent=2))
    except Exception as e:
        log.warning(f"[STATE] Kaydet hatası: {e}")

_persisted = _load_persisted_state()
_automation_state = {
    "running": _persisted.get("running", False),
    "thread": None,
    "cycle": _persisted.get("cycle", 0),
    "last_action": _persisted.get("last_action", ""),
    "last_cycle_at": _persisted.get("last_cycle_at", ""),
    "stats": _persisted.get("stats", {}),
    "logs": [],
}


def _auto_log(msg, level="info"):
    """Log'u hem Python logger'a hem de UI'daki Canlı Log'a yaz."""
    from datetime import datetime as _dt
    ts = _dt.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    if level == "error":
        log.error(msg)
    elif level == "warning":
        log.warning(msg)
    else:
        log.info(msg)
    _automation_state["logs"].append(line)
    if len(_automation_state["logs"]) > 200:
        _automation_state["logs"] = _automation_state["logs"][-200:]


def _automation_loop():
    """
    CRASH-PROOF OTOMASYON PIPELINE — ÜÇ KATLI HATA KORUMASI
    Hiçbir şekilde çökmez. Thread asla ölmez.
    Pipeline: Lead Bul (AI) → Puanla → Email Yaz → Gönder → Follow-up → Cleanup
    """
    # ═══ OUTER LAYER: En dıştaki koruma ═══
    try:
        import gc
        import random
        import traceback

        _auto_log("═══ PIPELINE THREAD BAŞLADI ═══")
        _automation_state["last_action"] = "Pipeline başlatılıyor..."

        # Başlangıçta duplicate sent_log kayıtlarını temizle
        try:
            removed = db.cleanup_duplicate_sent()
            if removed > 0:
                _auto_log(f"🧹 {removed} duplicate gönderim kaydı temizlendi")
        except Exception as cleanup_err:
            _auto_log(f"⚠️ Cleanup hatası: {cleanup_err}")

        # SendEngine — email göndermek için (opsiyonel)
        send_engine = None
        try:
            from core.send_engine import SendEngine
            send_engine = SendEngine()
            _auto_log("✅ SendEngine hazır")
        except Exception as e:
            _auto_log(f"⚠️ SendEngine yüklenemedi (devam ediliyor): {e}", "warning")

        # ═══ MIDDLE LAYER: Her cycle'ı koru ═══
        while _automation_state["running"]:
            try:
                _automation_state["cycle"] += 1
                cycle = _automation_state["cycle"]
                _auto_log(f"═══ Cycle {cycle} başlıyor ═══")
                _automation_state["last_action"] = f"Cycle {cycle} başlıyor..."
                emit_event("automation_update", {"action": f"Cycle {cycle}", "cycle": cycle, "running": True})

                total_discovered = 0

                # ═══════════════════════════════════════════════════
                # PHASE 1: AI LEAD KEŞFİ
                # ═══════════════════════════════════════════════════
                try:
                    _automation_state["last_action"] = "Phase 1: AI ile lead keşfi..."
                    _auto_log("🔍 Phase 1: AI lead keşfi başlıyor")

                    for sector in list(config.SECTORS):
                        if not _automation_state["running"]:
                            break
                        sector = sector.strip()
                        if not sector:
                            continue

                        try:
                            _automation_state["last_action"] = f"Phase 1: {sector} — AI aranıyor ({total_discovered} bulundu)"
                            _auto_log(f"🔍 AI arama: {sector}")
                            ai_leads = lead_finder._ai_bulk_lead_search(sector)

                            if ai_leads:
                                saved = 0
                                for nl in ai_leads:
                                    email = nl.get("email", "")
                                    if email and not db.lead_exists(email):
                                        try:
                                            db.add_discovered_lead(
                                                email=email,
                                                company=nl.get("company_name", ""),
                                                sector=sector,
                                                location=nl.get("city", "Nederland"),
                                                vehicles=str(nl.get("estimated_vehicles", "")),
                                                website=nl.get("website", ""),
                                                phone=nl.get("phone", ""),
                                                source="ai_discovery",
                                            )
                                            saved += 1
                                        except Exception:
                                            pass
                                total_discovered += saved
                                _auto_log(f"✅ {sector}: {saved} yeni lead bulundu! (toplam: {total_discovered})")
                                _automation_state["last_action"] = f"Phase 1: {sector} — {saved} lead! (toplam: {total_discovered})"
                            else:
                                _auto_log(f"⚠️ {sector}: lead bulunamadı (API yanıt boş)")
                        except Exception as e:
                            _auto_log(f"❌ {sector} hatası: {e}", "error")

                        # Rate limit koruması: sektörler arası yeterli bekleme
                        time.sleep(8)

                    _auto_log(f"📊 Phase 1 TAMAM: {total_discovered} lead keşfedildi")
                    _automation_state["last_action"] = f"Phase 1 tamam: {total_discovered} lead"
                except Exception as e:
                    _auto_log(f"❌ Phase 1 HATA: {e}", "error")

                gc.collect()
                if not _automation_state["running"]:
                    break

                # ═══════════════════════════════════════════════════
                # PHASE 2: LEAD PUANLAMA
                # ═══════════════════════════════════════════════════
                try:
                    _automation_state["last_action"] = "Phase 2: Lead puanlama..."
                    _auto_log("📊 Phase 2: Lead puanlama başlıyor")
                    unscored = db.get_all_leads()
                    unscored_leads = [l for l in unscored if not l.get("ai_score") or l.get("ai_score", 0) == 0]
                    if unscored_leads:
                        batch = unscored_leads[:20]
                        scores = lead_scorer.score_batch(batch)
                        for s in scores:
                            db.update_lead_ai_score(s["email"], s.get("score", 50), s.get("reason", ""))
                        _auto_log(f"✅ {len(scores)} lead puanlandı")
                        _automation_state["last_action"] = f"Phase 2: {len(scores)} lead puanlandı"
                    else:
                        _auto_log("ℹ️ Puanlanacak lead yok")
                except Exception as e:
                    _auto_log(f"❌ Phase 2 HATA: {e}", "error")

                gc.collect()
                if not _automation_state["running"]:
                    break

                # ═══════════════════════════════════════════════════
                # PHASE 2.5: DÜŞÜK SKORLU LEAD'LERİ YENİDEN PUANLA
                # ═══════════════════════════════════════════════════
                try:
                    _automation_state["last_action"] = "Phase 2.5: Düşük skorlu leadleri revize..."
                    low_score_leads = db.get_leads_for_rescoring(min_score=90, limit=10)
                    if low_score_leads:
                        _auto_log(f"🔄 Phase 2.5: {len(low_score_leads)} düşük skorlu lead revize ediliyor")
                        rescored = lead_scorer.score_batch(low_score_leads)
                        for s in rescored:
                            db.update_lead_ai_score(s["email"], s.get("score", 50), s.get("reason", ""))
                        _auto_log(f"✅ {len(rescored)} lead yeniden puanlandı")
                    else:
                        _auto_log("ℹ️ Revize edilecek lead yok")
                except Exception as e:
                    _auto_log(f"❌ Phase 2.5 HATA: {e}", "error")

                gc.collect()
                if not _automation_state["running"]:
                    break

                # ═══════════════════════════════════════════════════
                # PHASE 3: EMAIL YAZ + GÖNDER
                # ═══════════════════════════════════════════════════
                try:
                    _automation_state["last_action"] = "Phase 3: Email yazma ve gönderme..."
                    _auto_log("✉️ Phase 3: Email yazma & gönderme")
                    today_sent = db.get_today_sent_count()
                    remaining = max(0, config.DAILY_SEND_LIMIT - today_sent)
                    batch_size = min(10, remaining)
                    _auto_log(f"📊 Bugün gönderilen: {today_sent}/{config.DAILY_SEND_LIMIT}, kalan kota: {remaining}")

                    if batch_size > 0:
                        unsent = db.get_unsent_leads(limit=batch_size)
                        if unsent:
                            sent_count = 0
                            _auto_log(f"📋 {len(unsent)} gönderilmemiş lead bulundu")
                            for lead_data in unsent:
                                if not _automation_state["running"]:
                                    break
                                try:
                                    email_addr = lead_data.get("email", "")
                                    company = lead_data.get("company", "")
                                    sector = lead_data.get("sector", "")
                                    if not email_addr:
                                        continue

                                    # Duplicate gönderim kontrolü
                                    if db.is_duplicate_email(email_addr):
                                        continue

                                    _automation_state["last_action"] = f"Phase 3: {company or email_addr} — istihbarat toplaniyor..."
                                    _auto_log(f"🔍 Recon: {company or email_addr}")

                                    # 0. ReconAgent — Derinlemesine araştırma
                                    intel_context = ""
                                    try:
                                        from agents.recon_agent import recon_agent
                                        intel = recon_agent.investigate(lead_data)
                                        if intel:
                                            intel_context = recon_agent.format_for_copywriter(intel)
                                            profile_type = intel.get("psychological_profile", {}).get("type", "?")
                                            strategy = intel.get("persuasion_strategy", {}).get("primary_cialdini", "?")
                                            _auto_log(f"🧠 Intel: profil={profile_type}, strateji={strategy}")
                                    except Exception as recon_err:
                                        _auto_log(f"⚠️ Recon hatası (devam): {recon_err}")

                                    _automation_state["last_action"] = f"Phase 3: {company or email_addr} — email yazılıyor..."
                                    _auto_log(f"✍️ Email yazılıyor: {company or email_addr}")

                                    # 1. Copywriter — EmailDraft dataclass döner (+ intel context)
                                    draft = copywriter.write(lead_data, intel_context=intel_context)
                                    if not draft:
                                        _auto_log(f"⚠️ Draft boş: {company}")
                                        continue

                                    subject = draft.chosen_subject
                                    body_html = draft.body_html
                                    body_text = draft.body_text
                                    if not subject or not body_html:
                                        _auto_log(f"⚠️ Subject/body boş: {company}")
                                        continue

                                    # 2. QC — QCResult dataclass döner
                                    qc_score = 50
                                    qc_passed = True
                                    try:
                                        qc_result = quality.check(
                                            subject=subject,
                                            body_text=body_text,
                                            company_name=company,
                                            body_html=body_html
                                        )
                                        qc_score = qc_result.score
                                        qc_passed = qc_result.passed
                                        _auto_log(f"📊 QC skor: {qc_score}/100 ({'GEÇTI' if qc_passed else 'KALMA'})")
                                        if not qc_passed and qc_score < 40:
                                            _auto_log(f"⚠️ QC çok düşük ({qc_score}), atlanıyor: {company}")
                                            continue
                                    except Exception as qc_err:
                                        _auto_log(f"⚠️ QC hatası (devam): {qc_err}")

                                    # 3. Draft kaydet
                                    try:
                                        draft_dict = {
                                            "subject_a": draft.subject_a,
                                            "subject_b": draft.subject_b,
                                            "subject_c": draft.subject_c,
                                            "chosen_subject": subject,
                                            "body_html": body_html,
                                            "body_text": body_text,
                                            "qc_score": qc_score,
                                        }
                                        db.save_draft(email_addr, draft_dict)
                                    except Exception as draft_err:
                                        _auto_log(f"⚠️ Draft kayıt hatası: {draft_err}")

                                    # 4. Gönder
                                    if send_engine:
                                        try:
                                            from core.send_engine import EmailMessage
                                            msg = EmailMessage(
                                                to_email=email_addr,
                                                to_name=company,
                                                subject=subject,
                                                html_body=body_html,
                                                text_body=body_text,
                                                lead_id=email_addr,
                                            )
                                            result = send_engine.send(msg)
                                            success = result.get("success") if isinstance(result, dict) else getattr(result, "success", False)
                                            if success:
                                                method = result.get("method", "smtp") if isinstance(result, dict) else getattr(result, "method", "smtp")
                                                msg_id = result.get("message_id", "") if isinstance(result, dict) else getattr(result, "message_id", "")
                                                variant = "A"
                                                try:
                                                    variant = ab_test.get_variant() if ab_test else "A"
                                                except Exception:
                                                    pass
                                                db.log_sent(
                                                    email=email_addr,
                                                    company=company,
                                                    sector=sector,
                                                    subject=subject,
                                                    method=method,
                                                    message_id=msg_id,
                                                    ab_variant=variant
                                                )
                                                sent_count += 1
                                                _auto_log(f"✅ Email gönderildi: {company} ({email_addr})")

                                                # Follow-up zamanla (3 aşamalı)
                                                try:
                                                    follow_up.schedule_followups(
                                                        email=email_addr,
                                                        original_subject=subject,
                                                        company=company,
                                                        sector=sector,
                                                        vehicles=str(lead_data.get("vehicles", "")),
                                                    )
                                                    _auto_log(f"📅 Follow-up zamanlandı: {email_addr}")
                                                except Exception as fu_err:
                                                    _auto_log(f"⚠️ Follow-up zamanlama hatası: {fu_err}")
                                            else:
                                                err_msg = result.get("error", "bilinmiyor") if isinstance(result, dict) else getattr(result, "error", "bilinmiyor")
                                                _auto_log(f"❌ Gönderim başarısız: {email_addr} — {err_msg}")
                                        except Exception as send_err:
                                            _auto_log(f"❌ Gönderim hatası: {email_addr} — {send_err}", "error")
                                    else:
                                        _auto_log(f"⚠️ SendEngine yok — {email_addr} bekletiliyor")

                                except Exception as e:
                                    _auto_log(f"❌ Email işleme hatası: {e}", "error")
                                time.sleep(2)

                            _auto_log(f"📧 Phase 3 TAMAM: {sent_count} email gönderildi")
                            _automation_state["last_action"] = f"Phase 3: {sent_count} email gönderildi"
                            emit_event("email_sent", {"count": sent_count})
                        else:
                            _auto_log("ℹ️ Gönderilecek yeni lead yok (tümü gönderilmiş)")
                    else:
                        _auto_log(f"⚠️ Günlük limit doldu: {today_sent}/{config.DAILY_SEND_LIMIT} — yarına bekletiliyor")
                except Exception as e:
                    _auto_log(f"❌ Phase 3 HATA: {e}", "error")

                gc.collect()
                if not _automation_state["running"]:
                    break

                # ═══════════════════════════════════════════════════
                # PHASE 4: FOLLOW-UP
                # ═══════════════════════════════════════════════════
                try:
                    _automation_state["last_action"] = "Phase 4: Follow-up işleme..."
                    _auto_log("📬 Phase 4: Follow-up işleniyor")
                    processed = follow_up.process_pending()
                    _auto_log(f"✅ {len(processed)} follow-up işlendi")
                except Exception as e:
                    _auto_log(f"❌ Phase 4 HATA: {e}", "error")

                # ═══════════════════════════════════════════════════
                # PHASE 5: A/B TEST + RESPONSE TRACKING
                # ═══════════════════════════════════════════════════
                try:
                    _automation_state["last_action"] = "Phase 5: A/B test ve yanıt takibi..."
                    variant_stats = db.get_open_rates_by_variant()
                    if variant_stats:
                        winner = ab_test.determine_winner(variant_stats)
                        if winner:
                            _auto_log(f"🏆 A/B kazanan: {winner}")
                except Exception:
                    pass

                try:
                    response_tracker.check_inbox()
                except Exception:
                    pass

                # ═══════════════════════════════════════════════════
                # CYCLE TAMAMLANDI
                # ═══════════════════════════════════════════════════
                _automation_state["last_action"] = f"Cycle {cycle} tamamlandı — 5 dk bekleniyor..."
                _automation_state["last_cycle_at"] = datetime.now().isoformat()
                try:
                    _automation_state["stats"] = db.get_stats()
                except Exception:
                    pass

                emit_event("automation_update", {
                    "action": f"Cycle {cycle} tamamlandı",
                    "cycle": cycle,
                    "running": True,
                })

                _auto_log(f"✅ ═══ Cycle {cycle} TAMAMLANDI ═══ Sonraki: 5 dk")
                gc.collect()

                # 5 dakika bekle (300 saniye) — her saniye kontrol et
                for _ in range(300):
                    if not _automation_state["running"]:
                        break
                    time.sleep(1)

            except Exception as e:
                # Cycle hatası — devam et, durma
                _auto_log(f"❌ Cycle hatası: {e}", "error")
                try:
                    import traceback
                    traceback.print_exc()
                except Exception:
                    pass
                _automation_state["last_action"] = f"Hata: {str(e)[:100]} — 30sn sonra tekrar..."
                gc.collect()
                time.sleep(30)  # 30 sn bekle ve tekrar dene

        # While döngüsü bitti (running = False)
        _auto_log("Pipeline durduruldu (running=False)")
        _automation_state["last_action"] = "Pipeline durduruldu"

    except Exception as e:
        # En dıştaki koruma — thread güvenli şekilde durur, crash olmaz
        _auto_log(f"FATAL: {e}", "error")
        try:
            import traceback
            traceback.print_exc()
        except Exception:
            pass
        _automation_state["last_action"] = f"FATAL: {str(e)[:200]} — pipeline durdu"
        _automation_state["running"] = False
        gc.collect()
        # NOT recursive — thread safely dies, can be restarted via API


def _auto_start_automation():
    """Server basladiginda otomasyonu otomatik baslat.
    NOT: Passenger modunda devre disi — cron endpoint kullanilmali.
    """
    if IS_PASSENGER:
        log.info("[AUTO] Passenger modunda — otomasyon thread'i devre disi. "
                 "Cron endpoint /cron/run-cycle kullanin.")
        return

    if not config.AUTO_START:
        log.info("[AUTO] AUTO_START devre disi — manuel baslatma gerekli")
        return

    import time
    time.sleep(3)  # Server'in tam baslamasini bekle

    if _automation_state["running"]:
        return

    log.info("[AUTO] ═══ OTOMASYON OTOMATIK BASLADI ═══")
    log.info(f"[AUTO] Sektorler: {config.SECTORS}")
    log.info(f"[AUTO] Konum: {config.TARGET_LOCATION}")
    log.info(f"[AUTO] Mod: CANLI GÖNDERİM")
    log.info(f"[AUTO] Cycle arasi: {config.AUTOMATION_INTERVAL} dakika")

    _automation_state["running"] = True
    _automation_state["cycle"] = 0
    t = threading.Thread(target=_automation_loop, daemon=True)
    _automation_state["thread"] = t
    t.start()
    emit_event("automation_update", {"action": "Otomasyon otomatik baslatildi", "running": True})


@app.route("/api/automation/start", methods=["POST"])
def start_automation():
    """Tam otomasyonu baslat."""
    if _automation_state["running"]:
        return jsonify({"status": "already_running", "cycle": _automation_state["cycle"]})

    _automation_state["running"] = True
    _automation_state["cycle"] = 0
    t = threading.Thread(target=_automation_loop, daemon=True)
    _automation_state["thread"] = t
    t.start()
    emit_event("automation_update", {"action": "Otomasyon baslatildi", "running": True})
    return jsonify({"status": "started"})


@app.route("/api/automation/stop", methods=["POST"])
def stop_automation():
    """Otomasyonu durdur."""
    _automation_state["running"] = False
    emit_event("automation_update", {"action": "Otomasyon durduruldu", "running": False})
    return jsonify({"status": "stopped"})


@app.route("/api/automation/status", methods=["GET"])
def get_automation_status():
    """Otomasyon durumunu dondur — heartbeat dosyasından kontrol et."""
    _HEARTBEAT = os.path.join(PROJECT_ROOT, "data", "heartbeat.txt")

    # Heartbeat kontrolü: cron son 30 dk'da çalıştı mı?
    running = False
    last_cycle_at = ""
    try:
        if os.path.exists(_HEARTBEAT):
            with open(_HEARTBEAT, "r") as f:
                hb_time = f.read().strip()
            if hb_time:
                last_cycle_at = hb_time
                from datetime import datetime as _dt
                try:
                    hb_dt = _dt.fromisoformat(hb_time)
                    diff = (_dt.now() - hb_dt).total_seconds()
                    if diff < 1800:  # 30 dakika = 1800 saniye
                        running = True
                except Exception:
                    pass
    except Exception:
        pass

    # Fallback: persisted state veya in-memory state running ise
    persisted = _load_persisted_state()
    if not running and persisted.get("running"):
        # Persisted state'te de son cycle zamanını kontrol et
        p_cycle_at = persisted.get("last_cycle_at", "")
        if p_cycle_at:
            try:
                from datetime import datetime as _dt2
                p_dt = _dt2.fromisoformat(p_cycle_at)
                if (_dt2.now() - p_dt).total_seconds() < 1800:
                    running = True
                    if not last_cycle_at:
                        last_cycle_at = p_cycle_at
            except Exception:
                pass

    # In-memory state
    if _automation_state.get("running"):
        running = True

    # Disk state'ten cycle ve action bilgisi
    cycle = persisted.get("cycle", 0) or _automation_state.get("cycle", 0)
    last_action = persisted.get("last_action", "") or _automation_state.get("last_action", "")
    stats = persisted.get("stats", {}) or _automation_state.get("stats", {})
    if not last_cycle_at:
        last_cycle_at = persisted.get("last_cycle_at", "") or _automation_state.get("last_cycle_at", "")

    # DB'den bugün gönderim sayısını al
    if cycle == 0:
        try:
            sent_log = db.get_sent_emails()
            if sent_log and isinstance(sent_log, list):
                today_str = datetime.now().strftime("%Y-%m-%d")
                today_count = sum(1 for s in sent_log if str(s.get("sent_at", s.get("date", ""))).startswith(today_str))
                if today_count > 0:
                    cycle = today_count
                    if not last_action:
                        last_action = f"Bugün {today_count} email gönderildi"
        except Exception:
            pass

    return jsonify({
        "running": running,
        "cycle": cycle,
        "last_action": last_action,
        "last_cycle_at": last_cycle_at,
        "stats": stats,
        "logs": _automation_state.get("logs", [])[-50:],
    })


@app.route("/api/automation/test", methods=["GET"])
def test_automation():
    """Diagnostik: API key ve sistem testi."""
    results = {"api_key_set": bool(config.ANTHROPIC_API_KEY), "api_key_prefix": config.ANTHROPIC_API_KEY[:20] + "..." if config.ANTHROPIC_API_KEY else "YOK"}
    # Claude API test
    try:
        import requests as _r
        resp = _r.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": config.CLAUDE_MODEL, "max_tokens": 50, "messages": [{"role": "user", "content": "Say hello in 3 words"}]},
            timeout=15
        )
        results["api_status"] = resp.status_code
        if resp.ok:
            results["api_response"] = resp.json().get("content", [{}])[0].get("text", "")
        else:
            results["api_error"] = resp.text[:200]
    except Exception as e:
        results["api_error"] = str(e)
    results["sectors"] = list(config.SECTORS)
    results["model"] = config.CLAUDE_MODEL
    results["state"] = {"running": _automation_state["running"], "cycle": _automation_state["cycle"], "last_action": _automation_state["last_action"]}
    return jsonify(results)


# ─── TEMPLATES (Phase 3) ─────────────────────────────────────
@app.route("/api/templates", methods=["GET"])
def get_templates():
    """Mevcut email sablonlarini listele."""
    return jsonify({"templates": template_engine.get_templates()})


@app.route("/api/templates/active", methods=["POST"])
def set_active_template():
    """Aktif sablonu degistir."""
    data = request.json or {}
    tid = data.get("template_id", "")
    if template_engine.set_active(tid):
        return jsonify({"status": "ok", "active": tid})
    return jsonify({"error": "Sablon bulunamadi"}), 404


@app.route("/api/templates/preview", methods=["POST"])
def preview_template():
    """Sablon onizlemesi."""
    data = request.json or {}
    tid = data.get("template_id", "modern_dark")
    html = template_engine.preview(tid, data.get("content"))
    return jsonify({"html": html})


# ─── BREVO WEBHOOKS (Phase 3) ────────────────────────────────
@app.route("/api/webhooks/brevo", methods=["POST"])
def brevo_webhook_v2():
    """Brevo event webhook (open/click/bounce/unsubscribe)."""
    data = request.json or {}
    event_type = data.get("event", "").lower()
    email = data.get("email", "")
    msg_id = data.get("message-id", "")
    ts = data.get("ts_event", "")

    if not event_type or not email:
        return jsonify({"error": "event ve email gerekli"}), 400

    # Event mapping
    type_map = {
        "delivered": "delivered",
        "opened": "open", "open": "open",
        "click": "click", "clicked": "click",
        "hard_bounce": "bounce", "soft_bounce": "bounce", "bounce": "bounce",
        "unsubscribe": "unsubscribe", "unsubscribed": "unsubscribe",
        "spam": "spam", "complaint": "spam",
    }
    db_event = type_map.get(event_type)
    if not db_event:
        return jsonify({"status": "ignored", "event": event_type})

    # Veritabanina kaydet
    try:
        db.log_event(email, db_event, {"message_id": msg_id, "timestamp": ts})
        log.info(f"[WEBHOOK] {db_event}: {email}")
        emit_event("brevo_event", {"type": db_event, "email": email})

        # Bounce ise lead'i isaretle
        if db_event == "bounce":
            compliance.add_opt_out(email)
        elif db_event == "unsubscribe":
            compliance.add_opt_out(email)

    except Exception as e:
        log.error(f"[WEBHOOK] Hata: {e}")

    return jsonify({"status": "ok", "event": db_event})


# ─── REPORTS & EXPORT (Phase 3) ──────────────────────────────
@app.route("/api/reports", methods=["GET"])
def get_report():
    """Kapsamli kampanya raporu."""
    report = db.get_campaign_report()
    return jsonify(report)


@app.route("/api/reports/export", methods=["GET"])
def export_csv():
    """CSV olarak tum lead verileri."""
    import io
    data = db.get_export_data()
    if not data:
        return jsonify({"error": "Veri yok"}), 404

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=smartmailer_export.csv"}
    )


# ─── A/B AUTO DETERMINE (Phase 3) ────────────────────────────
@app.route("/api/ab-test/auto-determine", methods=["POST"])
def auto_determine_winner():
    """A/B test kazananini otomatik belirle."""
    variant_stats = db.get_open_rates_by_variant()
    if not variant_stats:
        return jsonify({"status": "no_data", "winner": None})
    winner = ab_test.determine_winner(variant_stats)
    return jsonify({"status": "determined" if winner else "insufficient_data",
                    "winner": winner, "stats": variant_stats})


# ─── CRON-TRIGGERED PIPELINE (Shared Hosting Uyumlu) ─────────
@app.route("/cron/run-cycle", methods=["GET", "POST"])
def cron_run_cycle():
    """
    CRON JOB İLE TETİKLENEN PİPELİNE.
    Passenger WSGI'da background threadler ölüyor, bu yüzden
    pipeline her 10 dakikada bir cron job ile çağrılır.
    
    Kullanım: curl https://app.fleettrackholland.nl/cron/run-cycle?secret=fleettrack2026
    """
    import gc
    import traceback

    # Güvenlik kontrolü
    deploy_secret = getattr(config, 'DEPLOY_SECRET', 'fleettrack2026')
    req_secret = request.args.get("secret", "")
    if not req_secret:
        req_secret = (request.json or {}).get("secret", "") if request.is_json else ""
    if req_secret != deploy_secret:
        return jsonify({"error": "Unauthorized"}), 403

    results = {
        "started_at": datetime.now().isoformat(),
        "phase_1_discover": {},
        "phase_2_score": {},
        "phase_3_send": {},
        "phase_4_followup": {},
    }

    _automation_state["cycle"] += 1
    _automation_state["running"] = True

    # ★ HEARTBEAT: Cron'un çalıştığını kaydet (badge için kritik)
    _HEARTBEAT = os.path.join(PROJECT_ROOT, "data", "heartbeat.txt")
    try:
        os.makedirs(os.path.dirname(_HEARTBEAT), exist_ok=True)
        with open(_HEARTBEAT, "w") as f:
            f.write(datetime.now().isoformat())
    except Exception:
        pass
    cycle = _automation_state["cycle"]
    _auto_log(f"═══ CRON Cycle {cycle} BAŞLADI ═══")

    # ═══ PHASE 1: AI LEAD KEŞFİ ═══
    total_discovered = 0
    try:
        _automation_state["last_action"] = f"Cron Cycle {cycle}: Phase 1 — AI lead keşfi"
        _auto_log("🔍 Phase 1: AI lead keşfi başlıyor")

        sectors_to_search = list(config.SECTORS)
        for sector in sectors_to_search:
            sector = sector.strip()
            if not sector:
                continue

            try:
                _auto_log(f"🔍 AI arama: {sector}")
                _automation_state["last_action"] = f"Phase 1: {sector} — AI aranıyor"
                ai_leads = lead_finder._ai_bulk_lead_search(sector)

                if ai_leads:
                    saved = 0
                    for nl in ai_leads:
                        email = nl.get("email", "")
                        if email and not db.lead_exists(email):
                            try:
                                db.add_discovered_lead(
                                    email=email,
                                    company=nl.get("company_name", ""),
                                    sector=sector,
                                    location=nl.get("city", "Nederland"),
                                    vehicles=str(nl.get("estimated_vehicles", "")),
                                    website=nl.get("website", ""),
                                    phone=nl.get("phone", ""),
                                    source="ai_discovery",
                                )
                                saved += 1
                            except Exception:
                                pass
                    total_discovered += saved
                    _auto_log(f"✅ {sector}: {saved} yeni lead (toplam: {total_discovered})")
                else:
                    _auto_log(f"⚠️ {sector}: lead bulunamadı")
            except Exception as e:
                _auto_log(f"❌ {sector} hatası: {e}", "error")

            time.sleep(5)  # Rate limit koruması

        results["phase_1_discover"] = {"total_discovered": total_discovered}
        _auto_log(f"📊 Phase 1 TAMAM: {total_discovered} lead keşfedildi")
    except Exception as e:
        _auto_log(f"❌ Phase 1 HATA: {e}", "error")
        results["phase_1_discover"] = {"error": str(e)}

    gc.collect()

    # ═══ PHASE 2: LEAD PUANLAMA ═══
    try:
        _automation_state["last_action"] = f"Cron Cycle {cycle}: Phase 2 — Lead puanlama"
        _auto_log("📊 Phase 2: Lead puanlama başlıyor")
        unscored = db.get_all_leads()
        unscored_leads = [l for l in unscored if not l.get("ai_score") or l.get("ai_score", 0) == 0]
        scored_count = 0
        if unscored_leads:
            batch = unscored_leads[:20]
            scores = lead_scorer.score_batch(batch)
            for s in scores:
                db.update_lead_ai_score(s["email"], s.get("score", 50), s.get("reason", ""))
            scored_count = len(scores)
            _auto_log(f"✅ {scored_count} lead puanlandı")
        else:
            _auto_log("ℹ️ Puanlanacak lead yok")
        results["phase_2_score"] = {"scored": scored_count}
    except Exception as e:
        _auto_log(f"❌ Phase 2 HATA: {e}", "error")
        results["phase_2_score"] = {"error": str(e)}

    gc.collect()

    # ═══ PHASE 3: EMAIL YAZ + GÖNDER ═══
    sent_count = 0
    try:
        _automation_state["last_action"] = f"Cron Cycle {cycle}: Phase 3 — Email yazma ve gönderme"
        _auto_log("✉️ Phase 3: Email yazma & gönderme")

        # SendEngine
        send_engine = None
        try:
            from core.send_engine import SendEngine, EmailMessage
            send_engine = SendEngine()
        except Exception as se:
            _auto_log(f"⚠️ SendEngine yüklenemedi: {se}", "warning")

        today_sent = db.get_today_sent_count()
        remaining = max(0, config.DAILY_SEND_LIMIT - today_sent)
        batch_size = min(10, remaining)
        _auto_log(f"📊 Bugün gönderilen: {today_sent}/{config.DAILY_SEND_LIMIT}, kalan: {remaining}")

        if batch_size > 0:
            unsent = db.get_unsent_leads(limit=batch_size)
            if unsent:
                _auto_log(f"📋 {len(unsent)} gönderilmemiş lead bulundu")
                for lead_data in unsent:
                    try:
                        email_addr = lead_data.get("email", "")
                        company = lead_data.get("company", "")
                        sector = lead_data.get("sector", "")
                        if not email_addr:
                            continue

                        if db.is_duplicate_email(email_addr):
                            continue

                        # ReconAgent
                        intel_context = ""
                        try:
                            from agents.recon_agent import recon_agent
                            intel = recon_agent.investigate(lead_data)
                            if intel:
                                intel_context = recon_agent.format_for_copywriter(intel)
                        except Exception:
                            pass

                        # Copywriter
                        _auto_log(f"✍️ Email yazılıyor: {company or email_addr}")
                        draft = copywriter.write(lead_data, intel_context=intel_context)
                        if not draft:
                            continue

                        subject = draft.chosen_subject
                        body_html = draft.body_html
                        body_text = draft.body_text
                        if not subject or not body_html:
                            continue

                        # QC
                        qc_score = 50
                        try:
                            qc_result = quality.check(
                                subject=subject, body_text=body_text,
                                company_name=company, body_html=body_html
                            )
                            qc_score = qc_result.score
                            if not qc_result.passed and qc_score < 40:
                                _auto_log(f"⚠️ QC çok düşük ({qc_score}), atlanıyor: {company}")
                                continue
                        except Exception:
                            pass

                        # Draft kaydet
                        try:
                            db.save_draft(email_addr, {
                                "subject_a": draft.subject_a, "subject_b": draft.subject_b,
                                "subject_c": draft.subject_c, "chosen_subject": subject,
                                "body_html": body_html, "body_text": body_text, "qc_score": qc_score,
                            })
                        except Exception:
                            pass

                        # Gönder
                        if send_engine:
                            msg = EmailMessage(
                                to_email=email_addr, to_name=company,
                                subject=subject, html_body=body_html,
                                text_body=body_text, lead_id=email_addr,
                            )
                            result = send_engine.send(msg)
                            success = result.get("success") if isinstance(result, dict) else getattr(result, "success", False)
                            if success:
                                method = result.get("method", "smtp") if isinstance(result, dict) else getattr(result, "method", "smtp")
                                msg_id = result.get("message_id", "") if isinstance(result, dict) else getattr(result, "message_id", "")
                                db.log_sent(email=email_addr, company=company, sector=sector,
                                            subject=subject, method=method, message_id=msg_id, ab_variant="A")
                                sent_count += 1
                                _auto_log(f"✅ Email gönderildi: {company} ({email_addr})")

                                try:
                                    follow_up.schedule_followups(
                                        email=email_addr, original_subject=subject,
                                        company=company, sector=sector,
                                        vehicles=str(lead_data.get("vehicles", "")),
                                    )
                                except Exception:
                                    pass
                            else:
                                err_msg = result.get("error", "?") if isinstance(result, dict) else getattr(result, "error", "?")
                                _auto_log(f"❌ Gönderim başarısız: {email_addr} — {err_msg}")
                    except Exception as e:
                        _auto_log(f"❌ Email işleme hatası: {e}", "error")
                    time.sleep(2)
            else:
                _auto_log("ℹ️ Gönderilecek yeni lead yok")
        else:
            _auto_log(f"⚠️ Günlük limit doldu: {today_sent}/{config.DAILY_SEND_LIMIT}")

        results["phase_3_send"] = {"sent": sent_count, "today_total": today_sent + sent_count}
        _auto_log(f"📧 Phase 3 TAMAM: {sent_count} email gönderildi")
    except Exception as e:
        _auto_log(f"❌ Phase 3 HATA: {e}", "error")
        results["phase_3_send"] = {"error": str(e)}

    gc.collect()

    # ═══ PHASE 4: FOLLOW-UP ═══
    try:
        _automation_state["last_action"] = f"Cron Cycle {cycle}: Phase 4 — Follow-up"
        _auto_log("📬 Phase 4: Follow-up işleniyor")
        processed = follow_up.process_pending()
        results["phase_4_followup"] = {"processed": len(processed)}
        _auto_log(f"✅ {len(processed)} follow-up işlendi")
    except Exception as e:
        _auto_log(f"❌ Phase 4 HATA: {e}", "error")
        results["phase_4_followup"] = {"error": str(e)}

    # ═══ PHASE 5: EVENT TRACKING & HOT LEAD DETECTION ═══
    try:
        _automation_state["last_action"] = f"Cron Cycle {cycle}: Phase 5 — Event Tracking"
        _auto_log("📊 Phase 5: Brevo event polling + hot lead detection")

        # Brevo Transactional Events API'den son event'leri çek
        phase5_results = {"events_fetched": 0, "hot_leads_detected": 0}
        try:
            import requests as req
            brevo_key = config.BREVO_API_KEY
            if brevo_key:
                headers = {"api-key": brevo_key, "accept": "application/json"}
                # Son 24 saatteki event'leri çek
                for event_type in ["opens", "clicks", "hardBounces", "softBounces", "unsubscriptions"]:
                    try:
                        resp = req.get(
                            f"https://api.brevo.com/v3/smtp/statistics/events?event={event_type}&days=1&limit=100",
                            headers=headers, timeout=15
                        )
                        if resp.ok:
                            events_data = resp.json().get("events", [])
                            for ev in events_data:
                                ev_email = (ev.get("email") or "").strip().lower()
                                ev_msg_id = ev.get("messageId") or ""
                                if not ev_email:
                                    continue
                                # Event tipi mapping
                                type_map = {
                                    "opens": "opened", "clicks": "click",
                                    "hardBounces": "hard_bounce", "softBounces": "soft_bounce",
                                    "unsubscriptions": "unsubscribe"
                                }
                                mapped_type = type_map.get(event_type, event_type)
                                # Duplicate check — aynı email+event+message_id varsa atla
                                existing = db.get_events_by_email_and_type(ev_email, mapped_type)
                                already_logged = any(
                                    e.get("message_id") == str(ev_msg_id) for e in existing
                                ) if ev_msg_id else False
                                if not already_logged:
                                    db.record_event(
                                        email=ev_email,
                                        event_type=mapped_type,
                                        message_id=str(ev_msg_id),
                                        metadata={"source": "brevo_api", "date": ev.get("date")}
                                    )
                                    phase5_results["events_fetched"] += 1

                                    # Bounce/unsub aksiyonları
                                    if mapped_type in ("hard_bounce", "soft_bounce"):
                                        db.mark_lead_invalid(ev_email)
                                        db.cancel_pending_followups(ev_email)
                                    elif mapped_type == "unsubscribe":
                                        db.add_opt_out(ev_email, reason="brevo_api")
                                        db.cancel_pending_followups(ev_email)
                    except Exception as ev_err:
                        _auto_log(f"⚠️ Brevo {event_type} çekme hatası: {ev_err}", "warning")
        except Exception as brevo_err:
            _auto_log(f"⚠️ Brevo API erişim hatası: {brevo_err}", "warning")

        # Hot lead otomatik tespiti
        hot_count = db.auto_detect_hot_leads()
        phase5_results["hot_leads_detected"] = hot_count

        results["phase_5_tracking"] = phase5_results
        _auto_log(f"✅ Phase 5: {phase5_results['events_fetched']} event, {hot_count} hot lead")
    except Exception as e:
        _auto_log(f"❌ Phase 5 HATA: {e}", "error")
        results["phase_5_tracking"] = {"error": str(e)}

    # Finalize
    _automation_state["last_action"] = f"Cron Cycle {cycle} tamamlandı"
    _automation_state["last_cycle_at"] = datetime.now().isoformat()
    try:
        _automation_state["stats"] = db.get_stats()
    except Exception:
        pass

    results["finished_at"] = datetime.now().isoformat()
    results["cycle"] = cycle
    _auto_log(f"✅ ═══ CRON Cycle {cycle} TAMAMLANDI ═══")

    # Running durumunu göster (cron çalıştığını göstermek için)
    _automation_state["running"] = True

    # State'i diske kaydet (Passenger process sıfırlamasına karşı)
    _save_persisted_state(_automation_state)

    return jsonify(results)


# ─── SOCKET.IO EVENTS ─────────────────────────────────────────
if HAS_SOCKETIO:
    @socketio.on("connect")
    def handle_connect():
        log.info("[WS] Client baglandi")
        emit("connected", {"status": "ok", "server_time": datetime.now().isoformat()})

    @socketio.on("disconnect")
    def handle_disconnect():
        log.info("[WS] Client ayrildi")

    @socketio.on("request_stats")
    def handle_request_stats():
        stats = db.get_stats()
        emit("stats_update", stats)


# ─── HELPERS ───────────────────────────────────────────────────
def _find_leads_file():
    candidates = [
        os.path.join(config.INPUT_DIR, "leads.csv"),
        os.path.join(config.BASE_DIR, "leads.csv"),
        os.path.join(config.BASE_DIR, "fleettrack-prospects-2026-03-11.csv"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


# ─── AUTO-DEPLOY (GitHub → Server otomatik güncelleme) ─────────
_deploy_state = {
    "last_deploy": None,
    "last_status": "never",
    "last_error": None,
}

@app.route("/api/admin/deploy", methods=["POST"])
def auto_deploy():
    """
    GitHub webhook veya cron job ile otomatik güncelleme.
    Güvenlik: DEPLOY_SECRET header kontrolü.
    """
    # Güvenlik kontrolü
    deploy_secret = getattr(config, 'DEPLOY_SECRET', 'fleettrack2026')
    req_secret = request.headers.get("X-Deploy-Secret", "")
    if req_secret != deploy_secret:
        # JSON body'den de kontrol et
        data = request.json or {}
        if data.get("secret") != deploy_secret:
            return jsonify({"error": "Unauthorized"}), 403

    import subprocess
    try:
        log.info("[DEPLOY] ═══ OTOMATİK GÜNCELLEME BAŞLADI ═══")

        # 1. Git pull
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        git_output = result.stdout + result.stderr
        log.info(f"[DEPLOY] Git pull: {git_output.strip()}")

        if result.returncode != 0:
            _deploy_state["last_status"] = "git_error"
            _deploy_state["last_error"] = git_output
            return jsonify({"status": "error", "message": git_output}), 500

        _deploy_state["last_deploy"] = datetime.now().isoformat()
        _deploy_state["last_status"] = "success"
        _deploy_state["last_error"] = None

        log.info("[DEPLOY] ═══ GÜNCELLEME TAMAMLANDI — Restart gerekebilir ═══")

        return jsonify({
            "status": "success",
            "git_output": git_output.strip(),
            "message": "Güncelleme başarılı. Değişiklikler hemen aktif — büyük değişikliklerde Python restart gerekebilir.",
            "deployed_at": _deploy_state["last_deploy"],
        })

    except subprocess.TimeoutExpired:
        _deploy_state["last_status"] = "timeout"
        return jsonify({"status": "error", "message": "Git pull timeout"}), 500
    except Exception as e:
        _deploy_state["last_status"] = "error"
        _deploy_state["last_error"] = str(e)
        log.error(f"[DEPLOY] Hata: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/admin/deploy/status", methods=["GET"])
def deploy_status():
    return jsonify(_deploy_state)

# ─── AUTO DATABASE SYNC ──────────────────────────────────────
def _auto_sync_db():
    """Her 30 dakikada veritabanını GitHub'a otomatik push eder."""
    import subprocess
    DB_PATH = os.path.join(PROJECT_ROOT, "data", "smartmailer_ultimate.db")
    SYNC_INTERVAL = 1800  # 30 dakika

    while True:
        time.sleep(SYNC_INTERVAL)
        try:
            if not os.path.exists(DB_PATH):
                continue

            # Git add + commit + push
            result = subprocess.run(
                ["git", "add", "data/smartmailer_ultimate.db"],
                cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                continue

            result = subprocess.run(
                ["git", "commit", "-m", f"auto-sync: database update {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
                cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                # Nothing to commit (no changes)
                continue

            result = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                log.info("[AUTO-SYNC] Veritabanı GitHub'a başarıyla push edildi.")
                emit_event("db_synced", {"time": datetime.now().isoformat()})
            else:
                log.warning(f"[AUTO-SYNC] Push başarısız: {result.stderr[:200]}")

        except Exception as e:
            log.error(f"[AUTO-SYNC] Hata: {e}")


# Auto-sync thread — sadece doğrudan çalıştırıldığında başlat (Passenger'da değil)
if not IS_PASSENGER:
    try:
        _sync_thread = threading.Thread(target=_auto_sync_db, daemon=True, name="DBAutoSync")
        _sync_thread.start()
        log.info("[AUTO-SYNC] Veritabanı otomatik sync aktif — her 30 dakikada bir GitHub'a push edilecek.")
    except Exception as _sync_err:
        log.warning(f"[AUTO-SYNC] Thread başlatılamadı: {_sync_err}")


# ─── MAIN ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  SmartMailer Ultimate v1.0")
    print("  SmartMailer Pro + FleetTrack CRM Birleşimi")
    print("  http://localhost:5000")
    mode_str = "GERÇEK GÖNDERİM"
    print(f"  {mode_str} | Sektorler: {', '.join(config.SECTORS[:5])}...")
    print(f"  Auto-Start: {'EVET' if config.AUTO_START else 'HAYIR'} | "
          f"Cycle: {config.AUTOMATION_INTERVAL} dk")
    if HAS_SOCKETIO:
        print("  WebSocket: [OK] Aktif")
    else:
        print("  WebSocket: [X] (pip install flask-socketio)")
    print("=" * 60)

    if HAS_SOCKETIO:
        socketio.run(app, host="0.0.0.0", port=5000, debug=True,
                     allow_unsafe_werkzeug=True)
    else:
        app.run(host="0.0.0.0", port=5000, debug=True)
