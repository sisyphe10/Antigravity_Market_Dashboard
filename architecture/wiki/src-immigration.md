---
id: "src-immigration"
name: "출입국 월별 통계 (fetch_immigration.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "23:30 (kodex 타이머 편승)"
status: "active"
code:
  - "execution/fetch_immigration.py"
reads: []
writes:
  - "store-dataset-csv"
depends_on:
  - "ext-data-apis"
alerts: ""
---

# 출입국 월별 통계 (fetch_immigration.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 23:30 (kodex 타이머 편승) · **Status:** active · **Project:** antigravity

법무부 출입국·외국인정책 통계월보(data.go.kr odcloud)를 수집해 dataset.csv(MACRO KOREA / IMMIGRATION 그룹, market.html DATA 탭)에 적재. data.go.kr이 GHA 해외 IP를 차단해 VM kodex 타이머(23:30)에 편승(KOSIS·일본 CAPEX와 동일 경로).

- 소스 2종: 15099985(월별 출입국자: 국민/외국인 × 입국/출국) + 15100016(체류자격별 체류외국인). 시리즈 5종(만명): 외국인 입국자·국민 출국자·체류외국인 총계·취업(E)·유학(D2·D4). 익월 하순~월말 갱신, 2022.1~ 백필.
- ★UDDI 함정: 파일 버전이 매월 새 UDDI로 갱신 → 스웨거 문서(infuser.odcloud.kr)에서 최신 버전을 동적 해석(하드코딩 금지). 컬럼명 공백·체류자격 표기(D2/유학D2/D2유학 3형) 변형은 키 정규화·정규식 코드 추출로 흡수.
- 전량 재조회 후 upsert(개정 self-heal). 실패는 경고 후 exit 0(다음 run 회수). `DATA_GO_KR_API_KEY` 미설정 시 skip. 신선도 감시 제외(IMMIGRATION은 DATASET_IGNORE, 월간·~1달 지연).

## Reads
- (none)

## Writes
- [[store-dataset-csv]] — dataset.csv (시장 시계열 통합)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합

## Code
- `execution/fetch_immigration.py`
