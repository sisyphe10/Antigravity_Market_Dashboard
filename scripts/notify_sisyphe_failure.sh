#!/bin/bash
set -euo pipefail
ENV_FILE="${ENV_FILE:-$(cd "$(dirname "$0")/.." && pwd)/.env}"  # self-locate
[ -r "$ENV_FILE" ] && { set -a; source "$ENV_FILE"; set +a; }

# launchd wrapper(run_timer_job.sh notify_failure / 봇 supervision)가 잡 이름을 첫 인자로 호출.
# (구 systemd OnFailure %i 인터페이스 유지 — 2026-07-13 문구를 맥미니 launchd 기준으로 전환)
UNIT="${1:-sisyphe-bot}"
DETAIL="${2:-}"   # 선택 인자: 실패 사유 한 줄. 메시지 끝에 코드블록으로 덧붙인다.
LOG_DIR='~/Antigravity_Market_Dashboard/logs/launchd'

# ─────────────────────────────────────────────────────────────────────────────
# 알림 억제 게이트 (2026-08-05, 사용자 지시: "재시도로 해결되는 건 알람 금지, 최종 실패만")
#
#   G1 연속 실패 게이트 — 곧 자동 재실행되는 잡(다음 실행까지 ≤ GAP_LIMIT)은 1차 실패를
#      침묵하고, 연속 2회째(= 재시도도 실패 = 최종 실패)부터 알린다. 재실행이 먼 잡
#      (일 1회 등)은 종전대로 즉시 알린다 — 24시간 뒤에 알리는 건 알림이 아니므로.
#      다음 실행 간격은 잡의 plist(StartInterval / StartCalendarInterval)에서 그때그때
#      산출한다. 잡 목록을 하드코딩하지 않으므로 스케줄이 바뀌어도 안 어긋난다.
#   G2 자동 리셋 — 마지막 실패가 2×간격(하한 1시간)보다 오래 전이면 그 사이 성공한 것으로
#      보고 카운터를 0으로 되돌린다. 산발적 1회 실패가 누적돼 알림이 되는 걸 막는다.
#   G3 버스트 쿨다운 — 발송 후 COOLDOWN(기본 6h) 안의 재실패는 억제하고 횟수만 세어,
#      다음 알림 본문에 "(직전 알림 이후 N회 더 실패)"로 합산 통지한다.
#
#   ★fail-open 원칙: 게이트가 확신할 수 없으면 무조건 발송한다. 노이즈보다 유실이 나쁘다.
#     - plist·PlistBuddy 부재, 시각 산출 실패 → 간격 미상 → 즉시 발송
#     - 상태 저장 실패(권한·디스크) → 억제하지 않고 발송  ← v2 수정
#   ★상태는 '발송 결과를 확인한 뒤' 기록한다(v2 수정). 발송 전에 last_alert 를 찍으면
#     전송이 실패했을 때 알림은 안 갔는데 쿨다운만 걸려 그 알림이 영구 유실된다.
#     (2026-08-05 Codex 검토 지적 — 이 스크립트가 고치려던 순단이 그대로 유실을 만든다)
#   ★NOTIFY_DRYRUN 은 상태를 일절 건드리지 않는다(v2 수정). 테스트가 실제 쿨다운을 켜면 안 된다.
#
#   침묵된 실패도 성공 stamp 미기록으로 남아 daily-selfcheck 의 STALE 감시에 그대로 걸린다.
#   테스트: NOTIFY_DRYRUN=1 (미발송·상태 불변) / NOTIFY_STATE_DIR (상태 격리)
#   튜닝:  NOTIFY_GAP_LIMIT · NOTIFY_COOLDOWN_SEC · NOTIFY_RESET_FLOOR
# ─────────────────────────────────────────────────────────────────────────────
JOB_KEY="${UNIT%%:*}"                       # "name: chain-timeout(...)" 형태 대응
GAP_LIMIT="${NOTIFY_GAP_LIMIT:-14400}"      # 4h 이내 재실행 = '재시도 있음'으로 간주
COOLDOWN="${NOTIFY_COOLDOWN_SEC:-21600}"    # 6h
RESET_FLOOR="${NOTIFY_RESET_FLOOR:-3600}"   # 연속 판정 리셋 창 하한 1h
STATE_DIR="${NOTIFY_STATE_DIR:-$(cd "$(dirname "$0")/.." && pwd)/logs/launchd/notify_state}"
DRYRUN="${NOTIFY_DRYRUN:-}"
STATE_FILE=""
SUP_NOTE=""
GATE_NOTE=""
S_NOW=0; S_FAILS=0; S_LAST_ALERT=0; S_SUP=0   # 발송 후 확정할 상태

