"""
core/template_engine.py — Email Template Engine (Phase 3)
Sektöre göre hazır HTML email şablonları.
Copywriter agent'ın ürettiği içeriği profesyonel şablona yerleştirir.
"""
from core.logger import get_logger

log = get_logger("template_engine")

# ─── TEMPLATE CATALOG ─────────────────────────────────────────

TEMPLATES = {
    "modern_dark": {
        "name": "Modern Dark",
        "description": "Koyu tema, profesyonel görünüm",
        "sectors": ["transport", "bouw", "default"],
        "html": """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<style>
body {{ margin:0; padding:0; background:#1a1a2e; font-family:'Segoe UI',Arial,sans-serif; }}
.container {{ max-width:600px; margin:0 auto; background:#16213e; border-radius:12px; overflow:hidden; }}
.header {{ background:linear-gradient(135deg,#0f3460,#533483); padding:32px 24px; text-align:center; }}
.header h1 {{ color:#e94560; margin:0; font-size:22px; }}
.header p {{ color:#a8a8c8; margin:8px 0 0; font-size:13px; }}
.body {{ padding:28px 24px; color:#d4d4e8; font-size:15px; line-height:1.7; }}
.cta {{ text-align:center; padding:0 24px 28px; }}
.cta a {{ display:inline-block; background:linear-gradient(135deg,#e94560,#533483); color:#fff;
  padding:14px 32px; border-radius:8px; text-decoration:none; font-weight:600; font-size:15px; }}
.footer {{ background:#0f0f23; padding:20px 24px; text-align:center; color:#666; font-size:11px; }}
.footer a {{ color:#e94560; text-decoration:none; }}
</style></head><body>
<div class="container">
  <div class="header">
    <h1>{company_name}</h1>
    <p>FleetTrack Holland — GPS Fleet Tracking</p>
  </div>
  <div class="body">{body_content}</div>
  <div class="cta"><a href="{cta_url}">{cta_text}</a></div>
  <div class="footer">
    FleetTrack Holland B.V. | <a href="{unsubscribe_url}">Uitschrijven</a>
  </div>
</div></body></html>""",
    },
    "clean_white": {
        "name": "Clean White",
        "description": "Beyaz tema, minimalist tasarım",
        "sectors": ["schoonmaak", "default"],
        "html": """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<style>
body {{ margin:0; padding:0; background:#f5f5f5; font-family:'Segoe UI',Arial,sans-serif; }}
.container {{ max-width:600px; margin:0 auto; background:#fff; border-radius:8px;
  box-shadow:0 2px 16px rgba(0,0,0,0.08); overflow:hidden; }}
.header {{ background:#2d3436; padding:28px 24px; }}
.header h1 {{ color:#fff; margin:0; font-size:20px; }}
.header p {{ color:#b2bec3; margin:6px 0 0; font-size:12px; }}
.body {{ padding:28px 24px; color:#2d3436; font-size:15px; line-height:1.7; }}
.cta {{ text-align:center; padding:0 24px 28px; }}
.cta a {{ display:inline-block; background:#0984e3; color:#fff;
  padding:14px 32px; border-radius:6px; text-decoration:none; font-weight:600; }}
.footer {{ border-top:1px solid #eee; padding:16px 24px; text-align:center; color:#999; font-size:11px; }}
.footer a {{ color:#0984e3; text-decoration:none; }}
</style></head><body>
<div class="container">
  <div class="header">
    <h1>{company_name}</h1>
    <p>FleetTrack Holland — GPS Voertuigvolgsysteem</p>
  </div>
  <div class="body">{body_content}</div>
  <div class="cta"><a href="{cta_url}">{cta_text}</a></div>
  <div class="footer">
    FleetTrack Holland B.V. | <a href="{unsubscribe_url}">Uitschrijven</a>
  </div>
</div></body></html>""",
    },
    "gradient_pro": {
        "name": "Gradient Pro",
        "description": "Gradient arka plan, premium his",
        "sectors": ["transport", "bouw", "schoonmaak", "default"],
        "html": """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<style>
body {{ margin:0; padding:20px; background:linear-gradient(135deg,#667eea,#764ba2);
  font-family:'Segoe UI',Arial,sans-serif; }}
.container {{ max-width:600px; margin:0 auto; background:#fff; border-radius:16px;
  box-shadow:0 20px 60px rgba(0,0,0,0.15); overflow:hidden; }}
.header {{ padding:32px 28px 24px; border-bottom:3px solid #667eea; }}
.header h1 {{ color:#2d3436; margin:0; font-size:22px; }}
.header p {{ color:#636e72; margin:6px 0 0; font-size:13px; }}
.body {{ padding:28px; color:#2d3436; font-size:15px; line-height:1.7; }}
.cta {{ text-align:center; padding:0 28px 32px; }}
.cta a {{ display:inline-block; background:linear-gradient(135deg,#667eea,#764ba2); color:#fff;
  padding:14px 36px; border-radius:50px; text-decoration:none; font-weight:600; font-size:15px;
  box-shadow:0 4px 15px rgba(102,126,234,0.4); }}
.footer {{ background:#f8f9fa; padding:16px 28px; text-align:center; color:#999; font-size:11px; }}
.footer a {{ color:#667eea; text-decoration:none; }}
</style></head><body>
<div class="container">
  <div class="header">
    <h1>{company_name}</h1>
    <p>FleetTrack Holland — Slimme Voertuigtracking</p>
  </div>
  <div class="body">{body_content}</div>
  <div class="cta"><a href="{cta_url}">{cta_text}</a></div>
  <div class="footer">
    FleetTrack Holland B.V. | <a href="{unsubscribe_url}">Uitschrijven</a>
  </div>
</div></body></html>""",
    },
}

