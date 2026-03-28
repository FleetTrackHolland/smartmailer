"""
core/api_guard.py — Self-Healing API Guard (Gemini + Claude)
Tüm AI API çağrılarını merkezi olarak korur.
- Otomatik Gemini ↔ Claude payload dönüşümü
- Rate limiter + exponential backoff + circuit breaker
- Thread-safe

Kullanım — agent'lar hiç değişmeden çalışır:
    from core.api_guard import api_guard
    response = api_guard.call(payload, headers)
"""
import time
import json
import threading
import requests
from core.logger import get_logger

log = get_logger("api_guard")

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class APIGuard:
    """Self-healing, rate-limit-aware API caller — Gemini & Claude."""

    def __init__(
        self,
        max_requests_per_minute: int = 14,
        max_retries: int = 3,
        base_backoff_seconds: float = 5.0,
        circuit_breaker_threshold: int = 8,
        circuit_breaker_cooldown: int = 90,
    ):
        self._lock = threading.Lock()
        self._max_rpm = max_requests_per_minute
        self._request_timestamps: list[float] = []

        self._max_retries = max_retries
        self._base_backoff = base_backoff_seconds

        self._consecutive_failures = 0
        self._cb_threshold = circuit_breaker_threshold
        self._cb_cooldown = circuit_breaker_cooldown
        self._circuit_open_until: float = 0

        self._total_calls = 0
        self._total_retries = 0
        self._total_429s = 0
        self._total_successes = 0

        # Provider detection
        from config import config as cfg
        self._provider = cfg.AI_PROVIDER  # "gemini" or "claude"
        self._gemini_key = cfg.GEMINI_API_KEY
        self._gemini_model = cfg.GEMINI_MODEL

        provider_name = "Gemini 2.0 Flash" if self._provider == "gemini" else "Claude"
        log.info(
            f"[API Guard] {provider_name} — {max_requests_per_minute} req/dk, "
            f"max {max_retries} retry"
        )

    # ─── RATE LIMITER ────────────────────────────────────────────

    def _wait_for_rate_limit(self):
        with self._lock:
            now = time.time()
            one_minute_ago = now - 60
            self._request_timestamps = [
                ts for ts in self._request_timestamps if ts > one_minute_ago
            ]
            if len(self._request_timestamps) >= self._max_rpm:
                oldest = self._request_timestamps[0]
                wait = (oldest + 60) - now + 0.5
                if wait > 0:
                    log.info(f"[API Guard] Rate limit — {wait:.1f}sn bekleniyor")
                    time.sleep(wait)
            self._request_timestamps.append(time.time())

    # ─── CIRCUIT BREAKER ─────────────────────────────────────────

    def _check_circuit_breaker(self) -> bool:
        if self._circuit_open_until > 0:
            if time.time() < self._circuit_open_until:
                remaining = int(self._circuit_open_until - time.time())
                log.warning(f"[API Guard] Circuit breaker AÇIK — {remaining}sn kaldı")
                return False
            else:
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
                f"[API Guard] ⚠️ Circuit breaker AÇILDI — {self._consecutive_failures} art arda hata!"
            )

    # ─── CLAUDE → GEMINI PAYLOAD DÖNÜŞÜMÜ ────────────────────────

    def _claude_to_gemini(self, payload: dict) -> tuple[str, dict]:
        """
        Claude formatındaki payload'ı Gemini formatına çevirir.
        Returns: (url, gemini_payload)
        """
        messages = payload.get("messages", [])
        max_tokens = payload.get("max_tokens", 4096)

        # Claude messages → Gemini contents
        contents = []
        for msg in messages:
            role = "user" if msg.get("role") == "user" else "model"
            text = msg.get("content", "")
            # Handle content that's a list (Claude format)
            if isinstance(text, list):
                text = " ".join(
                    part.get("text", "") for part in text if isinstance(part, dict)
                )
            contents.append({
                "role": role,
                "parts": [{"text": str(text)}]
            })

        gemini_payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.7,
            }
        }

        # System instruction (from Claude system field)
        system = payload.get("system")
        if system:
            gemini_payload["systemInstruction"] = {
                "parts": [{"text": system}]
            }

        model = self._gemini_model
        url = GEMINI_API_URL.format(model=model) + f"?key={self._gemini_key}"
        return url, gemini_payload

    def _gemini_to_claude_response(self, gemini_resp: requests.Response) -> requests.Response:
        """
        Gemini'nin response'ını Claude response formatına çevirir.
        Agent'lar fark etmeden çalışmaya devam eder.
        """
        try:
            data = gemini_resp.json()
            # Extract text from Gemini response
            text = ""
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                text = " ".join(p.get("text", "") for p in parts)

            # Build Claude-compatible response
            claude_format = {
                "content": [{"type": "text", "text": text}],
                "model": self._gemini_model,
                "role": "assistant",
                "stop_reason": "end_turn",
                "usage": data.get("usageMetadata", {})
            }

            # Create a fake Response object that looks like Claude's
            fake_resp = requests.models.Response()
            fake_resp.status_code = 200
            fake_resp._content = json.dumps(claude_format).encode("utf-8")
            fake_resp.headers["content-type"] = "application/json"
            fake_resp.encoding = "utf-8"
            return fake_resp

        except Exception as e:
            log.error(f"[API Guard] Gemini response parse hatası: {e}")
            return gemini_resp

    # ─── ANA API ÇAĞRISI ─────────────────────────────────────────

    def call(
        self,
        payload: dict,
        headers: dict,
        timeout: int = 60,
    ) -> requests.Response | None:
        """
        AI API'yi çağır — provider'a göre otomatik yönlendir.
        Agent'lar Claude formatında payload gönderir,
        api_guard otomatik olarak Gemini'ye çevirir.
        """
        self._total_calls += 1

        if not self._check_circuit_breaker():
            return None

        self._wait_for_rate_limit()

        # Provider'a göre URL ve payload belirle
        if self._provider == "gemini":
            url, actual_payload = self._claude_to_gemini(payload)
            actual_headers = {"Content-Type": "application/json"}
            is_gemini = True
        else:
            url = CLAUDE_API_URL
            actual_payload = payload
            actual_headers = headers
            is_gemini = False

        for attempt in range(self._max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    json=actual_payload,
                    headers=actual_headers,
                    timeout=timeout,
                )

                if resp.status_code == 429:
                    self._total_429s += 1
                    wait_time = self._base_backoff * (2 ** attempt)
                    retry_after = resp.headers.get("retry-after")
                    if retry_after:
                        try:
                            wait_time = max(wait_time, float(retry_after))
                        except (ValueError, TypeError):
                            pass
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

                if resp.status_code in (529, 503):
                    wait_time = 15 * (attempt + 1)
                    if attempt < self._max_retries:
                        self._total_retries += 1
                        log.warning(f"[API Guard] {resp.status_code} — {wait_time}sn bekleniyor")
                        time.sleep(wait_time)
                        continue
                    else:
                        self._record_failure()
                        return None

                if resp.ok:
                    self._record_success()
                    # Gemini response'ı Claude formatına çevir
                    if is_gemini:
                        return self._gemini_to_claude_response(resp)
                    return resp

                log.warning(f"[API Guard] API hata: {resp.status_code} — {resp.text[:200]}")
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
            "provider": self._provider,
            "model": self._gemini_model if self._provider == "gemini" else "claude",
            "total_calls": self._total_calls,
            "total_successes": self._total_successes,
            "total_retries": self._total_retries,
            "total_429s": self._total_429s,
            "consecutive_failures": self._consecutive_failures,
            "circuit_breaker_open": self._circuit_open_until > time.time(),
        }


# ─── GLOBAL SINGLETON ────────────────────────────────────────
api_guard = APIGuard()
