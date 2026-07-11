"""데이터 수집 신선도 점검 → 일별 수집이 2 거래일 이상 멈추면 텔레그램 경보.

배경(2026-06-24): Hotel ADR 일별 스크래퍼가 6/16 이후 조용히 죽었는데(미커밋 VM
크론) 아무 알림이 없어 8일간 방치됨. 일별 수집물이 N 거래일 이상 갱신 안 되면
탐지해 알린다.

배경2(2026-07-02): earnings_calendar_sync GHA가 6/1부터 한 달간 매일 실패(SA 키
stale)했는데 산출물이 repo 밖(구글 캘린더)이라 신선도 점검에 안 잡혀 방치됨.
→ 스케줄(cron) 워크플로의 "마지막 성공 경과일" 점검 추가 (.github/workflows 자동 발견).

판정 원리:
  각 "일별 수집 시리즈"마다 임계값(영업일)을 두고, 최신 데이터 일자가 그만큼 뒤처지면 경보.
  - 순수 일별(거래일) 시리즈: 임계 3 영업일 = "최근 2 거래일 연속 누락"에 해당.
  - 발행 지연이 큰 시리즈(예탁금 T+3, SCFI 주간)는 임계값을 늘려 오탐 방지.
  - 월별/분기별 매크로(ECOS_MACRO 등), 수동입력(fee_revenue), 명칭변경된 레거시 시리즈는 제외.

소스별 최신일자 추출:
  - dataset.csv: 데이터 타입별 max(날짜)
  - *.json: 내부 데이터 일자(있으면) else updated_at

실행:
  python execution/check_data_freshness.py            # 점검 + (경보 시) 텔레그램 발송
  python execution/check_data_freshness.py --dry-run  # 발송 없이 결과만 출력
환경변수: TELEGRAM_BOT_TOKEN(없으면 TELEGRAM_SISYPHE_BOT_TOKEN), TELEGRAM_CHAT_ID
항상 exit 0 (워크플로를 실패시키지 않음).
"""
import argparse
import csv
import json
import os
import sys
from datetime import date, datetime, timezone, timedelta

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── KRX 휴장일(주말 제외 공휴일·대체공휴일·연말휴장). 영업일 계산 정확도용. ──────
#    ★연 1회 갱신 필요. 미등재 연도는 주말만 반영 → 명절 클러스터 false positive 위험.
KR_HOLIDAYS = {
    # 2026 (대체공휴일 8/17 광복절·9/28 추석·10/5 개천절 포함)
    '2026-01-01', '2026-02-16', '2026-02-17', '2026-02-18', '2026-03-02',
    '2026-05-01', '2026-05-05', '2026-05-25', '2026-06-06',
    '2026-08-15', '2026-08-17', '2026-09-24', '2026-09-25', '2026-09-26',
    '2026-09-28', '2026-10-03', '2026-10-05', '2026-10-09', '2026-12-25', '2026-12-31',
    # 2027 (best-effort, 대체공휴일 포함 — 연초 확정 캘린더로 재검증)
    '2027-01-01', '2027-02-05', '2027-02-08', '2027-02-09', '2027-03-01',
    '2027-05-01', '2027-05-05', '2027-05-13', '2027-08-16',
    '2027-09-14', '2027-09-15', '2027-09-16', '2027-10-04', '2027-10-11',
    '2027-12-27', '2027-12-31',
}

