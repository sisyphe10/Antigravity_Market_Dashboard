# 상시 봇 launchd 유닛 (WP-A2a)

Oracle VM(Ubuntu, systemd) → 맥미니(macOS, launchd) 이전의 **상시 실행 텔레그램 봇 4종** 변환물.
원본 systemd 유닛: `Antigravity_Market_Dashboard/scripts/<이름>.service` (READ-ONLY).

계약: `../CONTRACT.md`(v3 + 인터페이스 0/0-1) 준수 — `/Library/LaunchDaemons` + `UserName`, 라벨 `com.antigravity.<이름>`,
venv python, wrapper **안전 파서** env 주입, 데몬 환경 표준(HOME/PATH/LANG), 로그 `__REPO__/logs/launchd/`,
공유 파일 원자적 갱신(mktemp+mv).

`__REPO__` = `/Users/__MACMINI_USER__/Antigravity_Market_Dashboard`. plist 안에는 이 경로가
**완전히 전개**돼 있어(예: `/Users/__MACMINI_USER__/Antigravity_Market_Dashboard/...`), 설치 시
`__MACMINI_USER__` **단일 토큰**만 sed 치환하면 모든 경로가 렌더링된다.

## 파일 목록

| 파일 | 내용 |
|---|---|
| `com.antigravity.sisyphe-bot.plist` | Sisyphe-Bot (펀드/일상) LaunchDaemon |
| `com.antigravity.ra-sisyphe-bot.plist` | RA_Sisyphe_bot (리서치 알림) LaunchDaemon |
| `com.antigravity.research-notes-bot.plist` | Research Notes 봇 LaunchDaemon (하위폴더 WorkingDirectory + PYTHONIOENCODING) |
| `com.antigravity.seonyuduo-exercise-bot.plist` | 선유듀오 운동봇 LaunchDaemon (execution/ WorkingDirectory + PYTHONIOENCODING) |
| `run_bot.sh` | 공용 봇 wrapper — 안전 env 파서 + 네트워크 대기 + child 실행 + 실패 알림/지연 |
| `install_bots.sh` | 맥미니 설치 스크립트(사용자명 검증 → 사전 게이트 → 토큰 치환 → 복사 → bootstrap) |
| `README.md` | 이 문서 |

## systemd → launchd 매핑표 (지시자 → plist 키/처리)

| systemd 지시자 (원본 `.service`) | launchd 처리 | 비고 |
|---|---|---|
| `[Service] User=ubuntu` | `UserName` = `__MACMINI_USER__` | LaunchDaemon 이 지정 사용자로 실행 (결정 12) |
| `WorkingDirectory=<경로>` | `WorkingDirectory` | 원본과 동일 경로(맥 기준) |
| `ExecStart=/usr/bin/python3 <script>` | `ProgramArguments` = `[run_bot.sh, <봇이름>, venv/bin/python3, <script>]` | 시스템 python → **venv python** (결정 5). wrapper 경유 |
| `EnvironmentFile=.../.env` | wrapper 의 **안전 파서**(첫 `=` 분리·양끝 동일 따옴표 한 쌍만 제거·리터럴 export, `set -a source` 금지) | CONTRACT v3. double/single-quote 스트립, JSON 한 줄 값 무손상 |
| `Environment=PYTHONIOENCODING=utf-8` | `EnvironmentVariables` dict | research-notes / seonyuduo 만 |
| (신규) 데몬 환경 표준 | `EnvironmentVariables`: `HOME`,`PATH`,`LANG` | 전 4종. launchd 는 로그인 환경 없음 (CONTRACT v3) |
| `Restart=always` | `KeepAlive` = `true` (wrapper=**child** 실행) | 어떤 종료여도 재기동 |
| `RestartSec=10` | wrapper **`sleep 10`**(재기동 경로=rc0+크래시 모두) + `ThrottleInterval=10`(바닥) | stop 시그널(130/143)은 제외. ThrottleInterval≠RestartSec — 아래 차이점 |
| `OnFailure=sisyphe-bot-notify@<unit>.service` | wrapper 가 **정상 실패 시 `notify_sisyphe_failure.sh <봇이름>` 호출** | child 종료코드 캡처로 구현. stop 시그널은 제외 |
| `StartLimitBurst=10` / `StartLimitIntervalSec=300` | (네이티브 등가물 없음) | 크래시 루프 억제는 **A4 crash_watcher**(starts 로그 소비)로 대체 — 아래 차이점 |
| `[Install] WantedBy=multi-user.target` | `RunAtLoad` = `true` + `launchctl enable` | 부팅/부트스트랩 시 기동 |
| `[Service] Type=simple` | (키 없음) | launchd 기본 실행 모델과 동일 |
| `[Unit] After=network.target` | wrapper **네트워크 대기**(api.telegram.org:443, ≤120s/5s) + KeepAlive | 아래 차이점 |
| `[Unit] Description=...` | (키 없음) | launchd 에 Description 없음. `Label` 이 식별 담당 |

