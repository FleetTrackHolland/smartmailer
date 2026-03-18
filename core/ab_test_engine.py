"""
core/ab_test_engine.py — A/B/C Test Engine
İlk N gönderimde konu satırlarını eşit dağıtır,
Brevo event'leri ile open rate takibi yapar,
kazanan konu otomatik seçilir.
"""
import random
from core.logger import get_logger

log = get_logger("ab_test")


class ABTestEngine:
    """
    A/B/C konu satırı test motoru.
    İlk test_size gönderimde varyantları eşit dağıtır.
    Yeterli veri toplandığında kazananı otomatik seçer.
    """

    def __init__(self, test_size: int = 12):
        """
        test_size: A/B/C testi için toplam test gönderim sayısı
                   (her varyanta test_size/3 gönderim)
        """
        self.test_size = test_size
        self._variant_counts = {"A": 0, "B": 0, "C": 0}
        self._winner = None  # Henüz kazanan yok
        self._total_sent = 0

    def select_variant(self, subject_a: str, subject_b: str,
                       subject_c: str) -> tuple[str, str]:
        """
        Hangi konu varyantını kullanacağını seç.
        Returns: (variant_letter, chosen_subject)
        """
        # Kazanan belirlendiyse her zaman onu kullan
        if self._winner:
            subjects = {"A": subject_a, "B": subject_b, "C": subject_c}
            log.debug(f"[A/B] Kazanan varyant: {self._winner}")
            return self._winner, subjects[self._winner]

        self._total_sent += 1

        # Test aşamasında: en az gönderilmiş varyantı seç
        if self._total_sent <= self.test_size:
            min_variant = min(self._variant_counts, key=self._variant_counts.get)
            self._variant_counts[min_variant] += 1

            subjects = {"A": subject_a, "B": subject_b, "C": subject_c}
            chosen = subjects[min_variant]

            log.info(f"[A/B TEST] Varyant {min_variant} seçildi "
                     f"({self._variant_counts}) — {chosen[:50]}")
            return min_variant, chosen

        # Test tamamlandı ama henüz kazanan seçilmedi
        # (open rate verisi bekleniyor, şimdilik rastgele)
        variant = random.choice(["A", "B", "C"])
        subjects = {"A": subject_a, "B": subject_b, "C": subject_c}
        return variant, subjects[variant]

    def determine_winner(self, variant_stats: dict) -> str | None:
        """
        Open rate verilerine göre kazananı belirle.
        variant_stats format: {"A": {"sent": 4, "opened": 2, "open_rate": 50.0}, ...}
        """
        if not variant_stats:
            return None

        # En az 3 gönderim olan varyantları filtrele
        eligible = {k: v for k, v in variant_stats.items()
                    if v.get("sent", 0) >= 3}

        if not eligible:
            log.info("[A/B] Yeterli veri yok, kazanan belirlenemedi")
            return None

        # En yüksek open rate
        winner = max(eligible, key=lambda k: eligible[k].get("open_rate", 0))
        winner_rate = eligible[winner].get("open_rate", 0)

        # İstatistiksel anlamlılık kontrolü (basit: en az %5 fark)
        rates = sorted([v.get("open_rate", 0) for v in eligible.values()], reverse=True)
        if len(rates) >= 2 and (rates[0] - rates[1]) < 5:
            log.info(f"[A/B] Fark çok küçük (%{rates[0]:.1f} vs %{rates[1]:.1f}), "
                     f"daha fazla veri gerekli")
            return None

        self._winner = winner
        log.info(f"[A/B] 🏆 KAZANAN: Varyant {winner} "
                 f"(open rate: %{winner_rate:.1f})")
        return winner

    def get_status(self) -> dict:
        return {
            "test_size": self.test_size,
            "total_sent": self._total_sent,
            "variant_counts": dict(self._variant_counts),
            "winner": self._winner,
            "phase": "testing" if self._total_sent <= self.test_size else
                     ("winner_selected" if self._winner else "awaiting_data"),
        }

    def reset(self):
        """Testi sıfırla."""
        self._variant_counts = {"A": 0, "B": 0, "C": 0}
        self._winner = None
        self._total_sent = 0
        log.info("[A/B] Test sıfırlandı")
