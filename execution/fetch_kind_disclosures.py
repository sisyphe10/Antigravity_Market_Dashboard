"""KIND 거래소 안내공시 수집 → disclosures.json에 누적 (source='KIND').

DART와의 중복 없이 거래소 고유 안내공시(매매거래정지/관리종목/단기과열/조회공시/
상장폐지/공시번복·불이행 등)만 수집해서 fetch_disclosures.py가 만든 disclosures.json에
KIND 항목을 append. 보유 종목 (portfolio_data.json) 매칭으로 필터.

KIND endpoint: POST https://kind.krx.co.kr/disclosure/todaydisclosure.do
- selDate=YYYY-MM-DD로 일별 모든 공시
- 종목명 기반 매칭 (KIND 응답에 종목코드 직접 포함 안 됨, companysummary_open의
  내부 ID는 KIND 자체 corp_code라 KRX 종목코드와 다름)

워크플로:
  1. portfolio_data.json → 보유 종목명 집합
  2. KIND 일별 공시 fetch (어제, 오늘)
  3. 거래소 안내공시 키워드 매칭 + 보유 종목명 매칭
  4. acptNo 기준 dedup (기존 disclosures.json items 검사)
  5. disclosures.json에 source='KIND' 항목 append

출력 disclosures.json items 스키마 (DART/KIND 공통, source로만 구분):
  {"rcept_no" or "acpt_no": "20260526000917", "code": "", "name": "코리아써키트",
   "date": "2026-05-26", "title": "매매거래정지 예고", "summary": "...",
   "url": "https://kind.krx.co.kr/common/disclsviewer.do?...", "source": "KIND"}

소스 구분 필드 'source'를 disclosures.json에 추가 (기존 DART는 source 누락 = 'DART'로 fallback).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
PORTFOLIO_FILE = ROOT / 'portfolio_data.json'
DISCLOSURES_FILE = ROOT / 'disclosures.json'

# 거래소 고유 안내공시 키워드 (DART와 겹치지 않는 거래소 발표 공시)
EXCHANGE_KW = (
    '매매거래정지', '매매거래 정지', '매매거래재개', '매매거래 재개',
    '관리종목 지정', '관리종목지정', '관리종목 해제', '관리종목해제',
    '단기과열', '상장폐지', '주권매매거래정지',
    '조회공시 요구', '조회공시요구',
    '공시번복', '공시불이행', '불성실공시법인',
    '주식분할', '주식병합',
    '투자위험종목 지정해제', '투자위험종목 최초지정',  # 시장감시위원회
)

SUMMARY_CHARS = 300


def _portfolio_names() -> set[str]:
    """portfolio_data.json에서 보유 종목명 set."""
    if not PORTFOLIO_FILE.exists():
        return set()
    with open(PORTFOLIO_FILE, encoding='utf-8') as f:
        d = json.load(f)
    names: set[str] = set()
    for pf, stocks in d.items():
        if pf.startswith('_'):
            continue
        for s in stocks:
            n = (s.get('name') or '').strip()
            if n:
                names.add(n)
    return names


def _load_disclosures() -> dict:
    if DISCLOSURES_FILE.exists():
        with open(DISCLOSURES_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {'updated_at': None, 'items': []}


def _fetch_kind_day(session: requests.Session, date_str: str) -> list[dict]:
    """KIND todaydisclosure.do — 해당 날짜 전체 공시 리스트 (raw rows)."""
    data = {
        'method': 'searchTodayDisclosureSub',
        'forward': 'todaydisclosure_sub',
        'currentPageSize': '500',
        'pageIndex': '1',
        'orderMode': '0',
        'orderStat': 'D',
        'marketType': '',
        'searchCorpName': '',
        'searchType': 'A',
        'keyword': '',
        'todayFlag': 'N',
        'selDate': date_str,
    }
    resp = session.post(
        'https://kind.krx.co.kr/disclosure/todaydisclosure.do',
        data=data,
        headers={'Referer': 'https://kind.krx.co.kr/disclosure/todaydisclosure.do?method=searchTodayDisclosureMain'},
        timeout=20,
    )
    resp.encoding = 'utf-8'
    soup = BeautifulSoup(resp.text, 'html.parser')
    rows: list[dict] = []
    for tr in soup.find_all('tr'):
        cells = tr.find_all('td')
        if len(cells) < 4:
            continue
        time_str = cells[0].get_text(strip=True)
        name = cells[1].get_text(strip=True)
        title = cells[2].get_text(strip=True)
        submitter = cells[3].get_text(strip=True)
        # acptNo는 cells[2]의 a.onclick에서 추출: openDisclsViewer('20260526000917', '')
        a = cells[2].find('a')
        m = re.search(r"openDisclsViewer\('(\d+)'", a.get('onclick', '')) if a else None
        acpt_no = m.group(1) if m else ''
        rows.append({
            'time': time_str,
            'name': name,
            'title': title,
            'submitter': submitter,
            'acpt_no': acpt_no,
            'date': date_str,
        })
    return rows


def main() -> None:
    portfolio_names = _portfolio_names()
    if not portfolio_names:
        print("portfolio_data.json에 보유 종목 없음 — 종료")
        return
    print(f"보유 종목: {len(portfolio_names)}개")

    existing = _load_disclosures()
    seen_keys = set()
    for it in existing.get('items', []):
        # DART는 rcept_no, KIND는 acpt_no. 둘 다 unique. KIND는 'kind:{acpt_no}' 접두로 격리.
        if it.get('source') == 'KIND':
            seen_keys.add(f"kind:{it.get('rcept_no') or it.get('acpt_no')}")
        else:
            seen_keys.add(f"dart:{it.get('rcept_no')}")
    print(f"기존 누적: {len(existing.get('items', []))}건 (KIND/DART 합)")

    # 어제~오늘 KIND 공시 fetch (시점 차이로 누락 방지)
    today = datetime.now(KST).date()
    dates = [today - timedelta(days=1), today]
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    # session init
    session.get('https://kind.krx.co.kr/disclosure/todaydisclosure.do?method=searchTodayDisclosureMain', timeout=15)

    new_items: list[dict] = []
    for d in dates:
        ds = d.strftime('%Y-%m-%d')
        try:
            rows = _fetch_kind_day(session, ds)
        except Exception as e:
            print(f"  {ds} KIND fetch 실패: {e}")
            continue
        for r in rows:
            # 1. 거래소 안내공시 키워드 매칭
            if not any(k in r['title'] for k in EXCHANGE_KW):
                continue
            # 2. 보유 종목명 매칭 — KIND 종목명에는 우선주명(예: '코리아써키트우')이 있을 수 있어
            #    portfolio name이 부분문자열로 포함되는지 검사
            matched_name = None
            for pn in portfolio_names:
                if pn == r['name'] or pn in r['name']:
                    matched_name = pn
                    break
            if not matched_name:
                continue
            # 3. dedup
            if not r['acpt_no']:
                continue
            key = f"kind:{r['acpt_no']}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            # 4. 항목 생성 (summary는 제목 + 제출인 + 시각 정도)
            summary = f"{r['submitter']} · {r['time']}"
            new_items.append({
                'rcept_no': r['acpt_no'],  # DART와 같은 필드명으로 통일 (UI 호환)
                'code': '',
                'name': matched_name,
                'date': r['date'],
                'title': r['title'],
                'summary': summary,
                'url': f"https://kind.krx.co.kr/common/disclsviewer.do?method=search&acptNo={r['acpt_no']}",
                'source': 'KIND',
            })
            print(f"  +{matched_name} | {r['title'][:50]}")

    print(f"\n신규 KIND: {len(new_items)}건")
    if new_items:
        # 누적 + 날짜 내림차순
        merged = existing.get('items', []) + new_items
        merged.sort(key=lambda x: (x.get('date', ''), x.get('rcept_no', '')), reverse=True)
        existing['items'] = merged
        existing['updated_at'] = datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')
        with open(DISCLOSURES_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        print(f"[성공] disclosures.json: 총 {len(merged)}건 (+{len(new_items)} KIND 신규)")
    else:
        print("[변경 없음]")


if __name__ == '__main__':
    main()
