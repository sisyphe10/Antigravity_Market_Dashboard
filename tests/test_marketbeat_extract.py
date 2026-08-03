# -*- coding: utf-8 -*-
"""marketbeat 전문 컨테이너 추출 회귀 테스트 (2026-08-03, GRMN 크롬 거부 사고)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bs4 import BeautifulSoup

from execution.earnings_bot.transcript_sources.marketbeat import MarketBeatSource
from execution.earnings_bot.transcript_sources.motley_fool import MotleyFoolSource

FIXTURE = os.path.join(os.path.dirname(__file__), 'transcript_fixtures',
                       'grmn_2q26_marketbeat_page.html')


def test_container_extraction_removes_chrome():
    with open(FIXTURE, encoding='utf-8', errors='ignore') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
    el = MarketBeatSource.extract_transcript_container(soup)
    assert el is not None
    text = el.get_text('\n', strip=True)
    # 콜 본문으로 시작 (페이지 크롬·AI Key Takeaways 없음)
    assert text.lstrip().startswith('Operator')
    assert 'Actual EPS' not in text
    assert 'Key Takeaways' not in text
    assert 'Learn more.' not in text
    assert len(text) > 25000
    # 클린 텍스트에서 분할도 성립
    prepared, qa = MotleyFoolSource()._split_sections(text)
    assert 'Actual EPS' not in prepared
    assert len(prepared) > 5000
    assert qa, '클린 컨테이너에서 Q&A 경계를 찾아야 함'


def test_container_absent_returns_none():
    soup = BeautifulSoup('<html><body><article>hello</article></body></html>',
                         'html.parser')
    assert MarketBeatSource.extract_transcript_container(soup) is None
