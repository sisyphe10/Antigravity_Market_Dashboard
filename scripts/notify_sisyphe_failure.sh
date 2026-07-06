#!/bin/bash
set -euo pipefail
ENV_FILE="${ENV_FILE:-$(cd "$(dirname "$0")/.." && pwd)/.env}"  # self-locate
[ -r "$ENV_FILE" ] && { set -a; source "$ENV_FILE"; set +a; }

# OnFailure에서 systemd template으로 호출됨: sisyphe-bot-notify@<unit-name>.service
# ExecStart=...notify_sisyphe_failure.sh %i  →  %i가 첫 인자로 전달됨
UNIT="${1:-sisyphe-bot}"

case "$UNIT" in
  sisyphe-bot)
    TEXT='🚨 <b>Sisyphe-Bot 중단</b>%0A10회 연속 실패로 자동 재시작이 중단되었습니다.%0A수동 확인이 필요합니다.%0A%0A<code>sudo systemctl restart sisyphe-bot</code>'
    ;;
  ra-sisyphe-bot)
    TEXT='⚠️ <b>RA_Sisyphe_bot 중단</b>%0A10회 연속 실패로 자동 재시작이 중단되었습니다.%0A%0A<code>sudo systemctl restart ra-sisyphe-bot</code>%0A<code>sudo journalctl -u ra-sisyphe-bot -n 50</code>'
    ;;
  research-notes-bot)
    TEXT='⚠️ <b>Research Notes 봇 중단</b>%0A10회 연속 실패로 자동 재시작이 중단되었습니다.%0A%0A<code>sudo systemctl restart research-notes-bot</code>%0A<code>sudo journalctl -u research-notes-bot -n 50</code>'
    ;;
  kodex-sectors)
    TEXT='⚠️ <b>KODEX 섹터 패치 실패</b>%0Asystemd timeout 또는 git/네트워크 오류로 KOSPI 200·KOSDAQ 150 섹터 수집이 중단되었습니다.%0A%0A<code>sudo journalctl -u kodex-sectors.service -n 50</code>'
    ;;
  earnings-bot)
    TEXT='🚨 <b>Earnings-Bot 실패</b>%0Asystemd timeout 또는 예외로 어닝봇 파이프라인이 중단되었습니다.%0Ajournal 확인이 필요합니다.%0A%0A<code>sudo journalctl -u earnings-bot.service -n 100</code>'
    ;;
  *)
    # 알 수 없는 unit이라도 누락 없이 알림
    TEXT="⚠️ <b>${UNIT} 실패</b>%0AsystemD OnFailure 트리거됨. journal 확인이 필요합니다.%0A%0A<code>sudo journalctl -u ${UNIT}.service -n 50</code>"
    ;;
esac

curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_SISYPHE_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}" \
  -d 'parse_mode=HTML' \
  -d "text=${TEXT}"
echo
