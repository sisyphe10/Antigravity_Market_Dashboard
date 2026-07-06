#!/bin/bash
set -euo pipefail
ENV_FILE="${ENV_FILE:-$(cd "$(dirname "$0")/.." && pwd)/.env}"  # self-locate
[ -r "$ENV_FILE" ] && { set -a; source "$ENV_FILE"; set +a; }

TEXT='⚠️ <b>landing-highlights 실패</b>%0A30분 회전 위젯 데이터 생성/push가 중단되었습니다.%0Ajournal 확인이 필요합니다.%0A%0A<code>sudo journalctl -u landing-highlights.service -n 50</code>'

curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_SISYPHE_BOT_TOKEN}/sendMessage"   -d "chat_id=${TELEGRAM_CHAT_ID}"   -d 'parse_mode=HTML'   -d "text=${TEXT}"
echo
