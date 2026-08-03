# -*- coding: utf-8 -*-
"""_split_sections (parser 1.1) 회귀 테스트.

픽스처: tests/transcript_fixtures/ccj_2q26_marketbeat_reconstructed.txt
  — 2026-07-31 CCJ 2Q26 marketbeat 전문 (DB transcripts id=234 prepared+qa 재구성).
  Operator 오프닝의 "wait until the Q&A session" / IR 멘트 "During the Q&A session"
  이 루즈 정규식(≤1.0)을 오분할시킨 실사고 케이스.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from execution.earnings_bot.transcript_sources.motley_fool import MotleyFoolSource

FIXTURE = os.path.join(os.path.dirname(__file__), 'transcript_fixtures',
                       'ccj_2q26_marketbeat_reconstructed.txt')


def _load_ccj() -> str:
    with open(FIXTURE, encoding='utf-8') as f:
        return f.read()


def test_ccj_2q26_operator_transition_split():
    """경영진 발표(Cory Kos·Tim Gitzel)는 prepared, Q&A 개시 선언부터 qa."""
    text = _load_ccj()
    prepared, qa = MotleyFoolSource()._split_sections(text)
    # 발표부가 prepared에 남아야 한다
    assert 'Cory Kos' in prepared
    assert 'we are now ready to take questions' in prepared
    # Q&A 개시 선언(Operator 헤더 스냅)부터 qa
    assert 'begin the question and answer session' in qa[:600]
    assert 'Brian Lee' in qa  # 첫 질문자
    # 오프닝 boilerplate의 "Q&A" 언급에서 잘리지 않았다 (구버전 오분할 지점)
    assert 'wait until the' in prepared and 'Q&A session before submitting' in prepared


def test_ccj_2q26_no_premature_split():
    """분할점이 발표부 이후여야 한다 — prepared가 실제 발표 분량(>10K자)."""
    text = _load_ccj()
    prepared, qa = MotleyFoolSource()._split_sections(text)
    assert len(prepared) > 10000, f'prepared={len(prepared)}자 — 오프닝에서 조기 분할 의심'
    assert len(qa) > 30000


def test_fool_style_header_line_split():
    """fool.com형 독립 줄 섹션 헤더."""
    text = (
        'PREPARED REMARKS\n'
        'Operator:\n'
        'Good morning. During the Q&A session, please limit yourself to one question.\n'
        'Jane Doe -- Chief Executive Officer\n'
        + ('Great quarter. ' * 300) + '\n'
        'QUESTIONS AND ANSWERS\n'
        'Operator:\n'
        'Our first question comes from John Analyst.\n'
        'John Analyst -- Big Bank -- Analyst\n'
        'Thanks for taking my question.\n'
    )
    prepared, qa = MotleyFoolSource()._split_sections(text)
    assert 'Great quarter' in prepared
    assert 'Q&A session, please limit' in prepared  # 문장 속 언급은 신호 아님
    assert qa.startswith('QUESTIONS AND ANSWERS')
    assert 'John Analyst' in qa


def test_no_confident_boundary_returns_whole_prepared():
    """경계 신호가 없으면 무분할 — 오분할보다 안전."""
    text = (
        'Operator:\n'
        'Welcome. We ask that you wait until the Q&A session before submitting questions.\n'
        'Jane Doe -- Chief Executive Officer\n'
        + ('Steady progress this quarter. ' * 200)
    )
    prepared, qa = MotleyFoolSource()._split_sections(text)
    assert qa == ''
    assert 'Steady progress' in prepared


def test_opening_safe_harbor_not_trimmed():
    """오프닝 Safe Harbor의 "Forward-Looking Statements"로 본문이 잘리면 안 된다."""
    text = (
        'Operator:\n'
        'Welcome.\n'
        'Forward-Looking Statements\n'
        'This call contains forward-looking statements.\n'
        'Jane Doe -- Chief Executive Officer\n'
        + ('Body content here. ' * 500)
    )
    prepared, qa = MotleyFoolSource()._split_sections(text)
    assert len(prepared) > 5000  # 본문이 살아 있다
