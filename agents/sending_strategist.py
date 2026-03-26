"""
agents/sending_strategist.py — Akıllı Gönderim Strateji Ajanı (v1)
Brevo Standard Plan (20.000 email/ay) bütçesini optimize eder.

Özellikler:
- Aylık bütçe takibi ve günlük dağılım
- Hafta içi/sonu ağırlıklandırma (B2B = iş günleri)
- Saat optimizasyonu (09-11, 14-16 CET)
- Sektör bazlı batching (spam önlemi)
- Günlük/aylık raporlama
"""
import calendar
from collections import defaultdict
from datetime import datetime, timedelta
from config import config
from core.logger import get_logger
from core.database import db

log = get_logger("sending_strategist")


class SendingStrategist:
    """Brevo 20K/ay bütçesini akıllıca dağıtan gönderim planlayıcı."""

    def __init__(self):
        self._sector_daily_counts: dict[str, int] = defaultdict(int)
        self._last_reset_day = datetime.now().date()
        log.info("SendingStrategist v1 hazır (20K/ay optimizasyon).")

    # ─── AYLIK BÜTÇE TAKİBİ ──────────────────────────────────────

    def get_monthly_budget(self) -> dict:
        """Bu ayki gönderim bütçesi durumu."""
        now = datetime.now()
        month_start = now.replace(day=1).strftime("%Y-%m-%d")
        month_end = now.replace(
            day=calendar.monthrange(now.year, now.month)[1]
        ).strftime("%Y-%m-%d")

        # Bu ay gönderilen toplam
        try:
            with db._conn() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM sent_log WHERE date(sent_at) >= ? AND date(sent_at) <= ?",
                    (month_start, month_end)
                ).fetchone()
                monthly_sent = row[0] if row else 0
        except Exception:
            monthly_sent = 0

        remaining = max(0, config.MONTHLY_SEND_LIMIT - monthly_sent)
        days_left = max(1, (now.replace(
            day=calendar.monthrange(now.year, now.month)[1]
        ) - now).days + 1)

        return {
            "monthly_limit": config.MONTHLY_SEND_LIMIT,
            "monthly_sent": monthly_sent,
            "remaining": remaining,
            "days_left": days_left,
            "usage_pct": round((monthly_sent / config.MONTHLY_SEND_LIMIT) * 100, 1),
            "month": now.strftime("%Y-%m"),
        }

    # ─── GÜNLÜK PLAN HESAPLA ─────────────────────────────────────

    def get_daily_plan(self) -> dict:
        """Bugün kaç email gönderilmeli — tüm faktörleri hesaplar."""
        self._reset_sector_counters()
        now = datetime.now()
        budget = self.get_monthly_budget()

        # Temel günlük limit: kalan / kalan gün
        base_daily = budget["remaining"] // budget["days_left"]

        # Hafta sonu azaltma
        is_weekend = now.weekday() >= 5  # Cumartesi=5, Pazar=6
        if is_weekend:
            daily_limit = int(base_daily * config.WEEKEND_CAPACITY)
            reason = "weekend"
        else:
            # Hafta içi: hafta sonunun payını da al
            # Kalan hafta sonlarını hesapla
            days_left = budget["days_left"]
            weekends_left = sum(
                1 for d in range(days_left)
                if (now + timedelta(days=d)).weekday() >= 5
            )
            weekdays_left = max(1, days_left - weekends_left)
            # Hafta sonu kapasitesini çıkar, kalanı hafta içlerine dağıt
            weekend_total = int(weekends_left * base_daily * config.WEEKEND_CAPACITY)
            weekday_share = (budget["remaining"] - weekend_total) // weekdays_left
            daily_limit = weekday_share
            reason = "weekday"

        # Config daily limit ile min al
        daily_limit = min(daily_limit, config.DAILY_SEND_LIMIT)
        # En az 10 (güvenlik)
        daily_limit = max(10, daily_limit)

        # Bugün zaten gönderilenleri çıkar
        today_sent = db.get_today_sent_count()
        remaining_today = max(0, daily_limit - today_sent)

        # Optimal saat mi?
        current_hour = now.hour
        in_optimal_hours = any(
            start <= current_hour < end
            for start, end in config.BEST_SEND_HOURS
        )

        return {
            "daily_limit": daily_limit,
            "today_sent": today_sent,
            "remaining_today": remaining_today,
            "is_weekend": is_weekend,
            "reason": reason,
            "in_optimal_hours": in_optimal_hours,
            "current_hour": current_hour,
            "best_hours": config.BEST_SEND_HOURS,
            "monthly_remaining": budget["remaining"],
            "monthly_usage_pct": budget["usage_pct"],
        }

    # ─── SEKTÖR BAZLI THROTTLE ───────────────────────────────────

    def _reset_sector_counters(self):
        """Gün değiştiyse sektör sayaçlarını sıfırla."""
        today = datetime.now().date()
        if today != self._last_reset_day:
            self._sector_daily_counts.clear()
            self._last_reset_day = today

    def can_send_to_sector(self, sector: str) -> tuple[bool, str]:
        """Bu sektöre bugün daha mail gönderilebilir mi?"""
        self._reset_sector_counters()
        sector_key = (sector or "unknown").lower().strip()
        count = self._sector_daily_counts.get(sector_key, 0)

        if count >= config.MAX_PER_SECTOR_DAILY:
            return False, (
                f"Sektör günlük limiti doldu: {sector_key} "
                f"({count}/{config.MAX_PER_SECTOR_DAILY})"
            )
        return True, ""

    def record_sector_send(self, sector: str):
        """Sektöre gönderim kaydı."""
        sector_key = (sector or "unknown").lower().strip()
        self._sector_daily_counts[sector_key] += 1

    def get_sector_stats(self) -> dict:
        """Bugünkü sektör bazlı gönderim istatistikleri."""
        self._reset_sector_counters()
        return dict(self._sector_daily_counts)

    # ─── GÖNDERİM ÖNERİSİ ────────────────────────────────────────

    def should_send_now(self) -> tuple[bool, str]:
        """Şu anda gönderim yapılması uygun mu?"""
        plan = self.get_daily_plan()

        # Aylık limit kontrolü
        if plan["monthly_remaining"] <= 0:
            return False, f"Aylık limit doldu ({config.MONTHLY_SEND_LIMIT:,}/ay)"

        # Günlük kalan kontrolü
        if plan["remaining_today"] <= 0:
            return False, f"Günlük limit doldu ({plan['daily_limit']}/gün)"

        # Optimal saat kontrolü — zorunlu değil, uyarı
        if not plan["in_optimal_hours"]:
            log.info(
                f"[STRATEJI] Optimal saat dışı (saat {plan['current_hour']}). "
                f"Önerilen: {plan['best_hours']}. Yine de gönderim yapılabilir."
            )

        return True, ""

    # ─── LEAD ÖNCELİKLENDİRME ─────────────────────────────────────

    def prioritize_leads(self, leads: list[dict], daily_limit: int) -> list[dict]:
        """Lead'leri akıllıca önceliklendirerek günlük limiti doldur.

        Öncelik sırası:
        1. Hot leads (yanıt veren)
        2. Yüksek AI skoru (>80)
        3. Büyük filolar (vehicles > 20)
        4. Sektör çeşitliliği (aynı sektörden çok fazla olmasın)
        """
        if not leads:
            return []

        # Sektör bazlı gruplama
        sector_groups: dict[str, list[dict]] = defaultdict(list)
        hot_leads = []
        high_score = []
        normal = []

        for lead in leads:
            sector = (lead.get("sector") or "unknown").lower()
            ai_score = lead.get("ai_score", 0)
            is_hot = lead.get("is_hot", 0)
            vehicles = lead.get("vehicles", 0) or 0

            if is_hot:
                hot_leads.append(lead)
            elif ai_score >= 80 or vehicles >= 20:
                high_score.append(lead)
            else:
                normal.append(lead)

            sector_groups[sector].append(lead)

        # Sıralama: hot → yüksek skor → normal
        hot_leads.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
        high_score.sort(key=lambda x: x.get("ai_score", 0), reverse=True)
        normal.sort(key=lambda x: x.get("ai_score", 0), reverse=True)

        prioritized = []
        sector_counts: dict[str, int] = defaultdict(int)

        for lead in hot_leads + high_score + normal:
            if len(prioritized) >= daily_limit:
                break

            sector = (lead.get("sector") or "unknown").lower()

            # Sektör limiti kontrolü
            if sector_counts[sector] >= config.MAX_PER_SECTOR_DAILY:
                continue

            prioritized.append(lead)
            sector_counts[sector] += 1

        log.info(
            f"[STRATEJI] {len(leads)} lead'den {len(prioritized)} seçildi. "
            f"Hot: {len(hot_leads)}, Yüksek skor: {len(high_score)}, "
            f"Normal: {len(normal)}. Sektörler: {dict(sector_counts)}"
        )

        return prioritized

    # ─── RAPOR ─────────────────────────────────────────────────────

    def get_strategy_report(self) -> dict:
        """Kapsamlı strateji raporu."""
        budget = self.get_monthly_budget()
        plan = self.get_daily_plan()
        sectors = self.get_sector_stats()

        return {
            "budget": budget,
            "daily_plan": plan,
            "sector_stats": sectors,
            "recommendations": self._generate_recommendations(budget, plan),
        }

    def _generate_recommendations(self, budget: dict, plan: dict) -> list[str]:
        """Strateji önerileri üret."""
        recs = []

        usage_pct = budget["usage_pct"]
        days_left = budget["days_left"]

        if usage_pct > 80:
            recs.append(
                f"⚠️ Aylık bütçenin %{usage_pct}'i kullanıldı. "
                f"Kalan {days_left} gün için tasarruf modu önerilir."
            )
        elif usage_pct < 30 and days_left < 15:
            recs.append(
                f"📈 Bütçe kullanımı düşük (%{usage_pct}). "
                f"Kalan {budget['remaining']} mail, {days_left} günde gönderilebilir. "
                f"Günlük limiti artırmayı düşünün."
            )

        if plan["is_weekend"]:
            recs.append("🌙 Hafta sonu — sadece yüksek öncelikli lead'ler gönderiliyor.")

        if not plan["in_optimal_hours"]:
            recs.append(
                f"⏰ Şu an optimal gönderim saati değil (saat {plan['current_hour']}). "
                f"En iyi: {plan['best_hours']}"
            )

        return recs

    def ping(self) -> bool:
        return True
