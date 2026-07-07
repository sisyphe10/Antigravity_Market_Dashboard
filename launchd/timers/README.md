# launchd 타이머 유닛 (WP-A2b) — systemd 타이머 8종 이전

Oracle VM(Ubuntu, systemd)의 스케줄 타이머 8종을 맥미니(macOS, launchd)로 변환한 산출물이다.
시스템 TZ = **Asia/Seoul** 전제(결정 10). plist·schedule.tsv 의 경로는 토큰(`__REPO__`, `__MACMINI_USER__`)으로 두고
`install_timers.sh` 가 sed 로 치환한다.

**배포 레이아웃 (CONTRACT 확정)**: 이 `launchd/` 트리는 맥미니에서 `__REPO__/launchd/` 로 배포(rsync)된다.
wrapper `run_timer_job.sh` 는 **`__REPO__/launchd/timers/` 에서 in-place 실행**되며 별도 위치로 **복사하지 않는다**(이중 사본 드리프트 방지).
그래서 wrapper 는 토큰을 쓰지 않고 **자기 경로에서 repo 루트를 self-locate**(`launchd/timers/` → 두 단계 상위)한다.
plist·schedule.tsv 는 이 in-place 경로(`__REPO__/launchd/timers/run_timer_job.sh`)를 참조한다.

## 파일 목록

| 파일 | 역할 |
|---|---|
| `com.antigravity.<이름>.plist` × 8 | LaunchDaemon 정의 (StartCalendarInterval = KST, `EnvironmentVariables` HOME/PATH/LANG) |
| `run_timer_job.sh` | 공용 wrapper — self-locate + **잡별 동시실행 락** + 안전 .env 파서 + 타임아웃 워치독 + 실행 + 원자적 성공 stamp(실패 시 notify+비정상종료) / 전용 실패 알림 |
| `schedule.tsv` | A4 catch-up 러너용 계약 파일 (`이름\tcron(5필드)\t실행커맨드`, 8행) |
| `install_timers.sh` | ① plist 토큰 치환 → `/Library/LaunchDaemons` + `bootstrap`, ② schedule.tsv 치환본 → `logs/launchd/` (**두 작업뿐** — wrapper 복사 없음) |
| `README.md` | 본 문서 |

## 대상 8종 — UTC → KST 환산표

**핵심 발견: 원본 8종의 `OnCalendar` 은 전부 `Asia/Seoul` 로 명시돼 있다. UTC 기준 유닛은 하나도 없었다.**
"UTC vs KST 혼재"라는 인상은 VM 의 시스템 TZ 가 UTC 라 `systemctl list-timers` 의 "NEXT" 컬럼이
UTC 로 표시되기 때문이며, `OnCalendar` 지시자 자체(=진짜 스케줄)는 모두 Asia/Seoul 이다.
따라서 **KST 환산 = OnCalendar 시각 그대로(항등)**, VM list-timers 의 UTC = KST − 9h. VM 실측치와 전부 일치.

| 이름 | 원본 OnCalendar (인용) | VM 실측(UTC, list-timers) | **KST** | launchd StartCalendarInterval | cron(5필드) |
|---|---|---|:---:|---|---|
| featured-kis | `*-*-* 15:50:00 Asia/Seoul` | 06:50 UTC | **15:50** | Hour 15 / Minute 50 | `50 15 * * *` |
| etf-collect | `*-*-* 16:30:00 Asia/Seoul` | 07:30 UTC | **16:30** | Hour 16 / Minute 30 | `30 16 * * *` |
| etf-collect-retry | `*-*-* 18:00:00 Asia/Seoul` | 09:00 UTC | **18:00** | Hour 18 / Minute 0 | `0 18 * * *` |
| landing-highlights | `*-*-* 18:45:00 Asia/Seoul` (2026-07-07 18:35→18:45 이격 — R1) | ~09:45 UTC | **18:45** | Hour 18 / Minute 45 | `45 18 * * *` |
| etf-active-alert | `*-*-* 19:00:00 Asia/Seoul` | 10:00 UTC | **19:00** | Hour 19 / Minute 0 | `0 19 * * *` |
| kodex-sectors | `*-*-* 23:30:00 Asia/Seoul` | 14:30 UTC | **23:30** | Hour 23 / Minute 30 | `30 23 * * *` |
| earnings-bot | `*-*-* 08:00:00 Asia/Seoul` | 23:00 UTC (전날) | **08:00** | Hour 8 / Minute 0 | `0 8 * * *` |
| update-stock-master | `Sat *-*-* 09:00:00 Asia/Seoul` | Sat 00:00 UTC | **토 09:00** | Weekday 6 / Hour 9 / Minute 0 | `0 9 * * 6` |

