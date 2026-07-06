#!/bin/bash
# run_timer_job.sh — launchd 타이머 공용 wrapper (Wave 0 / WP-A2b, codex 리뷰 3차 반영)
#
# 원본 systemd 타이머 8종을 macOS launchd로 이전하면서 systemd 가 무료로 주던 기능
# (EnvironmentFile 로드, OnFailure 알림, oneshot 성공/실패 판정, TimeoutStartSec)을 대체한다.
#
# 사용법:  run_timer_job.sh <이름>
#   <이름> ∈ featured-kis | etf-collect | etf-collect-retry | landing-highlights
#           | etf-active-alert | kodex-sectors | earnings-bot | update-stock-master
#
# 동작:
#   1. self-locate 로 REPO 결정(launchd/timers/ → repo 루트). 별도 사본 없음(배포 레이아웃 계약).
#   2. 잡 이름별 락 획득(mkdir, stale 는 rename 회수) — 중복 실행의 단일 방어선(인터페이스 1-1).
#      이미 살아있는 인스턴스가 있으면 조용히 스킵(exit 0).
#   3. .env 안전 파서(CONTRACT v3) 로드 후, 잡별 TimeoutStartSec 워치독 하에 실행.
#   4. 성공(exit 0)  → stamps/<이름>.last 원자적 기록(mktemp+mv). ★기록 실패 시 notify + 비정상 종료(인터페이스 1).
#   5. 실패(exit≠0/타임아웃) → 전용 notify 스크립트 호출 후 원래 exit 코드 유지, stamp 미기록.

set -u

NAME="${1:?usage: run_timer_job.sh <name>}"

# ── REPO self-locate (배포 레이아웃: __REPO__/launchd/timers/run_timer_job.sh) ──
#   이 파일은 항상 repo 의 launchd/timers/ 아래에 있으므로, 두 단계 상위가 repo 루트다.
#   토큰(__REPO__) 렌더 불필요 → 이중 사본/드리프트 없음(CONTRACT 배포 레이아웃).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
PY="$REPO/venv/bin/python3"           # 결정 5: pyenv 3.10.12 기반 venv
STAMP_DIR="$REPO/logs/launchd/stamps"
LOCK_ROOT="$REPO/logs/launchd/locks"

# 잡의 작업 디렉토리 = repo 루트 (원본 systemd WorkingDirectory 대응)
cd "$REPO" || { echo "[run_timer_job] cd $REPO 실패" >&2; exit 1; }

# venv 를 PATH 최상단에 → run_*.sh 헬퍼 안의 'python3'(PATH 의존)도 venv 로 해석되게 한다.
export PATH="$REPO/venv/bin:$PATH"

# ── 잡별 동시실행 락 (인터페이스 1-1) ───────────────────────────
#   mkdir(원자적)로 획득, pid 기록. 이미 살아있는 홀더면 스킵. stale 는 rename 으로 배타 회수
#   (rm -rf 후 mkdir 재시도식 TOCTOU 금지 — mv 로 고유 임시명 회수 후 내용 확인·삭제).
LOCK_HELD=""
release_lock() { [ -n "${LOCK_HELD:-}" ] && rm -rf "$LOCK_HELD"; LOCK_HELD=""; }
trap release_lock EXIT

read_holder() {  # $1=lock dir. pid 를 최대 3회(0.2s 간격) 재시도로 읽어 갓생성 창을 흡수. 실패 시 rc≠0.
  local lock="$1" tries=0 h=""
  while [ "$tries" -lt 3 ]; do
    [ -f "$lock/pid" ] && h="$(cat "$lock/pid" 2>/dev/null)"
    [ -n "$h" ] && { printf '%s' "$h"; return 0; }
    tries=$((tries+1)); sleep 0.2
  done
  return 1
}

