#!/bin/bash
# run_gha_job.sh — launchd GHA-잡 공용 wrapper (Wave 0 / WP-A12, Phase 2 사전 산출물)
#
# GitHub Actions 스케줄 워크플로우 9종을 맥미니(macOS, launchd)로 흡수하기 위한 wrapper.
# timers/run_timer_job.sh 의 패턴(자기 위치 self-locate · 잡별 동시실행 락 · 안전 .env 파서 ·
# 타임아웃 워치독 · 원자적 성공 stamp · 전용 실패 알림)을 **복제**한다.
# ★ timers/run_timer_job.sh 를 참조-실행하거나 수정하지 않는다(소유권 분리) — 패턴만 복사.
#
# GHA 특화 추가분:
#   (1) 실행 커맨드는 각 워크플로우 yml 의 실제 스텝(python 스크립트·인자)에서 도출.
#   (2) push 가 있는 잡은 repo 기존 scripts/safe_commit_push.sh 경유([skip ci] 규칙 그대로).
#   (3) GHA `concurrency: group: wrap-nav-pipeline` 공유 그룹 → 맥미니 내 **공유 파이프라인 락**으로 대체
#       (create_dashboard.py 의 동시 HTML 재생성·동시 push 를 직렬화. GHA_MIGRATION_PLAN 절차 3).
#   (4) FRED/ECOS/KOFIA/KRX 는 원본과 동일하게 API 키 미설정 시 **graceful skip(exit 0)**.
#
# 사용법:  run_gha_job.sh <이름>
#   <이름> ∈ gha-fred | gha-universe | gha-ecos | gha-kofia | gha-krx-valuation
#           | gha-disclosures | gha-crawl | gha-earnings-calendar-sync | gha-finalize-orders
#
# 동작:
#   1. self-locate 로 REPO 결정(launchd/gha/ → repo 루트). 별도 사본 없음(배포 레이아웃 계약).
#   2. 잡 이름별 락 획득(mkdir, stale 는 rename 회수) — 중복 실행의 단일 방어선(인터페이스 1-1).
#      이미 살아있는 인스턴스가 있으면 조용히 스킵(exit 0).
#   3. .env 안전 파서(CONTRACT v3) 로드.
#   4. wrap-nav-pipeline 소속 잡이면 공유 파이프라인 락을 **대기 획득**(GHA concurrency 대체).
#   5. 잡별 TimeoutStartSec 워치독 하에 실행.
#   6. 성공(exit 0)  → stamps/<이름>.last 원자적 기록(mktemp+mv). ★기록 실패 시 notify + 비정상 종료(인터페이스 1).
#   7. 실패(exit≠0/타임아웃) → notify_sisyphe_failure.sh <이름> 호출 후 원래 exit 코드 유지, stamp 미기록.

set -u

NAME="${1:?usage: run_gha_job.sh <name>}"

# ── REPO self-locate (배포 레이아웃: __REPO__/launchd/gha/run_gha_job.sh) ──
#   이 파일은 항상 repo 의 launchd/gha/ 아래에 있으므로, 두 단계 상위가 repo 루트다.
#   토큰(__REPO__) 렌더 불필요 → 이중 사본/드리프트 없음(CONTRACT 배포 레이아웃).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
PY="$REPO/venv/bin/python3"           # 결정 5: pyenv 3.10.12 기반 venv
STAMP_DIR="$REPO/logs/launchd/stamps"
LOCK_ROOT="$REPO/logs/launchd/locks"
PIPELINE_LOCK="$LOCK_ROOT/wrap-nav-pipeline.lock"   # GHA concurrency 그룹 대체 공유 락

# 잡의 작업 디렉토리 = repo 루트 (원본 GHA runner 의 checkout 루트 대응)
cd "$REPO" || { echo "[run_gha_job] cd $REPO 실패" >&2; exit 1; }