- **환산 근거**: KST = UTC + 9h. 원본 지시자가 이미 Asia/Seoul 이므로 mac(TZ=Asia/Seoul)에서 동일 시각을 그대로 기술.
  VM 실측치는 전부 "KST − 9h = UTC" 를 만족(예: 15:50 KST − 9 = 06:50 UTC)해 원본과 모순 없음.
- **launchd Weekday**: 0/7=일, 1=월, …, 6=토 → update-stock-master 는 `Weekday 6`.

## systemd → launchd 차이 (그리고 무엇이 보완하는가)

| systemd 기능 | launchd 대응 | 비고 |
|---|---|---|
| `Persistent=true` (부팅 시 놓친 잡 실행) | **부분 대응** | launchd 는 sleep 중 놓친 스케줄을 깨어날 때 1회만 실행, **완전 종료(shutdown) 중 놓친 건 건너뜀**. → **A4 catch-up 러너가 stamp + schedule.tsv 로 완전 보완**(이 패키지의 stamp 계약이 그 입력). |
| `EnvironmentFile=…/.env` | wrapper 안전 파서(`load_env`) | **CONTRACT v3**: `set -a; source` 금지(값 내 `$()`·backtick·`&`·JSON 이 쉘 해석됨). 행별 첫 `=` 로 KEY/VALUE 분리 → KEY 검증(`^[A-Za-z_][A-Za-z0-9_]*$`) → `export KEY=VALUE`(확장 없음). **양끝을 감싼 동일 따옴표 한 쌍(`"..."`/`'...'`)만 제거**(systemd 등가), 내부 따옴표는 보존 — ★VM .env 의 double-quote 값 1건(GOOGLE_SERVICE_ACCOUNT_KEY류)이 따옴표째 주입돼 깨지는 것 방지. |
| (없음) 데몬 로그인 환경 부재 | plist `EnvironmentVariables` | **CONTRACT v3**: 8종 전부 `HOME=/Users/<user>`, `PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`, `LANG=en_US.UTF-8` 명시. wrapper 는 여기에 `venv/bin` 을 PATH 최상단으로 덧댐. |
| `OnFailure=…-notify.service` | wrapper `notify_failure()` 분기 호출 | **landing-highlights 는 전용 `notify_landing_highlights_failure.sh`(인자 없음) 호출**(원본 landing-highlights-notify.service 등가). 나머지 7종은 `notify_sisyphe_failure.sh <이름>`(원본 sisyphe-bot-notify@ / earnings-bot-notify 대응). |
| `Type=oneshot` 성공/실패 판정 | wrapper 가 exit 코드 캡처 → 성공 stamp / 실패 알림 | 성공 stamp 는 `mktemp`+`mv -f` 원자적 rename(A4 가 빈/부분 파일 읽는 레이스 제거). **stamp 기록 자체가 실패하면 조용히 넘기지 않고 `notify` + exit 70**(잡 성공을 A4 가 미실행으로 오판하는 것 방지 — 인터페이스 1). |
| (systemd 단일 인스턴스 보장) | wrapper **잡별 동시실행 락** | launchd 발화와 A4 catch-up 직접 실행이 같은 wrapper 를 거치므로, 중복 실행의 단일 방어선(인터페이스 1-1). 아래 별도 섹션 참조. |
| **`TimeoutStartSec=…` (잡 강제종료 타임아웃)** | **wrapper 타임아웃 워치독으로 구현** | macOS 엔 coreutils `timeout` 없음 → bash monitor mode(`set -m`)로 잡을 자체 프로세스 그룹에 넣고, 초과 시 그룹 전체에 **TERM → 10초 유예 → KILL**. 타임아웃 시 exit 124 → 실패 처리(notify, stamp 미기록). 원본 값 그대로: featured-kis 15min / etf-collect·retry 30min / landing-highlights 5min / etf-active-alert 10min / kodex-sectors 10min / earnings-bot 45min / update-stock-master 15min. |
| `AccuracySec=…` (합병 창) | 등가물 없음 → 생략 | launchd 는 벽시계 시각에 발화(자체 경량 coalescing) |
| `RandomizedDelaySec=60` (landing-highlights) | 등가물 없음 → 생략 | 단일 잡이라 지터 무의미 |
| `After/Wants=network-online.target` | 등가물 없음 → 미복제 | 네트워크 미기동 시 잡 실패 가능 → 실패 알림 + 익일/캐치업 재시도로 흡수 |

