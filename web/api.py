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
from core.database import db
from core.ab_test_engine import ABTestEngine
from core.followup_engine import FollowUpEngine
from core.template_engine import TemplateEngine
from agents.copywriter_agent import CopywriterAgent, EmailDraft
from agents.quality_agent import QualityAgent
from agents.compliance_agent import ComplianceAgent
from agents.watchdog_agent import WatchdogAgent
from agents.lead_scorer import LeadScorer
from agents.response_tracker import ResponseTracker
from agents.lead_finder import LeadFinder

log = get_logger("web_api")

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


# ─── GLOBAL STATE ────────────────────────────────────────────────────
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

    return jsonify({"leads": leads, "count": len(leads)})


@app.route("/api/stats/daily", methods=["GET"])
def get_daily_stats():
    """Günlük gönderim istatistikleri — limit göstergesi için."""
    today_sent = db.get_today_sent_count()
    return jsonify({
        "today_sent": today_sent,
        "daily_limit": config.DAILY_SEND_LIMIT,
        "remaining": max(0, config.DAILY_SEND_LIMIT - today_sent),
        "percentage": round((today_sent / config.DAILY_SEND_LIMIT) * 100) if config.DAILY_SEND_LIMIT > 0 else 0,
    })


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
        {"name": "AI Copywriter", "icon": "✍️", "obj": copywriter},
        {"name": "AI Quality Control", "icon": "🧠", "obj": quality},
        {"name": "Compliance (AVG)", "icon": "⚖️", "obj": compliance},
        {"name": "Lead Scorer", "icon": "🔮", "obj": lead_scorer},
        {"name": "Watchdog", "icon": "🛡️", "obj": watchdog},
        {"name": "A/B Test Engine", "icon": "🎯", "obj": ab_test},
        {"name": "Follow-Up Engine", "icon": "🔄", "obj": follow_up},
        {"name": "Response Tracker", "icon": "💬", "obj": response_tracker},
        {"name": "Lead Finder", "icon": "🔍", "obj": lead_finder},
    ]
    result = []
    for a in agents_info:
        try:
            alive = a["obj"].ping() if hasattr(a["obj"], "ping") else True
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

        result.append({
            "name": a["name"],
            "icon": a["icon"],
            "status": status,
            "error": extra,
            "checked_at": datetime.now().isoformat(),
        })
    return jsonify({"agents": result})


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


