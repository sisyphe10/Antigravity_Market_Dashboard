# -*- coding: utf-8 -*-
"""부티크 액티브 ETF 유니버스 — 정적 시드 + 운용사별 동적 갱신(신규 상장 자동 반영).

adapter: timefolio(param=timeetf idx) | koact(param=fId) | truston(param=상품 페이지 URL)
         | kis(홈페이지 미제공 폴백, 상위 30종목 한도)
"""
import json
import re
import urllib.request
from datetime import datetime

UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read()


def _dec(b):
    for enc in ('utf-8', 'euc-kr', 'cp949'):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode('utf-8', 'ignore')


# etf_code -> (manager, name, adapter, param)
SEED = {
    # ── 타임폴리오 (timeetf.co.kr) ──
    '426030': ('타임폴리오', 'TIME 미국나스닥100액티브', 'timefolio', '2'),
    '426020': ('타임폴리오', 'TIME 미국S&P500액티브', 'timefolio', '5'),
    '456600': ('타임폴리오', 'TIME 글로벌AI인공지능액티브', 'timefolio', '6'),
    '494180': ('타임폴리오', 'TIME 글로벌소비트렌드액티브', 'timefolio', '8'),
    '485810': ('타임폴리오', 'TIME 글로벌바이오액티브', 'timefolio', '9'),
    '0019K0': ('타임폴리오', 'TIME 미국나스닥100채권혼합50액티브', 'timefolio', '10'),
    '0036D0': ('타임폴리오', 'TIME 미국배당다우존스액티브', 'timefolio', '18'),
    '0043Y0': ('타임폴리오', 'TIME 차이나AI테크액티브', 'timefolio', '19'),
    '478150': ('타임폴리오', 'TIME 글로벌우주테크&방산액티브', 'timefolio', '20'),
    '0113D0': ('타임폴리오', 'TIME 글로벌탑픽액티브', 'timefolio', '22'),
    '0185L0': ('타임폴리오', 'TIME 글로벌휴머노이드로봇산업액티브', 'timefolio', '25'),
    '410870': ('타임폴리오', 'TIME K컬처액티브', 'timefolio', '1'),
    '385720': ('타임폴리오', 'TIME 코스피액티브', 'timefolio', '11'),
    '441800': ('타임폴리오', 'TIME Korea플러스배당액티브', 'timefolio', '12'),
    '463050': ('타임폴리오', 'TIME K바이오액티브', 'timefolio', '13'),
    '495060': ('타임폴리오', 'TIME 코리아밸류업액티브', 'timefolio', '15'),
    '404120': ('타임폴리오', 'TIME K신재생에너지액티브', 'timefolio', '16'),
    '385710': ('타임폴리오', 'TIME K이노베이션액티브', 'timefolio', '17'),
    '0162Y0': ('타임폴리오', 'TIME 코스닥액티브', 'timefolio', '24'),
    # ── 삼성액티브 KoAct (samsungactive.co.kr) ──
    '0020H0': ('삼성액티브', 'KoAct 글로벌양자컴퓨팅액티브', 'koact', '2ETFQ5'),
    '0104H0': ('삼성액티브', 'KoAct 미국나스닥채권혼합50액티브', 'koact', '2ETFS3'),
    '462900': ('삼성액티브', 'KoAct 바이오헬스케어액티브', 'koact', '2ETFJ9'),
    '0051A0': ('삼성액티브', 'KoAct 브로드컴밸류체인액티브', 'koact', '2ETFR2'),
    '0113G0': ('삼성액티브', 'KoAct 미국바이오헬스케어액티브', 'koact', '2ETFS9'),
    '475070': ('삼성액티브', 'KoAct 글로벌친환경전력인프라액티브', 'koact', '2ETFL9'),
    '0222D0': ('삼성액티브', 'KoAct 신규상장', 'koact', '2ETFW1'),
    '490330': ('삼성액티브', 'KoAct 미국치매&뇌질환치료제액티브', 'koact', '2ETFO5'),
    '0186L0': ('삼성액티브', 'KoAct 미국로봇피지컬AI액티브', 'koact', '2ETFU7'),
    '0093D0': ('삼성액티브', 'KoAct 팔란티어밸류체인액티브', 'koact', '2ETFR9'),
    '471040': ('삼성액티브', 'KoAct 글로벌AI&로봇액티브', 'koact', '2ETFL3'),
    '497780': ('삼성액티브', 'KoAct 미국천연가스인프라액티브', 'koact', '2ETFO9'),
    '0219B0': ('삼성액티브', 'KoAct 광통신&위성네트워크액티브', 'koact', '2ETFV4'),
    '0132D0': ('삼성액티브', 'KoAct 글로벌K컬처밸류체인액티브', 'koact', '2ETFT2'),
    '0150K0': ('삼성액티브', 'KoAct 수소전력ESS인프라액티브', 'koact', '2ETFT9'),
    '0154H0': ('삼성액티브', 'KoAct 차이나바이오헬스케어액티브', 'koact', '2ETFT6'),
    '476850': ('삼성액티브', 'KoAct 배당성장액티브', 'koact', '2ETFM2'),
    '482030': ('삼성액티브', 'KoAct 반도체&2차전지핵심소재액티브', 'koact', '2ETFM8'),
    '0015B0': ('삼성액티브', 'KoAct 미국나스닥성장기업액티브', 'koact', '2ETFQ1'),
    '0163Y0': ('삼성액티브', 'KoAct 코스닥액티브', 'koact', '2ETFU6'),
    # fId 미확보 — 동적 갱신이 찾으면 koact 로 승격, 그전엔 KIS 폴백
    '495230': ('삼성액티브', 'KoAct 코리아밸류업액티브', 'kis', ''),
    '0074K0': ('삼성액티브', 'KoAct K수출핵심기업TOP30액티브', 'kis', ''),
    '0174B0': ('삼성액티브', 'KoAct 글로벌AI메모리반도체액티브', 'kis', ''),
    '487130': ('삼성액티브', 'KoAct AI인프라액티브', 'kis', ''),
    '0193G0': ('삼성액티브', 'KoAct 코스피액티브', 'kis', ''),
    # ── 트러스톤 ──
    '472720': ('트러스톤', 'TRUSTON 주주가치액티브', 'truston',
               'https://www.trustonasset.com/?ta_fund=truston-%ec%a3%bc%ec%a3%bc%ea%b0%80%ec%b9%98%ec%95%a1%ed%8b%b0%eb%b8%8c-etf472720'),
    '496130': ('트러스톤', 'TRUSTON 코리아밸류업액티브', 'truston',
               'https://www.trustonasset.com/?ta_fund=truston-%ec%bd%94%eb%a6%ac%ec%95%84%eb%b0%b8%eb%a5%98%ec%97%85%ec%95%a1%ed%8b%b0%eb%b8%8c%ec%a6%9d%ea%b6%8c%ec%83%81%ec%9e%a5%ec%a7%80%ec%88%98%ed%88%ac%ec%9e%90%ec%8b%a0%ed%83%81%ec%a3%bc%ec%8b%9d'),
    # ── DS자산운용 (홈페이지 ETF 섹션 없음) ──
    '0220B0': ('DS자산운용', 'DS 코스닥액티브', 'kis', ''),
    # ── 에셋플러스 (홈페이지 PDF 미노출) ──
    '442090': ('에셋플러스', '에셋플러스 코리아대장장이액티브', 'kis', ''),
    '407830': ('에셋플러스', '에셋플러스 글로벌플랫폼액티브', 'kis', ''),
    '433220': ('에셋플러스', '에셋플러스 글로벌대장장이액티브', 'kis', ''),
    '474920': ('에셋플러스', '에셋플러스 차이나일등기업포커스10액티브', 'kis', ''),
    '477490': ('에셋플러스', '에셋플러스 글로벌일등기업포커스10액티브', 'kis', ''),
    '451150': ('에셋플러스', '에셋플러스 글로벌영에이지액티브', 'kis', ''),
    '407820': ('에셋플러스', '에셋플러스 코리아플랫폼액티브', 'kis', ''),
    '0002C0': ('에셋플러스', '에셋플러스 인도일등기업포커스20액티브', 'kis', ''),
    '462340': ('에셋플러스', '에셋플러스 글로벌다이나믹시니어액티브', 'kis', ''),
}


