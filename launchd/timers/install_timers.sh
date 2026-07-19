#!/bin/bash
# install_timers.sh — Antigravity 타이머 8종 launchd 설치 (Wave 0 / WP-A2b, 배포 레이아웃 계약 반영)
#
# CONTRACT "배포 레이아웃": 이 launchd/ 트리는 맥미니에서 __REPO__/launchd/ 로 배포된다(rsync 대상).
# wrapper(run_timer_job.sh)는 __REPO__/launchd/timers/ 에서 self-locate 로 in-place 실행되며
# 별도 위치로 복사하지 않는다(이중 사본 드리프트 방지). 따라서 install 이 하는 일은 두 가지뿐:
#   ① plist 토큰 치환 → /Library/LaunchDaemons 설치 + (재)bootstrap
#   ② schedule.tsv 치환본 → __REPO__/logs/launchd/schedule.tsv (catch-up 러너 A4 의 확정 읽기 경로)
#
# 사용법:  sudo ./install_timers.sh [MACMINI_USER]
#   - MACMINI_USER 생략 시 $SUDO_USER → 콘솔 사용자 순으로 자동 결정.
#   - 반드시 sudo 로 실행 (LaunchDaemons 쓰기 + system 도메인 bootstrap 은 root 필요).
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── 토큰값 결정 ──────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: sudo 로 실행하세요 (LaunchDaemons 설치 + system bootstrap 은 root 필요)." >&2
  exit 1
fi

MACMINI_USER="${1:-${SUDO_USER:-}}"
if [ -z "$MACMINI_USER" ] || [ "$MACMINI_USER" = "root" ]; then
  MACMINI_USER="$(stat -f%Su /dev/console 2>/dev/null || true)"   # 콘솔 로그인 사용자 폴백
fi
if [ -z "$MACMINI_USER" ] || [ "$MACMINI_USER" = "root" ]; then
  echo "ERROR: 실제 사용자를 결정하지 못했습니다. 인자로 넘기세요: sudo ./install_timers.sh <user>" >&2
  exit 1
fi

# --- 사용자명 형식 엄격 검증 (sed 치환 안전, install_bots.sh valid_user 이식) --------------
# macOS 사용자명 규칙 + sed 특수문자(&·|·개행·공백·탭·대문자) 원천 차단.
# ★ grep -Eq 대신 case 글로브: grep 은 행 단위 매칭이라 'a\nb' 같은 개행이 ^...$ 앵커를 통과해
#   plist 파손을 유발한다. case 는 문자열 전체(개행 포함)에 매칭하므로 개행/제어문자를 정확히 거른다.
valid_user() {
  local u="$1"
  [ -n "$u" ] || return 1
  case "$u" in [a-z_]*) ;; *) return 1 ;; esac              # 첫 글자 소문자/밑줄
  case "$u" in *[!a-z0-9_-]*) return 1 ;; *) return 0 ;; esac  # 허용집합 밖 문자 존재 시 거부
}
if ! valid_user "$MACMINI_USER"; then
  echo "ERROR: 부적합한 사용자명 (허용: 소문자/숫자/밑줄/하이픈, 첫 글자는 소문자/밑줄)." >&2
  echo "       sudo ./install_timers.sh <macmini_user> 형식으로 실사용자명을 넘기세요." >&2
  exit 1
fi

USER_HOME="$(dscl . -read "/Users/$MACMINI_USER" NFSHomeDirectory 2>/dev/null | awk '{print $2}')"
USER_HOME="${USER_HOME:-/Users/$MACMINI_USER}"
REPO="$USER_HOME/Antigravity_Market_Dashboard"

if [ ! -d "$REPO" ]; then
  echo "ERROR: 레포가 없습니다: $REPO (경로 확인 후 재실행)" >&2
  exit 1
fi

# wrapper 는 in-place 참조 대상 → rsync 로 자리 잡았는지 사전 점검(설치가 아니라 검증).
WRAPPER="$REPO/launchd/timers/run_timer_job.sh"
if [ ! -f "$WRAPPER" ]; then
  echo "ERROR: wrapper 부재: $WRAPPER — launchd/ 트리 rsync 후 재실행(복사 설치하지 않음)." >&2
  exit 1
fi

echo "MACMINI_USER = $MACMINI_USER"
echo "REPO         = $REPO"
echo "WRAPPER      = $WRAPPER (in-place)"

DAEMON_DIR="/Library/LaunchDaemons"
NAMES=(featured-kis etf-collect etf-collect-retry landing-highlights \
       etf-active-alert kodex-sectors earnings-bot update-stock-master \
       memento-telegram wrap-principle-check us-etf-collect memory-cycle-alert)

# 토큰 치환 헬퍼: stdin → stdout
render() {
  sed -e "s#__MACMINI_USER__#${MACMINI_USER}#g" \
      -e "s#__REPO__#${REPO}#g"
}

# ── ② schedule.tsv 렌더 → logs/launchd (A4 catch-up 러너가 읽음) ──
install -d -o "$MACMINI_USER" -m 755 "$REPO/logs/launchd"
render < "$SRC_DIR/schedule.tsv" > "$REPO/logs/launchd/schedule.tsv"
chown "$MACMINI_USER" "$REPO/logs/launchd/schedule.tsv"
echo "installed: $REPO/logs/launchd/schedule.tsv"
# (stamps/locks 디렉토리는 wrapper 가 런타임에 mkdir 하므로 여기서 만들지 않는다.)

# ── ① plist 렌더 → LaunchDaemons → (재)bootstrap ────────────────
for name in "${NAMES[@]}"; do
  label="com.antigravity.$name"
  src="$SRC_DIR/$label.plist"
  dst="$DAEMON_DIR/$label.plist"

  if [ ! -f "$src" ]; then
    echo "WARN: plist 없음, 건너뜀: $src" >&2
    continue
  fi

  render < "$src" > "$dst"
  chown root:wheel "$dst"
  chmod 0644 "$dst"

  launchctl bootout system "$dst" 2>/dev/null || true   # 이미 적재면 내렸다가 재적재(idempotent)
  launchctl bootstrap system "$dst"
  echo "bootstrapped: $label"
done

echo
echo "완료. 적재 확인:  sudo launchctl list | grep com.antigravity"
echo "다음 실행 예정 확인은 README.md 검증 섹션 참고 (launchd 는 systemd list-timers 등가물 없음)."
