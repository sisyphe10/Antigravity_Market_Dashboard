#!/bin/bash
# install_all.sh — launchd 마스터 설치기 (D-day B6 = 이 스크립트 1회).
#
# root 로 한 번 실행하면 세 개별 installer 를 순서대로 돌린다:
#   1) bots/install_bots.sh      — 상시 봇 4종
#   2) timers/install_timers.sh  — 프로젝트 타이머 8종 (+ schedule.tsv)
#   3) system/install_system.sh  — 시스템 데몬 4종 (catchup·crash-watcher·git-pull·daily-selfcheck)
# ★ gha/ (GHA 흡수 9종) 는 **Phase 2** 이므로 여기서 설치하지 않는다 (의도적 제외).
#
# 개별 installer 는 무변경 — 이 스크립트는 순차 실행 + 요약 + 통합 검증 래핑만 한다.
# 한 단계라도 실패하면 그 지점에서 중단하고 어느 installer 였는지 명시한다.
# 마지막에 launchctl 로 plist 16개 로드 + 봇 4개 running 을 대조표로 검증한다.
#
# 사용법:  sudo ./install_all.sh [macmini_user]
#   macmini_user 미지정 시 sudo 를 실행한 계정($SUDO_USER)으로 추정.
set -u

# ── root 요구 (LaunchDaemons 설치 = root) ──────────────────────
if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: sudo 로 실행하세요 (LaunchDaemons 설치는 root 필요)." >&2
  echo "       sudo ./install_all.sh [macmini_user]" >&2
  exit 1
fi

# ── 사용자명 조기 검증 (개별 installer 도 재검증하지만 미리 차단) ──
valid_user() {
  local u="$1"
  [ -n "$u" ] || return 1
  case "$u" in [a-z_]*) ;; *) return 1 ;; esac
  case "$u" in *[!a-z0-9_-]*) return 1 ;; *) return 0 ;; esac
}
MACMINI_USER="${1:-${SUDO_USER:-}}"
if ! valid_user "$MACMINI_USER" || [ "$MACMINI_USER" = "root" ]; then
  echo "ERROR: 유효한 비-root 사용자명을 넘기세요: sudo ./install_all.sh <macmini_user>" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== launchd 마스터 설치 (user=$MACMINI_USER) — gha/ 는 Phase 2 제외 ==="
echo

# ── 단계 실행 (실패 시 즉시 중단 + installer 명시) ─────────────
run_step() {  # <제목> <installer 경로>
  local title="$1" installer="$2" rc
  echo "─── $title  ($installer) ───"
  if [ ! -f "$installer" ]; then
    echo "  ✗ installer 파일 없음: $installer — 중단" >&2
    return 1
  fi
  # rc 를 installer 직후 즉시 캡처한다. `if cmd; then …; fi` 뒤의 $? 는 조건 실패 시
  # (else 없음) if-구문 자체의 0 이 되어 실패를 삼킨다 — 그래서 분리해서 잡는다.
  /bin/bash "$installer" "$MACMINI_USER"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "  ✓ $title 설치 완료"
    echo
    return 0
  fi
  echo "  ✗ $title 설치 실패 — installer=$installer, rc=$rc. 여기서 중단합니다." >&2
  return "$rc"
}

run_step "① 봇 4종"    "$SCRIPT_DIR/bots/install_bots.sh"     || exit $?
run_step "② 타이머 8종" "$SCRIPT_DIR/timers/install_timers.sh" || exit $?
run_step "③ 시스템 4종" "$SCRIPT_DIR/system/install_system.sh" || exit $?

# ── 통합 검증 (별도 스크립트에 위임) ──────────────────────────
#   설치 판정은 verify_launchd.sh 기본 모드(plist 16 lint+로드+봇4 running+.err 금지패턴).
#   같은 스크립트를 `--status` 로 부르면 B7 상태판이 된다(재부팅 후 점검).
VERIFY="$SCRIPT_DIR/verify_launchd.sh"
echo "─── 통합 검증 (verify_launchd.sh) ───"
if [ ! -f "$VERIFY" ]; then
  echo "=== ⚠️ verify_launchd.sh 없음: $VERIFY — 설치는 됐으나 검증 불가 ===" >&2
  exit 1
fi
if /bin/bash "$VERIFY"; then
  echo "=== ✅ B6 완료 (verify PASS) ==="
  exit 0
else
  rc=$?
  echo "=== ⚠️ B6 검증 미달 (verify FAIL, rc=$rc) — 위 FAIL 사유 확인 ===" >&2
  exit "$rc"
fi