# ── 일별(거래일) 수집 시리즈: 데이터타입 → 임계 영업일 ───────────────────────
#   3 = "최근 2 거래일 연속 누락"이면 경보 (정상은 최신=전 거래일이라 gap≈1).
DATASET_DAILY = {
    'INDEX_KR': 3, 'INDEX_US': 3, 'INDEX_GLOBAL': 3, 'FX': 3, 'COMMODITY': 3,
    'KRX_VALUATION': 3, 'ECOS_RATE': 3, 'FRED_RATE': 3, 'INTEREST_RATE': 3,
    'BATTERY_METAL': 4, 'POLY_SILICON': 4, 'SEIBro': 4,  # SEIBro=예탁원 T+1
    'DRAM': 4, 'NAND': 4, 'DRAM_RETAIL': 4,
}
# 발행 지연 큰 dataset 시리즈: (모드, 임계). calendar=달력일, business=영업일
DATASET_LAGGED = {
    'DEPOSIT': ('business', 6),        # 고객예탁금/신용잔고: KOFIA T+3 공표
    'OCEAN_FREIGHT': ('calendar', 11), # SCFI: 주간
    'CRYPTO': ('calendar', 3),         # 24/7
    # SiliconData 지수: 주말 포함 일별, 발행 1~2일 지연. 공개창 7일 → 손실 전(5일) 경보
    'SDLLMTK': ('calendar', 5),
    'SDH100RT': ('calendar', 5),
    'SD_RAM': ('calendar', 5),
}
# 제외(일별 아님): 월·분기 매크로, 수동, 레거시 명칭변경
DATASET_IGNORE = {
    'ECOS_MACRO', 'ECOS_SECTOR', 'FRED_MACRO', 'FRED_SECTOR',
    'INDEX', 'Memory',
    'NPS_FUND',  # 국민연금 적립금: 연간+최신월 저빈도 — 일별 감시 부적합
    'KOSIS_PENSION',  # 퇴직연금 적립금: 연 1회 (통계청 12월 발표)
    'KOSIS_MACRO', 'KOSIS_SECTOR', 'JP_CAPEX',  # KOSIS 월간 (발표 1~2개월 지연)
}

# ── JSON 산출물: 파일 → 임계 영업일 ──────────────────────────────────────────
JSON_DAILY = {
    'disclosures.json': 3, 'kodex_sectors.json': 3, 'landing_highlights.json': 3,
    'featured_data.json': 3, 'featured_news.json': 3, 'investor_trading.json': 3,
    'index_returns.json': 3, 'index_history.json': 3, 'monthly_returns.json': 3,
    'universe.json': 3, 'universe_history.json': 3, 'contribution_data.json': 4,
}
JSON_LAGGED = {'kofia_stats.json': ('business', 6)}

# ── GHA 스케줄 워크플로 무성공 감시 ──────────────────────────────────────────
#   산출물이 repo 밖(구글 캘린더 등)이라 신선도 점검이 못 잡는 실패를 커버.
#   .github/workflows 에서 cron 스케줄 워크플로를 자동 발견 → GitHub API로
#   마지막 success run 경과일 점검. 매일 스케줄=3일, 주중 한정=4일(월요일 오탐 방지).
WORKFLOW_SELF = 'daily_health_check.yml'
WORKFLOW_DIR = os.path.join(ROOT, '.github', 'workflows')
GITHUB_REPO = os.environ.get('GITHUB_REPOSITORY', 'sisyphe10/Antigravity_Market_Dashboard')

# ── 맥미니 이관 잡 heartbeat 감시 (Phase 2) ──────────────────────────────────
#   산출물이 repo 밖(구글 캘린더)이거나 비시계열(finalize)이라 신선도가 못 잡는 잡의
#   '비실행'을 커버. 맥미니 wrapper가 성공 시 heartbeats.json을 [skip ci] push.
#   heartbeats.json = {잡이름: 마지막 성공 epoch(초)}. 이 워치독은 GHA 잔류라 맥미니
#   로컬 stamp를 못 봐 repo 커밋본을 읽는다. ★파일 없음/파싱실패=조용히 skip,
#   존재하는 엔트리만 검사(미이관 잡=엔트리 없음=침묵).
HEARTBEAT_FILE = 'heartbeats.json'
HEARTBEAT_THRESHOLD_DEFAULT = 3          # 매일 잡: 3일 무성공이면 경보
HEARTBEAT_THRESHOLDS = {                 # 잡별 임계(달력일) override
    'gha-earnings-calendar-sync': 2,     # 매일 → 2일
    'gha-finalize-orders': 4,            # 주말 무주문 no-op 감안
}

