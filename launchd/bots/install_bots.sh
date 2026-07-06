#!/bin/bash
#
# install_bots.sh — 맥미니에 상시 봇 LaunchDaemon 4종 설치/재설치 (WP-A2a)
#
# ★ 맥미니에서 sudo 로 실행한다. 지금(개발 시점)은 실행하지 않고 스크립트만 둔다.
#
#   sudo ./install_bots.sh [MACMINI_USER]
#
# 동작:
#   1) 사용자명 형식 엄격 검증(sed 인젝션/plist 파손 방지)
#   2) 사전 게이트: wrapper·venv python·.env·봇 스크립트·notify 스크립트 부재 시 즉시 실패
#      (경고 후 진행 금지 — broken daemon 설치 방지, codex 리뷰 상3 반영)
#   3) 각 plist 의 __MACMINI_USER__ 토큰 sed 치환 → /Library/LaunchDaemons 복사
#      → chown root:wheel, chmod 644
#   4) launchctl bootout(있으면) → bootstrap → enable → kickstart
#
# MACMINI_USER 인자 미지정 시 sudo 를 실행한 원래 사용자($SUDO_USER)로 추정.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "error: /Library/LaunchDaemons 설치는 root 권한이 필요합니다. sudo 로 실행하세요." >&2
    exit 1
fi

MACMINI_USER="${1:-${SUDO_USER:-$(id -un)}}"

# --- 사용자명 형식 엄격 검증 (sed 치환 안전) -------------------------------
# macOS 사용자명 규칙 + sed 특수문자(&·|·개행·공백·탭·대문자) 원천 차단.
# ★ grep -Eq 대신 case 글로브 사용: grep 은 행 단위 매칭이라 'a\nb' 같은 개행 삽입이
#   ^...$ 앵커를 통과(각 행이 개별 매칭)해 plist 파손을 유발한다. case 는 문자열 전체
#   (개행 포함)에 매칭하므로 개행/제어문자를 정확히 거른다.
valid_user() {
    local u="$1"
    [ -n "$u" ] || return 1
    case "$u" in [a-z_]*) ;; *) return 1 ;; esac         # 첫 글자 소문자/밑줄
    case "$u" in *[!a-z0-9_-]*) return 1 ;; *) return 0 ;; esac  # 허용집합 밖 문자 존재 시 거부
}
if ! valid_user "$MACMINI_USER"; then
    echo "error: 부적합한 사용자명 (허용: 소문자/숫자/밑줄/하이픈, 첫 글자는 소문자/밑줄)." >&2
    echo "       sudo $0 <macmini_user> 형식으로 실사용자명을 넘기세요." >&2
    exit 1
fi
if [ "$MACMINI_USER" = "root" ]; then
    echo "error: MACMINI_USER 가 root 입니다. 실사용자명을 인자로 넘기세요: sudo $0 <user>" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DAEMON_DIR="/Library/LaunchDaemons"
REPO="/Users/$MACMINI_USER/Antigravity_Market_Dashboard"

LABELS=(
    com.antigravity.sisyphe-bot
    com.antigravity.ra-sisyphe-bot
    com.antigravity.research-notes-bot
    com.antigravity.seonyuduo-exercise-bot
)

# 각 봇이 실제 실행하는 스크립트(존재 게이트 대상). plist ProgramArguments 와 일치해야 함.
BOT_SCRIPTS=(
    "$REPO/execution/sisyphe_bot.py"
    "$REPO/execution/ra_sisyphe_bot.py"
    "$REPO/execution/research_bot/research_notes_bot.py"
    "$REPO/execution/seonyuduo_exercise_bot.py"
)

# --- 사전 게이트 (하나라도 없으면 exit 1) ----------------------------------
FATAL=0
gate() {  # gate <설명> <경로> [x|f]
    local desc="$1" path="$2" mode="${3:-f}"
    if [ "$mode" = "x" ]; then
        [ -x "$path" ] && return 0
    else
        [ -e "$path" ] && return 0
    fi
    echo "error: 필수 파일 없음/실행불가 ($desc): $path" >&2
    FATAL=1
}

WRAPPER="$REPO/launchd/bots/run_bot.sh"
gate "wrapper"        "$WRAPPER"                            f
gate "venv python3"   "$REPO/venv/bin/python3"             x
gate ".env"           "$REPO/.env"                          f
gate "notify 스크립트(실행권한)" "$REPO/scripts/notify_sisyphe_failure.sh" x
for s in "${BOT_SCRIPTS[@]}"; do gate "봇 스크립트" "$s" f; done
for label in "${LABELS[@]}"; do gate "원본 plist" "$SCRIPT_DIR/$label.plist" f; done

if [ "$FATAL" -ne 0 ]; then
    echo "설치 중단: 위 필수 항목을 먼저 배치하세요 (repo 가 $REPO 에 배포됐는지 확인)." >&2
    exit 1
fi

# 로그 디렉터리(launchd StandardOut/Err, wrapper starts breadcrumb) 미리 생성.
sudo -u "$MACMINI_USER" mkdir -p "$REPO/logs/launchd/starts"

# wrapper 실행권한 보장.
chmod +x "$WRAPPER"

# --- 설치 ------------------------------------------------------------------
for label in "${LABELS[@]}"; do
    src="$SCRIPT_DIR/$label.plist"
    dst="$DAEMON_DIR/$label.plist"

    echo "==> $label"
    # 1) 토큰 치환하여 목적지에 렌더링(사용자명은 위에서 엄격 검증됨)
    sed "s|__MACMINI_USER__|$MACMINI_USER|g" "$src" > "$dst"
    # 2) 소유권/권한
    chown root:wheel "$dst"
    chmod 644 "$dst"
    # 3) 재부트스트랩(이미 로드돼 있으면 bootout 후 재로드)
    launchctl bootout "system/$label" 2>/dev/null || true
    launchctl bootstrap system "$dst"
    launchctl enable "system/$label"
    launchctl kickstart "system/$label" 2>/dev/null || true
done

echo
echo "설치 완료. 검증:"
for label in "${LABELS[@]}"; do
    echo "  launchctl print system/$label | grep -E 'state|pid|program'"
done
