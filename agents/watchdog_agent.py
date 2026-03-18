"""
agents/watchdog_agent.py — Sistem Kontrol & Gözetleme Ajani (Faz 1)
Tüm ajanların ve gönderim motorunun sağlığını izler.
Hata tespit eder, otomatik kurtarma girişiminde bulunur,
çözümsüz durumlarda console + log ile alarm üretir.
"""
import time
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional
from core.logger import get_logger

log = get_logger("watchdog")


@dataclass
class HealthStatus:
    name: str
    status: str       # "OK" | "WARNING" | "CRITICAL"
    detail: str = ""
    checked_at: datetime = field(default_factory=datetime.now)

    def is_ok(self)       -> bool: return self.status == "OK"
    def is_warning(self)  -> bool: return self.status == "WARNING"
    def is_critical(self) -> bool: return self.status == "CRITICAL"


class WatchdogAgent:
    """
    Faz 1 Watchdog — hafif sistem izleme.
    Gerçek zamanlı bir thread olarak arka planda çalışır.
    """

    CHECK_INTERVAL_SEC = 60   # Her 60 saniyede tam kontrol

    def __init__(self, agents: dict, config):
        self._agents  = agents       # {"copywriter": obj, "compliance": obj, ...}
        self._config  = config
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # İstatistikler
        self._check_count    = 0
        self._recovery_count = 0
        self._critical_count = 0
        self._start_time     = datetime.now()

        # Kampanya metrikleri (orchestrator tarafından güncellenir)
        self.sent_count    = 0
        self.failed_count  = 0
        self.bounce_count  = 0
        self.last_send_at: Optional[datetime] = None

        log.info("Watchdog ajani oluşturuldu.")

    # ─────────────────────────────────────────────────────────────
    # THREAD KONTROLÜ
    # ─────────────────────────────────────────────────────────────

    def start(self):
        """Watchdog'u arka plan thread olarak başlatır."""
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="WatchdogThread"
        )
        self._thread.start()
        log.info("Watchdog thread başlatıldı.")

    def stop(self):
        self._running = False
        log.info("Watchdog durduruldu.")

    def _loop(self):
        while self._running:
            try:
                self.run_checks()
            except Exception as e:
                log.error(f"Watchdog iç hatası: {e}")
            time.sleep(self.CHECK_INTERVAL_SEC)

    # ─────────────────────────────────────────────────────────────
    # ANA KONTROL METODU (manuel çağrı için de kullanılabilir)
    # ─────────────────────────────────────────────────────────────

    def run_checks(self) -> list[HealthStatus]:
        self._check_count += 1
        results = []

        # 1. Ajan ping kontrolü
        for name, agent in self._agents.items():
            results.append(self._check_agent(name, agent))

        # 2. Bounce rate kontrolü
        results.append(self._check_bounce_rate())

        # 3. Gönderim durgunluğu
        results.append(self._check_send_activity())

        # 4. API anahtar varlığı
        results.append(self._check_api_keys())

        # Özet log
        statuses = [r.status for r in results]
        if "CRITICAL" in statuses:
            self._critical_count += 1
            log.error(f"[WATCHDOG] 🔴 KRİTİK SORUN TESPT EDİLDİ | "
                      f"Kontrol #{self._check_count}")
        elif "WARNING" in statuses:
            log.warning(f"[WATCHDOG] ⚠️  Uyarılar var | Kontrol #{self._check_count}")
        else:
            log.debug(f"[WATCHDOG] ✅ Sistem sağlıklı | Kontrol #{self._check_count}")

        return results

    # ─────────────────────────────────────────────────────────────
    # TEKİL KONTROLLER
    # ─────────────────────────────────────────────────────────────

    def _check_agent(self, name: str, agent) -> HealthStatus:
        try:
            alive = agent.ping()
            if alive:
                return HealthStatus(name, "OK", "ping başarılı")
            else:
                log.warning(f"[WATCHDOG] {name} ping başarısız!")
                return HealthStatus(name, "WARNING", "ping yanıtsız")
        except Exception as e:
            log.error(f"[WATCHDOG] {name} hata: {e}")
            return HealthStatus(name, "CRITICAL", str(e))

    def _check_bounce_rate(self) -> HealthStatus:
        if self.sent_count == 0:
            return HealthStatus("bounce_rate", "OK", "Henüz gönderim yok")

        rate = self.bounce_count / self.sent_count
        if rate > 0.05:
            msg = (f"Bounce rate YÜKSEK: %{rate*100:.1f} "
                   f"({self.bounce_count}/{self.sent_count}) — KAMPANİYA DURDURULUYOR!")
            log.error(f"[WATCHDOG] 🔴 {msg}")
            # Orchestrator'a sinyal gönder (flag set)
            self._bounce_critical = True
            return HealthStatus("bounce_rate", "CRITICAL", msg)
        elif rate > 0.02:
            msg = f"Bounce rate yüksek: %{rate*100:.1f} — dikkat"
            log.warning(f"[WATCHDOG] ⚠️  {msg}")
            return HealthStatus("bounce_rate", "WARNING", msg)

        return HealthStatus("bounce_rate", "OK",
                            f"%{rate*100:.1f} ({self.bounce_count}/{self.sent_count})")

    def _check_send_activity(self) -> HealthStatus:
        """Son 2 saatte hiç gönderim yoksa ve lead bekliyorsa uyar."""
        if self.last_send_at is None:
            return HealthStatus("send_activity", "OK", "Kampanya henüz başlamadı")

        elapsed = datetime.now() - self.last_send_at
        if elapsed > timedelta(hours=2):
            msg = (f"Son gönderimden bu yana {elapsed.seconds//3600}s "
                   f"{(elapsed.seconds%3600)//60}dk geçti — sistem durmuş olabilir")
            log.warning(f"[WATCHDOG] ⚠️  {msg}")
            return HealthStatus("send_activity", "WARNING", msg)

        return HealthStatus("send_activity", "OK",
                            f"Son gönderim: {elapsed.seconds//60} dk önce")

    def _check_api_keys(self) -> HealthStatus:
        key = self._config.ANTHROPIC_API_KEY or ""
        if not key or len(key) < 10:
            return HealthStatus("api_keys", "CRITICAL",
                                "ANTHROPIC_API_KEY eksik — mail üretilemez!")
        if not self._config.TEST_MODE:
            if not self._config.BREVO_API_KEY and not self._config.BREVO_SMTP_PASS:
                return HealthStatus("api_keys", "CRITICAL",
                                    "Brevo kimlik bilgisi eksik — gönderim yapılamaz!")
        return HealthStatus("api_keys", "OK", "API anahtarları mevcut")

    # ─────────────────────────────────────────────────────────────
    # METRIK GÜNCELLEME (orchestrator tarafından çağrılır)
    # ─────────────────────────────────────────────────────────────

    def record_send(self, success: bool, bounced: bool = False):
        if success:
            self.sent_count += 1
            self.last_send_at = datetime.now()
        else:
            self.failed_count += 1
        if bounced:
            self.bounce_count += 1

    @property
    def should_stop_campaign(self) -> bool:
        return getattr(self, "_bounce_critical", False)

    # ─────────────────────────────────────────────────────────────
    # ÖZET RAPOR
    # ─────────────────────────────────────────────────────────────

    def get_summary(self) -> dict:
        uptime = datetime.now() - self._start_time
        return {
            "uptime_minutes": uptime.seconds // 60,
            "checks_run": self._check_count,
            "auto_recoveries": self._recovery_count,
            "critical_incidents": self._critical_count,
            "sent": self.sent_count,
            "failed": self.failed_count,
            "bounce": self.bounce_count,
        }

    def ping(self) -> bool:
        return True
