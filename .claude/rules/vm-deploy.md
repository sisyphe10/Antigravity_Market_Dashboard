---
patterns:
  - "execution/weather_bot.py"
---

# VM 배포 규칙

## 배포 타이밍
- 모든 작업 완료 후 세션 마지막에 1회만 배포
- 작업 중간에 VM 배포하지 않는다

## 배포 방식
```bash
ssh -i /c/Users/user/Antigravity_Market_Dashboard/ssh-key-2026-02-20.key ubuntu@144.24.70.224 \
  "cd /home/ubuntu/Antigravity_Market_Dashboard && git fetch origin main && git reset --hard origin/main && sudo systemctl restart weather-bot"
```

## VM Git 동기화
- VM에서는 git_sync() 사용: `git fetch + reset --hard` (충돌 불가)
- push 실패 시 git_push_safe() 사용: push → rebase 시도 → 실패 시 abort

## 스케줄 (weather_bot.py)
- 05:00 KST: 날씨 알림
- 05:10 KST: 캘린더 알림
- 09:30~15:35 KST: 30분 간격 포트폴리오 자동 업데이트 (거래일만)
- 16:00 KST: 일간 포트폴리오 업데이트 + market_alert 재생성
- 23:00 KST: 당일 주문 반영 + SEIBro TOP 50 수집 + market_alert 재생성
