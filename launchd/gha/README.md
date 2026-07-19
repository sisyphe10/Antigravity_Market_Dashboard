# launchd GHA-잡 유닛 (WP-A12) — GitHub Actions 스케줄 워크플로우 9종 이관 초안 (Phase 2)

Oracle VM → 맥미니 이전의 **Phase 2**(GHA 스케줄 컴퓨트 흡수) 사전 산출물이다.
`GHA_MIGRATION_PLAN.md`의 이관 대상 9개 워크플로우를, Phase 1 타이머 세트(`launchd/timers/`)와
**동일한 패턴**으로 launchd LaunchDaemon + 공용 wrapper로 변환한 것이다.

> **상태: 초안 (draft).** plist XML 유효성·스케줄 환산 정확성·`bash -n`은 검증 완료.
> **실기(맥미니) 검증은 Phase 2**(Phase 1 이전 후 2주 무사고 안정화 뒤)에서 수행한다.
> 메인 repo(`Antigravity_Market_Dashboard`)는 이 작업 내내 **read-only**로만 참조했다.

## 배포 레이아웃 (CONTRACT 확정)

이 `launchd/` 트리는 맥미니에서 `__REPO__/launchd/`로 배포(rsync)된다.
wrapper `run_gha_job.sh`는 `__REPO__/launchd/gha/`에서 **in-place 실행**되며 별도 위치로 복사하지 않는다
(이중 사본 드리프트 방지). 그래서 wrapper는 토큰을 쓰지 않고 자기 경로에서 repo 루트를
self-locate(`launchd/gha/` → 두 단계 상위)한다. plist·`schedule_gha.tsv`는 이 in-place 경로
(`__REPO__/launchd/gha/run_gha_job.sh`)를 참조한다.

`install_*.sh`가 하는 일(타이머 패키지와 동일 규격): ① plist 토큰(`__REPO__`, `__MACMINI_USER__`) 치환
→ `/Library/LaunchDaemons` 설치, ② `schedule_gha.tsv` 치환본 → `__REPO__/logs/launchd/`에 설치
(A4 catch-up 러너의 확정 읽기 경로). **wrapper 복사 없음.**

## 파일 목록

| 파일 | 역할 |
|---|---|
| `com.antigravity.gha-<이름>.plist` × 11 | LaunchDaemon 정의 (`StartCalendarInterval` = KST, `EnvironmentVariables` HOME/PATH/LANG) |
| `run_gha_job.sh` | 공용 wrapper — self-locate + 잡별 동시실행 락 + **wrap-nav-pipeline 공유 락** + 안전 .env 파서 + 타임아웃 워치독 + 실행 + 원자적 성공 stamp + 실패 알림. ★`timers/run_timer_job.sh`를 **패턴 복제**(참조/수정 안 함, 소유권 분리) |
| `schedule_gha.tsv` | A4 catch-up 러너용 계약 파일 (`이름\tcron(5필드 KST)\t실행커맨드`, 11행) |
| `install_gha.sh` | 컷오버용 잡 단위 설치/제거기 — 잡별/웨이브별 plist 토큰 치환→`/Library/LaunchDaemons`→bootstrap + **공유 schedule.tsv upsert**, `--remove` 롤백. bash 3.2 호환 |
| `README.md` | 본 문서 |

## 잡별 매핑표 (워크플로우 → 스크립트·스케줄·타임아웃·Wave)

