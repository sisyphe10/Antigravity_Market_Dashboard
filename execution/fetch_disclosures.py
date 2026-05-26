"""DART 공시 수집 → disclosures.json (누적, 매일 1회)

워크플로:
  1. portfolio_data.json의 현재 보유 종목코드 수집 (그룹 portfolio 중복 dedup)
  2. corp_codes.json이 없거나 7일 넘었으면 DART CORPCODE.xml 재다운로드
  3. 각 종목 corp_code로 list.json 호출 (bgn_de = 마지막 수집일 + 1, 기본 오늘부터)
  4. 신규 rcept_no만 추출 → document.xml 다운로드 → 첫 300자 요약
  5. disclosures.json에 누적 저장 (날짜 내림차순)

DART API 키는 환경변수 DART_API_KEY (.secrets/dart_api_keys.env 또는 GHA secret).

출력 스키마 (disclosures.json):
  {
    "updated_at": "2026-05-26 18:00 KST",
    "items": [
      {"rcept_no", "code", "name", "date" (YYYY-MM-DD), "title", "summary", "url"},
      ...
    ]
  }
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
PORTFOLIO_FILE = ROOT / 'portfolio_data.json'
DISCLOSURES_FILE = ROOT / 'disclosures.json'
CORP_CODES_FILE = ROOT / 'corp_codes.json'
CORP_CODES_TTL_DAYS = 7
DART_BASE = 'https://opendart.fss.or.kr/api'
USER_AGENT = 'Mozilla/5.0 (sisyphe10/Antigravity_Market_Dashboard)'
SUMMARY_CHARS = 300


def _load_api_key() -> str:
    key = os.environ.get('DART_API_KEY')
    if key:
        return key
    candidates = [
        ROOT / '.env',
        Path.home() / '.secrets' / 'dart_api_keys.env',
    ]
    for path in candidates:
        if path.exists():
            load_dotenv(path)
            key = os.environ.get('DART_API_KEY')
            if key:
                return key
    raise RuntimeError("DART_API_KEY 미설정 (env or .env or ~/.secrets/dart_api_keys.env)")


def _load_corp_codes(api_key: str) -> dict[str, str]:
    """stock_code(6자리) → corp_code(8자리) 매핑. cache_ttl 초과 시 DART에서 재다운로드."""
    fresh = False
    if CORP_CODES_FILE.exists():
        mtime = datetime.fromtimestamp(CORP_CODES_FILE.stat().st_mtime, tz=KST)
        age = datetime.now(KST) - mtime
        if age < timedelta(days=CORP_CODES_TTL_DAYS):
            fresh = True
    if fresh:
        with open(CORP_CODES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

    print(f"corp_codes.json 재다운로드 중 (DART CORPCODE.xml)...")
    r = requests.get(f'{DART_BASE}/corpCode.xml', params={'crtfc_key': api_key}, timeout=60)
    r.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    with zf.open('CORPCODE.xml') as fp:
        tree = ET.parse(fp)
    mapping: dict[str, str] = {}
    for item in tree.getroot().findall('list'):
        stock_code = (item.findtext('stock_code') or '').strip()
        corp_code = (item.findtext('corp_code') or '').strip()
        if stock_code and corp_code and len(stock_code) == 6:
            mapping[stock_code] = corp_code
    with open(CORP_CODES_FILE, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False)
    print(f"  → {len(mapping)}개 종목 매핑 저장")
    return mapping


def _load_disclosures() -> dict:
    if DISCLOSURES_FILE.exists():
        with open(DISCLOSURES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'updated_at': None, 'items': []}


def _list_disclosures(api_key: str, corp_code: str, bgn_de: str, end_de: str) -> list[dict]:
    """단일 종목의 공시 목록 (DART list.json). page_count=100, page_no 페이징."""
    all_items: list[dict] = []
    for page_no in range(1, 11):  # 최대 1000건
        params = {
            'crtfc_key': api_key,
            'corp_code': corp_code,
            'bgn_de': bgn_de,
            'end_de': end_de,
            'page_count': 100,
            'page_no': page_no,
        }
        r = requests.get(f'{DART_BASE}/list.json', params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        status = data.get('status')
        if status == '013':  # 조회된 데이터 없음
            break
        if status != '000':
            print(f"  Warning: list.json status={status} ({data.get('message')}) corp={corp_code}")
            break
        items = data.get('list') or []
        all_items.extend(items)
        if len(items) < 100:
            break
        time.sleep(0.1)
    return all_items


def _fetch_document_summary(api_key: str, rcept_no: str) -> str:
    """document.xml에서 본문 텍스트 추출 → 첫 SUMMARY_CHARS 자.
    DART XBRL은 상단에 <style>...</style> CSS 블록이 박혀있어 단순 태그 제거로는
    'xforms_title { font-size...' 같은 노이즈가 섞임. style/script 블록 통째로 제거 후 추출."""
    try:
        r = requests.get(f'{DART_BASE}/document.xml', params={'crtfc_key': api_key, 'rcept_no': rcept_no}, timeout=30)
        r.raise_for_status()
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        xml_names = [n for n in zf.namelist() if n.lower().endswith('.xml')]
        if not xml_names:
            return ''
        with zf.open(xml_names[0]) as fp:
            raw = fp.read().decode('utf-8', errors='ignore')
        # style/script 블록 통째 제거 (DART XBRL는 첫부분에 CSS 블록 박혀있음)
        text = re.sub(r'<style[^>]*>.*?</style>', ' ', raw, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
        # 모든 태그 제거 + HTML entity 제거 + 공백 정리
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'&(?:[a-zA-Z]+|#\d+);', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:SUMMARY_CHARS]
    except Exception as e:
        print(f"  Warning: document.xml 실패 ({rcept_no}): {e}")
        return ''


def _portfolio_stocks() -> dict[str, str]:
    """portfolio_data.json에서 현재 보유 종목코드 → 종목명 dict (중복 제거)."""
    if not PORTFOLIO_FILE.exists():
        raise RuntimeError(f"{PORTFOLIO_FILE} 없음")
    with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    out: dict[str, str] = {}
    for pf, stocks in data.items():
        if pf.startswith('_'):
            continue
        for s in stocks:
            code = str(s.get('code') or '').strip()
            if len(code) == 6:
                out[code] = s.get('name') or code
    return out


def main() -> None:
    api_key = _load_api_key()
    print(f"DART API key loaded (len={len(api_key)})")
    corp_map = _load_corp_codes(api_key)
    stocks = _portfolio_stocks()
    print(f"보유 종목: {len(stocks)}개")

    existing = _load_disclosures()
    seen_rcept = {item['rcept_no'] for item in existing.get('items', [])}
    print(f"기존 누적: {len(seen_rcept)}건")

    # 조회 구간: 사용자 요구는 "오늘부터 누적". 매일 cron이라 bgn=어제, end=오늘 (overlap 보호).
    today = datetime.now(KST).date()
    bgn_de = (today - timedelta(days=1)).strftime('%Y%m%d')
    end_de = today.strftime('%Y%m%d')
    print(f"조회 구간: {bgn_de} ~ {end_de}")

    new_items: list[dict] = []
    for code, name in sorted(stocks.items()):
        corp_code = corp_map.get(code)
        if not corp_code:
            print(f"  {code} ({name}): corp_code 매핑 없음, skip")
            continue
        items = _list_disclosures(api_key, corp_code, bgn_de, end_de)
        if not items:
            continue
        added = 0
        for it in items:
            rcept_no = (it.get('rcept_no') or '').strip()
            if not rcept_no or rcept_no in seen_rcept:
                continue
            seen_rcept.add(rcept_no)
            date_str = (it.get('rcept_dt') or '').strip()
            date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}" if len(date_str) == 8 else date_str
            title = (it.get('report_nm') or '').strip()
            summary = _fetch_document_summary(api_key, rcept_no)
            time.sleep(0.1)
            url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
            new_items.append({
                'rcept_no': rcept_no,
                'code': code,
                'name': name,
                'date': date_fmt,
                'title': title,
                'summary': summary,
                'url': url,
            })
            added += 1
        if added:
            print(f"  {code} {name}: +{added}건")

    print(f"\n신규 공시: {len(new_items)}건")

    # 누적 + 날짜 내림차순 정렬
    merged = existing.get('items', []) + new_items
    merged.sort(key=lambda x: (x.get('date', ''), x.get('rcept_no', '')), reverse=True)

    out = {
        'updated_at': datetime.now(KST).strftime('%Y-%m-%d %H:%M KST'),
        'items': merged,
    }
    with open(DISCLOSURES_FILE, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[성공] disclosures.json: 총 {len(merged)}건 (+{len(new_items)} 신규)")


if __name__ == '__main__':
    main()
