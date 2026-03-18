"""
agents/quality_agent.py — AI-Powered Email QC Agent (v3)
Claude AI ile akıllı kalite kontrolü + regex fallback.
Bağlamsal spam tespiti, profesyonellik tonu, CTA etkinliği değerlendirir.
"""
import re
import json
import requests
from dataclasses import dataclass, field
from config import config
from core.logger import get_logger

log = get_logger("quality")

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"

# ─── Regex fallback için spam listesi ─────────────────────────
SPAM_WORDS = [
    "100%", "actie nu", "bestel nu", "goedkoopste",
    "aanbieding", "direct voordeel",
    "free", "guarantee", "click here", "buy now", "limited time",
    "congratulations", "winner", "cash prize", "urgent", "act now",
    "!!!", "$$$", "€€€",
]

CTA_PATTERNS = [
    r"mag ik", r"kunt u", r"wilt u", r"bent u beschikbaar",
    r"bellen", r"afspraak", r"offerte", r"demo",
    r"vrijblijvend", r"contact", r"aanvragen",
]


@dataclass
class QCResult:
    passed: bool
    score: int          # 0-100
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    method: str = "regex"  # "ai" veya "regex"
    feedback: str = ""     # AI'dan yapıcı geri bildirim


AI_QC_PROMPT = """Je bent een senior e-mail marketing QC specialist. Beoordeel de volgende zakelijke cold e-mail op 10 criteria.

Geef per criterium een score van 0-10 en een kort commentaar.

CRITERIA:
1. spam_risk: Kans dat spam filters triggeren (10 = geen risico, 0 = direct in spam)
   - LET OP: woorden als "gratis montage", "gratis uitproberen" zijn ACCEPTABEL in B2B context
   - Onacceptabel: "GRATIS!!!", "KLIK HIER", "$$$", overmatig hoofdletters
2. professionalism: Toon en stijl passend voor een B2B cold e-mail
3. personalization: Mate van personalisatie (bedrijfsnaam, sector, specifieke pijnpunten)
4. cta_effectiveness: Duidelijkheid en aantrekkelijkheid van de call-to-action
5. subject_quality: Kracht van het onderwerp (open-rate potentieel)
6. value_proposition: Duidelijkheid van het aanbod en de voordelen
7. length_appropriate: Niet te lang, niet te kort (ideaal: 100-180 woorden)
8. compliance: AVG/GDPR (afmeldlink aanwezig, geen ongewenste beloftes)
9. grammar_dutch: Nederlandse taalcorrectheid
10. visual_design: HTML opmaak kwaliteit (als HTML aanwezig)

ANTWOORD EXACT IN DIT JSON FORMAT:
{
    "scores": {
        "spam_risk": {"score": 8, "comment": "..."},
        "professionalism": {"score": 9, "comment": "..."},
        "personalization": {"score": 7, "comment": "..."},
        "cta_effectiveness": {"score": 8, "comment": "..."},
        "subject_quality": {"score": 7, "comment": "..."},
        "value_proposition": {"score": 8, "comment": "..."},
        "length_appropriate": {"score": 9, "comment": "..."},
        "compliance": {"score": 10, "comment": "..."},
        "grammar_dutch": {"score": 9, "comment": "..."},
        "visual_design": {"score": 8, "comment": "..."}
    },
    "total_score": 83,
    "passed": true,
    "issues": ["lijst van serieuze problemen"],
    "improvements": ["concrete verbetersugesties"],
    "summary": "Korte samenvatting van de beoordeling"
}"""