# venv 를 PATH 최상단에 → safe_commit_push.sh 등 헬퍼 안의 'python3'(PATH 의존)도 venv 로 해석.
export PATH="$REPO/venv/bin:$PATH"

# 원본 GHA 는 각 스텝에 TZ=Asia/Seoul 을 명시했다. 맥미니 시스템 TZ 는 이미 Asia/Seoul(결정 10)이나
# 파이썬 로컬시각 의존 스크립트의 파이티(parity)를 위해 방어적으로 export(무해).
export TZ="${TZ:-Asia/Seoul}"

# ── 락 해제 (per-job + pipeline, 정상/실패/타임아웃 어느 종료 경로든) ──
#   ★소유권 확인 삭제 (Wave 0 확정 패턴 = system/catchup_runner.sh:96 lock_release 이식):
#   락 dir 의 pid 파일이 아직 우리($$)를 가리킬 때만 삭제한다. 우리 락이 stale 로 오인돼 타 인스턴스에
#   rename-회수·재획득된 경우(같은 경로에 새 홀더의 pid 기록됨), 우리 종료 트랩의 무조건 rm -rf 가 남의
#   락을 지우는 사고를 막는 근본 방어선. per-job 락과 공유 pipeline 락 둘 다 동일 적용.
JOB_LOCK_HELD=""
PIPELINE_HELD=""
release_one_lock() {  # $1=락 dir. pid 파일이 아직 $$ 일 때만 삭제(소유권 확인).
  local lock="$1"
  [ -n "$lock" ] || return 0
  [ "$(cat "$lock/pid" 2>/dev/null)" = "$$" ] && rm -rf "$lock"
}
release_locks() {
  release_one_lock "${JOB_LOCK_HELD:-}"
  release_one_lock "${PIPELINE_HELD:-}"
}
trap release_locks EXIT

read_holder() {  # $1=lock dir. pid 를 최대 3회(0.2s 간격) 재시도로 읽어 갓생성 창을 흡수. 실패 시 rc≠0.
  local lock="$1" tries=0 h=""
  while [ "$tries" -lt 3 ]; do
    [ -f "$lock/pid" ] && h="$(cat "$lock/pid" 2>/dev/null)"
    [ -n "$h" ] && { printf '%s' "$h"; return 0; }
    tries=$((tries+1)); sleep 0.2
  done
  return 1
}

# 락 디렉토리 1회 획득 시도. rc 0=획득(호출부가 *_HELD 설정), 1=살아있는 홀더가 점유(스킵/대기).
# stale(죽은/orphan 홀더) 은 rename 방식으로 배타 회수(rm -rf 후 mkdir 재시도식 TOCTOU 금지).
try_acquire() {
  local lock="$1" holder claimed h2
  mkdir -p "$LOCK_ROOT"
  if mkdir "$lock" 2>/dev/null; then
    echo $$ > "$lock/pid"; return 0
  fi
  if holder="$(read_holder "$lock")"; then
    if kill -0 "$holder" 2>/dev/null; then return 1; fi
  fi
  claimed="$lock.reclaim.$$.$RANDOM"
  if mv "$lock" "$claimed" 2>/dev/null; then
    h2=""
    [ -f "$claimed/pid" ] && h2="$(cat "$claimed/pid" 2>/dev/null)"
    if [ -n "$h2" ] && kill -0 "$h2" 2>/dev/null; then
      mv "$claimed" "$lock" 2>/dev/null || rm -rf "$claimed"
      return 1
    fi
    rm -rf "$claimed"
    if mkdir "$lock" 2>/dev/null; then
      echo $$ > "$lock/pid"; return 0
    fi
    return 1
  fi
  return 1
}

acquire_job_lock() {  # rc 0=획득, 2=이미 실행 중(스킵)
  if try_acquire "$LOCK_ROOT/$1.lock"; then JOB_LOCK_HELD="$LOCK_ROOT/$1.lock"; return 0; fi
  return 2
}

