"""독약 루프 차단 + 인덱스 페이지 URL 게이트 회귀 테스트 (2026-08-22).

배경: 오수집 tid 284(marketbeat 허브 페이지)가 청크 게이트에 매번 걸리며
night_llm 배치 60슬롯을 이틀 연속 전부 소진한 실사고.
DB·LLM 무접촉 — translator/store 함수는 전부 모킹.

실행: cd repo && PYTHONPATH=$PWD venv/bin/python3 -m pytest execution/earnings_bot/tests_poison_loop.py -q
"""
import json

from execution.earnings_bot import analysis_store, headless_llm, night_llm, transcript_store, translator
from execution.earnings_bot.transcript_gate import check_source

FILED = '2026-08-19'

# ── L1: url_index_page ───────────────────────────────────────────

BAD_URLS = [
    'https://www.marketbeat.com/earnings/transcripts/',      # 실사고 허브 (tid 284)
    'https://www.marketbeat.com/earnings/transcripts',       # 슬래시 없음
    'https://www.marketbeat.com/earnings/',                  # 섹션 루트
    'https://www.marketbeat.com/stocks/NASDAQ/ADI/earnings/',        # 랜딩 (GOOGL·TSLA 7/23 동형)
    'https://www.marketbeat.com/stocks/NYSE/BRK.B/earnings/?p=1',    # 랜딩+쿼리
]
GOOD_URLS = [
    'https://www.marketbeat.com/earnings/reports/2026-8-19-analog-devices-inc-stock/',  # 정상 리포트
    'https://www.marketbeat.com/earnings/transcripts/some-detail-slug/',                # 상세 슬러그
    'https://www.fool.com/earnings/call-transcripts/2026/08/19/analog-adi-q3/',         # 타 소스
    'https://notmarketbeat.com/earnings/',                                              # 호스트 경계
]


def test_index_urls_rejected():
    for u in BAD_URLS:
        g = check_source(u, FILED)
        assert not g.ok and 'url_index_page' in g.reasons, u


def test_legit_urls_pass():
    for u in GOOD_URLS:
        g = check_source(u, FILED)
        assert 'url_index_page' not in g.reasons, u


# ── night_llm: 실행 내 실패 항목 재선택 제외 ─────────────────────

def _stub_common(monkeypatch):
    monkeypatch.setattr(headless_llm, 'preflight', lambda: None)
    monkeypatch.setattr(analysis_store, 'publish_pending', lambda limit=50: [])
    monkeypatch.setattr(transcript_store, 'save_pending', lambda limit=60: [])
    monkeypatch.setattr(night_llm, 'DEADLINE_HHMM', '23:59')


def _run_main(capsys):
    rc = night_llm.main()
    out = capsys.readouterr().out.strip().splitlines()[-1]
    return rc, json.loads(out)['night_llm']


def test_translate_poison_excluded(monkeypatch, capsys):
    """tid 1이 게이트 거부로 반복 실패해도 1회만 시도되고 tid 2가 진행돼야 한다."""
    _stub_common(monkeypatch)
    monkeypatch.setattr(translator, 'process_pending', lambda **k: [])
    calls, done = [], set()

    def fake_translate(limit=1, oldest_first=False, exclude_ids=None):
        ex = set(exclude_ids or ())
        calls.append(frozenset(ex))
        for tid, ok in ((1, False), (2, True)):
            if tid in ex or tid in done:
                continue
            if ok:
                done.add(tid)
                return [{'transcript_id': tid, 'translated': True}]
            return [{'transcript_id': tid, 'translated': False, 'reason': 'chunk_gate_reject'}]
        return []

    monkeypatch.setattr(translator, 'translate_pending_transcripts', fake_translate)
    rc, stats = _run_main(capsys)
    assert rc == 0
    assert stats['translate_fail'] == 1 and stats['translate_ok'] == 1
    assert not stats['partial']
    assert calls == [frozenset(), frozenset({1}), frozenset({1})]  # 실패 즉시 제외됨


def test_analysis_poison_excluded(monkeypatch, capsys):
    _stub_common(monkeypatch)
    monkeypatch.setattr(translator, 'translate_pending_transcripts', lambda **k: [])
    done = set()

    def fake_process(limit=1, oldest_first=False, exclude_ids=None):
        ex = set(exclude_ids or ())
        for fid, ok in ((7, False), (8, True)):
            if fid in ex or fid in done:
                continue
            if ok:
                done.add(fid)
                return [{'filing_id': fid, 'ticker': 'OK1'}]
            return [{'filing_id': fid, 'error': 'boom'}]
        return []

    monkeypatch.setattr(translator, 'process_pending', fake_process)
    rc, stats = _run_main(capsys)
    assert rc == 0
    assert stats['analysis_fail'] == 1 and stats['analysis_ok'] == 1


def test_unknown_id_breaks_phase(monkeypatch, capsys):
    """실패 항목에 id가 없으면(제외 불가) 단계를 끝내 무한 루프를 막는다."""
    _stub_common(monkeypatch)
    monkeypatch.setattr(translator, 'process_pending', lambda **k: [])
    n = {'v': 0}

    def fake_translate(limit=1, oldest_first=False, exclude_ids=None):
        n['v'] += 1
        return [{'translated': False, 'reason': 'weird'}]   # transcript_id 없음

    monkeypatch.setattr(translator, 'translate_pending_transcripts', fake_translate)
    rc, stats = _run_main(capsys)
    assert rc == 0
    assert n['v'] == 1 and stats['translate_fail'] == 1