class QualityAgent:

    MAX_WORDS = 220
    MIN_WORDS = 40

    def __init__(self):
        self._headers = {
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    # ─── AI-POWERED CHECK (PRIMARY) ───────────────────────────────

    def check(self, subject: str, body_text: str,
              company_name: str, body_html: str = "") -> QCResult:
        """
        Ana kalite kontrolü. Önce AI dener, başarısız olursa regex'e düşer.
        """
        try:
            return self._ai_check(subject, body_text, company_name, body_html)
        except Exception as e:
            log.warning(f"[QC] AI kontrol başarısız ({e}), regex'e düşüyor...")
            return self._regex_check(subject, body_text, company_name)

    def _ai_check(self, subject: str, body_text: str,
                  company_name: str, body_html: str = "") -> QCResult:
        """Claude AI ile akıllı kalite kontrolü."""

        user_prompt = f"""Beoordeel deze zakelijke cold e-mail:

ONDERWERP: {subject}

BEDRIJF: {company_name}

E-MAIL TEKST:
{body_text}

{"HTML VERSIE:" + chr(10) + body_html[:2000] if body_html else ""}
"""

        payload = {
            "model": config.CLAUDE_MODEL,
            "max_tokens": 800,
            "system": AI_QC_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        resp = requests.post(CLAUDE_API_URL, json=payload,
                             headers=self._headers, timeout=30)
        if not resp.ok:
            raise Exception(f"Claude QC API hatası: {resp.status_code}")

        raw = resp.json()["content"][0]["text"]

        # JSON parse (Claude bazen markdown wrapping yapar)
        json_str = raw
        if "```json" in raw:
            json_str = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            json_str = raw.split("```")[1].split("```")[0]

        data = json.loads(json_str.strip())

        total_score = data.get("total_score", 0)
        passed = total_score >= config.QC_MIN_SCORE
        issues = data.get("issues", [])
        improvements = data.get("improvements", [])
        summary = data.get("summary", "")

        # Log sonuçları
        scores_detail = data.get("scores", {})
        low_scores = {k: v for k, v in scores_detail.items()
                      if isinstance(v, dict) and v.get("score", 10) < 6}

        if passed:
            log.info(f"[QC AI] ✅ Geçti — Skor: {total_score}/100 | {company_name}")
        else:
            log.warning(f"[QC AI] ❌ Başarısız — Skor: {total_score}/100 | "
                        f"Düşük: {list(low_scores.keys())} | {company_name}")

        return QCResult(
            passed=passed,
            score=total_score,
            issues=issues,
            warnings=improvements,
            method="ai",
            feedback=summary,
        )

    # ─── REGEX FALLBACK ───────────────────────────────────────────

    def _regex_check(self, subject: str, body_text: str,
                     company_name: str) -> QCResult:
        """Regex tabanlı yedek kontrol (AI ulaşılamadığında)."""
        issues = []
        warnings = []
        score = 100

        body_lower = body_text.lower()
        subj_lower = subject.lower()

        # 1. Uzunluk
        word_count = len(body_text.split())
        if word_count > self.MAX_WORDS:
            issues.append(f"Çok uzun: {word_count} kelime (max {self.MAX_WORDS})")
            score -= 20
        if word_count < self.MIN_WORDS:
            issues.append(f"Çok kısa: {word_count} kelime (min {self.MIN_WORDS})")
            score -= 15

        # 2. Spam kelimeleri
        found_spam = [w for w in SPAM_WORDS
                      if w.lower() in body_lower or w.lower() in subj_lower]
        if found_spam:
            issues.append(f"Spam kelimeleri: {found_spam}")
            score -= 25

        # 3. Konu ALL CAPS?
        caps_ratio = sum(1 for c in subject if c.isupper()) / max(len(subject), 1)
        if caps_ratio > 0.5:
            issues.append("Konu satırı çok büyük harf içeriyor")
            score -= 15

        # 4. Uzun konu
        if len(subject) > 70:
            warnings.append(f"Konu {len(subject)} karakter — bazı istemcilerde kısalabilir")
            score -= 5

        # 5. Şirket ismi
        company_words = company_name.lower().split()
        if not any(w in body_lower for w in company_words if len(w) > 3):
            warnings.append("Şirket ismi email gövdesinde geçmiyor")
            score -= 10

        # 6. CTA
        has_cta = any(re.search(p, body_lower) for p in CTA_PATTERNS)
        if not has_cta:
            issues.append("Net bir CTA bulunamadı")
            score -= 20

        # 7. Afmelden
        if "afmelden" not in body_lower and "unsubscribe" not in body_lower:
            issues.append("Afmelden linki eksik — AVG zorunlu!")
            score -= 30

        # 8. Link sayısı
        link_count = body_lower.count("http")
        if link_count > 3:
            warnings.append(f"{link_count} link — spam filtresi tetiklenebilir")
            score -= 5

        passed = len(issues) == 0 and score >= config.QC_MIN_SCORE

        if passed:
            log.info(f"[QC regex] ✅ Geçti — Skor: {score}/100 | {company_name}")
        else:
            log.warning(f"[QC regex] ❌ Başarısız — Skor: {score}/100 | "
                        f"Sorunlar: {issues} | {company_name}")

        return QCResult(passed=passed, score=score,
                        issues=issues, warnings=warnings, method="regex")

    def ping(self) -> bool:
        return True
