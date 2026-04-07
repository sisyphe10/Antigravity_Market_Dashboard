---
patterns:
  - "execution/weather_bot.py"
---

# VM 배포 규칙

## 배포 타이밍
- 모든 작업 완료 후 세션 마지막에 1회만 배포
- 작업 중간에 VM 배포하지 않는다

## 배포 방식 (일반)
```bash
ssh -i /c/Users/user/Antigravity_Market_Dashboard/ssh-key-2026-02-20.key ubuntu@144.24.70.224 \
  "cd /home/ubuntu/Antigravity_Market_Dashboard && bash scripts/deploy.sh"
```

## 배포 방식 (re-clone, .git 비대화 등)
```bash
ssh ... "cd /home/ubuntu/Antigravity_Market_Dashboard && bash scripts/deploy.sh reclone"
```

## 필수: 배포 전 검증
- weather_bot.py 변경 시 반드시 `python3 -c "compile(open('execution/weather_bot.py').read(), 'weather_bot.py', 'exec')"` 실행
- 배포 후 5초 대기 → `systemctl is-active` 확인
- deploy.sh가 자동으로 둘 다 수행

## VM untracked 파일 (re-clone 시 반드시 백업)
- `.env` - 환경변수/토큰
- `subscribers.json` - 텔레그램 구독자 목록
- `.budget_milestone` - 예산 마일스톤 추적
- `stock_price_history.json` - 주가 히스토리 캐시
- `execution/research_bot/research_notes.db` - 리서치 노트 DB
- `execution/research_bot/media/` - 리서치 이미지

## VM Git 동기화
- VM에서는 git_sync() 사용: `git fetch + reset --hard` (충돌 불가)
- push 실패 시 git_push_safe() 사용: push → rebase 시도 → 실패 시 abort

## 장애 대응 (systemd)
- 10회 연속 실패 시 자동 재시작 중단 (StartLimitBurst=10)
- 중단 시 텔레그램 알림 (OnFailure=weather-bot-notify.service)

## 스케줄 (weather_bot.py)
- 05:00 KST: 날씨 알림
- 05:05 KST: 캘린더 알림
- 05:10 KST: 리서치 헤드라인
- 09:30~15:35 KST: 30분 간격 포트폴리오 자동 업데이트 (거래일만)
- 16:00 KST: 일간 포트폴리오 업데이트 + market_alert 재생성
- 18:00 KST: Featured 데이터 수집
- 23:00 KST: 당일 주문 반영 + market_alert 재생성
- 3시간마다: 예산 소진율 체크