def refresh_timefolio():
    """timeetf 목록 2페이지 → {etf_code: (idx, name)}"""
    out = {}
    for cate in ('001', '002'):
        h = _dec(_get('https://timeetf.co.kr/m11_list.php?cate=%s' % cate))
        for m in re.finditer(
                r'm11_view\.php\?idx=(\d+)&cate=\d+">.*?class="name">([^<]+)<.*?codeNum"><span>([A-Z0-9]{6})',
                h, re.S):
            name = m.group(2).replace('&amp;', '&').strip()
            out[m.group(3)] = (m.group(1), name)
    return out


def refresh_koact():
    """samsungactive etf.do (페이지네이션) → {etf_code: (fId, name)}"""
    out = {}
    for page in range(1, 6):
        d = json.loads(_get(
            'https://www.samsungactive.co.kr/api/v1/product/etf.do?pageNo=%d' % page))
        etfs = d.get('etfs') or []
        if not etfs:
            break
        for e in etfs:
            t, f = e.get('stkTicker'), e.get('fId')
            if t and f:
                out[t] = (f, (e.get('fNm') or '').strip())
        total = int(d.get('totalCnt') or 0)
        if total and len(out) >= total:
            break
    return out


def refresh_truston():
    """트러스톤 홈 → ta_fund 링크 → {etf_code: 페이지URL} (fund_code·nonce 는 어댑터가 페이지에서 추출)"""
    h = _dec(_get('https://www.trustonasset.com'))
    out = {}
    for m in re.finditer(r'href="([^"]*\?ta_fund=[^"]*etf(\d{6})[^"]*)"', h):
        url = m.group(1)
        if url.startswith('/'):
            url = 'https://www.trustonasset.com' + url
        out[m.group(2)] = url
    return out


