# -*- coding: utf-8 -*-
"""chart-core P2b legacy renderer (2026-08-02 동결) — 롤백 주 경로.

AOE_CHART_LEGACY=1 로 create_dashboard 를 실행하면 이 동결본(코어 이관 직전의
DATA 탭 인라인 렌더러)으로 '현재 데이터'를 재생성한다 (git revert 는 인라인
데이터까지 과거로 돌아가므로 금지 — DECISION 8/2). P7(legacy 제거)에서 삭제.

이 파일은 create_dashboard.py 의 js_code 템플릿을 소스 레벨 verbatim 으로
추출한 것 — 수정 금지 (수정할 것이면 legacy 가 아니다).
"""

LEGACY_CMB_JS = """
        <script>
        (function() {
            var cmbData = CMB_DATA_PLACEHOLDER;
            var cmbSeriesUnit = CMB_UNIT_PLACEHOLDER;
            // RoC² 월말 백필 히스토리 — {시리즈: {d:[날짜…], v:[값…]}} (2026-07-30)
            var cmbRocHist = CMB_ROC_HIST_PLACEHOLDER;
            // RoC² 허용 시리즈 + 판독성 점수 {이름: [월런, 월AC1, 주런, 주AC1]}
            var cmbRocAllow = CMB_ROC_ALLOW_PLACEHOLDER;
            var cmbChart = null;
            var cmbAutoRangePending = false;
            var cmbClickOrder = [];
            var clickPalette = ['#000000','#0055cc','#cc0000','#006633','#6a0dad','#cc6600','#008080','#990066'];
            // ★KRX GOLD/ETS 거래대금은 dataset.csv 는 원 단위지만 파이썬 export 단계에서 이미
            //   억원으로 환산돼 넘어온다(412.7357 / 67.5571). 여기서 또 나누면 1억배로 축소된다.
            var seriesScale = { 'KOSPI Market Cap': 1e12, 'KOSDAQ Market Cap': 1e12,
                                '경상수지': 10, '외환보유액': 10 };   // 억달러 -> $B

            // MA 슬롯(0~3) 색상. 윈도우 값은 시리즈 빈도에 따라 동적 (MA_WINDOWS).
            var MA_DEFS = [
                { color: '#d32f2f' },
                { color: '#f57c00' },
                { color: '#1b5e20' },
                { color: '#1565c0' }
            ];
            // 빈도별 MA 윈도우 (직전 N개 실측치 기준): 일별=거래일, 월별=개월, 분기=분기
            var MA_WINDOWS = { D: [20, 60, 120, 200], M: [3, 6, 12, 24], Q: [4, 8, 12, null] };
            // MA/이격도 토글 상태 — 슬롯 인덱스(0~3) 기준 (윈도우 값이 빈도마다 달라지므로).
            // 시리즈 전환·기간 변경에도 유지 (새로고침 시 초기화). MA20(slot 0)만 기본 ON.
            var maActive = { 0: true, 1: false, 2: false, 3: false };
            var dispActive = { 0: false, 1: false, 2: false, 3: false };
            // 선택 시리즈 실측치 간격(중앙값)으로 빈도 판정: ≤8일=일별, ≤45일=월별, 그 외=분기
            window.cmbXLabel = function(d) {
                if (!d) return '';
                if (window._cmbXQuarter) {
                    var q = Math.floor((parseInt(d.slice(5, 7), 10) - 1) / 3) + 1;
                    return q + 'Q' + d.slice(2, 4);
                }
                return d.slice(2, 4) + '/' + d.slice(5, 7);
            };
            function cmbDetectFreq(obs) {
                if (!obs || obs.length < 3) return 'D';
                var gaps = [];
                for (var i = 1; i < obs.length; i++) {
                    gaps.push((Date.parse(obs[i].date) - Date.parse(obs[i - 1].date)) / 86400000);
                }
                gaps.sort(function(a, b){ return a - b; });
                var med = gaps[Math.floor(gaps.length / 2)];
                if (med <= 8) return 'D';
                if (med <= 45) return 'M';
                return 'Q';
            }
            // 빈도별 윈도우로 MA/이격도 버튼 라벨·표시·active 상태 동기화 (raw1에서만 호출)
            function cmbRelabelMaButtons(wins) {
                for (var sl = 0; sl < 4; sl++) {
                    var w = wins[sl];
                    var mb = document.getElementById('cmbMaBtn' + sl);
                    var db = document.getElementById('cmbDispBtn' + sl);
                    if (mb) {
                        if (w == null) { mb.style.display = 'none'; }
                        else { mb.style.display = ''; mb.textContent = 'MA' + w; mb.classList.toggle('active', !!maActive[sl]); }
                    }
                    if (db) {
                        if (w == null) { db.style.display = 'none'; }
                        else { db.style.display = ''; db.textContent = '' + w;
                               db.classList.toggle('active', !!dispActive[sl] && !window._cmbDispBlocked); }
                    }
                }
            }
            var cmbDispChart = null;
            var cmbRocChart = null;

            // 피어 차트 목록을 코어(cmbPeerCharts)에 접근자로 제공 — 차트 변수는 이 클로저 소유 (P2a)
            window._cmbPeerAccessor = function() { return [cmbChart, cmbDispChart, cmbRocChart]; };


            function colorForIndex(i) { return clickPalette[i % clickPalette.length]; }

            // ─────────────────────────────────────────────────────────────
            // RoC² (변화율의 변화율) — 2026-07-29
            //  ① 기간말 리샘플(월/주)  ② RoC¹  ③ RoC² = RoC¹의 전기 차분(%p)  ④ 3기간 스무딩
            //  ★계산은 표시 구간이 아니라 '전 기간' 원계열에서 한다 — 기본값 YTD 구간만으로
            //    계산하면 12개월 lag 이 통째로 구간 밖이라 결과가 전부 null 이 된다.
            //  ★RoC¹ 정의는 시리즈 성격에 따라 3갈래 (같은 %라도 의미가 다르다):
            //     level : 이름이 이미 변화율(전년동월비/증감률) → 레벨 그대로가 1차
            //     diff  : %·%p 인 '비율 수준'(금리·실업률·보유비중) → 전년동기 대비 %p 차분
            //             (실업률 3%→4% 를 +33% 로 읽으면 안 되므로 비율 변화율 금지)
            //     yoy   : 그 외 금액·수량 레벨 → 전년동기 대비 % 변화
            // ─────────────────────────────────────────────────────────────
            function cmbHexA(hex, a) {
                var m = /^#?([a-fA-F0-9][a-fA-F0-9])([a-fA-F0-9][a-fA-F0-9])([a-fA-F0-9][a-fA-F0-9])$/.exec(hex || '');
                if (!m) return hex;
                return 'rgba(' + parseInt(m[1], 16) + ',' + parseInt(m[2], 16) + ',' + parseInt(m[3], 16) + ',' + a + ')';
            }
            function cmbRocMA(arr, win) {
                var out = [];
                for (var i = 0; i < arr.length; i++) {
                    var sum = 0, n = 0;
                    for (var j = i - win + 1; j <= i; j++) {
                        if (j < 0 || arr[j] === null || arr[j] === undefined) continue;
                        sum += arr[j]; n++;
                    }
                    out.push(n === win ? sum / n : null);   // 창이 덜 차면 null (앞단 왜곡 방지)
                }
                return out;
            }
            // 'YYYY-MM' 에서 back 개월 뒤로 이동 (달력 기준 lag 조회용)
            function cmbMonthShift(key, back) {
                var y = +key.slice(0, 4), m = +key.slice(5, 7) - back;
                while (m <= 0) { m += 12; y -= 1; }
                return y + '-' + (m < 10 ? '0' + m : '' + m);
            }
            function cmbRocKind(name) {
                if (/전년동월비|전년동기|전년비|증감률/.test(name)) return 'level';
                var u = cmbSeriesUnit[name] || '';
                if (u === '%' || u === '%p') return 'diff';
                return 'yoy';
            }
            function cmbRocCompute(name, freqArg) {
                var arr = cmbData.data[name];
                if (!arr) return null;
                // freqArg = 진단·가용성 판정용 명시 주기(미지정이면 현재 UI 상태)
                var freq = ((freqArg || window.cmbRocFreq) === 'W') ? 'W' : 'M';
                // 1) 기간말 리샘플 — 각 월(주)의 마지막 관측만 남긴다.
                //    일별 데이터의 YoY 를 일별로 차분하면 판독 불가 수준으로 진동한다.
                // ★버킷 키 규칙 — dataset 과 history 가 반드시 같은 함수를 써야 한다(2026-07-30).
                var keyOf = (freq === 'M')
                    ? function(d) { return d.slice(0, 7); }
                    : function(d) { return '' + Math.floor(Date.parse(d) / 604800000); };
                var buckets = {}, order = [];
                for (var i = 0; i < cmbData.dates.length; i++) {
                    var v = arr[i];
                    if (v === null || v === undefined) continue;
                    var d = cmbData.dates[i];
                    var key = keyOf(d);
                    if (!buckets.hasOwnProperty(key)) order.push(key);
                    buckets[key] = { date: d, val: v };
                }
                // ★기간말 백필 히스토리 병합 (cmbRocHist ← roc_history.csv, 2026-07-30)
                //  ① roc_history.csv 는 '월말 ∪ 주말' 관측일의 합집합이다. 위 keyOf 로 날짜순
                //     덮어쓰면 M 은 그 달 마지막·W 는 그 주 마지막 관측이 남으므로 월·주 둘 다 쓴다
                //     (종전엔 월말값만 있어 freq==='M' 으로 가드했고 주(W)는 전 종목 불가였다).
                //  ② history 가 덮는 기간은 history 값으로 '덮어쓴다'(원천 단일화). dataset.csv 는
                //     수집 시점 스냅숏이고 야후 연속선물(NG=F·SI=F…)은 롤오버로 과거가 소급
                //     재작성되므로, 한 YoY 안에서 두 원천을 섞으면 이음매 오차가 커진다 —
                //     2026-07-30 실측 Silver 21.8%p·VIX 6.4%p·Brent 5.3%p(지수·환율·금리는 0.6%p↓).
                //  ③ 단 '표시 좌표'는 dataset.csv 의 그 기간 마지막 관측일을 유지한다. proj() 가
                //     commonDates 에서 위치를 찾으므로 history 의 기간말일이 축에 없으면 점이
                //     조용히 사라진다.
                var H = cmbRocHist[name];
                if (H && H.d) {
                    for (var hi = 0; hi < H.d.length; hi++) {
                        var hk = keyOf(H.d[hi]);
                        if (buckets.hasOwnProperty(hk)) {
                            buckets[hk].val = H.v[hi];
                        } else {
                            buckets[hk] = { date: H.d[hi], val: H.v[hi] };
                            order.push(hk);
                        }
                    }
                    // ★주 키는 숫자 문자열이라 사전순 정렬이 틀린다('999' > '1000') → 주기별 비교자
                    order.sort((freq === 'M') ? undefined
                                              : function(a, b) { return parseInt(a, 10) - parseInt(b, 10); });
                }
                var kind = cmbRocKind(name);
                var lag = (freq === 'M') ? 12 : 52;
                var need = (kind === 'level') ? 4 : lag + 2;
                if (order.length < need) return null;
                // ★lag·전기는 '버킷 인덱스'가 아니라 '달력' 기준으로 잡는다 (2026-07-30 교정).
                //   order[k-12] 는 버킷이 빈틈없이 월별일 때만 12개월 전이다. 분기 시리즈(3개월 간격)
                //   에서는 36개월 전, 국민연금 적립금(연간 이력+최근 월별)에서는 수년 전이 되어
                //   'YoY' 라벨이 붙은 값이 실제로는 다년 변화가 되어 버린다.
                var bucketBack = function(k, back) {
                    var pk = (freq === 'M') ? cmbMonthShift(order[k], back)
                                            : ('' + (parseInt(order[k], 10) - back));
                    return buckets.hasOwnProperty(pk) ? buckets[pk] : null;
                };
                // 2) RoC¹
                var roc1 = [], unit1;
                if (kind === 'level') {
                    unit1 = cmbSeriesUnit[name] || '%';
                    for (var k = 0; k < order.length; k++) roc1.push(buckets[order[k]].val);
                } else if (kind === 'diff') {
                    unit1 = '%p';
                    for (var k2 = 0; k2 < order.length; k2++) {
                        var p2 = bucketBack(k2, lag);
                        roc1.push(p2 ? (buckets[order[k2]].val - p2.val) : null);
                    }
                } else {
                    unit1 = '%';
                    for (var k3 = 0; k3 < order.length; k3++) {
                        var p3 = bucketBack(k3, lag);
                        if (!p3 || !p3.val) { roc1.push(null); continue; }
                        var r = (buckets[order[k3]].val / p3.val - 1) * 100;
                        roc1.push(isFinite(r) ? r : null);
                    }
                }
                // 3) RoC² = 전기 대비 차분 (단위는 항상 %p)
                var roc2 = [];
                for (var k4 = 0; k4 < roc1.length; k4++) {
                    // ★'전기' = 그 시리즈 자신의 직전 관측(= 직전 버킷). 분기 시리즈면 3개월 전,
                    //   월별이면 1개월 전이다. 달력 1개월 전을 강제하면 분기 시리즈는 그 버킷이
                    //   없어 RoC² 가 전부 null 이 된다(2026-07-30 실측: 분기 6종 5→0포인트).
                    //   전년동기(lag)만 달력 기준 — 그쪽은 '12개월 전'이라는 절대 기준이 있다.
                    var a = roc1[k4], b = (k4 > 0) ? roc1[k4 - 1] : null;
                    roc2.push((a === null || b === null || a === undefined || b === undefined) ? null : a - b);
                }
                // 4) 스무딩은 RoC² 에만. RoC¹ 은 수준 판단용 기준선이라 원값 유지.
                if (window.cmbRocSmooth !== false) roc2 = cmbRocMA(roc2, 3);
                return { order: order, buckets: buckets, roc1: roc1, roc2: roc2,
                         kind: kind, unit1: unit1, freq: freq };
            }

            // ── RoC² 불가 '사유' 진단 (2026-07-30) ─────────────────────────
            //  ★'이력이 짧다'와 '관측주기가 안 맞다'는 다른 문제다. 국민연금·퇴직연금 적립금은
            //    연 1회 관측이라 이력을 늘려도 12개월 lag 월 리샘플이 성립하지 않는다(월버킷 10개).
            //    월간 시리즈에 주(W) 리샘플을 걸어도 같은 성질의 문제(주 54버킷 불가).
            //    한 문장으로 뭉쳐 "이력이 짧습니다"라고 하면 백필하면 될 것처럼 읽혀서 오해를 부른다.
            function cmbRocDiag(name, freq) {
                freq = (freq === 'W') ? 'W' : 'M';
                // ★허용 목록 밖이면 계산 가능해도 쓰지 않는다 — RoC² 부호가 매 기간 뒤집혀
                //   판독이 안 되는 시리즈다(무작위 기대 런 2.0 근처). 사유를 숫자로 보여준다.
                if (!cmbRocAllow[name]) {
                    return { ok: false, why: 'RoC\u00b2 판독성 미달 — 부호가 거의 매 기간 뒤집혀 노이즈입니다 '
                                             + '(가격·지수 계열은 대체로 여기 해당). 부동산·유동성·물가·심리 지표에서 보세요' };
                }
                var R = cmbRocCompute(name, freq);
                if (R) {
                    for (var i = 0; i < R.roc2.length; i++) {
                        if (R.roc2[i] !== null && R.roc2[i] !== undefined) return { ok: true, why: '' };
                    }
                }
                var arr = cmbData.data[name];
                if (!arr) return { ok: false, why: '데이터가 없습니다' };
                var months = {};
                for (var j = 0; j < cmbData.dates.length; j++) {
                    if (arr[j] === null || arr[j] === undefined) continue;
                    months[cmbData.dates[j].slice(0, 7)] = 1;
                }
                var Hh = cmbRocHist[name];
                if (freq === 'M' && Hh && Hh.d) {
                    for (var h = 0; h < Hh.d.length; h++) months[Hh.d[h].slice(0, 7)] = 1;
                }
                var keys = Object.keys(months).sort();
                // 관측 주기(개월) = 월 버킷 간격의 중앙값. 일별·월별=1, 분기=3, 연간=12.
                var gaps = [];
                for (var g = 1; g < keys.length; g++) {
                    var a = keys[g - 1].split('-'), b = keys[g].split('-');
                    gaps.push((b[0] - a[0]) * 12 + (b[1] - a[1]));
                }
                gaps.sort(function(x, y) { return x - y; });
                var gap = gaps.length ? gaps[Math.floor(gaps.length / 2)] : 0;
                var nb = keys.length;
                if (freq === 'W' && gap >= 2) {
                    return { ok: false, why: '관측주기가 약 ' + gap + '개월이라 주(W) 리샘플이 성립하지 않습니다 — 월(M)로 보세요' };
                }
                if (gap >= 6) {
                    return { ok: false, why: '연 단위 관측(간격 약 ' + gap + '개월)이라 12개월 lag 월 리샘플이 성립하지 않습니다' };
                }
                if (gap >= 2) {
                    return { ok: false, why: '분기 관측(간격 약 ' + gap + '개월)이라 월 버킷이 ' + nb + '개뿐입니다 (14개 필요)' };
                }
                // 필요 버킷: RoC¹ 에 lag+1, RoC² 에 +1, 3기간 MA 에 +2 → 스무딩 ON 이면 lag+4.
                var needN = 12 + (window.cmbRocSmooth !== false ? 4 : 2);
                if (freq === 'W') {
                    return { ok: false, why: '이력이 짧아 계산할 수 없습니다 (주 리샘플은 연속 ' + (52 + (window.cmbRocSmooth !== false ? 4 : 2)) + '주 필요)' };
                }
                return { ok: false, why: '이력이 짧아 계산할 수 없습니다 (연속된 월 버킷 ' + needN + '개 필요 / 현재 ' + nb + '개)' };
            }
            // 주기 버튼 가용성 — 선택 시리즈가 그 주기로 RoC² 를 낼 수 있는지 반영(흐리게 + 클릭 차단)
            function cmbSyncRocFreqAvail() {
                ['M', 'W'].forEach(function(f) {
                    var btn = document.getElementById('cmbRocFreq' + f);
                    if (!btn) return;
                    var any = false;
                    for (var i = 0; i < cmbClickOrder.length; i++) {
                        if (cmbRocDiag(cmbClickOrder[i], f).ok) { any = true; break; }
                    }
                    var dis = cmbClickOrder.length > 0 && !any;
                    btn.style.opacity = dis ? '0.4' : '';
                    btn.style.pointerEvents = dis ? 'none' : '';
                    btn.title = dis ? ((f === 'W' ? '주(W)' : '월(M)') + ' 리샘플로는 선택 시리즈의 RoC\u00b2 를 낼 수 없습니다') : '';
                });
            }

            function fmtNum(v) {
                if (v === null || v === undefined) return '-';
                return Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
            }



            // 억원 단위 금액 시리즈 — 1조(=1만억) 이상은 'N조 N,NNN억' 통일 (2026-07-16 사용자 확정)
            var cmbEokSeries = {};
            Object.keys(cmbSeriesUnit).forEach(function(k) { if (cmbSeriesUnit[k] === '억원') cmbEokSeries[k] = 1; });
            function fmtEokTick(v) {   // 축 눈금용(짧게): 1,537.6조 / 5,000억
                var a = Math.abs(v), sgn = v < 0 ? '-' : '';
                if (a >= 10000) return sgn + (a / 10000).toLocaleString(undefined, { maximumFractionDigits: 1 }) + '조';
                return sgn + Math.round(a).toLocaleString() + '억';
            }

            // ── 엑셀식 칼럼 필터 (수수료 매출 rev-filter 패턴 이식, 검색창 대체) ──
            // cmbFilters: col -> 허용 표시값 배열 (키 없음 = 전체 허용)
            var cmbFilters = {};
            function cmbRowVal(row, col) {
                if (col === 'rank') return row.cells[1].textContent.trim();  // cells[0] = 별표
                if (col === 'country') return row.getAttribute('data-country') || '';
                if (col === 'group') return row.getAttribute('data-group') || '';
                return row.getAttribute('data-name') || '';
            }
            function cmbRowPasses(row, skipCol) {
                return ['rank', 'country', 'group', 'name'].every(function(c) {
                    if (c === skipCol) return true;
                    var f = cmbFilters[c];
                    return !f || f.indexOf(cmbRowVal(row, c)) !== -1;
                });
            }

            // ── 별표(즐겨찾기) — Watchlist 패턴 (2026-07-19). 헤더 ★ = 즐겨찾기만 보기 토글
            //    (엑셀식 필터와 AND 결합). 상태 = 맥미니 서버 저장(/watchlist/stars, 기기 공통,
            //    2026-07-20 전환) + localStorage는 즉시표시 캐시·오프라인 폴백.
            var cmbStars = {};
            var cmbStarList = [];   // 사용자 지정 순서(드래그). 서버 저장 형식 = 이 배열 그대로
            try {
                cmbStarList = JSON.parse(localStorage.getItem('cmbStars') || '[]') || [];
                cmbStarList.forEach(function(n) { cmbStars[n] = 1; });
            } catch (e) { cmbStarList = []; }
            var cmbStarOnly = false;
            try {
                fetch('/watchlist/stars').then(function(r) { return r.ok ? r.json() : null; }).then(function(a) {
                    if (!Array.isArray(a)) return;
                    cmbStars = {};
                    cmbStarList = a.slice();
                    a.forEach(function(n) { cmbStars[n] = 1; });
                    try { localStorage.setItem('cmbStars', JSON.stringify(a)); } catch (e) {}
                    cmbPaintStars();
                    if (cmbStarOnly) cmbApplyFilters();
                }).catch(function() {});
            } catch (e) {}
            function cmbSaveStars() {
                var arr = cmbStarList.filter(function(n) { return cmbStars[n]; });
                Object.keys(cmbStars).forEach(function(n) { if (arr.indexOf(n) < 0) arr.push(n); });
                cmbStarList = arr;
                try { localStorage.setItem('cmbStars', JSON.stringify(arr)); } catch (e) {}
                try {
                    fetch('/watchlist/stars', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(arr) }).catch(function() {});
                } catch (e) {}
            }
            function cmbPaintStars() {
                document.querySelectorAll('.cmb-series-row td.cmb-star').forEach(function(td) {
                    var on = !!cmbStars[td.parentNode.getAttribute('data-name')];
                    td.textContent = on ? '★' : '☆';
                    td.classList.toggle('on', on);
                });
                var th = document.getElementById('cmbStarTh');
                if (th) th.classList.toggle('on', cmbStarOnly);
                window.cmbApplyPin();
            }
            // 고정 블록 드래그 순서 변경 (2026-07-28). 순서 정본 = cmbStarList(서버 저장 배열).
            var _cmbDragName = null;
            function cmbClearDrop() {
                document.querySelectorAll('#cmbSideTable tr.cmb-drop').forEach(function(x) { x.classList.remove('cmb-drop'); });
            }
            function cmbBindDrag(row) {
                if (row._cmbDrag) return;   // 중복 바인드 방지 (cmbApplyPin 은 자주 불린다)
                row._cmbDrag = 1;
                row.addEventListener('dragstart', function(e) {
                    if (!row.classList.contains('cmb-pinned')) { e.preventDefault(); return; }
                    _cmbDragName = row.getAttribute('data-name');
                    row.classList.add('cmb-drag');
                    try { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', _cmbDragName); } catch (x) {}
                });
                row.addEventListener('dragover', function(e) {
                    if (!_cmbDragName || !row.classList.contains('cmb-pinned')) return;
                    e.preventDefault();
                    try { e.dataTransfer.dropEffect = 'move'; } catch (x) {}
                    if (row.getAttribute('data-name') !== _cmbDragName) { cmbClearDrop(); row.classList.add('cmb-drop'); }
                });
                row.addEventListener('drop', function(e) {
                    e.preventDefault(); e.stopPropagation();
                    cmbClearDrop();
                    var to = row.getAttribute('data-name');
                    if (!_cmbDragName || to === _cmbDragName) return;
                    var from = cmbStarList.indexOf(_cmbDragName), ti = cmbStarList.indexOf(to);
                    if (from < 0 || ti < 0) return;
                    cmbStarList.splice(from, 1);
                    var ni = cmbStarList.indexOf(to);
                    cmbStarList.splice(from < ti ? ni + 1 : ni, 0, _cmbDragName);   // 아래로=뒤에, 위로=앞에
                    cmbSaveStars();
                    window.cmbApplyPin();
                });
                row.addEventListener('dragend', function() {
                    row.classList.remove('cmb-drag');
                    cmbClearDrop();
                    _cmbDragName = null;
                    window._cmbDragJustEnded = 1;   // 드롭 직후 click 이 차트 선택을 건드리지 않도록
                    setTimeout(function() { window._cmbDragJustEnded = 0; }, 150);
                });
            }
            // 별표 행을 테이블 맨 위로 고정 + 구분행 삽입 (2026-07-28).
            // 상태를 DOM(td.cmb-star.on)에서 읽으므로 정렬·필터 어느 경로에서 불러도 동작한다.
            window.cmbApplyPin = function() {
                var tbody = document.querySelector('#cmbSideTable tbody');
                if (!tbody) return;
                var old = document.getElementById('cmbPinHead');
                if (old) old.parentNode.removeChild(old);
                var pinned = [];
                tbody.querySelectorAll('tr.cmb-series-row').forEach(function(r) {
                    var td = r.querySelector('td.cmb-star');
                    if (td && td.classList.contains('on')) pinned.push(r);
                });
                tbody.querySelectorAll('tr.cmb-pinned').forEach(function(r) {
                    r.classList.remove('cmb-pinned'); r.removeAttribute('draggable');
                });
                if (!window._cmbDragGuard) {   // 드롭 직후 잔여 click 삼키기 (캡처 단계)
                    window._cmbDragGuard = 1;
                    var tbl = document.getElementById('cmbSideTable');
                    if (tbl) tbl.addEventListener('click', function(e) {
                        if (window._cmbDragJustEnded) { e.stopPropagation(); e.preventDefault(); }
                    }, true);
                }
                if (!pinned.length) return;
                // 표시 순서 = 사용자 지정(cmbStarList). 목록에 없는 별표는 뒤로.
                pinned.sort(function(a, b) {
                    var ia = cmbStarList.indexOf(a.getAttribute('data-name'));
                    var ib = cmbStarList.indexOf(b.getAttribute('data-name'));
                    if (ia < 0) { ia = 9999; }
                    if (ib < 0) { ib = 9999; }
                    return ia - ib;
                });
                var tr = document.createElement('tr');
                tr.id = 'cmbPinHead';
                tr.className = 'cmb-pin-head';
                var td2 = document.createElement('td');
                td2.colSpan = 5;
                var shown = pinned.filter(function(r) { return r.style.display !== 'none'; }).length;
                td2.textContent = '';   // 텍스트 없는 구분선 — 개수는 툴바 버튼이 표시
                tr.appendChild(td2);
                tr.style.display = shown ? '' : 'none';
                // 별표 행을 맨 위로 (기존 상대순서 유지) → 구분선은 마지막 별표 행 '뒤'
                var ref = null;
                pinned.forEach(function(r) {
                    if (ref === null) { tbody.insertBefore(r, tbody.firstChild); }
                    else { ref.parentNode.insertBefore(r, ref.nextSibling); }
                    r.classList.add('cmb-pinned');
                    r.setAttribute('draggable', 'true');
                    cmbBindDrag(r);
                    ref = r;
                });
                if (ref) ref.parentNode.insertBefore(tr, ref.nextSibling);
            };
            window.cmbToggleStar = function(td, ev) {
                ev.stopPropagation();
                var name = td.parentNode.getAttribute('data-name');
                if (cmbStars[name]) {
                    delete cmbStars[name];
                    var si = cmbStarList.indexOf(name);
                    if (si >= 0) cmbStarList.splice(si, 1);
                } else {
                    cmbStars[name] = 1;
                    if (cmbStarList.indexOf(name) < 0) cmbStarList.push(name);
                }
                cmbSaveStars();
                cmbPaintStars();
                if (cmbStarOnly) cmbApplyFilters();
            };
            window.cmbToggleStarOnly = function(ev) {
                ev.stopPropagation();
                cmbStarOnly = !cmbStarOnly;
                cmbPaintStars();
                cmbApplyFilters();
            };

            // Data 칼럼 검색 — 시리즈명 부분일치, 엑셀 필터·별표 필터와 AND 결합
            var cmbSearchQ = '';
            window.cmbApplySearch = function(v) {
                cmbSearchQ = (v || '').trim().toLowerCase();
                cmbApplyFilters();
            };
            function cmbApplyFilters() {
                document.querySelectorAll('.cmb-series-row').forEach(function(row) {
                    var _nm = (row.getAttribute('data-name') || '').toLowerCase();
                    var pass = cmbRowPasses(row, null) &&
                        (!cmbStarOnly || cmbStars[row.getAttribute('data-name')]) &&
                        (!cmbSearchQ || _nm.indexOf(cmbSearchQ) >= 0);
                    row.style.display = pass ? '' : 'none';
                });
                ['rank', 'country', 'group', 'name'].forEach(function(c) {
                    var btn = document.querySelector('.cmb-filter-btn[data-col="' + c + '"]');
                    if (btn) btn.classList.toggle('cmb-filter-on', !!cmbFilters[c]);
                });
                window.cmbApplyPin();
            }
            function cmbCloseFilter() {
                var p = document.getElementById('cmbFilterPop');
                if (p) p.parentNode.removeChild(p);
            }
            window.cmbOpenFilter = function(btn, ev) {
                ev.stopPropagation();
                var col = btn.getAttribute('data-col');
                var existing = document.getElementById('cmbFilterPop');
                var reopen = !(existing && existing.dataset.col === col);
                cmbCloseFilter();
                if (!reopen) return;  // 같은 칼럼 ▾ 재클릭 = 닫기
                var vals = [];
                document.querySelectorAll('.cmb-series-row').forEach(function(row) {
                    if (!cmbRowPasses(row, col)) return;  // 엑셀 자동필터: 타 칼럼 필터 적용 집합 기준
                    var v = cmbRowVal(row, col);
                    if (vals.indexOf(v) === -1) vals.push(v);
                });
                if (col === 'rank') {
                    var rk = { Daily: 0, Weekly: 1, Monthly: 2, Yearly: 3 };
                    vals.sort(function(a, b) { return (rk[a] || 0) - (rk[b] || 0); });
                } else { vals.sort(); }
                var cur = cmbFilters[col];
                var inner = '<label class="cmb-filter-item"><input type="checkbox" id="cmbFAll"' +
                    (!cur ? ' checked' : '') + ' onchange="cmbFilterAll(this, \\'' + col + '\\')"> (전체 선택)</label>';
                vals.forEach(function(v) {
                    var on = (!cur || cur.indexOf(v) !== -1) ? ' checked' : '';
                    inner += '<label class="cmb-filter-item"><input type="checkbox" data-val="' +
                        v.replace(/"/g, '&quot;') + '"' + on + ' onchange="cmbFilterVal(\\'' + col + '\\')"> ' + v + '</label>';
                });
                var pop = document.createElement('div');
                pop.id = 'cmbFilterPop'; pop.className = 'cmb-filter-pop'; pop.dataset.col = col;
                pop.onclick = function(e) { e.stopPropagation(); };
                pop.innerHTML = inner;
                var host = document.getElementById('cmbSideHost');
                host.appendChild(pop);
                var br = btn.getBoundingClientRect(), hr = host.getBoundingClientRect();
                pop.style.left = Math.max(0, br.left - hr.left - 8) + 'px';
                pop.style.top = (br.bottom - hr.top + 6) + 'px';
            };
            window.cmbFilterAll = function(box, col) {
                document.getElementById('cmbFilterPop').querySelectorAll('input[data-val]').forEach(function(i) { i.checked = box.checked; });
                if (box.checked) { delete cmbFilters[col]; } else { cmbFilters[col] = []; }
                cmbApplyFilters();
            };
            window.cmbFilterVal = function(col) {
                var items = document.getElementById('cmbFilterPop').querySelectorAll('input[data-val]');
                var sel = [];
                items.forEach(function(i) { if (i.checked) sel.push(i.getAttribute('data-val')); });
                if (sel.length === items.length) { delete cmbFilters[col]; } else { cmbFilters[col] = sel; }
                var all = document.getElementById('cmbFAll');
                if (all) all.checked = sel.length === items.length;
                cmbApplyFilters();
            };
            document.addEventListener('click', cmbCloseFilter);

            // 선택 카운터(검색창 아래 "● N개 선택") 재계산 — 중앙화 함수.
            // active 토글이 일어나는 모든 경로가 buildCmbChart()를 거치므로 거기서 호출.
            function updateCmbGroupBadges() {
                var n = document.querySelectorAll('.cmb-series-row .cmb-chart-item.active').length;
                var el = document.getElementById('cmbSelCount');
                if (!el) return;
                el.textContent = n > 0 ? '● ' + n + '개 선택' : '';
            }

            // 3칼럼 헤더 정렬: <tr> 노드를 appendChild로 재정렬 (재렌더 아님 —
            // active 클래스/color-bar/tooltip 상태가 노드에 실려 있어 그대로 따라감).
            // Update 칼럼은 data-update-rank(0/1/2 = D/W/M 의미순) 숫자 비교.
            var _cmbSortKey = 'rank', _cmbSortAsc = true;
            function updateCmbSortArrows() {
                ['rank', 'country', 'group', 'name'].forEach(function(k) {
                    var sp = document.getElementById('cmbArr_' + k);
                    if (sp) sp.textContent = (k === _cmbSortKey) ? (_cmbSortAsc ? '▲' : '▼') : '';
                });
            }
            window.sortCmbTable = function(key) {
                if (_cmbSortKey === key) { _cmbSortAsc = !_cmbSortAsc; }
                else { _cmbSortKey = key; _cmbSortAsc = true; }
                var tbody = document.querySelector('#cmbSideTable tbody');
                if (!tbody) return;
                var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr.cmb-series-row'));
                rows.sort(function(a, b) {
                    var va, vb;
                    if (key === 'rank') { va = +a.getAttribute('data-update-rank'); vb = +b.getAttribute('data-update-rank'); }
                    else if (key === 'country') { va = (a.getAttribute('data-country') || '').toLowerCase(); vb = (b.getAttribute('data-country') || '').toLowerCase(); }
                    else if (key === 'group') { va = (a.getAttribute('data-group') || '').toLowerCase(); vb = (b.getAttribute('data-group') || '').toLowerCase(); }
                    else { va = (a.getAttribute('data-name') || '').toLowerCase(); vb = (b.getAttribute('data-name') || '').toLowerCase(); }
                    if (va < vb) return _cmbSortAsc ? -1 : 1;
                    if (va > vb) return _cmbSortAsc ? 1 : -1;
                    return 0; // 동률은 기존 순서 유지 (stable sort)
                });
                rows.forEach(function(r) { tbody.appendChild(r); });
                if (window.cmbApplyPin) window.cmbApplyPin();
                updateCmbSortArrows();
            };

            // 선택 표시: 행 전체 배경을 해당 시리즈 차트 색의 옅은 틴트(14%)로 하이라이트.
            // 인라인 스타일이라 tr:hover CSS보다 우선 — 선택 행은 hover에 안 씻김.
            function hexToTint(hex) {
                var m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
                if (!m) return 'rgba(0,0,0,0.10)';
                var n = parseInt(m[1], 16);
                return 'rgba(' + (n >> 16 & 255) + ',' + (n >> 8 & 255) + ',' + (n & 255) + ',0.14)';
            }
            function applyMarkerColors() {
                document.querySelectorAll('.cmb-chart-item').forEach(function(el) {
                    var row = el.closest('tr');
                    if (!row) return;
                    var idx = cmbClickOrder.indexOf(el.getAttribute('data-series'));
                    var tint = idx >= 0 ? hexToTint(colorForIndex(idx)) : '';
                    Array.prototype.forEach.call(row.cells, function(td) {
                        td.style.background = tint;
                    });
                });
            }

            function buildCmbChart() {
                var activeSet = {};
                document.querySelectorAll('.cmb-chart-item.active').forEach(function(el){
                    activeSet[el.getAttribute('data-series')] = true;
                });
                cmbClickOrder = cmbClickOrder.filter(function(n){ return activeSet[n]; });
                Object.keys(activeSet).forEach(function(n){
                    if (cmbClickOrder.indexOf(n) === -1) cmbClickOrder.push(n);
                });
                var selected = cmbClickOrder.slice();
                // 주기 가드 (2026-07-30) — 선택 시리즈가 주(W)로 RoC² 를 못 내면 조용히 월(M)로
                // 되돌린다. ★여기서는 상태만 고치고 그대로 진행한다(재귀 렌더 호출 금지).
                if (window.cmbRocOn && window.cmbRocFreq === 'W' && cmbClickOrder.length) {
                    var _okW = false, _okM = false;
                    for (var _gi = 0; _gi < cmbClickOrder.length; _gi++) {
                        if (cmbRocDiag(cmbClickOrder[_gi], 'W').ok) { _okW = true; break; }
                    }
                    if (!_okW) {
                        for (var _gj = 0; _gj < cmbClickOrder.length; _gj++) {
                            if (cmbRocDiag(cmbClickOrder[_gj], 'M').ok) { _okM = true; break; }
                        }
                        if (_okM) { window.cmbRocFreq = 'M'; cmbSyncRocUI(); }
                    }
                }
                applyMarkerColors();
                updateCmbGroupBadges();

                var startDate = document.getElementById('cmbStartDate').value;
                var endDate = document.getElementById('cmbEndDate').value;

                // Monthly/Yearly 시리즈는 최소 12개 관측이 보이도록 시작일 자동 확장.
                // 선택 변경 시에만 동작(cmbAutoRangePending) — 수동 날짜 입력은 존중.
                if (cmbAutoRangePending) {
                    cmbAutoRangePending = false;
                    var needStart = null;
                    selected.forEach(function(name) {
                        var row = document.querySelector('.cmb-series-row[data-name="' + name.replace(/"/g, '\\"') + '"]');
                        var rank = row ? +row.getAttribute('data-update-rank') : 0;
                        if (rank < 2) return;   // 0=D, 1=W는 대상 아님
                        var arr = cmbData.data[name];
                        if (!arr) return;
                        var obsDates = [];
                        for (var i = 0; i < cmbData.dates.length; i++) {
                            if (arr[i] !== null && arr[i] !== undefined && cmbData.dates[i] <= endDate) obsDates.push(cmbData.dates[i]);
                        }
                        if (!obsDates.length) return;
                        var d12 = obsDates[Math.max(0, obsDates.length - 12)];
                        if (needStart === null || d12 < needStart) needStart = d12;
                    });
                    if (needStart !== null && needStart < startDate) {
                        startDate = needStart;
                        document.getElementById('cmbStartDate').value = needStart;
                    }
                }

                var perSeries = [];
                selected.forEach(function(name) {
                    var arr = cmbData.data[name];
                    if (!arr) return;
                    var lookup = {};
                    var firstDate = '';
                    for (var i = 0; i < cmbData.dates.length; i++) {
                        var d = cmbData.dates[i];
                        if (d >= startDate && d <= endDate && arr[i] !== null && arr[i] !== undefined) {
                            lookup[d] = arr[i];
                            if (!firstDate) firstDate = d;
                        }
                    }
                    if (!firstDate) return;
                    perSeries.push({ name: name, lookup: lookup, firstDate: firstDate });
                });

                var commonStart = '';
                perSeries.forEach(function(s) {
                    if (s.firstDate > commonStart) commonStart = s.firstDate;
                });

                var dateSet = {};
                perSeries.forEach(function(s) {
                    Object.keys(s.lookup).forEach(function(d) {
                        if (d >= commonStart) dateSet[d] = true;
                    });
                });
                var commonDates = Object.keys(dateSet).sort();

                var mode = window.cmbForceNorm ? 'pct' : (perSeries.length === 1 ? 'raw1' : (perSeries.length === 2 ? 'raw2' : 'pct'));

                // 단일 선택(raw1)일 때만 MA/이격도 버튼 활성 (상태 값은 보존)
                var maRow = document.getElementById('cmbMaRow');
                if (maRow) maRow.classList.toggle('cmb-ma-disabled', mode !== 'raw1');
                // ★이격도 적격 판정 = 단위가 아니라 '데이터' 기준 (2026-07-28 동적 전환).
                //   이격도 = 값/MA×100 이라 분모(MA)가 0 근처면 발산한다. 표시 구간에서
                //     ① 부호가 섞이거나  ② 최소 절대값이 최대 절대값의 2% 미만이면 잠근다.
                //   종전 단위 기준(%·%p 일괄 차단)은 가동률·외국인비중처럼 '항상 양수인 비율'까지
                //   막았고, 반대로 0 을 넘나드는 무단위 지수(NFCI −0.552·은행 대출태도지수 −2)는
                //   놓쳤다. 데이터로 판정하면 신규 시리즈도 자동으로 걸러진다.
                function cmbDispEligible(s) {
                    if (!s) return false;
                    var pos = false, neg = false, mn = Infinity, mx = 0;
                    var ks = Object.keys(s.lookup);
                    for (var i = 0; i < ks.length; i++) {
                        var v = s.lookup[ks[i]];
                        if (v === null || v === undefined || isNaN(v)) continue;
                        if (v > 0) { pos = true; } else if (v < 0) { neg = true; }
                        var a = Math.abs(v);
                        if (a < mn) mn = a;
                        if (a > mx) mx = a;
                    }
                    if (mx === 0 || mn === Infinity) return false;
                    if (pos && neg) return false;        // 0 을 넘나드는 계열
                    return mn >= mx * 0.02;              // 0 에 바짝 붙는 구간이 있으면 부적격
                }
                var _dispBlocked = (mode !== 'raw1') || !cmbDispEligible(perSeries[0]);
                window._cmbDispBlocked = _dispBlocked;   // 선택 상태는 보존하고 렌더 시점에만 차단
                var dispGroup = document.getElementById('cmbDispGroup');
                if (dispGroup) dispGroup.classList.toggle('cmb-ma-disabled', _dispBlocked);
                var yEok = mode !== 'pct' && perSeries.length > 0 && !!cmbEokSeries[perSeries[0].name];
                var y1Eok = mode === 'raw2' && perSeries.length > 1 && !!cmbEokSeries[perSeries[1].name];

                var datasets = [];
                var dispDatasets = [];
                var _axAssign = [];   // 축 단위 주석 역산용 (name -> 실제 배정 축)
                // ★외국인 보유비중의 y축 강제는 '두 시리즈 단위가 같을 때'만 (2026-07-29).
                //   종전엔 무조건 y 로 묶어서 만명(입국자)과 %(보유비중)가 한 축을 공유했다.
                var _u0 = perSeries.length > 0 ? (cmbSeriesUnit[perSeries[0].name] || '') : '';
                var _u1 = perSeries.length > 1 ? (cmbSeriesUnit[perSeries[1].name] || '') : '';
                var _sameUnit = (_u0 === _u1);
                // ★분기 시리즈 표기 (2026-07-29): 선택 시리즈가 '전부' 분기일 때만 X축·핀 카드·
                //   툴팁 제목을 1Q26 형식으로. 다른 주기가 섞이면 종전 26/04 형식 유지.
                //   분기 스탬프는 관측월 말일(2026-04-30 = 2Q26)이라 월에서 바로 분기를 낸다.
                window._cmbXQuarter = perSeries.length > 0 && perSeries.every(function(s) {
                    return cmbDetectFreq(Object.keys(s.lookup).sort().map(function(d) {
                        return { date: d };
                    })) === 'Q';
                });
                perSeries.forEach(function(s, idx) {
                    var aligned = [];
                    var lastVal = null;
                    for (var i = 0; i < commonDates.length; i++) {
                        var d = commonDates[i];
                        if (s.lookup.hasOwnProperty(d)) lastVal = s.lookup[d];
                        aligned.push(lastVal);
                    }
                    var data;
                    // ★부분문자열 매칭 금지 (2026-07-28): '외국인 입국자'·'체류외국인 *' 가
                    //   보유비중으로 오분류돼 만명 값이 % 축에 레벨로 그려지던 버그.
                    //   보유비중 = 이름이 '외국인'/'외국인비중' 으로 끝나고 단위가 % 인 것만.
                    var isForeign = /외국인(비중)?$/.test(s.name) && cmbSeriesUnit[s.name] === '%';
                    var scale = isForeign ? 1 : (seriesScale[s.name] || 1);
                    if (isForeign) {
                        // 외국인 보유비중/지분율: 정규화/scale 없이 항상 레벨(%) 표시
                        data = aligned.slice();
                    } else if (mode === 'pct') {
                        var base = null;
                        for (var j = 0; j < aligned.length; j++) {
                            if (aligned[j] !== null) { base = aligned[j]; break; }
                        }
                        // base가 0/음수인 시리즈(스프레드, 경상수지, 대출태도지수 등)는
                        // % 정규화가 무의미(Infinity/부호반전) → 3개 이상 선택 시 제외
                        if (base === null || base <= 0) return;
                        data = aligned.map(function(v) {
                            if (v === null) return null;
                            return Math.round((v / base - 1) * 10000) / 100;
                        });
                    } else {
                        data = aligned.map(function(v) {
                            if (v === null) return null;
                            var sv = v / scale;
                            return scale >= 1e8 ? Math.round(sv) : sv;
                        });
                    }
                    var yAxisID = (mode === 'raw2' && idx === 1 && !(isForeign && _sameUnit)) ? 'y1' : 'y';
                    _axAssign.push({ name: s.name, ax: yAxisID });   // 축 주석 역산용
                    var clickIdx = cmbClickOrder.indexOf(s.name);
                    datasets.push({
                        label: s.name,
                        data: data,
                        borderColor: colorForIndex(clickIdx >= 0 ? clickIdx : 0),
                        backgroundColor: 'transparent',
                        borderWidth: 3,
                        borderJoinStyle: 'round',
                        borderCapStyle: 'round',
                        pointRadius: 0,
                        tension: 0.4,
                        cubicInterpolationMode: 'monotone',
                        spanGaps: true,
                        yAxisID: yAxisID,
                        _isForeign: isForeign
                    });

                    // 단일 선택일 때 토글된 MA / 이격도 추가.
                    // MA 윈도우 = 선택 시리즈의 "직전 N개 실측치"(forward-fill 축이 아니라
                    // 네이티브 관측치 기준). 일별→N 거래일, 월별→N개월, 분기→N분기.
                    // 윈도우 값은 빈도(MA_WINDOWS)에 따라 슬롯별로 달라지고 버튼 라벨도 동적.
                    if (mode === 'raw1') {
                        var fullArr = cmbData.data[s.name];
                        var fullDates = cmbData.dates;
                        // 네이티브 관측치 시퀀스 (non-null만, 전체 기간 — 긴 윈도우도 정확히 채움)
                        var obs = [];
                        for (var fi = 0; fi < fullArr.length; fi++) {
                            if (fullArr[fi] !== null && fullArr[fi] !== undefined) {
                                obs.push({ date: fullDates[fi], val: fullArr[fi] });
                            }
                        }
                        var freq = cmbDetectFreq(obs);
                        var wins = MA_WINDOWS[freq];
                        cmbRelabelMaButtons(wins);

                        // 직전 win개 관측치 이동평균 (running sum, O(n))
                        function computeNativeMA(obsArr, win) {
                            var out = new Array(obsArr.length);
                            var runSum = 0;
                            for (var i = 0; i < obsArr.length; i++) {
                                runSum += obsArr[i].val;
                                if (i >= win) runSum -= obsArr[i - win].val;
                                out[i] = (i >= win - 1) ? runSum / win : null;
                            }
                            return out;
                        }
                        // 관측치 MA를 commonDates에 forward-fill 매핑 (raw 선과 같은 리듬)
                        function buildFilledMap(obsArr, maAtObs) {
                            var byDate = {};
                            for (var oi = 0; oi < obsArr.length; oi++) {
                                byDate[obsArr[oi].date] = { ma: maAtObs[oi], rawVal: obsArr[oi].val };
                            }
                            var res = [];
                            var lastMa = null, lastRaw = null;
                            for (var ci = 0; ci < commonDates.length; ci++) {
                                var hit = byDate[commonDates[ci]];
                                if (hit !== undefined) { lastMa = hit.ma; lastRaw = hit.rawVal; }
                                res.push({ ma: lastMa, rawVal: lastRaw });
                            }
                            return res;
                        }

                        MA_DEFS.forEach(function(def, slot) {
                            var win = wins[slot];
                            if (win == null) return;                       // 분기 4번째 슬롯 등 미사용
                            if (!maActive[slot] && !dispActive[slot]) return;
                            var maAtObs = computeNativeMA(obs, win);
                            var filled = buildFilledMap(obs, maAtObs);
                            if (maActive[slot]) {
                                // MA도 본 라인과 같은 scale 적용 (KOSPI/KOSDAQ Market Cap은 1e12로 조 단위)
                                var maVisible = filled.map(function(pt) {
                                    if (pt.ma === null || pt.ma === undefined) return null;
                                    var sv = pt.ma / scale;
                                    return scale >= 1e8 ? Math.round(sv) : sv;
                                });
                                // 전 구간 null(데이터 부족)이면 범례 유령 항목 방지를 위해 생략
                                if (maVisible.some(function(v){ return v !== null; })) datasets.push({
                                    label: 'MA' + win,
                                    data: maVisible,
                                    borderColor: def.color,
                                    backgroundColor: 'transparent',
                                    borderWidth: 2.5,
                                    borderJoinStyle: 'round',
                                    borderCapStyle: 'round',
                                    pointRadius: 0,
                                    tension: 0.4,
                                    cubicInterpolationMode: 'monotone',
                                    spanGaps: true,
                                    yAxisID: yAxisID,
                                    _isForeign: isForeign
                                });
                            }
                            if (dispActive[slot] && !window._cmbDispBlocked) {
                                // 이격도 = 값/MA×100 (비율이라 단위 scale 자동 소거)
                                var dispVisible = filled.map(function(pt) {
                                    if (pt.ma === null || pt.ma === undefined) return null;
                                    if (pt.rawVal === null || pt.rawVal === undefined) return null;
                                    // 분모 방어: MA 가 값 대비 2% 미만이면 비율이 발산한다 (ma===0 만으론 부족)
                                    if (Math.abs(pt.ma) < Math.abs(pt.rawVal) * 0.02) return null;
                                    var _d = pt.rawVal / pt.ma * 100;
                                    if (!isFinite(_d)) return null;
                                    return Math.round(_d * 100) / 100;
                                });
                                if (dispVisible.some(function(v){ return v !== null; })) dispDatasets.push({
                                    label: '이격도' + win,
                                    data: dispVisible,
                                    borderColor: def.color,
                                    backgroundColor: 'transparent',
                                    borderWidth: 2.2,
                                    borderJoinStyle: 'round',
                                    borderCapStyle: 'round',
                                    pointRadius: 0,
                                    tension: 0.4,
                                    cubicInterpolationMode: 'monotone',
                                    spanGaps: true
                                });
                            }
                        });
                    }
                });

                // (2026-07-21) 구 raw2 3열 패딩 제거 — 끝점을 왼쪽으로 당겨 라벨 자리를 만들던
                // 옛 미봉책이었으나, 끝값 라벨을 우축 바깥 공통 열로 뺀 뒤로는 불필요하고 오히려
                // 끝점이 우축에서 떨어지는 원인이었음. 이제 끝점이 우축(y1)에 접한다 (사용자 요청).



                var endLabelPlugin = {
                    id: 'cmbEndLabels',
                    afterDatasetsDraw: function(chart) {
                        var ctx = chart.ctx;
                        var entries = [];
                        chart.data.datasets.forEach(function(ds, i) {
                            if (ds._skipEndLabel) return;
                            var meta = chart.getDatasetMeta(i);
                            if (meta.hidden) return;
                            var lastIdx = -1;
                            for (var k = ds.data.length - 1; k >= 0; k--) {
                                if (ds.data[k] !== null && ds.data[k] !== undefined) { lastIdx = k; break; }
                            }
                            if (lastIdx < 0) return;
                            var last = meta.data[lastIdx];
                            if (!last) return;
                            var val = ds.data[lastIdx];
                            var label;
                            if (ds._isForeign) {
                                // 값에 단위 금지 — % 는 하단 범례 우측 단위 표기가 담당 (2026-08-02 이전)
                                var _bf = (window._cmbAxisBandRef || {})[ds.yAxisID || 'y'] || Math.abs(val);
                                label = fmtUniformFix(val, _bf);
                            } else if ((chart._cmbMode || 'pct') === 'pct') {
                                // pct 끝값도 밴드를 따른다 (종전: 항상 정수)
                                var _bp = (window._cmbAxisBandRef || {})[ds.yAxisID || 'y'] || Math.abs(val);
                                label = (val >= 0 ? '+' : '') + fmtUniformFix(val, _bp) + '%';
                            } else {
                                // 끝값 라벨: 정수부 4자리(>=1000)부터 소수 제외, 그 외 최대 2자리 (2026-07-16 사용자 확정)
                                // 끝값 = 숫자만 (억원 시리즈는 축 단위(조/억)로 환산 — 단위는 하단 범례 우측 표기가 담당)
                                var _f2 = (chart.canvas.id === 'cmbDynamicChart')
                                    ? ((window._cmbAxisConv || {})[ds.yAxisID || 'y'] || 1) : 1;
                                var _ax = chart.scales[ds.yAxisID || 'y'] || chart.scales.y;
                                var _m2 = ((chart.canvas.id === 'cmbDynamicChart' && window._cmbAxisBandRef)
                                    ? (window._cmbAxisBandRef[ds.yAxisID || 'y'] || 0)
                                    : Math.max(Math.abs(_ax.min || 0), Math.abs(_ax.max || 0))) / _f2;
                                label = fmtUniformFix(val / _f2, _m2);
                            }
                            entries.push({ dotX: last.x, origY: last.y, y: last.y, label: label, color: ds.borderColor });
                        });
                        if (entries.length === 0) return;
                        // y 오름차순 정렬 후 minGap 강제 (위→아래 충돌 시 아래로 밀기)
                        entries.sort(function(a, b) { return a.origY - b.origY; });
                        var minGap = 14;
                        for (var i = 1; i < entries.length; i++) {
                            if (entries[i].y - entries[i-1].y < minGap) {
                                entries[i].y = entries[i-1].y + minGap;
                            }
                        }
                        // 차트 영역 밖으로 밀려나갔으면 위쪽으로 역보정
                        var area = chart.chartArea;
                        if (area) {
                            var maxY = area.bottom - 4;
                            for (var j = entries.length - 1; j > 0; j--) {
                                if (entries[j].y > maxY) entries[j].y = maxY;
                                if (entries[j-1].y > entries[j].y - minGap) entries[j-1].y = entries[j].y - minGap;
                            }
                        }
                        // 라벨 x = 우측 축(y1 등) '바깥' 공통 열 (2026-07-21 사용자 확정) —
                        // 선은 우축에 접한 채 두고, 끝값 숫자는 축 눈금 오른쪽에 그려 눈금과 겹침 원천 차단.
                        var rightAxesW = 0;
                        Object.keys(chart.scales).forEach(function(sid) {
                            var sc = chart.scales[sid];
                            if (sid !== 'x' && sc && sc.options && sc.options.position === 'right' && sc.width) rightAxesW += sc.width;
                        });
                        var labelX = (area ? area.right : 0) + rightAxesW + 4;
                        ctx.save();
                        ctx.font = 'bold 15px sans-serif';
                        ctx.textBaseline = 'middle';
                        ctx.textAlign = 'left';
                        entries.forEach(function(e) {
                            // 리더선: 끝점→라벨 (계열색 55%, web-chart 표준) — 라벨이 축 바깥·충돌회피로
                            // 밀려도 어느 선의 값인지 읽히게. 이동량이 미미하면 생략.
                            if (labelX - e.dotX > 10 || Math.abs(e.y - e.origY) > 1) {
                                ctx.save();
                                ctx.globalAlpha = 0.6;
                                ctx.strokeStyle = e.color;
                                ctx.lineWidth = 2;   // 2026-07-21 사용자: 리더선 더 두껍게 (1→2)
                                ctx.beginPath();
                                ctx.moveTo(e.dotX + 4, e.origY);
                                ctx.lineTo(labelX - 3, e.y);
                                ctx.stroke();
                                ctx.restore();
                            }
                            ctx.fillStyle = e.color;
                            // 끝점 동그라미 3px — 라벨은 충돌 회피로 밀릴 수 있으니 실제 점(origY)에 표시
                            ctx.beginPath();
                            ctx.arc(e.dotX, e.origY, 3, 0, Math.PI * 2);
                            ctx.fill();
                            ctx.fillText(e.label, labelX, e.y);
                        });
                        ctx.restore();
                    }
                };

                // ── RoC² 서브패널 데이터 (범례 생성보다 앞) ──
                var rocDatasets = [];
                if (window.cmbRocOn) {
                    var _rocPos = {};
                    for (var _ri = 0; _ri < commonDates.length; _ri++) _rocPos[commonDates[_ri]] = _ri;
                    perSeries.forEach(function(s) {
                        if (!cmbRocAllow[s.name]) return;   // 판독성 미달 → 패널에 올리지 않는다
                        var R = cmbRocCompute(s.name);
                        if (!R) return;
                        var _ci = cmbClickOrder.indexOf(s.name);
                        var col = colorForIndex(_ci >= 0 ? _ci : 0);
                        // 기간말 관측일 인덱스에만 값을 얹고 spanGaps 로 잇는다 (표시 구간 밖은 자동 절단)
                        var proj = function(vals) {
                            var out = [], any = false;
                            for (var z = 0; z < commonDates.length; z++) out.push(null);
                            for (var k = 0; k < R.order.length; k++) {
                                var pi = _rocPos[R.buckets[R.order[k]].date];
                                if (pi === undefined) continue;
                                if (vals[k] === null || vals[k] === undefined) continue;
                                out[pi] = Math.round(vals[k] * 100) / 100;
                                any = true;
                            }
                            return any ? out : null;
                        };
                        var suffix = (perSeries.length > 1) ? (' ' + s.name) : '';
                        // ★패널은 RoC² 단독 (2026-07-29). RoC¹ 동반은 시도했다가 철회했다 —
                        //   외환보유액처럼 RoC¹(YoY ±15%)이 축을 잡으면 RoC²(±1%p)가 납작해지고,
                        //   RoC¹ 을 우축(y1)으로 빼면 메인 차트와의 x축 픽셀 정렬이 깨진다.
                        //   RoC¹ 계산은 RoC² 의 중간 산물이라 cmbRocCompute 안에 그대로 남아 있다.
                        var d2 = proj(R.roc2);
                        if (d2) rocDatasets.push({
                            label: 'RoC²' + suffix, data: d2,
                            borderColor: col, backgroundColor: 'transparent',
                            borderWidth: 2.6, borderJoinStyle: 'round', borderCapStyle: 'round',
                            pointRadius: 0, tension: 0.4,
                            cubicInterpolationMode: 'monotone', spanGaps: true, _rocUnit: '%p'
                        });
                    });
                }

                // ※범례 생성은 축 단위(yJo/y1Jo, _cmbAxisUnits) 계산 뒤로 이동 (2026-08-02) —
                //   항목에 단위를 인라인 표기(`고객예탁금(조원) +25.4%`)하려면 조원 승격 판정이 선행돼야 함.
                var legendEl = document.getElementById('cmbChartLegend');
                function cmbBuildLegend() {
                    var legendHTML = datasets.map(function(ds) {
                        var c = ds.borderColor;
                        // 설정 기간 변화율: pct 모드는 정규화된 값이라 last 자체가 변화율,
                        // raw 모드는 (last/first - 1)*100. 첫/마지막 non-null 값으로 계산.
                        var vals = ds.data.filter(function(v) { return v !== null && v !== undefined && !isNaN(v); });
                        var pctStr = '';
                        if (vals.length >= 2) {
                            var first = vals[0];
                            var last = vals[vals.length - 1];
                            var pct;
                            if (mode === 'pct') {
                                pct = last - first;
                            } else if (first !== 0) {
                                pct = (last / first - 1) * 100;
                            } else {
                                pct = 0;
                            }
                            pctStr = '<span>' + (pct >= 0 ? '+' : '') + fmtUniformFix(pct, Math.abs(pct)) + '%</span>';
                        }
                        // 축 단위를 시리즈명 바로 뒤에 표기 (2026-08-02 사용자 확정 — 축 상단 주석 폐지).
                        // MA 등 파생선은 cmbSeriesUnit 미등록이라 자동으로 단위 없음.
                        var unitStr = (mode !== 'pct') ? (cmbUnitLabel(ds.label, (ds.yAxisID === 'y1') ? y1Jo : yJo) || '') : '';
                        return '<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px;font-size:14px;">' +
                            '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + c + ';"></span>' +
                            ds.label + unitStr + pctStr + '</span>';
                    }).join('');
                    // 이격도는 기간 변화율 대신 마지막 값 표시 (100 기준 과열/침체 지표)
                    legendHTML += dispDatasets.map(function(ds) {
                        var vals = ds.data.filter(function(v) { return v !== null && v !== undefined && !isNaN(v); });
                        var lastStr = vals.length ? '<span>' + fmtUniformFix(vals[vals.length - 1], Math.abs(vals[vals.length - 1])) + '</span>' : '';
                        return '<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px;font-size:14px;">' +
                            '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + ds.borderColor + ';"></span>' +
                            ds.label + lastStr + '</span>';
                    }).join('');
                    // RoC 계열도 마지막 값 표기 (단위는 계열별 _rocUnit — RoC² 는 항상 %p)
                    legendHTML += rocDatasets.map(function(ds) {
                        var vals = ds.data.filter(function(v) { return v !== null && v !== undefined && !isNaN(v); });
                        var lastStr = vals.length ? '<span>' + fmtUniformFix(vals[vals.length - 1], Math.abs(vals[vals.length - 1])) + (ds._rocUnit || '') + '</span>' : '';
                        return '<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px;font-size:14px;">' +
                            '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + ds.borderColor + ';"></span>' +
                            ds.label + lastStr + '</span>';
                    }).join('');
                    if (legendEl) legendEl.innerHTML = legendHTML;
                }

                var _yMaxAbs = 0, _y1MaxAbs = 0, _yMinPos = Infinity, _y1MinPos = Infinity;
                var _yHasNonPos = false, _y1HasNonPos = false;   // 음수·0 포함 축은 로그축 성립 불가 → 선형 폴백
                datasets.forEach(function(ds) {
                    if (ds._skipEndLabel) return;
                    ds.data.forEach(function(v) {
                        if (v === null || v === undefined) return;
                        var a = Math.abs(v);
                        if (ds.yAxisID === 'y1') {
                            if (a > _y1MaxAbs) _y1MaxAbs = a;
                            if (v > 0 && v < _y1MinPos) _y1MinPos = v;
                            if (v <= 0) _y1HasNonPos = true;
                        } else {
                            if (a > _yMaxAbs) _yMaxAbs = a;
                            if (v > 0 && v < _yMinPos) _yMinPos = v;
                            if (v <= 0) _yHasNonPos = true;
                        }
                    });
                });
                var yJo = yEok && _yMaxAbs >= 10000, y1Jo = y1Eok && _y1MaxAbs >= 10000;
                // 시리즈별 단위 맵(CMB_SERIES_UNITS) 기반 축 주석 — 억원은 1조 이상 시 (조원) 승격
                function cmbUnitLabel(name, jo) {
                    var u = cmbSeriesUnit[name];
                    if (!u) return null;
                    if (u === '억원') return jo ? '(조원)' : '(억원)';
                    return '(' + u + ')';
                }
                // ★축 단위 주석은 perSeries 순서가 아니라 '실제 yAxisID 배정'에서 역산한다 (2026-07-28).
                //   isForeign 은 y 로 강제되므로 순서로 매기면 데이터 없는 y1 에 단위만 뜨는 어긋남이 났다.
                //   한 축에 서로 다른 단위가 얹히면 오표기 대신 생략한다.
                function cmbAxisUnitFor(ax, jo) {
                    var us = [];
                    _axAssign.forEach(function(a) {
                        if (a.ax !== ax) return;
                        var u = cmbUnitLabel(a.name, jo);
                        if (u && us.indexOf(u) < 0) us.push(u);
                    });
                    return us.length === 1 ? us[0] : null;
                }
                window._cmbAxisUnits = {
                    y: (mode !== 'pct') ? cmbAxisUnitFor('y', yJo) : null,
                    y1: (mode === 'raw2') ? cmbAxisUnitFor('y1', y1Jo) : null
                };
                cmbBuildLegend();   // 단위 인라인 표기 때문에 조원 승격(yJo/y1Jo) 판정 뒤에 렌더
                // 축별 표시 환산 계수 — MA 등 파생선도 같은 축 규칙을 타도록 축 기준으로 기록
                window._cmbAxisConv = { y: (yEok && yJo) ? 10000 : 1, y1: (y1Eok && y1Jo) ? 10000 : 1 };
                // ★자릿수 밴드 기준 = 축의 '최종 끝값' (2026-07-28 사용자 룰 변경. 종전 = 축 최대값).
                //   최대값 기준이면 기간에 큰 값이 한 번만 있어도 축 전체가 정수로 뭉개졌다
                //   (예: ETS 거래대금 끝값 67.56 인데 구간 최대 225.6 -> 68 로 표시).
                //   MA·이격도 파생선은 제외하고 축에 처음 배정된 주 시리즈의 마지막 실측값을 쓴다.
                var _yLastAbs = null, _y1LastAbs = null;
                datasets.forEach(function(ds) {
                    if (ds._skipEndLabel) return;
                    if (/^MA\d/.test(ds.label || '') || /^이격도/.test(ds.label || '')) return;
                    var _ax = (ds.yAxisID === 'y1') ? 'y1' : 'y';
                    if (_ax === 'y1' ? (_y1LastAbs !== null) : (_yLastAbs !== null)) return;
                    for (var _i = ds.data.length - 1; _i >= 0; _i--) {
                        var _v = ds.data[_i];
                        if (_v === null || _v === undefined || isNaN(_v)) continue;
                        if (_ax === 'y1') { _y1LastAbs = Math.abs(_v); } else { _yLastAbs = Math.abs(_v); }
                        break;
                    }
                });
                // 끝값을 못 찾으면(전 구간 결측) 종전대로 최대값으로 폴백
                window._cmbAxisBandRef = { y: (_yLastAbs === null ? _yMaxAbs : _yLastAbs),
                                           y1: (_y1LastAbs === null ? _y1MaxAbs : _y1LastAbs) };

                // 음수·0 포함 시리즈(괴리율 등)는 Log 자동 무시 — 로그축에 음수가 들어가면
                // 선·끝값 라벨이 축 하단으로 뭉개진다 (2026-08-02 실사고: 삼성전자 현선물 괴리율 -5.33).
                var yType = (mode === 'pct' || _yHasNonPos) ? 'linear' : (window.cmbLogOn === false ? 'linear' : 'logarithmic');
                var yLogPad = yType === 'logarithmic' ? cmbLogPad(_yMinPos, _yMaxAbs) : null;
                var y1Type = (window.cmbLogOn === false || _y1HasNonPos) ? 'linear' : 'logarithmic';
                var y1LogPad = y1Type === 'logarithmic' ? cmbLogPad(_y1MinPos, _y1MaxAbs) : null;
                var scalesConfig = {
                    x: { type: 'category', display: datasets.length > 0, ticks: { maxTicksLimit: 6, callback: function(val){ return window.cmbXLabel(this.getLabelForValue(val)); }, maxRotation: 0, font: { size: 15 }, color: '#000' }, grid: { color: '#eee', display: true }, border: { color: '#000', width: 2 } },
                    y: {
                        type: yType,
                        position: 'left',
                        grace: '8%',
                        min: yLogPad ? yLogPad.min : undefined,
                        max: yLogPad ? yLogPad.max : undefined,
                        afterBuildTicks: cmbEnsureBoundTicks,
                        ticks: { maxTicksLimit: 8, autoSkip: false, callback: function(v){ return mode === 'pct' ? v + '%' : cmbTickFmt(v, this, yEok && yJo); }, font: { size: 15 }, color: '#000' },
                        grid: { color: '#eee' },
                        border: { color: '#000', width: 2 }
                    }
                };
                if (mode === 'raw2' && datasets.some(function(ds){ return ds.yAxisID === 'y1'; })) {
                    scalesConfig.y1 = {
                        type: y1Type,
                        position: 'right',
                        grace: '8%',
                        min: y1LogPad ? y1LogPad.min : undefined,
                        max: y1LogPad ? y1LogPad.max : undefined,
                        afterBuildTicks: cmbEnsureBoundTicks,
                        ticks: { maxTicksLimit: 8, autoSkip: false, callback: function(v){ return cmbTickFmt(v, this, y1Eok && y1Jo); }, font: { size: 15 }, color: '#000' },
                        grid: { drawOnChartArea: false },
                        border: { color: '#000', width: 2 }
                    };
                }

                // 툴팁도 눈금·끝값과 같은 밴드(_cmbAxisBandRef)를 따른다 (2026-07-28).
                // ★억원 계열의 전체형(`34조 2,669억`)만 사용자 확정 예외 — 나머지는 값에 단위를 붙이지 않는다.
                var tooltipLabel = function(ctx) {
                    if (ctx.parsed.y === null || ctx.parsed.y === undefined) return ctx.dataset.label + ': -';
                    var _tax = ctx.dataset.yAxisID || 'y';
                    var _tb = (window._cmbAxisBandRef || {})[_tax] || 0;
                    if (mode === 'pct') return ctx.dataset.label + ': ' + fmtUniformFix(ctx.parsed.y, _tb) + '%';
                    var _eokAx = _tax === 'y1' ? y1Eok : yEok;
                    if (_eokAx) return ctx.dataset.label + ': ' + fmtEokFull(ctx.parsed.y);
                    var _tf = (window._cmbAxisConv || {})[_tax] || 1;
                    return ctx.dataset.label + ': ' + fmtUniformFix(ctx.parsed.y / _tf, _tb / _tf);
                };

                // 우측 end-label(예: 예탁금 1,199,264) 잘림 방지 — 최장 라벨 폭만큼 오른쪽 패딩 동적 확보
                var _measCtx = document.createElement('canvas').getContext('2d');
                _measCtx.font = 'bold 15px sans-serif';
                var _maxLabelW = 0;
                datasets.forEach(function(ds) {
                    if (ds._skipEndLabel) return;
                    var lv = null;
                    for (var _k = ds.data.length - 1; _k >= 0; _k--) { if (ds.data[_k] !== null && ds.data[_k] !== undefined) { lv = ds.data[_k]; break; } }
                    if (lv === null) return;
                    var _lbl;
                    if (ds._isForeign) { _lbl = lv.toFixed(1) + '%'; }
                    else if (mode === 'pct') { var _r = Math.sign(lv) * Math.round(Math.abs(lv)); _lbl = (_r >= 0 ? '+' : '') + _r + '%'; }
                    else { var _mf = (ds.yAxisID === 'y1' ? (y1Eok && y1Jo) : (yEok && yJo)) ? 10000 : 1; _lbl = fmtUniformFix(lv / _mf, (ds.yAxisID === 'y1' ? _y1MaxAbs : _yMaxAbs) / _mf); }
                    var _w = _measCtx.measureText(_lbl).width;
                    if (_w > _maxLabelW) _maxLabelW = _w;
                });
                var _rightPad = Math.max(60, Math.ceil(_maxLabelW) + 12);

                if (cmbChart) {
                    // 재사용: 인스턴스 유지하고 데이터/축/툴팁만 교체 (destroy+new 멈칫 제거)
                    cmbChart.options.layout.padding.right = _rightPad;
                    cmbChart.options.layout.padding.top = 6;
                    cmbChart.data.labels = commonDates;
                    cmbChart.data.datasets = datasets;
                    // scales 전체 교체 — 이전 raw2의 y1축 잔재 제거 후 새 구성 적용
                    var _sc = cmbChart.options.scales;
                    Object.keys(_sc).forEach(function(k){ delete _sc[k]; });
                    Object.keys(scalesConfig).forEach(function(k){ _sc[k] = scalesConfig[k]; });
                    // tooltip 콜백은 mode를 캡처하므로 매번 교체
                    cmbChart.options.plugins.tooltip.callbacks.label = tooltipLabel;
                    cmbChart._cmbTipLabel = tooltipLabel;   // 클릭 핀 카드가 같은 포맷 사용
                    cmbChart._cmbMode = mode;   // update 전 대입 — 첫 draw가 endLabel에서 읽음
                    cmbChart.update('none');
                } else {
                    cmbChart = new Chart(document.getElementById('cmbDynamicChart'), {
                        type: 'line',
                        data: { labels: commonDates, datasets: datasets },
                        plugins: [endLabelPlugin, cmbCrosshairPlugin, cmbPinPlugin],
                        options: {
                            responsive: true, maintainAspectRatio: false,
                            devicePixelRatio: 2 * (window.devicePixelRatio || 1),
                            layout: { padding: { right: _rightPad, top: 6 } },
                            interaction: { mode: 'index', intersect: false },
                            plugins: {
                                legend: { display: false },
                                // animation:false — 동기 툴팁이 draw()만으로 위치 갱신되도록 (애니메이션 속성이면 제자리에 멈춤)
                                // 글씨 +1px (12→13, 2026-07-21 사용자 확정 — 클릭 핀 카드와 동일 크기)
                                // 카드 제목 = 원본 날짜(YYYY-MM-DD) — 축약(YY/MM)은 x축 눈금 전용 (2026-08-02 사용자 확정)
                                tooltip: { animation: false, titleFont: { size: 13 }, bodyFont: { size: 13 }, callbacks: { title: function(cs){ return cs.length ? String(cs[0].label) : ''; }, label: tooltipLabel } }
                            },
                            scales: scalesConfig
                        }
                    });
                    cmbChart._cmbMode = mode;   // 생성자 첫 draw는 mode 미설정으로 끝값이 +N% 오표기 -> 재렌더로 교정
                    cmbChart._cmbTipLabel = tooltipLabel;   // 클릭 핀 카드가 같은 포맷 사용
                    cmbChart.update('none');
                }

                // 이격도 서브패널 — 100 기준선 점선 + 메인 y축 폭에 맞춰 x축 정렬
                var dispPanel = document.getElementById('cmbDispPanel');
                if (dispPanel) {
                    if (dispDatasets.length > 0) {
                        dispPanel.style.display = '';
                        var mainYWidth = (cmbChart.scales && cmbChart.scales.y) ? cmbChart.scales.y.width : 0;
                        if (cmbDispChart) {
                            // 재사용: 데이터·y축폭만 갱신
                            cmbDispChart.data.labels = commonDates;
                            cmbDispChart.data.datasets = dispDatasets;
                            cmbDispChart.options.scales.y.afterFit = function(scale) { if (mainYWidth > 0) scale.width = mainYWidth; };
                            cmbDispChart.update('none');
                        } else {
                            var disp100Plugin = {
                                id: 'cmbDisp100',
                                beforeDatasetsDraw: function(chart) {
                                    var ys = chart.scales.y;
                                    var area = chart.chartArea;
                                    if (!ys || !area) return;
                                    var y100 = ys.getPixelForValue(100);
                                    if (y100 < area.top || y100 > area.bottom) return;
                                    var c = chart.ctx;
                                    c.save();
                                    c.strokeStyle = '#999';
                                    c.setLineDash([4, 4]);
                                    c.lineWidth = 1;
                                    c.beginPath();
                                    c.moveTo(area.left, y100);
                                    c.lineTo(area.right, y100);
                                    c.stroke();
                                    c.restore();
                                }
                            };
                            // 이격도 고점/저점: 극값 지점에서 오른쪽 끝까지 수평 보조선(점선) + 값 라벨
                            var dispHiLoPlugin = {
                                id: 'cmbDispHiLo',
                                afterDatasetsDraw: function(chart) {
                                    var area = chart.chartArea, ys = chart.scales.y, ctx = chart.ctx;
                                    if (!area || !ys) return;
                                    chart.data.datasets.forEach(function(ds, di) {
                                        var meta = chart.getDatasetMeta(di);
                                        if (meta.hidden) return;
                                        var maxV = -Infinity, minV = Infinity, maxI = -1, minI = -1;
                                        for (var i = 0; i < ds.data.length; i++) {
                                            var v = ds.data[i];
                                            if (v === null || v === undefined || isNaN(v)) continue;
                                            if (v > maxV) { maxV = v; maxI = i; }
                                            if (v < minV) { minV = v; minI = i; }
                                        }
                                        if (maxI < 0) return;
                                        [{ v: maxV, i: maxI, up: true }, { v: minV, i: minI, up: false }].forEach(function(pt) {
                                            var p = meta.data[pt.i];
                                            if (!p) return;
                                            var py = ys.getPixelForValue(pt.v);
                                            ctx.save();
                                            ctx.strokeStyle = ds.borderColor;
                                            ctx.globalAlpha = 0.55;
                                            ctx.setLineDash([4, 3]);
                                            ctx.lineWidth = 1;
                                            ctx.beginPath();
                                            ctx.moveTo(p.x, py);
                                            ctx.lineTo(area.right, py);
                                            ctx.stroke();
                                            ctx.setLineDash([]);
                                            ctx.globalAlpha = 1;
                                            ctx.fillStyle = ds.borderColor;
                                            ctx.beginPath();
                                            ctx.arc(p.x, py, 2.5, 0, 2 * Math.PI);
                                            ctx.fill();
                                            ctx.font = 'bold 11px sans-serif';
                                            ctx.textAlign = 'left';
                                            ctx.textBaseline = pt.up ? 'bottom' : 'top';
                                            ctx.fillText(pt.v.toFixed(1), area.right + 4, py + (pt.up ? -2 : 2));
                                            ctx.restore();
                                        });
                                    });
                                }
                            };
                            cmbDispChart = new Chart(document.getElementById('cmbDispChart'), {
                                type: 'line',
                                data: { labels: commonDates, datasets: dispDatasets },
                                plugins: [endLabelPlugin, disp100Plugin, dispHiLoPlugin, cmbCrosshairPlugin],
                                options: {
                                    responsive: true, maintainAspectRatio: false,
                                    devicePixelRatio: 2 * (window.devicePixelRatio || 1),
                                    layout: { padding: { right: 60 } },
                                    interaction: { mode: 'index', intersect: false },
                                    plugins: {
                                        legend: { display: false },
                                        tooltip: { animation: false, callbacks: { label: function(ctx) {
                                            if (ctx.parsed.y === null || ctx.parsed.y === undefined) return ctx.dataset.label + ': -';
                                            return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(1);
                                        } } }
                                    },
                                    scales: {
                                        x: { type: 'category', ticks: { maxTicksLimit: 6, callback: function(val){ return window.cmbXLabel(this.getLabelForValue(val)); }, maxRotation: 0, font: { size: 15 }, color: '#000' }, grid: { color: '#eee', display: true }, border: { color: '#000', width: 2 } },
                                        y: {
                                            type: 'linear',
                                            position: 'left',
                                            grace: '8%',
                        afterBuildTicks: cmbEnsureBoundTicks,
                                            afterFit: function(scale) { if (mainYWidth > 0) scale.width = mainYWidth; },
                                            ticks: { maxTicksLimit: 8, autoSkip: false, callback: function(v){ return cmbTickFmt(v, this, false); }, font: { size: 15 }, color: '#000' },
                                            grid: { color: '#eee' },
                                            border: { color: '#000', width: 2 }
                                        }
                                    }
                                }
                            });
                            cmbDispChart._cmbMode = 'raw1';   // 생성자 첫 draw 전 대입 + 재렌더 (B와 동일 사유)
                            cmbDispChart.update('none');
                        }
                    } else {
                        dispPanel.style.display = 'none';
                        if (cmbDispChart) { cmbDispChart.destroy(); cmbDispChart = null; }
                    }
                }

                // ── RoC² 서브패널 — 0 기준선 점선 + 메인 y축 폭에 맞춰 x축 정렬 ──
                //    (이격도 패널과 동일 규격: 자기 x축 보유, 크로스헤어 동기, Download 합성 대상)
                var rocPanel = document.getElementById('cmbRocPanel');
                if (rocPanel) {
                    if (rocDatasets.length > 0) {
                        rocPanel.style.display = '';
                        var rocYWidth = (cmbChart.scales && cmbChart.scales.y) ? cmbChart.scales.y.width : 0;
                        var rocTip = function(ctx) {
                            if (ctx.parsed.y === null || ctx.parsed.y === undefined) return ctx.dataset.label + ': -';
                            return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(2) + (ctx.dataset._rocUnit || '%p');
                        };
                        if (cmbRocChart) {
                            cmbRocChart.data.labels = commonDates;
                            cmbRocChart.data.datasets = rocDatasets;
                            cmbRocChart.options.plugins.tooltip.callbacks.label = rocTip;
                            cmbRocChart._cmbTipLabel = rocTip;
                            cmbRocChart.options.scales.y.afterFit = function(scale) { if (rocYWidth > 0) scale.width = rocYWidth; };
                            cmbRocChart.update('none');
                        } else {
                            var roc0Plugin = {
                                id: 'cmbRoc0',
                                beforeDatasetsDraw: function(chart) {
                                    var ys = chart.scales.y, area = chart.chartArea;
                                    if (!ys || !area) return;
                                    var y0 = ys.getPixelForValue(0);
                                    if (y0 < area.top || y0 > area.bottom) return;
                                    var c = chart.ctx;
                                    c.save();
                                    c.strokeStyle = '#666';
                                    c.setLineDash([4, 4]);
                                    c.lineWidth = 1.2;
                                    c.beginPath();
                                    c.moveTo(area.left, y0);
                                    c.lineTo(area.right, y0);
                                    c.stroke();
                                    c.restore();
                                }
                            };
                            cmbRocChart = new Chart(document.getElementById('cmbRocChart'), {
                                type: 'line',
                                data: { labels: commonDates, datasets: rocDatasets },
                                plugins: [endLabelPlugin, roc0Plugin, cmbCrosshairPlugin, cmbAxisUnitPlugin],
                                options: {
                                    responsive: true, maintainAspectRatio: false,
                                    devicePixelRatio: 2 * (window.devicePixelRatio || 1),
                                    // top = 축 위 단위 주석 자리. 패널(h=200)이라 메인(34)보다 얕게 준다.
                                    layout: { padding: { right: 60, top: 24 } },
                                    interaction: { mode: 'index', intersect: false },
                                    plugins: {
                                        legend: { display: false },
                                        tooltip: { animation: false, titleFont: { size: 13 }, bodyFont: { size: 13 },
                                            callbacks: {
                                                title: function(cs){ return cs.length ? String(cs[0].label) : ''; },
                                                label: rocTip
                                            } }
                                    },
                                    scales: {
                                        x: { type: 'category', ticks: { maxTicksLimit: 6, callback: function(val){ return window.cmbXLabel(this.getLabelForValue(val)); }, maxRotation: 0, font: { size: 15 }, color: '#000' }, grid: { color: '#eee', display: true }, border: { color: '#000', width: 2 } },
                                        y: {
                                            type: 'linear',
                                            position: 'left',
                                            grace: '8%',
                                            // ★0 을 항상 축 범위에 포함 (2026-07-30 사용자 요청) — RoC² 는 부호가
                                            //   곧 가속/감속이라 0선이 보여야 둔화를 판독할 수 있다. 종전엔 값이
                                            //   전부 한쪽 부호면 0 이 범위 밖으로 나가 roc0Plugin 이 0선 그리기를
                                            //   건너뛰었다(area.top~bottom 밖이면 return).
                                            beginAtZero: true,
                                            afterBuildTicks: cmbEnsureBoundTicks,
                                            afterFit: function(scale) { if (rocYWidth > 0) scale.width = rocYWidth; },
                                            // ★눈금은 숫자만. 단위 '%p' 는 축 최상단 위에 1회 표기한다(아래 _cmbAxisUnits).
                                            //   y축 폭은 메인 차트와의 픽셀 정렬 때문에 afterFit 으로 고정돼 있어서,
                                            //   눈금에 단위를 붙이면 폭을 넘어가 글씨가 잘렸다(2026-07-30 사용자 지적).
                                            //   자릿수는 사이트 표준 fmtByMag(|v|<10 둘째, 10~999 첫째, 1000+ 정수).
                                            ticks: { maxTicksLimit: 6, autoSkip: false, callback: function(v){ return fmtByMag(v); }, font: { size: 15 }, color: '#000' },
                                            grid: { color: '#eee' },
                                            border: { color: '#000', width: 2 }
                                        }
                                    }
                                }
                            });
                            cmbRocChart._cmbMode = 'raw1';   // 끝값 라벨 = 원값 포맷 (이격도 패널과 동일)
                            cmbRocChart._cmbTipLabel = rocTip;
                            // RoC² 는 정의상 항상 %p — 축 위에 1회 표기(눈금엔 숫자만)
                            cmbRocChart._cmbAxisUnits = { y: '(%p)', y1: null };
                            cmbRocChart._cmbAxisUnitDy = 10;   // 패널은 여백이 얕아 메인(20)보다 가깝게
                            cmbRocChart.update('none');
                        }
                    } else {
                        rocPanel.style.display = 'none';
                        if (cmbRocChart) { cmbRocChart.destroy(); cmbRocChart = null; }
                    }
                    // 선택 시리즈로 RoC² 가 안 나오면 패널이 조용히 사라져 고장으로 읽힌다.
                    // 버튼을 흐리게 + native title 로 '실제 사유'를 표시한다 (cmbRocDiag).
                    var rocBtn = document.getElementById('cmbRocBtn');
                    if (rocBtn) {
                        var lack = !!window.cmbRocOn && rocDatasets.length === 0;
                        rocBtn.style.opacity = lack ? '0.4' : '';
                        var _why = '';
                        if (lack) {
                            var _f = (window.cmbRocFreq === 'W') ? 'W' : 'M';
                            for (var _di = 0; _di < cmbClickOrder.length; _di++) {
                                var _d = cmbRocDiag(cmbClickOrder[_di], _f);
                                if (!_d.ok) { _why = cmbClickOrder[_di] + ' — ' + _d.why; break; }
                            }
                            if (!_why) _why = 'RoC\u00b2 를 계산할 수 없습니다';
                        } else if (cmbClickOrder.length) {
                            // 정상 표시 중이면 그 시리즈의 판독성 점수를 알려준다(과신 방지)
                            var _a = cmbRocAllow[cmbClickOrder[0]];
                            if (_a) {
                                var _wk = (window.cmbRocFreq === 'W');
                                var _r = _wk ? _a[2] : _a[0], _c = _wk ? _a[3] : _a[1];
                                if (_r !== null && _r !== undefined) {
                                    _why = '판독성: 부호 유지 평균 ' + _r + (_wk ? '주' : '개월')
                                         + ' · 자기상관 ' + _c + ' (무작위면 2.0 / 0)';
                                }
                            }
                        }
                        rocBtn.title = _why;
                    }
                    cmbSyncRocFreqAvail();
                }
            }

            window.toggleCmbSeries = function(el, ev) {
                var multi = ev && (ev.shiftKey || ev.ctrlKey || ev.metaKey);
                if (multi) {
                    // 다중 선택 모드: 기존 동작 (토글)
                    el.classList.toggle('active');
                } else {
                    // 단일 선택 모드: 다른 항목 모두 해제 + 현재만 active
                    var key = el.getAttribute('data-series');
                    document.querySelectorAll('.cmb-chart-item.active').forEach(function(x) {
                        if (x !== el) x.classList.remove('active');
                    });
                    el.classList.add('active');
                    cmbClickOrder = [key];
                }
                cmbAutoRangePending = true;   // 선택 변경 → M/Y 시리즈 최소 12관측 자동 확장
                buildCmbChart();
            };
            window.toggleCmbMA = function(slot, el) {
                maActive[slot] = !maActive[slot];
                el.classList.toggle('active', maActive[slot]);
                buildCmbChart();
            };
            window.toggleCmbDisp = function(slot, el) {
                dispActive[slot] = !dispActive[slot];
                el.classList.toggle('active', dispActive[slot]);
                buildCmbChart();
            };
            window.cmbToggleRoc = function(el) {
                window.cmbRocOn = !window.cmbRocOn;
                el.classList.toggle('active', !!window.cmbRocOn);
                cmbSyncRocUI();
                buildCmbChart();
            };
            window.cmbToggleRocSmooth = function(el) {
                window.cmbRocSmooth = (window.cmbRocSmooth === false);
                el.classList.toggle('active', window.cmbRocSmooth !== false);
                buildCmbChart();
            };
            window.cmbSetRocFreq = function(f) {
                // 불가한 주기로는 전환하지 않는다 — 전환 직후 빈 패널로 죽는 상태를 만들지 않기 위해.
                if (cmbClickOrder.length) {
                    var any = false;
                    for (var i = 0; i < cmbClickOrder.length; i++) {
                        if (cmbRocDiag(cmbClickOrder[i], f).ok) { any = true; break; }
                    }
                    if (!any) return;
                }
                window.cmbRocFreq = f;
                cmbSyncRocUI();
                buildCmbChart();
            };
            function cmbSyncRocUI() {
                var opts = document.getElementById('cmbRocOpts');
                if (opts) opts.style.display = window.cmbRocOn ? 'inline-flex' : 'none';
                var f = window.cmbRocFreq || 'M';
                var bm = document.getElementById('cmbRocFreqM');
                var bw = document.getElementById('cmbRocFreqW');
                if (bm) bm.classList.toggle('active', f === 'M');
                if (bw) bw.classList.toggle('active', f === 'W');
            }
            // ★정식 배선 (2026-07-30, 사용자 승인) — `?roc2=1` 테스트 게이트 제거. 버튼 상시 노출.
            //   게이트 시절: /[?&]roc2=1/ 이 아니면 btn.style.display='none'. 되돌릴 일이 생기면
            //   그 분기만 복원하면 된다(미사용이던 window._cmbRocEnabled 는 함께 제거).
            (function() {
                cmbSyncRocUI();
            })();
            window.updateCmbChart = buildCmbChart;
            window.clearCmbSelections = function() {
                document.querySelectorAll('.cmb-chart-item.active').forEach(function(el){ el.classList.remove('active'); });
                cmbClickOrder = [];
                buildCmbChart();
            };

            // 화살표 위/아래 키로 시리즈 단일 선택 네비 (input 포커스 시 무시)
            document.addEventListener('keydown', function(e) {
                if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
                var ae = document.activeElement;
                var tag = ae && ae.tagName;
                if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (ae && ae.isContentEditable)) return;
                var items = Array.prototype.slice.call(document.querySelectorAll('.cmb-chart-item'))
                    .filter(function(el) {
                        var row = el.closest('tr');
                        return !row || row.style.display !== 'none';  // 필터 통과(보이는) 행만
                    });
                if (items.length === 0) return;
                e.preventDefault();
                var activeIdx = -1;
                for (var i = 0; i < items.length; i++) {
                    if (items[i].classList.contains('active')) { activeIdx = i; break; }
                }
                var nextIdx;
                if (activeIdx < 0) {
                    nextIdx = (e.key === 'ArrowDown') ? 0 : items.length - 1;
                } else {
                    nextIdx = activeIdx + (e.key === 'ArrowDown' ? 1 : -1);
                    if (nextIdx < 0) nextIdx = items.length - 1;
                    if (nextIdx >= items.length) nextIdx = 0;
                }
                document.querySelectorAll('.cmb-chart-item.active').forEach(function(el) { el.classList.remove('active'); });
                items[nextIdx].classList.add('active');
                cmbClickOrder = [items[nextIdx].getAttribute('data-series')];
                items[nextIdx].scrollIntoView({ block: 'nearest' });
                buildCmbChart();
            });

            cmbPaintStars();
            cmbApplyFilters();
            updateCmbSortArrows();
            buildCmbChart();
        })();
        </script>
        """