## 봇별 요약

| 봇 | Label | WorkingDirectory (맥) | 실행 스크립트 | 특이 |
|---|---|---|---|---|
| sisyphe-bot | com.antigravity.sisyphe-bot | `__REPO__` | `execution/sisyphe_bot.py` (상대) | — |
| ra-sisyphe-bot | com.antigravity.ra-sisyphe-bot | `__REPO__` | `execution/ra_sisyphe_bot.py` (상대) | — |
| research-notes-bot | com.antigravity.research-notes-bot | `__REPO__/execution/research_bot` | `.../execution/research_bot/research_notes_bot.py` (절대) | PYTHONIOENCODING=utf-8 |
| seonyuduo-exercise-bot | com.antigravity.seonyuduo-exercise-bot | `__REPO__/execution` | `.../execution/seonyuduo_exercise_bot.py` (절대) | PYTHONIOENCODING=utf-8 |

- sisyphe/ra 는 원본이 상대경로 ExecStart(`execution/*.py`) + WorkingDirectory=repo 루트 → 그대로 유지(launchd 가 chdir 후 child 실행 → 상대경로 해석됨).
- research-notes/seonyuduo 는 원본이 절대경로 ExecStart → 그대로 절대경로 유지.
- 전 4종 `EnvironmentVariables` 에 `HOME=/Users/__MACMINI_USER__`, `PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`, `LANG=en_US.UTF-8` 명시(데몬 환경 표준).

## 지시자 누락 대조표 (자체 점검)

원본 `.service` 의 모든 지시자를 1:1 확인. **누락 없음.** OnFailure/After 는 wrapper 로 **구현**됨.
StartLimit* 만 네이티브 등가물이 없어 A4 crash_watcher 로 대체(설계상 위임, 아래 차이점).

| # | 지시자 | sisyphe | ra | research-notes | seonyuduo | 처리 |
|---|---|:---:|:---:|:---:|:---:|---|
| 1 | Description | ✓ | ✓ | ✓ | ✓ | Label 로 대체 |
| 2 | After=network.target | ✓ | ✓ | ✓ | ✓ | **wrapper 네트워크 대기 + KeepAlive** |
| 3 | StartLimitBurst=10 | △ | △ | △ | △ | 네이티브 등가물 없음 → **A4 crash_watcher 대체** |
| 4 | StartLimitIntervalSec=300 | △ | △ | △ | △ | 상동(크래시 루프 판정 창) |
| 5 | OnFailure=...notify | ✓ | ✓ | ✓ | ✓ | **wrapper 가 정상 실패 시 notify 호출** |
| 6 | User=ubuntu | ✓ | ✓ | ✓ | ✓ | UserName |
| 7 | WorkingDirectory | ✓ | ✓ | ✓ | ✓ | WorkingDirectory |
| 8 | ExecStart | ✓ | ✓ | ✓ | ✓ | ProgramArguments(wrapper+venv) |
| 9 | Restart=always | ✓ | ✓ | ✓ | ✓ | KeepAlive=true |
| 10 | RestartSec=10 | ✓ | ✓ | ✓ | ✓ | wrapper sleep 10 (rc0+크래시, stop시그널 제외) + ThrottleInterval 바닥 |
| 11 | EnvironmentFile | ✓ | ✓ | ✓ | ✓ | wrapper 안전 파서 |
| 12 | Type=simple | — | — | ✓ | ✓ | launchd 기본(키 불필요) |
| 13 | Environment=PYTHONIOENCODING | — | — | ✓ | ✓ | EnvironmentVariables |
| 14 | WantedBy=multi-user.target | ✓ | ✓ | ✓ | ✓ | RunAtLoad + enable |

`△` = 네이티브 등가물 부재로 계약상 A4 로 위임. 나머지는 이 패키지 내에서 처리 완료.

## 검증 방법 & 결과

이 환경엔 맥 전용 `plutil` 이 없어 **python `xml.etree`** 로 well-formed 검증(맥에선 추가로 `plutil -lint` 권장).

- **plist XML well-formed (`xml.etree`)** — 4/4 통과. dict 키/값 짝수 정합, 루트=plist, `EnvironmentVariables` 하위키 확인.
  - sisyphe/ra: HOME·PATH·LANG (10 keys) / research·seonyuduo: HOME·PATH·LANG·PYTHONIOENCODING (10 keys)