| 잡 이름 (label suffix) | 원본 워크플로우 | KST 스케줄 | 실행(도출한 스텝, 요약) | Timeout | Wave | 파이프라인 락 | API 키 게이트 |
|---|---|---|---|:---:|:---:|:---:|---|
| `gha-fred` | `daily_fred.yml` | 07:50 화~토 | fetch_fred_data → create_dashboard → safe_push(dataset.csv, market.html) | 900s | 1 | ✔ | `FRED_API_KEY` (없으면 skip) |
| `gha-universe` | `daily_universe.yml` | 18:30 + 07:00 매일 | fetch_universe → safe_push(universe.json, universe_history.json) | 1800s | 1 | ✔ | 없음 |
| `gha-ecos` | `daily_ecos.yml` | 17:40 월~금 | fetch_ecos_data → create_dashboard → safe_push(dataset.csv, market.html) | 900s | 1 | ✔ | `ECOS_API_KEY` (없으면 skip) |
| `gha-kofia` | `daily_kofia.yml` | 17:30 월~금 | fetch_kofia_stats + fetch_nps_fund → create_dashboard → safe_push(kofia_stats.json, index.html, dataset.csv, market.html) | 900s | 1 | ✔ | `DATA_GO_KR_API_KEY` (없으면 skip) |
| `gha-krx-valuation` | `daily_krx_valuation.yml` | 18:30 월~금 | fetch_krx_valuation → create_dashboard → safe_push(dataset.csv, market.html) | 900s | 2 | ✔ | `KRX_ID`+`KRX_PW` (없으면 skip) |
| `gha-disclosures` | `daily_disclosures.yml` | 16:30 매일 | fetch_disclosures + fetch_kind_disclosures → safe_push(disclosures.json, corp_codes.json) | 900s | 2 | ✘ | `DART_API_KEY` |
| `gha-crawl` | `daily_crawl.yml` (스케줄분만) | 23:00 매일 | 대형 파이프라인(백필·크롤·NAV·차트·SEIBro) → create_dashboard → safe_push(다수, `--xlsx-conflict bail`) | 3600s | 2 | ✔ | `KRX_ID`/`KRX_PW`(외국인, tolerated) |
| `gha-earnings-calendar-sync` | `earnings_calendar_sync.yml` | 07:00 매일 | earnings_calendar_sync **`--skip-ir-day`** (실적 캘린더만, git push 없음, Google Calendar 직접 기록) | 1800s | 3 | ✘ | `FINNHUB_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_KEY` |
| `gha-earnings-ir-day` | `earnings_calendar_sync.yml` | 07:15 매일 | earnings_calendar_sync **`--skip-earnings`** (IR Day = Finnhub 뉴스 315종목 + EDGAR 8-K, git push 없음) | 1800s | 3 | ✘ | `FINNHUB_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_KEY` |
| `gha-finalize-orders` | `finalize_orders.yml` | 16:00 매일 | finalize_pending_orders + finalize_pending_aum → calc_wrap_nav → calc_returns → create_portfolio_tables → create_dashboard → safe_push(`--xlsx-conflict fail`) | 1800s | 3 | ✔ | 없음 |
| `gha-taiwan-revenue` | `daily_taiwan_revenue.yml` | 23:20 매일 | fetch_taiwan_revenue + crosscheck(tolerated) → create_dashboard → safe_push(taiwan_revenue.csv, market.html) | 1800s | — | ✘ | FinMind(익명 폴백) |

> **2026-07-20 분리(★)**: `gha-earnings-calendar-sync`(07:00)가 실적 캘린더 Google Calendar 쓰기(~146건×3s)만으로 900s를 소진해 뒤따르던 IR Day(Finnhub 315종목)가 워치독에 강제종료됐다. → 실적/`IR Day`를 **두 잡으로 분리**(`--skip-ir-day`/`--skip-earnings`), IR Day는 07:15로 스태거·타임아웃 900→1800s. IR Day 실측 소요 ~9분(315종목). 두 잡은 `agearn…`/`agird…`로 이벤트 ID 네임스페이스가 달라 캘린더 중복 없음.

> **Timeout 주(★)**: 원본 GHA yml 9종 **어디에도 `timeout-minutes` 지정이 없다**(GHA 기본 360분 적용).
> 위 Timeout은 워치독용으로 잡 성격에 맞춰 **내가 부여한 보수적 추정치**다. Phase 2 실측 후 조정 대상.
>
> **파이프라인 락**: 원본 yml에 `concurrency: group: wrap-nav-pipeline`이 있는 7종에 ✔.
> `daily_disclosures`·`earnings_calendar_sync`는 원본에 concurrency 블록이 없어 ✘(아래 동시성 절 참조).

## UTC → KST 환산표 (원본 cron → launchd StartCalendarInterval)

**KST = UTC + 9h.** 원본 cron은 전부 UTC 기준(GHA 러너 표준). 맥미니 시스템 TZ = Asia/Seoul(결정 10)이라
launchd `StartCalendarInterval`은 **KST 벽시계 값 그대로** 기술한다. launchd Weekday: 0/7=일, 1=월, …, 6=토.