# ─── BREVO WEBHOOK ─────────────────────────────────────────────
@app.route("/webhook/brevo", methods=["POST"])
def brevo_webhook():
    """Brevo event webhook'u: open, click, bounce, unsubscribe."""
    events = request.json
    if not events:
        return jsonify({"error": "Boş payload"}), 400

    if not isinstance(events, list):
        events = [events]

    for event in events:
        event_type = event.get("event", "unknown")
        email = event.get("email", "")
        message_id = event.get("message-id", "")

        db.record_event(email, event_type, message_id, event)

        if event_type == "unsubscribe" and email:
            compliance.add_unsubscribe(email, "brevo_webhook")

        emit_event("brevo_event", {"type": event_type, "email": email})

    # A/B test kazanan kontrolü
    variant_stats = db.get_open_rates_by_variant()
    if variant_stats:
        ab_test.determine_winner(variant_stats)

    return jsonify({"received": len(events)})


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
    stats = db.get_stats()
    recent = db.get_recent_sent(20)
    ab_status = ab_test.get_status()
    variant_stats = db.get_open_rates_by_variant()

    # Source distribution — kaynak dağılımı
    all_leads = db.get_all_leads()
    source_dist = {}
    for lead in all_leads:
        src = lead.get("source", "csv") or "csv"
        source_dist[src] = source_dist.get(src, 0) + 1

    return jsonify({
        **stats,
        "recent_sent": recent,
        "ab_test": {**ab_status, "variant_stats": variant_stats},
        "unsubscribe_count": len(compliance._unsubscribe),
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


# ─── TÜM GİDEN MAİLLER ──────────────────────────────────────
@app.route("/api/sent/all", methods=["GET"])
def get_all_sent():
    """Tüm gönderilen emailleri draft içerikleriyle birlikte döndür."""
    sent = db.get_all_sent_with_content(limit=200)
    return jsonify({"emails": sent, "count": len(sent)})


# ─── DUPLICATE PREVENTION ────────────────────────────────────
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


@app.route("/unsubscribe", methods=["GET"])
def public_unsubscribe():
    """Alıcıların email'deki link ile listeden çıkması için public sayfa."""
    email = request.args.get("email", "").strip().lower()
    if email:
        try:
            compliance.add_unsubscribe(email, "email_link")
            with db._conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO opt_out (email, reason, ip_address) VALUES (?, ?, ?)",
                    (email, "email_link", request.remote_addr)
                )
            db.cancel_pending_followups(email)
            _notify_admin_unsubscribe(email, "email_link")
            log.info(f"[UNSUB] {email} email link ile çıkarıldı")
        except Exception as e:
            log.error(f"[UNSUB] Public error: {e}")

    return """<!DOCTYPE html>
    <html><head><meta charset='utf-8'><title>Afgemeld</title>
    <style>body{font-family:Arial;display:flex;align-items:center;justify-content:center;height:100vh;background:#0a0a12;color:#e8e8f0}
    .box{text-align:center;padding:40px;border-radius:16px;background:rgba(20,20,35,.9);border:1px solid rgba(255,255,255,.1)}
    h2{color:#00d68f}p{color:#8888a8;margin-top:12px}</style></head>
    <body><div class='box'><h2>✅ U bent afgemeld</h2>
    <p>U ontvangt geen verdere e-mails van ons.</p>
    <p style='font-size:12px;margin-top:20px'>FleetTrack Holland</p></div></body></html>"""


@app.route("/api/opt-out/list", methods=["GET"])
def get_optout_list():
    """Tüm opt-out kayıtlarını listele."""
    try:
        with db._conn() as conn:
            rows = conn.execute("SELECT * FROM opt_out ORDER BY created_at DESC").fetchall()
            return jsonify({"opt_outs": [dict(r) for r in rows], "count": len(rows)})
    except Exception:
        return jsonify({"opt_outs": [], "count": len(compliance._unsubscribe)})


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
def health_check():
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
_automation_state = {
    "running": False,
    "thread": None,
    "cycle": 0,
    "last_action": "",
    "last_cycle_at": "",
    "stats": {},
}


def _automation_loop():
    """
    SIRASAL OTOMASYON PIPELINE — Shared hosting'de crash'i önler.
    Her phase arasında gc.collect() ile bellek temizliği yapılır.
    Pipeline: Lead Bul (max 100) → Puanla → Email Yaz → Gönder → Follow-up → Cleanup
    """
    import gc
    import random

    try:
        _automation_state["last_action"] = "Orchestrator yükleniyor..."
        from agents.orchestrator import Orchestrator
        orch = Orchestrator()
        _automation_state["last_action"] = "Orchestrator hazır — pipeline başlıyor..."
    except Exception as e:
        _automation_state["running"] = False
        _automation_state["last_action"] = f"HATA: Orchestrator yüklenemedi — {e}"
        log.error(f"[AUTO] FATAL: Orchestrator import/init hatası: {e}")
        import traceback
        traceback.print_exc()
        emit_event("automation_update", {"action": _automation_state["last_action"], "running": False, "error": str(e)})
        return

    _dutch_cities = [
        "Amsterdam", "Rotterdam", "Den Haag", "Utrecht", "Eindhoven",
        "Tilburg", "Groningen", "Almere", "Breda", "Nijmegen",
        "Arnhem", "Haarlem", "Enschede", "Apeldoorn", "Amersfoort",
        "Zaanstad", "Zwolle", "Leiden", "Zoetermeer", "Maastricht"
    ]
    _exhausted_combos = set()

    while _automation_state["running"]:
        try:
            _automation_state["cycle"] += 1
            cycle = _automation_state["cycle"]
            log.info(f"[AUTO] ═══ Cycle {cycle} başlıyor ═══ [SIRASAL PIPELINE]")

            # ══════════════════════════════════════════════════════
            # PHASE 1: LEAD KEŞFİ (max 100 lead bulana kadar)
            # ══════════════════════════════════════════════════════
            _automation_state["last_action"] = "Phase 1: Lead keşfi başlıyor..."
            emit_event("automation_update", {"action": _automation_state["last_action"], "cycle": cycle})

            total_discovered = 0
            MAX_LEADS_PER_CYCLE = 100

            for sector in list(config.SECTORS):
                if not _automation_state["running"] or total_discovered >= MAX_LEADS_PER_CYCLE:
                    break
                sector = sector.strip()
                if not sector:
                    continue

                combo_key = (sector.lower(), config.TARGET_LOCATION.lower())
                if combo_key in _exhausted_combos:
                    continue

                try:
                    _automation_state["last_action"] = f"Phase 1: {sector} taranıyor... ({total_discovered}/{MAX_LEADS_PER_CYCLE})"
                    log.info(f"[AUTO] Sektör taranıyor: {sector} / {config.TARGET_LOCATION}")
                    new_leads = lead_finder.discover_leads(sector, config.TARGET_LOCATION)
                    count = len(new_leads) if new_leads else 0
                    total_discovered += count
                    log.info(f"[AUTO] {sector}: {count} lead bulundu (toplam: {total_discovered})")

                    if count == 0:
                        _exhausted_combos.add(combo_key)
                    elif combo_key in _exhausted_combos:
                        _exhausted_combos.discard(combo_key)
                except Exception as e:
                    log.error(f"[AUTO] {sector} keşif hatası: {e}")

                # Sektörler arası bekleme — sunucu koruması
                if _automation_state["running"]:
                    time.sleep(30)

            log.info(f"[AUTO] Phase 1 tamamlandı: {total_discovered} yeni lead")
            gc.collect()  # Bellek temizliği
            time.sleep(10)

            # ══════════════════════════════════════════════════════
            # PHASE 2: GENİŞLETİLMİŞ ARAMA (her 3. cycle)
            # ══════════════════════════════════════════════════════
            if _automation_state["running"] and cycle % 3 == 0:
                _automation_state["last_action"] = "Phase 2: Şehir bazlı genişletilmiş arama..."
                emit_event("automation_update", {"action": _automation_state["last_action"], "cycle": cycle})

                expanded_found = 0
                city = random.choice(_dutch_cities)
                sector = random.choice(list(config.SECTORS)) if config.SECTORS else "transport"

                combo_key = (sector.lower(), city.lower())
                if combo_key not in _exhausted_combos:
                    try:
                        log.info(f"[AUTO] Genişletilmiş arama: {sector} / {city}")
                        new_leads = lead_finder.discover_leads(sector, city)
                        count = len(new_leads) if new_leads else 0
                        expanded_found = count
                        if count > 0:
                            log.info(f"[AUTO] ✅ {sector}/{city}: {count} yeni lead!")
                            total_discovered += count
                        else:
                            _exhausted_combos.add(combo_key)
                    except Exception as e:
                        log.error(f"[AUTO] Genişletilmiş arama hatası ({sector}/{city}): {e}")

                log.info(f"[AUTO] Phase 2 tamamlandı: {expanded_found} lead")
                gc.collect()
                time.sleep(30)

            # ══════════════════════════════════════════════════════
            # PHASE 3: AI SEKTÖR KEŞFİ (her 5. cycle)
            # ══════════════════════════════════════════════════════
            if _automation_state["running"] and cycle % 5 == 0:
                _automation_state["last_action"] = "Phase 3: AI yeni sektör araştırıyor..."
                emit_event("automation_update", {"action": _automation_state["last_action"], "cycle": cycle})
                try:
                    log.info("[AUTO] AI ile yeni sektör araştırılıyor...")
                    import requests as _req
                    _ai_resp = _req.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": config.ANTHROPIC_API_KEY,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json"
                        },
                        json={
                            "model": "claude-sonnet-4-20250514",
                            "max_tokens": 300,
                            "messages": [{"role": "user", "content":
                                f"Hollanda'da araç filosu kullanan sektörler listesi ver. "
                                f"Şu sektörler zaten var: {', '.join(config.SECTORS)}. "
                                f"Bunların dışında 5 yeni sektör öner. Sadece Hollandaca sektör isimlerini virgülle ayırarak ver, başka açıklama ekleme."
                            }]
                        },
                        timeout=30
                    )
                    if _ai_resp.status_code == 200:
                        _new_sectors_text = _ai_resp.json()["content"][0]["text"].strip()
                        _new_sectors = [s.strip() for s in _new_sectors_text.split(",") if s.strip()]
                        _added = [s for s in _new_sectors if s.lower() not in [x.lower() for x in config.SECTORS]]
                        if _added:
                            config.SECTORS.extend(_added[:5])
                            log.info(f"[AUTO] {len(_added)} yeni sektör eklendi: {', '.join(_added[:5])}")
                        else:
                            log.info("[AUTO] Yeni sektör bulunamadı")
                except Exception as e:
                    log.error(f"[AUTO] Sektör keşif hatası: {e}")

                gc.collect()
                time.sleep(10)

            # Tükenmiş kombinasyonları periyodik temizle
            if cycle % 5 == 0:
                cleared = len(_exhausted_combos)
                _exhausted_combos.clear()
                log.info(f"[AUTO] {cleared} tükenmiş kombinasyon sıfırlandı")

            log.info(f"[AUTO] Toplam {total_discovered} yeni lead keşfedildi (cycle {cycle})")

            # ══════════════════════════════════════════════════════
            # PHASE 4: AI LEAD SCORING (batch 20)
            # ══════════════════════════════════════════════════════
            if _automation_state["running"]:
                _automation_state["last_action"] = "Phase 4: Lead'ler puanlanıyor..."
                emit_event("automation_update", {"action": _automation_state["last_action"], "cycle": cycle})
                try:
                    unscored = db.get_all_leads()
                    unscored_leads = [l for l in unscored if not l.get("ai_score") or l.get("ai_score", 0) == 0]
                    if unscored_leads:
                        batch = unscored_leads[:20]
                        scores = lead_scorer.score_batch(batch)
                        for s in scores:
                            db.update_lead_ai_score(s["email"], s.get("score", 50), s.get("reason", ""))
                        log.info(f"[AUTO] {len(scores)} lead puanlandı")
                    else:
                        log.info("[AUTO] Puanlanacak lead yok")
                except Exception as e:
                    log.error(f"[AUTO] Lead scoring hatası: {e}")

                gc.collect()
                time.sleep(10)

            # ══════════════════════════════════════════════════════
            # PHASE 5: EMAIL YAZ + QC + GÖNDER (batch 10)
            # ══════════════════════════════════════════════════════
            if _automation_state["running"]:
                _automation_state["last_action"] = "Phase 5: Email'ler yazılıp gönderiliyor..."
                emit_event("automation_update", {"action": _automation_state["last_action"], "cycle": cycle})
                try:
                    today_sent = db.get_today_sent_count()
                    remaining = max(0, config.DAILY_SEND_LIMIT - today_sent)
                    batch_size = min(10, remaining)  # Bir seferde max 10

                    if batch_size > 0:
                        unsent = db.get_unsent_leads(limit=batch_size)
                        if unsent:
                            log.info(f"[AUTO] {len(unsent)} lead'e email gönderilecek (günlük kalan: {remaining})")
                            stats_result = orch.run_campaign(max_send=len(unsent))
                            log.info(f"[AUTO] Kampanya: {stats_result.sent} gönderildi, "
                                     f"{stats_result.skipped_quality} QC fail, "
                                     f"{stats_result.skipped_compliance} compliance atlandı")
                            emit_event("email_sent", {"count": stats_result.sent})
                        else:
                            log.info("[AUTO] Gönderilecek yeni lead yok")
                    else:
                        log.info(f"[AUTO] Günlük limit doldu ({today_sent}/{config.DAILY_SEND_LIMIT})")
                except Exception as e:
                    log.error(f"[AUTO] Kampanya hatası: {e}")

                gc.collect()
                time.sleep(30)

            # ══════════════════════════════════════════════════════
            # PHASE 6: FOLLOW-UP İŞLEME
            # ══════════════════════════════════════════════════════
            if _automation_state["running"]:
                _automation_state["last_action"] = "Phase 6: Follow-up'lar işleniyor..."
                emit_event("automation_update", {"action": _automation_state["last_action"], "cycle": cycle})
                try:
                    processed = follow_up.process_pending()
                    log.info(f"[AUTO] {len(processed)} follow-up işlendi")
                except Exception as e:
                    log.error(f"[AUTO] Follow-up hatası: {e}")

                gc.collect()
                time.sleep(10)

            # ══════════════════════════════════════════════════════
            # PHASE 7: A/B TEST + RESPONSE TRACKING + CLEANUP
            # ══════════════════════════════════════════════════════
            _automation_state["last_action"] = "Phase 7: A/B test ve yanıt takibi..."
            try:
                variant_stats = db.get_open_rates_by_variant()
                if variant_stats:
                    winner = ab_test.determine_winner(variant_stats)
                    if winner:
                        log.info(f"[AUTO] 🏆 A/B Test kazananı: Varyant {winner}")
            except Exception as e:
                log.error(f"[AUTO] A/B test hatası: {e}")

            try:
                response_tracker.check_inbox()
            except Exception:
                pass

            # ══════════════════════════════════════════════════════
            # CYCLE TAMAMLANDI
            # ══════════════════════════════════════════════════════
            _automation_state["last_action"] = f"Cycle {cycle} tamamlandı — {config.AUTOMATION_INTERVAL} dk bekleniyor..."
            _automation_state["last_cycle_at"] = datetime.now().isoformat()
            _automation_state["stats"] = db.get_stats()
            emit_event("automation_update", {
                "action": "Cycle tamamlandı",
                "cycle": cycle,
                "stats": _automation_state["stats"],
            })

            log.info(f"[AUTO] ═══ Cycle {cycle} tamamlandı ═══ "
                     f"Sektör: {len(config.SECTORS)} | "
                     f"Sonraki: {config.AUTOMATION_INTERVAL} dk sonra")

            gc.collect()  # Son bellek temizliği

            # Sonraki cycle için bekle
            wait_seconds = config.AUTOMATION_INTERVAL * 60
            for _ in range(wait_seconds):
                if not _automation_state["running"]:
                    break
                time.sleep(1)

        except Exception as e:
            log.error(f"[AUTO] Cycle hatası: {e}")
            import traceback
            traceback.print_exc()
            gc.collect()
            time.sleep(60)