- **쉘 문법 (`bash -n`)** — run_bot.sh, install_bots.sh 통과.
- **안전 .env 파서 (가짜 .env 로 실행)** — 통과:
  - `SIMPLE=abc`, 따옴표 값(`"a b c"`→`a b c`, `'hello world'`→공백 보존), JSON 한 줄(`GOOGLE_SERVICE_ACCOUNT_KEY='{...,"priv":"a=b=c",...}'` → 내부 `=`·따옴표 무손상), `EQ_IN_VAL=k=v=w`(첫 `=` 분리), 선행공백+`export ` 접두, 무효 키(`123BAD`) 스킵.
  - **보안**: `$(touch ...)`·backtick·`&`·`#` 포함 값이 **리터럴로 export 되고 실행되지 않음**(probe 파일 미생성 확인).
- **wrapper 제어흐름 (mock notify + mock bot, sleep 계측)** — 통과:
  - exit 0 → notify **없음** + **sleep 적용**(rc=0 재기동 경로도 RestartSec 등가 지연, 계측 ~2s).
  - exit 3(크래시) → notify `<봇이름>` **1회 호출** + sleep 적용 → rc=3.
  - SIGTERM 을 **wrapper 로** 전달(launchd bootout/deploy 경로) → child 가 TERM 수신(graceful) → rc=143, notify **없음**, **지연 0s**(즉시 종료).
  - SIGINT/SIGTERM(rc 130/143)은 "의도적 중지"로 분류돼 알림·지연 모두 제외.
- **CHILD 재사용 PID 방지** — child 반환 후 `CHILD=""` 로 초기화. 크래시 후 sleep 중 wrapper 에 TERM 주입 시 `forward_term` 이 `CHILD=[]`(빈 값)으로 발화 → 재사용된 PID 로 시그널 미전파 확인.
- **네트워크 대기** — reachable 시 즉시(1s) return, 미도달 시 최대 120초 후 진행(무한 대기 없음).
- **starts 로그 epoch 형식 (인터페이스 0)** — 13회 기동 후 정확히 10줄, **모든 행이 순수 epoch 정수**(`date +%s`), 잔여 임시파일 0. (사람이 읽는 날짜 포맷 제거 — 워처 epoch 기대 충족.)
- **install `-x` 게이트** — notify 스크립트 존재+**실행권한** 확인으로 상향. (Windows/git-bash 는 shebang `.sh` 를 항상 실행가능으로 보고해 음성 케이스 재현 불가하나, `[ -x ]` 자체는 정상 동작 확인 — macOS 에서 권한 소실 시 정상 거부.)

### 맥미니에서의 설치 후 검증(권장 순서)

```bash
plutil -lint /Library/LaunchDaemons/com.antigravity.sisyphe-bot.plist            # 문법
launchctl print system/com.antigravity.sisyphe-bot | grep -E 'state|pid|program' # 로드 상태
for l in sisyphe-bot ra-sisyphe-bot research-notes-bot seonyuduo-exercise-bot; do
  echo "== $l =="; launchctl print system/com.antigravity.$l 2>&1 | grep -E 'state =|pid =';
done
tail -f ~/Antigravity_Market_Dashboard/logs/launchd/sisyphe-bot.err              # 로그
```

## 알려진 차이점 (systemd → launchd)

1. **크래시 루프 상한(StartLimitBurst) 은 A4 crash_watcher 로 위임**
   systemd 는 `300초 내 10회 실패 → 재기동 중단`으로 크래시 루프를 억제했다. launchd 엔 횟수 기반
   give-up 이 없어 KeepAlive 봇은 무한 재기동한다. **실패 알림 자체는 wrapper 가 건별로 이미 발송**한다
   (아래 2). 반복 크래시의 *억제/에스컬레이션*(예: 무한 알림 방지·일시 정지)은 **A4 crash_watcher** 가
   `logs/launchd/starts/<봇>.log`(원자적 최근 10줄, 짧은 간격 = 루프)를 소비해 담당한다.
   → 즉 wrapper=건별 알림+지연, A4=루프 판정. 이 분업은 codex 리뷰 v1 지시에 따른 것.

2. **OnFailure = wrapper 건별 notify (구현됨, 단 stop 시그널 제외 — CONTRACT 인터페이스 0-1)**
   wrapper 가 봇을 child 로 띄우고 종료코드를 캡처한다. 종료코드가 `0/130(SIGINT)/143(SIGTERM)` 이 아니면
   **진짜 크래시**로 보아 `scripts/notify_sisyphe_failure.sh <봇이름>` 을 호출하고 `sleep 10` 후 동일 코드로 종료
   → launchd KeepAlive 재기동. **stop 시그널(130/143)을 제외한 것은 의도적**(codex 2차 승인, CONTRACT 0-1 명문화):
   launchd 의 bootout/deploy/재부팅은 SIGTERM 으로 봇을 멈추는데, 이를 실패로 알리면 매 배포마다 오알림이 발생한다.
   이는 systemd 가 `systemctl stop`(SIGTERM)을 clean stop 으로 처리해 OnFailure 를 발화하지 않는 것과 동일한 의미다.
   (드문 SIGSEGV=139 등 crash-signal 은 stop 집합에 없으므로 알림 대상으로 남는다.)

