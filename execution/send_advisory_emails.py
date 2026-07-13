# -*- coding: utf-8 -*-
"""orders/email_send_request.json → 하이웍스 SMTP 자문지 메일 발송 (B안, 2026-07-13)

launchd 60초 폴러(run_timer_job.sh send-advisory-emails)가 호출. wrap.html Email 탭의
[메일 발송 요청]이 Contents API+PAT로 기록한 요청을 감지해 5통(컴플/삼성/NH/DB/한투) 발송.

★★★ 안전 3중 가드 (codex 리뷰 중점) ★★★
  가드1 — 모드 단일출처: 발송 모드는 **맥 로컬 ~/email_config.json 의 mode 만** 신뢰(기본 'test').
          요청 파일(email_send_request.json)의 mode 필드는 감사/표시용으로만 저장, 발송 판단에 절대 미사용.
          → 페이지 조작/버그로 real 전환 불가.
  가드2 — real 전환 조건: config mode 값 변경 + 사용자 명시 승인 후에만. 코드가 자동 전환하지 않음.
  가드3 — 발송 직전 assert: mode=='test' 인데 To/CC/BCC 에 본인(SELF) 외 주소가 하나라도 있으면
          SendGuardError → **전체 배치 중단(부분발송 없음) + 텔레그램 알림**. test 모드 수신자는
          resolve_recipients 가 To=[본인]·CC=[]·BCC=[] 로만 구성하고, assert 는 그 위의 방어선.

멱등: 요청 ts 를 처리 후 orders/email_send_result.json 에 기록. 재실행 시 ts<=마지막처리 스킵.
비밀번호·메일 전문 로그 미기록 (요약만). SMTP 비번은 .env HIWORKS_MAIL_PASSWORD(사용자 입력).
"""
import json
import os
import re
import sys
import time
import subprocess
from datetime import datetime, timezone, timedelta

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_SLUG = os.environ.get('GITHUB_REPOSITORY', 'sisyphe10/Antigravity_Market_Dashboard')
CONFIG_PATH = os.path.expanduser('~/email_config.json')          # 맥 로컬 전용 (repo 밖)
RESULT_PATH = os.path.join(ROOT, 'orders', 'email_send_result.json')
MAX_ATTACH_TOTAL = 5 * 1024 * 1024   # 폴러측 방어 상한(클라이언트가 요청 900KB 로 이미 제한)
KST = timezone(timedelta(hours=9))
# ★가드 핵심(codex 리뷰 치명 반영): test 안전 기준·BCC 기록 주소는 config 와 무관한 고정 상수.
#   config.from 이 실수/악의로 오염돼도 test 발송은 이 주소 단독으로만 나간다.
SELF_CANONICAL = 'kts@investlife.com'
STATE_STAMP = os.path.join(ROOT, 'logs', 'launchd', 'send-advisory-emails.processed')
COMPLIANCE_STAMP = os.path.join(ROOT, 'logs', 'launchd', 'compliance_sent.date')
BROKER_KEYS = ('samsung', 'nh', 'db', 'kis')


class SendGuardError(Exception):
    """test-safety 위반 등 발송 차단 사유 (전체 배치 중단)."""


# ─────────────────────────── 순수 가드/조립 함수 (단위테스트 대상) ───────────────────────────
def norm_addr(s):
    """'이름 <email@x>' 또는 'email@x' → 소문자 이메일만. 비교·assert 정규화용."""
    m = re.search(r'<([^>]+)>', s or '')
    addr = m.group(1) if m else (s or '')
    return addr.strip().lower()


def resolve_mode(config):
    """가드1+2: 발송 모드는 config 만 신뢰. real 은 mode=='real' **그리고** real_send_armed==True
    (2단계 명시 조건)일 때만. 그 외·누락 → 'test'. 요청 파일 mode 는 절대 참조하지 않음."""
    c = config or {}
    if c.get('mode') == 'real' and c.get('real_send_armed') is True:
        return 'real'
    return 'test'


def resolve_recipients(mode, acct):
    """가드3 기반: test → 본인(SELF_CANONICAL) 단독. real → 실수신자 + BCC 본인(보낸기록).
    ★본인 주소는 config 가 아닌 고정 상수 — config 오염으로도 test 수신자가 바뀌지 않는다."""
    if mode == 'test':
        return {'to': [SELF_CANONICAL], 'cc': [], 'bcc': []}
    return {
        'to': list(acct.get('to', [])),
        'cc': list(acct.get('cc', [])),
        'bcc': [SELF_CANONICAL],
    }


