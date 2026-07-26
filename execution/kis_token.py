"""
KIS Open API 공유 액세스 토큰 매니저.

모든 KIS 수집기(Featured / 투자유의 enrichment / Universe 한국분 등)가
**하나의 토큰 캐시를 공유**하기 위한 모듈. 직접 호출보다 이걸 거쳐야 함.

핵심 원칙 (KIS 운영 제약 대응):
- 액세스 토큰은 24h 유효 + "1일 1회 발급 원칙". 유효기간 내 잦은 재발급은
  이용 제한 + 매번 알림톡 발송 → **매 run 재발급 금지, 캐시 재사용**.
- 여러 cron job이 토큰 만료 직후 동시에 재발급하면 "1분당 1회" 제한에 걸려
  무관한 컬렉터까지 실패 → **파일 락(fcntl)으로 단일 갱신 보장**(double-checked).
- 자격증명 우선순위: 환경변수(KIS_APP_KEY/KIS_APP_SECRET) → ~/KIS/config/kis_devlp.yaml(my_app/my_sec).
- 새 발급 전에 MCP/공식 kis_auth가 남긴 캐시(~/KIS/config/KIS<YYYYMMDD>)를 먼저 임포트해
  불필요한 재발급(알림톡)을 회피.

production: Oracle VM(Linux, cron/systemd). local: Windows 테스트 가능(fcntl 없으면 msvcrt 폴백).

사용 예:
    from kis_token import get_access_token, kis_get
    tok = get_access_token()
    rows = kis_get("/uapi/domestic-stock/v1/quotations/volume-rank",
                   tr_id="FHPST01710000", params={...})
"""
import os
import json
import time
import contextlib
from datetime import datetime, timedelta, timezone

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

KST = timezone(timedelta(hours=9))

# 실전 도메인 (이 appkey는 실전 전용 — 모의 미지원)
BASE_URL = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443")

_CONFIG_DIR = os.path.expanduser(os.path.join("~", "KIS", "config"))
# 공유 캐시(우리 포맷). 공식 kis_auth의 KIS<date>와 별도 — 포맷/수명 정책을 우리가 통제.
CACHE_PATH = os.getenv("KIS_TOKEN_CACHE", os.path.join(_CONFIG_DIR, "kis_token_shared.json"))
LOCK_PATH = CACHE_PATH + ".lock"

# 만료 여유분: 실제 만료 10분 전부터 갱신 대상으로 본다.
_REFRESH_MARGIN_SEC = 600
# 발급 직후 재시도 폭주 방지(같은 프로세스): 마지막 발급 시도 후 최소 간격.
_MIN_REISSUE_INTERVAL_SEC = 60
_HTTP_TIMEOUT = 10

_last_issue_attempt = 0.0


# ───────────────────────────── 자격증명 ─────────────────────────────
def _load_credentials():
    """env 우선, 없으면 ~/KIS/config/kis_devlp.yaml(my_app/my_sec) 폴백."""
    app = os.getenv("KIS_APP_KEY")
    sec = os.getenv("KIS_APP_SECRET")
    if app and sec:
        return app.strip(), sec.strip()

    yaml_path = os.path.join(_CONFIG_DIR, "kis_devlp.yaml")
    if os.path.exists(yaml_path):
        creds = {}
        with open(yaml_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                for key in ("my_app", "my_sec"):
                    if line.startswith(key + ":"):
                        val = line.split(":", 1)[1].strip().strip('"').strip("'")
                        creds[key] = val
        if creds.get("my_app") and creds.get("my_sec"):
            return creds["my_app"], creds["my_sec"]

    raise RuntimeError(
        "KIS 자격증명 없음: 환경변수 KIS_APP_KEY/KIS_APP_SECRET 또는 "
        f"{yaml_path}(my_app/my_sec)를 설정하세요."
    )


# ───────────────────────────── 파일 락 ─────────────────────────────
@contextlib.contextmanager
def _file_lock(timeout=30):
    """크로스플랫폼 배타적 파일 락 (LOCK_NB + 재시도 스핀)."""
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    f = open(LOCK_PATH, "w")
    acquired = False
    deadline = time.time() + timeout
    try:
        if os.name == "posix":
            import fcntl
            while True:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError:
                    if time.time() >= deadline:
                        raise TimeoutError("KIS 토큰 락 획득 시간초과")
                    time.sleep(0.2)
        else:  # Windows 테스트용
            import msvcrt
            while True:
                try:
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    acquired = True
                    break
                except OSError:
                    if time.time() >= deadline:
                        raise TimeoutError("KIS 토큰 락 획득 시간초과")
                    time.sleep(0.2)
        yield
    finally:
        if acquired:
            try:
                if os.name == "posix":
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                else:
                    import msvcrt
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
        f.close()


# ───────────────────────────── 캐시 입출력 ─────────────────────────────
def _parse_dt(s):
    """'YYYY-MM-DD HH:MM:SS' → tz-aware(KST) datetime."""
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)


