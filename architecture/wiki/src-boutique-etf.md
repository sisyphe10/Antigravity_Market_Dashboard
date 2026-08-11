---
id: "src-boutique-etf"
name: "부티크 액티브 ETF 팔로업 (boutique_etf collect+alert)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "09:10 / 10:10 / 18:20 평일 (boutique-etf 타이머)"
status: "active"
code:
  - "execution/boutique_etf/collect.py"
  - "execution/boutique_etf/registry.py"
  - "execution/boutique_etf/adapters.py"
  - "execution/boutique_etf/enrich.py"
  - "execution/boutique_etf/changes.py"
  - "execution/boutique_etf/alert.py"
  - "execution/boutique_etf/db.py"
  - "scripts/run_boutique_etf.sh"
reads: []
writes:
  - "store-boutique-etf-db"
depends_on:
  - "ext-data-apis"
alerts: "편입/편출·급변 텔레그램 (Sisyphe-Bot, 특이사항 없으면 무발송)"
---

# 부티크 액티브 ETF 팔로업 (boutique_etf collect+alert)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 09:10 / 10:10 / 18:20 평일 (boutique-etf 타이머) · **Status:** active · **Project:** antigravity

2026-08-04 신설. 부티크 액티브 ETF **56종**(타임폴리오 19·삼성 KoAct 25·트러스톤 2·DS 1·에셋플러스 9)의 NAV·AUM·편입/편출·시총대비 매매를 매 영업일 팔로업하는 독립 파이프라인. etfcheck 전수(313종) 파이프라인([[src-active-etf]]) 중단의 부분 대체 — 기존 잡·[[store-etf-db]]는 불가침.

- 흐름: 레지스트리 갱신(`registry.py`, 운용사 목록 동적 반영) → ETF별 구성종목(운용사 홈페이지 어댑터, 실패 시 KIS 폴백) + KIS 시세(NAV·AUM) → 시총 보강(국내 KIS·해외 KIS×환율) → invest_amt 산출 → 변경 탐지(`changes.py`).
- **어댑터**(`adapters.py`): 타임폴리오(`timeetf.co.kr` xlsx, 당일만)·KoAct(삼성 `samsungactive.co.kr` JSON, 과거일 가능)·트러스톤(WP admin-ajax nonce)·KIS 폴백(상위 30종 한도). 연속 실패 3회 시 그 어댑터 회로 차단.
- **멱등성**: 수집은 ETF 단위 멱등(당일 ok 스킵)이라 하루 3회 실행해도 중복 적재 없음. NAV·AUM은 **장중(09:00~15:30) 수집분에만** 갱신(장 전 수집분은 전일 종가 NAV·전일 보유분이 짝이 맞아 덮으면 어긋남). PDF 롤오버 가드=구성종목 지문(raw_code:qty:weight 해시)이 직전 ok일과 같으면 `status='stale'` → 변경탐지 제외.
- **알림**(`alert.py`, Sisyphe-Bot·`subscribers.json` 브로드캐스트, `run_boutique_etf.sh`에서 수집 직후 실행): 편입/편출/급변 계층형 텔레그램. 구분 라벨은 `신규(New)`/`편출(X)`/`증가(+)`/`감소(-)`(2026-08-11 한글 통일 — 기호만으론 눈에 안 띈다는 지적). 행 정렬=매매추정액 desc, 유입→유출 부호가 바뀌는 경계에 실선 구분선(U+2500×17, 2026-08-11). 신규·편출은 무조건, 급변만 매매추정액 ≥50억원 또는 종목 시총의 ≥0.1%. dedup=`alert_sent` 테이블(항목 단위 증분) → 늦게 온 운용사만 `(추가)`로 나감. 채권·현금성 파킹 보유분은 수집 단계에서 통째 제외(비율이 구조적으로 커 알림 오염).
- 뷰어 재빌드=맥 `~/work/charts/260715_현선물공매도/build_viewer_boutique.py` → `/charts/test_boutique_active_etf.html`(★테스트 페이지, nav 미배선). 실행 위치=[[timer-boutique-etf]] wrapper(`run_boutique_etf.sh`)가 collect→alert→뷰어를 순차 실행하되 부분 실패해도(공휴일 전량 stale·일부 운용사 장애) 확보된 ETF의 알림·페이지는 나가도록 코드만 보관 후 반환.
- 해외주식형 에셋플러스 3종은 KIS 구성종목 미제공 → 구조적 미커버(매일 fail 3건은 정상). 백필 안 함(첫 수집=2026-08-04).

## Reads
- (none)

## Writes
- [[store-boutique-etf-db]] — boutique_etf.db (부티크 액티브 ETF SQLite)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/boutique_etf/collect.py`
- `execution/boutique_etf/registry.py`
- `execution/boutique_etf/adapters.py`
- `execution/boutique_etf/enrich.py`
- `execution/boutique_etf/changes.py`
- `execution/boutique_etf/alert.py`
- `execution/boutique_etf/db.py`
- `scripts/run_boutique_etf.sh`

## Alerts
⚠ 편입/편출·급변 텔레그램 (Sisyphe-Bot, 특이사항 없으면 무발송)
