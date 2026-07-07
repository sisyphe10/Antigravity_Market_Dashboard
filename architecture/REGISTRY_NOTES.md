# REGISTRY_NOTES — 수집 근거·불확실 항목·정리 후보

`architecture/registry.json`(v1, 2026-07-07)의 부속 문서. 컴포넌트 **113개**의 수집 근거, 불확실하게 남긴 항목, 그리고 전수 조사 중 발견한 정리 후보(신규만)를 기록한다.

---

## 1. 수집 방법·기준

- **기준 트리 = `origin/main`** (HEAD `0250792f`). 로컬 워킹트리는 origin보다 **수십 커밋 뒤처져 있어**(`e33ce836` dead-code 정리 이전 상태 + launchd 트리·Taiwan/Japan 파이프라인 미반영), 모든 판정을 `git show/ls-tree/grep origin/main`로 수행했다. 로컬 파일 목록만 보면 이미 삭제된 파일이 살아 있는 것처럼 보이므로 신뢰하지 않았다.
- **소스**: `.github/workflows/*`(17개 파일), `scripts/*.service|*.timer|*.sh`, `launchd/`(bots·timers·gha·system 전체), `execution/` 모듈 전수, 루트 `*.html`, `sources.json`, `execution/config.py`, `.claude/rules/*`, 봇 스케줄은 `sisyphe_bot.py`/`ra_sisyphe_bot.py`의 `run_daily` 정의 실측.
- **교차검증**: `C:\Users\user\macmini_migration\INVENTORY_LIVE.md`(2026-07-06 VM 실측 — 실행 중 봇 4·타이머 enabled 상태·crontab·.env 키·외부 도메인)와 대조. hotel-adr.timer가 VM에서 `disabled`인 것 확인.
- **스케줄(KST)**: GHA cron은 UTC → +9h 환산(요일 이동 반영, 예 gha-fred 화~토). systemd `OnCalendar=... Asia/Seoul`은 그대로. 봇 내부 잡은 코드의 `datetime.time(hour=..., tzinfo=kst)` 실측.
- **참조 무결성**: 동봉 셀프체크(scratchpad `selfcheck.py`) — id 유일성 113/113, `depends_on` 전건이 실재 컴포넌트 id, `reads/writes`의 id형 토큰 전건 실재. **문제 0건**. (파일 경로형 reads/writes는 자유 문자열로 허용.)

### 컴포넌트 수(타입별)
bot 4 · timer 10 · gha_workflow 15 · page 12 · pipeline_source 40 · dataset 9 · store 7 · infra 7 · external 6 · watcher 3 = **113**.
status: active 102 · planned 7 · frozen 2 · retired 2.

> **예상(60~90)을 초과한 이유**: 과제 스펙 작성 시점 이후 origin에 (1) 맥미니 이전 `launchd/` 레이어(bots·timers·gha 9종 초안·system 데몬 4), (2) Taiwan 월매출 + Japan capex 파이프라인, (3) heartbeats 워치독이 추가됐다. 이들을 반영하니 113이 됐다. 인위적으로 줄이기보다 전수를 유지했다.

---

## 2. 설계 판단 (중복·경계 처리)

- **VM(systemd) ↔ 맥미니(launchd) 동일 논리 컴포넌트는 1건으로.** 봇 4·타이머 8은 각각 한 카드에 두 런타임 파일(`scripts/*.service` + `launchd/*/*.plist`)을 함께 담고 `runs_on: vm_macmini`로 표기(현재 VM, 이전 후 맥미니). GHA plist 9종은 기존 gha_workflow 카드와 중복이라 개별 카드로 만들지 않고 `launchd-gha-phase2` 1건 + 각 GHA 카드 desc의 Phase 2 언급으로 처리.
- **system 데몬 4종은 신규 컴포넌트**: `daemon-git-pull`(현재 VM `*/5` cron으로 라이브=active), `daemon-catchup`·`daemon-crash-watcher`·`daemon-daily-selfcheck`(맥미니 전용, 초안·검증 완료 → status planned).
- **market_crawler는 마스터 1건**: DRAM/NAND·원자재·크립토·FX·지수·리튬(SMM)·폴리실리콘·해상운임을 이 카드에 접고, 별도 모듈이 있는 SMP(`src-smp-kpx`)·SiliconData(`src-silicondata`)만 서브 카드로 분리(각자 전용 데이터·메모리 존재). 리튬은 전용 fetcher가 없어 크롤러에 접었다.
- **stores는 큐레이션**: dataset.csv·Wrap_NAV.xlsx·portfolio/contribution/fee/landing/taiwan json·etf/earnings/research DB·orders/·sources_state/·heartbeats(planned)만 카드화. 그 외 다수 산출 json은 `reads/writes`에 파일 경로로만 기재(카드 폭증 방지).
- **봇 내부 헬퍼는 봇 카드에 흡수**: `daily_alert.py`(날씨)·`daily_calendar.py`·`daily_portfolio_report.py`·`fetch_wics_mapping.py`·`update_price_history.py`·`fetch_featured_news.py`는 sisyphe_bot이 subprocess로 호출하는 내부 잡이라 `bot-sisyphe` desc에 흡수(개별 pipeline_source 카드 미생성). 근거는 §4의 검증 결과.