LABELS = {
    'INDEX_KR': 'KR 지수/외인(INDEX_KR)', 'INDEX_US': '미국 지수(INDEX_US)',
    'INDEX_GLOBAL': '글로벌 지수(NIKKEI/TSEC)', 'FX': '환율(FX)',
    'COMMODITY': '원자재(COMMODITY)', 'KRX_VALUATION': 'KRX PER/PBR/배당',
    'ECOS_RATE': 'ECOS 금리(일별)', 'FRED_RATE': 'FRED 금리(일별)',
    'INTEREST_RATE': '금리(INTEREST_RATE)', 'BATTERY_METAL': '리튬(BATTERY_METAL)',
    'POLY_SILICON': '폴리실리콘', 'SEIBro': 'SEIBro TOP50',
    'DRAM': 'DRAM 현물', 'NAND': 'NAND 현물', 'DRAM_RETAIL': 'DRAM 소매최저가',
    'DEPOSIT': '예탁금/신용잔고', 'OCEAN_FREIGHT': 'SCFI 운임', 'CRYPTO': '암호화폐',
    'SDLLMTK': 'SiliconData LLM 토큰지수', 'SDH100RT': 'SiliconData H100 렌탈지수',
    'SD_RAM': 'SiliconData RAM 지수',
    'disclosures.json': '보유종목 공시', 'kodex_sectors.json': 'KODEX 섹터',
    'landing_highlights.json': '랜딩 하이라이트', 'featured_data.json': 'Featured 랭킹',
    'featured_news.json': 'Featured 뉴스', 'investor_trading.json': '투자자 수급',
    'index_returns.json': '지수 1M(universe RSI)', 'index_history.json': '지수 일별(RSI/MDD)',
    'monthly_returns.json': 'Monthly Returns', 'universe.json': 'Universe',
    'universe_history.json': 'Universe 일별', 'contribution_data.json': '기여도 탭',
    'kofia_stats.json': 'KOFIA 예탁금',
}


def parse_d(s):
    s = str(s).strip()[:10]
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None


def business_days_between(d0: date, d1: date) -> int:
    """d0(제외) ~ d1(포함) 사이 영업일 수(주말+KRX휴장 제외). d1<=d0이면 0."""
    if d1 <= d0:
        return 0
    n = 0
    cur = d0 + timedelta(days=1)
    while cur <= d1:
        if cur.weekday() < 5 and cur.strftime('%Y-%m-%d') not in KR_HOLIDAYS:
            n += 1
        cur += timedelta(days=1)
    return n


def gap(latest: date, today: date, mode: str) -> int:
    if mode == 'calendar':
        return (today - latest).days
    return business_days_between(latest, today)