def assert_test_safety(mode, rcpts):
    """가드3: test 모드인데 본인(SELF_CANONICAL) 외 주소가 하나라도 있으면 발송 차단."""
    if mode != 'test':
        return
    self_n = norm_addr(SELF_CANONICAL)
    allrc = list(rcpts.get('to', [])) + list(rcpts.get('cc', [])) + list(rcpts.get('bcc', []))
    bad = [r for r in allrc if norm_addr(r) != self_n]
    if bad:
        raise SendGuardError('TEST 모드 위반: 본인(%s) 외 수신자 %r — 전체 발송 차단' % (self_n, bad))


def broker_keys_needing_compliance(keys, compliance_done):
    """컴플라이언스 선발송 규칙: compliance 미발송 상태에서 증권사 키가 있으면 그 목록 반환(위반).
    compliance 키는 항상 허용. test/real 동일 적용(흐름 자체를 강제)."""
    if compliance_done:
        return []
    return [k for k in keys if k in BROKER_KEYS]


def decode_attachments(mail):
    """★첨부는 오직 요청 JSON 의 base64(클라이언트 downloadOrderExcel 생성본)에서만.
    자문지/ 폴더는 절대 참조하지 않는다(과거 템플릿 오발송 원천 차단). (filename, bytes) 리스트 반환."""
    import base64
    out, total = [], 0
    for a in (mail.get('attachments') or []):
        fn = a.get('filename') or 'attachment.xlsx'
        b64 = a.get('content_b64') or ''
        try:
            raw = base64.b64decode(b64, validate=True)
        except Exception as e:
            raise SendGuardError('첨부 base64 디코드 실패(%s): %s' % (fn, str(e)[:80]))
        if not raw:
            raise SendGuardError('첨부 내용 없음: %s' % fn)
        total += len(raw)
        out.append((fn, raw))
    if total > MAX_ATTACH_TOTAL:
        raise SendGuardError('첨부 총량 초과: %d bytes' % total)
    return out


# 서명 시작 마커(plain 본문 안) + 하이웍스 실서명 HTML 원본(정확 재현)
SIG_MARKER = '김 태 식 운용3본부/매니저'
SIG_HTML_INNER = (
    '<p style="margin:0;"><b>김 태 식 <span style="color:#404040;">운용3본부/매니저</span></b></p>'
    '<p style="margin:0;"><b>라이프자산운용 <span style="color:#858585;">Life Asset Management, Inc.</span></b>'
    '<br>서울 영등포구 국제금융로 10, Two IFC 14F</p>'
    '<p style="margin:0;">02-6105-6836&nbsp;&nbsp;|&nbsp;&nbsp;010-9932-0334&nbsp;&nbsp;|&nbsp;&nbsp;'
    '<a href="mailto:kts@investlife.com" style="color:#163fc7;text-decoration:underline;">kts@investlife.com</a></p>'
)


def html_body(plain):
    """plain 본문 → HTML(굴림 12px). 메시지부는 평문 그대로(<br>), 서명 블록은 하이웍스 실서명 HTML로 교체.
    plain 폴백은 원문 그대로(build_mime의 text/plain)."""
    import html as _html
    idx = plain.find(SIG_MARKER)
    msg = plain[:idx] if idx >= 0 else plain
    inner = _html.escape(msg).replace('\n', '<br>') + (SIG_HTML_INNER if idx >= 0 else '')
    return ('<div style="font-family:굴림,Gulim,sans-serif;font-size:12px;line-height:1.6;color:#000;">'
            + inner + '</div>')


