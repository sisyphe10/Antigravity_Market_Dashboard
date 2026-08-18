# P0 기준선 동결 — AoE 차트 시스템 (2026-08-02)

설계 정본: 맥미니 `~/work/analysis/260802_chart_core/DECISION_draft.md`

## Chart.js 버전 매트릭스 (동결 시점 실측)

| 소비자 | 로드 방식 | 버전 | 비고 |
|---|---|---|---|
| market.html (idx·cmb·kofia·AUM) | `/assets/vendor/js/chart.umd.min.js` | **4.5.1** | vendored — 8/2 repo 편입 전까지 git 미추적이었음 |
| wrap.html (WRAP) | `https://cdn.jsdelivr.net/npm/chart.js` | **미고정(latest)** | ★버전 드리프트 리스크 — 코어 번들로 해소 예정 |
| /charts/ 뷰어 5종 | `chart.js@4.4.1` CDN | 4.4.1 | 템플릿 고정 |
| featured/hotels | vendored 4.5.1 | 4.5.1 | |

**P1 결정 예정**: 코어 번들 버전 = 4.5.1 기준(최다 소비자 현행).

## 차트 인스턴스 기능표 (create_dashboard.py 13 + 뷰어)

| # | 차트 | 위치 | 유형 | Log | 정규화 | 핀 | 끝값 | 크로스헤어 | 내비 | DL/Copy | 서브패널 | 전환 단계 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | cmb (DATA) | market L3846 | line ±y1 | ●(음수 폴백) | ● | ● | ● | ●(3면 동기) | ● | ●/● | 이격도·RoC² | P2 (정본) |
| 2 | cmbDispChart | market L3948 | line 패널 | - | - | - | ● | ●동기 | 종속 | 합성 | - | P2 |
| 3 | cmbRocChart | market L4026 | line 패널 | - | - | - | ● | ●동기 | 종속 | 합성 | (%p) 상단 주석 잔존 | P2 |
| 4 | idx (INDICES) | market L1630 | line | ● | ●(자동) | - | ● | ● | 부분 | ●/● | - | P3 |
| 5 | wrap (WRAP) | wrap L4766 | line | - | 상시 pct | - | ● | - | - | - | pw게이트 치유 | P5 |
| 6 | (L5115 미분류) | market | — P1 때 실사 | | | | | | | | | P3 |
| 7 | aumStacked | market L5305 | bar+line | - | - | - | - | - | - | - | - | P6 |
| 8 | cumulativeAum | market L5671 | line | - | - | - | - | - | - | - | - | P6 |
| 9-10 | kofia 2종 | market L8308/8316 | mini line | - | - | - | - | - | - | - | - | P6 |
| 11 | topChart | featured L11136 | line | - | - | - | - | - | - | - | - | P3 |
| 12 | hotelAdr | hotels L11706 | line | - | - | - | - | - | - | - | - | P3 |
| 13 | 뷰어 5종 | chart_template | line ±pct축 | ● | ● | ● | ● | ● | ● | ●/- | isAux 보조선 | P4 |
| 14 | FCF | 자체 구현 | line | - | - | - | - | - | - | - | - | P4 후반 |

범례·단위: cmb·뷰어 = 하단 범례 인라인 단위(8/2 확정 규격). 기타 차트는 미적용 상태로 동결.

