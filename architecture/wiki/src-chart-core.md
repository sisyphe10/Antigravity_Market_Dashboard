---
id: "src-chart-core"
name: "AoE 차트 코어 (chart_core/aoe_chart.js)"
domain: "ops-infra"
project: "antigravity"
type: "pipeline_source"
runs_on: "vm_macmini"
schedule_kst: "빌드타임 인라인 임베드 (상시)"
status: "active"
code:
  - "chart_core/dist/aoe_chart.js"
  - "chart_core/build_core.py"
  - "execution/legacy_chart_renderers.py"
reads: []
writes: []
depends_on: []
alerts: ""
---

# AoE 차트 코어 (chart_core/aoe_chart.js)

**Domain:** 운영 · 인프라 · **Type:** Source · **Runs on:** vm_macmini · **Schedule (KST):** 빌드타임 인라인 임베드 (상시) · **Status:** active · **Project:** antigravity

AoE 전 차트의 렌더링 양식 유일 정본 (2026-08-02 착수). "양식 하나만 고치면 모든 차트가 따라오게" — DATA 탭(cmb) 규격을 코어로 추출해 market/wrap/뷰어에 공유한다. `nav_style.py`가 네비·색의 정본이라면, 이 코어는 차트·서브패널·범례·축의 정본이다.

- **경계**: 코어 = 렌더 프레임·축/단위/환산·범례(하단 인라인 단위 + 기간 변화율 %p)·끝값·크로스헤어/핀/툴팁 동기·내비·Download/Copy·서브패널 프레임(이격도·RoC²)·y2 우측축·log-pad·테마 토큰. / 페이지 = 데이터·도메인 계산(MA·이격도·RoC²)·사이드바·pw게이트 트리거만 잔류.
- **배포 = 빌드타임 인라인 임베드**: create_dashboard 가 `_load_aoe_core_js()` 로 `dist/aoe_chart.js` 를 읽어 `<script>` 로 인라인. 모듈 로드 시 즉시 실행돼 코어 부재·sha 불일치는 **기동 즉시 치명 실패**(부분 페이지 게시 차단 — P1a 사고 재발 방지).
- **무결성**: `dist/aoe_chart.manifest.json`(coreVersion·coreSha256·chartJsVersion) 대조. 코어만 고치고 `build_core.py` 를 안 돌리면 sha 불일치로 생성 거부.
- **Chart.js 버전 코어 번들 고정 = 4.5.1** (구 wrap.html 은 CDN latest 미고정 드리프트였음 → 코어로 해소).
- **legacy 롤백 주 경로**: `AOE_CHART_LEGACY=1 python execution/create_dashboard.py` = 코어 이관 직전 동결 렌더러(`execution/legacy_chart_renderers.py`, 소스 verbatim 추출)로 **현재 데이터**를 재생성. git revert 는 인라인 데이터까지 과거로 돌리므로 금지. P7(legacy 제거)에서 삭제 예정.
- **회귀 하네스**: `chart_core/harness/run_snapshots.py`(playwright) + `golden/*.json` — 축·눈금·데이터 체크섬·범례·툴팁·파일명 + 핀/크로스헤어 인터랙션 스냅샷. fixtures 는 불변(갱신 시 golden 재생성). "승인되지 않은 변화 0" 원칙.
- **뷰어 소스 스냅샷**: `chart_core/viewer_src/` = 맥미니 `/charts/` 뷰어 빌더·템플릿 편입본. **실행 정본은 맥미니**, repo 사본은 기록용 — 뷰어 수정 시 맥미니 먼저 → 스냅샷 갱신(이중 수정 금지).
- **전환 단계**: P0(기준선 동결·하네스) → P1(코어 추출) → P2(DATA 3면) → P3(INDICES·hotels ADR) → P4(뷰어·etf·건설) → P5(WRAP·y2축) **완료(8/2)**. P6(AUM stacked·kofia mini·FCF) · P7(legacy 제거 + 표 토큰 전면화) 잔여.
- ★수정 규칙: 차트 렌더 규격 변경은 반드시 이 코어에서만. 코어 편집 후 `python3 chart_core/build_core.py` 로 manifest sha 재생성 필수.

## Reads
- (none)

## Writes
- (none)

## Depends on
- (none)

## Code
- `chart_core/dist/aoe_chart.js`
- `chart_core/build_core.py`
- `execution/legacy_chart_renderers.py`
