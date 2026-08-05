#!/bin/bash
set -euo pipefail
ENV_FILE="${ENV_FILE:-$(cd "$(dirname "$0")/.." && pwd)/.env}"  # self-locate
[ -r "$ENV_FILE" ] && { set -a; source "$ENV_FILE"; set +a; }

# launchd wrapper(run_timer_job.sh notify_failure / 봇 supervision)가 잡 이름을 첫 인자로 호출.
# (구 systemd OnFailure %i 인터페이스 유지 — 2026-07-13 문구를 맥미니 launchd 기준으로 전환)
UNIT="${1:-sisyphe-bot}"
LOG_DIR='~/Antigravity_Market_Dashboard/logs/launchd'

# ─────────────────────────────────────────────────────────────────────────────
# 알림 억제 게이트 (2026-08-05, 사용자 지시: "재시도로 해결되는 건 알람 금지, 최종 실패만")
#
#   G1 연속 실패 게이트 — 곧 자동 재실행되는 잡(다음 실행까지 ≤ GAP_LIMIT)은 1차 실패를
#      침묵하고, 연속 2회째(= 재시도도 실패 = 최종 실패)부터 알린다. 재실행이 먼 잡
#      (일 1회 등)은 종전대로 즉시 알린다 — 24시간 뒤에 알리는 건 알림이 아니므로.
#      다음 실행 간격은 잡의 plist(StartInterval / StartCalendarInterval)에서 그때그때
#      산출한다. 잡 목록을 이 스크립트에 하드코딩하지 않으므로 스케줄이 바뀌어도 안 어긋난다.
#   G2 자동 리셋 — 마지막 실패가 2×간격보다 오래 전이면 그 사이 성공한 것으로 보고 카운터를
#      0으로 되돌린다. 며칠 간격의 산발적 1회 실패가 누적돼 알림이 되는 걸 막는다.
#   G3 버스트 쿨다운 — 알림 발송 후 COOLDOWN(기본 6h) 안의 재실패는 억제하고 횟수만 세어,
#      다음 알림 본문에 "(쿨다운 동안 N회 더 실패)"로 합산 통지한다. 정보는 유실되지 않는다.
#
#   원칙: 게이트 내부 오류는 전부 fail-open(=알림 발송). 노이즈보다 알림 유실이 더 나쁘다.
#   침묵된 실패도 stamp 미기록으로 남아 daily-selfcheck 의 STALE 감시에 그대로 걸린다.
#   테스트: NOTIFY_DRYRUN=1 (텔레그램 미발송, 판정만 출력)
# ─────────────────────────────────────────────────────────────────────────────
JOB_KEY="${UNIT%%:*}"                       # "name: chain-timeout(...)" 형태 대응
GAP_LIMIT="${NOTIFY_GAP_LIMIT:-14400}"      # 4h 이내 재실행 = '재시도 있음'으로 간주
COOLDOWN="${NOTIFY_COOLDOWN_SEC:-21600}"    # 6h
STATE_DIR="${NOTIFY_STATE_DIR:-$(cd "$(dirname "$0")/.." && pwd)/logs/launchd/notify_state}"
SUP_NOTE=""
GATE_NOTE=""

# 다음 자동 재실행까지 남은 초. 산출 불가(상주 봇·plist 없음 등)면 0 → 즉시 알림.
next_run_gap() {
  local plist="/Library/LaunchDaemons/com.antigravity.${JOB_KEY}.plist" si hours h d best now_h
  [ -r "$plist" ] || { echo 0; return; }
  si="$(/usr/libexec/PlistBuddy -c 'Print :StartInterval' "$plist" 2>/dev/null || true)"
  if [ -n "$si" ] && [ "$si" -gt 0 ] 2>/dev/null; then echo "$si"; return; fi
  hours="$(/usr/libexec/PlistBuddy -c 'Print :StartCalendarInterval' "$plist" 2>/dev/null \
           | sed -nE 's/.*Hour = ([0-9]+).*/\1/p' || true)"
  [ -n "$hours" ] || { echo 0; return; }
  now_h="$(date +%H)"; now_h="${now_h#0}"; : "${now_h:=0}"
  best=24
  for h in $hours; do
    h="${h#0}"; : "${h:=0}"
    d=$(( (h - now_h + 24) % 24 )); [ "$d" -eq 0 ] && d=24
    [ "$d" -lt "$best" ] && best="$d"
  done
  echo $(( best * 3600 ))
}

