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

# ── 체인 게이트 v2 설정 (기본 OFF — schedule.tsv 4번째 컬럼이 비면 전부 미동작) ──
#   schedule.tsv 는 A2b 가 __REPO__/logs/launchd/schedule.tsv 로 설치(치환본). 여기서는
#   "내 이름 행의 4번째 컬럼(<선행잡>[:<타임아웃HHMM>])"만 읽어 선행 완료를 기다린다.
SCHEDULE_TSV="${SCHEDULE_TSV:-$REPO/logs/launchd/schedule.tsv}"
CHAIN_POLL_SEC="${CHAIN_POLL_SEC:-60}"           # 대기 폴링 간격
CHAIN_DEFAULT_WAIT_SEC="${CHAIN_DEFAULT_WAIT_SEC:-2700}"  # HHMM 미지정 시 대기(45분)
CHAIN_MAX_WAIT_SEC="${CHAIN_MAX_WAIT_SEC:-7200}" # ★절대 대기 상한(120분) — 어떤 계산이든 유계화

# 잡의 작업 디렉토리 = repo 루트 (원본 systemd WorkingDirectory 대응)
cd "$REPO" || { echo "[run_timer_job] cd $REPO 실패" >&2; exit 1; }

# venv 를 PATH 최상단에 → run_*.sh 헬퍼 안의 'python3'(PATH 의존)도 venv 로 해석되게 한다.
export PATH="$REPO/venv/bin:$PATH"

# ── 잡별 동시실행 락 (인터페이스 1-1) ───────────────────────────
#   mkdir(원자적)로 획득, pid 기록. 이미 살아있는 홀더면 스킵. stale 는 rename 으로 배타 회수
#   (rm -rf 후 mkdir 재시도식 TOCTOU 금지 — mv 로 고유 임시명 회수 후 내용 확인·삭제).
LOCK_HELD=""
release_lock() {  # 소유권 확인 삭제(= system/catchup_runner.sh:96 lock_release / gha release_one_lock 이식):
  # 락 dir 의 pid 파일이 아직 우리($$)를 가리킬 때만 삭제. 우리 락이 stale 로 오인돼 타 인스턴스에
  # rename-회수·재획득된 경우(pid 파일이 새 홀더로 바뀜), 무조건 rm -rf 가 남의 락을 지우는 사고를 막는다.
  local lock="${LOCK_HELD:-}"
  [ -n "$lock" ] || return 0
  [ "$(cat "$lock/pid" 2>/dev/null)" = "$$" ] && rm -rf "$lock"
}
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
    send-advisory-emails) echo 300  ;;   # SMTP 5통 여유(신규 60초 폴러)
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
    send-advisory-emails) "$PY" execution/send_advisory_emails.py || return $? ;;
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