# ── 공유 파이프라인 락 (GHA concurrency: wrap-nav-pipeline, cancel-in-progress:false 대체) ──
#   GHA 는 같은 그룹의 두 번째 run 을 취소하지 않고 큐잉했다 → 여기서도 스킵이 아니라 **대기 획득**.
#   단일 워킹트리에서 create_dashboard.py 의 HTML 동시 재생성/동시 push 를 직렬화하는 게 목적.
#   상한(cap) 초과 시 rc 1 → 호출부가 notify + 비정상 종료(데이터 공백은 dispatch/캐치업으로 복구).
acquire_pipeline_lock() {
  local waited=0 cap="${PIPELINE_WAIT_CAP:-3600}" step=5
  while :; do
    if try_acquire "$PIPELINE_LOCK"; then PIPELINE_HELD="$PIPELINE_LOCK"; return 0; fi
    [ "$waited" -ge "$cap" ] && return 1
    sleep "$step"; waited=$((waited+step))
  done
}

# wrap-nav-pipeline concurrency 그룹 소속 판정(원본 yml 에 `group: wrap-nav-pipeline` 있는 잡).
#   포함: fred/universe/ecos/kofia/krx-valuation/crawl/finalize-orders (7종)
#   제외: disclosures(concurrency 블록 없음)·earnings-calendar-sync(concurrency 없음, git push 없음)
is_pipeline_job() {
  case "$1" in
    gha-fred|gha-universe|gha-ecos|gha-kofia|gha-krx-valuation|gha-crawl|gha-finalize-orders|gha-taiwan-revenue) return 0 ;;
    *) return 1 ;;
  esac
}

# ── .env 안전 로드 (CONTRACT v3, timers wrapper 와 동일 파서) ─────
#   systemd EnvironmentFile 대체. 값 내 공백·&·$()·backtick·JSON 을 절대 쉘 해석하지 않는다.
#   행별 첫 '=' 로 KEY/VALUE 분리 → KEY 검증(^[A-Za-z_][A-Za-z0-9_]*$) → export KEY=VALUE(확장 없음).
#   VALUE 양끝을 감싼 동일 따옴표 한 쌍("..." 또는 '...')만 제거(systemd 등가). 내부 따옴표는 보존.
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
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    case "$key" in ''|[0-9]*) continue ;; esac
    stripped="${key//[A-Za-z0-9_]/}"
    [ -z "$stripped" ] || continue
    case "$value" in
      \"*\") value="${value#\"}"; value="${value%\"}" ;;
      \'*\') value="${value#\'}"; value="${value%\'}" ;;
    esac
    export "$key=$value"
  done < "$env_file"
}

# ── 잡별 TimeoutStartSec (초 단위) ──────────────────────────────
#   ★원본 GHA yml 에는 timeout-minutes 지정이 없어 GHA 기본 360분이 적용됐다.
#   워치독용으로는 무의미하므로 잡 성격에 맞춘 보수적 추정치를 부여(Phase 2 실측 후 조정).
job_timeout_seconds() {
  case "$1" in
    gha-fred)                    echo 900  ;;   # API fetch + dashboard + push (~15min)
    gha-universe)                echo 1800 ;;   # yfinance 다종목 fetch (~30min)
    gha-ecos)                    echo 900  ;;
    gha-kofia)                   echo 900  ;;
    gha-krx-valuation)           echo 900  ;;   # pykrx 로그인 + fetch
    gha-disclosures)             echo 900  ;;   # DART + KIND fetch
    gha-crawl)                   echo 3600 ;;   # 대형 파이프라인(백필·크롤·차트·SEIBro selenium) ~60min
    gha-earnings-calendar-sync)  echo 900  ;;   # finnhub + Google Calendar sync
    gha-finalize-orders)         echo 1800 ;;   # finalize + calc_wrap_nav + dashboard + push
    gha-taiwan-revenue)          echo 1800 ;;   # FinMind 53종목 + crosscheck + dashboard
    *)                           echo 1800 ;;   # 미지정 안전 기본
  esac
}

