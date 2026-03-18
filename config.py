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
    UNSUBSCRIBE_URL    = os.getenv("UNSUBSCRIBE_URL", "https://www.fleettrackholland.nl/afmelden")

    # ─── ÇALIŞMA MODU ────────────────────────────────────────────
    TEST_MODE          = os.getenv("TEST_MODE", "true").lower() == "true"
    HUMAN_REVIEW       = os.getenv("HUMAN_REVIEW", "false").lower() == "true"
    DELAY_MIN          = int(os.getenv("DELAY_MIN", "25"))
    DELAY_MAX          = int(os.getenv("DELAY_MAX", "55"))
    DAILY_SEND_LIMIT   = int(os.getenv("DAILY_SEND_LIMIT", "80"))

    # ─── PERFORMANCE ─────────────────────────────────────────────
    QC_MIN_SCORE       = int(os.getenv("QC_MIN_SCORE", "90"))
    QC_MAX_RETRIES     = int(os.getenv("QC_MAX_RETRIES", "5"))
    PARALLEL_WORKERS   = int(os.getenv("PARALLEL_WORKERS", "3"))
    FOLLOWUP_ENABLED   = os.getenv("FOLLOWUP_ENABLED", "true").lower() == "true"
    FOLLOWUP_DAY_1     = int(os.getenv("FOLLOWUP_DAY_1", "3"))
    FOLLOWUP_DAY_2     = int(os.getenv("FOLLOWUP_DAY_2", "7"))
    FOLLOWUP_DAY_3     = int(os.getenv("FOLLOWUP_DAY_3", "14"))

    # ─── OTOMASYON ───────────────────────────────────────────────
    SECTORS            = os.getenv("SECTORS",
        "transport,bouw,schoonmaak,logistiek,koerier,"
        "verhuisbedrijf,taxi,ambulance,bezorgdienst,"
        "groenvoorziening,installatiebedrijf,catering,"
        "afvalverwerking,beveiliging,thuiszorg,"
        "loodgieter,elektricien,dakdekker,schildersbedrijf"
    ).split(",")
    TARGET_LOCATION    = os.getenv("TARGET_LOCATION", "Nederland")
    AUTO_START         = os.getenv("AUTO_START", "true").lower() == "true"
    AUTOMATION_INTERVAL = int(os.getenv("AUTOMATION_INTERVAL", "30"))

    # ─── LEAD DISCOVERY (ULTIMATE) ───────────────────────────────
    MAX_LEADS_PER_SEARCH    = int(os.getenv("MAX_LEADS_PER_SEARCH", "300"))
    PARALLEL_CITY_WORKERS   = int(os.getenv("PARALLEL_CITY_WORKERS", "5"))
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
        if not self.TEST_MODE:
            if not self.BREVO_API_KEY and not self.BREVO_SMTP_PASS:
                errors.append("BREVO_API_KEY veya BREVO_SMTP_PASS gerekli")
            if not self.SENDER_EMAIL:
                errors.append("SENDER_EMAIL eksik")
        return errors

config = Config()
