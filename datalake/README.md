# datalake/ — 맥미니 데이터레이크 + 문답 위키

설계 전문: [DESIGN.md](DESIGN.md) · 데이터는 맥미니 `~/datalake` (레포 외부), 코드는 이 폴더.

## 최초 설치 (맥미니 컷오버 완료 후, 순서대로)

```bash
cd ~/Antigravity_Market_Dashboard

# 1. 초기화 (트리 생성 + venv 의존성 + CLAUDE.md)
bash datalake/init_datalake.sh

# 2. 리서치 노트 원문 전량 백필 (수 분)
venv/bin/python3 datalake/export_research_notes.py --all

# 3. KRX 전 종목 백필 — 야간 배치 권장, 중단돼도 재실행하면 이어서
nohup venv/bin/python3 datalake/backfill_krx.py > ~/datalake/backfill.log 2>&1 &
tail -f ~/datalake/backfill.log        # 진행 확인 (패스 7개, 총 수 시간)

# 4. 해외 유니버스 백필
venv/bin/python3 datalake/backfill_overseas.py

# 5. 카탈로그·DuckDB 뷰 생성 + 현황 검증
venv/bin/python3 datalake/build_catalog.py
venv/bin/python3 datalake/build_catalog.py --check

# 6. 일일 타이머 4종 설치
sudo bash datalake/launchd/install_datalake_timers.sh

# 7. 백업 repo 최초 push (사전에 gh로 sisyphe-datalake private repo 생성돼 있음)
bash datalake/backup_datalake.sh --init

# 8. 문답 웹 UI
bash datalake/webui/run_webui.sh          # 127.0.0.1:8787
tailscale serve --bg 8787                 # 테일넷 내부 공개
```

## 일일 스케줄 (launchd)

| 잡 | KST | 하는 일 |
|:---:|:---:|:---|
| datalake-market-update | 20:30 | KRX 당일 단면 + 지수/수급 30일 + 해외 14일 upsert, 카탈로그 갱신 |
| datalake-research-export | 23:20 | 어제+오늘 노트 원문 md 재생성 (멱등) |
| datalake-snapshot | 23:50 | 덮어쓰기형 산출물 gzip 보존 |
| datalake-backup | 일 10:00 | `sisyphe-datalake` private repo push |

성공 stamp: `logs/launchd/stamps/datalake-*.last` · 실패 시 텔레그램 notify (기존 스크립트 재사용)

## 자주 쓰는 명령

```bash
# 특정 종목 수정주가 재백필 (무상증자·액면분할 후)
venv/bin/python3 datalake/backfill_krx.py --pass ohlcv --tickers 005930,000660

# 특정일 노트 재export / 스냅샷 복원
venv/bin/python3 datalake/export_research_notes.py --date 2026-07-01
gzip -dc ~/datalake/snapshots/2026/07/01/kodex_sectors.json.gz | head

# Claude Code로 문답 (웹 UI 대신)
cd ~/datalake && claude
```

## 주의

- **KRX 페이싱 0.5s·연속 실패 5회 중단** 로직을 우회하지 말 것 (계정 잠금)
- `market.duckdb`·`_staging/`은 재생성물 — 백업 제외 (backup .gitignore)
- 백필 스크립트는 데이터 있는 백테스트용 `~/krx_data`(구 수집물)와 무관 — datalake가 정본
