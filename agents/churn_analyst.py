"""
agents/churn_analyst.py — Churn Analiz Ajanı (v1)
Unsubscribe paternlerini analiz eder, ortak noktaları çıkarır,
ve copywriter'a feed edecek insight'lar üretir.

Analiz boyutları:
- Sektör bazlı churn rate
- Email frekansı korelasyonu
- Anket yanıtı paternleri
- Zamanlama analizi (hangi follow-up adımında çıkıyorlar?)
- Gönderim zamanı korelasyonu
"""
import json
from datetime import datetime
from collections import defaultdict
from config import config
from core.logger import get_logger
from core.database import db

log = get_logger("churn_analyst")


class ChurnAnalyst:
    """Unsubscribe verilerini analiz eden ve copywriter'a öneriler sunan agent."""

    def __init__(self):
        self._last_report = None
        self._insights_cache = []
        log.info("ChurnAnalyst v1 hazır (patern analizi + copywriter feed).")

    # ─── ANA ANALİZ ───────────────────────────────────────────────

    def generate_churn_report(self) -> dict:
        """Kapsamlı churn analiz raporu üret."""
        survey_stats = db.get_survey_stats()
        opt_out_data = self._get_opt_out_analysis()
        sector_analysis = self._analyze_sectors()
        timing_analysis = self._analyze_timing()
        frequency_analysis = self._analyze_frequency()

        insights = self._extract_insights(
            survey_stats, opt_out_data, sector_analysis,
            timing_analysis, frequency_analysis
        )
        recommendations = self._generate_recommendations(insights)

        report = {
            "generated_at": datetime.now().isoformat(),
            "survey_stats": survey_stats,
            "opt_out_data": opt_out_data,
            "sector_analysis": sector_analysis,
            "timing_analysis": timing_analysis,
            "frequency_analysis": frequency_analysis,
            "insights": insights,
            "recommendations": recommendations,
        }

        # Raporu kaydet
        try:
            db.save_churn_report(report, insights, recommendations)
        except Exception as e:
            log.warning(f"Churn raporu kaydedilemedi: {e}")

        self._last_report = report
        self._insights_cache = insights

        log.info(
            f"[CHURN] Rapor üretildi — "
            f"{survey_stats.get('total_surveys', 0)} anket, "
            f"{len(insights)} insight, "
            f"{len(recommendations)} öneri."
        )
        return report

    # ─── OPT-OUT ANALİZİ ──────────────────────────────────────────

    def _get_opt_out_analysis(self) -> dict:
        """Opt-out verilerini analiz et."""
        try:
            with db._conn() as conn:
                # Toplam opt-out
                total = conn.execute("SELECT COUNT(*) FROM opt_out").fetchone()[0]
                total_unsub = conn.execute("SELECT COUNT(*) FROM unsubscribes").fetchone()[0]

                # Brevo webhook kaynaklı
                brevo_count = conn.execute(
                    "SELECT COUNT(*) FROM opt_out WHERE reason LIKE 'brevo_%'"
                ).fetchone()[0]

                # Email link kaynaklı
                link_count = conn.execute(
                    "SELECT COUNT(*) FROM opt_out WHERE reason = 'email_link'"
                ).fetchone()[0]

                # Son 7 gün trend
                recent = conn.execute(
                    "SELECT COUNT(*) FROM opt_out WHERE created_at >= datetime('now', '-7 days')"
                ).fetchone()[0]

                # Son 30 gün trend
                monthly = conn.execute(
                    "SELECT COUNT(*) FROM opt_out WHERE created_at >= datetime('now', '-30 days')"
                ).fetchone()[0]

                # Toplam gönderilen mail
                total_sent = conn.execute("SELECT COUNT(*) FROM sent_log").fetchone()[0]
                churn_rate = round((total / max(1, total_sent)) * 100, 2) if total_sent else 0

                return {
                    "total_opt_outs": total,
                    "total_unsubscribes": total_unsub,
                    "from_brevo_webhook": brevo_count,
                    "from_email_link": link_count,
                    "last_7_days": recent,
                    "last_30_days": monthly,
                    "total_sent": total_sent,
                    "churn_rate_pct": churn_rate,
                }
        except Exception as e:
            log.error(f"Opt-out analizi hatası: {e}")
            return {"total_opt_outs": 0, "churn_rate_pct": 0}

    # ─── SEKTÖR ANALİZİ ───────────────────────────────────────────

    def _analyze_sectors(self) -> dict:
        """Sektör bazlı churn oranı analizi."""
        try:
            with db._conn() as conn:
                # Her sektörden kaç mail gönderildi
                sent_by_sector = conn.execute("""
                    SELECT sector, COUNT(*) as cnt
                    FROM sent_log WHERE sector != ''
                    GROUP BY sector
                """).fetchall()
                sent_map = {r["sector"]: r["cnt"] for r in sent_by_sector}

                # Her sektörden kaç kişi çıktı
                # opt_out tablosundaki email'leri leads tablosuyla eşleştir
                unsub_by_sector = conn.execute("""
                    SELECT l.sector, COUNT(DISTINCT o.email) as cnt
                    FROM opt_out o
                    LEFT JOIN leads l ON LOWER(o.email) = LOWER(l.email)
                    WHERE l.sector IS NOT NULL AND l.sector != ''
                    GROUP BY l.sector
                """).fetchall()
                unsub_map = {r["sector"]: r["cnt"] for r in unsub_by_sector}

                # Sektör bazlı churn rate hesapla
                sector_rates = {}
                for sector, sent in sent_map.items():
                    unsubs = unsub_map.get(sector, 0)
                    rate = round((unsubs / max(1, sent)) * 100, 2)
                    sector_rates[sector] = {
                        "sent": sent,
                        "unsubscribed": unsubs,
                        "churn_rate_pct": rate,
                    }

                # En yüksek churn rate'e göre sırala
                high_churn = sorted(
                    sector_rates.items(),
                    key=lambda x: x[1]["churn_rate_pct"],
                    reverse=True
                )

                return {
                    "by_sector": sector_rates,
                    "highest_churn": high_churn[:5] if high_churn else [],
                    "lowest_churn": high_churn[-5:] if high_churn else [],
                }
        except Exception as e:
            log.error(f"Sektör analizi hatası: {e}")
            return {"by_sector": {}, "highest_churn": [], "lowest_churn": []}

    # ─── ZAMANLAMA ANALİZİ ─────────────────────────────────────────

    def _analyze_timing(self) -> dict:
        """Unsubscribe'ların zamanlamasını analiz et."""
        try:
            with db._conn() as conn:
                # Hangi saatte çıkıyorlar?
                hour_rows = conn.execute("""
                    SELECT CAST(strftime('%H', created_at) AS INTEGER) as hour,
                           COUNT(*) as cnt
                    FROM opt_out
                    GROUP BY hour ORDER BY cnt DESC
                """).fetchall()
                peak_hours = {r["hour"]: r["cnt"] for r in hour_rows}

                # Hangi gün çıkıyorlar?
                day_rows = conn.execute("""
                    SELECT CAST(strftime('%w', created_at) AS INTEGER) as weekday,
                           COUNT(*) as cnt
                    FROM opt_out
                    GROUP BY weekday
                """).fetchall()
                day_names = ["Pazar", "Pazartesi", "Salı", "Çarşamba",
                             "Perşembe", "Cuma", "Cumartesi"]
                peak_days = {day_names[r["weekday"]]: r["cnt"] for r in day_rows}

                # Follow-up adımlarındaki çıkış
                fu_unsubs = conn.execute("""
                    SELECT f.step, COUNT(DISTINCT o.email) as cnt
                    FROM opt_out o
                    INNER JOIN followups f ON LOWER(o.email) = LOWER(f.email)
                    WHERE f.status = 'sent'
                    GROUP BY f.step
                """).fetchall()
                after_followup = {f"step_{r['step']}": r["cnt"] for r in fu_unsubs}

                return {
                    "peak_hours": peak_hours,
                    "peak_days": peak_days,
                    "after_followup_step": after_followup,
                }
        except Exception as e:
            log.error(f"Zamanlama analizi hatası: {e}")
            return {"peak_hours": {}, "peak_days": {}, "after_followup_step": {}}

    # ─── FREKANS ANALİZİ ──────────────────────────────────────────

    def _analyze_frequency(self) -> dict:
        """Email frekansı ile churn korelasyonu."""
        try:
            with db._conn() as conn:
                # Çıkan kişiler ortalama kaç email almıştı?
                avg_row = conn.execute("""
                    SELECT AVG(email_count) as avg_emails
                    FROM (
                        SELECT o.email, COUNT(s.id) as email_count
                        FROM opt_out o
                        LEFT JOIN sent_log s ON LOWER(o.email) = LOWER(s.email)
                        GROUP BY o.email
                    )
                """).fetchone()
                avg_emails_churners = round(avg_row["avg_emails"] or 0, 1)

                # Kalanlar ortalama kaç email almıştı?
                avg_row2 = conn.execute("""
                    SELECT AVG(email_count) as avg_emails
                    FROM (
                        SELECT l.email, COUNT(s.id) as email_count
                        FROM leads l
                        INNER JOIN sent_log s ON LOWER(l.email) = LOWER(s.email)
                        LEFT JOIN opt_out o ON LOWER(l.email) = LOWER(o.email)
                        WHERE o.email IS NULL
                        GROUP BY l.email
                    )
                """).fetchone()
                avg_emails_retained = round(avg_row2["avg_emails"] or 0, 1)

                return {
                    "avg_emails_before_churn": avg_emails_churners,
                    "avg_emails_retained": avg_emails_retained,
                    "frequency_matters": avg_emails_churners > avg_emails_retained,
                }
        except Exception as e:
            log.error(f"Frekans analizi hatası: {e}")
            return {
                "avg_emails_before_churn": 0,
                "avg_emails_retained": 0,
                "frequency_matters": False,
            }

    # ─── INSIGHT ÇIKARIMI ──────────────────────────────────────────

    def _extract_insights(self, surveys, opt_out, sectors,
                          timing, frequency) -> list[str]:
        """Tüm analizlerden actionable insight'lar çıkar."""
        insights = []

        # 1. Churn rate kontrolü
        churn_rate = opt_out.get("churn_rate_pct", 0)
        if churn_rate > 5:
            insights.append(
                f"⚠️ YÜKSEK CHURN: Genel unsubscribe oranı %{churn_rate} "
                f"— sektör ortalaması %2-3. Acil aksiyon gerekli."
            )
        elif churn_rate > 2:
            insights.append(
                f"📊 CHURN NORMAL: Unsubscribe oranı %{churn_rate} — sektör ortalaması civarı."
            )
        else:
            insights.append(
                f"✅ DÜŞÜK CHURN: Unsubscribe oranı %{churn_rate} — çok iyi performans."
            )

        # 2. Anket sonuçları
        reasons = surveys.get("reasons", {})
        if reasons:
            top_reason = max(reasons, key=reasons.get)
            REASON_LABELS = {
                "too_many": "Çok fazla email",
                "not_relevant": "İçerik alakasız",
                "already_have": "Zaten GPS çözümü var",
                "bad_timing": "Kötü zamanlama",
                "not_requested": "Talep etmedim",
                "other": "Diğer",
            }
            label = REASON_LABELS.get(top_reason, top_reason)
            insights.append(
                f"📝 EN SIK NEDEN: '{label}' — "
                f"{reasons[top_reason]} kişi bu seçeneği seçti."
            )

        # 3. Sektör bazlı risk
        high_churn = sectors.get("highest_churn", [])
        if high_churn and len(high_churn) > 0:
            worst_sector, data = high_churn[0]
            if data["churn_rate_pct"] > 5:
                insights.append(
                    f"🏭 RİSKLİ SEKTÖR: '{worst_sector}' sektörü %{data['churn_rate_pct']} "
                    f"churn rate ile en yüksek kayıp oranına sahip. "
                    f"({data['unsubscribed']}/{data['sent']} çıkış)"
                )

        # 4. Follow-up adımı korelasyonu
        fu_steps = timing.get("after_followup_step", {})
        if fu_steps:
            worst_step = max(fu_steps, key=fu_steps.get)
            insights.append(
                f"🔄 FOLLOw-UP RİSKİ: En çok çıkış {worst_step} sonrası "
                f"({fu_steps[worst_step]} kişi). Bu adımın tonu gözden geçirilmeli."
            )

        # 5. Frekans insight
        if frequency.get("frequency_matters"):
            insights.append(
                f"📨 FREKANS UYARISI: Çıkanlar ortalama "
                f"{frequency['avg_emails_before_churn']} email almış, "
                f"kalanlar {frequency['avg_emails_retained']}. "
                f"Çok email gönderimi churn'ü artırıyor olabilir."
            )

        # 6. Trend
        recent = opt_out.get("last_7_days", 0)
        monthly = opt_out.get("last_30_days", 0)
        if monthly > 0:
            weekly_avg = monthly / 4
            if recent > weekly_avg * 1.5:
                insights.append(
                    f"📈 ARTAN TREND: Son 7 günde {recent} çıkış — "
                    f"aylık ortalamanın ({weekly_avg:.0f}/hafta) üzerinde!"
                )

        return insights

    # ─── ÖNERİ ÜRETME ─────────────────────────────────────────────

    def _generate_recommendations(self, insights: list[str]) -> list[str]:
        """Insight'lara göre copywriter + strateji önerileri üret."""
        recommendations = []

        for insight in insights:
            if "ÇOK FAZLA EMAIL" in insight.upper() or "FREKANS" in insight.upper():
                recommendations.append(
                    "COPYWRITER: Email gönderim sıklığını azalt. "
                    "Follow-up aralıklarını 3-7-14 günden 5-10-20 güne çıkar. "
                    "İlk email'de daha fazla değer sun ki follow-up'a gerek kalmasın."
                )
            if "ALAKASIZ" in insight.upper() or "NOT_RELEVANT" in insight.upper():
                recommendations.append(
                    "COPYWRITER: Sektöre özel kişiselleştirmeyi artır. "
                    "Generic GPS tracking mesajları yerine sektör-spesifik pain point'lere odaklan. "
                    "Örn: nakliye → 'yakıt tasarrufu', kurye → 'teslimat optimizasyonu'."
                )
            if "ZATEN GPS" in insight.upper() or "ALREADY_HAVE" in insight.upper():
                recommendations.append(
                    "COPYWRITER: 'Mevcut çözümünüzden farkımız' mesajı ekle. "
                    "Rakip karşılaştırma yerine 'X özelliğimiz sektörde benzersiz' yaklaşımı. "
                    "Zaten çözümü olanları lead scoring'de düşük puanla."
                )
            if "RİSKLİ SEKTÖR" in insight.upper():
                recommendations.append(
                    "STRATEJI: Yüksek churn'lü sektörlere gönderim azalt veya durdur. "
                    "Bu sektördeki email tonunu tamamen değiştir — daha yumuşak, eğitici içerik. "
                    "Lead scoring'de bu sektörü düşük ağırlıkla puan."
                )
            if "FOLLOW-UP RİSKİ" in insight.upper():
                recommendations.append(
                    "COPYWRITER: Sorunlu follow-up adımının tonunu değiştir. "
                    "Muhtemelen çok agresif veya tekrarlayıcı. "
                    "Yeni yaklaşım dene: case study, sektör raporu veya ücretsiz araç."
                )

        if not recommendations:
            recommendations.append(
                "✅ Churn oranı sağlıklı seviyelerde. Mevcut stratejiyi sürdür."
            )

        return recommendations

    # ─── COPYWRITER FEED ───────────────────────────────────────────

    def get_insights_for_copywriter(self) -> list[str]:
        """Copywriter'ın email yazarken kullanacağı insight'lar."""
        if not self._insights_cache:
            # Cache boşsa rapor üret
            report = self.generate_churn_report()
            return report.get("recommendations", [])
        return self._insights_cache

    def get_copywriter_context(self, sector: str = "") -> str:
        """Copywriter prompt'una enjekte edilecek churn bilgisi."""
        report = self._last_report or self.generate_churn_report()

        context_parts = [
            "\n=== CHURN ANALYSIS INSIGHTS ===",
            "De Churn Analyst Agent heeft de volgende inzichten gevonden:",
        ]

        # Genel churn rate
        churn_rate = report.get("opt_out_data", {}).get("churn_rate_pct", 0)
        context_parts.append(f"- Algemeen uitschrijfpercentage: {churn_rate}%")

        # Sektöre özel bilgi
        if sector:
            sector_data = report.get("sector_analysis", {}).get("by_sector", {})
            sec_info = sector_data.get(sector, {})
            if sec_info:
                context_parts.append(
                    f"- Sector '{sector}': {sec_info.get('churn_rate_pct', 0)}% "
                    f"uitschrijfpercentage ({sec_info.get('unsubscribed', 0)} van {sec_info.get('sent', 0)})"
                )

        # Anket sonuçları
        survey_stats = report.get("survey_stats", {})
        top_reasons = survey_stats.get("reasons", {})
        if top_reasons:
            reasons_str = ", ".join(
                f"'{k}': {v}" for k, v in list(top_reasons.items())[:3]
            )
            context_parts.append(f"- Belangrijkste redenen voor uitschrijving: {reasons_str}")

        # Öneriler
        recs = report.get("recommendations", [])
        for rec in recs[:3]:
            if "COPYWRITER" in rec.upper():
                context_parts.append(f"- ACTIE: {rec}")

        context_parts.append("=== EINDE CHURN INZICHTEN ===\n")
        return "\n".join(context_parts)

    # ─── EXCLUSION RULES ───────────────────────────────────────────

    def suggest_exclusion_rules(self) -> list[dict]:
        """Gönderilmemesi gereken lead profilleri."""
        report = self._last_report or self.generate_churn_report()
        rules = []

        # Yüksek churn sektörleri
        high_churn = report.get("sector_analysis", {}).get("highest_churn", [])
        for sector, data in high_churn:
            if data["churn_rate_pct"] > 10 and data["sent"] >= 10:
                rules.append({
                    "type": "sector_exclude",
                    "sector": sector,
                    "reason": f"Churn rate %{data['churn_rate_pct']} — sektör çok riskli",
                    "action": "reduce_frequency",  # exclude / reduce_frequency / change_tone
                })

        return rules

    def ping(self) -> bool:
        return True
