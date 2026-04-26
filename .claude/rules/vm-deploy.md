---
patterns:
  - "execution/sisyphe_bot.py"
  - "execution/ra_sisyphe_bot.py"
  - "execution/research_bot/research_notes_bot.py"
---

# VM 배포 규칙

## 봇 구성 (3개)
| 텔레그램 봇 | systemd | 파일 | 토큰 환경변수 |
|---|---|---|---|
| Sisyphe-Bot | sisyphe-bot | execution/sisyphe_bot.py | TELEGRAM_SISYPHE_BOT_TOKEN |
| Research Notes | research-notes-bot | execution/research_bot/research_notes_bot.py | TELEGRAM_RESEARCH_NOTES_BOT_TOKEN |
| RA_Sisyphe_bot | ra-sisyphe-bot | execution/ra_sisyphe_bot.py | TELEGRAM_RA_SISYPHE_BOT_TOKEN |

서비스 unit 파일은 모두 `scripts/` 아래에 통일 (sisyphe-bot.service, research-notes-bot.service, ra-sisyphe-bot.service, sisyphe-bot-notify.service).

## 배포 타이밍
- 모든 작업 완료 후 세션 마지막에 1회만 배포
- 작업 중간에 VM 배포하지 않는다

## 배포 방식 (일반)
```bash
ssh -i /c/Users/user/Antigravity_Market_Dashboard/ssh-key-2026-02-20.key ubuntu@144.24.70.224 \
  "cd /home/ubuntu/Antigravity_Market_Dashboard && bash scripts/deploy.sh"
```

## 배포 방식 (re-clone)
```bash
ssh ... "cd /home/ubuntu/Antigravity_Market_Dashboard && bash scripts/deploy.sh reclone"
```

## 필수: 배포 전 검증
- 봇 파일 변경 시 deploy.sh가 3개 봇 모두 syntax 검증 (`compile()`) 자동 수행
- 배포 후 5초 대기 → 3개 봇 모두 `systemctl is-active` 확인 (deploy.sh 자동)

## VM untracked 파일 (re-clone 시 반드시 백업, deploy.sh BACKUP_FILES에 등록)
- `.env` - 환경변수/토큰
- `subscribers.json` - Sisyphe-Bot 구독자
- `subscribers_ra_sisyphe.json` - RA_Sisyphe_bot 구독자
- `kna_state.json` - KNA 마지막으로 본 글 ID
- `.budget_milestone` - 예산 마일스톤 추적
- `.wisereport_sent.json` - WiseReport 당일 전송 기록
- `stock_price_history.json` - 주가 히스토리 캐시
- `execution/research_bot/research_notes.db` - Research Notes DB
- `execution/research_bot/media/` - Research Notes 이미지
- `etf_data.db` - ETF 구성종목 DB

## VM Git 동기화
- VM에서는 git_sync() 사용: `git fetch + reset --hard` (충돌 불가)
- push 실패 시 git_push_safe() 사용: push → fetch+merge+push (rebase 불가, 바이너리 충돌 우려)

## 장애 대응 (systemd)
- 10회 연속 실패 시 자동 재시작 중단 (StartLimitBurst=10)
- 중단 시 텔레그램 알림 (OnFailure=sisyphe-bot-notify.service) — 모든 봇이 공유

## 스케줄

### sisyphe-bot (펀드/일상)
- 05:00 KST: 날씨 알림
- 05:05 KST: 캘린더 알림 + D-Day
- 09:30~15:35 KST: 30분 간격 포트폴리오 자동 업데이트 (거래일만)
- 16:00 KST: 일간 포트폴리오 리포트
- 16:05 KST: 투자유의종목 재생성 (market_alert.html)
- 16:10 KST: 투자일지 데이터 수집
- 16:20 KST: 야간 포트폴리오 새로고침 + Featured 1차
- 16:30 KST: ETF 데이터 수집
- 18:30 KST: Featured 2차 (KRX 18:10 배포)
- 20:00 KST: 백업 (16:xx 실패 재시도)
- 23:00 KST: 투자유의종목 야간 업데이트
- 08:30 KST: Featured 익일 복구

### ra-sisyphe-bot (리서치 알림)
- 05:10 KST: Research Notes 헤드라인
- 05:15 KST: 투자유의종목 일일 요약 (텔레그램 메시지)
- 07:00~17:00 KST 매시 정각: WiseReport 신규 리서치 리포트
- 18:00 KST: KNA 세계원전시장동향 신규 게시글
