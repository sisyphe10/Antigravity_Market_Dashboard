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
3. endLabel·crosshair 플러그인 사본 2벌(idx/cmb) — 미세 동작 차이 가능
4. 뷰어 소스가 맥미니 단독(미추적)이었음 → 8/2 `chart_core/viewer_src/` 스냅샷 편입(승인). **P4까지 맥미니가 실행 정본, repo 사본은 기록용** — 이중 수정 금지, 뷰어 수정 시 맥미니 먼저→스냅샷 갱신.

## fixture (불변 — 갱신 시 golden 재생성 필수)
- `fixtures/market_baseline.html` — 2026-08-02 16:45 생성본 (오늘 확정 규격 전부 반영: 툴팁 원본날짜·범례 인라인 단위·음수 선형 폴백·Copy/파일명)
- `fixtures/chart_viewer2_baseline.html` — 동일 시점 뷰어

## 회귀 하네스
- `harness/run_snapshots.py` — playwright(chromium)로 fixture를 로컬 HTTP 서빙 후 시나리오 실행,
  차트 상태(축 min/max·ticks·datasets 값 해시·범례 텍스트·툴팁 제목·파일명)를 JSON 덤프
- golden: `harness/golden/*.json` — diff 0 = 통과. 의도 변경 시 golden 갱신+사유 커밋 메시지 기록
- 실행: `python chart_core/harness/run_snapshots.py [--update]`