## 알려진 기준선 결함 (전환 시 해소 — "의도된 차이" 허용 목록 후보)
1. ~~wrap Chart.js 미고정 CDN (→ 코어 번들)~~ **해소 (2026-08-02 P5 — 4.5.1 고정+코어 인라인)**
2. RoC² 패널 `(%p)` 상단 주석 잔존 (메인 차트는 범례 인라인으로 이행 완료)
3. ~~endLabel·crosshair 플러그인 사본 2벌(idx/cmb) — 미세 동작 차이 가능.~~ **해소 (P2a·P2b cmb / P3 idx — 2026-08-02). 잔존 사본은 wrap 1벌뿐(P5 대상)**
4. 뷰어 소스가 맥미니 단독(미추적)이었음 → 8/2 `chart_core/viewer_src/` 스냅샷 편입(승인). **P4까지 맥미니가 실행 정본, repo 사본은 기록용** — 이중 수정 금지, 뷰어 수정 시 맥미니 먼저→스냅샷 갱신.
5. ~~cmb 원값 모드에서 %단위 시리즈의 범례 기간 변화율이 나눗셈 %로 계산됨 — 괴리율 0.045→-5.33이 `-1,699%`로 표기(golden `data_basis_neg_linear` 참조). 2026-07-19 확정 규격(%·%p 시리즈=레벨 차이 %p)은 pct 모드에만 적용돼 있음 → P2에서 규격 정합.~~ **해소 (2026-08-02 P2b, dc11309e — raw 모드도 레벨 차이 %p, MA 파생선은 같은 축 주 시리즈 단위 상속)**

## P6·P7 완료 — 프로젝트 종결 상태 (2026-08-02 밤)
- **P6**: 코어 프리셋 `stackedBar`(스택 축·합계 라벨 cmbStackTotalPlugin·축단위 주석·끝값/핀 없음)·`mini`(11px·크로스헤어만) + `ids.legend: null`(범례 없음). wrap AUM·누적 AUM(스택 막대), research 주별 막대, etf 실적 mixed(매출 라인+이익 막대+0선 aux) 전환. kofia 미니 2종=미호출 데드 코드 확인(랜딩 폐지 잔재) → 삭제.
- **P7**: legacy 일체 은퇴(플래그·동결 렌더러·코어 심·픽스처·시나리오 — 롤백=git revert), **정적 금지 검사 상시화**(build_core.py: create_dashboard의 `new Chart(` 허용 2건 초과 시 실패 — seibro 가로바·미국 ETF), 데드 코드 삭제(targetTransform·landing kofia), **표 토큰 aoe_tokens.css**(비색상 규격 — 글씨·패딩·정렬·tabular-nums·선 두께, manifest sha 검증) 신설+표 페이지 3종(bop·pipeline·calendar) 적용(렌더 보존, tabular-nums만 신규).
- **codex 리뷰 2차(P4~P5) 반영**: 범례 단위=정규화 좌축만 생략(우축 원값 계열 단위 유지)·끝값 폭 측정 pct 분기 좌축 한정·wrap 주축=실제 앵커 페어 지표(전역 지표 순서 아님 — 라이브 재현 검증).
- 잔여 백로그: ①벤치마크만×비중/AUM 선택=빈 차트(legacy 동작 보존 — 빈 상태 안내는 UX 개선 항목) ②하네스 공백: WRAP/FCF/y2 축 축소 재사용·Download PNG 픽셀·페인터 출력·토글 복귀 ③wrap 표·기타 페이지 표의 토큰 적용 확대 ④construction_val/wrapper 구 3사 페이지(con_*.html) 정리 여부 실사.

## P5 이후 상태 (2026-08-02)
- **WRAP CHART 전환 완료** — 마지막 endLabel·렌더 사본 제거. 코어에 **y2 축**(두 번째 우축, y2 데이터셋 존재 시만 활성 — 밴드·환산·조/억 승격·로그패드·범례 단위·툴팁 전부 축별 확장).
- wrap 지표→축 배정: 앵커 지표 그룹=주축(y), 이후 y1·y2 순 (수익률·MDD=같은 %축, 구 '좌측 승격' 일반화 — 비중·AUM 단독 선택 시 그 지표가 좌축). stepped 비중·지표별 명도 변형은 페이지 데이터셋 속성으로 유지.
- Chart.js 미고정 CDN → 4.5.1 고정+코어 인라인(결함 1 해소). Download/Copy=코어 헬퍼. 범례가 인라인 단위+기간 변화(+197%p 식)를 새로 얻음. pw게이트 힐 타이머·_wrapHealKick 유지.
- 검증: 로컬(게이트 우회) 3축 콤보·비중 단독 좌축·콘솔 0 → gh-pages 라이브에서 동일 확인. 렌더러 사본 잔존 0 — 남은 단계는 P6(AUM stacked·kofia mini·research 막대 프리셋)·P7(legacy 제거+표 토큰+하네스 백로그).