# ── 소스별 최신일자 추출 ─────────────────────────────────────────────────────
def dataset_type_max(data_dir: str) -> dict:
    out = {}
    path = os.path.join(data_dir, 'dataset.csv')
    with open(path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            d = parse_d(row.get('날짜', ''))
            if not d:
                continue
            t = row.get('데이터 타입', '?')
            if t not in out or d > out[t]:
                out[t] = d
    return out


def json_top_field_date(path: str, field: str):
    """JSON 최상위 특정 필드의 날짜(예: universe.json의 data_date). 없으면 None."""
    try:
        obj = json.load(open(path, encoding='utf-8'))
    except Exception:
        return None
    return parse_d(obj.get(field)) if isinstance(obj, dict) else None


def json_data_date(path: str, today: date):
    """내부 데이터 일자 우선, 없으면 updated_at 일자. 미래 날짜(스케줄/만기 등)는 today로 상한."""
    try:
        obj = json.load(open(path, encoding='utf-8'))
    except Exception:
        return None
    best = None

    def consider(s):
        nonlocal best
        d = parse_d(s)
        if d and date(2024, 1, 1) <= d <= today:
            if best is None or d > best:
                best = d

    def walk(o, depth):
        if depth > 7:
            return
        if isinstance(o, str):
            consider(o)
        elif isinstance(o, dict):
            for k, v in o.items():
                consider(k)
                walk(v, depth + 1)
        elif isinstance(o, list):
            for v in o:
                walk(v, depth + 1)

    walk(obj, 0)
    if best is None and isinstance(obj, dict):
        for k in ('updated_at', 'updated', 'last_updated'):
            if isinstance(obj.get(k), str):
                consider(obj[k])
    return best


def scheduled_workflows():
    """cron 스케줄이 있는 워크플로 자동 발견 → [(파일명, 임계 달력일)].
    dow 필드가 '*'가 아니면(주중 한정 등) 4일, 매일이면 3일."""
    out = []
    try:
        names = sorted(os.listdir(WORKFLOW_DIR))
    except OSError:
        return out
    for fn in names:
        if not fn.endswith(('.yml', '.yaml')) or fn == WORKFLOW_SELF:
            continue
        try:
            with open(os.path.join(WORKFLOW_DIR, fn), encoding='utf-8') as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        crons = [ln.split('cron:', 1)[1].split('#')[0].strip().strip('\'"')
                 for ln in lines if 'cron:' in ln and not ln.lstrip().startswith('#')]
        if not crons:
            continue
        fields = crons[0].split()
        weekday_only = len(fields) == 5 and fields[4] != '*'
        out.append((fn, 4 if weekday_only else 3))
    return out


def _gh_api(path: str):
    """GitHub API GET(json). 실패 시 예외 전파."""
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com/repos/{GITHUB_REPO}{path}", headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': 'antigravity-health-check'})
    tok = os.environ.get('GITHUB_TOKEN')
    if tok:
        req.add_header('Authorization', f'Bearer {tok}')
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def workflow_states():
    """파일명 → state('active'/'disabled_manually'…) 일괄 조회. 실패 시 None(판별 불가)."""
    try:
        wfs = _gh_api('/actions/workflows?per_page=100').get('workflows', [])
        return {w.get('path', '').rsplit('/', 1)[-1]: w.get('state', '') for w in wfs}
    except Exception as e:
        print(f"  ⚠️ workflow 목록 API 실패: {e}")
        return None


def workflow_last_success(fn: str):
    """워크플로 최신 success run의 KST 일자. 성공 이력 없음=None, API 오류='ERR'.
    updated_at 사용: 옛 실패 run을 나중에 rerun 성공시켜도 최근 성공으로 인정."""
    try:
        runs = _gh_api(f'/actions/workflows/{fn}/runs?status=success&per_page=1'
                       ).get('workflow_runs', [])
    except Exception as e:
        print(f"  ⚠️ workflow API 실패({fn}): {e}")
        return 'ERR'
    if not runs:
        return None
    ts = runs[0].get('updated_at') or runs[0]['created_at']
    dt = datetime.strptime(ts, '%Y-%m-%dT%H:%M:%SZ')
    return dt.replace(tzinfo=timezone.utc).astimezone(KST).date()


def check_workflows(today: date):
    """스케줄 워크플로 경보 리스트: [(파일명, 마지막성공일|None|'ERR', 경과일, 임계)]"""
    alerts = []
    states = workflow_states()
    for fn, thr in scheduled_workflows():
        if states is not None and states.get(fn, 'active') != 'active':
            print(f"  (skip) {fn} — 비활성 워크플로 ({states.get(fn)})")
            continue
        last = workflow_last_success(fn)
        if last == 'ERR':
            alerts.append((fn, 'ERR', None, thr))
        elif last is None:
            alerts.append((fn, None, None, thr))
        else:
            g = (today - last).days
            if g >= thr:
                alerts.append((fn, last, g, thr))
    return alerts


def check_heartbeats(data_dir: str, today: date):
    """맥미니 이관 잡의 heartbeat 정체 경보: [(잡이름, 마지막성공일, 경과일, 임계)].
    heartbeats.json 없음/파싱 실패 → 조용히 skip. 파일에 존재하는 엔트리만 검사
    (미이관 잡=엔트리 없음=침묵). 값이 epoch(초)가 아니면 그 엔트리만 조용히 무시."""
    path = os.path.join(data_dir, HEARTBEAT_FILE)
    if not os.path.exists(path):
        return []
    try:
        hb = json.load(open(path, encoding='utf-8'))
    except Exception:
        return []
    if not isinstance(hb, dict):
        return []
    alerts = []
    for job, ts in hb.items():
        thr = HEARTBEAT_THRESHOLDS.get(job, HEARTBEAT_THRESHOLD_DEFAULT)
        try:
            last = datetime.fromtimestamp(float(ts), tz=KST).date()
        except (TypeError, ValueError, OSError, OverflowError):
            continue
        g = (today - last).days
        if g >= thr:
            alerts.append((job, last, g, thr))
    return alerts


def check(data_dir: str, today: date):
    """경보 항목 리스트 반환: [(label, latest, gap_value, mode, threshold)]"""
    alerts = []
    dmax = dataset_type_max(data_dir)

    def add(label, latest, mode, thr):
        if latest is None:
            alerts.append((label, None, None, mode, thr))  # 데이터 자체 없음
            return
        g = gap(latest, today, mode)
        if g >= thr:
            alerts.append((label, latest, g, mode, thr))

    for typ, thr in DATASET_DAILY.items():
        add(LABELS.get(typ, typ), dmax.get(typ), 'business', thr)
    for typ, (mode, thr) in DATASET_LAGGED.items():
        add(LABELS.get(typ, typ), dmax.get(typ), mode, thr)
    for fn, thr in JSON_DAILY.items():
        p = os.path.join(data_dir, fn)
        if fn == 'universe.json':
            # values 배열엔 날짜가 없어 walk가 updated_at(매 run now)로 폴백 → 전면 carry-forward
            # stale을 못 잡음. fetch_universe가 쓰는 data_date(실제 시세일)를 우선 사용.
            latest = json_top_field_date(p, 'data_date') or json_data_date(p, today)
        else:
            latest = json_data_date(p, today)
        add(LABELS.get(fn, fn), latest, 'business', thr)
    for fn, (mode, thr) in JSON_LAGGED.items():
        add(LABELS.get(fn, fn), json_data_date(os.path.join(data_dir, fn), today), mode, thr)
    return alerts


def build_message(alerts, wf_alerts, hb_alerts, today: date) -> str:
    lines = [f"\U0001F6A8 데이터 수집 점검 경보 ({today})"]
    if alerts:
        lines += ["", "다음 일별 수집이 임계 이상 멈췄습니다:", ""]
        for label, latest, g, mode, thr in sorted(alerts, key=lambda a: (a[2] is not None, -(a[2] or 10**9))):
            unit = '일' if mode == 'calendar' else '영업일'
            if latest is None:
                lines.append(f"• {label} — 데이터 없음")
            else:
                lines.append(f"• {label} — 최신 {latest.strftime('%m-%d')} ({g}{unit} 지연, 임계 {thr})")
    if wf_alerts:
        lines += ["", "GHA 스케줄 워크플로 무성공:", ""]
        for fn, last, g, thr in wf_alerts:
            name = fn[:-4] if fn.endswith('.yml') else fn
            if last == 'ERR':
                lines.append(f"• {name} — 점검 API 실패 (수동 확인 필요)")
            elif last is None:
                lines.append(f"• {name} — 성공 이력 없음")
            else:
                lines.append(f"• {name} — 마지막 성공 {last.strftime('%m-%d')} ({g}일 경과, 임계 {thr})")
    if hb_alerts:
        lines += ["", "맥미니 잡 heartbeat 정체:", ""]
        for job, last, g, thr in hb_alerts:
            lines.append(f"• 맥미니 잡 {job} heartbeat 정체 {g}일 (마지막 성공 {last.strftime('%m-%d')}, 임계 {thr})")
    lines += ["", "정상 항목은 생략. (자동 점검 · check_data_freshness.py)"]
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    import urllib.request
    import urllib.parse
    token = os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('TELEGRAM_SISYPHE_BOT_TOKEN')
    chat = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        print("  ⚠️ TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 미설정 → 발송 생략")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({'chat_id': chat, 'text': text,
                                   'disable_web_page_preview': 'true'}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            ok = r.status == 200
            print(f"  텔레그램 발송 {'성공' if ok else 'HTTP '+str(r.status)}")
            return ok
    except Exception as e:
        print(f"  ⚠️ 텔레그램 발송 실패: {e}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='발송 없이 결과만 출력')
    ap.add_argument('--data-dir', default=ROOT, help='데이터 파일 디렉토리(테스트용)')
    ap.add_argument('--today', default=None, help='기준일 YYYY-MM-DD(테스트용)')
    args = ap.parse_args()

    today = parse_d(args.today) if args.today else datetime.now(tz=KST).date()
    print(f"기준일: {today} ({today.strftime('%A')})  data-dir={args.data_dir}")

    alerts = check(args.data_dir, today)
    wf_alerts = check_workflows(today)
    hb_alerts = check_heartbeats(args.data_dir, today)
    if not alerts and not wf_alerts and not hb_alerts:
        print("✅ 일별 수집·GHA 워크플로·맥미니 heartbeat 전부 정상 (경보 없음)")
        return

    msg = build_message(alerts, wf_alerts, hb_alerts, today)
    print("\n" + msg + "\n")
    if args.dry_run:
        print("[dry-run] 발송 생략")
    else:
        send_telegram(msg)


if __name__ == '__main__':
    main()
