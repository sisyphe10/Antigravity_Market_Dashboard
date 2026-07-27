# -*- coding: utf-8 -*-
"""Research Notes 태깅 공용 모듈 — 온톨로지·개체 마스터·별칭 매칭.

설계 원칙 (Codex 검토 반영):
- Universe(universe_tickers.csv)가 상장 종목 마스터의 단일 출처. 여기에 비상장 기업·
  기관·인물을 억지로 넣지 않고 entities_extra.csv 로 분리한다.
- 별칭은 strong / weak 두 등급. strong은 규칙만으로 자동 승인, weak는 LLM 문맥 판정
  대상 후보로만 올린다.
- 모든 후보는 표면형과 문자 위치를 함께 반환해 근거(evidence)를 남길 수 있게 한다.
- 마스터 해시(universe_hash / ontology_version / alias_hash)를 노출해 태그 캐시 키에
  포함시킨다. 마스터가 바뀌면 재태깅 여부를 명시적으로 판단할 수 있다.
"""
import csv
import hashlib
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)  # datalake/tagging → repo root 는 두 단계 위
if os.path.basename(HERE) == "tagging":
    REPO = os.path.dirname(os.path.dirname(HERE))

ONTOLOGY_PATH = os.path.join(HERE, "ontology.json")
ALIASES_PATH = os.path.join(HERE, "aliases_manual.csv")
ENTITIES_EXTRA_PATH = os.path.join(HERE, "entities_extra.csv")
UNIVERSE_PATH = os.path.join(REPO, "universe_tickers.csv")

# 증권사 리서치 헤더: "[SK증권 반도체 한동희]", "[메리츠증권 반도체/디스플레이 김선우]"
HEADER_RE = re.compile(r"\[([^\[\]]{2,40}?(?:증권|투자증권|자산운용|리서치|투자자문))[^\[\]]{0,40}\]")
# 본문 말미 출처: "(by https://t.me/...)", "- 로이터", "by J.P.Morgan"
BYLINE_RE = re.compile(r"(?:^|\n)\s*(?:\(?by |출처[:：]|자료[:：])", re.IGNORECASE)

# 기업명이지만 일반명사로 훨씬 자주 쓰여 자동 별칭에서 제외하는 표기.
# (진짜 언급을 잡아야 하면 aliases_manual.csv 에 required_context 와 함께 등록한다)
AUTO_ALIAS_STOPWORDS = {"대상", "한국", "대한", "우리", "신세계", "인터파크"}

TICKER_PREFIXES = (
    "KRX", "KOSDAQ", "NASDAQ", "NYSE", "NYSEAMERICAN", "TPE", "TYO",
    "HKG", "SHA", "SHE", "AMS", "ETR", "EPA", "TSE",
)


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def nfkc(s):
    return unicodedata.normalize("NFKC", s or "")


# --------------------------------------------------------------------------- #
# 로더
# --------------------------------------------------------------------------- #
def load_ontology(path=ONTOLOGY_PATH):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    data = json.loads(raw)
    themes = {t["id"]: t for t in data["themes"]}
    for t in data["themes"]:
        p = t.get("parent")
        if p and p not in themes:
            raise ValueError("ontology: unknown parent %r for %r" % (p, t["id"]))
    return {
        "version": data["version"],
        "hash": _sha(raw),
        "themes": themes,
        "order": [t["id"] for t in data["themes"]],
    }


