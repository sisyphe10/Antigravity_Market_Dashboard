---
id: "daemon-daily-selfcheck"
name: "일일 셀프체크 다이제스트 (08:50, 변화 시에만 발송)"
domain: "ops-infra"
project: "antigravity"
type: "timer"
runs_on: "vm_macmini"
schedule_kst: "08:50 매일"
status: "active"
code:
  - "launchd/system/daily_selfcheck.sh"
  - "launchd/system/com.antigravity.daily-selfcheck.plist"
reads:
  - "logs/launchd/stamps/"
  - "logs/launchd/starts/"
  - "~/.claude/.credentials.json"
  - "logs/launchd/schedule.tsv"
writes:
  - "logs/launchd/selfcheck_state/active"
depends_on:
  - "infra-vm-macmini"
  - "infra-telegram"
alerts: "새 경고(🆕)·해소(✅) 시에만 발송 → 텔레그램 · 지속 경고는 주 1회 다이제스트 · 정상·무변화는 무음(로그만)"
---

# 일일 셀프체크 다이제스트 (08:50, 변화 시에만 발송)

**Domain:** 운영 · 인프라 · **Type:** Timer · **Runs on:** vm_macmini · **Schedule (KST):** 08:50 매일 · **Status:** active · **Project:** antigravity

맥미니 상태를 매일 08:50 KST 점검해 **경고 상태가 변했을 때만** 텔레그램으로 요약을 보내는 launchd 데몬(`com.antigravity.daily-selfcheck`). 2026-07-11 컷오버로 라이브.

- ★**2026-07-15 설계 반전(사용자 지시)**: 원래는 정상이어도 매일 발송해 메시지 존재 자체가 liveness 신호인 dead-man's switch였으나, 매일의 정상 알림 소음이 그 값어치를 넘어선다고 판단 — warn이 없으면 발송을 생략하고 로컬 로그만 남긴다. **dead-man 감시 역할은 외부 워치독([[gha-daily-health-check]], 11:00 KST)이 승계** — 맥미니가 통째로 죽어도 GitHub 쪽에서 잡히므로 침묵이 감시 공백이 되지 않는다.

- ★★**2026-08-12 변화 기반 알림 게이트(사용자 지시)**: 07-15 억제는 "정상이면 무음"까지였고 **경고가 그대로여도 매일 재발송**됐다 — 은퇴한 [[timer-wrap-principle-check]]이 설치본 `schedule.tsv`에 남아 만든 STALE 오탐 하나가 8/7~8/12 동일 메시지 6통을 보냈다(원인 항목은 `3930367c`로 제거). 이제 모든 경고를 **변동 숫자를 뺀 안정 키**로 정규화해 **신규(🆕)·해소(✅)에만 발송**하고, 지속분은 ⏳ 요약 1줄로 붙이며, 지속 경고 전체 상세는 `SELFCHECK_DIGEST_SEC`(기본 7일)마다 한 번만 재발송한다. 정상 + 무변화 = 무음.
  - **키 설계**: 새 경고는 반드시 `add_warn <key> <detail>` 한 경로로만 추가한다(메시지 직접 조립 시 키가 없어 게이트를 조용히 우회). 디스크는 `disk:low`/`disk:critical`(`SELFCHECK_DISK_CRIT_GB` 기본 2G)로 **분리**해 low→critical 악화가 "무변화"에 묻히지 않게 했고, 웹 3종(`web:caddy`·`web:tsnet`·`web:snap_*`)·oauth 3종도 독립 키다.
  - **상태 파일 `logs/launchd/selfcheck_state/active`**(1행 `v1 <마지막 다이제스트 epoch>`, 2행~ `<키> <최초관측 epoch>`)는 ★**git 미추적 필수** — 추적되면 5분 auto-pull이 덮어써 상태가 사라진다(같은 8/12에 `schedule.tsv`가 겪은 버그). `.gitignore`에 등재.
  - **알림 유실 방지**([[infra-telegram]] 알림 억제 게이트 v2의 교훈 이식 — "알림을 줄이는 변경은 유실 경로부터 열거"): 상태 기록은 **검증된 발송 성공 후에만**(텔레그램 `"ok":true`, 최대 3회 재시도) — 발송 실패·`.env` 부재·자격 부재는 전부 실패로 반환해 다음 실행이 같은 diff를 재시도한다. 상태 파일이 깨지면 **fail-open**(전량 신규 재발송), 점검 자체를 못 돌린 항목(python·schedule.tsv·cron 파싱 실패)은 이전 키를 **이월**해 거짓 ✅ 해소를 만들지 않는다. 발송 후 상태 쓰기 실패는 로그+별도 경고로 크게 드러낸다. `SELFCHECK_DRYRUN=1`은 렌더·로그만 하고 발송·상태 갱신을 하지 않는다.