| 잡 | 원본 cron (UTC) | UTC 해석 | **+9h → KST** | 요일 이동 | launchd SCI |
|---|---|---|:---:|---|---|
| `gha-fred` | `50 22 * * 1-5` | 22:50 월~금 | **07:50 화~토** | ★+1일(익일로 넘어감) | array 5×{Weekday 2-6, 7:50} |
| `gha-universe` | `30 9 * * *` / `0 22 * * *` | 09:30 / 22:00 매일 | **18:30 / 07:00** | 07:00은 +1일(매일→매일) | array [{18:30},{7:00}] |
| `gha-ecos` | `40 8 * * 1-5` | 08:40 월~금 | **17:40 월~금** | 이동 없음 | array 5×{Weekday 1-5, 17:40} |
| `gha-kofia` | `30 8 * * 1-5` | 08:30 월~금 | **17:30 월~금** | 이동 없음 | array 5×{Weekday 1-5, 17:30} |
| `gha-krx-valuation` | `30 9 * * 1-5` | 09:30 월~금 | **18:30 월~금** | 이동 없음 | array 5×{Weekday 1-5, 18:30} |
| `gha-disclosures` | `30 7 * * *` | 07:30 매일 | **16:30 매일** | 이동 없음 | dict {16:30} |
| `gha-crawl` | `0 14 * * *` | 14:00 매일 | **23:00 매일** | 이동 없음 | dict {23:00} |
| `gha-earnings-calendar-sync` | `0 22 * * *` | 22:00 매일 | **07:00 매일** | +1일(매일→매일) | dict {7:00} |
| `gha-finalize-orders` | `0 7 * * *` | 07:00 매일 | **16:00 매일** | 이동 없음 | dict {16:00} |

### ★ 요일 이동 재검산 (환산의 핵심 함정 — `gha-fred`)

`daily_fred`는 cron 요일 `1-5`(월~금 UTC 22:50)인데, +9h 하면 시각이 07:50이 되면서 **날짜가 다음 날로 넘어간다**:
월UTC→화KST, 화→수, 수→목, 목→금, 금→토. 따라서 KST 요일은 **화~토(Weekday 2-6)**이다.
(원본 yml 주석도 "07:50 KST Tue-Sat"로 이를 확인.) 반면 ecos/kofia/krx는 KST 시각이 17~18시대라
날짜가 안 넘어가 요일 이동이 없다(월~금 그대로 = Weekday 1-5).

`gha-universe`·`gha-earnings-calendar-sync`의 22:00 UTC → 07:00 KST도 +1일이지만, 둘 다 **매일** 실행이라
"매일 → 매일"로 요일 제약이 무의미(단일/이중 dict로 그대로 기술).

## systemd/GHA → launchd 차이 (무엇이 보완하는가)

타이머 패키지(`launchd/timers/README.md`)와 동일한 보완 구조를 그대로 계승한다:

- **`EnvironmentFile=.env`** → wrapper `load_env()` 안전 파서(CONTRACT v3). `set -a; source` 금지.
- **데몬 로그인 환경 부재** → plist `EnvironmentVariables`에 HOME/PATH/LANG 명시 + wrapper가 `venv/bin`을 PATH 최상단으로 덧댐.
- **`OnFailure` 알림** → wrapper `notify_failure()` = `scripts/notify_sisyphe_failure.sh <이름>` 호출.
- **성공/실패 판정** → wrapper가 exit 코드 캡처 → 성공 stamp(`mktemp`+`mv -f`) / 실패 알림. stamp 기록 실패 시 notify + exit 70.
- **`TimeoutStartSec`** → wrapper 타임아웃 워치독(`set -m` 프로세스 그룹 kill, TERM→10s→KILL, 초과 시 exit 124).
- **단일 인스턴스 보장** → 잡별 동시실행 락(`logs/launchd/locks/<이름>.lock`, mkdir + rename-reclaim).
- **부팅 시 놓친 잡** → `schedule_gha.tsv` + stamp 계약으로 A4 catch-up 러너가 보완.

### GHA 고유 — 동시성(concurrency)의 락 변환

