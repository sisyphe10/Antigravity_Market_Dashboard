# Datalake — 맥미니 데이터레이크 + 문답 위키 설계

작성: 2026-07-11 (Fable 5) · 승인 범위: 전 상장 + 해외 유니버스 백필 / 맥미니 로컬 + 백업 전용 private repo / 웹 UI 문답 / 스크립트 전체 제작

## 1. 목표

1. **(a) Research Notes 원문 아카이브** — 텔레그램 원문(`research_notes.db`)을 일별 `.md`로 영구 적재
2. **(b) 일별 수집 데이터 적재** — 덮어쓰기형 산출물의 과거 유실 방지 (일별 gzip 스냅샷)
3. **(d) KRX/KIS 과거 종가 전량 백필** — 전 상장종목 + 해외 유니버스, 일봉 종가 기준, 이후 매일 증분
4. **(c) 문답 위키** — md 코퍼스 + DuckDB + Claude API 웹 UI로 자연어 질의

## 2. 저장소 레이아웃 (맥미니 `~/datalake`, 레포 외부)

```
~/datalake/
├── CLAUDE.md                        # Claude Code 세션용 문답 지침 (templates/에서 복사)
├── research_notes/
│   ├── 2026/2026-07-11.md           # 일 1파일: frontmatter + 메시지별 원문·출처·기사본문
│   └── media/2026-07-11/<id>.jpg    # 봇 media/ 사본 (자기완결)
├── market/
│   ├── market.duckdb                # 데이터셋별 뷰 (build_catalog.py가 재생성 — 백업 제외)
│   ├── kr_ohlcv/2026.parquet        # 데이터셋별 연도 파티션 parquet
│   ├── kr_marcap/  kr_fundamental/  kr_foreign/  kr_index_ohlcv/  kr_etf_ohlcv/
│   ├── kr_investor_value/           # 시장 단위 투자자별 매매대금 (KOSPI/KOSDAQ)
│   ├── overseas_ohlcv/              # 해외 유니버스 (yfinance)
│   └── */_staging/                  # 백필 중간 산출물 (finalize 후 삭제 — 백업 제외)
├── snapshots/2026/07/11/*.gz        # 덮어쓰기형 레포 산출물 일별 보존
└── catalog/
    ├── INDEX.md                     # 데이터셋 목록 (자동 생성)
    └── kr_ohlcv.md ...              # 스키마·기간·행수·쿼리 예시 (자동 생성)
```

코드는 전부 메인 레포 `datalake/`에 커밋 — 데이터만 `~/datalake`.

## 3. 데이터셋 정의 (일봉·종가 기준, 분봉 제외)

| 데이터셋 | 소스 | 백필 방식 | 일일 증분 |
|:---:|:---:|:---|:---|
| kr_ohlcv | pykrx(로그인) | 종목별 상장일~ (수정주가) | 당일 시장 단면 2콜 |
| kr_marcap | pykrx | 종목별 전 기간 | 당일 시장 단면 |
| kr_fundamental | pykrx | 종목별 전 기간 (PER/PBR/DIV/EPS/BPS/DPS) | 당일 시장 단면 |
| kr_foreign | pykrx | 종목별 전 기간 (외국인 보유비중 레벨) | 당일 시장 단면 |
| kr_index_ohlcv | pykrx | 지수 코드별 전 기간 (KOSPI/KOSDAQ/KRX/테마) | 지수별 최근 30일 |
| kr_etf_ohlcv | pykrx | ETF별 전 기간 (NAV 포함) | 당일 시장 단면 |
| kr_investor_value | pykrx | KOSPI/KOSDAQ 전 기간 | 최근 30일 |
| overseas_ohlcv | yfinance | 유니버스 해외 종목 상장일~ (US/TYO/TPE/HKG/EU) | 종목별 최근 14일 |

- KIS는 **당일 확정치 검증·보조**로만 사용(`execution/kis_token.py` 재사용). 대량 히스토리는 KRX가 주력 — KIS 기간별시세는 100건/콜 제한이라 백필에 부적합.
- **수정주가 캐비앳**: 무상증자·액면분할 등 corporate action은 과거를 소급 변경 → `backfill_krx.py --pass ohlcv --tickers <종목>`으로 해당 종목만 재백필. 분기 1회 전체 재백필은 선택 사항.
- 규모: kr_ohlcv 약 1,000만 행 → parquet 수백 MB. 전체 합계 수 GB 이내 (디스크 512GB 여유).

## 4. 페이싱·안전 규칙 (★KRX 계정 잠금 방지)

