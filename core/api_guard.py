"""
core/api_guard.py — Self-Healing API Guard (Rate Limit + Circuit Breaker)
Tüm Claude API çağrılarını merkezi olarak korur.
- Otomatik retry + exponential backoff (429 hatalarında)
- Token-bucket rate limiter (dakika başı istek sınırı)
- Circuit breaker (art arda hata → geçici durdurma)
- Retry-After header desteği
- Thread-safe (otomasyon pipeline ile uyumlu)

Kullanım:
    from core.api_guard import api_guard
    response = api_guard.call(payload, headers)
"""
import time
import threading
import requests
from core.logger import get_logger

log = get_logger("api_guard")

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"


class APIGuard:
    """Self-healing, rate-limit-aware API caller for Claude."""

    def __init__(
        self,
        max_requests_per_minute: int = 4,
        max_retries: int = 4,
        base_backoff_seconds: float = 12.0,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_cooldown: int = 120,
    ):
        # Rate limiter — token bucket (thread-safe)
        self._lock = threading.Lock()
        self._max_rpm = max_requests_per_minute
        self._request_timestamps: list[float] = []

        # Retry settings
        self._max_retries = max_retries
        self._base_backoff = base_backoff_seconds

        # Circuit breaker
        self._consecutive_failures = 0
        self._cb_threshold = circuit_breaker_threshold
        self._cb_cooldown = circuit_breaker_cooldown
        self._circuit_open_until: float = 0

        # Stats
        self._total_calls = 0
        self._total_retries = 0
        self._total_429s = 0
        self._total_successes = 0

        log.info(
            f"[API Guard] Hazır — {max_requests_per_minute} req/dk, "
            f"max {max_retries} retry, circuit breaker: {circuit_breaker_threshold} hata"
        )

    # ─── RATE LIMITER ────────────────────────────────────────────

    def _wait_for_rate_limit(self):
        """Token-bucket: dakika başı max N istek. Gerekirse bekler."""
        with self._lock:
            now = time.time()
            one_minute_ago = now - 60

            # Eski timestamp'leri temizle
            self._request_timestamps = [
                ts for ts in self._request_timestamps if ts > one_minute_ago
            ]

            if len(self._request_timestamps) >= self._max_rpm:
                # En eski isteğin 1 dakika dolmasını bekle
                oldest = self._request_timestamps[0]
                wait = (oldest + 60) - now + 0.5  # +0.5s güvenlik payı
                if wait > 0:
                    log.info(f"[API Guard] Rate limit — {wait:.1f}sn bekleniyor ({len(self._request_timestamps)}/{self._max_rpm} req/dk)")
                    time.sleep(wait)

            self._request_timestamps.append(time.time())

    # ─── CIRCUIT BREAKER ─────────────────────────────────────────

    def _check_circuit_breaker(self) -> bool:
        """Circuit breaker açık mı kontrol et."""
        if self._circuit_open_until > 0:
            if time.time() < self._circuit_open_until:
                remaining = int(self._circuit_open_until - time.time())
                log.warning(f"[API Guard] Circuit breaker AÇIK — {remaining}sn kaldı")
                return False
            else:
                # Cooldown bitti, circuit'i kapat
                log.info("[API Guard] Circuit breaker kapandı — tekrar deneniyor")
                self._circuit_open_until = 0
                self._consecutive_failures = 0
        return True

    def _record_success(self):
        self._consecutive_failures = 0
        self._total_successes += 1

    def _record_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._cb_threshold:
            self._circuit_open_until = time.time() + self._cb_cooldown
            log.error(
                f"[API Guard] ⚠️ Circuit breaker AÇILDI — {self._consecutive_failures} art arda hata! "
                f"{self._cb_cooldown}sn bekleniyor..."
            )

    # ─── ANA API ÇAĞRISI ─────────────────────────────────────────

    def call(
        self,
        payload: dict,
        headers: dict,
        timeout: int = 60,
    ) -> requests.Response | None:
        """
        Claude API'yi çağır — rate limit + retry + circuit breaker korumalı.
        Başarılı → Response döner.
        Başarısız → None döner (exception fırlatmaz, pipeline çökmez).
        """
        self._total_calls += 1

        # Circuit breaker kontrolü
        if not self._check_circuit_breaker():
            return None

        # Rate limiter — gerekirse bekle
        self._wait_for_rate_limit()

        # Retry loop with exponential backoff
        for attempt in range(self._max_retries + 1):
            try:
                resp = requests.post(
                    CLAUDE_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                )

                if resp.status_code == 429:
                    self._total_429s += 1
                    # Retry-After header kontrolü
                    wait_time = self._base_backoff * (2 ** attempt)
                    retry_after = resp.headers.get("retry-after")
                    if retry_after:
                        try:
                            wait_time = max(wait_time, float(retry_after))
                        except (ValueError, TypeError):
                            pass

                    # Max wait cap: 120 saniye
                    wait_time = min(wait_time, 120)

                    if attempt < self._max_retries:
                        self._total_retries += 1
                        log.warning(
                            f"[API Guard] 429 Rate limit — {wait_time:.0f}sn bekleniyor "
                            f"(deneme {attempt + 1}/{self._max_retries + 1})"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        log.error("[API Guard] 429 — tüm denemeler başarısız")
                        self._record_failure()
                        return None

                if resp.status_code == 529:
                    # Anthropic overloaded
                    wait_time = 30 * (attempt + 1)
                    if attempt < self._max_retries:
                        self._total_retries += 1
                        log.warning(f"[API Guard] 529 Overloaded — {wait_time}sn bekleniyor")
                        time.sleep(wait_time)
                        continue
                    else:
                        self._record_failure()
                        return None

                if resp.ok:
                    self._record_success()
                    return resp

                # Diğer hatalar (400, 401, 500, vb.) — retry yok
                log.warning(f"[API Guard] API hata: {resp.status_code}")
                self._record_failure()
                return resp

            except requests.exceptions.Timeout:
                log.warning(f"[API Guard] Timeout (deneme {attempt + 1})")
                if attempt < self._max_retries:
                    self._total_retries += 1
                    time.sleep(5 * (attempt + 1))
                    continue
                self._record_failure()
                return None

            except requests.exceptions.ConnectionError as e:
                log.warning(f"[API Guard] Bağlantı hatası: {e}")
                if attempt < self._max_retries:
                    self._total_retries += 1
                    time.sleep(10 * (attempt + 1))
                    continue
                self._record_failure()
                return None

            except Exception as e:
                log.error(f"[API Guard] Beklenmeyen hata: {e}")
                self._record_failure()
                return None

        return None

    # ─── İSTATİSTİKLER ───────────────────────────────────────────

    def get_stats(self) -> dict:
        return {
            "total_calls": self._total_calls,
            "total_successes": self._total_successes,
            "total_retries": self._total_retries,
            "total_429s": self._total_429s,
            "consecutive_failures": self._consecutive_failures,
            "circuit_breaker_open": self._circuit_open_until > time.time(),
        }


# ─── GLOBAL SINGLETON ────────────────────────────────────────
api_guard = APIGuard()