## 잡 매핑 (wrapper 내부)

| 이름 | 실제 실행 (원본 ExecStart 기준) |
|---|---|
| featured-kis | `venv/python3 execution/fetch_featured_data_kis.py` → (실패무시) `enrich_newhigh_themes.py` |
| etf-collect / etf-collect-retry | `bash scripts/run_etf_collect.sh` (재개형·idempotent) |
| landing-highlights | `bash scripts/run_landing_highlights.sh` |
| etf-active-alert | `bash scripts/run_etf_active_alert.sh` |
| kodex-sectors | `bash scripts/run_kodex_sectors.sh` |
| earnings-bot | `venv/python3 -m execution.earnings_bot.runner` |
| update-stock-master | `bash scripts/run_update_stock_master.sh` |

> featured-kis 는 원본에서 enrich 단계가 `ExecStartPost=-…`(`-` 접두)로 **실패해도 서비스 성공**이었다.
> wrapper 도 동일하게 fetch 성공 여부로만 stamp/알림을 결정하고 enrich 실패는 무시한다.

## 잡별 동시실행 락 (인터페이스 1-1)

launchd 타이머 발화와 A4 catch-up 러너의 직접 실행이 **같은 wrapper** 를 거치므로, 둘이 동시에 같은 잡을
띄우면 중복 실행이 된다. 이를 막는 단일 방어선이 잡 이름별 락이다.

- **락 = 디렉토리** `<REPO>/logs/launchd/locks/<이름>.lock` — `mkdir` 는 원자적이라 "동시에 둘이 성공"할 수 없다. 획득 즉시 안에 `pid`(=`$$`) 기록.
- **이미 살아있는 홀더**(`pid` 가 `kill -0` 로 생존 확인)면 두 번째 인스턴스는 **조용히 스킵(exit 0)** — 원본 `run_etf_collect.sh` 의 flock `exit 0` 스킵 의미와 동일. 실행 중인 쪽이 stamp 를 남긴다.
- **stale 락 회수는 rename 방식**(★`rm -rf` 후 `mkdir` 재시도식 TOCTOU 금지): 죽은/orphan 홀더면 락 dir 을 **고유 임시명(`.reclaim.$$.$RANDOM`)으로 `mv`** → `mv` 에 성공한 1개 프로세스만 그 stale dir 을 소유 → 내용 재확인(그새 살아났으면 되돌리고 스킵) 후 삭제 → `mkdir` 재시도. 회수 도중 다른 인스턴스가 선점하면 스킵.
- **갓 생성된 락의 pid 공백 창**은 `pid` 를 최대 3회(0.2s 간격) 재시도로 읽어 흡수 → 라이브 홀더를 stale 로 오판하지 않는다.
- 락은 `trap release_lock EXIT` 로 **정상/실패/타임아웃 어느 종료 경로든 해제**(`rm -rf` 자기 락). 하드 크래시로 남은 락만 다음 회차가 rename 회수.

