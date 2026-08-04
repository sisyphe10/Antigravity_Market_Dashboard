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
alerts: ""
---

# Featured KIS/신고가 (fetch_featured_data_kis.py + enrich)

**Domain:** 포트폴리오 · WRAP · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 15:50 (featured-kis 타이머) · **Status:** active · **Project:** antigravity

KIS 시세로 20일 신고가(`newhigh_20d.json`)를 만들고 테마를 enrich하는 수집기(15:50 타이머).

- `enrich_newhigh_themes.py`가 Naver 뉴스+Haiku로 테마 부착(실패해도 수집 유지).
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

## Code
- `execution/fetch_featured_data_kis.py`
- `execution/enrich_newhigh_themes.py`
- `execution/newhigh_themes.py`
- `execution/krx_session.py`
- `execution/repair_featured_history.py`