원본에서 7종이 공유하던 `concurrency: group: wrap-nav-pipeline` (`cancel-in-progress: false`)를
맥미니에서는 **공유 파이프라인 락**(`logs/launchd/locks/wrap-nav-pipeline.lock`)으로 대체했다
(GHA_MIGRATION_PLAN 절차 3의 "flock 락 파일" 요구).

- **목적**: 단일 워킹트리에서 여러 잡이 `create_dashboard.py`로 같은 HTML을 동시 재생성하거나 동시에
  push하는 것을 직렬화(로컬 손상·push 레이스 방지). `safe_commit_push.sh`가 push 레이스는 이미 자가복구하지만,
  로컬 HTML 재생성 인터리브는 별도 방어가 필요.
- **의미**: GHA는 두 번째 run을 취소하지 않고 **큐잉**했으므로, 여기서도 스킵이 아니라 **대기 획득**(blocking,
  상한 `PIPELINE_WAIT_CAP` 기본 3600s). 상한 초과 시 notify + exit 75(EX_TEMPFAIL, dispatch/캐치업 재시도 대상).
- **소속(7종)**: fred/universe/ecos/kofia/krx-valuation/crawl/finalize-orders.
  **제외(2종)**: disclosures·earnings-calendar-sync(원본에 concurrency 없음).
- **주의**: 현재 초안은 파이프라인 락을 **잡 전체 구간** 동안 보유한다(GHA 큐 의미에 충실). Phase 2에서
  경합/스루풋 실측 후, `create_dashboard`+push 구간만 감싸도록 좁히는 최적화 여지 있음(자체 리뷰 지점).

### GHA 고유 — heartbeat 방출 (Phase 2 워치독 감시 보조, CONTRACT 인터페이스 4)

wrapper는 **잡 성공 stamp 기록 직후** repo 루트 `heartbeats.json`에 `{"<잡이름>": <epoch>}`를 upsert하고
그 파일만 `[skip ci]`로 push한다. **9잡 전부 방출**한다(Wave 1부터 heartbeat가 쌓여 감시 커버가 이관 즉시 시작).

- **왜 필요한가**: 맥미니 타이머 실패는 (실행됨+비정상종료) 외에 **(아예 안 돎: 데몬 미적재·정전·TZ드리프트)**가 있고,
  후자는 wrapper가 안 돌아 `notify_failure`도 없다. 그 '비실행'은 **산출물 파일 신선도**로만 잡는데, `gha-earnings-calendar-sync`
  (산출물=Google Calendar, repo 밖)와 `gha-finalize-orders`(비시계열)는 dated repo 산출물이 없어 신선도 감시 공백이다
  (audit `phase2_watchdog_audit.md` §3). heartbeat가 이 공백을 메운다.
- **흐름**:
  1. `emit_heartbeat <잡>` — venv python으로 기존 `heartbeats.json` 병합(없거나 파손이면 새 dict) → `<잡>=now-epoch` → **같은 디렉토리 temp → `mv -f`** 원자적 갱신.
  2. `scripts/safe_commit_push.sh -m "heartbeat: <잡> [skip ci]" -- heartbeats.json` (파일 1개, `[skip ci]`로 daily_crawl 미기동).
- **소비자**: GHA 잔류 워치독 `check_data_freshness`의 heartbeat 나이 감시 섹션(`patches/heartbeat_freshness.patch` — A14/A15).
  `HEARTBEAT_JOBS`에 **없는 잡은 침묵**, 파일 부재/파싱 실패도 침묵 → **패치를 어느 시점에 적용해도 안전**(이관 전 상태 무해).
- **격리(감시 보조라 잡에 안 번짐)**: mktemp·JSON upsert·mv·push 어느 단계가 실패해도 **잡 종료코드(rc)는 불변**,
  경고 로그만 남긴다(다음 성공 방출이 자연 회복). heartbeat는 데이터 정합이 아니라 "살아있음" 신호라 push 레이스도 무해.
- **graceful-skip 잡**(API 키 미설정 fred/ecos/kofia/krx)도 rc=0이라 stamp+heartbeat 방출 — "wrapper가 정상 실행됨" 신호로 정확.

## 컷오버 절차 (잡별 1개씩 — GHA schedule 제거 커밋과 짝)

`GHA_MIGRATION_PLAN.md`의 표준 절차를 따른다. **하루 1개씩, 병행 실행 금지**(push race 방지):

