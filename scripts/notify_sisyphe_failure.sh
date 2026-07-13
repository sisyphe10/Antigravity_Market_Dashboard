#!/bin/bash
set -euo pipefail
ENV_FILE="${ENV_FILE:-$(cd "$(dirname "$0")/.." && pwd)/.env}"  # self-locate
[ -r "$ENV_FILE" ] && { set -a; source "$ENV_FILE"; set +a; }

# launchd wrapper(run_timer_job.sh notify_failure / 봇 supervision)가 잡 이름을 첫 인자로 호출.
# (구 systemd OnFailure %i 인터페이스 유지 — 2026-07-13 문구를 맥미니 launchd 기준으로 전환)
UNIT="${1:-sisyphe-bot}"
LOG_DIR='~/Antigravity_Market_Dashboard/logs/launchd'

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

curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_SISYPHE_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}" \
  -d 'parse_mode=HTML' \
  -d "text=${TEXT}"
echo