---

## 3. 불확실·플래그 항목 (status/desc에 표기함)

| 항목 | 불확실성 | 처리 |
|---|---|---|
| `launchd-gha-phase2` (GHA 9종 맥미니 초안) | **draft** — plist XML·스케줄·bash 문법만 검증, 실기(맥미니) 미검증. Timeout 값은 원본 yml에 없어 임의 보수 추정. | status `planned`, desc에 draft 명시 |
| `daemon-catchup`/`crash-watcher`/`daily-selfcheck` | 맥미니 전용, 아직 어디서도 라이브 아님(VM 대응 잡 없음/부분). daily-selfcheck는 2026-07-06 신규 커밋. | status `planned` |
| `store-heartbeats` | Phase 2 wrapper가 채우는 파일. 현재 정착 여부 불명(초기 커밋만 관찰, GHA wrapper는 맥미니용). | status `planned` |
| `gha-earnings-calendar-sync` alerts | repo 밖(Google Calendar) 산출이라 실패 알림 경로 없음. VM cron 15:00 + GHA 07:00 **이중 실행**. | desc·alerts에 명시(§5 정리후보 1번과 연결) |
| `src-investor-trading` 스케줄 | sisyphe_bot 내 subprocess(line ~1022) 호출은 확인했으나 정확한 발화 시각 미확정("장 마감 후"로 표기). | schedule_kst 근사 |
| `src-japan-capex` | 비교적 신규(SEAJ/JMTBA). 전용 타이머 없이 kodex 23:30 편승은 코드 주석으로 확인, 별도 스케줄 문서 부재. | desc에 ★신규·편승 명시 |
| `page-hotels` / `hotel_adr.csv` | 데이터 동결(수집 은퇴). 페이지·CSV는 잔존. | status `frozen` |
| `bot-research-notes` `research_headlines.json` write | 봇이 헤드라인을 쌓아 RA_Sisyphe 05:10이 읽는 관계는 rules 문서 기반 추정(코드 라인 미대조). | 영향 경미, 그대로 둠 |

---

## 4. 검증했으나 dead 아님으로 판명 (오탐 방지 기록)

전수 조사 중 "소비자 없어 보이는" 후보를 origin/main에서 **정확한 import/subprocess 패턴으로 재확인**한 결과, 아래는 모두 **라이브**였다 → 정리 후보에서 제외:

- `execution/daily_alert.py`(날씨) — `sisyphe_bot.py:183 from daily_alert import ...` + 05:00 subprocess.
- `execution/daily_calendar.py` — `sisyphe_bot.py:208 from daily_calendar import ...` + 05:10 subprocess.
- `execution/daily_portfolio_report.py` — `sisyphe_bot.py:250/792` subprocess + `wrap_config.py` 매핑 touchpoint.
- `execution/fetch_wics_mapping.py` — `sisyphe_bot.py:955` subprocess.
- `execution/update_price_history.py` — `sisyphe_bot.py:965` subprocess.
- `execution/fetch_featured_news.py` — `sisyphe_bot.py:1010` subprocess, `create_dashboard.py:8634` 소비, `check_data_freshness` 감시.
- 루트 `push_wrap_nav.py`·`add_universe_ticker.py` — 수동 CLI(코드 참조 0은 정상). `local_safe_push.py`가 "manual push button"으로 문서화.
- **execution/*.py 전수 orphan 스캔 결과 무참조 모듈 0건.**

> 교훈: `.disabled` 워크플로가 가리키는 모듈(daily_calendar/daily_alert/daily_portfolio_report)이 dead처럼 보이나, 실제 로직은 봇 내부 잡으로 살아 있다. 워크플로만 은퇴했을 뿐 모듈은 현역.

---

## 5. 정리 후보 (★신규 발견만 — 삭제는 리드→사용자 승인 경로, 여기선 기록만)

> 2026-07-07 오전 `e33ce836`로 이미 정리된 13개 파일(hotel 세트·`fetch_kna_news.py`·`fetch_featured_data.py`·`compare_featured.py`·`_send_semianalysis_once.py`·`build_full_mapping.py`·`build_sector_mapping.py`·`fetch_us_sector_mapping.py`·`test_cumulative_return.py`·`test_futures.html` 등)은 **제외**했다. (팀리드가 언급한 `audits/deadcode_repo.md`는 origin/main·로컬 어디에도 없어 참조 못 함 → 대신 `e33ce836` 커밋의 삭제 파일 목록을 already-cleaned 집합으로 사용. **이 audit 문서 경로 부재 자체를 확인 필요 항목으로 남김.**)

신규 발견은 **dead code가 아니라 대부분 문서·상태 드리프트/중복**이다. 코드 orphan은 §4대로 0건.

| # | 항목 | 유형 | 근거 (grep/관찰) | 확신도 |
|---|---|---|---|---|
| 1 | `earnings_calendar_sync` **이중 실행** (VM cron 15:00 + GHA 07:00) | 중복 실행 | `INVENTORY_LIVE.md` crontab `0 6 * * *`(=15:00 KST) + `earnings_calendar_sync.yml` cron `0 22`(=07:00 KST). launchd/gha README도 "결정 11: 맥미니 단일화 필요"로 명시. 캘린더 중복 기록 우려. | **높음** |
| 2 | `.claude/rules/vm-deploy.md` "봇 구성 (**3개**)" 표 | 문서 드리프트 | 실제 라이브 봇 **4개**(seonyuduo-exercise-bot 누락). `INVENTORY_LIVE.md` §1에 4개 running 확인. 표만 3행. → 문서 갱신 대상(삭제 아님). | **높음** |
| 3 | `.claude/rules/dashboard.md` 페이지 목록 | 문서 드리프트 | `taiwan.html`·`universe_lab.html` 미기재(origin에 실재 + create_dashboard PAGES 등록). 페이지 의존체인 표도 미반영. → 문서 갱신. | 중간 |
| 4 | `architecture.html` 수동 관리 드리프트 | 문서/코드 | dashboard.md 스스로 경고: create_dashboard 탭바 헬퍼 수정 시 수동 동기화 필요. 이 레지스트리 기반 위키로 대체되면 해소 → **architecture.html 은퇴 후보**(위키 이관 완료 시). | 중간 |
| 5 | GHA `run_backfill.yml` + `run_merge_ddr5.yml` | 휴면 워크플로 | 정기 스케줄 없음, 자기 파일/스크립트 push에만 반응하는 초기 셋업/일회성 도구. `merge_ddr5_data.py`는 이 워크플로 외 참조 0. → 아카이브/삭제 후보(롤백 위험 낮음). registry에 `gha-dormant-push`(frozen)로 격리. | 중간 |
| 6 | 로컬 워킹트리 stale (origin 대비 수십 커밋 뒤) | 상태/위생 | `git merge-base --is-ancestor HEAD origin/main` = 로컬이 뒤처짐. `e33ce836`가 origin에서 지운 13파일이 **로컬엔 잔존**(fetch_hotel_adr.py 등). 이미 정리된 집합이라 repo 후보는 아니나, **로컬 pull 필요**(편집·검증 시 stale 파일 오인 위험). | 중간 |
| 7 | 루트 백업 xlsx 다수 (`Wrap_NAV.xlsx.bak-*`, `*.local_backup*` 등 6개) | 잔재 파일 | 로컬 워킹트리에 수동 백업 6개 잔존. origin 추적 여부는 미확정(대부분 로컬 전용으로 보임). 정리 시 최신 1~2개만 남기고 삭제 검토. | 낮음 |

**정리 후보 없음이 확인된 영역**: `execution/*.py`(orphan 0), 루트 수동 CLI(add_aum/add_fee_revenue/add_universe_ticker/push_wrap_nav — 정상 무참조), `.disabled` 워크플로가 가리키는 봇 헬퍼 모듈(§4).

---

## 6. 렌더러 팀 참고

- 스키마 계약 준수(meta + components[], 14 필드). `reads`/`writes`는 컴포넌트 id 또는 파일 경로 혼용(id형 토큰만 무결성 검증됨).
- `depends_on`은 항상 컴포넌트 id → 그래프 엣지로 안전하게 사용 가능.
- status 색상 권장: active=정상, planned=점선/회색(맥미니 미이전), frozen=흐림(동결), retired=취소선.
- `runs_on` 스윔레인: vm_macmini 46 · github 25 · gha 32 · laptop 2 · external 8.
- 대용량 페이지(`etf.html` 18MB, `featured.html` 11MB)는 링크만(임베드 금지).