# ── 체인 게이트 (v2, 기본 OFF) ──────────────────────────────────
#   schedule.tsv 4번째 컬럼 = <선행잡>[:<타임아웃HHMM(KST)>]. 비어 있으면(3컬럼 현행 포함)
#   게이트 없음 = 현행과 100% 동일. ★락 획득 "전"에 대기 → 대기 중 잡별 락을 점유하지 않는다.
#   신선도 판정: 선행 stamp 가 "오늘(KST 00:00 이후)" 갱신됐는가 = 선행이 오늘 완료됐는가.
#   타임아웃 데드라인: HHMM 을 ★"게이트 시작"이 아니라 tsv 2번째 컬럼(cron)의 예정 발화 HHMM 에 앵커한다.
#     데드라인 HHMM ≥ 예정 발화 HHMM → 발화일(오늘) 그 시각 / 미만 → 익일. 이러면 (a) kodex 23:30←crawl:0030
#     = 익일 00:30, (b) 19:00 잡+1930 인데 19:40 늦은 시작 = 오늘 19:30 이미 경과 → 즉시 timeout+폴백.
#   ★절대 대기 상한 120분: 어떤 계산이든 deadline=min(계산값, 시작+CHAIN_MAX_WAIT_SEC). 오설정·catch-up
#     아침 재발화 등 잔여 경계를 전부 "최대 2시간 후 폴백+notify"로 유계화. 미지정 시 now+기본대기(45분).
#   초과 시 경고+notify 후 ★폴백 실행(스킵 아님) — 선행 지연이 후행 데이터 공백으로 번지지 않게.
#   ★fail-open: HHMM/예정발화 오형식·범위밖, tsv 부재·불가독은 게이트를 무시하고 잡을 정상 실행
#     (오타·환경문제가 수집 중단으로 안 번지게). 빈 4번째 컬럼은 애초에 게이트 없음(현행 동일).
kst_midnight() {  # <now_epoch> → 오늘 00:00 KST epoch (시스템 TZ 무관, 고정 UTC+9)
  echo $(( ( ($1 + 32400) / 86400 ) * 86400 - 32400 ))
}
read_stamp_epoch() {  # <file> → 정수 epoch, 없거나 비정수면 0 (엄격)
  local v=""
  [ -f "$1" ] && v="$(head -n1 "$1" 2>/dev/null)"
  v="${v#"${v%%[![:space:]]*}"}"; v="${v%"${v##*[![:space:]]}"}"
  case "$v" in ''|*[!0-9]*) echo 0 ;; *) echo "$v" ;; esac
}
chain_lookup() {  # <name> → 그 행의 "<cron(2번째)>\t<체인(4번째)>" 출력(없으면 빈 문자열). 3컬럼 하위호환.
  # ★무음 fail-open: tsv 부재·불가독·행 부재 → 빈 출력(게이트 없음, 기존 플로우 보존).
  #   ‘성공 경로에서 tsv 를 매 발화 읽는 것’은 수용된 신규 동작(설계 §4). 읽기 오류는 조용히 넘긴다.
  [ -f "$SCHEDULE_TSV" ] && [ -r "$SCHEDULE_TSV" ] || return 0
  local c1 c2 c3 c4
  while IFS=$'\t' read -r c1 c2 c3 c4 || [ -n "$c1" ]; do
    case "$c1" in ''|\#*) continue ;; esac
    [ "$c1" = "$1" ] && { printf '%s\t%s' "$c2" "${c4:-}"; return 0; }
  done < "$SCHEDULE_TSV" 2>/dev/null
  return 0
}
wait_for_chain() {  # <name> — 4번째 컬럼이 있으면 선행 stamp 신선까지 대기 (락 획득 전 호출)
  local name="$1" row cron spec pred hhmm now today0 deadline stamp cap
  local hh mm dl_min fmin fhour frest fire_min
  row="$(chain_lookup "$name")"
  cron="${row%%$'\t'*}"; spec="${row#*$'\t'}"
  [ -n "$spec" ] || return 0                    # ★기본 OFF: 컬럼 비면/무매칭 즉시 통과(현행 100% 동일)
  pred="${spec%%:*}"
  case "$spec" in *:*) hhmm="${spec#*:}" ;; *) hhmm="" ;; esac
  [ -n "$pred" ] || return 0

  now="$(date +%s)"; today0="$(kst_midnight "$now")"
  cap=$(( now + CHAIN_MAX_WAIT_SEC ))           # ★절대 대기 상한(시작+120분)

  if [ -z "$hhmm" ]; then
    deadline=$(( now + CHAIN_DEFAULT_WAIT_SEC ))            # 타임아웃 미지정 → 기본 대기
  else
    # HHMM 검증. 4자리·HH<24·MM<60 아니면 ★fail-open(게이트 무시+경고 1줄, 잡 정상 실행) — 오타 유계화.
    case "$hhmm" in
      [0-9][0-9][0-9][0-9]) : ;;
      *) echo "[run_timer_job] $name: 체인 타임아웃 '$hhmm' 형식오류(HHMM 4자리 아님) → 게이트 무시, 정상 실행" >&2
         return 0 ;;
    esac
    hh=$((10#${hhmm%??})); mm=$((10#${hhmm#??}))
    if [ "$hh" -ge 24 ] || [ "$mm" -ge 60 ]; then
      echo "[run_timer_job] $name: 체인 타임아웃 '$hhmm' 범위밖(HH<24·MM<60) → 게이트 무시, 정상 실행" >&2
      return 0
    fi
    dl_min=$(( hh*60 + mm ))
    # ★데드라인 앵커 = "게이트 시작"이 아니라 tsv 2번째 컬럼(cron)의 예정 발화 HHMM(분·시).
    #   늦은 시작(launchd 지연/수면해제/catch-up)이 오늘의 정상 데드라인을 익일로 오판하지 않게 한다.
    read -r fmin fhour frest <<< "$cron"
    case "${fmin:-}" in ''|*[!0-9]*) fmin="" ;; esac
    case "${fhour:-}" in ''|*[!0-9]*) fhour="" ;; esac
    if [ -z "$fmin" ] || [ -z "$fhour" ]; then
      echo "[run_timer_job] $name: 예정 발화 HHMM 파싱 불가(cron='$cron') → 게이트 무시, 정상 실행" >&2
      return 0
    fi
    fmin=$((10#$fmin)); fhour=$((10#$fhour))
    if [ "$fmin" -ge 60 ] || [ "$fhour" -ge 24 ]; then
      echo "[run_timer_job] $name: 예정 발화 범위밖(cron='$cron') → 게이트 무시, 정상 실행" >&2
      return 0
    fi
    fire_min=$(( fhour*60 + fmin ))
    # 데드라인 HHMM ≥ 예정 발화 HHMM → 발화일(오늘) 그 시각 / 미만 → 익일.
    if [ "$dl_min" -ge "$fire_min" ]; then
      deadline=$(( today0 + dl_min*60 ))
    else
      deadline=$(( today0 + 86400 + dl_min*60 ))
    fi
  fi

  # ★상한 클램프: min(데드라인, 시작+120분). 오설정·catch-up 재발화 등 잔여 경계를 전부 유계화.
  [ "$deadline" -gt "$cap" ] && deadline="$cap"

  echo "[run_timer_job] $name: 체인 대기 시작 pred='$pred' deadline=$deadline (poll ${CHAIN_POLL_SEC}s)" >&2
  while : ; do
    now="$(date +%s)"; today0="$(kst_midnight "$now")"
    stamp="$(read_stamp_epoch "$STAMP_DIR/$pred.last")"
    if [ "$stamp" -ge "$today0" ]; then
      echo "[run_timer_job] $name: 선행 '$pred' 오늘 완료 확인(stamp=$stamp) → 진행" >&2
      return 0
    fi
    if [ "$now" -ge "$deadline" ]; then
      echo "[run_timer_job] $name: 선행 '$pred' 미완료·타임아웃(deadline=$deadline) → 경고+notify 후 폴백 실행" >&2
      load_env "$REPO/.env"                     # notify 스크립트가 .env(토큰) 필요할 수 있어 선로드(멱등)
      "$REPO/scripts/notify_sisyphe_failure.sh" "$name: chain-timeout(pred=$pred)" || true
      return 0                                  # ★폴백: 스킵 아님, 그대로 실행
    fi
    sleep "$CHAIN_POLL_SEC"
  done
}

# ── 실행 ────────────────────────────────────────────────────────
wait_for_chain "$NAME"      # v2 체인 게이트(기본 OFF, 락 획득 전). 4번째 컬럼 비면 즉시 반환.

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
  # 게시 스냅숏 갱신 (웹서빙 W5) - 실패해도 잡 rc 불변
  /bin/bash "$REPO/scripts/publish_snapshot.sh" >> "$REPO/logs/launchd/publish.log" 2>&1 \
    || echo "[run_timer_job] $NAME: publish_snapshot 실패(경고)" >&2
  # gh-pages 게시 (D-수정안 2026-07-12) - 실패해도 잡 rc 불변, 다음 성공 게시가 회복
  /bin/bash "$REPO/scripts/publish_pages.sh" >> "$REPO/logs/launchd/publish_pages.log" 2>&1 \
    || echo "[run_timer_job] $NAME: publish_pages 실패(경고)" >&2
else
  notify_failure "$NAME"
fi

exit "$rc"