## 검증

### plist well-formed 검증 (Python)
`plistlib.load` + `xml.dom.minidom.parse` 로 8종 전부 검사 — **8/8 well-formed + 유효 plist**.
StartCalendarInterval 파싱 결과가 환산표와 일치함을 확인:

```
earnings-bot         well-formed  sci={'Hour': 8,  'Minute': 0}
etf-active-alert     well-formed  sci={'Hour': 19, 'Minute': 0}
etf-collect-retry    well-formed  sci={'Hour': 18, 'Minute': 0}
etf-collect          well-formed  sci={'Hour': 16, 'Minute': 30}
featured-kis         well-formed  sci={'Hour': 15, 'Minute': 50}
kodex-sectors        well-formed  sci={'Hour': 23, 'Minute': 30}
landing-highlights   well-formed  sci={'Hour': 18, 'Minute': 45}
update-stock-master  well-formed  sci={'Weekday': 6, 'Hour': 9, 'Minute': 0}
```

### 타임아웃 워치독 데스크체크 (bash 로직)
빠른 잡(2s)/느린 잡(30s)을 각각 5s·2s 타임아웃으로 실행하는 자립 하네스로 워치독 로직을 검증했다:
- 2s 잡 / 5s 타임아웃 → **rc=0, 정상 완료** (stamp 기록 경로)
- 30s 잡 / 2s 타임아웃 → **약 2초 만에 rc=124 반환 + 프로세스 종료** (실패 경로: notify 호출, stamp 미기록)

프로세스 그룹 kill(`set -m` + `kill -TERM -pgid`)은 POSIX/BSD 의미로 macOS 에서 손자 프로세스까지 정리된다
(Git Bash 하네스는 로직/반환코드/타이밍만 확인; pgroup 시맨틱은 macOS 대상 설계).

### .env 안전 파서 검증 (v3 따옴표 스트립 포함)
- `KEY={"json":"a b","x":$(whoami)}` (따옴표 없는 raw 값) → `$(whoami)` 가 **실행되지 않고 리터럴로** export (`set -a; source` 였다면 명령 치환 실행됨).
- `KEY="{"type":"service_account",...}"` (VM 실존 double-quote 값 케이스) → 양끝 `"` **한 쌍만 제거**돼 `{"type":"service_account",...}` 로 주입, **내부 따옴표 보존**.
- `KEY='{"type":...}'` (single-quote JSON) → 양끝 `'` 제거, 내부 double-quote 보존.
- `1BAD=…` / `BAD-KEY=…` (부적격 KEY) → 스킵. `KEY="unterminated` (짝 안 맞음) → 스트립 안 함(리터럴 유지).

### 동시실행 락 데스크체크 (bash 로직)
같은 잡 이름으로 wrapper 를 **동시에 2회** 띄우고(느린 잡), 임시 `locks/` 를 써서 검증:
- **정확히 1개만 진입**(락 획득 → 잡 실행 = 카운터 1), 다른 1개는 스킵(exit 0) 확인.
- 죽은 홀더 pid 를 심은 stale 락 → rename 회수 후 정상 획득, `.reclaim.*` 잔재 없음 확인.