def _read_cache():
    """우리 캐시 읽기 → 유효하면 토큰 문자열, 아니면 None."""
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        exp = _parse_dt(data["expires_at"])
        if exp > datetime.now(KST) + timedelta(seconds=_REFRESH_MARGIN_SEC):
            return data["access_token"]
    except Exception:
        pass
    return None


def _write_cache(token, expires_at):
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(
            {
                "access_token": token,
                "expires_at": expires_at,
                "issued_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
            },
            f,
            ensure_ascii=False,
        )
    os.replace(tmp, CACHE_PATH)  # 원자적 교체


def _import_official_cache():
    """
    MCP/공식 kis_auth가 남긴 ~/KIS/config/KIS<YYYYMMDD> (포맷: token:/valid-date:)를
    우리 캐시로 임포트. 새 발급(알림톡) 회피용. 성공 시 토큰, 아니면 None.
    """
    fname = "KIS" + datetime.now(KST).strftime("%Y%m%d")
    path = os.path.join(_CONFIG_DIR, fname)
    try:
        token, valid_date = None, None
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("token:"):
                    token = line.split(":", 1)[1].strip()
                elif line.startswith("valid-date:"):
                    valid_date = line.split(":", 1)[1].strip()
        if not (token and valid_date):
            return None
        exp = _parse_dt(valid_date)
        if exp > datetime.now(KST) + timedelta(seconds=_REFRESH_MARGIN_SEC):
            _write_cache(token, valid_date)
            return token
    except Exception:
        pass
    return None


# ───────────────────────────── 토큰 발급 ─────────────────────────────
def _issue_token():
    """KIS에 신규 토큰 발급 요청 → (token, expires_at). rate-limit 가드 포함."""
    global _last_issue_attempt
    elapsed = time.time() - _last_issue_attempt
    if elapsed < _MIN_REISSUE_INTERVAL_SEC:
        time.sleep(_MIN_REISSUE_INTERVAL_SEC - elapsed)
    _last_issue_attempt = time.time()

    app, sec = _load_credentials()
    res = requests.post(
        f"{BASE_URL}/oauth2/tokenP",
        headers={"content-type": "application/json"},
        data=json.dumps(
            {"grant_type": "client_credentials", "appkey": app, "appsecret": sec}
        ),
        timeout=_HTTP_TIMEOUT,
    )
    if res.status_code != 200:
        raise RuntimeError(f"KIS 토큰 발급 실패 [{res.status_code}]: {res.text[:200]}")
    j = res.json()
    token = j["access_token"]
    expires_at = j.get("access_token_token_expired")
    if not expires_at:  # 폴백: expires_in(초)로 계산
        sec_left = int(j.get("expires_in", 86400))
        expires_at = (datetime.now(KST) + timedelta(seconds=sec_left)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    return token, expires_at


def get_access_token(force=False):
    """
    공유 액세스 토큰 반환. 캐시 재사용 우선, 만료 시에만 락 잡고 단일 갱신.
    force=True면 캐시 무시하고 강제 재발급(긴급 시에만).
    """
    if not force:
        tok = _read_cache()
        if tok:
            return tok

    with _file_lock():
        # double-checked: 락 대기 중 다른 프로세스가 갱신했을 수 있음
        if not force:
            tok = _read_cache()
            if tok:
                return tok
            tok = _import_official_cache()  # 공식 캐시 재활용(알림톡 회피)
            if tok:
                return tok
        token, expires_at = _issue_token()
        _write_cache(token, expires_at)
        return token


# ───────────────────────────── 인증 요청 헬퍼 ─────────────────────────────
# KIS 초당 거래건수 제한(~20/s) 보수적 가드.
_MIN_CALL_INTERVAL_SEC = 0.06
_last_call_ts = 0.0


def _throttle():
    global _last_call_ts
    gap = time.time() - _last_call_ts
    if gap < _MIN_CALL_INTERVAL_SEC:
        time.sleep(_MIN_CALL_INTERVAL_SEC - gap)
    _last_call_ts = time.time()


_MAX_5XX_RETRY = 3   # KIS 랭킹 엔드포인트는 간헐적으로 5xx 반환 → 짧게 재시도


def kis_get(path, tr_id, params, tr_cont="", custtype="P", retry_on_expire=True):
    """
    인증 GET 호출. 헤더 자동 구성(authorization/appkey/appsecret/tr_id) + timeout 강제.
    반환: 응답 JSON(dict).
    - 토큰 만료(401) 시 1회 강제 재발급 후 재시도.
    - 5xx(서버 일시 오류)·네트워크 오류 시 최대 _MAX_5XX_RETRY회 짧은 백오프 재시도.
    """
    app, sec = _load_credentials()
    url = f"{BASE_URL}{path}"

    def _headers():
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {get_access_token()}",
            "appkey": app,
            "appsecret": sec,
            "tr_id": tr_id,
            "tr_cont": tr_cont,
            "custtype": custtype,
        }

    last_exc = None
    for attempt in range(_MAX_5XX_RETRY):
        _throttle()
        try:
            headers = _headers()
            res = requests.get(url, headers=headers, params=params, timeout=_HTTP_TIMEOUT)
            if res.status_code == 401 and retry_on_expire:
                headers["authorization"] = f"Bearer {get_access_token(force=True)}"
                _throttle()
                res = requests.get(url, headers=headers, params=params, timeout=_HTTP_TIMEOUT)
            if 500 <= res.status_code < 600:
                last_exc = requests.HTTPError(f"{res.status_code} server error")
                time.sleep(0.5 * (attempt + 1))   # 0.5s, 1.0s 백오프
                continue
            res.raise_for_status()
            return res.json()
        except requests.exceptions.RequestException as e:
            last_exc = e
            time.sleep(0.5 * (attempt + 1))
    raise last_exc