# 다음 자동 재실행까지 남은 초. 산출 불가(상주 봇·plist 없음 등)면 0 → 즉시 알림.
# 한계(수용): Hour 만 본다. Minute·Weekday 조합은 복원하지 않는다. 같은 hour 재실행은
# 24h 로 계산돼 '즉시 알림' 쪽으로 기울므로 안전한 방향이다. 주간(Weekday) 잡이 생기면
# 촘촘한 잡으로 오판할 수 있으니 그때 이 함수를 확장할 것 — 현재 그런 잡은 없다.
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

# 상태 원자적 기록. rc 0 = 저장됨(또는 dry-run 이라 건너뜀), rc 1 = 저장 실패.
write_state() {   # $1=last_fail $2=fails $3=last_alert $4=suppressed
  [ -n "$DRYRUN" ] && return 0
  local tmp="${STATE_FILE}.tmp.$$"
  printf '%s %s %s %s\n' "$1" "$2" "$3" "$4" > "$tmp" 2>/dev/null || return 1
  mv -f "$tmp" "$STATE_FILE" 2>/dev/null || { rm -f "$tmp" 2>/dev/null || true; return 1; }
  return 0
}

gate_decide() {   # rc 0 = 발송, rc 1 = 억제
  local now gap need last_fail fails last_alert sup line reset_sec v
  mkdir -p "$STATE_DIR" 2>/dev/null || return 0        # 상태 못 쓰면 fail-open
  STATE_FILE="$STATE_DIR/$JOB_KEY"
  now="$(date +%s 2>/dev/null || true)"
  case "${now:-}" in ''|*[!0-9]*) return 0 ;; esac      # 시각 산출 실패 → fail-open
  gap="$(next_run_gap)"; case "${gap:-}" in ''|*[!0-9]*) gap=0 ;; esac

  last_fail=0; fails=0; last_alert=0; sup=0
  if [ -r "$STATE_FILE" ]; then
    line="$(cat "$STATE_FILE" 2>/dev/null || true)"
    read -r last_fail fails last_alert sup <<<"$line" || true
  fi
  for v in last_fail fails last_alert sup; do          # 손상값은 0 으로
    eval "case \"\${$v:-}\" in ''|*[!0-9]*) $v=0 ;; esac"
  done
  # 시계 역행 방어: 미래 타임스탬프는 신뢰하지 않는다(쿨다운이 영구화되는 것을 막는다)
  [ "$last_alert" -gt "$now" ] && last_alert=0
  [ "$last_fail" -gt "$now" ] && last_fail=0

  # G2 자동 리셋 (창 = 2×간격, 하한 RESET_FLOOR)
  reset_sec=$(( gap * 2 ))
  [ "$reset_sec" -lt "$RESET_FLOOR" ] && reset_sec="$RESET_FLOOR"
  if [ "$gap" -gt 0 ] && [ "$last_fail" -gt 0 ] && [ $(( now - last_fail )) -gt "$reset_sec" ]; then
    fails=0
  fi
  fails=$(( fails + 1 ))

  # G1 연속 실패 게이트
  need=1
  [ "$gap" -gt 0 ] && [ "$gap" -le "$GAP_LIMIT" ] && need=2
  if [ "$fails" -lt "$need" ]; then
    write_state "$now" "$fails" "$last_alert" "$sup" || {
      echo "[notify] $JOB_KEY: 상태 저장 실패 — 억제하지 않고 발송(fail-open)" >&2
      return 0
    }
    echo "[notify] $JOB_KEY: 1차 실패 — 약 $(( gap / 60 ))분 뒤 자동 재실행 예정이라 알림 보류(연속 ${need}회부터 발송)" >&2
    return 1
  fi

  # G3 버스트 쿨다운
  if [ "$last_alert" -gt 0 ] && [ $(( now - last_alert )) -lt "$COOLDOWN" ]; then
    sup=$(( sup + 1 ))
    write_state "$now" "$fails" "$last_alert" "$sup" || {
      echo "[notify] $JOB_KEY: 상태 저장 실패 — 억제하지 않고 발송(fail-open)" >&2
      return 0
    }
    echo "[notify] $JOB_KEY: 쿨다운($(( COOLDOWN / 3600 ))h) 내 재실패 — 억제 누적 ${sup}회" >&2
    return 1
  fi

  # 발송 경로 — 상태는 여기서 쓰지 않는다. 발송 결과를 보고 확정한다.
  S_NOW="$now"; S_FAILS="$fails"; S_LAST_ALERT="$last_alert"; S_SUP="$sup"
  [ "$sup" -gt 0 ] && SUP_NOTE="%0A%0A(직전 알림 이후 ${sup}회 더 실패)"
  [ "$fails" -gt 1 ] && GATE_NOTE="%0A연속 ${fails}회 실패 — 자동 재시도로 복구되지 않았습니다."
  return 0
}

