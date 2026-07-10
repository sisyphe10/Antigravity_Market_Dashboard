#!/bin/bash
# verify_launchd.sh — launchd 설치/상태 검증기 (단독 실행 가능, 2모드).
#
#   (기본, 인자 없음)  = ★설치 판정 (B6): plist 16 lint + 로드 + 봇4 running(pid 안정)
#                        + .err 금지패턴 부재 → 마지막에 PASS/FAIL 한 줄 (exit 0/1).
#   --status           = ★상태판 (B7·재부팅 후): 봇 상태 + 타이머 다음 발화/최근 stamp 나이
#                        + git-pull 실패 요약 + 시스템 데몬 로드. 사람이 눈으로 훑는 용도 (항상 exit 0).
#
# install_all.sh 가 마지막에 (기본 모드로) 호출한다. gha/ 는 Phase 2라 대상 아님.
# bash 3.2 / BSD 도구(launchctl·plutil·date -r) 전제(맥미니).
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"          # launchd/ → repo 루트
LOGDIR="$REPO/logs/launchd"
STAMP_DIR="$LOGDIR/stamps"
SCHEDULE_TSV="${SCHEDULE_TSV:-$LOGDIR/schedule.tsv}"
LAUNCHD_DIR="${LAUNCHD_DIR:-/Library/LaunchDaemons}"
PID_STABLE_WAIT="${PID_STABLE_WAIT:-2}"       # 봇 pid 안정 확인 간격(초)

BOT_LABELS="com.antigravity.sisyphe-bot com.antigravity.ra-sisyphe-bot com.antigravity.research-notes-bot com.antigravity.seonyuduo-exercise-bot"
TIMER_LABELS="com.antigravity.featured-kis com.antigravity.etf-collect com.antigravity.etf-collect-retry com.antigravity.landing-highlights com.antigravity.etf-active-alert com.antigravity.kodex-sectors com.antigravity.earnings-bot com.antigravity.update-stock-master"
SYSTEM_LABELS="com.antigravity.catchup com.antigravity.crash-watcher com.antigravity.git-pull com.antigravity.daily-selfcheck"
ALL_LABELS="$BOT_LABELS $TIMER_LABELS $SYSTEM_LABELS"

FORBIDDEN='Traceback \(most recent call last\)|command not found|No such file or directory|Permission denied|ModuleNotFoundError'

is_loaded()  { launchctl print "system/$1" >/dev/null 2>&1; }
is_running() { launchctl print "system/$1" 2>/dev/null | grep -q "state = running"; }
job_pid()    { launchctl print "system/$1" 2>/dev/null | awk '/^[[:space:]]*pid = [0-9]/{print $3; exit}'; }
short()      { echo "${1#com.antigravity.}"; }

kst_midnight() { echo $(( ( ($1 + 32400) / 86400 ) * 86400 - 32400 )); }
read_int()   { local v=""; [ -f "$1" ] && v="$(head -n1 "$1" 2>/dev/null)"; v="${v//[!0-9]/}"; echo "${v:-0}"; }
human_age()  { local s="$1"; [ "$s" -lt 0 ] && s=0
  if   [ "$s" -ge 86400 ]; then echo "$((s/86400))d"
  elif [ "$s" -ge 3600 ];  then echo "$((s/3600))h"
  else echo "$((s/60))m"; fi; }
fmt_epoch()  { date -r "$1" '+%m-%d %H:%M' 2>/dev/null || echo "@$1"; }

