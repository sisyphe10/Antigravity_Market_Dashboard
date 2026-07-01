"""액티브 ETF 구성종목 변동 — 일일 텔레그램 알림 (Sisyphe-Bot).

VM systemd 타이머(etf-active-alert.timer, 19:00 KST)가 실행한다.
etf_data.db → compute_active_etf_changes() 로 변동을 계산하고(대시보드 etf.html과
동일한 단일 출처 모듈), subscribers.json 구독자에게 브로드캐스트한다.

- 토큰: .env 의 Sisyphe-Bot 토큰 (daily_alert.py 와 동일 소스)
- 구독자: subscribers.json (sisyphe_bot.load_subscribers 와 동일 파일)
- dedup: .etf_active_alert_sent.json {last_sent_date: latest}
  → 휴장일에 타이머가 떠도 latest 가 안 바뀌면 무발송 (재발송 방지)
- 분할: chunk_by_lines (HTML 태그 안 끊김)

봇 프로세스와 무관한 독립 실행이므로 봇 재시작/배포가 진행 중 알림을 죽이지 않는다
(ETF 수집을 systemd 로 분리한 것과 같은 이유).
"""
import os
import sys
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'execution', 'etf_collector'))

STATE_FILE = os.path.join(REPO, '.etf_active_alert_sent.json')
SUBSCRIBERS_FILE = os.path.join(REPO, 'subscribers.json')
ENV_FILE = os.path.join(REPO, '.env')
TOKEN_KEY = 'TELEGRAM_' + 'SISYPHE_BOT_TOKEN'  # Sisyphe-Bot


def _load_token():
    # python-dotenv 우선, 실패 시 .env 라인 파싱 폴백
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)
    except Exception:
        pass
    tok = os.getenv(TOKEN_KEY)
    if tok:
        return tok.strip().strip('"').strip("'")
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding='utf-8') as f:
            for ln in f:
                s = ln.strip()
                if s.startswith(TOKEN_KEY + '='):
                    return s.split('=', 1)[1].strip().strip('"').strip("'")
    return None


def _load_subscribers():
    if not os.path.exists(SUBSCRIBERS_FILE):
        return []
    try:
        with open(SUBSCRIBERS_FILE, encoding='utf-8') as f:
            data = json.load(f)
        return list(data) if isinstance(data, (list, set)) else list(data)
    except Exception as e:
        logging.error("subscribers.json 읽기 실패: %s", e)
        return []


def _load_last_sent():
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, encoding='utf-8') as f:
            return json.load(f).get('last_sent_date')
    except Exception:
        return None


def _save_last_sent(date_str):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'last_sent_date': date_str}, f)
    except Exception as e:
        logging.error("상태 파일 저장 실패: %s", e)


def _send(token, chat_id, text):
    import requests
    r = requests.post(
        f'https://api.telegram.org/bot{token}/sendMessage',
        json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML',
              'disable_web_page_preview': True},
        timeout=15,
    )
    ok = r.ok and r.json().get('ok')
    if not ok:
        logging.error("send fail chat=%s status=%s body=%s", chat_id, r.status_code, r.text[:200])
    return ok


def main():
    from active_etf_changes import compute_active_etf_changes, format_telegram_message, chunk_by_lines

    result = compute_active_etf_changes()
    latest = result.get('latest')
    if not latest:
        logging.info("ETF 데이터 없음 — 종료")
        return
    if result.get('first_run'):
        logging.info("최초 수집(전일 없음) — 미발송, 상태 미갱신")
        return

    # dedup: latest 가 지난 발송과 같으면(휴장일 등) 무발송
    last = _load_last_sent()
    if last == latest:
        logging.info("이미 발송한 날짜(%s) — 무발송", latest)
        return

    msg = format_telegram_message(result)
    if msg is None:
        logging.info("발송할 내용 없음 — 상태만 갱신(%s)", latest)
        _save_last_sent(latest)
        return

    token = _load_token()
    if not token:
        logging.error("봇 토큰 없음 — 종료(상태 미갱신)")
        return
    subs = _load_subscribers()
    if not subs:
        logging.warning("구독자 없음 — 상태만 갱신")
        _save_last_sent(latest)
        return

    chunks = chunk_by_lines(msg)
    sent = 0
    for cid in subs:
        ok = True
        for ch in chunks:
            if not _send(token, cid, ch):
                ok = False
        sent += 1 if ok else 0
    logging.info("액티브 ETF 알림 전송 %d/%d (chunks=%d, latest=%s, changed=%d)",
                 sent, len(subs), len(chunks), latest, result['totals']['etfs_changed'])

    # 최소 1명 성공 시 dedup 갱신 (전원 실패면 다음 실행에서 재시도)
    if sent > 0:
        _save_last_sent(latest)


if __name__ == "__main__":
    main()
