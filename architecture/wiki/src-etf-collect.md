---
id: "src-etf-collect"
name: "ETF 구성종목 수집 (collect_etf_daily.py)"
domain: "market-kr"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "16:30 / 18:00 (etf-collect 타이머)"
status: "active"
code:
  - "execution/etf_collector/collect_etf_daily.py"
  - "execution/etf_collector/etf_db.py"
  - "execution/etf_collector/etfcheck_client.py"
  - "scripts/run_etf_collect.sh"
  - "scripts/import_etf_transfer.py"
  - "scripts/make_etf_seed.py"
reads: []
writes:
  - "store-etf-db"
depends_on:
  - "ext-data-apis"
  - "infra-vm-macmini"
alerts: ""
---

# ETF 구성종목 수집 (collect_etf_daily.py)

**Domain:** 국내 시장 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 16:30 / 18:00 (etf-collect 타이머) · **Status:** active · **Project:** antigravity

전체 ETF 목록 + 구성종목/비중을 etfcheck 등에서 수집해 `etf_data.db`(SQLite)에 적재.

- idempotent(성공 시 재실행 스킵). 봇에서 분리된 타이머가 소유([[timer-etf-collect]] 16:30 / [[timer-etf-collect-retry]] 18:00).
- etf.html 액티브 탭·19:00 알림의 원천 DB.
- ★**VM-side 수집 + 정본 병합으로 재설계(2026-07-21)**: 2026-07-11 맥미니 이전 후 맥미니 공인 IP가 한국 금융 소스에 직접 도달 불가 — etfcheck WAF가 IP 차단(정적 파일까지 403), KRX OpenAPI(Akamai)는 SSH SOCKS 터널의 MTU 문제로 타임아웃. 반면 Oracle VM([[infra-vm-macmini]])은 두 소스 모두 직결 200이라, `run_etf_collect.sh`가 **오케스트레이터**로 바뀌었다: ① 수집기 코드를 VM에 scp 동기화 → ② `make_etf_seed.py`로 정본에 이미 있는 당일 목록을 소형 전송 DB에 시드(KRX 재조회 회피 = KRX 간헐장애 내성) → ③ VM에서 `ETF_DB_PATH=전송DB collect_etf_daily.py <날짜>` 실행(구성종목만 etfcheck) + WAL 체크포인트 → ④ 전송 DB scp 회수 → ⑤ `import_etf_transfer.py --min-ok 1000`으로 완결성 검증 후 맥미니 정본(`etf_data.db` ~635M)에 원자적 병합(미달 시 정본 미변경·전송 DB 보존해 재-import 가능). `collect_etf_daily.py`는 날짜 인자와 `ETF_DB_PATH` override를 받도록 확장됐다.
- (구 방식) 맥미니 로컬 수집 + etfcheck만 SSH SOCKS 프록시(`ETFCHECK_PROXY`)로 우회한 방식은 KRX가 계속 실패해 폐기 — `etfcheck_client.py`의 `ETFCHECK_PROXY` 지원 코드만 잔존.
- etfcheck 내부 API 키는 사이트 개편마다 로테이션(2026-07-08 → 2026-07-21 `#$dser#GVEWS329@`, 30s 인증 버킷·`Referer` 필수).

## Reads
- (none)

## Writes
- [[store-etf-db]] — etf_data.db (ETF 구성종목 SQLite)

## Depends on
- [[ext-data-apis]] — 외부 데이터 API/소스 집합
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)

## Code
- `execution/etf_collector/collect_etf_daily.py`
- `execution/etf_collector/etf_db.py`
- `execution/etf_collector/etfcheck_client.py`
- `scripts/run_etf_collect.sh`
- `scripts/import_etf_transfer.py`
- `scripts/make_etf_seed.py`
