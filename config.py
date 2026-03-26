"""
config.py — SmartMailer Ultimate Konfigürasyon
SmartMailer Pro + FleetTrack CRM birleşik ayarlar.
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # ─── AI ──────────────────────────────────────────────────────
    ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL       = "claude-haiku-4-5-20251001"

    # ─── BREVO ───────────────────────────────────────────────────
    BREVO_API_KEY      = os.getenv("BREVO_API_KEY", "")
    BREVO_SMTP_HOST    = os.getenv("BREVO_SMTP_HOST", "smtp-relay.brevo.com")
    BREVO_SMTP_PORT    = int(os.getenv("BREVO_SMTP_PORT", "587"))
    BREVO_SMTP_USER    = os.getenv("BREVO_SMTP_USER", "")
    BREVO_SMTP_PASS    = os.getenv("BREVO_SMTP_PASS", "")

    # ─── GÖNDEREN ────────────────────────────────────────────────
    SENDER_NAME        = os.getenv("SENDER_NAME", "Fleet Track Holland")
    SENDER_EMAIL       = os.getenv("SENDER_EMAIL", "")
    COMPANY_NAME       = os.getenv("COMPANY_NAME", "FleetTrack Holland B.V.")
    COMPANY_KVK        = os.getenv("COMPANY_KVK", "")
    COMPANY_ADDRESS    = os.getenv("COMPANY_ADDRESS", "")
    COMPANY_PHONE      = os.getenv("COMPANY_PHONE", "")
    COMPANY_WEBSITE    = os.getenv("COMPANY_WEBSITE", "https://www.fleettrackholland.nl")
    UNSUBSCRIBE_URL    = os.getenv("UNSUBSCRIBE_URL", "https://app.fleettrackholland.nl/unsubscribe")
    BCC_EMAIL          = os.getenv("BCC_EMAIL", "sales@fleettrackholland.nl")

    # ─── ÇALIŞMA MODU ────────────────────────────────────────────
    HUMAN_REVIEW       = os.getenv("HUMAN_REVIEW", "false").lower() == "true"
    DELAY_MIN          = int(os.getenv("DELAY_MIN", "15"))
    DELAY_MAX          = int(os.getenv("DELAY_MAX", "35"))
    DAILY_SEND_LIMIT   = int(os.getenv("DAILY_SEND_LIMIT", "650"))
    MONTHLY_SEND_LIMIT = int(os.getenv("MONTHLY_SEND_LIMIT", "20000"))

    # ─── PERFORMANCE ─────────────────────────────────────────────
    QC_MIN_SCORE       = int(os.getenv("QC_MIN_SCORE", "90"))
    QC_MAX_RETRIES     = int(os.getenv("QC_MAX_RETRIES", "5"))
    PARALLEL_WORKERS   = int(os.getenv("PARALLEL_WORKERS", "5"))
    FOLLOWUP_ENABLED   = os.getenv("FOLLOWUP_ENABLED", "true").lower() == "true"
    FOLLOWUP_DAY_1     = int(os.getenv("FOLLOWUP_DAY_1", "3"))
    FOLLOWUP_DAY_2     = int(os.getenv("FOLLOWUP_DAY_2", "7"))
    FOLLOWUP_DAY_3     = int(os.getenv("FOLLOWUP_DAY_3", "14"))

    # ─── SMART SENDING STRATEGY ──────────────────────────────────
    BEST_SEND_HOURS    = [(9, 11), (14, 16)]  # CET — B2B optimal saatler
    WEEKEND_CAPACITY   = float(os.getenv("WEEKEND_CAPACITY", "0.2"))  # Haftasonu %20
    MAX_PER_SECTOR_DAILY = int(os.getenv("MAX_PER_SECTOR_DAILY", "60"))

    # ─── PASSENGER / PRODUCTION DETECTION ────────────────────────
    IS_PASSENGER = bool(
        os.environ.get("PASSENGER_BASE_URI")
        or "passenger" in os.environ.get("SERVER_SOFTWARE", "").lower()
        or os.environ.get("PASSENGER_MODE", "").lower() == "true"
    )

    # ─── OTOMASYON ───────────────────────────────────────────────
    SECTORS            = os.getenv("SECTORS",
        "transport,bouw,schoonmaak,logistiek,koerier,"
        "verhuisbedrijf,taxi,ambulance,bezorgdienst,"
        "groenvoorziening,installatiebedrijf,catering,"
        "afvalverwerking,beveiliging,thuiszorg,"
        "loodgieter,elektricien,dakdekker,schildersbedrijf,"
        "vuilophaal,autorijschool,garage,autoverhuur,"
        "glas,stukadoor,timmerman,metselaar"
    ).split(",")
    TARGET_LOCATION    = os.getenv("TARGET_LOCATION", "Nederland")
    # Passenger'da AUTO_START devre dışı — cron ile çalıştırılır
    AUTO_START         = (os.getenv("AUTO_START", "true").lower() == "true") and not IS_PASSENGER
    DEPLOY_SECRET      = os.getenv("DEPLOY_SECRET", "fleettrack2026")
    AUTOMATION_INTERVAL = int(os.getenv("AUTOMATION_INTERVAL", "15"))

    # ─── LEAD DISCOVERY (ULTIMATE) ───────────────────────────────
    MAX_LEADS_PER_SEARCH    = int(os.getenv("MAX_LEADS_PER_SEARCH", "500"))
    PARALLEL_CITY_WORKERS   = int(os.getenv("PARALLEL_CITY_WORKERS", "1"))
    TELEFOONBOEK_ENABLED    = os.getenv("TELEFOONBOEK_ENABLED", "true").lower() == "true"
    OPENSTREETMAP_ENABLED   = os.getenv("OPENSTREETMAP_ENABLED", "true").lower() == "true"
    EMAIL_VERIFY_MX         = os.getenv("EMAIL_VERIFY_MX", "true").lower() == "true"
    EMAIL_VERIFY_SMTP       = os.getenv("EMAIL_VERIFY_SMTP", "false").lower() == "true"

    # ─── DOSYA YOLLARI ───────────────────────────────────────────
    BASE_DIR           = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR           = os.path.join(BASE_DIR, "data")
    INPUT_DIR          = os.path.join(DATA_DIR, "input")
    OUTPUT_DIR         = os.path.join(DATA_DIR, "output")
    LOGS_DIR           = os.path.join(DATA_DIR, "logs")
    UNSUBSCRIBE_FILE   = os.path.join(DATA_DIR, "unsubscribe_list.csv")
    SENT_LOG_FILE      = os.path.join(OUTPUT_DIR, "sent_log.csv")

    def validate(self) -> list[str]:
        errors = []
        if not self.ANTHROPIC_API_KEY:
            errors.append("ANTHROPIC_API_KEY eksik")
        if not self.BREVO_API_KEY and not self.BREVO_SMTP_PASS:
            errors.append("BREVO_API_KEY veya BREVO_SMTP_PASS gerekli")
        if not self.SENDER_EMAIL:
            errors.append("SENDER_EMAIL eksik")
        return errors

config = Config()
