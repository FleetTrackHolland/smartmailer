#!/bin/bash
# SmartMailer Auto-Deploy Script
# Bu script cron job ile çalışır ve GitHub'dan otomatik güncelleme çeker.
# Kullanım: crontab -e → */5 * * * * /path/to/deploy.sh

APP_DIR="/home/fleettrackholland/domains/app.fleettrackholland.nl/public_html"
LOG_FILE="$APP_DIR/data/deploy.log"

cd "$APP_DIR" || exit 1

# Git pull
echo "[$(date)] Checking for updates..." >> "$LOG_FILE"
OUTPUT=$(git pull origin main 2>&1)
echo "[$(date)] $OUTPUT" >> "$LOG_FILE"

# Eğer değişiklik varsa — uygulama restart
if echo "$OUTPUT" | grep -q "Already up to date"; then
    echo "[$(date)] No changes." >> "$LOG_FILE"
else
    echo "[$(date)] ✅ Updated! Restarting application..." >> "$LOG_FILE"
    # Passenger restart (DirectAdmin/cPanel hosting)
    mkdir -p "$APP_DIR/tmp"
    touch "$APP_DIR/tmp/restart.txt"
    # Alternatif: WSGI process kill
    pkill -f "passenger.*smartmailer" 2>/dev/null || true
    pkill -f "python.*api" 2>/dev/null || true
    echo "[$(date)] ✅ Application restarted." >> "$LOG_FILE"
fi