# cron(분 시 일 월 요일) → 다음 발화 epoch (일간/주간만; 못 구하면 빈 문자열)
next_fire() {
  local cron="$1" now="$2" m h dom mon dow t0 f i cur want
  read -r m h dom mon dow <<< "$cron"
  case "${m:-}" in ''|*[!0-9]*) return 0 ;; esac
  case "${h:-}" in ''|*[!0-9]*) return 0 ;; esac
  m=$((10#$m)); h=$((10#$h)); t0="$(kst_midnight "$now")"
  if [ "${dow:-*}" = "*" ]; then
    f=$(( t0 + h*3600 + m*60 )); [ "$f" -le "$now" ] && f=$(( f + 86400 )); echo "$f"; return 0
  fi
  case "$dow" in ''|*[!0-9]*) return 0 ;; esac      # 복합 요일은 미지원(빈 반환)
  want=$((10#$dow)); [ "$want" -eq 7 ] && want=0
  for i in 0 1 2 3 4 5 6 7; do
    f=$(( t0 + i*86400 + h*3600 + m*60 ))
    cur="$(date -r "$f" +%w 2>/dev/null)"
    [ "$cur" = "$want" ] && [ "$f" -gt "$now" ] && { echo "$f"; return 0; }
  done
}

# schedule.tsv 에서 <이름> 행의 cron(2번째 컬럼) 반환
cron_of() {
  [ -f "$SCHEDULE_TSV" ] || return 0
  local c1 c2 c3 c4
  while IFS=$'\t' read -r c1 c2 c3 c4 || [ -n "$c1" ]; do
    case "$c1" in ''|\#*) continue ;; esac
    [ "$c1" = "$1" ] && { printf '%s' "$c2"; return 0; }
  done < "$SCHEDULE_TSV" 2>/dev/null
}

# ── 모드 ①: 설치 판정 ─────────────────────────────────────────
install_verify() {
  local fail=0 reasons="" lbl p ef name
  # plist lint + 로드
  for lbl in $ALL_LABELS; do
    p="$LAUNCHD_DIR/$lbl.plist"
    if [ ! -f "$p" ]; then fail=1; reasons="$reasons noplist:$(short "$lbl")"; continue; fi
    plutil -lint "$p" >/dev/null 2>&1 || { fail=1; reasons="$reasons lint:$(short "$lbl")"; }
    is_loaded "$lbl" || { fail=1; reasons="$reasons unloaded:$(short "$lbl")"; }
  done
  # 봇 running + pid 안정: 간격을 두고 pid 를 두 번 읽어 ★동일한지 확인(다르면 크래시 재시작=flapping).
  local before_list="" pair before after
  for lbl in $BOT_LABELS; do
    before="$(job_pid "$lbl")"
    if [ -z "$before" ] || ! is_running "$lbl"; then
      fail=1; reasons="$reasons notrunning:$(short "$lbl")"; before=""
    fi
    before_list="$before_list $lbl=$before"
  done
  sleep "$PID_STABLE_WAIT"
  for pair in $before_list; do
    lbl="${pair%%=*}"; before="${pair#*=}"
    [ -n "$before" ] || continue                    # 이미 not-running 로 기록됨
    after="$(job_pid "$lbl")"
    if [ -z "$after" ] || ! is_running "$lbl"; then fail=1; reasons="$reasons flapping:$(short "$lbl")"; continue; fi
    [ "$after" = "$before" ] || { fail=1; reasons="$reasons pidchg:$(short "$lbl")"; }
  done
  # .err 금지패턴
  for ef in "$LOGDIR"/*.err; do
    [ -f "$ef" ] || continue
    if grep -qE "$FORBIDDEN" "$ef" 2>/dev/null; then
      fail=1; name="$(basename "$ef" .err)"; reasons="$reasons err:$name"
    fi
  done
  if [ "$fail" -eq 0 ]; then
    echo "PASS launchd: plist 16 lint+로드 OK, 봇 4 running(pid 안정), .err 금지패턴 없음"
    return 0
  fi
  echo "FAIL launchd:$reasons"
  return 1
}

# ── 모드 ②: 상태판 (--status) ────────────────────────────────
status_board() {
  local now lbl s cron nf age sf fc last
  now="$(date +%s)"
  echo "=== launchd 상태판 ($(date '+%Y-%m-%d %H:%M %Z')) ==="
  echo "[봇]"
  for lbl in $BOT_LABELS; do
    if is_running "$lbl"; then echo "  ✓ $(short "$lbl")  running (pid $(job_pid "$lbl"))"
    else echo "  ✗ $(short "$lbl")  running 아님"; fi
  done
  echo "[타이머]  이름  다음발화  ·  최근 stamp 나이"
  for lbl in $TIMER_LABELS; do
    s="$(short "$lbl")"; cron="$(cron_of "$s")"
    nf="$(next_fire "$cron" "$now")"; [ -n "$nf" ] && nf="$(fmt_epoch "$nf")" || nf="?"
    sf="$STAMP_DIR/$s.last"
    if [ -f "$sf" ]; then age="$(human_age $(( now - $(read_int "$sf") )))"; else age="stamp없음"; fi
    is_loaded "$lbl" || nf="미로드"
    printf '  %-20s  %-11s  last %s\n' "$s" "$nf" "$age"
  done
  echo "[git-pull]"
  fc="$(read_int "$LOGDIR/git-pull.failcount")"
  last="$(grep 'FAIL' "$LOGDIR/git-pull.log" 2>/dev/null | tail -1)"
  echo "  연속실패=$fc  |  최근: ${last:-(실패 로그 없음)}"
  echo "[시스템]"
  for lbl in $SYSTEM_LABELS; do
    if is_loaded "$lbl"; then echo "  ✓ $(short "$lbl")  로드됨"; else echo "  ✗ $(short "$lbl")  미로드"; fi
  done
}

case "${1:-}" in
  --status) status_board; exit 0 ;;
  ''|--verify) install_verify; exit $? ;;
  *) echo "usage: $0 [--status]" >&2; exit 2 ;;
esac
