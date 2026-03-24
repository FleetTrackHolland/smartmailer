"""
core/database.py — SmartMailer Ultimate SQLite Persistence Layer
Tüm verileri kalıcı olarak saklar: leads, drafts, sent_log, campaigns, events,
activities, reminders, opt_out. SmartMailer Pro + FleetTrack CRM birleşimi.
"""
import os
import json
import sqlite3
from datetime import datetime
from contextlib import contextmanager
from config import config
from core.logger import get_logger

log = get_logger("database")

DB_PATH = os.path.join(config.DATA_DIR, "smartmailer_ultimate.db")


class Database:
    """Thread-safe SQLite veritabanı yöneticisi."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_tables()
        log.info(f"Veritabanı hazır: {self.db_path}")

    @contextmanager
    def _conn(self):
        """Thread-safe bağlantı context manager."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ─── TABLE CREATION ───────────────────────────────────────────

    def _init_tables(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    company TEXT DEFAULT '',
                    sector TEXT DEFAULT '',
                    location TEXT DEFAULT '',
                    vehicles INTEGER DEFAULT 0,
                    phone TEXT DEFAULT '',
                    website TEXT DEFAULT '',
                    score INTEGER DEFAULT 0,
                    ai_score INTEGER DEFAULT 0,
                    ai_score_reason TEXT DEFAULT '',
                    status TEXT DEFAULT 'new',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    subject_a TEXT DEFAULT '',
                    subject_b TEXT DEFAULT '',
                    subject_c TEXT DEFAULT '',
                    chosen_subject TEXT DEFAULT '',
                    body_html TEXT DEFAULT '',
                    body_text TEXT DEFAULT '',
                    qc_score INTEGER DEFAULT 0,
                    qc_passed INTEGER DEFAULT 0,
                    qc_issues TEXT DEFAULT '[]',
                    qc_method TEXT DEFAULT 'regex',
                    compliance_ok INTEGER DEFAULT 1,
                    compliance_reason TEXT DEFAULT '',
                    auto_fix_retries INTEGER DEFAULT 0,
                    version INTEGER DEFAULT 1,
                    ab_variant TEXT DEFAULT 'A',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (email) REFERENCES leads(email)
                );

                CREATE TABLE IF NOT EXISTS sent_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    company TEXT DEFAULT '',
                    sector TEXT DEFAULT '',
                    subject TEXT DEFAULT '',
                    ab_variant TEXT DEFAULT 'A',
                    method TEXT DEFAULT '',
                    message_id TEXT DEFAULT '',
                    test_mode INTEGER DEFAULT 0,
                    campaign_id TEXT DEFAULT '',
                    sent_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'running',
                    total_leads INTEGER DEFAULT 0,
                    processed INTEGER DEFAULT 0,
                    sent INTEGER DEFAULT 0,
                    skipped_compliance INTEGER DEFAULT 0,
                    skipped_quality INTEGER DEFAULT 0,
                    failed INTEGER DEFAULT 0,
                    test_mode INTEGER DEFAULT 0,
                    started_at TEXT DEFAULT (datetime('now')),
                    ended_at TEXT
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    message_id TEXT DEFAULT '',
                    event_type TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    received_at TEXT DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
                CREATE INDEX IF NOT EXISTS idx_leads_ai_score ON leads(ai_score DESC);
                CREATE INDEX IF NOT EXISTS idx_drafts_email ON drafts(email);
                CREATE INDEX IF NOT EXISTS idx_sent_email ON sent_log(email);
                CREATE INDEX IF NOT EXISTS idx_sent_campaign ON sent_log(campaign_id);
                CREATE INDEX IF NOT EXISTS idx_events_email ON events(email);
                CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

                -- v4: Follow-Up tablosu
                CREATE TABLE IF NOT EXISTS followups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    step INTEGER DEFAULT 1,
                    scheduled_at TEXT NOT NULL,
                    sent_at TEXT,
                    status TEXT DEFAULT 'pending',
                    original_subject TEXT DEFAULT '',
                    company TEXT DEFAULT '',
                    sector TEXT DEFAULT '',
                    vehicles TEXT DEFAULT '',
                    campaign_id TEXT DEFAULT '',
                    subject TEXT DEFAULT '',
                    body_html TEXT DEFAULT '',
                    body_text TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- v4: Response Tracking tablosu
                CREATE TABLE IF NOT EXISTS responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    classification TEXT DEFAULT 'unknown',
                    confidence REAL DEFAULT 0.0,
                    sentiment INTEGER DEFAULT 50,
                    summary TEXT DEFAULT '',
                    response_text TEXT DEFAULT '',
                    original_subject TEXT DEFAULT '',
                    auto_reply_sent INTEGER DEFAULT 0,
                    classified_at TEXT DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_followups_email ON followups(email);
                CREATE INDEX IF NOT EXISTS idx_followups_status ON followups(status);
                CREATE INDEX IF NOT EXISTS idx_followups_scheduled ON followups(scheduled_at);
                CREATE INDEX IF NOT EXISTS idx_responses_email ON responses(email);
                CREATE INDEX IF NOT EXISTS idx_responses_class ON responses(classification);

                -- v5: Unsubscribe tablosu
                CREATE TABLE IF NOT EXISTS unsubscribes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    reason TEXT DEFAULT '',
                    unsubscribed_at TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_unsubscribes_email ON unsubscribes(email);
            """)

            # Safe ALTER TABLE for new columns (ignore if already exist)
            for col_def in [
                "ALTER TABLE leads ADD COLUMN contact_person TEXT DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN discovery_score INTEGER DEFAULT 0",
                "ALTER TABLE leads ADD COLUMN source TEXT DEFAULT 'csv'",
                "ALTER TABLE leads ADD COLUMN is_hot INTEGER DEFAULT 0",
                "ALTER TABLE leads ADD COLUMN icebreaker TEXT DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN notes TEXT DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN next_action TEXT DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN followup_1_date TEXT DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN followup_2_date TEXT DEFAULT ''",
            ]:
                try:
                    conn.execute(col_def)
                except sqlite3.OperationalError:
                    pass  # Column already exists

            # FleetTrack CRM tabloları
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS activities (
                    id TEXT PRIMARY KEY,
                    lead_email TEXT NOT NULL,
                    type TEXT DEFAULT 'manual',
                    text TEXT DEFAULT '',
                    date TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (lead_email) REFERENCES leads(email)
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    lead_email TEXT NOT NULL,
                    text TEXT DEFAULT '',
                    date TEXT DEFAULT '',
                    completed INTEGER DEFAULT 0,
                    FOREIGN KEY (lead_email) REFERENCES leads(email)
                );

                CREATE TABLE IF NOT EXISTS opt_out (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    reason TEXT DEFAULT '',
                    ip_address TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_activities_lead ON activities(lead_email);
                CREATE INDEX IF NOT EXISTS idx_reminders_lead ON reminders(lead_email);
                CREATE INDEX IF NOT EXISTS idx_opt_out_email ON opt_out(email);

                -- v5: Agent self-improvement (learning) tablosu
                CREATE TABLE IF NOT EXISTS agent_learning (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    learning_type TEXT DEFAULT 'feedback',
                    context TEXT DEFAULT '',
                    lesson TEXT DEFAULT '',
                    metric_before REAL DEFAULT 0,
                    metric_after REAL DEFAULT 0,
                    applied INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_agent_learning_name ON agent_learning(agent_name);
                CREATE INDEX IF NOT EXISTS idx_agent_learning_type ON agent_learning(learning_type);
            """)

    # ─── LEADS CRUD ───────────────────────────────────────────────

    def upsert_lead(self, lead: dict) -> int:
        """Lead ekle veya güncelle. Email unique key."""
        email = (lead.get("Email") or lead.get("email") or "").strip().lower()
        if not email:
            return 0

        vehicles = lead.get("Vehicles") or lead.get("vehicles") or 0
        try:
            vehicles = int(vehicles)
        except (ValueError, TypeError):
            vehicles = 0

        with self._conn() as conn:
            conn.execute("""
                INSERT INTO leads (email, company, sector, location, vehicles, phone, website, score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    company = excluded.company,
                    sector = excluded.sector,
                    location = excluded.location,
                    vehicles = excluded.vehicles,
                    phone = excluded.phone,
                    website = excluded.website,
                    score = excluded.score,
                    updated_at = datetime('now')
            """, (
                email,
                lead.get("Company") or lead.get("company") or "",
                lead.get("Sector") or lead.get("sector") or "",
                lead.get("Location") or lead.get("location") or "",
                vehicles,
                lead.get("Phone") or lead.get("phone") or "",
                lead.get("Website") or lead.get("website") or "",
                lead.get("Score") or lead.get("score") or 0,
            ))
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def import_leads_from_csv(self, csv_path: str) -> int:
        """CSV dosyasından lead'leri içe aktar."""
        import csv
        count = 0
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                self.upsert_lead(dict(row))
                count += 1
        log.info(f"{count} lead CSV'den içe aktarıldı: {csv_path}")
        return count

    def add_discovered_lead(self, email: str, company: str = "",
                            sector: str = "", location: str = "",
                            vehicles: str = "", website: str = "",
                            phone: str = "", contact_person: str = "",
                            discovery_score: int = 60, source: str = "web_discovery",
                            icebreaker: str = "") -> bool:
        """Keşfedilen lead'i veritabanına ekle (upsert)."""
        email = email.strip().lower()
        if not email or "@" not in email:
            return False

        try:
            veh = int(vehicles) if vehicles and str(vehicles).isdigit() else 0
        except (ValueError, TypeError):
            veh = 0

        lead_data = {
            "email": email,
            "company": company,
            "sector": sector,
            "location": location,
            "vehicles": veh,
            "phone": phone,
            "website": website,
            "score": discovery_score,
        }
        try:
            self.upsert_lead(lead_data)
            with self._conn() as conn:
                conn.execute("""
                    UPDATE leads SET
                        source = ?,
                        contact_person = ?,
                        icebreaker = ?,
                        discovery_score = ?,
                        status = CASE WHEN status = 'new' THEN 'discovered' ELSE status END,
                        updated_at = datetime('now')
                    WHERE email = ?
                """, (source, contact_person, icebreaker, discovery_score, email))
            return True
        except Exception as e:
            log.debug(f"Lead kayıt hatası ({email}): {e}")
            return False

    def get_all_leads(self, order_by_ai_score: bool = False) -> list[dict]:
        """Tüm lead'leri getir."""
        order = "ai_score DESC, score DESC" if order_by_ai_score else "id ASC"
        with self._conn() as conn:
            rows = conn.execute(f"SELECT * FROM leads ORDER BY {order}").fetchall()
            return [dict(r) for r in rows]

    def get_lead_by_email(self, email: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM leads WHERE email = ?",
                               (email.strip().lower(),)).fetchone()
            return dict(row) if row else None

    def lead_exists(self, email: str) -> bool:
        """Email zaten veritabanında mı?"""
        with self._conn() as conn:
            row = conn.execute("SELECT 1 FROM leads WHERE email = ? LIMIT 1",
                               (email.strip().lower(),)).fetchone()
            return row is not None

    def get_unsent_leads(self, limit: int = 100) -> list[dict]:
        """Henüz gönderilmemiş lead'leri getir (unsubscribe/opt-out hariç)."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT l.* FROM leads l
                LEFT JOIN sent_log s ON l.email = s.email
                LEFT JOIN unsubscribes u ON l.email = u.email
                LEFT JOIN opt_out o ON l.email = o.email
                WHERE s.email IS NULL
                  AND u.email IS NULL
                  AND o.email IS NULL
                  AND l.email != ''
                  AND l.status NOT IN ('excluded', 'opted_out', 'invalid')
                ORDER BY l.ai_score DESC, l.score DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def is_unsubscribed(self, email: str) -> bool:
        """Email unsubscribe veya opt-out listesinde mi?"""
        email = email.strip().lower()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM unsubscribes WHERE email = ? LIMIT 1",
                (email,)
            ).fetchone()
            if row:
                return True
            row = conn.execute(
                "SELECT 1 FROM opt_out WHERE email = ? LIMIT 1",
                (email,)
            ).fetchone()
            return row is not None

    def get_leads_for_scoring(self, limit: int = 30) -> list[dict]:
        """AI puanlaması yapılmamış lead'leri getir."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM leads
                WHERE (ai_score = 0 OR ai_score IS NULL)
                  AND email != ''
                ORDER BY score DESC, created_at ASC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_leads_for_rescoring(self, min_score: int = 90, limit: int = 20) -> list[dict]:
        """AI skoru düşük olan lead'leri yeniden puanlamak için getir."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM leads
                WHERE ai_score > 0 AND ai_score < ?
                  AND email != ''
                ORDER BY ai_score DESC, score DESC
                LIMIT ?
            """, (min_score, limit)).fetchall()
            return [dict(r) for r in rows]

    def is_duplicate_email(self, email: str) -> bool:
        """Bu email daha önce gönderilmiş mi?"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM sent_log WHERE email = ? LIMIT 1",
                (email.strip().lower(),)
            ).fetchone()
            return row is not None

    def update_lead_ai_score(self, email: str, score: int, reason: str = ""):
        with self._conn() as conn:
            conn.execute("""
                UPDATE leads SET ai_score = ?, ai_score_reason = ?, updated_at = datetime('now')
                WHERE email = ?
            """, (score, reason, email.strip().lower()))

    def flag_lead_hot(self, email: str):
        """Lead'i 'hot' olarak işaretle (yanıt var)."""
        with self._conn() as conn:
            conn.execute("""
                UPDATE leads SET is_hot = 1, status = 'hot', updated_at = datetime('now')
                WHERE email = ?
            """, (email.strip().lower(),))

    def mark_lead_invalid(self, email: str):
        """Bounce — geçersiz lead."""
        with self._conn() as conn:
            conn.execute("""
                UPDATE leads SET status = 'invalid', updated_at = datetime('now')
                WHERE email = ?
            """, (email.strip().lower(),))

    def update_lead_status(self, email: str, status: str):
        """Lead durumunu güncelle."""
        with self._conn() as conn:
            conn.execute("""
                UPDATE leads SET status = ?, updated_at = datetime('now')
                WHERE email = ?
            """, (status, email.strip().lower()))

    # ─── DRAFTS CRUD ──────────────────────────────────────────────

    def save_draft(self, email: str, draft_data: dict) -> int:
        """Taslak kaydet veya güncelle."""
        email = email.strip().lower()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id, version FROM drafts WHERE email = ? ORDER BY version DESC LIMIT 1",
                (email,)
            ).fetchone()

            version = (existing["version"] + 1) if existing else 1

            conn.execute("""
                INSERT INTO drafts (email, subject_a, subject_b, subject_c, chosen_subject,
                    body_html, body_text, qc_score, qc_passed, qc_issues, qc_method,
                    compliance_ok, compliance_reason, auto_fix_retries, version, ab_variant)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                email,
                draft_data.get("subject_a", ""),
                draft_data.get("subject_b", ""),
                draft_data.get("subject_c", ""),
                draft_data.get("chosen_subject", ""),
                draft_data.get("body_html", ""),
                draft_data.get("body_text", ""),
                draft_data.get("qc_score", 0),
                1 if draft_data.get("qc_passed") else 0,
                json.dumps(draft_data.get("qc_issues", [])),
                draft_data.get("qc_method", "regex"),
                1 if draft_data.get("compliance_ok", True) else 0,
                draft_data.get("compliance_reason", ""),
                draft_data.get("auto_fix_retries", 0),
                version,
                draft_data.get("ab_variant", "A"),
            ))
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def get_latest_drafts(self) -> dict:
        """Her email için en son taslağı getir."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT d.* FROM drafts d
                INNER JOIN (
                    SELECT email, MAX(version) as max_ver FROM drafts GROUP BY email
                ) latest ON d.email = latest.email AND d.version = latest.max_ver
                ORDER BY d.created_at DESC
            """).fetchall()

            result = {}
            for r in rows:
                d = dict(r)
                d["qc_issues"] = json.loads(d.get("qc_issues") or "[]")
                d["qc_passed"] = bool(d.get("qc_passed"))
                d["compliance_ok"] = bool(d.get("compliance_ok"))
                lead = self.get_lead_by_email(d["email"])
                d["lead"] = lead
                result[d["email"]] = d
            return result

    def get_draft_by_email(self, email: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("""
                SELECT * FROM drafts WHERE email = ?
                ORDER BY version DESC LIMIT 1
            """, (email.strip().lower(),)).fetchone()
            if row:
                d = dict(row)
                d["qc_issues"] = json.loads(d.get("qc_issues") or "[]")
                d["qc_passed"] = bool(d.get("qc_passed"))
                d["compliance_ok"] = bool(d.get("compliance_ok"))
                d["lead"] = self.get_lead_by_email(d["email"])
                return d
            return None

    # ─── SENT LOG ─────────────────────────────────────────────────

    def log_sent(self, email: str, company: str = "", sector: str = "",
                 subject: str = "", method: str = "", message_id: str = "",
                 campaign_id: str = "", ab_variant: str = "A",
                 test_mode: bool = False):
        """Email gönderimini logla — sadece ilk gönderimi kaydet."""
        email_lower = email.lower().strip()
        with self._conn() as conn:
            # Duplicate gönderimi önle
            already = conn.execute(
                "SELECT 1 FROM sent_log WHERE email = ? LIMIT 1",
                (email_lower,)
            ).fetchone()
            if already:
                log.debug(f"[DB] Duplicate gönderim engellendi: {email_lower}")
                return
            conn.execute("""
                INSERT INTO sent_log (email, company, sector, subject, ab_variant,
                    method, message_id, test_mode, campaign_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (email_lower, company, sector, subject, ab_variant,
                  method, message_id, 0, campaign_id))

    def get_sent_emails(self) -> list[dict]:
        """Gönderilmiş email kayıtlarını dict listesi olarak döndür."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT email, sent_at, method FROM sent_log"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_sent_email_set(self) -> set:
        """Gönderilmiş email adreslerini set olarak döndür."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT email FROM sent_log"
            ).fetchall()
            return {r["email"] for r in rows}

    def get_recent_sent(self, limit: int = 20) -> list[dict]:
        """Son gönderilen emailleri listele."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT s.email, s.company, s.sector, s.subject, s.method,
                       s.ab_variant, s.sent_at, d.qc_score
                FROM sent_log s
                LEFT JOIN drafts d ON s.email = d.email
                ORDER BY s.sent_at DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_sent_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM sent_log").fetchone()[0]

    def get_today_sent_count(self) -> int:
        """Bugün gönderilen email sayısını döndür."""
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM sent_log WHERE date(sent_at) = date('now')"
            ).fetchone()[0]

    def get_all_sent_with_content(self, limit: int = 200) -> list[dict]:
        """Tüm gönderilen emailleri draft içerikleriyle birlikte döndür."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT s.email, s.company, s.sector, s.subject, s.method,
                       s.message_id, s.ab_variant, s.sent_at,
                       d.body_html, d.body_text, d.chosen_subject,
                       d.qc_score, d.subject_a, d.subject_b, d.subject_c,
                       CASE WHEN e_open.id IS NOT NULL THEN 1 ELSE 0 END as was_opened,
                       CASE WHEN r.id IS NOT NULL THEN 1 ELSE 0 END as replied
                FROM sent_log s
                LEFT JOIN drafts d ON s.email = d.email
                LEFT JOIN events e_open ON s.email = e_open.email AND e_open.event_type IN ('open','opened','unique_opened')
                LEFT JOIN responses r ON s.email = r.email
                GROUP BY s.id
                ORDER BY s.sent_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_sent_email_content(self, email: str) -> dict:
        """Gönderilmiş email içeriğini sent_log + drafts birleştirerek döndür."""
        with self._conn() as conn:
            row = conn.execute("""
                SELECT s.email, s.company, s.subject, s.method, s.sent_at, s.ab_variant,
                       d.body_html, d.body_text, d.subject_a, d.subject_b, d.subject_c,
                       d.chosen_subject, d.qc_score
                FROM sent_log s
                LEFT JOIN drafts d ON s.email = d.email
                WHERE s.email = ?
                ORDER BY s.sent_at DESC
                LIMIT 1
            """, (email.lower(),)).fetchone()
            if row:
                return dict(row)
            return {}

    def get_duplicate_stats(self) -> dict:
        """Duplicate önleme istatistikleri."""
        with self._conn() as conn:
            total_leads = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            total_sent = conn.execute("SELECT COUNT(DISTINCT email) FROM sent_log").fetchone()[0]
            total_sent_rows = conn.execute("SELECT COUNT(*) FROM sent_log").fetchone()[0]
            duplicate_sends = total_sent_rows - total_sent
            return {
                "total_leads": total_leads,
                "unique_sent": total_sent,
                "total_sent_rows": total_sent_rows,
                "duplicate_sends": duplicate_sends,
                "unsent_leads": total_leads - total_sent,
            }

    def cleanup_duplicate_sent(self) -> int:
        """sent_log'daki duplicate gönderim kayıtlarını temizle. Her email için sadece ilk kaydı tut."""
        with self._conn() as conn:
            # Duplicate kayıtları say
            before = conn.execute("SELECT COUNT(*) FROM sent_log").fetchone()[0]
            # Her email için en eski kaydı tut, gerisini sil
            conn.execute("""
                DELETE FROM sent_log WHERE id NOT IN (
                    SELECT MIN(id) FROM sent_log GROUP BY email
                )
            """)
            after = conn.execute("SELECT COUNT(*) FROM sent_log").fetchone()[0]
            removed = before - after
            if removed > 0:
                log.info(f"[DB] 🧹 {removed} duplicate gönderim kaydı silindi (önceki: {before}, şimdi: {after})")
            return removed

    # ─── CAMPAIGNS ────────────────────────────────────────────────

    def create_campaign(self, campaign_id: str, total_leads: int,
                        test_mode: bool) -> int:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO campaigns (campaign_id, total_leads, test_mode)
                VALUES (?, ?, ?)
            """, (campaign_id, total_leads, 1 if test_mode else 0))
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def update_campaign_stats(self, campaign_id: str, **kwargs):
        """Kampanya istatistiklerini güncelle."""
        valid_fields = {"processed", "sent", "skipped_compliance",
                        "skipped_quality", "failed", "status"}
        updates = {k: v for k, v in kwargs.items() if k in valid_fields}
        if not updates:
            return

        if "status" in updates and updates["status"] == "completed":
            updates["ended_at"] = datetime.now().isoformat()

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [campaign_id]

        with self._conn() as conn:
            conn.execute(
                f"UPDATE campaigns SET {set_clause} WHERE campaign_id = ?",
                values
            )

    def get_campaign(self, campaign_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM campaigns WHERE campaign_id = ?",
                (campaign_id,)
            ).fetchone()
            return dict(row) if row else None

    # ─── EVENTS (Brevo webhook) ───────────────────────────────────

    def record_event(self, email: str, event_type: str,
                     message_id: str = "", metadata: dict = None):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO events (email, message_id, event_type, metadata)
                VALUES (?, ?, ?, ?)
            """, (email, message_id, event_type,
                  json.dumps(metadata or {})))

    # Alias for webhook compatibility
    def log_event(self, email: str, event_type: str, metadata: dict = None):
        """Alias for record_event (webhook uyumluluğu)."""
        self.record_event(email, event_type, metadata=metadata)

    def get_events_by_type(self, event_type: str, limit: int = 100) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM events WHERE event_type = ?
                ORDER BY received_at DESC LIMIT ?
            """, (event_type, limit)).fetchall()
            return [dict(r) for r in rows]

    def get_open_rates_by_variant(self) -> dict:
        """A/B test varyantına göre açılma oranları."""
        with self._conn() as conn:
            variants = {}
            for variant in ["A", "B", "C"]:
                sent = conn.execute(
                    "SELECT COUNT(*) FROM sent_log WHERE ab_variant = ?",
                    (variant,)
                ).fetchone()[0]
                opened = conn.execute("""
                    SELECT COUNT(DISTINCT e.email) FROM events e
                    INNER JOIN sent_log s ON e.email = s.email
                    WHERE s.ab_variant = ? AND e.event_type IN ('open','opened','unique_opened')
                """, (variant,)).fetchone()[0]
                if sent > 0:
                    variants[variant] = {
                        "sent": sent, "opened": opened,
                        "rate": round(opened / sent * 100, 1)
                    }
            return variants

    # ─── FOLLOW-UP (v4) ──────────────────────────────────────────

    def schedule_followup(self, email: str, step: int, scheduled_at: str,
                          original_subject: str = "", company: str = "",
                          sector: str = "", vehicles: str = "",
                          campaign_id: str = ""):
        """Follow-up zamanla."""
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO followups (email, step, scheduled_at, original_subject,
                    company, sector, vehicles, campaign_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (email.strip().lower(), step, scheduled_at,
                  original_subject, company, sector, vehicles, campaign_id))

    def get_pending_followups(self) -> list[dict]:
        """Zamanı gelen bekleyen follow-up'ları getir."""
        now = datetime.now().isoformat()
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM followups
                WHERE status = 'pending' AND scheduled_at <= ?
                ORDER BY scheduled_at ASC
            """, (now,)).fetchall()
            return [dict(r) for r in rows]

    def update_followup_status(self, followup_id: int, status: str,
                               subject: str = "", body_html: str = "",
                               body_text: str = ""):
        with self._conn() as conn:
            if status == "sent":
                conn.execute("""
                    UPDATE followups SET status = ?, sent_at = datetime('now'),
                        subject = ?, body_html = ?, body_text = ?
                    WHERE id = ?
                """, (status, subject, body_html, body_text, followup_id))
            else:
                conn.execute(
                    "UPDATE followups SET status = ? WHERE id = ?",
                    (status, followup_id))

    def cancel_pending_followups(self, email: str):
        """E-posta için tüm bekleyen follow-up'ları iptal et."""
        with self._conn() as conn:
            conn.execute("""
                UPDATE followups SET status = 'cancelled'
                WHERE email = ? AND status = 'pending'
            """, (email.strip().lower(),))

    def postpone_followups(self, email: str, days: int = 3):
        """Follow-up'ları N gün ertele."""
        from datetime import timedelta
        new_date = (datetime.now() + timedelta(days=days)).isoformat()
        with self._conn() as conn:
            conn.execute("""
                UPDATE followups SET scheduled_at = ?
                WHERE email = ? AND status = 'pending'
            """, (new_date, email.strip().lower()))

    def get_followup_stats(self) -> dict:
        """Follow-up istatistikleri (detaylı)."""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM followups").fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM followups WHERE status = 'pending'"
            ).fetchone()[0]
            sent = conn.execute(
                "SELECT COUNT(*) FROM followups WHERE status = 'sent'"
            ).fetchone()[0]
            cancelled = conn.execute(
                "SELECT COUNT(*) FROM followups WHERE status = 'cancelled'"
            ).fetchone()[0]
            skipped = conn.execute(
                "SELECT COUNT(*) FROM followups WHERE status LIKE 'skipped%'"
            ).fetchone()[0]
            error = conn.execute(
                "SELECT COUNT(*) FROM followups WHERE status = 'error'"
            ).fetchone()[0]
            # Per-step breakdown
            steps = {}
            for step in [1, 2, 3]:
                step_total = conn.execute(
                    "SELECT COUNT(*) FROM followups WHERE step = ?",
                    (step,)
                ).fetchone()[0]
                step_sent = conn.execute(
                    "SELECT COUNT(*) FROM followups WHERE step = ? AND status = 'sent'",
                    (step,)
                ).fetchone()[0]
                steps[f"step_{step}"] = {"total": step_total, "sent": step_sent}

            return {
                "total": total, "pending": pending, "sent": sent, "pending_count": pending,
                "cancelled": cancelled, "skipped": skipped, "error": error,
                "steps": steps,
            }

    def get_followup_detail(self, limit: int = 100) -> list[dict]:
        """Kişi bazlı detaylı follow-up listesi."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT f.*, l.company as lead_company, l.sector as lead_sector,
                       l.ai_score, l.source
                FROM followups f
                LEFT JOIN leads l ON f.email = l.email
                ORDER BY f.scheduled_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_all_followups(self, limit: int = 100) -> list[dict]:
        """Tüm follow-up kayıtlarını detaylı döndür."""
        return self.get_followup_detail(limit=limit)

    def get_sent_email_content(self, email: str) -> dict | None:
        """Gönderilmiş e-postanın subject ve tarih bilgisini döndür."""
        with self._conn() as conn:
            row = conn.execute("""
                SELECT email, subject, sent_at, company, sector
                FROM sent_log WHERE email = ? ORDER BY sent_at ASC LIMIT 1
            """, (email.lower().strip(),)).fetchone()
            return dict(row) if row else None

    def get_followups_for_email(self, email: str) -> list[dict]:
        """Belirli bir e-posta için tüm follow-up kayıtlarını döndür."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT id, email, step, status, subject, body_text, body_html,
                       scheduled_at, sent_at
                FROM followups WHERE email = ?
                ORDER BY step ASC
            """, (email.lower().strip(),)).fetchall()
            return [dict(r) for r in rows]

    # ─── RESPONSES (v4) ──────────────────────────────────────────

    def save_response(self, email: str, classification: str,
                      confidence: float = 0.0, sentiment: int = 50,
                      summary: str = "", response_text: str = "",
                      original_subject: str = ""):
        """Yanıt sınıflandırmasını kaydet."""
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO responses (email, classification, confidence,
                    sentiment, summary, response_text, original_subject)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (email.strip().lower(), classification, confidence,
                  sentiment, summary, response_text, original_subject))

    def has_response(self, email: str) -> bool:
        """Bu email'den yanıt gelmiş mi?"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM responses WHERE email = ?",
                (email.strip().lower(),)
            ).fetchone()
            return row is not None

    def has_opened(self, email: str) -> bool:
        """Bu email açılmış mı?"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM events WHERE email = ? AND event_type IN ('open','opened','unique_opened') LIMIT 1",
                (email.strip().lower(),)
            ).fetchone()
            return row is not None

    def add_opt_out(self, email: str, reason: str = "response"):
        """Opt-out işle + event kaydet."""
        self.record_event(email, "unsubscribe", metadata={"source": reason})
        with self._conn() as conn:
            conn.execute("""
                UPDATE leads SET status = 'opted_out', updated_at = datetime('now')
                WHERE email = ?
            """, (email.strip().lower(),))

    def get_response_stats(self) -> dict:
        """Yanıt istatistikleri."""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
            total_responses = total
            classifications = {}
            for cls in ["interested", "not_interested", "question",
                        "out_of_office", "bounce", "unsubscribe"]:
                count = conn.execute(
                    "SELECT COUNT(*) FROM responses WHERE classification = ?",
                    (cls,)
                ).fetchone()[0]
                classifications[cls] = count
            return {"total": total, "total_responses": total_responses,
                    "classifications": classifications}

    def get_hot_leads(self) -> list[dict]:
        """İlgi gösteren 'hot' lead'leri getir."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT l.*, r.summary as response_summary, r.classified_at
                FROM leads l
                JOIN responses r ON l.email = r.email
                WHERE r.classification = 'interested'
                ORDER BY r.classified_at DESC
            """).fetchall()
            return [dict(r) for r in rows]

    def get_events_by_email_and_type(self, email: str, event_type: str) -> list[dict]:
        """Belirli email ve event türü için event'leri getir."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM events WHERE email = ? AND event_type = ?
                ORDER BY received_at DESC
            """, (email.strip().lower(), event_type)).fetchall()
            return [dict(r) for r in rows]

    def auto_detect_hot_leads(self) -> int:
        """2+ kez açan veya link tıklayan lead'leri otomatik hot yap."""
        count = 0
        with self._conn() as conn:
            # 2+ kez açan lead'ler
            rows = conn.execute("""
                SELECT e.email, COUNT(*) as open_count
                FROM events e
                JOIN leads l ON e.email = l.email
                WHERE e.event_type IN ('open','opened','unique_opened')
                  AND l.is_hot = 0
                GROUP BY e.email
                HAVING COUNT(*) >= 2
            """).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE leads SET is_hot = 1, status = 'hot', updated_at = datetime('now') WHERE email = ?",
                    (row["email"],)
                )
                count += 1

            # Link tıklayan lead'ler
            click_rows = conn.execute("""
                SELECT DISTINCT e.email
                FROM events e
                JOIN leads l ON e.email = l.email
                WHERE e.event_type = 'click'
                  AND l.is_hot = 0
            """).fetchall()
            for row in click_rows:
                conn.execute(
                    "UPDATE leads SET is_hot = 1, status = 'hot', updated_at = datetime('now') WHERE email = ?",
                    (row["email"],)
                )
                count += 1

        if count > 0:
            log.info(f"[DB] 🔥 {count} yeni hot lead tespit edildi")
        return count

    # ─── STATS ────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        with self._conn() as conn:
            total_leads = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            total_sent = conn.execute("SELECT COUNT(*) FROM sent_log").fetchone()[0]
            total_drafts = conn.execute(
                "SELECT COUNT(DISTINCT email) FROM drafts"
            ).fetchone()[0]
            bounces = conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type IN ('bounce','hard_bounce','soft_bounce')"
            ).fetchone()[0]
            opens = conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type IN ('open','opened','unique_opened')"
            ).fetchone()[0]
            hot_leads = conn.execute(
                "SELECT COUNT(*) FROM responses WHERE classification = 'interested'"
            ).fetchone()[0]
            total_followups = conn.execute(
                "SELECT COUNT(*) FROM followups WHERE status = 'sent'"
            ).fetchone()[0]
            unsubscribes = conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'unsubscribe'"
            ).fetchone()[0]

            return {
                "total_leads": total_leads,
                "total_sent": total_sent,
                "total_drafts": total_drafts,
                "bounces": bounces,
                "opens": opens,
                "open_rate": round(opens / max(total_sent, 1) * 100, 1),
                "hot_leads": hot_leads,
                "followups_sent": total_followups,
                "unsubscribe_count": unsubscribes,
            }

    # ─── REPORTS ─────────────────────────────────────────────────

    def get_campaign_report(self) -> dict:
        """Kapsamlı kampanya raporu."""
        with self._conn() as conn:
            total_leads = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            total_sent = conn.execute("SELECT COUNT(*) FROM sent_log").fetchone()[0]
            total_opens = conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'open'"
            ).fetchone()[0]
            total_clicks = conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'click'"
            ).fetchone()[0]
            total_bounces = conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'bounce'"
            ).fetchone()[0]
            total_unsubs = conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_type = 'unsubscribe'"
            ).fetchone()[0]

            sectors = conn.execute("""
                SELECT sector, COUNT(*) as cnt FROM leads
                WHERE sector IS NOT NULL AND sector != ''
                GROUP BY sector ORDER BY cnt DESC
            """).fetchall()

            fu_total = conn.execute("SELECT COUNT(*) FROM followups").fetchone()[0]
            fu_sent = conn.execute(
                "SELECT COUNT(*) FROM followups WHERE status = 'sent'"
            ).fetchone()[0]
            fu_pending = conn.execute(
                "SELECT COUNT(*) FROM followups WHERE status = 'pending'"
            ).fetchone()[0]

            responses = conn.execute("""
                SELECT classification, COUNT(*) as cnt FROM responses
                GROUP BY classification ORDER BY cnt DESC
            """).fetchall()

            daily = conn.execute("""
                SELECT DATE(sent_at) as day, COUNT(*) as cnt
                FROM sent_log
                WHERE sent_at >= DATE('now', '-14 days')
                GROUP BY day ORDER BY day
            """).fetchall()

            return {
                "summary": {
                    "total_leads": total_leads,
                    "total_sent": total_sent,
                    "total_opens": total_opens,
                    "total_clicks": total_clicks,
                    "total_bounces": total_bounces,
                    "total_unsubs": total_unsubs,
                    "open_rate": round(total_opens / max(total_sent, 1) * 100, 1),
                    "click_rate": round(total_clicks / max(total_sent, 1) * 100, 1),
                    "bounce_rate": round(total_bounces / max(total_sent, 1) * 100, 1),
                },
                "sectors": [{"sector": r["sector"], "count": r["cnt"]} for r in sectors],
                "followup_funnel": {
                    "total": fu_total, "sent": fu_sent, "pending": fu_pending,
                },
                "responses": [{"type": r["classification"], "count": r["cnt"]} for r in responses],
                "daily_sends": [{"date": r["day"], "count": r["cnt"]} for r in daily],
            }

    def get_export_data(self) -> list[dict]:
        """CSV export için tüm lead verileri."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT l.email, l.company, l.sector, l.location,
                       l.vehicles, l.ai_score, l.ai_score_reason, l.source,
                       l.created_at,
                       CASE WHEN s.id IS NOT NULL THEN 'Evet' ELSE 'Hayir' END as sent,
                       s.sent_at,
                       CASE WHEN e.id IS NOT NULL THEN 'Evet' ELSE 'Hayir' END as opened,
                       CASE WHEN r.id IS NOT NULL THEN r.classification ELSE '' END as response,
                       (SELECT COUNT(*) FROM followups f WHERE f.email = l.email AND f.status = 'sent') as followup_count
                FROM leads l
                LEFT JOIN sent_log s ON l.email = s.email
                LEFT JOIN events e ON l.email = e.email AND e.event_type = 'open'
                LEFT JOIN responses r ON l.email = r.email
                GROUP BY l.email
                ORDER BY l.ai_score DESC
            """).fetchall()
            return [dict(r) for r in rows]

    # ─── AGENT SELF-IMPROVEMENT ────────────────────────────────────

    def save_agent_feedback(self, agent_name: str, learning_type: str,
                            context: str, lesson: str,
                            metric_before: float = 0, metric_after: float = 0):
        """Agent öğrenme kaydı ekle."""
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO agent_learning (agent_name, learning_type, context,
                    lesson, metric_before, metric_after)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (agent_name, learning_type, context, lesson,
                  metric_before, metric_after))

    def get_agent_learnings(self, agent_name: str = None, limit: int = 50) -> list[dict]:
        """Agent öğrenme kayıtlarını getir."""
        with self._conn() as conn:
            if agent_name:
                rows = conn.execute("""
                    SELECT * FROM agent_learning WHERE agent_name = ?
                    ORDER BY created_at DESC LIMIT ?
                """, (agent_name, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM agent_learning ORDER BY created_at DESC LIMIT ?
                """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_agent_performance(self) -> dict:
        """Tüm agentlerin öğrenme metrikleri."""
        with self._conn() as conn:
            agents = conn.execute("""
                SELECT agent_name, COUNT(*) as total_learnings,
                       AVG(metric_after - metric_before) as avg_improvement
                FROM agent_learning
                GROUP BY agent_name
            """).fetchall()
            return {r["agent_name"]: {"learnings": r["total_learnings"],
                    "avg_improvement": round(r["avg_improvement"] or 0, 2)} for r in agents}

    # ─── UNSUBSCRIBE ─────────────────────────────────────────────

    def add_unsubscribe(self, email: str, reason: str = "") -> bool:
        """Email adresini unsubscribe listesine ekle."""
        with self._conn() as conn:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO unsubscribes (email, reason)
                    VALUES (?, ?)
                """, (email.strip().lower(), reason))
                return True
            except Exception:
                return False

    def get_unsubscribe_count(self) -> int:
        """Toplam unsubscribe sayısı."""
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM unsubscribes").fetchone()[0]

    def get_all_unsubscribed(self) -> list[dict]:
        """Tüm unsubscribe listesini döndür."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM unsubscribes ORDER BY unsubscribed_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    # ─── LEADS BY SOURCE ─────────────────────────────────────────

    def get_leads_by_source(self, source: str, limit: int = 100) -> list[dict]:
        """Belirli bir kaynaktan bulunan lead'leri döndür."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM leads WHERE source = ?
                ORDER BY created_at DESC LIMIT ?
            """, (source, limit)).fetchall()
            return [dict(r) for r in rows]


# Singleton instance
db = Database()