# Varsayılan CTA
DEFAULT_CTA_URL = "https://fleettrackholland.nl/demo"
DEFAULT_CTA_TEXT = "Gratis Demo Aanvragen"
DEFAULT_UNSUB_URL = "https://fleettrackholland.nl/unsubscribe"


class TemplateEngine:
    """Email şablon motoru."""

    def __init__(self):
        self._active_template = "modern_dark"
        log.info(f"TemplateEngine hazir ({len(TEMPLATES)} sablon).")

    def get_templates(self) -> list[dict]:
        """Mevcut şablonları listele."""
        return [
            {
                "id": tid,
                "name": t["name"],
                "description": t["description"],
                "sectors": t["sectors"],
                "active": tid == self._active_template,
            }
            for tid, t in TEMPLATES.items()
        ]

    def set_active(self, template_id: str) -> bool:
        """Aktif şablonu değiştir."""
        if template_id in TEMPLATES:
            self._active_template = template_id
            log.info(f"[TEMPLATE] Aktif sablon: {template_id}")
            return True
        return False

    def render(self, body_html: str, company_name: str = "",
               cta_url: str = None, cta_text: str = None,
               unsubscribe_url: str = None) -> str:
        """İçeriği aktif şablona yerleştir."""
        template = TEMPLATES.get(self._active_template, TEMPLATES["modern_dark"])
        return template["html"].format(
            body_content=body_html,
            company_name=company_name or "Geachte heer/mevrouw",
            cta_url=cta_url or DEFAULT_CTA_URL,
            cta_text=cta_text or DEFAULT_CTA_TEXT,
            unsubscribe_url=unsubscribe_url or DEFAULT_UNSUB_URL,
        )

    def preview(self, template_id: str, sample_content: str = None) -> str:
        """Şablon önizlemesi oluştur."""
        template = TEMPLATES.get(template_id)
        if not template:
            return "<p>Template bulunamadi</p>"
        content = sample_content or (
            "<p>Beste heer/mevrouw,</p>"
            "<p>Wist u dat bedrijven met GPS fleet tracking gemiddeld "
            "<strong>23% brandstofbesparing</strong> realiseren?</p>"
            "<p>FleetTrack Holland biedt u een complete oplossing voor "
            "voertuigbeheer, routeoptimalisatie en real-time tracking.</p>"
            "<p>Met vriendelijke groet,<br>FleetTrack Holland Team</p>"
        )
        return template["html"].format(
            body_content=content,
            company_name="Uw Bedrijf",
            cta_url=DEFAULT_CTA_URL,
            cta_text=DEFAULT_CTA_TEXT,
            unsubscribe_url=DEFAULT_UNSUB_URL,
        )

    def ping(self) -> bool:
        return True