def load_universe(path=UNIVERSE_PATH):
    """universe_tickers.csv → {ticker: {name, sector}} + 무결성 검증."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    rows = list(csv.DictReader(raw.splitlines()))
    if not rows:
        raise ValueError("universe: empty")
    required = {"섹터", "티커", "기업명"}
    missing = required - set(rows[0].keys())
    if missing:
        raise ValueError("universe: missing columns %s" % missing)

    out, dups = {}, []
    for r in rows:
        tk = (r["티커"] or "").strip()
        nm = (r["기업명"] or "").strip()
        sec = (r["섹터"] or "").strip()
        if not tk or not nm or not sec:
            raise ValueError("universe: blank field in row %r" % r)
        if ":" not in tk or tk.split(":", 1)[0] not in TICKER_PREFIXES:
            raise ValueError("universe: unexpected ticker format %r" % tk)
        if tk in out:
            dups.append(tk)
            continue
        out[tk] = {"name": nm, "sector": sec}
    if dups:
        raise ValueError("universe: duplicate tickers %s" % dups[:5])
    return {"rows": out, "hash": _sha(raw), "count": len(out)}


def load_entities_extra(path=ENTITIES_EXTRA_PATH):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    out = {}
    for r in csv.DictReader(raw.splitlines()):
        eid = (r["entity_id"] or "").strip()
        if not eid:
            continue
        out[eid] = {
            "type": r["type"].strip(),
            "label_ko": r["label_ko"].strip(),
            "label_en": (r.get("label_en") or "").strip(),
            "industry": (r.get("industry") or "").strip(),
            "aliases": [a.strip() for a in (r.get("aliases") or "").split("|") if a.strip()],
        }
    return {"rows": out, "hash": _sha(raw)}


def load_manual_aliases(path=ALIASES_PATH):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    rows = []
    for r in csv.DictReader(raw.splitlines()):
        alias = (r["alias"] or "").strip()
        if not alias:
            continue
        mode = (r["match_mode"] or "substr").strip()
        # 한글이 섞인 별칭의 substr 는 낱말 경계 검사를 붙여 오탐을 줄인다
        if mode == "substr" and re.search(r"[가-힣]", alias):
            mode = "ko_boundary"
        rows.append({
            "entity_id": r["entity_id"].strip(),
            "alias": alias,
            "strength": (r["strength"] or "weak").strip(),
            "match_mode": mode,
            "required_context": [x for x in (r.get("required_context") or "").split("|") if x],
            "blocked_context": [x for x in (r.get("blocked_context") or "").split("|") if x],
        })
    return {"rows": rows, "hash": _sha(raw)}


# --------------------------------------------------------------------------- #
# 별칭 인덱스
# --------------------------------------------------------------------------- #
def _auto_aliases(universe):
    """Universe에서 기계적으로 만들 수 있는 별칭.

    - 정식 기업명: 한글 3자 이상 / 영문 4자 이상 → strong
      (그보다 짧으면 일반명사 충돌 위험이 커서 weak)
    - 거래소 포함 티커 표기(KRX:005930) → strong
    - 국내 6자리 코드 단독(005930, A005930) → strong (Universe에 존재할 때만)
    - 해외 심볼 단독(MU, NVDA) → 4자 이상 strong, 3자 이하 weak
    """
    out = []
    for tk, meta in universe["rows"].items():
        exch, sym = tk.split(":", 1)
        name = meta["name"]
        han = len(re.findall(r"[가-힣]", name))
        if name in AUTO_ALIAS_STOPWORDS:
            mode = None
        elif han:
            # 한글 2자 기업명(농심·풍산 등)은 일반명사 충돌이 잦아 weak로 낮춘다
            strength = "strong" if han >= 3 else "weak"
            mode = "ko_boundary"
        else:
            strength = "strong" if len(name) >= 5 else "weak"
            mode = "ci_token"
        if mode:
            out.append({"entity_id": tk, "alias": name, "strength": strength,
                        "match_mode": mode, "required_context": [], "blocked_context": [],
                        "origin": "auto:name"})
        out.append({"entity_id": tk, "alias": tk, "strength": "strong",
                    "match_mode": "ci_token", "required_context": [], "blocked_context": [],
                    "origin": "auto:ticker"})
        if exch in ("KRX", "KOSDAQ") and re.fullmatch(r"\d{6}", sym):
            out.append({"entity_id": tk, "alias": sym, "strength": "strong",
                        "match_mode": "code6", "required_context": [], "blocked_context": [],
                        "origin": "auto:code"})
        elif re.fullmatch(r"[A-Z.]{1,6}", sym):
            # 1~2자 심볼(T, F, KR, MU…)은 영문 본문에서 단독 매칭이 폭증한다.
            # $ 접두가 붙은 형태만 인정해 오탐을 원천 차단한다.
            if len(sym) <= 2:
                mode, strength = "symbol_dollar", "strong"
            elif len(sym) == 3:
                mode, strength = "symbol", "weak"
            else:
                mode, strength = "symbol", "strong"
            out.append({"entity_id": tk, "alias": sym, "strength": strength,
                        "match_mode": mode, "required_context": [], "blocked_context": [],
                        "origin": "auto:symbol"})
    return out


def build_alias_index(universe=None, manual=None, extra=None):
    universe = universe or load_universe()
    manual = manual or load_manual_aliases()
    extra = extra or load_entities_extra()

    entries = _auto_aliases(universe)
    for e in extra["rows"].items():
        eid, meta = e
        for a in meta["aliases"]:
            han = len(re.findall(r"[가-힣]", a))
            entries.append({
                "entity_id": eid, "alias": a,
                "strength": "strong" if (han >= 2 or len(a) >= 4) else "weak",
                "match_mode": "ko_boundary" if han else "ci_token",
                "required_context": [], "blocked_context": [], "origin": "extra",
            })
    for m in manual["rows"]:
        m = dict(m)
        m["origin"] = "manual"
        entries.append(m)

    # 수동 정의가 자동 정의를 덮어쓴다 (뒤에 오는 것이 우선)
    index = {}
    for e in entries:
        key = (nfkc(e["alias"]).lower(), e["entity_id"])
        index[key] = e

    unknown = [e["entity_id"] for e in index.values()
               if e["entity_id"] not in universe["rows"]
               and e["entity_id"] not in extra["rows"]]
    return {
        "entries": sorted(index.values(), key=lambda x: (-len(x["alias"]), x["alias"])),
        "unknown_entity_ids": sorted(set(unknown)),
        "hash": _sha(manual["hash"] + extra["hash"] + universe["hash"]),
    }


# --------------------------------------------------------------------------- #
# 매칭
# --------------------------------------------------------------------------- #
_WORD_EDGE = r"[0-9A-Za-z가-힣]"

# 한글 별칭 뒤에 붙어도 같은 낱말로 인정할 조사·접미어 (긴 것부터)
KO_SUFFIXES = (
    "으로부터", "에서는", "에서도", "이라고", "라고는", "으로는", "에게는",
    "부터", "까지", "보다", "처럼", "에서", "으로", "에게", "라고", "이라", "만이",
    "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "만", "로",
    "랑", "든", "나", "야", "다", "요", "주", "사", "측", "발", "행", "산", "제",
)


def _iter_hits(text, alias, mode):
    """(start, end, surface) 생성. mode별 경계 규칙 적용."""
    t = text
    if mode in ("ci_substr", "ci_token", "symbol"):
        hay, needle = t.lower(), alias.lower()
    else:
        hay, needle = t, alias
    if mode == "code6":
        for m in re.finditer(r"(?<![0-9])A?" + re.escape(alias) + r"(?![0-9])", t):
            yield m.start(), m.end(), m.group(0)
        return
    if mode == "symbol":
        pat = r"(?<![0-9A-Za-z])\$?" + re.escape(alias) + r"(?![0-9A-Za-z])"
        for m in re.finditer(pat, t, re.IGNORECASE):
            yield m.start(), m.end(), m.group(0)
        return
    if mode == "symbol_dollar":
        # $MU / $T 처럼 티커 표기가 명시된 경우만. 대소문자는 구분한다.
        pat = r"(?<![0-9A-Za-z])\$" + re.escape(alias) + r"(?![0-9A-Za-z])"
        for m in re.finditer(pat, t):
            yield m.start(), m.end(), m.group(0)
        return
    start = 0
    while True:
        i = hay.find(needle, start)
        if i < 0:
            return
        j = i + len(needle)
        start = i + 1
        before = t[i - 1] if i > 0 else ""
        after = t[j] if j < len(t) else ""
        if mode in ("token", "ci_token"):
            if re.match(_WORD_EDGE, before or " ") or re.match(_WORD_EDGE, after or " "):
                continue
        elif mode == "ko_boundary":
            # 왼쪽에 한글/영숫자가 붙으면 다른 낱말의 일부다 (예: "에이치브이엠" ← "브이엠")
            if re.match(_WORD_EDGE, before or " "):
                continue
            # 오른쪽이 한글이면 조사/접미어일 때만 인정 (예: "컨텍트"의 "컨텍" 차단)
            if re.match(r"[가-힣]", after or " "):
                tail = t[j:j + 4]
                if not any(tail.startswith(sfx) for sfx in KO_SUFFIXES):
                    continue
        yield i, j, t[i:j]


def detect_source_spans(text):
    """리서치 채널 헤더 구간 — 이 안에서 매칭된 개체는 role='source' 후보."""
    spans = []
    for m in HEADER_RE.finditer(text):
        spans.append((m.start(), m.end()))
    return spans


def find_candidates(text, alias_index, max_hits_per_alias=3):
    """규칙 기반 후보 추출.

    반환: [{entity_id, alias, surface, start, end, strength, in_source_header, origin}]
    strength='strong' 은 자동 승인 후보, 'weak' 는 LLM 문맥 판정 대상.
    """
    text = nfkc(text or "")
    if not text:
        return []
    src_spans = detect_source_spans(text)
    seen, out = set(), []
    for e in alias_index["entries"]:
        alias = nfkc(e["alias"])
        if not alias or alias.lower() not in text.lower():
            continue
        if e["blocked_context"] and any(b and b in text for b in e["blocked_context"]):
            continue
        if e["required_context"] and not any(r in text for r in e["required_context"]):
            continue
        n = 0
        for s, t_, surface in _iter_hits(text, alias, e["match_mode"]):
            key = (e["entity_id"], s, t_)
            if key in seen:
                continue
            # 더 긴 별칭이 이미 같은 구간을 덮었으면 건너뛴다
            if any(o["start"] <= s and t_ <= o["end"] for o in out):
                continue
            seen.add(key)
            out.append({
                "entity_id": e["entity_id"],
                "alias": e["alias"],
                "surface": surface,
                "start": s,
                "end": t_,
                "strength": e["strength"],
                "origin": e.get("origin", "manual"),
                "in_source_header": any(a <= s < b for a, b in src_spans),
            })
            n += 1
            if n >= max_hits_per_alias:
                break
    return sorted(out, key=lambda x: x["start"])


def sectors_for(entity_ids, universe):
    """승인된 상장 종목에서만 결정론적으로 섹터를 파생."""
    secs = []
    for eid in entity_ids:
        meta = universe["rows"].get(eid)
        if meta and meta["sector"] not in secs:
            secs.append(meta["sector"])
    return sorted(secs)


def masters_fingerprint():
    """태그 캐시 키에 넣을 마스터 지문."""
    onto = load_ontology()
    uni = load_universe()
    idx = build_alias_index(universe=uni)
    return {
        "ontology_version": onto["version"],
        "ontology_hash": onto["hash"],
        "universe_hash": uni["hash"],
        "universe_count": uni["count"],
        "alias_hash": idx["hash"],
        "alias_count": len(idx["entries"]),
        "unknown_entity_ids": idx["unknown_entity_ids"],
    }


if __name__ == "__main__":
    import pprint
    pprint.pprint(masters_fingerprint())