_UPSERT = ('INSERT INTO etf_registry (etf_code,manager,name,adapter,param,updated_at)'
           ' VALUES (?,?,?,?,?,?)'
           ' ON CONFLICT(etf_code) DO UPDATE SET manager=excluded.manager,'
           ' name=excluded.name, adapter=excluded.adapter, param=excluded.param,'
           ' updated_at=excluded.updated_at')


def sync(conn):
    """SEED upsert 후 동적 갱신 반영. 갱신 실패는 경고만(시드 유지). 신규 코드는 자동 추가."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for code, (mgr, name, adapter, param) in SEED.items():
        # 신규 삽입 + 기존 kis 폴백 행을 시드의 전용 어댑터로 승격 (동적 갱신 결과는 보존)
        conn.execute(
            'INSERT INTO etf_registry (etf_code,manager,name,adapter,param,updated_at)'
            ' VALUES (?,?,?,?,?,?)'
            ' ON CONFLICT(etf_code) DO UPDATE SET adapter=excluded.adapter,'
            ' param=excluded.param, updated_at=excluded.updated_at'
            " WHERE etf_registry.adapter='kis' AND excluded.adapter!='kis'",
            (code, mgr, name, adapter, param, now))
    warns = []
    try:
        for code, (idx, name) in refresh_timefolio().items():
            conn.execute(_UPSERT, (code, '타임폴리오', name, 'timefolio', idx, now))
    except Exception as e:
        warns.append('timefolio refresh: %s' % e)
    try:
        for code, (fid, name) in refresh_koact().items():
            conn.execute(_UPSERT, (code, '삼성액티브', name or 'KoAct', 'koact', fid, now))
    except Exception as e:
        warns.append('koact refresh: %s' % e)
    try:
        for code, url in refresh_truston().items():
            row = conn.execute('SELECT name FROM etf_registry WHERE etf_code=?', (code,)).fetchone()
            name = row['name'] if row else 'TRUSTON %s' % code
            conn.execute(_UPSERT, (code, '트러스톤', name, 'truston', url, now))
    except Exception as e:
        warns.append('truston refresh: %s' % e)
    conn.commit()
    return warns