def build_mime(mail, rcpts, from_hdr, attachments):
    """MIME 조립: multipart/mixed(대체 plain+html + 첨부). body/subject 는 요청 그대로.
    attachments=[(filename, bytes)]. HTML 은 서명만 스타일(html_body)."""
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication
    plain = mail.get('body', '')
    outer = MIMEMultipart('mixed')
    outer['From'] = from_hdr
    outer['To'] = ', '.join(rcpts['to'])
    if rcpts.get('cc'):
        outer['Cc'] = ', '.join(rcpts['cc'])
    outer['Subject'] = mail['subject']
    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText(plain, 'plain', 'utf-8'))                 # 폴백
    alt.attach(MIMEText(html_body(plain), 'html', 'utf-8'))       # 서명 스타일본
    outer.attach(alt)
    for fname, raw in attachments:
        part = MIMEApplication(
            raw, _subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        part.add_header('Content-Disposition', 'attachment', filename=('utf-8', '', fname))
        outer.attach(part)
    return outer


def build_send_plan(mode, mails, config):
    """pre-flight: 전 메일의 키 검증 + 수신자 해석 + 가드3 assert + 첨부(요청 base64) 디코드를
    **발송 전** 일괄 수행. 하나라도 실패하면 예외 → 호출부가 전체 배치를 중단(부분발송 방지)."""
    accounts = config.get('accounts', {})
    keys = [m.get('key') for m in mails]
    if len(keys) != len(set(keys)):
        raise SendGuardError('요청 mails 에 중복 key: %r' % keys)
    plan = []
    for mail in mails:
        key = mail.get('key')
        acct = accounts.get(key)
        if acct is None:
            raise SendGuardError('email_config.json 에 계정 미정의: %r' % key)
        rcpts = resolve_recipients(mode, acct)
        assert_test_safety(mode, rcpts)                     # ★가드3
        atts = decode_attachments(mail)                     # 요청 base64 만 (자문지/ 미참조)
        plan.append({'mail': mail, 'rcpts': rcpts, 'attachments': atts})
    return plan


# ─────────────────────────── I/O·발송·알림 (부작용) ───────────────────────────
def send_telegram(text):
    import urllib.request
    import urllib.parse
    token = os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('TELEGRAM_SISYPHE_BOT_TOKEN')
    chat = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        print('  ⚠️ TELEGRAM 토큰/챗 미설정 → 알림 생략')
        return False
    url = 'https://api.telegram.org/bot%s/sendMessage' % token
    data = urllib.parse.urlencode({'chat_id': chat, 'text': text,
                                   'disable_web_page_preview': 'true'}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            return r.status == 200
    except Exception as e:
        print('  ⚠️ 텔레그램 실패: %s' % str(e).replace(token, '<TOKEN>'))
        return False


def fetch_request():
    """요청을 GitHub Contents API(raw)로 직접 읽어 로컬 pull 지연/레이스 우회. 없으면 None."""
    import urllib.request
    import urllib.error
    url = 'https://api.github.com/repos/%s/contents/orders/email_send_request.json?ref=main' % REPO_SLUG
    headers = {'Accept': 'application/vnd.github.raw+json',
               'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'send-advisory-emails'}
    tok = os.environ.get('GH_PAT') or os.environ.get('GITHUB_TOKEN')
    if tok:
        headers['Authorization'] = 'Bearer ' + tok
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def last_processed_ts():
    if not os.path.exists(RESULT_PATH):
        return ''
    try:
        with open(RESULT_PATH, encoding='utf-8') as f:
            return (json.load(f) or {}).get('ts', '') or ''
    except Exception:
        return ''


def _stamp_ts():
    if not os.path.exists(STATE_STAMP):
        return ''
    try:
        with open(STATE_STAMP, encoding='utf-8') as f:
            return f.read().strip()
    except Exception:
        return ''


def already_processed(ts):
    """멱등: result(원격 감사) 또는 로컬 stamp 중 하나라도 ts 이상이면 처리됨."""
    return any(ts <= mk for mk in (last_processed_ts(), _stamp_ts()) if mk)


def mark_processing(ts):
    """발송 루프 진입 직전 원자적 기록 → 발송 도중 크래시해도 재발송 안 함(at-most-once).
    ※ 프레임워크(run_timer_job.sh)의 잡별 락이 동시 실행을 이미 차단하므로, 이 stamp 는
       크래시-후-재시작 시 중복 발송만 막으면 된다."""
    os.makedirs(os.path.dirname(STATE_STAMP), exist_ok=True)
    tmp = STATE_STAMP + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(ts)
    os.replace(tmp, STATE_STAMP)


def compliance_sent_today():
    """오늘(KST) 컴플라이언스 발송 성공 기록이 있으면 True."""
    try:
        with open(COMPLIANCE_STAMP, encoding='utf-8') as f:
            return f.read().strip() == datetime.now(KST).strftime('%Y-%m-%d')
    except Exception:
        return False


def mark_compliance_sent():
    os.makedirs(os.path.dirname(COMPLIANCE_STAMP), exist_ok=True)
    tmp = COMPLIANCE_STAMP + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(datetime.now(KST).strftime('%Y-%m-%d'))
    os.replace(tmp, COMPLIANCE_STAMP)


def smtp_send(config, msg, rcpts, password):
    """SMTP SSL 465 발송. ★password 는 절대 로그/예외메시지에 넣지 않음."""
    import smtplib
    smtp = config['smtp']
    envelope_from = norm_addr(config.get('from', SELF_CANONICAL))
    all_rcpt = list(rcpts['to']) + list(rcpts.get('cc', [])) + list(rcpts.get('bcc', []))
    with smtplib.SMTP_SSL(smtp['host'], int(smtp['port']), timeout=30) as s:
        s.login(smtp['user'], password)
        s.sendmail(envelope_from, all_rcpt, msg.as_string())


def push_result(result):
    os.makedirs(os.path.dirname(RESULT_PATH), exist_ok=True)
    with open(RESULT_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    try:
        subprocess.run(
            ['bash', 'scripts/safe_commit_push.sh', '-m',
             'ORDER email send result: %s (%s, %d통)' % (
                 result.get('date', ''), result.get('mode', ''), len(result.get('sent', []))),
             '--', 'orders/email_send_result.json'],
            cwd=ROOT, timeout=180, check=False)
    except Exception as e:
        print('  ⚠️ result push 실패: %s' % e)


def main():
    req = fetch_request()
    if not req or not isinstance(req, dict):
        return 0                                   # 요청 없음 → 조용히 종료
    ts = req.get('ts', '')
    if not ts:
        print('⚪ 요청에 ts 없음 → 스킵')
        return 0
    if already_processed(ts):
        return 0                                   # 멱등: 이미 처리(result 또는 로컬 stamp)

    if not os.path.exists(CONFIG_PATH):
        print('⚪ email_config.json 없음 → 대기(설정 전)')
        return 0
    with open(CONFIG_PATH, encoding='utf-8') as f:
        config = json.load(f)

    mode = resolve_mode(config)                    # ★가드1: config 만 신뢰
    password = os.environ.get('HIWORKS_MAIL_PASSWORD')
    if not password:
        print('⚪ HIWORKS_MAIL_PASSWORD 미설정 → 대기(비번 입력 전)')
        return 0                                   # 비번 준비 전엔 조용히 대기(재시도)

    now = datetime.now(KST)
    # pre-flight: 전 메일 가드 통과 + 첨부 해석 (하나라도 실패 시 예외 → 전체 중단)
    try:
        plan = build_send_plan(mode, req.get('mails', []), config)
    except SendGuardError as e:
        print('❌ 가드 차단: %s' % e)
        send_telegram('🚫 자문지 메일 발송 차단(가드)\n%s\n요청 ts=%s' % (e, ts))
        push_result({'date': now.strftime('%Y-%m-%d'), 'ts': ts, 'mode': mode,
                     'sent': [], 'failed': [], 'blocked': str(e),
                     'processed_at': now.isoformat()})
        return 1
    except Exception as e:
        print('❌ pre-flight 실패: %s' % e)
        send_telegram('❌ 자문지 메일 준비 실패\n%s\n요청 ts=%s' % (str(e)[:200], ts))
        return 1

    # ★가드 통과 후 발송 직전 처리표식 → 발송 도중 크래시해도 재발송 없음(at-most-once)
    mark_processing(ts)
    sent, failed = [], []
    for item in plan:
        key = item['mail'].get('key')
        try:
            msg = build_mime(item['mail'], item['rcpts'], config.get('from', SELF_CANONICAL),
                             item['attachments'])
            smtp_send(config, msg, item['rcpts'], password)
            sent.append(key)
            print('  ✅ %s 발송 (수신 %d)' % (key, len(item['rcpts']['to'])))
        except Exception as e:
            failed.append({'key': key, 'err': str(e)[:200]})
            print('  ❌ %s 실패: %s' % (key, str(e)[:200]))

    result = {'date': now.strftime('%Y-%m-%d'), 'ts': ts, 'mode': mode,
              'sent': sent, 'failed': failed, 'processed_at': now.isoformat()}
    push_result(result)
    if 'compliance' in sent:               # 컴플라이언스 발송 성공 → 증권사 발송 잠금 해제(오늘)
        mark_compliance_sent()
    tag = '[TEST→본인]' if mode == 'test' else '[실발송]'
    summary = '📧 자문지 메일 %s %d통 발송' % (tag, len(sent))
    if failed:
        summary += ', 실패 %d (%s)' % (len(failed), ', '.join(f['key'] for f in failed))
    send_telegram(summary)
    print(summary)
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