1. 맥미니에서 `sudo ./install_gha.sh <잡이름>` — plist 토큰 치환→`/Library/LaunchDaemons`→bootstrap +
   해당 잡의 스케줄 행을 공유 `schedule.tsv`에 upsert(A4 catch-up 자동 커버). 아래 §install_gha.sh 참조.
2. `sudo launchctl kickstart -k system/com.antigravity.gha-<이름>`로 즉시 1회 테스트 → stamp·로그·라이브 데이터 확인.
3. **같은 날 짝 커밋**: 메인 repo에서 해당 워크플로우 yml의 **`schedule:` 트리거만 제거**하고
   `workflow_dispatch:`는 **유지**(롤백 = schedule 블록 복원 커밋 1개, 워크플로우 파일 삭제 금지).
4. 컷오버 후 1주 모니터링 — `check_data_freshness`가 산출 데이터 신선도로 자동 검증.
   실패 시 즉시 `gh workflow run <yml>`(workflow_dispatch)로 데이터 공백 메움.
5. 컷오버 로그 `logs/YYYY-MM-DD_gha_wave<N>.md` 기록.

**Wave 순서**: Wave 1(fred/universe/ecos/kofia) → Wave 2(krx-valuation/disclosures/crawl) →
**Wave 3(earnings-calendar-sync → finalize-orders)**. `finalize-orders`는 주문·AUM 확정 =
오동작 시 포트폴리오 데이터 직접 훼손이므로 **모든 Wave 안정화 후 최후에 이관**한다.

## install_gha.sh 사용법 (Phase 2 컷오버 도구)

컷오버는 잡 단위이므로 설치도 잡 단위다. **root 필수**(`/Library/LaunchDaemons` 쓰기 + system 도메인 launchctl).
bash 3.2 호환(macOS 기본 `/bin/bash`).

```bash
sudo ./install_gha.sh <잡이름>        # 잡 1개 설치 (권장: 컷오버 1일 1잡)
sudo ./install_gha.sh --wave <N>      # Wave N(1|2|3)의 잡 전부 설치 (검증 후 일괄/재설치용)
sudo ./install_gha.sh --remove <잡>   # 롤백: bootout + plist 삭제 + schedule.tsv 행 제거
sudo ./install_gha.sh --list          # 잡/웨이브 목록
```

동작:
- **설치**: `com.antigravity.<잡>.plist`의 `__REPO__`·`__MACMINI_USER__` 토큰을 sed 치환 → `/Library/LaunchDaemons`에
  설치(root:wheel 0644) → `launchctl bootout`(있으면)+`bootstrap system` → `launchctl enable`. 이어 `schedule_gha.tsv`의
  해당 잡 행을 `__REPO__` 치환해 **설치된 공유 `$REPO/logs/launchd/schedule.tsv`에 upsert**한다
  (동명 행이 있으면 교체, 없으면 append — 중복 방지). 타이머가 이미 넣어둔 행·다른 GHA 행은 건드리지 않는다.
- **제거(`--remove`)**: `bootout system/<label>` → plist 삭제 → `schedule.tsv`에서 그 잡 행만 제거. 롤백/재이관에 사용.
- **맥 사용자**(토큰 `__MACMINI_USER__`): `MACMINI_USER` 환경변수 > `SUDO_USER` > REPO 소유자(`stat -f`) > `id -un` 순.
- **원자성 + 반쪽 설치 방지** (codex 리뷰 반영): plist 는 목적지에 직접 쓰지 않고 **같은 디렉토리 temp → `mv -f`**(동일 FS 원자 rename)로
  설치해 부분/실패 sed 가 기존 plist 를 오염시키지 않는다. 이후 **bootstrap 실패 또는 schedule upsert 실패 시 `bootout`+plist 삭제로 롤백**
  (load 됐으나 tsv 행 없는 반쪽 상태 방지). `schedule.tsv` 갱신도 `mktemp`(같은 디렉토리)+`mv -f` 원자적, 소유자를 맥 사용자로 유지(래퍼가 user 로 stamps/locks 생성 + A4 read).

주의:
- `--wave`는 여러 잡을 한 번에 설치하므로 **표준 "하루 1잡" 컷오버 원칙과 배치**된다. 웨이브 전체가 이미 검증됐거나
  전면 재설치(예: repo 재배포 후) 때만 쓴다. 스크립트가 실행 시 이 점을 경고 출력한다.
