#!/bin/bash
set -euo pipefail
ENV_FILE="/home/ubuntu/Antigravity_Market_Dashboard/.env"
[ -r "$ENV_FILE" ] && { set -a; source "$ENV_FILE"; set +a; }

UNIT="${1:-sisyphe-bot}"

case "$UNIT" in
  earnings-bot)
    TEXT='🚨 <b>Earnings-Bot 실패</b>%0Asystemd timeout 또는 예외로 어닝봇 파이프라인이 중단되었습니다.%0Ajournal 확인이 필요합니다.%0A%0A<code>sudo journalctl -u earnings-bot.service -n 100</code>'
    ;;
  *)
    TEXT='🚨 <b>Sisyphe-Bot 중단</b>%0A10회 연속 실패로 자동 재시작이 중단되었습니다.%0A수동 확인이 필요합니다.%0A%0A<code>sudo systemctl restart sisyphe-bot</code>'
    ;;
esac

curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_SISYPHE_BOT_TOKEN}/sendMessage"   -d "chat_id=${TELEGRAM_CHAT_ID}"   -d 'parse_mode=HTML'   -d "text=${TEXT}"
