#!/bin/bash
# deploy.sh - Safe deployment script for weather-bot
# Usage:
#   ./scripts/deploy.sh          # pull + validate + restart
#   ./scripts/deploy.sh reclone  # backup + re-clone + restore + restart
set -e

REPO_DIR="/home/ubuntu/Antigravity_Market_Dashboard"
BACKUP_DIR="/tmp/dashboard_backup"

# ── untracked 파일 백업 목록 ──
BACKUP_FILES=(
    ".env"
    "subscribers.json"
    ".budget_milestone"
    "stock_price_history.json"
    "execution/research_bot/research_notes.db"
)
BACKUP_DIRS=(
    "execution/research_bot/media"
)

backup() {
    echo "📦 Backing up untracked files..."
    rm -rf "$BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    for f in "${BACKUP_FILES[@]}"; do
        if [ -f "$REPO_DIR/$f" ]; then
            mkdir -p "$BACKUP_DIR/$(dirname "$f")"
            cp "$REPO_DIR/$f" "$BACKUP_DIR/$f"
            echo "  ✓ $f"
        fi
    done
    for d in "${BACKUP_DIRS[@]}"; do
        if [ -d "$REPO_DIR/$d" ]; then
            mkdir -p "$BACKUP_DIR/$d"
            cp -r "$REPO_DIR/$d/"* "$BACKUP_DIR/$d/" 2>/dev/null || true
            echo "  ✓ $d/"
        fi
    done
}

restore() {
    echo "📦 Restoring untracked files..."
    for f in "${BACKUP_FILES[@]}"; do
        if [ -f "$BACKUP_DIR/$f" ]; then
            mkdir -p "$(dirname "$REPO_DIR/$f")"
            cp "$BACKUP_DIR/$f" "$REPO_DIR/$f"
            echo "  ✓ $f"
        fi
    done
    for d in "${BACKUP_DIRS[@]}"; do
        if [ -d "$BACKUP_DIR/$d" ]; then
            mkdir -p "$REPO_DIR/$d"
            cp -r "$BACKUP_DIR/$d/"* "$REPO_DIR/$d/" 2>/dev/null || true
            echo "  ✓ $d/"
        fi
    done
}

validate() {
    echo "🔍 Validating weather_bot.py..."
    cd "$REPO_DIR"
    python3 -c "compile(open('execution/weather_bot.py').read(), 'weather_bot.py', 'exec')" || {
        echo "❌ Syntax error! Aborting."
        return 1
    }
    echo "  ✓ Syntax OK"
}

healthcheck() {
    echo "🏥 Health check (5s)..."
    sleep 5
    if sudo systemctl is-active --quiet weather-bot; then
        echo "✅ weather-bot is running"
    else
        echo "❌ weather-bot crashed!"
        sudo journalctl -u weather-bot --no-pager -n 15 | grep -v 'getUpdates'
        return 1
    fi
}

deploy() {
    cd "$REPO_DIR"
    echo "📥 Pulling latest code..."
    git fetch origin main
    git reset --hard origin/main

    validate || exit 1

    echo "🔄 Restarting weather-bot..."
    sudo systemctl restart weather-bot
    healthcheck
}

reclone() {
    backup

    echo "🗑️  Removing old repo..."
    rm -rf "$REPO_DIR"

    echo "📥 Fresh clone..."
    cd /home/ubuntu
    git clone https://github.com/sisyphe10/Antigravity_Market_Dashboard.git

    restore
    validate || exit 1

    echo "🔄 Restarting weather-bot..."
    sudo systemctl restart weather-bot
    healthcheck
}

case "${1:-deploy}" in
    deploy)   deploy ;;
    reclone)  reclone ;;
    backup)   backup ;;
    restore)  restore ;;
    validate) validate ;;
    *)        echo "Usage: $0 {deploy|reclone|backup|restore|validate}" ;;
esac
