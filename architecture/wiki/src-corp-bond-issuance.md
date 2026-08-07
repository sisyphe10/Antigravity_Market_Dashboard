---
id: "src-corp-bond-issuance"
name: "미국·한국 회사채 발행액 (fetch_corp_bond_issuance.py)"
domain: "market-global"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "07:50 화~토 (gha-daily-fred 편승)"
status: "active"
code:
  - "execution/fetch_corp_bond_issuance.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 미국·한국 회사채 발행액 (fetch_corp_bond_issuance.py)

**Domain:** 해외 · 매크로 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 07:50 화~토 (gha-daily-fred 편승) · **Status:** active · **Project:** antigravity

2026-08-07 신설. 회사채 발행액 월간 2종 — `미 회사채 발행액`($B, 소수 1자리, dtype=`BOND_ISSUANCE_US`) + `회사채 발행액`(억원 정수, dtype=`BOND_ISSUANCE_KR`) — 을 dataset.csv DATA(MACRO US·KOREA)에 적재. dtype 을 소스별로 분리해 [[gha-daily-health-check]] 신선도를 개별 추적한다(SiliconData 3종과 동일 원칙 — 공유 타입이면 한 원천이 죽어도 가려진다). [[gha-daily-fred]] 편승(맥미니 launchd 미러 `gha-fred` 잡 동일).

- **미국 = SIFMA US Fixed Income Securities Statistics xlsx 직링크** — Issuance 시트 Corporates 열(non-convertible/convertible debt·MTNs·Yankee bonds 합계). ★파일의 월별 데이터는 최근 13개월 롤링 창뿐 → 매 run 창 전체를 재파싱해 개정치 upsert. 과거 이력은 Wayback 스냅숏 6개(2021~2025)를 `--backfill` 로 1회 스티칭: 2019-01~ 복원, 단 **2022-10~2023-04 7개월은 아카이브 공백 = 영구 결측**. 스냅숏 구간 값은 당시 공표 빈티지(이후 소급 개정 미반영)라 2025 연간 합이 최신 공표치와 ~0.7% 어긋난다. 회사채 전용 파일(1996~, IG/HY)은 2026년 현재 HubSpot 폼 뒤 게이트라 직링크·아카이브 모두 없음. 구층 레이아웃 대응: 헤더 `Corporates`(현행)/`Corporate Debt`(2021~22).
- **한국 = 금투협 채권정보센터 발행통계 기간별** — proframe XML POST(`BIS-KOFIABOND` / `BISIssStatisSrchSO` / `listTrm`, 세션 불필요). ★응답의 `회사채` 행 = **일반회사채**(은행채·기타금융채·ABS 는 별도 행) — 금감원 직접금융 총계(금융채·ABS 포함)와 모집단이 달라 **임의 합산·교차앵커 금지, 금감원 수치를 앵커로 쓰지 말 것**. 행 판정 = 국문 `회사채` AND 영문명 `Corporate` 동시 일치, 값=`val2`, 단위 억원. 이력 2006-01~. 진행 중인 달은 부분값이라 제외(월말 < 오늘 인 달만) + 최근 4개 완료월은 매 run 재조회해 D+1 지연·정정을 self-heal.
- **가드**: 값 범위(미 0~1,000 $B·한 0~100만 억원) + 창 축소·랙(미 75일) 감지 + 앵커(파싱 창에 해당 월이 있을 때만 검사, 창이 지나가면 자동 소멸: 미 2025-12=69.8±10% 등). 시트·헤더는 문자열 탐색(행번호 하드코딩 금지), xlsx magic bytes 검증(폼 게이트 전환 감지). 소스 단위로 격리해 하나가 죽어도 다른 원천은 계속되고, 하나라도 실패하면 exit 1(편승 잡에선 경고만 tolerate).
- 사용: 인자 없음=증분(매일 잡) · `--backfill`=최초 1회 전체 스티칭 · `--dry-run`.

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_corp_bond_issuance.py`