acquire_lock() {  # rc 0=획득, 2=이미 실행 중(스킵)
  local name="$1"
  local lock="$LOCK_ROOT/$name.lock"   # 별도 선언 — 한 local 문 안에서 $name 참조 시 set -u 로 unbound
  local holder claimed h2
  mkdir -p "$LOCK_ROOT"
  if mkdir "$lock" 2>/dev/null; then
    echo $$ > "$lock/pid"; LOCK_HELD="$lock"; return 0
  fi
  # 락 존재 → 홀더가 살아있으면 스킵
  if holder="$(read_holder "$lock")"; then
    if kill -0 "$holder" 2>/dev/null; then return 2; fi
  fi
  # orphan/죽은 홀더 → rename 으로 배타적 회수 (mv 성공한 1개만 stale dir 소유)
  claimed="$lock.reclaim.$$.$RANDOM"
  if mv "$lock" "$claimed" 2>/dev/null; then
    h2=""
    [ -f "$claimed/pid" ] && h2="$(cat "$claimed/pid" 2>/dev/null)"
    if [ -n "$h2" ] && kill -0 "$h2" 2>/dev/null; then
      # 회수 도중 홀더가 실은 살아있었다(경합) → 되돌리고 스킵
      mv "$claimed" "$lock" 2>/dev/null || rm -rf "$claimed"
      return 2
    fi
    rm -rf "$claimed"
    if mkdir "$lock" 2>/dev/null; then
      echo $$ > "$lock/pid"; LOCK_HELD="$lock"; return 0
    fi
    return 2   # 그새 타 인스턴스가 선점 → 스킵
  fi
  return 2     # rename 실패 = 타 인스턴스가 먼저 회수/획득 → 스킵
}

# ── .env 안전 로드 (CONTRACT v3) ────────────────────────────────
#   systemd EnvironmentFile 대체. 값 내 공백·&·$()·backtick·JSON 을 절대 쉘 해석하지 않는다.
#   행별로 첫 '=' 로 KEY/VALUE 분리 → KEY 검증(^[A-Za-z_][A-Za-z0-9_]*$) → export KEY=VALUE(확장 없음).
#   ★v3: VALUE 양끝을 감싼 동일 따옴표 한 쌍("..." 또는 '...')만 제거(systemd 등가). 내부 따옴표는 보존.
#   (VM .env 에 double-quote 값 1건 실존 — 리터럴 보존 시 따옴표째 주입돼 파손되므로 반드시 제거.)
load_env() {
  local env_file="$1"
  [ -f "$env_file" ] || return 0
  local line key value stripped
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"                       # CRLF 방어
    case "$line" in ''|'#'*) continue ;; esac   # 빈 줄/주석 스킵
    line="${line#export }"                      # 'export ' 접두 허용
    case "$line" in *=*) : ;; *) continue ;; esac
    key="${line%%=*}"
    value="${line#*=}"
    # KEY 앞뒤 공백 트림
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    # KEY 검증: 첫 글자는 숫자 불가, 허용 문자(영숫자·_)만
    case "$key" in ''|[0-9]*) continue ;; esac
    stripped="${key//[A-Za-z0-9_]/}"
    [ -z "$stripped" ] || continue
    # VALUE 를 감싼 동일 따옴표 한 쌍만 제거(systemd 호환). 내부는 확장하지 않는다.
    case "$value" in
      \"*\") value="${value#\"}"; value="${value%\"}" ;;
      \'*\') value="${value#\'}"; value="${value%\'}" ;;
    esac
    export "$key=$value"
  done < "$env_file"
}

# ── 잡별 TimeoutStartSec (원본 .service 값 그대로, 초 단위) ──────
job_timeout_seconds() {
  case "$1" in
    featured-kis)         echo 900  ;;   # 원본 TimeoutStartSec=15min
    etf-collect)          echo 1800 ;;   # 원본 30min
    etf-collect-retry)    echo 1800 ;;   # etf-collect.service 공유 → 30min
    landing-highlights)   echo 300  ;;   # 원본 5min
    etf-active-alert)     echo 600  ;;   # 원본 10min
    kodex-sectors)        echo 600  ;;   # 원본 10min
    earnings-bot)         echo 2700 ;;   # 원본 45min
    update-stock-master)  echo 900  ;;   # 원본 15min
    *)                    echo 1800 ;;   # 미지정 안전 기본(90s 대신 30min)
  esac
}

# ── 전용 실패 알림 (systemd OnFailure 대응) ─────────────────────
notify_failure() {
  case "$1" in
    landing-highlights)
      # 원본 OnFailure=landing-highlights-notify.service → 전용 스크립트(인자 없음)
      "$REPO/scripts/notify_landing_highlights_failure.sh" || true
      ;;
    *)
      # 나머지: 원본 OnFailure=sisyphe-bot-notify@<이름> / earnings-bot-notify → 통합 스크립트
      "$REPO/scripts/notify_sisyphe_failure.sh" "$1" || true
      ;;
  esac
}

# ── 성공 stamp 원자적 기록 (mktemp + mv -f). rc≠0 이면 호출부가 notify+비정상종료 ──
write_stamp() {
  local name="$1" tmp
  mkdir -p "$STAMP_DIR" || return 1
  tmp="$(mktemp "$STAMP_DIR/.$name.XXXXXX")" || return 1
  if ! date +%s > "$tmp"; then rm -f "$tmp"; return 1; fi
  mv -f "$tmp" "$STAMP_DIR/$name.last" || { rm -f "$tmp"; return 1; }
  return 0
}

