---
id: "src-ism-pmi"
name: "미국 ISM 서베이 8종 (fetch_ism_pmi.py)"
domain: "market-global"
project: "antigravity"
type: "pipeline_source"
runs_on: "gha"
schedule_kst: "07:50 화~토 (gha-daily-fred 편승)"
status: "active"
code:
  - "execution/fetch_ism_pmi.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 미국 ISM 서베이 8종 (fetch_ism_pmi.py)

**Domain:** 해외 · 매크로 · **Type:** Source · **Runs on:** gha · **Schedule (KST):** 07:50 화~토 (gha-daily-fred 편승) · **Status:** active · **Project:** antigravity

2026-08-05 신설. 미국 ISM 서베이 8종 — 제조업 4종(헤드라인·신규주문·고용·가격) + 서비스업 4종(헤드라인·기업활동·신규주문·가격) — 을 수집해 dataset.csv DATA(MACRO/US)에 적재(dtype=`ISM_MACRO`, 전부 50 기준 확산지수, 이름에 국가 접두 없음 — Country 칼럼이 표시). [[gha-daily-fred]]가 FRED 조회 앞단에서 먼저 돌린다(맥미니 launchd 미러 `gha-fred` 잡 동일).

- **★원천 = investing 이벤트차트 단일**: ISM이 2016년 FRED 재배포 라이선스를 회수(`NAPM` 삭제·API 400)해 FRED·DBnomics·ismworld·ECOS·Nasdaq·EconDB가 전부 막힘/오염(2026-08-05 전수 실측). curl_cffi(chrome impersonate) 필수(plain urllib는 403). ForexFactory `previous`는 최신월 교차검증용으로만 유효.
- **★관측월 배정 = 인덱스 기반**(release stamp 직접 사용 금지): timestamp는 관측월이 아니라 발표일(전월치를 다음 달 첫 영업일 공표)이라 `발표월−1`을 그대로 쓰면 스탬프 오류 구간이 밀린다. `first_ref = 첫 발표월−1`, `span == 관측수`일 때만 `i번째 관측 = first_ref + i개월`.
- **★드리프트 런 검사**(codex 지적 반영): 결측 1·중복 1이 상쇄되면 개수는 맞으면서 사이 구간만 밀린다 → 각 관측의 (발표월−1)과 배정 관측월 차이의 **연속 비영(非零) 최대 길이**가 `MAX_DRIFT_RUN` 초과 시 그 시리즈 차단(정상=전부 0, 2008 스탬프 오류=런 1 통과).
- **★앵커는 허용오차**(`ANCHOR_TOL`): ISM이 매년 1월 계절조정계수를 소급 개정하므로 완전일치 앵커는 매년 1월 거짓 실패를 낸다.
- 실패 처리: 시리즈 단위 격리(예외 시 그 시리즈만 skip)하되 **하나라도 실패하면 exit 1**(러너가 `|| echo`로 tolerate해도 종료코드가 감시 신호). 스크래핑 원천이라 잡에선 경고만 — FRED 조회는 계속되고 다음 run이 회수.

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_ism_pmi.py`