- 설치는 plist 를 load 만 하고 **즉시 실행하지 않는다**(`RunAtLoad=false`). 즉시 1회 테스트는 위 컷오버 절차 2번의 `kickstart`.
- `schedule.tsv`는 타이머 패키지가 만든 것을 **공유**한다. GHA 잡 행은 upsert 로 얹히므로 A4 catch-up 이 타이머+GHA 를 한 파일로 커버.

## ★ 이관 시 반드시 처리할 항목 (판단·후속 필요 — 플래그)

1. **★ `earnings_calendar_sync` 이중 실행 정리 (결정 11)**: 현재 이 잡은 **VM cron(15:00 KST) + GHA(07:00 KST)
   두 번** 돈다. 맥미니 이전 시 **맥미니 단일화**로 통합해야 한다(GHA_MIGRATION_PLAN Wave 3 권장:
   맥미니가 유일 실행자, GHA는 workflow_dispatch 백업). → **Phase 1에서 VM cron이 맥미니로 넘어올 때, 이
   `gha-earnings-calendar-sync` 타이머와 시각을 하나로 합치고 나머지 하나를 제거**할 것. 시각(07:00 vs 15:00)은
   운영자 결정 사항(현 초안은 GHA 원본 07:00 KST 유지). 이중 실행 방치 시 캘린더 중복 기록 우려.

2. **`gha-disclosures` push 방식 변경**: 원본은 `stefanzweifel/git-auto-commit-action`(+`skip_fetch:true`)을 썼으나,
   맥미니엔 그 액션이 없으므로 **`safe_commit_push.sh`로 통일**했다(메시지·파일 패턴·`[skip ci]` 동일).
   기능 동등(오히려 push 레이스 자가복구가 추가됨). concurrency 그룹 밖이지만 xlsx를 안 건드려 xlsx 가드 무발동.

3. **`gha-crawl` 외부 도구 의존 (부트스트랩 전제)**: 원본은 매 run 스텝으로 **한글 폰트**(`fonts-nanum` 등)와
   **Chrome**(`browser-actions/setup-chrome`, SEIBro selenium용)을 설치했다. 맥미니에선 **A5/A6 부트스트랩이 미리
   설치**한 것을 전제로 하고 wrapper는 재설치하지 않는다. Chrome 미설치 시 `fetch_seibro_data.py`가 실패하나
   원본과 동일하게 tolerated(`|| echo`)라 잡 전체는 계속 진행. → 부트스트랩 체크리스트에 **Chrome + Pretendard/Nanum
   폰트**가 포함됐는지 Phase 2 착수 전 확인 필요.

4. **`run_*.sh` 헬퍼 하드코딩 경로 (타이머 패키지 공통 이슈)**: 이 GHA 잡들은 `scripts/run_*.sh`를 호출하지 않고
   대부분 `venv/python3 execution/<스크립트>` 직접 실행이라 A2b가 지적한 `/home/ubuntu` 하드코딩 문제의 직접 대상은
   아니다. 단 `safe_commit_push.sh`·`merge_wrap_nav.py`는 상대경로/`python3`(PATH)만 쓰므로 wrapper의 PATH 주입으로 해결됨.

5. **git push 인증**: 맥미니 repo clone에 origin push 권한(SSH 키 또는 토큰)이 있어야 `safe_commit_push.sh`가 동작.
   Phase 1 이전 체크리스트에서 push 자격 구성 확인(A8 rsync 범위 밖 인프라 항목).

6. **`schedule_gha.tsv`의 `gha-universe` 이중 스케줄 (자체 리뷰 지점 — 판단 필요)**: universe는 하루 2회(18:30·07:00)
   돌지만 5필드 cron 한 줄로는 두 시각을 표현할 수 없다. 과제 스펙(9행)에 맞춰 **catch-up 앵커로 07:00 한 시각만** 기재했다
   (밤샘 종료·정전 후 부팅 시 놓치기 쉬운 아침 실행을 우선 포착). **plist는 두 시각 모두 정확히 스케줄**하므로
   정시 실행엔 영향 없고, 이 tsv 축소는 A4 catch-up의 18:30 누락 감지만 약화(universe는 Wave 1 자가치유 + 23:00
   crawl이 관련 데이터 재수집이라 다음 실행이 흡수). → A4 러너가 잡당 복수 행을 지원하도록 확장하면 10행으로 정밀화 가능.

