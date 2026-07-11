# Datalake — 문답 지침 (Claude Code 세션용)

이 디렉토리는 개인 데이터레이크다. 질문을 받으면 아래 자산에서 **실제 조회한 근거**로 답한다. 추측 금지.

## 자산 지도

| 위치 | 내용 | 조회 방법 |
|:---:|:---|:---|
| `catalog/INDEX.md` | 데이터셋 목록·스키마·기간 | **항상 먼저 읽기** |
| `market/market.duckdb` | 국내 전 상장종목 일봉(수정주가)·시총·밸류·외국인·지수·ETF·투자자 수급·해외 일봉 뷰 | `venv python + duckdb` 또는 duckdb CLI, 읽기전용 |
| `research_notes/YYYY/YYYY-MM-DD.md` | 텔레그램 리서치 노트 원문 (리포트 요지·기사·메모) | Grep → Read |
| `snapshots/YYYY/MM/DD/*.gz` | 대시보드 산출물 일별 스냅샷 | `gzip -dc`로 특정일 복원 |
| `~/Antigravity_Market_Dashboard/architecture/wiki/*.md` | 시스템(봇·잡·페이지) 구조 위키 | Grep → Read |

## 수치 조회 예시

```bash
~/Antigravity_Market_Dashboard/venv/bin/python3 -c "
import duckdb
con = duckdb.connect('$HOME/datalake/market/market.duckdb', read_only=True)
print(con.execute(\"SELECT date, close FROM kr_ohlcv WHERE name='삼성전자' ORDER BY date DESC LIMIT 5\").fetchdf())"
```

## 답변 규칙

- 한국어 존댓말, 결론 먼저
- % = 소수점 첫째 자리 / 금액 = 억원 (조 초과 시 `NN조 N,NNN억원`)
- 리서치 노트 인용 시 날짜·출처(전달: ...) 명시
- 데이터에 없으면 없다고 답한다 (카탈로그 기간 밖·미수집 종목 등)

## 유지보수 (코드는 레포 `datalake/`에 있음)

- 수정주가 소급 반영: `python3 datalake/backfill_krx.py --pass ohlcv --tickers <코드,...>`
- 카탈로그 재생성: `python3 datalake/build_catalog.py`
- 일일 잡 상태: `~/Antigravity_Market_Dashboard/logs/launchd/stamps/datalake-*.last`
