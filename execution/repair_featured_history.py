# -*- coding: utf-8 -*-
"""
비거래일 오염 정리 — featured_data.json / kis_price_history.json 에서 KRX 비거래일 데이터를 제거.

배경: 2026-06-02 KRX→KIS 컷오버 이후 fetch_featured_data_kis.py 에 거래일 가드가 없어
토·일·공휴일에도 랭킹 30행이 기록되고 kis_price_history 에 비거래일 고가가 누적됐다.
그 결과 `dates_sorted[-20:]` 이 실제로는 약 14거래일만 커버해 20일 신고가가 과다판정됐다.

정책:
- 랭킹 6종(비거래일 행)은 전일 값 중복이므로 삭제한다.
- 과거 거래일의 신고가 판정 결과는 **소급 재판정하지 않는다.** 그날 그렇게 판정돼
  이미 텔레그램으로 발송된 이력이기 때문. 앞으로의 판정만 읽기 필터로 정확해진다.
- 삭제분은 전량 journal 로 남겨 되돌릴 수 있게 한다.

사용:
    python3 execution/repair_featured_history.py            # dry-run (기본, 아무것도 안 씀)
    python3 execution/repair_featured_history.py --apply    # 백업+journal 남기고 실제 정리
"""
import hashlib
import io
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from krx_session import is_session, KST

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEATURED = os.path.join(REPO, 'featured_data.json')
KIS_HIST = os.path.join(REPO, 'kis_price_history.json')
BACKUP_ROOT = os.path.expanduser('~/tmp')       # repo 밖 (게시·git 대상 아님)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_json(path, obj):
    tmp = path + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)       # rename(2) — 부분 기록 상태가 보이지 않음


def plan_featured():
    recs = json.load(io.open(FEATURED, encoding='utf-8'))
    bad = [r for r in recs if not is_session(r.get('d', ''))]
    keep = [r for r in recs if is_session(r.get('d', ''))]
    dates = sorted({r.get('d') for r in bad})
    return recs, keep, bad, dates


def plan_kis_hist():
    hist = json.load(io.open(KIS_HIST, encoding='utf-8'))
    bad_dates = sorted(d for d in hist.get('dates', []) if not is_session(d))
    n_high = n_close = 0
    for st in hist.get('stocks', {}).values():
        n_high += sum(1 for d in st.get('highs', {}) if not is_session(d))
        n_close += sum(1 for d in st.get('closes', {}) if not is_session(d))
    return hist, bad_dates, n_high, n_close


def apply_kis_hist(hist):
    removed = {}
    hist['dates'] = [d for d in hist.get('dates', []) if is_session(d)]
    for code, st in hist.get('stocks', {}).items():
        rh = {d: v for d, v in st.get('highs', {}).items() if not is_session(d)}
        rc = {d: v for d, v in st.get('closes', {}).items() if not is_session(d)}
        if rh or rc:
            removed[code] = {'highs': rh, 'closes': rc}
        if rh:
            st['highs'] = {d: v for d, v in st['highs'].items() if is_session(d)}
        if rc:
            st['closes'] = {d: v for d, v in st['closes'].items() if is_session(d)}
    return hist, removed


def main():
    apply = '--apply' in sys.argv
    recs, keep, bad, bad_dates = plan_featured()
    hist, hist_bad_dates, n_high, n_close = plan_kis_hist()

    print('== featured_data.json ==')
    print('  전체 %d행 → 유지 %d / 제거 %d' % (len(recs), len(keep), len(bad)))
    print('  비거래일 %d일: %s' % (len(bad_dates), ', '.join(bad_dates)))
    from collections import Counter
    print('  제거 type 분포:', dict(Counter(r.get('type') for r in bad)))
    print('== kis_price_history.json ==')
    print('  비거래일 %d일: %s' % (len(hist_bad_dates), ', '.join(hist_bad_dates)))
    print('  제거 대상 highs %d개 / closes %d개 (종목 %d)' % (n_high, n_close, len(hist.get('stocks', {}))))

    # 룩백 회복 실측: 최근 20개 날짜 창이 실제 몇 거래일을 덮는지
    all_dates = sorted(set(hist.get('dates', [])))
    print('  히스토리 날짜 %d개 중 거래일 %d개 (최근 20개 창의 거래일 수: %d → 20)'
          % (len(all_dates), sum(1 for d in all_dates if is_session(d)),
             sum(1 for d in all_dates[-20:] if is_session(d))))

    if not apply:
        print('\n[dry-run] 아무것도 쓰지 않았다. 실제 정리는 --apply')
        return 0
    if not bad and not hist_bad_dates:
        print('\n정리할 비거래일 없음 — 종료')
        return 0

    stamp = datetime.now(tz=KST).strftime('%Y%m%d_%H%M%S')
    bdir = os.path.join(BACKUP_ROOT, 'featured_repair_' + stamp)
    os.makedirs(bdir, exist_ok=True)
    manifest = {'created_at': stamp, 'files': {}}
    for p in (FEATURED, KIS_HIST):
        dst = os.path.join(bdir, os.path.basename(p))
        shutil.copy2(p, dst)
        manifest['files'][os.path.basename(p)] = {'sha256': sha256(p), 'bytes': os.path.getsize(p)}
    hist2, removed_hist = apply_kis_hist(hist)
    # 역변환 journal — 제거한 것만 담는다(복원용)
    journal = {'created_at': stamp,
               'featured_removed': bad,
               'kis_hist_removed': removed_hist,
               'note': '과거 거래일의 신고가 판정은 소급 재판정하지 않음(발송 이력 보존)'}
    with io.open(os.path.join(bdir, 'journal.json'), 'w', encoding='utf-8') as f:
        json.dump(journal, f, ensure_ascii=False)
    with io.open(os.path.join(bdir, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    atomic_write_json(FEATURED, keep)
    atomic_write_json(KIS_HIST, hist2)
    print('\n정리 완료. 백업·journal: %s' % bdir)
    return 0


if __name__ == '__main__':
    sys.exit(main())
