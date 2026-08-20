---
id: "src-featured-kis"
name: "Featured KIS/신고가 (fetch_featured_data_kis.py + enrich)"
domain: "portfolio-wrap"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "15:50 (featured-kis 타이머)"
status: "active"
code:
  - "execution/fetch_featured_data_kis.py"
  - "execution/enrich_newhigh_themes.py"
  - "execution/newhigh_themes.py"
  - "execution/krx_session.py"
  - "execution/repair_featured_history.py"
reads: []
writes:
  - "store-featured-data"
  - "featured_data_kis.json"
  - "newhigh_themes.json"
depends_on:
  - "ext-data-apis"
  - "infra-headless-llm"
alerts: ""
---

# Featured KIS/신고가 (fetch_featured_data_kis.py + enrich)

**Domain:** 포트폴리오 · WRAP · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 15:50 (featured-kis 타이머) · **Status:** active · **Project:** antigravity

KIS 시세로 20일 신고가(`newhigh_20d.json`)를 만들고 테마를 enrich하는 수집기(15:50 타이머).

- `enrich_newhigh_themes.py`가 Naver 뉴스+LLM으로 테마 부착(실패해도 수집 유지) — 섹터별 테마 부여·의미 통합·테마 설명 3개 호출.
- ★**테마 LLM 구독 이관 + 마감 예산(2026-08-20)**: 세 호출이 종량 Haiku API에서 **구독 headless**([[infra-headless-llm]])로 넘어갔다(`NEWHIGH_LLM`, 기본 `headless`·롤백 `api`). 이 잡은 뒤에 **16:00 [[bot-ra-sisyphe]] 신고가 알림이라는 고정 마감**이 걸려 있어, 백엔드 전환으로 호출 지연 특성이 달라지는 만큼 `NEWHIGH_DEADLINE`(기본 480s) 예산을 함께 뒀다 — 초과하면 **잔여 섹터를 테마 없이 넘긴다** — 테마는 부가정보이고 알림 정시 발송이 상위 목표라는 판단(부분 테마 > 지연·누락).
- 16:00 RA_Sisyphe_bot 신고가 알림이 이 산출을 소비. Featured 배치 KIS 전환 완료.
- ★**2026-08-04 featured-revival**: ① **거래일 가드**(`krx_session.py`, 주말+공휴일+5/1·12/31, holidays 미설치 시 fail-open) — 비거래일엔 랭킹·신고가 이력을 쓰지 않아 `dates_sorted[-20:]`가 실제 20거래일을 커버(과다판정 방지). ② **테마 sidecar**(`newhigh_themes.py` → `newhigh_themes.json`) — 15:50이 부여한 테마를 16:20·18:30 재수집이 `newhigh_20d.json`을 통째로 다시 쓰며 날려버리던 문제를, 테마 정본을 sidecar에 영속하고 매 수집마다 materialized view로 병합해 해결(LLM·네트워크 미사용, 멱등). ③ `repair_featured_history.py`=KRX 컷오버 이후 누적된 비거래일 오염 행을 백업+journal 남기고 정리하는 1회성 도구(`--apply`).

## Reads
- (none)

## Writes
- [[store-featured-data]] — featured_data.json / newhigh_20d.json
- `featured_data_kis.json`
- `newhigh_themes.json`

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합
- [[infra-headless-llm]] — 구독 LLM 백엔드 (headless claude · codex 폴백)

## Code
- `execution/fetch_featured_data_kis.py`
- `execution/enrich_newhigh_themes.py`
- `execution/newhigh_themes.py`
- `execution/krx_session.py`
- `execution/repair_featured_history.py`
