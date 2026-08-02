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
1. wrap Chart.js 미고정 CDN (→ 코어 번들)
2. RoC² 패널 `(%p)` 상단 주석 잔존 (메인 차트는 범례 인라인으로 이행 완료)
3. ~~endLabel·crosshair 플러그인 사본 2벌(idx/cmb) — 미세 동작 차이 가능.~~ **해소 (P2a·P2b cmb / P3 idx — 2026-08-02). 잔존 사본은 wrap 1벌뿐(P5 대상)**
4. 뷰어 소스가 맥미니 단독(미추적)이었음 → 8/2 `chart_core/viewer_src/` 스냅샷 편입(승인). **P4까지 맥미니가 실행 정본, repo 사본은 기록용** — 이중 수정 금지, 뷰어 수정 시 맥미니 먼저→스냅샷 갱신.
5. ~~cmb 원값 모드에서 %단위 시리즈의 범례 기간 변화율이 나눗셈 %로 계산됨 — 괴리율 0.045→-5.33이 `-1,699%`로 표기(golden `data_basis_neg_linear` 참조). 2026-07-19 확정 규격(%·%p 시리즈=레벨 차이 %p)은 pct 모드에만 적용돼 있음 → P2에서 규격 정합.~~ **해소 (2026-08-02 P2b, dc11309e — raw 모드도 레벨 차이 %p, MA 파생선은 같은 축 주 시리즈 단위 상속)**

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