7. **`notify_sisyphe_failure.sh` generic 분기**: 9종 모두 스크립트에 전용 case가 없어 generic `*` 분기로 빠진다.
   알림은 정상 발송되나 안내 커맨드가 `journalctl -u <이름>.service`(Linux)라 launchd 환경엔 부적합.
   메인 repo read-only 계약이라 이 초안에선 손대지 않음 → mac 문구 추가는 별도 작업(Fable/후속 WP).

## 검증 (수행 완료)

- **`bash -n run_gha_job.sh` / `bash -n install_gha.sh`**: 둘 다 통과(구문 OK). `install_gha.sh`는 bash 3.2 금칙(연관배열·mapfile·`${v^^}`·`;;&`) 미사용 스캔도 클린.
- **`install_gha.sh` schedule.tsv 병합 로직**: 격리 하네스로 upsert(append)·재upsert(동명 교체=단일 유지)·`__REPO__` 치환·TAB 3필드 보존·미지정 잡 rc3 거부·`--remove`(행 제거하되 타이머 행 보존) 전부 확인.
- **`install_gha.sh` 원자화+롤백 (codex 수정)**: 격리 하네스로 ①정상=temp+mv 설치·토큰치환·upsert 실행·hidden temp 잔재 0 ②upsert 실패→bootout+plist 삭제 롤백 ③bootstrap 실패→plist 삭제·upsert 미도달 ④sed 실패→기존 dst 무손상(직접 쓰기 없음)·temp 정리 전부 확인.
- **`run_gha_job.sh` 소유권 확인 락 해제 (codex 수정)**: 격리 하네스로 ①우리 pid 락=삭제 ②남의 pid(재획득) 락=보존 ③빈 인자=no-op ④pid 없는 락=보존 확인 — per-job·pipeline 락 공통 함수. Wave 0 확정 패턴(`catchup_runner.sh:96` lock_release) 이식.
- **`run_gha_job.sh` heartbeat 방출 (인터페이스 4)**: 실제 wrapper를 gha-kofia graceful-skip 경로로 구동한 end-to-end 하네스로 ①빈/부재→heartbeats.json 생성 upsert ②기존 타 잡 엔트리(gha-other) 보존+대상 잡 추가 ③push 스텁 인자 정확(`-m heartbeat: <잡> [skip ci] -- heartbeats.json`) ④push 실패 시 wrapper rc 불변(0)+파일 갱신됨+경고 로그 전부 확인.
- **plist 9종**: `xml.dom.minidom.parse` + `plistlib.load`로 전부 **well-formed + 유효 plist** 확인.
  `StartCalendarInterval` 파싱 결과가 위 환산표와 1:1 일치, Label=파일명, ProgramArguments 인자=label suffix,
  EnvironmentVariables에 HOME/PATH/LANG 존재까지 자동 대조 → 9/9 OK.
  (초기 `gha-finalize-orders`는 주석 내 `--xlsx-conflict`의 `--`가 XML 주석 금칙 → 문구 `xlsx-conflict=fail`로 수정 후 통과.)
- **`schedule_gha.tsv`**: 9행, 각 행 3필드(TAB 2개) 확인.
- **환산표**: 각 워크플로우 cron(UTC) → +9h → KST를 요일 이동 포함 재검산(특히 `gha-fred`의 화~토, 22:00 UTC 잡의 +1일).

**실기 검증(맥미니, Phase 2)** — 설치 후:
```bash
sudo launchctl list | grep com.antigravity.gha      # 적재된 9개 라벨 + 마지막 exit status
sudo launchctl print system/com.antigravity.gha-fred # 개별 잡 상태/다음 실행
sudo launchctl kickstart -k system/com.antigravity.gha-ecos   # 즉시 테스트
ls -l <REPO>/logs/launchd/stamps/gha-*.last          # 성공 stamp 확인
```
> launchd엔 `systemctl list-timers` 같은 "다음 발화 일람표"가 없다. 잡별 `launchctl print`로 확인.