# ───────────────────────── 배치 당일 등락률 ─────────────────────────
_MULTPRICE_PATH = "/uapi/domestic-stock/v1/quotations/intstock-multprice"
_MULTPRICE_TRID = "FHKST11300006"


def fetch_changes(codes):
    """종목 코드 리스트 → {code: 당일 등락률(%)} (KIS intstock-multprice, 30종목/콜).

    prdy_ctrt(전일대비율)는 **장중 실시간** 갱신되어 FDR 일봉(당일 봉 지연) 대비
    /update 라이브 시세에 적합. 조회 실패 종목은 결과 dict에서 누락(호출측 폴백).
    """
    out = {}
    codes = [str(c).zfill(6) for c in codes if c]
    for i in range(0, len(codes), 30):
        chunk = codes[i:i + 30]
        params = {}
        for j, c in enumerate(chunk, 1):
            params[f"FID_COND_MRKT_DIV_CODE_{j}"] = "J"
            params[f"FID_INPUT_ISCD_{j}"] = c
        try:
            j = kis_get(_MULTPRICE_PATH, tr_id=_MULTPRICE_TRID, params=params)
            for row in (j.get("output") or []):
                code = row.get("inter_shrn_iscd")
                ctrt = row.get("prdy_ctrt")
                if not code or ctrt in (None, ""):
                    continue
                try:
                    out[code] = float(ctrt)
                except (TypeError, ValueError):
                    continue
        except Exception:
            continue   # 청크 실패 → 해당 종목은 호출측에서 FDR 폴백
    return out


# ───────────────────────── 확정 일봉(종가) ─────────────────────────
_DAILY_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
_DAILY_TRID = "FHKST03010100"


def fetch_daily_closes(codes, start_ymd, end_ymd, adj="0"):
    """종목 코드 리스트 → {code(6자리): {'YYYY-MM-DD': 확정 종가(float)}}.

    KIS 일봉은 장 마감(15:30) 후 KRX 확정 종가를 반환 → FDR 일봉(당일 봉 장중 지연/잠정)과 달리
    NAV 기준가 산출에 적합한 '확정 종가' 소스. 100봉/콜 제한 → 날짜 윈도우 분할.
    조회 실패 종목은 결과 dict에서 누락(호출측 FDR 폴백). start_ymd/end_ymd: 'YYYYMMDD'.
    """
    out = {}
    for code in [str(c).zfill(6) for c in codes if c]:
        series = {}
        cur_end = end_ymd
        guard = 0
        while cur_end >= start_ymd and guard < 16:
            guard += 1
            params = {
                "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code,
                "FID_INPUT_DATE_1": start_ymd, "FID_INPUT_DATE_2": cur_end,
                "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": adj,
            }
            try:
                j = kis_get(_DAILY_PATH, tr_id=_DAILY_TRID, params=params)
            except Exception:
                break
            bars = [b for b in (j.get("output2") or [])
                    if b.get("stck_bsop_date") and b.get("stck_clpr")]
            if not bars:
                break
            for b in bars:
                dd = b["stck_bsop_date"]
                try:
                    series[f"{dd[:4]}-{dd[4:6]}-{dd[6:]}"] = float(b["stck_clpr"])
                except (TypeError, ValueError):
                    continue
            earliest = min(b["stck_bsop_date"] for b in bars)
            if earliest <= start_ymd:
                break
            cur_end = (datetime.strptime(earliest, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
        if series:
            out[code] = series
    return out


if __name__ == "__main__":
    # 스모크 테스트: 토큰 확보(가능하면 캐시/공식캐시 재사용 → 신규 발급 없음)
    t = get_access_token()
    print(f"[kis_token] OK token_len={len(t)} cache={CACHE_PATH}")
