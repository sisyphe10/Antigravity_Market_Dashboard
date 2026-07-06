# launchd 산출물 공통 계약 (Wave 0 — 병렬 에이전트 인터페이스)

병렬 작업이 **파일 겹침 없이** 동시에 돌기 위한 단일 참조 문서. (DECISIONS 결정 15)

## 소유권 매트릭스 — 각자 자기 경로 안에서만 쓰기

| 패키지 | 배타적 출력 경로 (기준: `C:\Users\user\macmini_migration\`) |
|:---:|:---:|
| A2a 봇 유닛 | `launchd/bots/` |
| A2b 타이머 유닛 | `launchd/timers/` |
| A4 catch-up 러너 | `launchd/system/` |
| A7 BSD 호환성 감사 | `audits/` (bsd_compat_audit.md) |
| A5+A6 부트스트랩·의존성 | `scripts/bootstrap_macmini.sh`, `scripts/smoke_imports.sh`, `requirements-macmini.txt` (+`scripts/BOOTSTRAP_README.md`) |
| A8 rsync 컷오버 | `scripts/presync.sh`, `scripts/cutover_sync.sh`, `scripts/verify_data.sh` (+`scripts/RSYNC_README.md`) |
| A9+A10 런북·롤백 | `playbooks/DDAY_RUNBOOK.md`, `playbooks/ROLLBACK.md` |
| A12 GHA plist 초안 (Phase 2) | `launchd/gha/` |
| A14 Phase 2 컷오버 실행물 | `playbooks/PHASE2_RUNBOOK.md`, `patches/` (GHA schedule 제거 wave 패치) |
| A15 워치독 정합 감사 | `audits/phase2_watchdog_audit.md` |
| A16 git-pull 유닛 (Phase 1 갭) | `launchd/system/` 내 git-pull 관련 파일 (기존 소유팀) |
| 통합 (Fable) | `scripts/inventory_vm.sh`, CONTRACT/STATUS/BLUEPRINT 등 공용 문서, 그 외 전부 |

- 메인 repo `C:\Users\user\Antigravity_Market_Dashboard\`는 **전원 READ-ONLY** (systemd 원본 = `scripts/*.service|*.timer`)
- 타 패키지 경로·STATUS.md·BLUEPRINT.md 등 공용 문서 수정 금지 (통합은 Fable 전담)

## 공통 규칙

- **계층**: `/Library/LaunchDaemons` + `UserName` 지정 (결정 12), 시스템 TZ=**Asia/Seoul** (결정 10)
- **경로 토큰** (렌더링은 설치 스크립트가 sed 치환): `__MACMINI_USER__`, `__REPO__` = `/Users/__MACMINI_USER__/Antigravity_Market_Dashboard`
- **라벨**: `com.antigravity.<이름>` (파일명 = `<라벨>.plist`)
- **Python**: `__REPO__/venv/bin/python3` (pyenv 3.10.12 기반 venv — 결정 5)
- **env 주입 (v3 — 2026-07-06 확정)**: launchd엔 EnvironmentFile이 없음 → wrapper가 `.env`를 **안전 파서**로 로드. `set -a; source` 금지 (값 내 공백·`&`·`$()`·backtick이 쉘 해석됨). 규격: 행별로 첫 `=` 기준 KEY/VALUE 분리, KEY가 `^[A-Za-z_][A-Za-z0-9_]*$`일 때만 export, VALUE는 쉘 확장 없이 처리하되 **양끝을 감싼 동일 따옴표 한 쌍(`"..."` 또는 `'...'`)만 제거** (systemd EnvironmentFile 등가 — ★VM .env에 double-quote 값 1건 실존 확인, 리터럴 보존 시 해당 키 파손). 내부 따옴표·이스케이프는 그대로 보존. bash while-read로 구현(python 금지)
- **데몬 환경 표준**: 모든 plist `EnvironmentVariables`에 `HOME=/Users/__MACMINI_USER__`, `PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`, `LANG=en_US.UTF-8` 명시 (launchd는 로그인 환경이 없음)
- **stamp/로그 쓰기 원자성**: 공유 파일 갱신은 `mktemp`(같은 디렉토리) → `mv -f` 원자적 rename만 사용
- **로그**: `StandardOutPath`/`StandardErrorPath` = `__REPO__/logs/launchd/<이름>.out|.err`
- **실패 알림** (systemd OnFailure 대응): wrapper가 exit≠0 시 `__REPO__/scripts/notify_sisyphe_failure.sh <이름>` 호출
- **봇 공통**: `KeepAlive=true`, `ThrottleInterval=10` (Restart=always/RestartSec=10 대응), `WorkingDirectory` 원본 유닛과 동일
- **타이머 공통**: `StartCalendarInterval`은 **KST 기준으로 기술** (원본 OnCalendar가 UTC/Asia-Seoul 혼재 — 반드시 원본 확인 후 환산표 문서화)

## 배포 레이아웃 (통합 확정 — 2026-07-06)

- 이 `launchd/` 산출물 트리는 맥미니에서 **`__REPO__/launchd/`** 로 배포된다 (rsync 대상 포함). wrapper·러너 참조 경로는 전부 이 전제를 따름 (예: `__REPO__/launchd/bots/run_bot.sh`, `__REPO__/launchd/system/catchup_runner.sh`). 별도 위치(`__REPO__/scripts/launchd/` 등)로 복사 설치 금지 — 이중 사본 드리프트 방지.
- install 스크립트가 하는 일은 두 가지뿐: ① plist 토큰 치환 → `/Library/LaunchDaemons` 설치 ② schedule.tsv 치환본 → `__REPO__/logs/launchd/schedule.tsv` 설치 (catch-up 러너의 확정 읽기 경로).

## 패키지 간 인터페이스 (파일이 아니라 계약으로 연결)

0. **봇 starts 로그 (2차 리뷰로 격상)** — 봇 wrapper(A2a)는 매 기동 시 `__REPO__/logs/launchd/starts/<봇이름>.log`에 **epoch 정수(`date +%s`) 한 줄** append (최근 10줄 유지, mktemp+mv 원자 절삭). 크래시 워처(A4)는 epoch 정수가 아닌 행을 **무시**한다 (`tr`류 강제 숫자화 금지).
0-1. **봇 알림 carve-out (codex 승인)** — 봇 wrapper의 "exit≠0 → notify"에서 종료코드 130(SIGINT)·143(SIGTERM)은 launchd 의도적 중지(systemd clean-stop 등가)로 보아 **알림 제외**. crash-signal(SIGSEGV 등)은 알림 대상.
1. **성공 stamp** — 타이머 wrapper(A2b)는 잡 성공 시 `date +%s > __REPO__/logs/launchd/stamps/<이름>.last` 기록 (mktemp+mv). **기록 실패는 조용히 넘기지 말고 notify + 비정상 종료.** catch-up 러너(A4)는 이 stamp만 읽는다.
1-1. **잡별 동시실행 락** — `run_timer_job.sh`(A2b)가 잡 이름별 락(mkdir 기반, stale 회수는 rename 방식)을 잡는다. launchd 타이머 발화와 catch-up 직접 실행(A4)이 같은 wrapper를 거치므로 이 락이 중복 실행의 단일 방어선.
2. **schedule.tsv** — A2b가 `launchd/timers/schedule.tsv` 생성: `이름<TAB>KST 스케줄(cron 5필드)<TAB>실행 커맨드` 8행. A4는 이 파일을 파싱해 "부팅 시점에 놓친 잡"을 판정한다 (A4는 이 파일을 수정하지 않음). Phase 2에서 install_gha.sh가 GHA 행을 upsert.
2-1. **catch-up 허용 wrapper (2026-07-07 확장)** — A4의 커맨드 검증 허용 목록 = `launchd/timers/run_timer_job.sh` **및** `launchd/gha/run_gha_job.sh` (둘 다 잡별 락·stamp·notify·타임아웃 소유 wrapper). 그 외 커맨드는 경고+skip.
2-2. **잡당 tsv 1행 원칙 (결정 19)** — 러너가 같은 이름 복수 행을 같은 stamp로 이중 큐잉하므로, 복수 스케줄 잡(gha-universe 18:30+07:00)도 tsv엔 대표 1행(07:00)만. plist는 전 시각 정확 스케줄 — tsv는 catch-up 앵커일 뿐.
3. **notify 스크립트** — 모두 repo의 기존 `scripts/notify_sisyphe_failure.sh`를 호출만 (수정 금지).
