#!/bin/bash
# check_daemon_ports.sh — AoE 웹 데몬 3종 포트 헬스체크 + 자가복구 (2026-07-27 신설)
#
# 대상 (다운 시 사용자 체감이 서로 다름):
#   watchlist(8778)      : / 및 /index.html 리다이렉트 대상 → 죽으면 첫 화면부터 502
#   datalake-webui(8787) : Wiki·Earnings 탭 502
#   plan-api(8790)       : Memento/Ledger 데이터 로드·저장 실패 (페이지 자체는 뜸)
#
# KeepAlive 가 못 살리는 유형(좀비 프로세스의 포트 점유 → bind 실패 반복 등)을 감시한다
# (실사례: 2026-07-16 plan-api 8790 좀비 점유 → 502 지속).
# 동작: probe → 다운이면 launchctl kickstart -k 1회 → 대기 후 재probe → 텔레그램 보고.
#   전부 정상(무개입)      → 무음 exit 0
#   kickstart 로 복구됨    → 텔레그램 알림 + exit 0
#   복구 실패 잔존         → 텔레그램 알림 + exit 1 (runner notify_failure 추가 발화)
# 실행 주체: launchd 타이머(root) — kickstart 에 sudo 불요. 수동(user) 실행 시 probe 만 유효.
set -u

probe() {  # $1=url → http code (000=연결실패)
  curl -s -o /dev/null -m 5 -w '%{http_code}' "$1" 2>/dev/null || echo 000
}

is_up() {  # 2xx/3xx = 정상
  case "$1" in 2??|3??) return 0 ;; *) return 1 ;; esac
}

NAMES=(watchlist datalake-webui plan-api)
URLS=("http://127.0.0.1:8778/" "http://127.0.0.1:8787/" "http://127.0.0.1:8790/plan")
WAITS=(20 20 130)   # kickstart 후 재확인 대기(초) — plan-api 기동 ~120초

report=""
kicked=0
still_down=0

for i in "${!NAMES[@]}"; do
  name="${NAMES[$i]}"; url="${URLS[$i]}"; wait_s="${WAITS[$i]}"
  code="$(probe "$url")"
  if is_up "$code"; then
    continue
  fi
  kicked=1
  launchctl kickstart -k "system/com.antigravity.$name" 2>/dev/null
  sleep "$wait_s"
  code2="$(probe "$url")"
  if is_up "$code2"; then
    report="$report
- $name: 다운(HTTP $code) → kickstart 재시작 → 복구됨"
  else
    still_down=1
    report="$report
- $name: 다운(HTTP $code) → kickstart 후에도 실패(HTTP $code2) — 수동 점검 필요 (좀비 포트 점유 의심: lsof -ti :PORT)"
  fi
done

if [ "$kicked" -eq 1 ]; then
  msg="🩺 AoE 데몬 헬스체크$report"
  if [ -n "${TELEGRAM_SISYPHE_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    curl -s -m 10 "https://api.telegram.org/bot${TELEGRAM_SISYPHE_BOT_TOKEN}/sendMessage" \
      -d "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=${msg}" > /dev/null || true
  fi
  echo "$msg"
fi

exit "$still_down"