## codex 리뷰 반영 (2026-08-02, P2b~P3 커밋 4개 대상)
- 조치 완료: ①DATA 섹션이 자립하도록 코어 임베드+Chart.js 가드 로더를 js_code 앞에 배치(단, `<script src>` 중복이면 **Chart 클래스가 재정의돼 레지스트리가 갈라짐** — `window.Chart || document.write(...)` 조건부 로드 필수) ②legacy 롤백 시 크로스헤어·핀 불능 → 코어에 legacy 호환 심(`cmbFamilyOf`: `_cmbPeerAccessor` 등록 페이지에 전역 패밀리 배선, P7에서 legacy와 함께 제거) ③legacy 눈금 밴드 계약 → `cmbTickFmt`에 window 폴백 ④서브패널 신규 생성 시 잔여 호버 1회 재도장 ⑤legacy 픽스처(`market_legacy_baseline.html`)+시나리오 2종 상시화 → 총 15 시나리오.
- 하네스 잔여 공백(P7 백로그): Download PNG 픽셀·합성 검증 없음(파일명만)·핀/크로스헤어 캔버스 페인팅 미검증(상태만)·USD→Local 복귀·빈 선택·호텔 3일 미만 분기 미커버.

## P4 이후 상태 (2026-08-02)
- **뷰어 정식 전환 3종**: chart_viewer2(현선물·수급·ETF)·chart_viewer_etf(레버리지ETF AUM, 실적 섹션 자체 차트는 P6 mixed 대상)·chart_viewer_construction(건설 13사, 평균 점선=`_cmbAux` 보조선 규격) — 셸 템플릿 `chart_template_core.html` + `chart_common.core_template()`(코어 sha 검증+센티널 치환). Chart.js CDN 4.4.1→4.5.1 고정.
- 코어 P4 일반화: pct 분기=좌축 한정·y1 축=데이터셋 존재 기준·`_cmbPinSuppress`(드래그 팬 잔여 click 억제)·`_cmbAux`(범례·툴팁·핀 제외 보조선)·**로그축 경계=유효숫자 3자리 니스 라운딩**(min 내림·max 올림, 사용자 확정 8/2).
- 전환 제외·연기: research(주별 **막대** → P6 프리셋)·FCF(자체 구현+추정 구간 표기 → P4b)·bop/pipeline/calendar(표 페이지 — 표 토큰 P7)·chart_viewer.html(구 viewer1, 상시 페이지 메모리 '삭제 금지' — 현상 유지, P7 재검토).
- 하네스: viewer2 fixture=코어 기반으로 교체, 추출기=표준(_extract_std) 통일. 총 13 시나리오.
- 뷰어 인프라 계약: 실행·서빙 루트=`~/work/charts/260715_현선물공매도`(Caddy /charts/*), 빌드=repo venv python3, 산출 html은 쓰는 즉시 라이브(별도 게시 없음).

## P3 이후 상태 (2026-08-02)
- **코어 다중 인스턴스화**: 크로스헤어·핀·피어(`chart._cmbFamily`)와 축 밴드·환산·단위(`chart._cmbAxisBandRef` 등)를 window 전역에서 차트 인스턴스로 이전 — 한 페이지에 여러 표준 라인 패밀리(cmb+idx)가 공존해도 상태가 새지 않는다. `window._cmbPeerAccessor` 폐기(코어가 패밀리 자체 배선). DATA 회귀 = 하네스 diff 0 검증.
- `cmbRenderCharts(view)` 파라미터 추가: `ids`(캔버스·범례·패널 id, 패널 null=건너뜀)·`xLabel`·`logOn`·`legendSuffix` — 기본값은 전부 cmb.
- **INDICES(idx) 전환 완료**: 페이지는 데이터 준비(정규화·USD 모드)만, 렌더=코어 `mode:'pct'`. idx 전용 crosshair/endLabel/포맷터/범례 사본 삭제. 표준 획득: 끝값 공통열+리더선·핀 카드·범례 기간 변화율·`/ USD` 접미. 하네스 `idx_default`·`idx_usd`(+패밀리 격리 검증).
- **hotels ADR 전환 완료**: 표준 라인(raw1)+코어 임베드+Copy/Download+표준 범례(`/ 천원` 접미)·Log 축. 하네스 `hotel_adr`+fixture `hotels_baseline.html`.
- **기능표 정정(실사)**: #11 `topChart`는 featured가 아니라 **seibro의 가로 바 차트**(비시간축 랭킹) — 코어 모델 밖이라 **제외**(featured 페이지에는 차트 없음). #6 L5115 미분류 = `_build_target_transform_chart_section`(NH 목표전환형 1호) — **호출부 없는 데드 코드**, 이관 불요(정리는 P7).
- ※P3 롤백 = git revert (legacy 플래그는 DATA 전환 전용 동결본 — idx/hotels 구 렌더러는 미포함).

## P2b 이후 상태 (2026-08-02)
- cmb(DATA) 렌더 프레임 전체가 코어 `cmbRenderCharts(view)` 로 이관 — DATA 클로저에는 데이터·도메인 계산(MA·이격도·RoC²)·사이드바·RoC 진단 UI만 잔류, `new Chart(` 0건.
- 롤백 주 경로: `AOE_CHART_LEGACY=1 python execution/create_dashboard.py` = 코어 이관 직전 동결 렌더러(`execution/legacy_chart_renderers.py`)+현재 데이터 재생성 (P7에서 제거).
- golden 스냅샷은 P2b부터 git 추적 (그 전엔 `.gitignore` `*.json` 광역 규칙에 삼켜져 로컬 전용이었음).

## fixture (불변 — 갱신 시 golden 재생성 필수)
- `fixtures/market_baseline.html` — 2026-08-02 16:45 생성본 (오늘 확정 규격 전부 반영: 툴팁 원본날짜·범례 인라인 단위·음수 선형 폴백·Copy/파일명)
- `fixtures/chart_viewer2_baseline.html` — 동일 시점 뷰어

## 회귀 하네스
- `harness/run_snapshots.py` — playwright(chromium)로 fixture를 로컬 HTTP 서빙 후 시나리오 실행,
  차트 상태(축 min/max·ticks·datasets 값 해시·범례 텍스트·툴팁 제목·파일명)를 JSON 덤프
- golden: `harness/golden/*.json` — diff 0 = 통과. 의도 변경 시 golden 갱신+사유 커밋 메시지 기록
- 실행: `python chart_core/harness/run_snapshots.py [--update]`

## 백로그 진행 (2026-08-03)
- **③ 표 토큰 확대 — 대시보드·wrap 완료** (49d72ada·cfb52c15·4b1174d4): market/wrap 페이지에 aoe_tokens.css 임베드(tokensSha256 검증 로더 `_load_aoe_tokens_css`), `.portfolio-table` 2블록·`.rt-*`·cmb 사이드테이블(인라인 th_base/cell_base)을 var(--aoe-t-*) 배선. 페이지 고유 값은 컨테이너 셀렉터 변수 재정의로 외재화(렌더 보존 — ts.net 다크 computed 기준선 diff 0, tabular-nums만 신규·P7 전례). 다크 스킨의 크기 셀렉터 재단언(17px 등) 제거는 잔여 표(universe·seibro·featured 등) 토큰화 후 별도 단계.
- **② 하네스 일부**: 다운로드 파일명 날짜=비결정 필드 → DATE 마스킹 후 비교(골든 재생성, EOL도 LF 정규화). **playwright+chromium 을 맥미니 repo venv에 상주 설치** — 하네스 실행 환경이 정본 기기에 고정됨.
- ★재발 함정: market.html 재생성 후 커밋까지 6분 지연 → git_pull 5분 주기 `checkout -- *.html`에 되돌려짐(8/2 동일 사고). 재생성→어서션→커밋→게시를 **한 SSH 체인**으로 재적용해 회수.

## 표 토큰 2차 확대 + hotels 은퇴 (2026-08-03, 2056013a)
- 배선 추가: featured(전 표)·etf(메인+구성종목 서브표)·universe(전 표, 일반 문자열 CSS라 쓰기 지점에서 토큰 주입)·market 대만 패널(tw-table)·Monthly Returns(테이블 레벨만 — 셀 인라인은 전용 다크 커스텀 유지). 헤더 인셋 밑줄은 `inset 0 calc(-1 * var(--aoe-t-head-underline)) 0` 패턴.
- **hotels.html 은퇴**(사용자 지시 — 수집 은퇴·DATA 라인 제거에 이은 페이지 삭제): generate_hotels_html()+미호출 데드코드 _build_hotel_mini_summary() 삭제, 하네스 hotel_adr 시나리오·fixture·golden 제거(13→12 시나리오), 라이브 404 확인. hotel_adr.csv 데이터는 보존.
- 잔여 미배선 표: seibro(1)·market_alert(2)·architecture(1)·wrap 내 contrib-tbl/fee-table/iter-table/sector-table·건설 con_* 페이지(백로그④와 함께).

## 표 토큰 3차 (2026-08-03, 4186477d)
- seibro·market_alert(투자유의)·architecture(skill-table) 배선 완료. market_alert·architecture 생성기는 공용 로더 `execution/aoe_tokens_util.py`(sha 검증) 사용 — create_dashboard 자체 로더와의 통합은 후속 정리.
- 이제 남은 미배선 표 = wrap 내 contrib-tbl/fee-table/iter-table/sector-table + 건설 con_* 페이지(백로그④)뿐. 이후 다크 스킨 크기 재단언 제거 가능.

## 백로그④ 완료 — 건설 구 3사 페이지 정리 (2026-08-03)
- 실사 결과: con_soojoo·con_pbrper(iframe 서브차트)+val/wrapper 빌더 = 구세대. 링크 0·viewer-daily 미실행(construction 계열=분기 수동)·현행 build_construction.py(13사, 코어 표준)가 동일 출력 파일명을 직접 생성하며 대체. ★wrapper 빌더는 실행 시 현행 건설 탭을 덮어쓰는 위험물이었음.
- 조치: 4파일을 맥미니 `_retired_20260803/`로 이동(트리 git 미추적 → rm 대신 아카이브), repo viewer_src 스냅숏에서 구 빌더 2개 제거(git 복원 가능). 수주잔고 데이터·현행 페이지는 무관.

## 다크 스킨 표 크기 재단언 제거 (2026-08-03, 2e36ab49·08279f05) — 표 토큰 체계 완성
- 코어에 `--aoe-t-head-font`(헤더·보조 셀 슬롯, 기본 inherit) 신설(manifest 갱신). 다크 범위 전 표의 th·보조 셀(cmb Country/Group·arch sk-sum/sk-code·MR 헤더)을 이 슬롯으로 배선.
- 스킨의 `table,td{17px!important}`·`th{15px!important}` 셀렉터 재단언 → `table{--aoe-t-font:17px!important;--aoe-t-head-font:15px!important}` **변수 선언으로 교체**. 아키텍처 전용 15/13 타이포 절도 표 부분은 `.skill-table` 변수 재선언으로 전환. **표 크기에 대한 스킨 셀렉터 덮어쓰기 = 0.**
- 검증(다크 computed): market(cmb·tw·MR)·featured·etf·alert = 본문 17/헤더 15 유지, arch = 15/13(7/28 확정 규격) 유지. 의도된 변화 1건: cmb Country/Group 셀 17→15(블랭킷 룰이 뭉개던 보조 위계 복원).
- ★함정 기록: ①7/28 "타이포 2단 통일" 절이 arch 표를 15/13으로 재단언하고 있었음 — 전역 17/15 가정으로 접근하면 회귀로 오판(실제로는 확정 규격) ②같은 시각 다른 세션이 create_architecture를 다크 네이티브로 전환(5010b462)하며 8/3 오전의 토큰 배선을 걷어냄 — 동시 세션 작업 중 재배선 필요했음. 변수 선언에도 !important 필요(페이지 컨테이너 값보다 우선하기 위함).

## 범례 변화율 자릿수 통일 (2026-08-04)
- `cmbBuildLegend` 변화율 자릿수: 항목별 `|pct|` → **범례 전체 최대 `|pct|` 공유 기준** (`_legPctOf` 분리 + `_legMaxAbs`). 주 시리즈 +95.3% 옆 MA20이 +9.88%로 어긋나던 문제 — 축 눈금·끝값의 공유 기준 방식과 통일. 이격도·RoC 마지막 값 표기는 종전(항목별) 유지.

## 2026-08-06 — 휠 내비게이션 표준 개정 (전 뷰어 소급)
사용자 재개정: **일반 휠 = X축 확대·축소(끝=최신 날짜 고정, 위=확대 0.8 / 아래=축소 1.25)**, **Ctrl·Shift+휠 = 커서 지점 앵커 확대·축소**(기존 유지), **휠 팬(시간축 이동) 폐지 — 좌우 이동은 클릭 드래그 담당**. 차트 영역 밖 휠은 페이지 스크롤 유지(`{passive:false}` + 영역 판정 후 preventDefault).
- 적용 위치 = 뷰어 셸 템플릿 `chart_template_core.html`(실행 정본=맥미니 `~/work/charts/260715_현선물공매도/`, 본 `viewer_src/`는 기록 스냅샷). 레거시 `chart_template.html`도 동일 개정(현재 소비자 없음).
- 재생성 완료 5종: chart_viewer2 · chart_viewer_etf · chart_viewer_dsn · chart_viewer_construction · chart_viewer_research.
- **휠 핸들러 없음(무변경)**: create_dashboard.py 전 차트(cmb/DATA·INDICES·AUM·kofia·featured)·wrap.html — 휠 내비 자체가 미구현. bop·pipeline·calendar·fcf·boutique·nuclear·tennis 뷰어도 동일.
- **의도적 미변경**: `chart_core/fixtures/chart_viewer2_baseline.html`(불변 동결 fixture — 갱신 시 golden 재생성 필요), `~/work/analysis/260719_메모리3사_주가실적PER`(휠=커서 앵커 줌 구현으로 이미 신표준 취지 부합), `_retired_20260803/`·`.bak_*`.

## 축 단위 주석 잘림 fix + 15px 승급 (2026-08-19)
- wrap AUM(stackedBar)에서 Y축 (억원) 주석 상단이 잘림(사용자 지적). padTop 24가 주석 기준선을 캔버스 y=4에 놓아 13px 글씨 윗부분이 캔버스 밖이었다.
- 조치: ①stackedBar padding.top 24→34 ②cmbAxisUnitPlugin 기준선 하한 클램프(ty<14→14 — mini 등 얕은 프레임 안전망) ③주석 폰트 13→15px(축 눈금 15px와 통일 — 서브패널 (%p)·(조원) 주석 포함 전역 적용).