# 텔레그램 발송. rc 0 = Telegram 이 ok:true 로 확인한 경우에만.
# 순단 대비 3회 재시도(5s/10s). 응답 본문은 로그에 남기지 않는다.
send_telegram() {
  local i rc resp
  if [ -z "${TELEGRAM_SISYPHE_BOT_TOKEN:-}" ] || [ -z "${TELEGRAM_CHAT_ID:-}" ]; then
    echo "[notify] 텔레그램 토큰/chat_id 없음 — 발송 불가" >&2
    return 1
  fi
  for i in 1 2 3; do
    set +e
    resp="$(curl -s --max-time 20 -X POST \
      "https://api.telegram.org/bot${TELEGRAM_SISYPHE_BOT_TOKEN}/sendMessage" \
      -d "chat_id=${TELEGRAM_CHAT_ID}" -d 'parse_mode=HTML' -d "text=$1" 2>/dev/null)"
    rc=$?
    set -e
    if [ "$rc" -eq 0 ] && printf '%s' "$resp" | grep -q '"ok":true'; then
      return 0
    fi
    echo "[notify] $JOB_KEY: 텔레그램 발송 실패 ${i}/3 (curl rc=$rc)" >&2
    [ "$i" -lt 3 ] && sleep $(( 5 * i ))
  done
  return 1
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
  map-weekly)
    TEXT="🗺️ <b>시스템 지도 주간 보정 실패</b>%0A일요일 22:10 crontab 잡(weekly_map_update.sh)이 중단되었습니다.%0A지도가 몇 주씩 조용히 낡는 것을 막기 위한 알림입니다.%0A%0A<code>tail -n 40 ~/tmp/map_update.log</code>"
    ;;
  *)
    # 알 수 없는 잡 이름이라도 누락 없이 알림 (체인 게이트 'name: chain-timeout(...)' 형식 포함)
    JOB="${UNIT%%:*}"
    TEXT="⚠️ <b>${UNIT} 실패</b>%0Alaunchd 잡 실패 알림. 로그 확인이 필요합니다.%0A%0A<code>tail -n 50 ${LOG_DIR}/${JOB}.err</code>"
    ;;
esac

TEXT="${TEXT}${GATE_NOTE}${SUP_NOTE}"

# 상세 사유. 본문은 x-www-form-urlencoded 로 실려가므로 & = % + # 와 HTML 꺾쇠는 제거한다.
if [ -n "$DETAIL" ]; then
  DETAIL_SAFE="$(printf '%s' "$DETAIL" | tr -d '&=%+#<>' | tr '\n' ' ' | cut -c1-300)"
  [ -n "$DETAIL_SAFE" ] && TEXT="${TEXT}%0A%0A<code>${DETAIL_SAFE}</code>"
fi

if [ -n "$DRYRUN" ]; then
  echo "[notify] DRYRUN 발송(상태 불변): ${TEXT}"
  exit 0
fi

if send_telegram "$TEXT"; then
  # 발송이 확인된 뒤에만 쿨다운 시작점을 찍는다.
  write_state "$S_NOW" "$S_FAILS" "$S_NOW" 0 \
    || echo "[notify] $JOB_KEY: 상태 저장 실패(경고) — 다음 실패 때 중복 알림 가능" >&2
else
  # 미전달. last_alert 를 갱신하지 않아 다음 실패에서 알림을 다시 시도한다.
  write_state "$S_NOW" "$S_FAILS" "$S_LAST_ALERT" "$S_SUP" || true
  echo "[notify] $JOB_KEY: 텔레그램 3회 모두 실패 — 알림 미전달(다음 실패에서 재시도)" >&2
  exit 1
fi

# ── 자가진단 2단계 (2026-07-16): headless claude 가 로그·코드를 읽고 원인
# 진단을 🩺 후속 메시지로 발송 (읽기 전용, 잡당 60분 쿨다운, 실패해도 무해).
DIAG="$(cd "$(dirname "$0")" && pwd)/diagnose_failure.sh"
if [ -x "$DIAG" ]; then
  nohup "$DIAG" "$UNIT" >/dev/null 2>&1 &
fi