# ── 이름 → 실제 잡 실행. 각 분기의 exit 코드를 그대로 반환 ──────
run_job() {
  case "$1" in
    featured-kis)
      # 원본: ExecStart=python3 execution/fetch_featured_data_kis.py (성공 판정 대상)
      #       ExecStartPost=-python3 execution/enrich_newhigh_themes.py ('-' = 비정상 EXIT 무시)
      "$PY" execution/fetch_featured_data_kis.py || return $?
      "$PY" execution/enrich_newhigh_themes.py || true
      ;;
    etf-collect|etf-collect-retry)
      # 원본: 두 타이머 모두 etf-collect.service(run_etf_collect.sh) 트리거.
      #       collect_etf_daily.py 는 재개형(ok>=1000이면 idempotent no-op)이라 재시도 안전.
      /bin/bash scripts/run_etf_collect.sh || return $?
      ;;
    landing-highlights)   /bin/bash scripts/run_landing_highlights.sh || return $? ;;
    etf-active-alert)     /bin/bash scripts/run_etf_active_alert.sh   || return $? ;;
    kodex-sectors)        /bin/bash scripts/run_kodex_sectors.sh      || return $? ;;
    earnings-bot)         "$PY" -m execution.earnings_bot.runner       || return $? ;;
    update-stock-master)  /bin/bash scripts/run_update_stock_master.sh || return $? ;;
    *)
      echo "[run_timer_job] 알 수 없는 잡: $1" >&2
      return 64
      ;;
  esac
  return 0
}

# ── 타임아웃 워치독 ─────────────────────────────────────────────
#   macOS 엔 coreutils 'timeout' 이 없음 → bash monitor mode 로 잡을 자체 프로세스 그룹에
#   넣고, 워치독이 timeout 초과 시 그룹 전체에 TERM → 10초 유예 → KILL 을 보낸다.
#   그룹 kill 이라 python 손자 프로세스까지 확실히 정리된다. 타임아웃이면 124 반환.
run_with_timeout() {
  local timeout_s="$1" name="$2"
  local flag; flag="$(mktemp "${TMPDIR:-/tmp}/rtj.XXXXXX")"; rm -f "$flag"

  set -m                                  # 이후 background 잡은 각자 프로세스 그룹 리더가 됨
  ( run_job "$name" ) &
  local job_pid=$!
  (
    sleep "$timeout_s"
    : > "$flag"                           # 타임아웃 발생 표식
    kill -TERM -"$job_pid" 2>/dev/null || kill -TERM "$job_pid" 2>/dev/null
    sleep 10
    kill -KILL -"$job_pid" 2>/dev/null || kill -KILL "$job_pid" 2>/dev/null
  ) &
  local watch_pid=$!
  set +m

  wait "$job_pid" 2>/dev/null             # 잡이 실제로 죽을 때까지(TERM/KILL 포함) 블록
  local rc=$?

  # 잡 종료 → 워치독(및 그 sleep) 그룹째 취소
  kill -TERM -"$watch_pid" 2>/dev/null || kill -TERM "$watch_pid" 2>/dev/null
  wait "$watch_pid" 2>/dev/null

  if [ -e "$flag" ]; then
    rm -f "$flag"
    echo "[run_timer_job] $name: TimeoutStartSec(${timeout_s}s) 초과 → 프로세스 그룹 강제 종료" >&2
    return 124
  fi
  rm -f "$flag"
  return "$rc"
}

# ── 실행 ────────────────────────────────────────────────────────
acquire_lock "$NAME"
case $? in
  0) : ;;   # 획득
  2) echo "[run_timer_job] $NAME: 이미 다른 인스턴스가 실행 중 → 스킵" >&2; exit 0 ;;
esac

load_env "$REPO/.env"

run_with_timeout "$(job_timeout_seconds "$NAME")" "$NAME"
rc=$?

if [ "$rc" -eq 0 ]; then
  if ! write_stamp "$NAME"; then
    # 잡은 성공했으나 stamp 기록 실패 → 조용히 넘기지 않고 알림 + 비정상 종료(인터페이스 1).
    echo "[run_timer_job] $NAME: stamp 기록 실패 → notify + 비정상 종료" >&2
    notify_failure "$NAME"
    exit 70   # EX_SOFTWARE: A4 가 성공으로 오판하지 않도록 명시적 실패
  fi
else
  notify_failure "$NAME"
fi

exit "$rc"