3. **RestartSec — wrapper sleep 10 로 보완(모든 재기동 경로)**
   launchd `ThrottleInterval=10` 은 *직전 시작 시각* 기준 최소 재기동 간격이라, 봇이 10초 넘게 돌다 죽으면
   **즉시** 재시작돼 systemd `RestartSec=10`(죽은 뒤 항상 10초 대기)과 다르다. systemd `Restart=always` 는 **정상 종료
   재시작에도 RestartSec 을 적용**하므로, wrapper 는 **rc=0(정상)과 크래시 종료 둘 다**에서 종료 직전 `sleep 10` 을 넣어
   "죽은 뒤 10초"를 보장한다. stop 시그널(130/143)은 재기동이 아닌 정지이므로 지연을 넣지 않아 bootout 을 지체시키지
   않는다. ThrottleInterval 은 초단타 크래시의 바닥 간격으로 함께 둔다.

4. **`After=network.target` = wrapper 네트워크 대기로 보완**
   부팅 직후 네트워크 미준비 상태의 초기 실패 루프를 줄이려 wrapper 가 시작 시 `api.telegram.org:443` 도달까지
   최대 120초(5초 간격) 폴링한다. 도달 못 해도 진행하여 봇 자체 재시도에 맡긴다(무한 대기 없음).

5. **시스템 TZ 의존**
   원본은 유닛에 TZ 를 명시하지 않고 시스템 TZ(Asia/Seoul)에 의존했다. plist 도 per-unit TZ 를 두지 않고
   **맥미니 시스템 TZ=Asia/Seoul(결정 10)** 에 의존한다. 봇 내부 KST 스케줄이 맞으려면 시스템 TZ 설정이 선행돼야 한다.

6. **시스템 python → venv python**
   원본 `/usr/bin/python3` → 맥에선 `__REPO__/venv/bin/python3`(pyenv 3.10.12 기반 venv, 결정 5).
   venv·.env·봇 스크립트·wrapper·notify 스크립트가 없으면 `install_bots.sh` 가 **설치를 중단**한다(exit 1).

## 설치 / 롤백 (맥미니에서)

```bash
# 설치 (sudo 필수). 사용자명 미지정 시 $SUDO_USER 추정. 사용자명은 ^[a-z_][a-z0-9_-]*$ 로 엄격 검증.
cd ~/Antigravity_Market_Dashboard/launchd/bots
sudo ./install_bots.sh              # 또는: sudo ./install_bots.sh <macmini_user>

# 롤백 (개별)
sudo launchctl bootout system/com.antigravity.sisyphe-bot
sudo rm /Library/LaunchDaemons/com.antigravity.sisyphe-bot.plist
```

`install_bots.sh` 는 sed 치환 **전에** 사용자명 형식을 검증하고, wrapper·venv python3·`.env`·notify 스크립트·
봇 스크립트 4개·원본 plist 4개의 존재를 **사전 게이트**로 확인한다. 하나라도 없으면 broken daemon 을 설치하지 않고
`exit 1` 한다.

## 배포 레이아웃 전제 (판단 지점)

plist 는 wrapper 를 `__REPO__/launchd/bots/run_bot.sh` 로 참조하고, wrapper 는 자기 경로에서 두 단계
상위를 `__REPO__` 로 자가 탐색한다. 즉 **이 `launchd/` 트리가 맥미니의 repo 아래(`__REPO__/launchd/`)에
배포**된다고 전제한다(모든 참조 대상 — `.env`, `logs/`, `scripts/notify_*` — 이 `__REPO__` 하위라 자연스러움).
repo 밖 다른 위치로 배포하려면 plist 의 wrapper 경로만 조정하면 된다. (rsync/부트스트랩 = Fable 담당)

## A4 crash_watcher 인터페이스 (제공)

- **starts 로그 (CONTRACT 인터페이스 0)**: wrapper 가 매 기동 시 `logs/launchd/starts/<봇>.log` 에
  **epoch 정수(`date +%s`) 한 줄**을 원자적으로 기록(mktemp+mv, 최근 10줄 유지). 짧은 간격의 다수 항목 = 크래시 루프
  신호. A4 는 이 파일을 **읽기만** 하며 epoch 정수가 아닌 행은 무시한다(강제 숫자화 금지). ★사람이 읽는 날짜
  포맷 금지 — 워처가 epoch 를 기대한다.
- **봇 이름 집합**: `sisyphe-bot`, `ra-sisyphe-bot`, `research-notes-bot`, `seonyuduo-exercise-bot`
  (= notify 스크립트 첫 인자, = starts 로그 파일명 stem).
