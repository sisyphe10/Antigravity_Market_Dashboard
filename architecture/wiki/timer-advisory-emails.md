---
id: "timer-advisory-emails"
name: "자문지 메일 발송 폴러 (send-advisory-emails 60초)"
domain: "portfolio-wrap"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "60초 폴러 (상시)"
status: "active"
code:
  - "execution/send_advisory_emails.py"
  - "launchd/timers/com.antigravity.send-advisory-emails.plist"
  - "launchd/timers/run_timer_job.sh"
reads:
  - "store-orders-pending"
  - "page-wrap"
writes:
  - "store-orders-pending"
depends_on:
  - "infra-vm-macmini"
  - "page-wrap"
alerts: "OnFailure(연속 실패 ~10분) → notify_sisyphe_failure.sh → 텔레그램"
---

# 자문지 메일 발송 폴러 (send-advisory-emails 60초)

**Domain:** 포트폴리오 · WRAP · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 60초 폴러 (상시) · **Status:** active · **Project:** antigravity

2026-07-13 신설. wrap.html Email 탭의 [메일 발송 요청]이 GitHub Contents API로 기록한 `orders/email_send_request.json`을 감지해 하이웍스 SMTP로 자문지 메일(컴플/삼성/NH/DB/한투)을 발송하는 launchd 60초 폴러. `run_timer_job.sh send-advisory-emails` → `execution/send_advisory_emails.py`.

- **StartInterval=60**(StartCalendarInterval 아님). 요청이 없으면 즉시 exit0, 락으로 중복 실행 방어.
- **안전 3중 가드**: ① 발송 모드는 맥 로컬 `~/email_config.json`의 `mode`만 신뢰(기본 `test`) — 요청 파일의 mode 필드는 감사용, 발송 판단에 미사용. ② real 전환은 config `mode=='real'` **그리고** `real_send_armed==True`(2단계 명시) + 사용자 승인 후에만, 코드가 자동 전환 안 함. ③ 발송 직전 assert: test인데 수신자에 본인(`kts@investlife.com`) 외 주소가 하나라도 있으면 `SendGuardError`로 **전체 배치 중단**(부분발송 없음) + 텔레그램 알림.
- **멱등**: 처리한 요청 ts를 `orders/email_send_result.json` + `logs/launchd/send-advisory-emails.processed`에 기록, 재실행 시 ts≤마지막처리 스킵. 비밀번호·메일 전문은 로그 미기록(요약만). SMTP 비번은 `.env HIWORKS_MAIL_PASSWORD`.
- **첨부**: 요청 base64만 사용(자문지/ 폴더 매칭·fallback 없음), 폴러측 총량 상한 5MiB(클라이언트가 900KB로 이미 제한).
- 컴플라이언스 선발송 게이팅은 2026-07-13 사용자 지시로 제거(UI enable + 폴러 guard 해제) — 증권사 키가 컴플 발송 성공을 더는 요구하지 않음.
- 일시 5xx/네트워크로 GitHub 요청 조회가 실패해도 배치를 죽이지 않고, 연속 10회(≈10분)마다만 알림(분당 스팸 방지).

## Reads
- [[store-orders-pending]] — orders/ (pending_orders · aum_pending)
- [[page-wrap]] — wrap.html (WRAP 대시보드)

## Writes
- [[store-orders-pending]] — orders/ (pending_orders · aum_pending)

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (Oracle VM → 맥미니)
- [[page-wrap]] — wrap.html (WRAP 대시보드)

## Code
- `execution/send_advisory_emails.py`
- `launchd/timers/com.antigravity.send-advisory-emails.plist`
- `launchd/timers/run_timer_job.sh`

## Alerts
⚠ OnFailure(연속 실패 ~10분) → notify_sisyphe_failure.sh → 텔레그램