- 수집: 봇 4종 running 여부 · **`schedule.tsv` 등재 타이머**(2026-07-16 기준 10종 — memento-telegram·wrap-principle-check 추가) stamp 신선도(OK n/N) · 24h 재시작 수 · 디스크 여유 · git-pull 실패연속/HEAD 나이. 타이머 목록은 하드코딩이 아니라 `schedule.tsv`를 읽어 열거 — 새 타이머는 그 표에 등재되는 순간 자동으로 감시망에 든다.
- **웹 섹션(2026-07-11 W9 추가)**: Caddy(`com.antigravity.web`) running · ts.net 도달성(자기 ts.net을 tailscale IP로 resolve) · 게시 스냅숏(`current`) 나이. 2026-07-20 도달성 프로브 대상을 `/index.html` → `/watchlist/`로 교체 — 랜딩 폐지로 `/index.html`이 302 리다이렉트를 반환해 false DOWN으로 잡히던 문제([[web-caddy]]). 이 섹션은 **감지 전용**(warn만 냄) — 웹 데몬 3종의 포트 probe+자가복구(kickstart)는 별도 [[timer-daemon-health]](11:00)가 담당한다.
- ★**Claude 구독 인증 만료 사전 경고(2026-08-08 추가)**: `~/.claude/.credentials.json`의 `claudeAiOauth.refreshTokenExpiresAt`을 읽어 잔여 일수를 계산하고, **D-7 이내면 사전 경고 / 이미 만료면 즉시 ⚠️**를 낸다(`SELFCHECK_OAUTH_WARN_DAYS`·`SELFCHECK_CRED_FILE`로 조정, 파일 판독 실패도 "만료일 확인 불가" 경고). 2026-08-08 사고 대응 — 토큰이 07:20에 조용히 만료되며 **구독 쿼터를 쓰는 headless 잡 4종**([[daemon-datalake-webui]] 위키 문답 · [[src-research-tagging]] 리서치 태깅 · [[infra-telegram]] 실패 자가치료 · [[page-system-map]] 지도 주간 보정)이 한꺼번에 정지했는데, `claude -p`가 **인증 실패에도 exit 0**을 돌려줘 잡 rc 감시로는 잡히지 않았다. rc가 못 보는 실패라 **만료 날짜를 앞질러 보는 것**이 유일한 감지 경로다.
- 실제 문제(봇 다운/타이머 STALE/디스크 부족/웹 다운/인증 만료)만 키를 만들고, 그 **키 집합의 변화**가 곧 발송 여부다. ℹ️ 라인(24h 재시작 수·대형 로그)은 참고 정보라 발송되는 메시지에 얹히기만 하고 단독으로는 발송을 유발하지 않는다.
- 실적 다이제스트(08:00) 후, 신선도 워치독(11:00) 전 배치.

## Reads
- `logs/launchd/stamps/`
- `logs/launchd/starts/`
- `~/.claude/.credentials.json`
- `logs/launchd/schedule.tsv`

## Writes
- `logs/launchd/selfcheck_state/active`

## Depends on
- [[infra-vm-macmini]] — 컴퓨트 호스트 (맥미니)
- [[infra-telegram]] — 텔레그램 (알림·상호작용 채널)

## Code
- `launchd/system/daily_selfcheck.sh`
- `launchd/system/com.antigravity.daily-selfcheck.plist`

## Alerts
⚠ 새 경고(🆕)·해소(✅) 시에만 발송 → 텔레그램 · 지속 경고는 주 1회 다이제스트 · 정상·무변화는 무음(로그만)