def _auto_start_automation():
    """Server basladiginda otomasyonu otomatik baslat."""
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
    """Otomasyon durumunu dondur."""
    return jsonify({
        "running": _automation_state["running"],
        "cycle": _automation_state["cycle"],
        "last_action": _automation_state["last_action"],
        "last_cycle_at": _automation_state["last_cycle_at"],
        "stats": _automation_state["stats"],
    })


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


# ─── AUTOMATION STATE ─────────────────────────────────────────
automation_state = {
    "running": False,
    "thread": None,
    "cycle": 0,
    "current_step": "",
    "last_cycle": None,
    "logs": [],
    "stats": {"leads_found": 0, "scored": 0, "sent": 0, "followups": 0, "errors": 0},
}


def _auto_log(msg):
    """Otomasyon loguna mesaj ekle (son 100 satır tut)."""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    automation_state["logs"].append(line)
    if len(automation_state["logs"]) > 100:
        automation_state["logs"] = automation_state["logs"][-100:]
    log.info(f"[AUTOMATION] {msg}")


def _run_automation_cycle():
    """Tek bir otomasyon döngüsü — 6 aşama."""
    import traceback

    automation_state["cycle"] += 1
    cycle = automation_state["cycle"]
    _auto_log(f"=== Döngü {cycle} başladı ===")
    stats = automation_state["stats"]

    # 1. LEAD KEŞFİ (AI-only — shared hosting'de hızlı)
    automation_state["current_step"] = "1. Lead Keşfi (AI)"
    _auto_log("Aşama 1: AI ile lead keşfi...")
    try:
        sectors_to_search = config.SECTORS[:3] if hasattr(config, 'SECTORS') else ["transport"]
        for sector in sectors_to_search:
            if not automation_state["running"]:
                break
            try:
                _auto_log(f"  Sektör: {sector}...")
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
                                    discovery_score=65,
                                )
                                saved += 1
                            except Exception:
                                pass
                    stats["leads_found"] += saved
                    _auto_log(f"  {sector}: {saved} yeni lead kaydedildi")
                else:
                    _auto_log(f"  {sector}: lead bulunamadı")
            except Exception as e:
                _auto_log(f"  {sector} HATA: {str(e)[:80]}")
            time.sleep(2)
    except Exception as e:
        _auto_log(f"  Lead keşfi HATA: {str(e)[:80]}")
        stats["errors"] += 1

    if not automation_state["running"]:
        return

    # 2. AI PUANLAMA
    automation_state["current_step"] = "2. AI Puanlama"
    _auto_log("Aşama 2: AI puanlama...")
    try:
        unsent = db.get_unsent_leads(limit=20)
        unscored = [l for l in unsent if not l.get("ai_score")]
        if unscored:
            scores = lead_scorer.score_batch(unscored[:10])
            for sd in scores:
                db.update_lead_ai_score(
                    email=sd["email"], score=sd.get("score", 50),
                    reason=sd.get("reason", ""))
            stats["scored"] += len(scores)
            _auto_log(f"  {len(scores)} lead puanlandı")
        else:
            _auto_log("  Puanlanacak yeni lead yok")
    except Exception as e:
        _auto_log(f"  Puanlama HATA: {e}")
        stats["errors"] += 1

    if not automation_state["running"]:
        return

    # 3. EMAIL YAZMA + KALİTE KONTROL + GÖNDERİM
    automation_state["current_step"] = "3. Email Yazma + Gönderim"
    _auto_log("Aşama 3: Email yazma ve gönderim...")
    try:
        from dataclasses import asdict
        from core.send_engine import SendEngine, EmailMessage
        send_eng = SendEngine()
        leads_to_send = db.get_unsent_leads(limit=config.DAILY_SEND_LIMIT)
        sent_this_cycle = 0
        for lead in leads_to_send:
            if not automation_state["running"]:
                break
            if sent_this_cycle >= 10:  # Max 10 per cycle
                break

            email = (lead.get("email") or "").strip()
            company = lead.get("company") or "?"
            if not email or db.is_unsubscribed(email) or db.is_duplicate_email(email):
                continue

            try:
                draft = copywriter.write(lead)
                if not draft:
                    continue

                # QC check
                qc = quality.check(
                    subject=draft.chosen_subject,
                    body_text=draft.body_text,
                    company_name=company,
                    body_html=draft.body_html)

                if qc.score < 70:
                    _auto_log(f"  QC düşük ({qc.score}): {company} — atlandı")
                    continue

                # Save draft
                draft_dict = asdict(draft) if hasattr(draft, '__dataclass_fields__') else {}
                draft_dict["qc_score"] = qc.score
                db.save_draft(email, draft_dict)

                # Send
                msg = EmailMessage(
                    to_email=email, to_name=company,
                    subject=draft.chosen_subject,
                    html_body=draft.body_html, text_body=draft.body_text,
                    lead_id=email)
                result = send_eng.send(msg)
                if result.success:
                    sent_this_cycle += 1
                    stats["sent"] += 1
                    db.log_sent(email=email, company=company,
                                sector=lead.get("sector", ""),
                                subject=draft.chosen_subject,
                                method=result.method,
                                message_id=result.message_id)
                    _auto_log(f"  SENT: {company} ({email})")
                    # Delay between sends
                    import random
                    time.sleep(random.randint(15, 45))
                else:
                    _auto_log(f"  FAIL: {company} — {result.error}")
                    stats["errors"] += 1
            except Exception as e:
                _auto_log(f"  Hata ({company}): {e}")
                stats["errors"] += 1

        _auto_log(f"  Bu döngüde {sent_this_cycle} email gönderildi")
    except Exception as e:
        _auto_log(f"  Gönderim HATA: {e}")
        stats["errors"] += 1

    if not automation_state["running"]:
        return

    # 4. FOLLOW-UP
    automation_state["current_step"] = "4. Follow-Up"
    _auto_log("Aşama 4: Follow-up kontrolü...")
    try:
        from agents.orchestrator import Orchestrator
        orch = Orchestrator()
        followups_sent = orch.process_followups()
        stats["followups"] += len(followups_sent)
        _auto_log(f"  {len(followups_sent)} follow-up gönderildi")
    except Exception as e:
        _auto_log(f"  Follow-up HATA: {e}")

    # 5. YANIT TAKİP
    automation_state["current_step"] = "5. Yanıt Takip"
    _auto_log("Aşama 5: Yanıt takibi...")
    _auto_log("  (Yanıt takip BCC üzerinden pasif çalışıyor)")

    # 6. TAMAMLANDI
    automation_state["current_step"] = "6. Döngü tamamlandı"
    automation_state["last_cycle"] = datetime.now().isoformat()
    _auto_log(f"=== Döngü {cycle} tamamlandı ===")


