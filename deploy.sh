#!/bin/bash
# SmartMailer Auto-Deploy + Cron Pipeline Script
# Bu script hem deploy hem de otomasyon pipeline'ı yönetir.
#
# KURULUM (sunucuda crontab -e ile):
# --- Git deploy (her 5 dakikada) ---
# */5 * * * * /home/fleettrackholland/domains/app.fleettrackholland.nl/public_html/deploy.sh deploy >> /home/fleettrackholland/domains/app.fleettrackholland.nl/public_html/data/cron.log 2>&1
#
# --- Pipeline çalıştır (her 10 dakikada, sadece izin verilen saatlerde) ---
# Pazartesi-Cumartesi 08:00-18:59:
# */10 8-18 * * 1-6 /home/fleettrackholland/domains/app.fleettrackholland.nl/public_html/deploy.sh pipeline >> /home/fleettrackholland/domains/app.fleettrackholland.nl/public_html/data/cron.log 2>&1
# Pazar 12:00-18:59:
# */10 12-18 * * 0 /home/fleettrackholland/domains/app.fleettrackholland.nl/public_html/deploy.sh pipeline >> /home/fleettrackholland/domains/app.fleettrackholland.nl/public_html/data/cron.log 2>&1

APP_DIR="/home/fleettrackholland/domains/app.fleettrackholland.nl/public_html"
LOG_FILE="$APP_DIR/data/cron.log"
SECRET="fleettrack2026"
SITE_URL="https://app.fleettrackholland.nl"

mkdir -p "$APP_DIR/data"

ACTION="${1:-all}"

# ─── DEPLOY: Git pull + restart ───────────────────────────────
do_deploy() {
    cd "$APP_DIR" || exit 1
    echo "[$(date)] [DEPLOY] Checking for updates..."
    OUTPUT=$(git pull origin main 2>&1)
    echo "[$(date)] [DEPLOY] $OUTPUT"

    if echo "$OUTPUT" | grep -q "Already up to date"; then
        echo "[$(date)] [DEPLOY] No changes."
    else
        echo "[$(date)] [DEPLOY] ✅ Updated! Restarting application..."
        mkdir -p "$APP_DIR/tmp"
        touch "$APP_DIR/tmp/restart.txt"
        pkill -f "passenger.*smartmailer" 2>/dev/null || true
        pkill -f "python.*api" 2>/dev/null || true
        echo "[$(date)] [DEPLOY] ✅ Application restarted."
    fi
}

# ─── PIPELINE: Curl ile otomasyon cycle çalıştır ──────────────
do_pipeline() {
    # ★ SAAT KONTROLÜ — Hollanda saati ile gönderim penceresi
    # Pazartesi-Cumartesi: 08:00-19:00, Pazar: 12:00-19:00
    HOUR=$(date +%H)
    DOW=$(date +%u)  # 1=Mon, 7=Sun

    if [ "$DOW" = "7" ]; then
        # Pazar: 12:00-19:00
        if [ "$HOUR" -lt 12 ] || [ "$HOUR" -ge 19 ]; then
            echo "[$(date)] [PIPELINE] ⏰ Pazar gönderim saati dışı (saat $HOUR). İzin: 12:00-19:00 — atlanıyor."
            return 0
        fi
    else
        # Pazartesi-Cumartesi: 08:00-19:00
        if [ "$HOUR" -lt 8 ] || [ "$HOUR" -ge 19 ]; then
            echo "[$(date)] [PIPELINE] ⏰ Gönderim saati dışı (saat $HOUR). İzin: 08:00-19:00 — atlanıyor."
            return 0
        fi
    fi

    echo "[$(date)] [PIPELINE] Starting cron cycle..."
    
    # Timeout 600s (10 dakika) — pipeline uzun sürebilir
    RESPONSE=$(curl -s -m 600 "${SITE_URL}/cron/run-cycle?secret=${SECRET}" 2>&1)
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[$(date)] [PIPELINE] ✅ Cycle tamamlandı: $RESPONSE"
    else
        echo "[$(date)] [PIPELINE] ❌ Hata (exit: $EXIT_CODE): $RESPONSE"
        # Site uyanmamış olabilir — bir kere ping at
        curl -s -m 10 "${SITE_URL}/" > /dev/null 2>&1
        sleep 5
        # Tekrar dene
        RESPONSE=$(curl -s -m 600 "${SITE_URL}/cron/run-cycle?secret=${SECRET}" 2>&1)
        echo "[$(date)] [PIPELINE] Retry sonuç: $RESPONSE"
    fi
}

# ─── ANA MANTIK ───────────────────────────────────────────────
case "$ACTION" in
    deploy)
        do_deploy
        ;;
    pipeline)
        do_pipeline
        ;;
    all)
        do_deploy
        do_pipeline
        ;;
    *)
        echo "Kullanım: $0 {deploy|pipeline|all}"
        exit 1
        ;;
esac