- 호출 간 **0.5초 페이싱** ([[project_krx_size_indices]] 검증값)
- **연속 실패 5회 → 즉시 중단** (KRX 로그인 5회 잠금 — [[project_antigravity_kodex_sectors_krx]])
- 체크포인트(`_staging/checkpoint.json`)로 재개 가능 — 중단 후 재실행 시 이어서
- 백필은 **야간 배치 권장** (nohup, 패스당 30~90분 × 7패스 ≈ 이틀 밤 분할)
- pykrx import 시 stdout 억제 + 자격증명 미출력 (`fetch_krx_valuation.py` 패턴 준수)

## 5. 일일 파이프라인 (launchd, 맥미니)

| 잡 이름 | KST | 스크립트 | 비고 |
|:---:|:---:|:---|:---|
| datalake-market-update | 20:30 매일 | daily_market_update.py | 휴장일=빈 응답 조용 skip, 30일 lookback 자가치유 |
| datalake-research-export | 23:20 매일 | export_research_notes.py | 어제+오늘 재생성(멱등), 23:00 요약 잡과 분리 |
| datalake-snapshot | 23:50 매일 | snapshot_archiver.py | 레포 산출물 gzip 보존 |
| datalake-backup | 일요일 10:00 | backup_datalake.sh | private repo `sisyphe-datalake` push |

- 기존 타이머와 충돌 없는 시각 (landing 18:45 / etf-active 19:00 / kodex 23:30 / 16~17시 배포금지 회피)
- **기존 파일 무수정**: 전용 wrapper `datalake/launchd/run_datalake_job.sh`가 CONTRACT 규약(잡별 락·stamp·.env 안전파서·타임아웃·notify)을 자체 구현. `run_timer_job.sh`·`schedule.tsv`는 건드리지 않음 → catch-up 러너 대상 아님. 대신 각 잡이 lookback/멱등으로 자가치유하므로 부팅 누락 무해 (스냅샷만 해당일 1회 유실 가능 — 허용).
- market-update 후 build_catalog.py 자동 실행 (뷰·카탈로그 갱신)

## 6. 문답 위키

### 6-1. 웹 UI (`datalake/webui/`)
- FastAPI + Claude API(`claude-opus-4-8`, adaptive thinking) 에이전틱 루프
- 도구 4종: `run_sql`(DuckDB 읽기전용) / `search_notes`(md 코퍼스 grep) / `read_file`(datalake 내부만) / `list_datasets`(카탈로그)
- 바인딩 `127.0.0.1:8787` → `tailscale serve --bg 8787`로 **테일넷 내부에서만** 접근 (외부 미노출)
- ANTHROPIC_API_KEY는 기존 `.env` 재사용
- 기동: launchd 등록은 사용 패턴 확인 후 (v1은 수동 `bash datalake/webui/run_webui.sh`)

### 6-2. Claude Code 경로 (보조)
- 맥미니에서 `cd ~/datalake && claude` — `CLAUDE.md`가 코퍼스 위치·duckdb 쿼리법 안내
- 시스템 구조 질문은 기존 `architecture/wiki/` 코퍼스가 계속 담당

### 6-3. Phase 2 (보류)
- 임베딩 RAG 인덱스, Notion 요약 역수집, 상폐 종목 히스토리, 종목별 투자자 수급(`--with-stock-flows`)

## 7. 백업

- `~/datalake`를 git repo로 초기화 → private repo `sisyphe10/sisyphe-datalake`에 주 1회 push
- 제외: `market.duckdb`(재생성물), `_staging/` — parquet+md+media만
- media 비대 시 월 단위 점검 (backup 스크립트가 repo 총 크기 로그)

## 8. 실행 순서 (컷오버 완료 후)

1. `bash datalake/init_datalake.sh` — ~/datalake 트리 생성, venv에 duckdb·pyarrow·yfinance 설치, CLAUDE.md 배치
2. `python3 datalake/export_research_notes.py --all` — 원문 전량 백필 (수 분)
3. `nohup python3 datalake/backfill_krx.py > ~/datalake/backfill.log 2>&1 &` — 야간 배치 (재개 가능)
4. `python3 datalake/backfill_overseas.py`
5. `python3 datalake/build_catalog.py` — 뷰+카탈로그 생성
6. `sudo bash datalake/launchd/install_datalake_timers.sh` — 타이머 4종 설치
7. `bash datalake/backup_datalake.sh --init` — 백업 repo 최초 push
8. 웹 UI: `bash datalake/webui/run_webui.sh` + `tailscale serve --bg 8787`

검증: 각 단계 후 `python3 datalake/build_catalog.py --check` (행수·기간 출력), 웹 UI에서 샘플 질의 3종.
