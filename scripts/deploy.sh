#!/bin/bash
# deploy.sh - Safe deployment for sisyphe-bot + research-notes-bot + research-alerts-bot
# Usage:
#   ./scripts/deploy.sh          # pull + validate + restart all bots
#   ./scripts/deploy.sh reclone  # backup + re-clone + restore + restart
set -e

REPO_DIR="/home/ubuntu/Antigravity_Market_Dashboard"
BACKUP_DIR="/tmp/dashboard_backup"

# ── untracked 파일 백업 목록 ──
BACKUP_FILES=(
    ".env"
    "subscribers.json"
    "subscribers_research.json"
    "kna_state.json"
    ".budget_milestone"
    ".wisereport_sent.json"
    "stock_price_history.json"
    "execution/research_bot/research_notes.db"
    "etf_data.db"
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

BOTS=(sisyphe-bot research-notes-bot research-alerts-bot)
SCRIPTS=(execution/sisyphe_bot.py execution/research_bot/research_notes_bot.py execution/research_alerts_bot.py)

validate() {
    echo "🔍 Validating bot scripts..."
    cd "$REPO_DIR"
    for s in "${SCRIPTS[@]}"; do
        python3 -c "compile(open('$s').read(), '$s', 'exec')" || {
            echo "❌ Syntax error in $s! Aborting."
            return 1
        }
        echo "  ✓ $s OK"
    done
}

healthcheck() {
    echo "🏥 Health check (5s)..."
    sleep 5
    local rc=0
    for b in "${BOTS[@]}"; do
        if sudo systemctl is-active --quiet "$b"; then
            echo "✅ $b is running"
        else
            echo "❌ $b crashed!"
            sudo journalctl -u "$b" --no-pager -n 15 | grep -v 'getUpdates'
            rc=1
        fi
    done
    return $rc
}

deploy() {
    cd "$REPO_DIR"
    echo "📥 Pulling latest code..."
    git fetch origin main
    git reset --hard origin/main

    validate || exit 1

    for b in "${BOTS[@]}"; do
        echo "🔄 Restarting $b..."
        sudo systemctl restart "$b"
    done
    healthcheck
}

reclone() {
    backup

    echo "🗑️  Removing old repo..."
    rm -rf "$REPO_DIR"

    echo "📥 Fresh clone..."
    cd /home/ubuntu
    # .env에서 GH_PAT 읽기 (push 인증용)
    GH_PAT=$(grep '^GH_PAT=' "$BACKUP_DIR/.env" 2>/dev/null | cut -d= -f2)
    if [ -n "$GH_PAT" ]; then
        git clone "https://sisyphe10:${GH_PAT}@github.com/sisyphe10/Antigravity_Market_Dashboard.git"
    else
        git clone https://github.com/sisyphe10/Antigravity_Market_Dashboard.git
    fi

    restore
    validate || exit 1

    for b in "${BOTS[@]}"; do
        echo "🔄 Restarting $b..."
        sudo systemctl restart "$b"
    done
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
