"""
KIS 기반 시가총액 조회 — 투자유의종목(market_alert) enrichment 전용.

지정 종목 코드 리스트 → {code: 시가총액(억원)}  (inquire_price.hts_avls 사용).
기존 FDR StockListing Marcap + 네이버 40페이지 스크랩 폴백을 대체한다.

설계 원칙 (점진 롤아웃 안전):
- **절대 예외를 올리지 않는다.** 자격증명 미설정/네트워크 오류/KIS 장애 시
  빈(또는 부분) 딕셔너리를 반환 → 호출측은 기존 FDR marcap으로 폴백.
- 단위: hts_avls는 억원 단위 정수 문자열 → 기존 krx_data marcap(억원)과 동일.

관련: execution/kis_token.py (공유 토큰 + kis_get 헬퍼), project_antigravity_kis_migration.
"""
import logging

try:
    from kis_token import kis_get, get_access_token
    _AVAILABLE = True
except Exception:  # 모듈/자격증명 부재 시에도 import는 깨지지 않게
    _AVAILABLE = False

_INQUIRE_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
_TR_ID = "FHKST01010100"


def _canonical_market(name):
    """rprs_mrkt_kor_name(예: KOSPI200, KSQ150, KONEX, KRX100) → 'KOSPI'|'KOSDAQ'|''.
    KOSDAQ150은 'KSQ150'으로 옴. KRX100 등 거래소 판별 불가 값은 ''(호출측 폴백으로 해소)."""
    n = str(name or "").strip().upper()
    if "KOSPI" in n:
        return "KOSPI"
    if "KOSDAQ" in n or n.startswith("KSQ"):
        return "KOSDAQ"
    return ""


def fetch_stock_meta(codes):
    """
    codes: list[str] (종목코드). 반환: {code: {'marcap': 시가총액(억원, int), 'market': 'KOSPI'|'KOSDAQ'}}.
    inquire_price 1회로 hts_avls(시총)와 rprs_mrkt_kor_name(시장구분)을 함께 확보.
    KIS 미사용/실패 종목·판별 불가 필드는 결과에서 빠진다(호출측이 FDR/네이버로 폴백).
    """
    result = {}
    if not _AVAILABLE:
        return result

    # 토큰 1회 프로브: 자격증명 부재/발급 실패 시 즉시 폴백(종목별 재시도로 인한
    # 토큰 재발급 간격 가드(60s) 누적 지연 방지).
    try:
        get_access_token()
    except Exception as e:
        logging.warning("KIS 토큰 확보 실패 → 종목 메타 조회 건너뜀: %s", e)
        return result

    # 중복 제거 + 공란 제거 (입력 순서 보존)
    uniq = [c for c in dict.fromkeys(codes) if c]
    for code in uniq:
        try:
            j = kis_get(
                _INQUIRE_PRICE_PATH,
                tr_id=_TR_ID,
                params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code},
            )
            output = j.get("output") or {}
            avls = output.get("hts_avls")  # 시가총액 (억원)
            market = _canonical_market(output.get("rprs_mrkt_kor_name"))
            entry = {}
            if avls not in (None, "", "0"):
                entry["marcap"] = int(avls)
            if market:
                entry["market"] = market
            if entry:
                result[code] = entry
        except Exception as e:
            logging.debug("KIS 종목 메타 조회 실패 %s: %s", code, e)
    return result


def fetch_marcap(codes):
    """
    codes: list[str] (종목코드). 반환: {code: 시가총액(억원, int)}.
    KIS 미사용/실패 종목은 결과에서 빠진다(호출측이 FDR로 폴백).
    """
    return {c: m["marcap"] for c, m in fetch_stock_meta(codes).items() if "marcap" in m}


if __name__ == "__main__":
    # 스모크 테스트: 삼성전자(KOSPI) + 에코프로(KOSDAQ)
    m = fetch_marcap(["005930", "086520", ""])
    for code, eok in m.items():
        jo = eok // 10000
        rem = eok % 10000
        print(f"  {code}: {eok:,}억 ({jo}조 {rem}억)")
    print(f"[kis_marcap] available={_AVAILABLE} got={len(m)}")