def _auto_start_automation():
    """Otomasyon döngüsünü başlat — her 30 dakikada tekrar."""
    automation_state["running"] = True
    interval = getattr(config, "AUTOMATION_INTERVAL", 30) * 60  # dakika -> saniye
    _auto_log("Otomasyon pipeline başlatıldı")
    while automation_state["running"]:
        try:
            _run_automation_cycle()
        except Exception as e:
            import traceback
            _auto_log(f"DÖNGÜ HATASI: {e}")
            _auto_log(f"Traceback: {traceback.format_exc()[:300]}")
        if not automation_state["running"]:
            break
        automation_state["current_step"] = "Bekleniyor..."
        _auto_log(f"Sonraki döngü {interval // 60} dakika sonra...")
        # 30 sn'lik parçalarda bekle (durdurma için duyarlı)
        for _ in range(interval // 30):
            if not automation_state["running"]:
                break
            time.sleep(30)

    _auto_log("Otomasyon durduruldu")
    automation_state["current_step"] = ""


@app.route("/api/automation/start", methods=["POST"])
def api_automation_start():
    """Otomasyon pipeline'ı başlat."""
    if automation_state["running"]:
        return jsonify({"ok": True, "message": "Zaten çalışıyor"})
    automation_state["running"] = True
    automation_state["stats"] = {"leads_found": 0, "scored": 0, "sent": 0, "followups": 0, "errors": 0}
    t = threading.Thread(target=_auto_start_automation, daemon=True)
    automation_state["thread"] = t
    t.start()
    return jsonify({"ok": True, "message": "Otomasyon başlatıldı"})


@app.route("/api/automation/stop", methods=["POST"])
def api_automation_stop():
    """Otomasyon pipeline'ı durdur."""
    automation_state["running"] = False
    automation_state["current_step"] = "Durduruluyor..."
    _auto_log("Durdurma isteği alındı")
    return jsonify({"ok": True, "message": "Otomasyon durduruluyor..."})


@app.route("/api/automation/status")
def api_automation_status():
    """Otomasyon durumunu döndür."""
    return jsonify({
        "running": automation_state["running"],
        "cycle": automation_state["cycle"],
        "current_step": automation_state["current_step"],
        "last_cycle": automation_state["last_cycle"],
        "stats": automation_state["stats"],
        "logs": automation_state["logs"][-30:],  # Son 30 log satırı
    })


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

    # Otomasyonu otomatik baslat
    auto_thread = threading.Thread(target=_auto_start_automation, daemon=True)
    auto_thread.start()

    if HAS_SOCKETIO:
        socketio.run(app, host="0.0.0.0", port=5000, debug=True,
                     allow_unsafe_werkzeug=True)
    else:
        app.run(host="0.0.0.0", port=5000, debug=True)
