#!/bin/bash
#
# run_bot.sh — 공용 launchd 봇 wrapper (Oracle VM systemd → 맥미니 launchd 이전, WP-A2a)
#
# plist 의 ProgramArguments 는 항상 이 wrapper 를 경유한다:
#
#   ProgramArguments = [ run_bot.sh, <봇이름>, <python>, <스크립트...> ]
#   예) run_bot.sh sisyphe-bot /Users/x/.../venv/bin/python3 execution/sisyphe_bot.py
#
# 책임(codex 리뷰 v1 반영):
#   1) .env 를 안전 파서로 로드(set -a source 금지 — 값 내 공백·&·$()·backtick·# 미실행).
#   2) 부팅 직후 네트워크 대기(api.telegram.org:443, 최대 120초·5초 간격, 실패해도 진행).
#   3) 봇을 exec 가 아닌 child 로 실행하고 종료코드를 캡처.
#      - 정상 실패(exit 1..127 등, stop 시그널 제외) → notify_sisyphe_failure.sh <봇이름> 호출
#        후 sleep 10(RestartSec=10 등가) → 동일 코드로 종료. launchd KeepAlive 가 재기동.
#      - SIGTERM/SIGINT(rc 143/130)=launchd 의도적 중지 → 알림/지연 없음(systemd clean stop 대응).
#   4) 매 기동 시각을 starts/<봇이름>.log 에 원자적으로 기록(최근 10줄) → A4 crash_watcher 가
#      크래시 루프 억제/에스컬레이션에 사용. wrapper 자신은 건별 알림+지연만 담당.

if [ "$#" -lt 2 ]; then
    echo "usage: $0 <bot-name> <command...>" >&2
    exit 64
fi

NAME="$1"
shift

# 이 스크립트는 $REPO/launchd/bots/run_bot.sh 에 위치한다 → 두 단계 상위가 $REPO.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"

# --- 안전 .env 파서 (CONTRACT v3) ------------------------------------------
# 행별 첫 '=' 기준 KEY/VALUE 분리. KEY 형식 검증 후에만 export. 쉘 확장 없음
# — 변수에 담아 export 하므로 값 내 $()·backtick·&·# 이 실행되지 않는다.
# 값 양끝을 감싼 '동일' 따옴표 한 쌍("..." 또는 '...')만 제거(systemd EnvironmentFile 등가),
# 내부 따옴표·이스케이프는 그대로 보존.
# ★VM .env 에 double-quote 값 1건 실존(예: GOOGLE_SERVICE_ACCOUNT_KEY JSON 한 줄) — 따옴표째
#   주입되면 해당 키가 파손되므로 반드시 양끝 " 제거. 첫 '=' 분리라 값 내부 '='·$·백틱은 보존.
load_env() {
    local env_file="$1" line key val
    [ -r "$env_file" ] || return 0
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line%$'\r'}"                                  # CRLF 대비
        line="${line#"${line%%[![:space:]]*}"}"               # ltrim
        case "$line" in ''|'#'*) continue ;; esac             # 빈 줄/주석
        line="${line#export }"                                # 선택적 export 접두
        case "$line" in *=*) ;; *) continue ;; esac
        key="${line%%=*}"                                     # 첫 '=' 앞
        val="${line#*=}"                                      # 첫 '=' 뒤(값 내 '=' 보존)
        key="${key%"${key##*[![:space:]]}"}"                  # key rtrim
        [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue  # KEY 형식 검증
        case "$val" in                                        # 양끝 한 겹 따옴표 제거
            \"*\") val="${val#\"}"; val="${val%\"}" ;;
            \'*\') val="${val#\'}"; val="${val%\'}" ;;
        esac
        export "$key=$val"
    done < "$env_file"
}

# --- 네트워크 대기 (best-effort) -------------------------------------------
# 부팅 직후 네트워크 미준비 상태에서 봇이 텔레그램에 붙지 못하는 초기 루프 완화.
# 최대 120초(5초 간격) 폴링. 실패해도 진행하여 봇 자체 재시도에 맡긴다.
wait_for_network() {
    local host="api.telegram.org" port=443 waited=0
    while [ "$waited" -lt 120 ]; do
        if (exec 3<>"/dev/tcp/$host/$port") 2>/dev/null; then
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
    done
    return 1
}

# --- 크래시 breadcrumb (원자적: mktemp + mv -f) ----------------------------
# CONTRACT 인터페이스 0: 매 기동 시각을 **epoch 정수(`date +%s`) 한 줄**로 기록(최근 10줄 유지).
# A4 crash_watcher 는 epoch 정수 행만 읽고 나머지는 무시하므로 반드시 순수 정수여야 한다
# (사람이 읽는 날짜 포맷을 쓰면 tr 강제숫자화 시 거대값→영구 오탐). 이전 9줄 + 이번 1줄을
# 임시파일에 쓴 뒤 원자적 rename.
record_start() {
    local dir="$REPO/logs/launchd/starts"
    local log="$dir/$NAME.log" tmp
    mkdir -p "$dir" 2>/dev/null || return 0
    tmp="$(mktemp "$log.XXXXXX" 2>/dev/null)" || return 0
    {
        [ -f "$log" ] && tail -n 9 "$log"
        date +%s
    } > "$tmp" 2>/dev/null && mv -f "$tmp" "$log" 2>/dev/null || rm -f "$tmp" 2>/dev/null
}

# launchd StandardOut/StandardErr 대상 디렉터리 보장(launchd 는 상위를 만들지 않음).
mkdir -p "$REPO/logs/launchd" 2>/dev/null || true

record_start
load_env "$REPO/.env"
wait_for_network || true

# --- 봇 실행 (child + 종료코드 캡처 + 시그널 전달) -------------------------
CHILD=""
forward_term() { [ -n "$CHILD" ] && kill -TERM "$CHILD" 2>/dev/null || true; }
trap forward_term TERM INT

"$@" &
CHILD=$!
wait "$CHILD"
rc=$?
# trap 이 wait 를 깨웠고 child 가 아직 살아있으면 실제 종료까지 재수확.
if kill -0 "$CHILD" 2>/dev/null; then
    wait "$CHILD"
    rc=$?
fi
# child 는 이제 반드시 종료됨 → CHILD 를 비워, 아래 sleep 중 TERM 수신 시 forward_term 이
# 재사용된(다른 프로세스의) PID 에 시그널을 보내지 않도록 한다.
CHILD=""

case "$rc" in
    130|143)
        # 130=SIGINT, 143=SIGTERM = launchd 의도적 중지(bootout/deploy/재부팅).
        # 재기동이 아니라 정지이므로 지연·알림 없이 즉시 종료(SIGKILL 전에 신속 정리).
        ;;
    0)
        # 정상 종료지만 KeepAlive 가 재기동한다 → systemd Restart=always+RestartSec=10 등가로 지연.
        sleep 10
        ;;
    *)
        # 진짜 크래시(예: 파이썬 예외 exit 1) → 건별 알림 + RestartSec=10 등가 지연.
        "$REPO/scripts/notify_sisyphe_failure.sh" "$NAME" >/dev/null 2>&1 || true
        sleep 10
        ;;
esac

exit "$rc"
