#!/bin/bash
# deploy.sh - Safe deployment for sisyphe-bot + research-notes-bot + ra-sisyphe-bot
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
    "subscribers_ra_sisyphe.json"
    "kna_state.json"
    ".budget_milestone"
    ".wisereport_sent.json"
    ".portfolio_report_sent.json"
    ".ledger_notified.json"
    "stock_price_history.json"
    "seonyuduo_exercise_user_map.json"
    "seonyuduo_chats.json"
    ".seonyuduo_cal_reminded.json"
    "execution/research_bot/research_notes.db"
    "etf_data.db"
    "execution/earnings_bot/earnings.db"
    "execution/earnings_bot/ticker_cik_cache.json"
)
BACKUP_DIRS=(
    "execution/research_bot/media"
    "sources_state"
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

BOTS=(sisyphe-bot research-notes-bot ra-sisyphe-bot seonyuduo-exercise-bot)
SCRIPTS=(execution/sisyphe_bot.py execution/research_bot/research_notes_bot.py execution/ra_sisyphe_bot.py execution/seonyuduo_exercise_bot.py)
EARNINGS_BOT_TIMER=earnings-bot.timer
KODEX_TIMER=kodex-sectors.timer
LANDING_HIGHLIGHTS_TIMER=landing-highlights.timer
ETF_TIMER=etf-collect.timer
EARNINGS_BOT_SCRIPTS=(
    execution/earnings_bot/runner.py
    execution/earnings_bot/edgar_monitor.py
    execution/earnings_bot/scheduler.py
    execution/earnings_bot/translator.py
    execution/earnings_bot/notion_publisher.py
    execution/earnings_bot/transcript_watch.py
)

validate() {
    echo "🔍 Validating bot scripts..."
    cd "$REPO_DIR"
    for s in "${SCRIPTS[@]}" "${EARNINGS_BOT_SCRIPTS[@]}"; do
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
    # earnings-bot은 oneshot timer라 is-active 검사 X. timer 활성 여부 확인.
    if sudo systemctl is-active --quiet "$EARNINGS_BOT_TIMER"; then
        echo "✅ $EARNINGS_BOT_TIMER is active"
    else
        echo "⚠️  $EARNINGS_BOT_TIMER inactive (한 번도 enable 안 됐을 수 있음)"
    fi
    if sudo systemctl is-active --quiet "$KODEX_TIMER"; then
        echo "✅ $KODEX_TIMER is active"
    else
        echo "⚠️  $KODEX_TIMER inactive"
    fi
    if sudo systemctl is-active --quiet "$LANDING_HIGHLIGHTS_TIMER"; then
        echo "✅ $LANDING_HIGHLIGHTS_TIMER is active"
    else
        echo "⚠️  $LANDING_HIGHLIGHTS_TIMER inactive"
    fi
    if sudo systemctl is-active --quiet "$ETF_TIMER"; then
        echo "✅ $ETF_TIMER is active"
    else
        echo "⚠️  $ETF_TIMER inactive (한 번도 enable 안 됐을 수 있음)"
    fi
    return $rc
}

install_earnings_bot_units() {
    # systemd unit 파일을 /etc/systemd/system/과 동기화.
    # repo의 unit과 다르면 cp + daemon-reload. 최초 설치 시 timer enable.
    local need_reload=0
    local need_enable=0
    if [ ! -f /etc/systemd/system/earnings-bot.service ]; then
        echo "🔧 earnings-bot systemd unit 최초 설치..."
        need_enable=1
    fi
    for unit in earnings-bot.service earnings-bot.timer earnings-bot-notify.service; do
        if [ ! -f "/etc/systemd/system/$unit" ] || ! cmp -s "$REPO_DIR/scripts/$unit" "/etc/systemd/system/$unit"; then
            echo "  → sync $unit"
            sudo cp "$REPO_DIR/scripts/$unit" /etc/systemd/system/
            need_reload=1
        fi
    done
    if [ "$need_reload" = 1 ]; then
        sudo systemctl daemon-reload
        echo "  ✓ daemon-reload"
    fi
    if [ "$need_enable" = 1 ]; then
        sudo systemctl enable --now earnings-bot.timer
        echo "  ✓ earnings-bot.timer enabled + started"
    fi
}

install_kodex_units() {
    # KRX가 GHA Azure IP 차단으로 VM에서 실행 (매일 23:30 KST)
    local need_reload=0
    local need_enable=0
    if [ ! -f /etc/systemd/system/kodex-sectors.service ]; then
        echo "🔧 kodex-sectors systemd unit 최초 설치..."
        need_enable=1
    fi
    for unit in kodex-sectors.service kodex-sectors.timer; do
        if [ ! -f "/etc/systemd/system/$unit" ] || ! cmp -s "$REPO_DIR/scripts/$unit" "/etc/systemd/system/$unit"; then
            echo "  → sync $unit"
            sudo cp "$REPO_DIR/scripts/$unit" /etc/systemd/system/
            need_reload=1
        fi
    done
    chmod +x "$REPO_DIR/scripts/run_kodex_sectors.sh"
    if [ "$need_reload" = 1 ]; then
        sudo systemctl daemon-reload
        echo "  ✓ daemon-reload"
    fi
    if [ "$need_enable" = 1 ]; then
        sudo systemctl enable --now kodex-sectors.timer
        echo "  ✓ kodex-sectors.timer enabled + started"
    fi
}

install_etf_units() {
    # ETF 구성종목 수집 (매일 16:30 + 18:00 재시도 KST). 봇 apscheduler에서 분리 —
    # 배포(봇 재시작)가 진행 중인 수집을 죽이지 않도록 별도 systemd 서비스로 실행.
    local need_reload=0
    local need_enable=0
    if [ ! -f /etc/systemd/system/etf-collect.service ]; then
        echo "🔧 etf-collect systemd unit 최초 설치..."
        need_enable=1
    fi
    for unit in etf-collect.service etf-collect.timer etf-collect-retry.timer; do
        if [ ! -f "/etc/systemd/system/$unit" ] || ! cmp -s "$REPO_DIR/scripts/$unit" "/etc/systemd/system/$unit"; then
            echo "  → sync $unit"
            sudo cp "$REPO_DIR/scripts/$unit" /etc/systemd/system/
            need_reload=1
        fi
    done
    chmod +x "$REPO_DIR/scripts/run_etf_collect.sh"
    if [ "$need_reload" = 1 ]; then
        sudo systemctl daemon-reload
        echo "  ✓ daemon-reload"
    fi
    if [ "$need_enable" = 1 ]; then
        sudo systemctl enable --now etf-collect.timer
        sudo systemctl enable --now etf-collect-retry.timer
        echo "  ✓ etf-collect.timer + etf-collect-retry.timer enabled + started"
    fi
}

install_bot_units() {
    # 3개 봇 service 파일 + sisyphe-bot-notify@.service template 동기화.
    # OnFailure 매핑 변경 등 .service 파일 수정 시 자동 반영. 기존 sisyphe-bot-notify.service는
    # 더 이상 OnFailure target이 아님 (deprecated), unit 자체는 유지 — 외부 수동 호출 호환성 보존.
    local need_reload=0
    for unit in sisyphe-bot.service ra-sisyphe-bot.service research-notes-bot.service seonyuduo-exercise-bot.service sisyphe-bot-notify@.service; do
        if [ ! -f "/etc/systemd/system/$unit" ] || ! cmp -s "$REPO_DIR/scripts/$unit" "/etc/systemd/system/$unit"; then
            echo "  → sync $unit"
            sudo cp "$REPO_DIR/scripts/$unit" /etc/systemd/system/
            need_reload=1
        fi
    done
    chmod +x "$REPO_DIR/scripts/notify_sisyphe_failure.sh"
    if [ "$need_reload" = 1 ]; then
        sudo systemctl daemon-reload
        echo "  ✓ daemon-reload"
    fi
    # 신규 봇 최초 1회 enable (기존 봇은 이미 enable됨 → restart 루프가 담당)
    if ! sudo systemctl is-enabled --quiet seonyuduo-exercise-bot 2>/dev/null; then
        sudo systemctl enable --now seonyuduo-exercise-bot
        echo "  ✓ seonyuduo-exercise-bot enabled + started (최초)"
    fi
}

install_landing_highlights_units() {
    # 30분 간격으로 landing_highlights.json 재생성 + push (16:00~16:59 KST 가드)
    local need_reload=0
    local need_enable=0
    if [ ! -f /etc/systemd/system/landing-highlights.service ]; then
        echo "🔧 landing-highlights systemd unit 최초 설치..."
        need_enable=1
    fi
    for unit in landing-highlights.service landing-highlights.timer landing-highlights-notify.service; do
        if [ ! -f "/etc/systemd/system/$unit" ] || ! cmp -s "$REPO_DIR/scripts/$unit" "/etc/systemd/system/$unit"; then
            echo "  → sync $unit"
            sudo cp "$REPO_DIR/scripts/$unit" /etc/systemd/system/
            need_reload=1
        fi
    done
    chmod +x "$REPO_DIR/scripts/run_landing_highlights.sh"
    if [ "$need_reload" = 1 ]; then
        sudo systemctl daemon-reload
        echo "  ✓ daemon-reload"
    fi
    if [ "$need_enable" = 1 ]; then
        sudo systemctl enable --now landing-highlights.timer
        echo "  ✓ landing-highlights.timer enabled + started"
    fi
}

deploy() {
    cd "$REPO_DIR"
    echo "📥 Pulling latest code..."
    git fetch origin main
    git reset --hard origin/main

    validate || exit 1

    install_bot_units
    install_earnings_bot_units
    install_kodex_units
    install_landing_highlights_units
    install_etf_units

    for b in "${BOTS[@]}"; do
        echo "🔄 Restarting $b..."
        sudo systemctl restart "$b"
    done
    # earnings-bot은 timer라 restart 불필요 — 다음 OnUnitActiveSec(5분)에 자동 실행
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

    install_bot_units
    install_earnings_bot_units
    install_kodex_units
    install_landing_highlights_units
    install_etf_units

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