### 설치 후 검증 (맥미니에서)
```bash
sudo ./install_timers.sh <MACMINI_USER>          # 설치 + bootstrap
sudo launchctl list | grep com.antigravity        # 적재된 8개 라벨 + 마지막 exit status
sudo launchctl print system/com.antigravity.featured-kis   # 개별 잡 상태/다음 실행
# 즉시 테스트(스케줄 안 기다리고):
sudo launchctl kickstart -k system/com.antigravity.kodex-sectors
ls -l <REPO>/logs/launchd/stamps/                 # 성공 stamp 확인
cat <REPO>/logs/launchd/<이름>.out                # 표준출력 로그
# 타임아웃 실동작 확인(원하면): job_timeout_seconds 를 임시로 5 로 낮춰 kickstart →
#   .err 에 "TimeoutStartSec(5s) 초과 → 프로세스 그룹 강제 종료" + exit 124 + stamp 미갱신 확인
```
> launchd 에는 `systemctl list-timers` 같은 "다음 발화 일람표"가 없다. 잡별 `launchctl print` 로 확인한다.

## 이전 시 반드시 처리할 외부 의존 (A2b 범위 밖 — 플래그)

1. **`scripts/run_*.sh` 헬퍼의 하드코딩 경로**: `run_etf_collect.sh` 등이 `REPO=/home/ubuntu/Antigravity_Market_Dashboard`
   를 하드코딩하고 내부에서 `python3`(PATH 의존)를 호출한다. 맥에서는 `/home/ubuntu/…` 가 없어 **cd 실패**.
   wrapper 가 `PATH` 최상단에 `venv/bin` 을 넣어 `python3` 는 해결하지만, **하드코딩된 `/home/ubuntu` 경로는 고칠 수 없다**
   (메인 repo read-only). → run_*.sh 5종은 마이그레이션 중 A7/Fable 가 경로를 `$REPO` 상대 또는 mac 경로로 패치해야 함.
2. **`notify_sisyphe_failure.sh` 메시지**: featured-kis/etf-collect/etf-collect-retry/etf-active-alert/update-stock-master 는
   스크립트의 `case` 에 전용 분기가 없어 generic `*` 분기(문구가 `journalctl -u <이름>.service` 를 안내)로 빠진다.
   알림 자체는 정상 발송되나 안내 커맨드가 launchd 환경엔 부적합 → 필요 시 mac 문구 추가는 별도 작업(수정 금지 계약이라 A2b 는 손대지 않음).
   (landing-highlights 는 전용 `notify_landing_highlights_failure.sh` 로 분기하므로 이 항목과 무관. kodex-sectors/earnings-bot 은 전용 분기 있음.)
3. **schedule.tsv 토큰**: 커맨드 컬럼이 `__REPO__` 토큰을 담는다. `install_timers.sh` 가 치환본을
   `<REPO>/logs/launchd/schedule.tsv` 로 설치하므로 **A4 는 그 치환본을 읽어야 한다**(원본 `launchd/timers/schedule.tsv` 는 토큰 상태).

## stamp / 실패 알림 계약 (A4·notify 연결)

- 성공: `<REPO>/logs/launchd/stamps/<이름>.last` 에 `date +%s` 기록. **`mktemp`(같은 디렉토리)+`mv -f` 원자적 rename** — A4 가 빈/부분 파일을 읽지 않도록 보장.
- **stamp 기록 실패**(mkdir/mktemp/date/mv 중 하나라도 실패): 조용히 넘기지 않고 `notify_failure` 호출 + **exit 70** — 잡은 성공했지만 A4 가 성공으로 오판하지 않게 명시적 실패(인터페이스 1).
- 실패(exit≠0/타임아웃 124): landing-highlights → `notify_landing_highlights_failure.sh`, 나머지 → `notify_sisyphe_failure.sh <이름>`. 호출 후 원래 exit 코드 유지, stamp 미기록.
- **동시실행 스킵**(락 미획득): exit 0, 잡 미실행, stamp 미기록(실행 중인 인스턴스가 stamp 를 남김). 위 "잡별 동시실행 락" 참조.
- etf-collect-retry 는 자기 이름으로 별도 stamp(`etf-collect-retry.last`) 기록 — A4 가 두 잡을 독립 추적.
- **락 파일 경로**: `<REPO>/logs/launchd/locks/<이름>.lock` (wrapper 가 런타임 생성, A4 와 공유하는 방어선).
