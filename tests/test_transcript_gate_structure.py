# -*- coding: utf-8 -*-
"""check_structure + 승격된 비율 게이트 회귀 테스트 (2026-08-03)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from execution.earnings_bot.transcript_gate import (
    check_structure, check_translation, PREP_HEADER, QA_HEADER,
    MIN_TRANSLATION_RATIO, MAX_TRANSLATION_RATIO)

PREP_EN = 'Good morning. ' * 200          # 2,800자
QA_EN = 'Question and answer. ' * 300     # 6,300자
PREP_KR = '좋은 아침입니다. ' * 150
QA_KR = '질문과 답변입니다. ' * 320


def _kr(prep=True, qa=True):
    parts = []
    if prep:
        parts.append(f'{PREP_HEADER}\n\n{PREP_KR}')
    if qa:
        parts.append(f'{QA_HEADER}\n\n{QA_KR}')
    return '\n\n'.join(parts)


def test_healthy_structure_passes():
    g = check_structure(PREP_EN, QA_EN, _kr())
    assert g.ok, g.reasons


def test_missing_prepared_section_blocked():
    """CCJ 사고 유형 — 발표부 원문이 있는데 번역에 발표 섹션이 없음."""
    g = check_structure(PREP_EN, QA_EN, _kr(prep=False))
    assert not g.ok
    assert any('prep_header' in r for r in g.reasons)


def test_qa_header_hallucination_blocked():
    """원문 Q&A가 없는데(무분할 행) 번역에 Q&A 헤더가 생기면 차단."""
    g = check_structure(PREP_EN, '', _kr())
    assert not g.ok
    assert 'qa_header_hallucinated' in g.reasons


def test_no_split_row_passes_without_qa_header():
    g = check_structure(PREP_EN, '', _kr(qa=False))
    assert g.ok, g.reasons


def test_section_ratio_low_blocked():
    """전체 비율은 정상인데 발표 섹션만 뭉텅 탈락한 경우."""
    thin = f'{PREP_HEADER}\n\n짧음\n\n{QA_HEADER}\n\n{QA_KR * 2}'
    g = check_structure(PREP_EN, QA_EN, thin)
    assert not g.ok
    assert any('prep_section_ratio_low' in r for r in g.reasons)


def test_ratio_hard_bounds():
    raw = PREP_EN + '\n' + QA_EN
    tiny = '너무 짧은 번역'
    g = check_translation(raw, tiny)
    assert not g.ok and any('translation_ratio_low' in r for r in g.reasons)
    bloat = _kr() * 4
    g2 = check_translation(raw, bloat, prepared=PREP_EN, qa=QA_EN)
    assert any('translation_ratio_high' in r for r in g2.reasons)
    assert 0 < MIN_TRANSLATION_RATIO < MAX_TRANSLATION_RATIO