# ── 실패 알림 (systemd OnFailure 대응) ─────────────────────────
#   GHA 잡 9종 전부 전용 분기가 없어 notify_sisyphe_failure.sh 의 generic '*' 분기로 빠진다.
#   (알림은 정상 발송되나 안내 커맨드가 journalctl 이라 launchd 환경엔 부적합 → README 플래그 참조.)
notify_failure() {
  "$REPO/scripts/notify_sisyphe_failure.sh" "$1" || true
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

# ── heartbeat 방출 (CONTRACT 인터페이스 4 — Phase 2 워치독 감시 보조) ──────────
#   성공 stamp 직후, repo 루트 heartbeats.json 에 {"<잡>": <epoch>} 를 upsert(원자적)하고
#   그 파일만 safe_commit_push 로 [skip ci] push. 소비자 = GHA 잔류 워치독
#   (check_data_freshness heartbeat 나이 감시) — 산출물이 repo 밖(Google Calendar)이거나
#   비시계열이라 신선도가 못 잡는 잡의 '비실행'을 커버한다. Wave 1부터 전 잡이 방출해
#   감시 커버가 이관 즉시 시작된다(엔트리 없는 잡은 소비자가 침묵).
#   ★heartbeat 는 감시 보조 — mktemp/upsert/mv/push 어느 단계 실패도 잡 결과(rc)에 번지지
#     않고 경고 로그만 남긴다(다음 성공 방출이 자연 회복). venv python 으로 JSON 병합(가장 견고).
emit_heartbeat() {
  local name="$1" hb="$REPO/heartbeats.json" tmp now
  now="$(date +%s)"
  tmp="$(mktemp "$REPO/.heartbeats.XXXXXX")" || {
    echo "[run_gha_job] $name: heartbeat mktemp 실패 → 스킵(감시 보조)" >&2; return 0
  }
  # 기존 heartbeats.json 병합(없거나 파손이면 새 dict). 결과를 tmp 로 출력 → 원자적 mv.
  if "$PY" - "$hb" "$name" "$now" > "$tmp" <<'PYHB'
import json, sys
path, job, now = sys.argv[1], sys.argv[2], int(sys.argv[3])
try:
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        data = {}
except Exception:
    data = {}
data[job] = now
json.dump(data, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
sys.stdout.write('\n')
PYHB
  then
    if mv -f "$tmp" "$hb"; then
      /bin/bash scripts/safe_commit_push.sh -m "heartbeat: $name [skip ci]" -- heartbeats.json \
        || echo "[run_gha_job] $name: heartbeat push 실패 → 경고만(다음 성공 방출 시 회복)" >&2
    else
      rm -f "$tmp"; echo "[run_gha_job] $name: heartbeat mv 실패 → 스킵(감시 보조)" >&2
    fi
  else
    rm -f "$tmp"; echo "[run_gha_job] $name: heartbeat JSON upsert 실패 → 스킵(감시 보조)" >&2
  fi
  return 0
}

# ── 이름 → 실제 잡 실행. 각 분기의 exit 코드를 그대로 반환 ──────
#   실행 커맨드는 대응 워크플로우 yml 의 스텝에서 그대로 도출. `|| echo`(tolerated) 스텝은
#   원본과 동일하게 실패해도 계속 진행하고, 그 외 스텝은 실패 시 잡 실패로 전파한다.
run_job() {
  case "$1" in
    # ── daily_fred.yml (Wave 1) ───────────────────────────────
    gha-fred)
      if [ -z "${FRED_API_KEY:-}" ]; then
        echo "[gha-fred] FRED_API_KEY 미설정 → graceful skip (no failure)" >&2; return 0
      fi
      "$PY" execution/fetch_fred_data.py || return $?
      "$PY" execution/create_dashboard.py || return $?
      /bin/bash scripts/safe_commit_push.sh \
        -m "Auto-update: FRED US macro series [skip ci]" \
        -- dataset.csv market.html || return $?
      ;;

    # ── daily_universe.yml (Wave 1) ───────────────────────────
    gha-universe)
      "$PY" execution/fetch_universe.py || return $?
      /bin/bash scripts/safe_commit_push.sh \
        -m "Auto: Universe data update [skip ci]" \
        -- universe.json universe_history.json || return $?
      ;;

    # ── daily_ecos.yml (Wave 1) ───────────────────────────────
    gha-ecos)
      if [ -z "${ECOS_API_KEY:-}" ]; then
        echo "[gha-ecos] ECOS_API_KEY 미설정 → graceful skip (no failure)" >&2; return 0
      fi
      "$PY" execution/fetch_ecos_data.py || return $?
      "$PY" execution/create_dashboard.py || return $?
      /bin/bash scripts/safe_commit_push.sh \
        -m "Auto-update: ECOS BOK series [skip ci]" \
        -- dataset.csv market.html || return $?
      ;;

    # ── daily_kofia.yml (Wave 1) ──────────────────────────────
    gha-kofia)
      if [ -z "${DATA_GO_KR_API_KEY:-}" ]; then
        echo "[gha-kofia] DATA_GO_KR_API_KEY 미설정 → graceful skip (no failure)" >&2; return 0
      fi
      "$PY" execution/fetch_kofia_stats.py || return $?
      "$PY" execution/fetch_nps_fund.py || return $?   # 국민연금 적립금(내부 graceful skip)
      "$PY" execution/create_dashboard.py || return $?
      /bin/bash scripts/safe_commit_push.sh \
        -m "Auto-update: KOFIA deposit/credit stats [skip ci]" \
        -- kofia_stats.json index.html dataset.csv market.html || return $?
      ;;

    # ── daily_krx_valuation.yml (Wave 2) ──────────────────────
    gha-krx-valuation)
      if [ -z "${KRX_ID:-}" ] || [ -z "${KRX_PW:-}" ]; then
        echo "[gha-krx-valuation] KRX_ID/KRX_PW 미설정 → graceful skip (no failure)" >&2; return 0
      fi
      "$PY" execution/fetch_krx_valuation.py || return $?
      "$PY" execution/create_dashboard.py || return $?
      /bin/bash scripts/safe_commit_push.sh \
        -m "Auto-update: KRX index valuation [skip ci]" \
        -- dataset.csv market.html || return $?
      ;;

    # ── daily_disclosures.yml (Wave 2) ────────────────────────
    #   원본은 git-auto-commit-action(file_pattern) 사용 → 맥미니에선 safe_commit_push 로 통일.
    #   concurrency 그룹 밖이나 push 레이스 자가복구를 위해 동일 스크립트 경유.
    gha-disclosures)
      "$PY" execution/fetch_disclosures.py || return $?
      "$PY" execution/fetch_kind_disclosures.py || return $?
      /bin/bash scripts/safe_commit_push.sh \
        -m "Auto: DART + KIND disclosures update [skip ci]" \
        -- disclosures.json corp_codes.json || return $?
      ;;

    # ── daily_crawl.yml (스케줄분, Wave 2) ────────────────────
    #   ★ font-nanum·Chrome 은 GHA 스텝(apt/setup-chrome)이 매 run 설치했으나, 맥미니에선
    #     부트스트랩(A5/A6)이 미리 설치한 것을 전제(여기서 재설치하지 않음). SEIBro selenium 은
    #     Chrome 필요 → 미설치면 fetch_seibro_data.py 가 실패하나 tolerated(|| echo)라 계속 진행.
    gha-crawl)
      "$PY" execution/backfill_yfinance_history.py || return $?
      "$PY" execution/fetch_monthly_returns.py || return $?
      "$PY" execution/fetch_index_returns.py || return $?
      "$PY" execution/import_memory_data.py || return $?
      "$PY" execution/market_crawler.py || return $?
      "$PY" calculate_wrap_nav.py || return $?
      "$PY" calculate_returns.py || return $?
      "$PY" execution/fetch_danawa_price.py || echo "다나와 수집 실패 (계속 진행)"
      rm -f charts/*.png
      "$PY" execution/draw_charts.py || return $?
      "$PY" execution/fetch_krx_data.py || echo "KRX 데이터 수집 실패 (계속 진행)"
      "$PY" execution/fetch_krx_foreign.py || echo "외국인 보유비중 수집 실패 (계속 진행)"
      "$PY" execution/fetch_deposit_data.py || echo "예탁금 수집 실패 (계속 진행)"
      "$PY" execution/draw_wrap_charts.py || return $?
      "$PY" execution/create_portfolio_tables.py || return $?
      "$PY" execution/create_contribution_data.py || echo "기여도 데이터 생성 실패 (계속 진행)"
      "$PY" execution/fetch_seibro_data.py || echo "SEIBro 수집 실패 (계속 진행)"
      "$PY" execution/create_dashboard.py || return $?
      /bin/bash scripts/safe_commit_push.sh \
        -m "Auto-update: Market data and dashboard [skip ci]" \
        --xlsx-conflict bail \
        -- dataset.csv charts/*.png index.html market.html wrap.html universe.html seibro.html \
           featured.html featured_data.json portfolio_data.json contribution_data.json \
           Wrap_NAV.xlsx kodex_sectors.json seibro_tickers.json monthly_returns.json \
           index_returns.json index_history.json || return $?
      ;;

    # ── earnings_calendar_sync.yml (Wave 3, ★VM cron 이중실행 정리) ──
    #   git push 없음(Google Calendar/Sheet 직접 기록). 파이썬 스크립트만 실행.
    gha-earnings-calendar-sync)
      "$PY" execution/earnings_calendar_sync.py || return $?
      ;;

    # ── finalize_orders.yml (Wave 3, 최고 민감 — 최후 이관) ──
    #   --xlsx-conflict fail: 드롭된 커밋이 finalize 된 NEW/AUM 을 소리없이 잃으므로 빨간 실패로.
    gha-finalize-orders)
      "$PY" execution/finalize_pending_orders.py || return $?
      "$PY" execution/finalize_pending_aum.py || return $?
      "$PY" calculate_wrap_nav.py || echo "calculate_wrap_nav 실패 (계속 진행)"
      "$PY" calculate_returns.py || echo "calculate_returns 실패 (계속 진행)"
      "$PY" execution/create_portfolio_tables.py || return $?
      "$PY" execution/create_dashboard.py || return $?
      /bin/bash scripts/safe_commit_push.sh \
        -m "Auto: finalize ORDER/AUM + Dashboard regenerate [skip ci]" \
        --xlsx-conflict fail \
        -- Wrap_NAV.xlsx orders/pending_orders.json orders/aum_pending.json portfolio_data.json \
           index.html market.html wrap.html universe.html seibro.html featured.html hotels.html || return $?
      ;;
    gha-taiwan-revenue)
      # 원본 daily_taiwan_revenue.yml 3스텝. 토큰 미설정 시 익명(300req/hr) 동작 — skip 없음.
      "$PY" execution/fetch_taiwan_revenue.py || return $?
      "$PY" execution/fetch_taiwan_revenue.py --crosscheck || echo "[gha-taiwan-revenue] crosscheck 실패(tolerated, 로그 전용)" >&2
      "$PY" execution/create_dashboard.py || return $?
      /bin/bash scripts/safe_commit_push.sh \
        -m "Auto-update: Taiwan monthly revenue [skip ci]" \
        -- taiwan_revenue.csv market.html || return $?
      ;;

    *)
      echo "[run_gha_job] 알 수 없는 잡: $1" >&2
      return 64
      ;;
  esac
  return 0
}

# ── 타임아웃 워치독 (timers wrapper 와 동일 — macOS 엔 coreutils timeout 없음) ──
#   bash monitor mode(set -m)로 잡을 자체 프로세스 그룹에 넣고, 초과 시 그룹 전체에
#   TERM → 10초 유예 → KILL. python 손자 프로세스까지 정리된다. 타임아웃이면 124 반환.
run_with_timeout() {
  local timeout_s="$1" name="$2"
  local flag; flag="$(mktemp "${TMPDIR:-/tmp}/rgj.XXXXXX")"; rm -f "$flag"

  set -m
  ( run_job "$name" ) &
  local job_pid=$!
  (
    sleep "$timeout_s"
    : > "$flag"
    kill -TERM -"$job_pid" 2>/dev/null || kill -TERM "$job_pid" 2>/dev/null
    sleep 10
    kill -KILL -"$job_pid" 2>/dev/null || kill -KILL "$job_pid" 2>/dev/null
  ) &
  local watch_pid=$!
  set +m

  wait "$job_pid" 2>/dev/null
  local rc=$?

  kill -TERM -"$watch_pid" 2>/dev/null || kill -TERM "$watch_pid" 2>/dev/null
  wait "$watch_pid" 2>/dev/null

  if [ -e "$flag" ]; then
    rm -f "$flag"
    echo "[run_gha_job] $name: TimeoutStartSec(${timeout_s}s) 초과 → 프로세스 그룹 강제 종료" >&2
    return 124
  fi
  rm -f "$flag"
  return "$rc"
}

# ── 실행 ────────────────────────────────────────────────────────
acquire_job_lock "$NAME"
case $? in
  0) : ;;
  2) echo "[run_gha_job] $NAME: 이미 다른 인스턴스가 실행 중 → 스킵" >&2; exit 0 ;;
esac

load_env "$REPO/.env"

# wrap-nav-pipeline 소속이면 공유 락 대기 획득(GHA concurrency 대체). 상한 초과 시 실패 처리.
if is_pipeline_job "$NAME"; then
  if ! acquire_pipeline_lock; then
    echo "[run_gha_job] $NAME: wrap-nav-pipeline 락 대기 상한 초과 → notify + 비정상 종료" >&2
    notify_failure "$NAME"
    exit 75   # EX_TEMPFAIL: 일시적 경합 실패(dispatch/캐치업 재시도 대상)
  fi
fi

run_with_timeout "$(job_timeout_seconds "$NAME")" "$NAME"
rc=$?

if [ "$rc" -eq 0 ]; then
  if ! write_stamp "$NAME"; then
    echo "[run_gha_job] $NAME: stamp 기록 실패 → notify + 비정상 종료" >&2
    notify_failure "$NAME"
    exit 70   # EX_SOFTWARE: A4 가 성공으로 오판하지 않도록 명시적 실패
  fi
  # 성공 stamp 직후 heartbeat 방출(감시 보조). 실패해도 rc 에 번지지 않음(인터페이스 4).
  emit_heartbeat "$NAME"
  # 게시 스냅숏 갱신 (웹서빙 W5) - 실패해도 잡 rc 불변, 다음 성공 게시가 회복
  /bin/bash "$REPO/scripts/publish_snapshot.sh" >> "$REPO/logs/launchd/publish.log" 2>&1 \
    || echo "[run_gha_job] $NAME: publish_snapshot 실패(경고)" >&2
  # gh-pages 게시 (D-수정안 2026-07-12) - 실패해도 잡 rc 불변, 다음 성공 게시가 회복
  /bin/bash "$REPO/scripts/publish_pages.sh" >> "$REPO/logs/launchd/publish_pages.log" 2>&1 \
    || echo "[run_gha_job] $NAME: publish_pages 실패(경고)" >&2
else
  notify_failure "$NAME"
fi

exit "$rc"
