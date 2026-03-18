"""
main.py — SmartMailer Ultimate Entry Point
SmartMailer Pro + FleetTrack CRM birleşik girişi.
CLI ile lead keşfi, kampanya, veya web dashboard başlatma.
"""
import sys
import os
import argparse

# Proje kökünü PATH'e ekle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config
from core.logger import get_logger

log = get_logger("main")


def main():
    parser = argparse.ArgumentParser(
        description="SmartMailer Ultimate — Lead Discovery & Email Automation",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--web", action="store_true",
                        help="Web dashboard başlat (varsayılan)")
    parser.add_argument("--discover", action="store_true",
                        help="Lead keşfi yap (CLI)")
    parser.add_argument("--campaign", action="store_true",
                        help="Email kampanyası başlat (CLI)")
    parser.add_argument("--test", action="store_true",
                        help="Test modunda çalış")
    parser.add_argument("--sector", type=str, default="transport",
                        help="Hedef sektör (keşif için)")
    parser.add_argument("--location", type=str, default="Nederland",
                        help="Hedef konum")
    parser.add_argument("--limit", type=int, default=0,
                        help="Gönderim limiti")
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("PORT", 5000)),
                        help="Web dashboard portu (Railway: $PORT env var)")

    args = parser.parse_args()

    if args.test:
        config.TEST_MODE = True

    print("=" * 60)
    print("  SmartMailer Ultimate v1.0")
    print("  SmartMailer Pro + FleetTrack CRM Birleşimi")
    print("=" * 60)

    # Config validation
    errors = config.validate()
    if errors and not config.TEST_MODE:
        for e in errors:
            print(f"  ❌ {e}")
        print("\n  .env dosyasını kontrol edin.")
        sys.exit(1)

    mode_str = "TEST MODU" if config.TEST_MODE else "GERÇEK GÖNDERİM"
    print(f"  Mod: {mode_str}")
    print(f"  Sektörler: {', '.join(config.SECTORS[:5])}...")
    print(f"  Konum: {config.TARGET_LOCATION}")
    print(f"  Anthropic: {'✅' if config.ANTHROPIC_API_KEY else '❌'}")
    print(f"  Brevo: {'✅' if config.BREVO_API_KEY else '❌'}")
    print("=" * 60)

    if args.discover:
        run_discovery(args.sector, args.location)
    elif args.campaign:
        run_campaign(args.limit)
    else:
        run_web(args.port)


def run_discovery(sector: str, location: str):
    """CLI lead keşfi."""
    from agents.lead_finder import LeadFinder
    finder = LeadFinder()

    print(f"\n🔍 Lead keşfi başlıyor: {sector} / {location}")
    results = finder.discover_leads(sector, location)
    stats = finder.get_discovery_stats()

    print(f"\n📊 Sonuçlar:")
    print(f"   Bulunan: {stats.get('leads_found', 0)}")
    print(f"   Kaydedilen: {stats.get('leads_saved', 0)}")
    print(f"   Dizin tarama: {stats.get('directories_scraped', 0)}")
    print(f"   Telefoonboek: {stats.get('telefoonboek_found', 0)}")
    print(f"   OpenStreetMap: {stats.get('openstreetmap_found', 0)}")
    print(f"   MX doğrulamalı: {stats.get('mx_verified', 0)}")
    print(f"   AI çağrısı: {stats.get('ai_calls', 0)}")
    print(f"   Hatalar: {stats.get('errors', 0)}")

    if results:
        print(f"\n📋 İlk 10 lead:")
        for i, lead in enumerate(results[:10], 1):
            print(f"   {i}. {lead.get('company_name', '?')} — {lead.get('email', '?')} "
                  f"({lead.get('source', '?')}) [{lead.get('score', 0)}p]")


def run_campaign(limit: int = 0):
    """CLI kampanya başlatma."""
    from agents.orchestrator import Orchestrator
    orch = Orchestrator()

    max_send = limit or config.DAILY_SEND_LIMIT
    print(f"\n📬 Kampanya başlıyor (limit: {max_send})")
    stats = orch.run_campaign(max_send=max_send)

    print(f"\n📊 Kampanya Sonuçları:")
    print(f"   Toplam lead: {stats.total_leads}")
    print(f"   İşlenen: {stats.processed}")
    print(f"   Gönderilen: {stats.sent}")
    print(f"   Compliance atladı: {stats.skipped_compliance}")
    print(f"   QC başarısız: {stats.skipped_quality}")
    print(f"   Hata: {stats.failed}")


def run_web(port: int = 5000):
    """Web dashboard başlat."""
    is_production = os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RENDER")
    debug_mode = not is_production

    print(f"\n🌐 Web Dashboard başlatılıyor...")
    print(f"   http://localhost:{port}")
    print(f"   Mod: {'PRODUCTION' if is_production else 'DEVELOPMENT'}")
    print(f"   Durdurmak için Ctrl+C\n")

    # web/api.py'yi import et ve çalıştır
    from web.api import app, socketio, HAS_SOCKETIO, _auto_start_automation
    import threading

    # Otomasyon thread'ini başlat
    auto_thread = threading.Thread(target=_auto_start_automation, daemon=True)
    auto_thread.start()

    if HAS_SOCKETIO and socketio:
        socketio.run(app, host="0.0.0.0", port=port, debug=debug_mode,
                     allow_unsafe_werkzeug=True)
    else:
        app.run(host="0.0.0.0", port=port, debug=debug_mode)


if __name__ == "__main__":
    main()
