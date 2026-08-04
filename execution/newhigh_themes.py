# -*- coding: utf-8 -*-
"""
신고가 테마 sidecar — `newhigh_themes.json` 에 (날짜, 종목코드)별 테마를 영속 저장한다.

배경(2026-08-04 확인): 15:50 타이머가 `enrich_newhigh_themes.py` 로 테마를 부여해도
16:20·18:30 재수집이 `newhigh_20d.json` 을 통째로 다시 써서 theme 이 전부 사라졌다.
(15:50 로그 "테마 46/79종목 부여" ↔ 18:30 산출 파일의 theme 0건)

구조:
    newhigh_20d.json   = 수집 결과 + sidecar 를 합친 **materialized view** (기존 소비자 계약 그대로)
    newhigh_themes.json = 테마의 정본 (수집이 몇 번 돌든 살아남는다)

이 모듈은 LLM·네트워크를 쓰지 않는다. 매 수집마다 호출해도 안전하다.
"""
import io
import json
import os
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
SIDECAR = 'newhigh_themes.json'
KEEP_DAYS = 400          # 날짜 엔트리 보관 상한


def _path(base=None):
    return os.path.join(base, SIDECAR) if base else SIDECAR


def load(base=None):
    try:
        with io.open(_path(base), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {'dates': {}}
    except Exception:
        return {'dates': {}}


def save(side, base=None):
    """오래된 날짜 prune 후 atomic write."""
    dates = side.setdefault('dates', {})
    for d in sorted(dates)[:-KEEP_DAYS] if len(dates) > KEEP_DAYS else []:
        dates.pop(d, None)
    p = _path(base)
    tmp = p + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as f:
        json.dump(side, f, ensure_ascii=False)
    os.replace(tmp, p)


def hydrate(data, base=None):
    """
    newhigh_20d 딕셔너리에 sidecar 테마를 입힌다(제자리 수정). 반환 = 채운 종목 수.
    이미 theme 이 있는 종목은 건드리지 않는다(방금 생성한 결과가 우선).
    """
    side = load(base)
    entry = (side.get('dates') or {}).get(data.get('date')) or {}
    themes = entry.get('themes') or {}
    n = 0
    for s in data.get('stocks', []):
        if s.get('theme'):
            continue
        t = (themes.get(s.get('code')) or {}).get('theme')
        if t:
            s['theme'] = t
            n += 1
        else:
            s.setdefault('theme', '')
    if not data.get('theme_descriptions') and entry.get('descriptions'):
        data['theme_descriptions'] = entry['descriptions']
    if entry.get('enriched_at') and not data.get('themes_enriched_at'):
        data['themes_enriched_at'] = entry['enriched_at']
    return n


def record(date, code_to_theme, descriptions=None, base=None, model=''):
    """생성된 테마를 sidecar 에 upsert 한다(빈 문자열은 저장하지 않음)."""
    side = load(base)
    entry = side.setdefault('dates', {}).setdefault(date, {'themes': {}})
    now = datetime.now(tz=KST).isoformat()
    themes = entry.setdefault('themes', {})
    for code, theme in (code_to_theme or {}).items():
        if not theme:
            continue
        themes[code] = {'theme': theme, 'generated_at': now, 'model': model}
    if descriptions:
        entry['descriptions'] = descriptions
    entry['enriched_at'] = now
    save(side, base)
    return len(themes)