gate_decide() {   # rc 0 = 발송, rc 1 = 억제
  local now gap need last_fail fails last_alert sup line
  mkdir -p "$STATE_DIR" 2>/dev/null || return 0        # 상태 못 쓰면 fail-open
  now="$(date +%s)"
  gap="$(next_run_gap)"; [ -n "$gap" ] || gap=0
  last_fail=0; fails=0; last_alert=0; sup=0
  if [ -r "$STATE_DIR/$JOB_KEY" ]; then
    line="$(cat "$STATE_DIR/$JOB_KEY" 2>/dev/null || true)"
    read -r last_fail fails last_alert sup <<<"$line" || true
  fi
  # 숫자 아닌 값(파일 손상)은 0 으로
  for v in last_fail fails last_alert sup; do
    eval "case \"\${$v:-}\" in ''|*[!0-9]*) $v=0 ;; esac"
  done

  # G2 자동 리셋
  if [ "$gap" -gt 0 ] && [ "$last_fail" -gt 0 ] && [ $(( now - last_fail )) -gt $(( gap * 2 )) ]; then
    fails=0
  fi
  fails=$(( fails + 1 ))
  last_fail="$now"

  # G1 연속 실패 게이트
  need=1
  [ "$gap" -gt 0 ] && [ "$gap" -le "$GAP_LIMIT" ] && need=2
  if [ "$fails" -lt "$need" ]; then
    printf '%s %s %s %s\n' "$last_fail" "$fails" "$last_alert" "$sup" > "$STATE_DIR/$JOB_KEY" 2>/dev/null || true
    echo "[notify] $JOB_KEY: 1차 실패 — 약 $(( gap / 60 ))분 뒤 자동 재실행 예정이라 알림 보류(연속 ${need}회부터 발송)" >&2
    return 1
  fi

  # G3 버스트 쿨다운
  if [ "$last_alert" -gt 0 ] && [ $(( now - last_alert )) -lt "$COOLDOWN" ]; then
    sup=$(( sup + 1 ))
    printf '%s %s %s %s\n' "$last_fail" "$fails" "$last_alert" "$sup" > "$STATE_DIR/$JOB_KEY" 2>/dev/null || true
    echo "[notify] $JOB_KEY: 쿨다운($(( COOLDOWN / 3600 ))h) 내 재실패 — 억제 누적 ${sup}회" >&2
    return 1
  fi

  [ "$sup" -gt 0 ] && SUP_NOTE="%0A%0A(직전 알림 이후 ${sup}회 더 실패)"
  [ "$fails" -gt 1 ] && GATE_NOTE="%0A연속 ${fails}회 실패 — 자동 재시도로 복구되지 않았습니다."
  printf '%s %s %s %s\n' "$last_fail" "$fails" "$now" "0" > "$STATE_DIR/$JOB_KEY" 2>/dev/null || true
  return 0
}

set +e
gate_decide
GATE_RC=$?
set -e
[ "$GATE_RC" -eq 1 ] && exit 0

case "$UNIT" in
  sisyphe-bot)
    TEXT="🚨 <b>Sisyphe-Bot 중단</b>%0A연속 실패로 자동 재시작이 중단되었습니다.%0A수동 확인이 필요합니다.%0A%0A<code>sudo launchctl kickstart -k system/com.antigravity.sisyphe-bot</code>%0A<code>tail -n 50 ${LOG_DIR}/sisyphe-bot.err</code>"
    ;;
  ra-sisyphe-bot)
    TEXT="⚠️ <b>RA_Sisyphe_bot 중단</b>%0A연속 실패로 자동 재시작이 중단되었습니다.%0A%0A<code>sudo launchctl kickstart -k system/com.antigravity.ra-sisyphe-bot</code>%0A<code>tail -n 50 ${LOG_DIR}/ra-sisyphe-bot.err</code>"
    ;;
  research-notes-bot)
    TEXT="⚠️ <b>Research Notes 봇 중단</b>%0A연속 실패로 자동 재시작이 중단되었습니다.%0A%0A<code>sudo launchctl kickstart -k system/com.antigravity.research-notes-bot</code>%0A<code>tail -n 50 ${LOG_DIR}/research-notes-bot.err</code>"
    ;;
  kodex-sectors)
    TEXT="⚠️ <b>KODEX 섹터 패치 실패</b>%0Atimeout 또는 git/네트워크 오류로 KOSPI 200·KOSDAQ 150 섹터 수집이 중단되었습니다.%0A%0A<code>tail -n 50 ${LOG_DIR}/kodex-sectors.err</code>"
    ;;
  earnings-bot)
    TEXT="🚨 <b>Earnings-Bot 실패</b>%0Atimeout 또는 예외로 어닝봇 파이프라인이 중단되었습니다.%0A로그 확인이 필요합니다.%0A%0A<code>tail -n 100 ${LOG_DIR}/earnings-bot.err</code>"
    ;;
  send-advisory-emails)
    TEXT="⚠️ <b>자문지 메일 폴러 실패</b>%0AGitHub 요청 조회 연속 실패(약 10분 지속) 또는 발송 오류입니다.%0A%0A<code>tail -n 50 ${LOG_DIR}/send-advisory-emails.err</code>"
    ;;
  *)
    # 알 수 없는 잡 이름이라도 누락 없이 알림 (체인 게이트 'name: chain-timeout(...)' 형식 포함)
    JOB="${UNIT%%:*}"
    TEXT="⚠️ <b>${UNIT} 실패</b>%0Alaunchd 잡 실패 알림. 로그 확인이 필요합니다.%0A%0A<code>tail -n 50 ${LOG_DIR}/${JOB}.err</code>"
    ;;
esac

TEXT="${TEXT}${GATE_NOTE}${SUP_NOTE}"

if [ -n "${NOTIFY_DRYRUN:-}" ]; then
  echo "[notify] DRYRUN 발송: ${TEXT}"
  exit 0
fi

curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_SISYPHE_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}" \
  -d 'parse_mode=HTML' \
  -d "text=${TEXT}"
echo

# ── 자가진단 2단계 (2026-07-16): headless claude 가 로그·코드를 읽고 원인
# 진단을 🩺 후속 메시지로 발송 (읽기 전용, 잡당 60분 쿨다운, 실패해도 무해).
DIAG="$(cd "$(dirname "$0")" && pwd)/diagnose_failure.sh"
if [ -x "$DIAG" ]; then
  nohup "$DIAG" "$UNIT" >/dev/null 2>&1 &
fi
