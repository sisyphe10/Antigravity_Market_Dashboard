// aoe_chart.js — AoE 공용 차트 코어 (v0.2.0, P1 착수 2026-08-02 · P2b 렌더 프레임 편입)
// 정본: chart_core/dist/aoe_chart.js — 양식 수정은 반드시 이 파일에서.
// 소비: create_dashboard.py 가 빌드타임에 <script> 인라인 임베드 (manifest sha 검증).
// 중복 임베드 가드: 각 블록의 typeof 체크 (한 페이지에 여러 번 들어가도 1회만 등록).

        if (typeof window.downloadChartImage !== 'function') {
            // opts.copy=true 면 파일 저장 대신 클립보드 복사 (2026-08-02, copyChartImage 경유)
            window.downloadChartImage = function(canvasId, baseName, legendId, extraCanvasId, opts) {
                var src = document.getElementById(canvasId);
                if (!src) { console.warn('canvas not found:', canvasId); return; }
                // ── 고해상도 저장: 클릭 순간에만 차트를 DL_DPR로 재렌더 (화면 해상도는 그대로) ──
                var DL_DPR = 4;
                var _getCh = (window.Chart && Chart.getChart) ? function(t){ return Chart.getChart(t); } : function(){ return null; };
                var _mainChart = _getCh(canvasId);
                // 보조 캔버스 다중 지원 (이격도 + RoC², 2026-07-29). 문자열 1개도 그대로 허용.
                var _extraIds = extraCanvasId ? (Array.isArray(extraCanvasId) ? extraCanvasId : [extraCanvasId]) : [];
                var _visibleExtras = function() {
                    return _extraIds.map(function(id){ return document.getElementById(id); })
                        .filter(function(el){ return el && el.offsetParent !== null && el.width; });
                };
                var _extraCharts = _visibleExtras().map(_getCh).filter(Boolean);
                var _prevMainDpr = _mainChart ? (_mainChart.options.devicePixelRatio || (window.devicePixelRatio || 1)) : null;
                var _prevExtraDprs = _extraCharts.map(function(c){ return c.options.devicePixelRatio || (window.devicePixelRatio || 1); });
                if (_mainChart) { _mainChart.options.devicePixelRatio = DL_DPR; _mainChart.resize(); _mainChart.draw(); }
                _extraCharts.forEach(function(c){ c.options.devicePixelRatio = DL_DPR; c.resize(); c.draw(); });
                try {
                var w = src.width, h = src.height;
                var scale = src.clientWidth ? (w / src.clientWidth) : 1;

                // 보조 캔버스(이격도·RoC² 서브패널) — 보이는 것만 메인 아래에 순서대로 세로 합성
                var _extras = _visibleExtras();
                var extraH = 0;
                var _extraHs = _extras.map(function(el){
                    var hh = Math.round(el.height * (w / el.width));
                    extraH += hh;
                    return hh;
                });

                // 하단 범례 항목 수집 (컬러닷 + 라벨)
                var legendItems = [];
                var legendSuffix = '';
                if (legendId) {
                    var legendEl = document.getElementById(legendId);
                    if (legendEl) {
                        legendEl.querySelectorAll(':scope > span').forEach(function(span) {
                            var dot = span.querySelector('span[style*="background"]');
                            var text = (span.textContent || '').trim();
                            if (dot) {
                                legendItems.push({ color: dot.style.background || dot.style.backgroundColor || '#888', text: text });
                            } else if (text) {
                                legendSuffix = text;  // 예: "/ USD"
                            }
                        });
                    }
                }

                var legendH = legendItems.length ? Math.round(44 * scale) : 0;
                var tmp = document.createElement('canvas');
                tmp.width = w; tmp.height = h + extraH + legendH;
                var ctx = tmp.getContext('2d');
                ctx.fillStyle = '#ffffff';
                ctx.fillRect(0, 0, tmp.width, tmp.height);
                ctx.drawImage(src, 0, 0);
                var _yOff = h;
                _extras.forEach(function(el, i) { ctx.drawImage(el, 0, _yOff, w, _extraHs[i]); _yOff += _extraHs[i]; });

                if (legendItems.length) {
                    var fontPx = Math.round(13 * scale);
                    var fontItem = fontPx + "px Pretendard, system-ui, sans-serif";
                    var fontSuffix = '600 ' + fontPx + "px Pretendard, system-ui, sans-serif";
                    ctx.textBaseline = 'middle';
                    var dotR = Math.round(5 * scale);
                    var gapDotText = Math.round(7 * scale);
                    var gapItems = Math.round(18 * scale);
                    var suffixGap = Math.round(6 * scale);
                    var totalW = 0;
                    ctx.font = fontItem;
                    legendItems.forEach(function(it, i) {
                        totalW += dotR * 2 + gapDotText + ctx.measureText(it.text).width;
                        if (i < legendItems.length - 1) totalW += gapItems;
                    });
                    if (legendSuffix) { ctx.font = fontSuffix; totalW += suffixGap + ctx.measureText(legendSuffix).width; }
                    var x = Math.max(Math.round((w - totalW) / 2), Math.round(10 * scale));
                    var y = h + extraH + Math.round(legendH / 2);
                    ctx.font = fontItem;
                    legendItems.forEach(function(it, i) {
                        ctx.beginPath();
                        ctx.fillStyle = it.color;
                        ctx.arc(x + dotR, y, dotR, 0, Math.PI * 2);
                        ctx.fill();
                        x += dotR * 2 + gapDotText;
                        ctx.fillStyle = '#222';
                        ctx.fillText(it.text, x, y);
                        x += ctx.measureText(it.text).width;
                        if (i < legendItems.length - 1) x += gapItems;
                    });
                    if (legendSuffix) {
                        x += suffixGap;
                        ctx.font = fontSuffix;
                        ctx.fillStyle = '#555';
                        ctx.fillText(legendSuffix, x, y);
                    }
                }
                var d = new Date();
                var pad = function(n){return n<10?'0'+n:''+n;};
                var stamp = d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate());
                // 파일명에 선택 시리즈명 포함 (2026-08-02 사용자 확정) — MA·이격도·RoC 파생선 제외,
                // 4개 이상이면 앞 3개 + '외N'. 파일명 금지문자는 '-' 치환.
                var _names = [];
                if (_mainChart) {
                    _mainChart.data.datasets.forEach(function(ds) {
                        var l = ds.label || '';
                        if (!l || ds._skipEndLabel) return;
                        if (/^MA\d/.test(l) || /^이격도/.test(l) || /^RoC/.test(l)) return;
                        if (_names.indexOf(l) < 0) _names.push(l);
                    });
                }
                // 접두어(AoE_Data 등) 없이 시리즈명부터 시작 (2026-08-02 사용자 확정) — 없을 때만 baseName 폴백
                var _namePart = '';
                if (_names.length) {
                    var _shown = _names.slice(0, 3).join('·');
                    if (_names.length > 3) _shown += ' 외' + (_names.length - 3);
                    _namePart = _shown.replace(/[\\/:*?"<>|]/g, '-');
                }
                var _dataUrl = tmp.toDataURL('image/png');   // sync — async toBlob는 user activation 상실
                if (opts && opts.copy) {
                    // 클립보드 복사 — dataURL을 동기로 Blob 변환 후 write (클릭 제스처 유지)
                    var _bin = atob(_dataUrl.split(',')[1]);
                    var _u8 = new Uint8Array(_bin.length);
                    for (var _bi = 0; _bi < _bin.length; _bi++) _u8[_bi] = _bin.charCodeAt(_bi);
                    var _pr = navigator.clipboard.write([new ClipboardItem({ 'image/png': new Blob([_u8], { type: 'image/png' }) })]);
                    var _btn = opts.btn;
                    if (_btn) {
                        var _orig = _btn.textContent;
                        // 되돌림 타이머는 promise 확정 후에 시작 — 확정 전에 먼저 돌면 피드백이 안 보인다
                        _pr.then(function(){ _btn.textContent = 'Copied ✓'; }, function(e){ console.warn('clipboard copy failed:', e); _btn.textContent = 'Copy failed'; })
                           .then(function(){ setTimeout(function(){ _btn.textContent = _orig; }, 1500); });
                    }
                } else {
                    var a = document.createElement('a');
                    a.href = _dataUrl;
                    a.download = (_namePart || baseName || 'chart') + '_' + stamp + '.png';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                }
                } finally {
                    if (_mainChart) { _mainChart.options.devicePixelRatio = _prevMainDpr; _mainChart.resize(); _mainChart.draw(); }
                    _extraCharts.forEach(function(c, i) { c.options.devicePixelRatio = _prevExtraDprs[i]; c.resize(); c.draw(); });
                }
            };
            window.copyChartImage = function(canvasId, legendId, extraCanvasId, btn) {
                window.downloadChartImage(canvasId, null, legendId, extraCanvasId, { copy: true, btn: btn });
            };
        }

// ── cmb(DATA) 양식 공용 블록 (P1b 이동 2026-08-02) — 포맷터·눈금 정책·축단위 플러그인 ──
// 원래 DATA IIFE 클로저 내부였으나 순수/자립 블록이라 전역 승격 (클로저 코드는 스코프 체인으로 참조)
            // 자릿수 원칙 (2026-07-16 사용자 확정): |v|<10 소수 둘째, 10~999 첫째, 1000+ 정수
            function fmtByMag(v) {
                if (v === null || v === undefined) return '-';
                var a = Math.abs(v);
                return Number(v).toLocaleString(undefined, { maximumFractionDigits: a < 10 ? 2 : (a < 1000 ? 1 : 0) });
            }

            function fmtUniformFix(v, maxAbs) {   // 끝값용: 축 자릿수로 패딩 (84 -> 84.0)
                if (v === null || v === undefined) return '-';
                var dp = maxAbs < 10 ? 2 : (maxAbs < 100 ? 1 : 0);   // 일의자리 2dp·십의자리 1dp·백의자리+ 정수
                return Number(v).toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });
            }

            function cmbTickFmt(v, ax, jo) {
                var f = jo ? 10000 : 1;
                var m;
                // ★밴드 기준 = 차트 인스턴스 _cmbAxisBandRef (cmbRenderCharts 가 메인 차트에만 부착).
                //   P3 다중 패밀리 공존을 위해 window 전역·canvas id 판별 제거 — 서브패널은
                //   인스턴스에 밴드가 없으므로 종전대로 축 최대값 기준(else)으로 간다.
                var _bandRef = ax.chart && ax.chart._cmbAxisBandRef;   // (P7: legacy window 폴백 제거)
                if (_bandRef)
                    m = (_bandRef[ax.id] || Math.abs(ax.max || 0)) / f;
                else
                    m = Math.max(Math.abs(ax.min || 0), Math.abs(ax.max || 0)) / f;
                var _vv = v / f;
                // 로그 축에서 대역이 넓으면 큰 눈금에 소수가 붙는다 → 1,000 이상은 정수 (2026-07-28)
                return fmtUniform(_vv, Math.abs(_vv) >= 1000 ? 1000 : m);
            }

            function fmtEokFull(v) {   // 끝값·툴팁용: 1,537조 5,713억
                var a = Math.abs(v), sgn = v < 0 ? '-' : '';
                if (a >= 10000) {
                    var jo = Math.floor(a / 10000), eok = Math.round(a % 10000);
                    return sgn + jo.toLocaleString() + '조' + (eok ? ' ' + eok.toLocaleString() + '억' : '');
                }
                return sgn + Math.round(a).toLocaleString() + '억';
            }

                // Y축 시작·끝값 눈금 보장 (2026-07-16 사용자 확정) — grace로 벌어진 축 양끝에
                // 라벨이 없던 문제. 끝 눈금이 축 경계와 2% 이내면 스냅, 멀면 경계 눈금 추가.
                function cmbEnsureBoundTicks(ax) {
                    var t = ax.ticks;
                    if (!t || !t.length) return;
                    var span = ax.max - ax.min;
                    if (!(span > 0)) return;
                    if ((t[0].value - ax.min) / span > 0.02) t.unshift({ value: ax.min });
                    else t[0].value = ax.min;
                    if ((ax.max - t[t.length - 1].value) / span > 0.02) t.push({ value: ax.max });
                    else t[t.length - 1].value = ax.max;
                    // 최종 선별 (2026-07-16 1안 확정): 양끝 고정 + 내부는 스케일 공간(로그축=log)
                    // 최소 간격을 확보하며 최대 8개 — 경계·밀집 눈금의 라벨 겹침 원천 차단
                    var MAXT = 8;
                    var sv = function(v) { return (ax.type === 'logarithmic' && v > 0) ? Math.log(v) : v; };
                    var lo = sv(t[0].value), hi = sv(t[t.length - 1].value), rng = hi - lo;
                    if (rng > 0 && t.length > 2) {
                        var minGap = rng / (MAXT + 1);
                        var kept = [t[0]];
                        for (var k = 1; k < t.length - 1; k++) {
                            if (kept.length < MAXT - 1
                                && sv(t[k].value) - sv(kept[kept.length - 1].value) >= minGap
                                && hi - sv(t[k].value) >= minGap) kept.push(t[k]);
                        }
                        kept.push(t[t.length - 1]);
                        ax.ticks = kept;
                    }
                }

                function cmbEokTickVal(v, jo) {
                    return fmtByMag(jo ? v / 10000 : v);
                }

                // Y축 단위 주석(서브패널 전용) — 눈금엔 숫자만, 단위는 축 최상단 위에 1회 표기.
                // ★메인 차트는 2026-08-02부터 하단 범례 우측 표기로 전환 — 단위 유무에 따라
                //   padding.top(34/6)이 달라져 차트 시작 높이가 들쭉날쭉하던 문제.
                var cmbAxisUnitPlugin = {
                    id: 'cmbAxisUnit',
                    afterDraw: function(chart) {
                        // 차트별 지정(chart._cmbAxisUnits)만 사용 — P3에서 window 전역 폐기
                        // (서브패널은 단위가 고정이라 cmbRenderCharts 가 생성 시 직접 지정한다)
                        var u = chart._cmbAxisUnits;
                        if (!u) return;
                        var ctx = chart.ctx, ty = chart.chartArea.top - (chart._cmbAxisUnitDy || 20);   // 최상단 눈금 라벨과 겹침 방지
                        ctx.save();
                        ctx.font = '13px sans-serif';
                        ctx.fillStyle = '#000';
                        if (u.y) { ctx.textAlign = 'right'; ctx.fillText(u.y, chart.scales.y.right + 2, ty); }
                        if (u.y1 && chart.scales.y1) { ctx.textAlign = 'left'; ctx.fillText(u.y1, chart.scales.y1.left - 2, ty); }
                        ctx.restore();
                    }
                };

                // 로그축 경계 니스 라운딩 (2026-08-02 사용자 지적): 경계 눈금은 축 min/max 를
                // 그대로 라벨링하는데, 패딩 원값(예: 주가 3,472,049)이 일의자리까지 노출됐다.
                // 경계를 유효숫자 3자리로 min=내림·max=올림 — 데이터는 항상 안쪽, 라벨=실제 축값.
                function cmbNice3(v, up) {
                    if (!(v > 0)) return v;
                    var e = Math.pow(10, Math.floor(Math.log10(v)) - 2);
                    return (up ? Math.ceil(v / e - 1e-9) : Math.floor(v / e + 1e-9)) * e;
                }
                function cmbLogPad(minPos, maxV) {
                    if (!(minPos > 0) || !(maxV > 0) || minPos === Infinity) return null;
                    var llo = Math.log10(minPos), lhi = Math.log10(maxV);
                    var pad = (lhi - llo) * (0.05 / 0.90) || 0.02;
                    return { min: cmbNice3(Math.pow(10, llo - pad), false),
                             max: cmbNice3(Math.pow(10, lhi + pad), true) };
                }

// fmtUniform — fmtUniformFix가 호출하는 기저 포맷터 (P1b 후속 이동: 전역 함수는 클로저 내부를 못 본다)
            // 축 자릿수 통일: 같은 축 안에서는 하나의 밴드를 따른다.
            // ★밴드 기준 = 축의 '최종 끝값' (2026-07-28 변경. 종전 = 축 최대값)
            //   인자명 maxAbs 는 호환 유지 — 실제로 넘어오는 값은 _cmbAxisBandRef(끝값).
            function fmtUniform(v, maxAbs) {
                if (v === null || v === undefined) return '-';
                var dp = maxAbs < 10 ? 2 : (maxAbs < 100 ? 1 : 0);   // 일의자리 2dp·십의자리 1dp·백의자리+ 정수
                return Number(v).toLocaleString(undefined, { maximumFractionDigits: dp });
            }

// ── cmb(DATA) 크로스헤어·클릭핀·툴팁 동기 (P2a 이동 2026-08-02) ──
// ★P3 다중 패밀리(2026-08-02): 호버·핀 상태와 피어 목록은 전역이 아니라 '패밀리'
//   (cmbRenderCharts 1회 호출로 묶인 메인+서브패널) 단위 — 한 페이지에 cmb·idx 등
//   여러 표준 라인 차트가 공존해도 상태가 서로 새지 않도록 chart._cmbFamily 에 배선.
//   family = { hover: {idx,yPx,activeId}, pin: {date}, peers: [charts...] }
//   (P2a 의 window._cmbPeerAccessor 전역 접근자는 폐기 — 패밀리가 자기 피어를 직접 안다.)
function cmbPeerCharts(self) {
    var fam = self && self._cmbFamily;
    if (!fam) return [];
    return fam.peers.filter(function(c) {
        return c && c !== self && c.canvas;
    });
}
// (P7: legacy 호환 심 cmbFamilyOf 제거 — AOE_CHART_LEGACY 동결 렌더러 은퇴와 함께)

            function cmbSyncTooltip(other, idx) {
                if (!other || !other.tooltip) return;
                var els = [];
                if (idx !== null) {
                    other.data.datasets.forEach(function(ds, di) {
                        var v = ds.data[idx];
                        if (v !== null && v !== undefined) els.push({ datasetIndex: di, index: idx });
                    });
                }
                var area = other.chartArea;
                var pos = { x: 0, y: 0 };
                if (els.length && area) {
                    pos.x = other.scales.x.getPixelForValue(idx);
                    pos.y = (area.top + area.bottom) / 2;
                }
                other.tooltip.setActiveElements(els, pos);
                if (other.setActiveElements) other.setActiveElements(els);
            }

            var cmbCrosshairPlugin = {
                id: 'cmbCrosshair',
                afterEvent: function(chart, args) {
                    var e = args.event;
                    var area = chart.chartArea;
                    if (!area) return;
                    var _fam = chart._cmbFamily;
                    if (!_fam) return;   // 패밀리 배선 전(생성 직후 첫 draw) — 상태 없음
                    var cmbHoverState = _fam.hover, cmbPin = _fam.pin;
                    var _peers = cmbPeerCharts(chart);
                    var inside = e.x !== null && e.y !== null &&
                        e.x >= area.left && e.x <= area.right && e.y >= area.top && e.y <= area.bottom;
                    if (e.type === 'mouseout' || !inside) {
                        if (cmbHoverState.idx !== null) {
                            cmbHoverState.idx = null;
                            cmbHoverState.activeId = null;
                            args.changed = true;
                            _peers.forEach(function(o) {
                                cmbSyncTooltip(o, null);
                                o.draw();
                            });
                        }
                        return;
                    }
                    // 클릭 = 데이터 카드 고정(핀) — 같은 날짜 재클릭 해제, 다른 지점 클릭 이동 (2026-07-21 표준)
                    if (e.type === 'click' && chart._cmbPinHost) {
                        // P4: 드래그 팬 직후의 잔여 click 은 핀이 아니다 — 페이지(TV식 내비)가
                        // dragend 에 chart._cmbPinSuppress = true 를 세우면 1회 무시하고 소거
                        if (chart._cmbPinSuppress) { chart._cmbPinSuppress = false; return; }
                        var pIdx = Math.round(chart.scales.x.getValueForPixel(e.x));
                        var pMax = chart.data.labels.length - 1;
                        if (pIdx < 0) pIdx = 0;
                        if (pIdx > pMax) pIdx = pMax;
                        var pDate = chart.data.labels[pIdx];
                        cmbPin.date = (cmbPin.date === pDate) ? null : pDate;
                        args.changed = true;
                        return;
                    }
                    if (e.type !== 'mousemove') return;
                    var idx = Math.round(chart.scales.x.getValueForPixel(e.x));
                    var maxIdx = chart.data.labels.length - 1;
                    if (idx < 0) idx = 0;
                    if (idx > maxIdx) idx = maxIdx;
                    // 약한 마그넷: 현재 날짜(idx)의 데이터 점이 커서에서 12px 이내면 가로선을 그 점에 스냅
                    var yPx = e.y;
                    var snapRadius = 12;
                    var bestDist = null;
                    chart.data.datasets.forEach(function(ds, di) {
                        var v = ds.data[idx];
                        if (v === null || v === undefined) return;
                        var meta = chart.getDatasetMeta(di);
                        if (meta.hidden || !meta.data[idx]) return;
                        var py = meta.data[idx].y;
                        if (py === null || py === undefined || isNaN(py)) return;
                        var dist = Math.abs(py - e.y);
                        if (dist <= snapRadius && (bestDist === null || dist < bestDist)) {
                            bestDist = dist;
                            yPx = py;
                        }
                    });
                    var moved = cmbHoverState.idx !== idx;
                    cmbHoverState.idx = idx;
                    cmbHoverState.yPx = yPx;
                    cmbHoverState.activeId = chart.canvas.id;
                    args.changed = true;
                    _peers.forEach(function(o) {
                        if (moved) cmbSyncTooltip(o, idx);
                        o.draw();
                    });
                },
                afterDraw: function(chart) {
                    var _fam = chart._cmbFamily;
                    if (!_fam) return;
                    var cmbHoverState = _fam.hover;
                    if (cmbHoverState.idx === null) return;
                    var area = chart.chartArea;
                    var xs = chart.scales.x;
                    if (!area || !xs) return;
                    var xPx = xs.getPixelForValue(cmbHoverState.idx);
                    if (xPx < area.left || xPx > area.right) return;
                    var ctx = chart.ctx;
                    ctx.save();
                    ctx.strokeStyle = '#888';
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.moveTo(xPx, area.top);
                    ctx.lineTo(xPx, area.bottom);
                    ctx.stroke();
                    if (cmbHoverState.activeId === chart.canvas.id &&
                        cmbHoverState.yPx >= area.top && cmbHoverState.yPx <= area.bottom) {
                        ctx.beginPath();
                        ctx.moveTo(area.left, cmbHoverState.yPx);
                        ctx.lineTo(area.right, cmbHoverState.yPx);
                        ctx.stroke();
                    }
                    ctx.restore();
                }
            };

            // 클릭 핀 플러그인 (2026-07-21 표준): 클릭한 날짜의 세로 점선 + 데이터 카드를 캔버스에
            // 상주로 그림 — 플러그인이 직접 그려 Download PNG에도 포함. 값 포맷은 툴팁과 공용
            // (chart._cmbTipLabel = 빌드 시점 tooltipLabel 콜백).
            var cmbPinPlugin = {
                id: 'cmbPinCard',
                afterDraw: function(chart) {
                    var _famP = chart._cmbFamily;
                    if (!_famP || !chart._cmbPinHost) return;
                    var cmbPin = _famP.pin;
                    if (cmbPin.date === null) return;
                    var idx = chart.data.labels.indexOf(cmbPin.date);
                    if (idx < 0) return;   // 창 밖으로 나가면 표시만 생략 (상태는 유지)
                    var area = chart.chartArea, xs = chart.scales.x, ctx = chart.ctx;
                    if (!area || !xs) return;
                    var xPx = xs.getPixelForValue(idx);
                    if (xPx < area.left - 1 || xPx > area.right + 1) return;
                    ctx.save();
                    ctx.strokeStyle = 'rgba(17,17,17,0.45)';
                    ctx.setLineDash([4, 4]);
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.moveTo(xPx, area.top);
                    ctx.lineTo(xPx, area.bottom);
                    ctx.stroke();
                    ctx.setLineDash([]);
                    var lines = [];
                    chart.data.datasets.forEach(function(ds, di) {
                        var meta = chart.getDatasetMeta(di);
                        if (meta.hidden || ds._cmbAux) return;
                        var v = ds.data[idx];
                        if (v === null || v === undefined) return;
                        var txt = chart._cmbTipLabel
                            ? chart._cmbTipLabel({ dataset: ds, parsed: { y: v } })
                            : (ds.label + ': ' + v);
                        lines.push({ txt: txt, color: ds.borderColor });
                    });
                    if (!lines.length) { ctx.restore(); return; }
                    var title = String(cmbPin.date);
                    ctx.font = 'bold 13px sans-serif';
                    var w = ctx.measureText(title).width;
                    ctx.font = '13px sans-serif';
                    lines.forEach(function(l) { var tw = ctx.measureText(l.txt).width + 14; if (tw > w) w = tw; });
                    var pad = 10, lh = 19;
                    var boxW = w + pad * 2, boxH = pad * 2 + lh * (lines.length + 1);
                    var bx = xPx + 12;
                    if (bx + boxW > area.right) bx = xPx - 12 - boxW;
                    if (bx < area.left) bx = area.left + 4;
                    var by = area.top + 8;
                    ctx.fillStyle = 'rgba(0,0,0,0.8)';
                    ctx.beginPath();
                    ctx.roundRect(bx, by, boxW, boxH, 6);
                    ctx.fill();
                    ctx.textBaseline = 'middle';
                    ctx.textAlign = 'left';
                    ctx.fillStyle = '#fff';
                    ctx.font = 'bold 13px sans-serif';
                    ctx.fillText(title, bx + pad, by + pad + lh / 2);
                    ctx.font = '13px sans-serif';
                    lines.forEach(function(l, li) {
                        var ly = by + pad + lh * (li + 1) + lh / 2;
                        ctx.fillStyle = l.color;
                        ctx.beginPath();
                        ctx.arc(bx + pad + 4, ly, 4, 0, Math.PI * 2);
                        ctx.fill();
                        ctx.fillStyle = '#fff';
                        ctx.fillText(l.txt, bx + pad + 14, ly);
                    });
                    ctx.restore();
                }
            };

// ── cmb(DATA) 렌더 프레임 (P2b 이동 2026-08-02) — 끝값 라벨·서브패널 기준선 페인터·
//    메인/이격도/RoC² 차트 생성·재사용 프레임·하단 범례·축 단위/환산·툴팁 포맷.
//    페이지(클로저)는 데이터·도메인 계산(MA·이격도·RoC²)만 하고 cmbRenderCharts(view) 호출.
//    view = { labels, datasets, dispDatasets, rocDatasets, mode, yEok, y1Eok,
//             axAssign, unitMap, charts: {main, disp, roc} } → { main, disp, roc } 반환
//    (차트 인스턴스는 페이지 클로저 소유 — _cmbPeerAccessor 와 같은 원칙, P2a 참조).
                var cmbEndLabelPlugin = {
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
                                // ★밴드·환산은 차트 인스턴스에서 읽는다 (P3 다중 패밀리 — window 전역 폐기.
                                //   메인 차트만 _cmbAxisBandRef/_cmbAxisConv 보유, 서브패널은 축 기준 폴백)
                                var _bf = (chart._cmbAxisBandRef || {})[ds.yAxisID || 'y'] || Math.abs(val);
                                label = fmtUniformFix(val, _bf);
                            } else if ((chart._cmbMode || 'pct') === 'pct' && (ds.yAxisID || 'y') === 'y') {
                                // pct 끝값도 밴드를 따른다 (종전: 항상 정수)
                                // ★P4: pct 분기는 좌축(y) 한정 — 뷰어 정규화 모드는 우축(y1) 레벨
                                //   계열(괴리율 등)을 원값으로 유지한다 (cmb 는 pct 모드에 y1 없음 → 영향 0)
                                var _bp = (chart._cmbAxisBandRef || {})[ds.yAxisID || 'y'] || Math.abs(val);
                                label = (val >= 0 ? '+' : '') + fmtUniformFix(val, _bp) + '%';
                            } else {
                                // 끝값 라벨: 정수부 4자리(>=1000)부터 소수 제외, 그 외 최대 2자리 (2026-07-16 사용자 확정)
                                // 끝값 = 숫자만 (억원 시리즈는 축 단위(조/억)로 환산 — 단위는 하단 범례 우측 표기가 담당)
                                var _f2 = (chart._cmbAxisConv || {})[ds.yAxisID || 'y'] || 1;
                                var _ax = chart.scales[ds.yAxisID || 'y'] || chart.scales.y;
                                var _m2 = (chart._cmbAxisBandRef
                                    ? (chart._cmbAxisBandRef[ds.yAxisID || 'y'] || 0)
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

                            var cmbDisp100Plugin = {
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
                            var cmbDispHiLoPlugin = {
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

                            var cmbRoc0Plugin = {
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

            // 스택 막대 합계 라벨 (P6 이동 — 구 wrap AUM totalLabelPlugin 2벌 → 코어 1벌).
            // 보이는 스택의 꼭대기 막대 위에 합계 숫자를 그린다.
            var cmbStackTotalPlugin = {
                id: 'cmbStackTotals',
                afterDatasetsDraw: function(chart) {
                    var ctx = chart.ctx;
                    var datasets = chart.data.datasets;
                    var meta0 = chart.getDatasetMeta(0);
                    if (!meta0 || !meta0.data) return;
                    for (var i = 0; i < meta0.data.length; i++) {
                        var total = 0;
                        for (var d = 0; d < datasets.length; d++) {
                            if (chart.isDatasetVisible(d)) total += datasets[d].data[i] || 0;
                        }
                        if (total === 0) continue;
                        var lastMeta = null;
                        for (var dv = datasets.length - 1; dv >= 0; dv--) {
                            if (chart.isDatasetVisible(dv)) { lastMeta = chart.getDatasetMeta(dv); break; }
                        }
                        if (!lastMeta) continue;
                        var bar = lastMeta.data[i];
                        if (!bar) continue;
                        ctx.save();
                        ctx.font = 'bold 11px sans-serif';
                        ctx.fillStyle = '#000';
                        ctx.textAlign = 'center';
                        ctx.textBaseline = 'bottom';
                        ctx.fillText(Math.round(total), bar.x, bar.y - 4);
                        ctx.restore();
                    }
                }
            };

            function cmbRenderCharts(view) {
                var commonDates = view.labels;
                var datasets = view.datasets;
                var dispDatasets = view.dispDatasets;
                var rocDatasets = view.rocDatasets;
                var mode = view.mode;
                var yEok = view.yEok, y1Eok = view.y1Eok;
                var y2Eok = view.y2Eok || false;   // P5: 두 번째 우축(y2) — wrap AUM 등, y2 데이터셋이 있을 때만 활성
                var _axAssign = view.axAssign;
                var cmbSeriesUnit = view.unitMap;
                var cmbChart = view.charts.main, cmbDispChart = view.charts.disp, cmbRocChart = view.charts.roc;
                // ★P3 파라미터 (기본값 = cmb/DATA — 전부 생략하면 종전과 동일):
                //   ids: 캔버스·범례·서브패널 DOM id. 패널 id 에 null 을 주면 그 패널 프레임은 건너뜀
                //        (한 페이지에 두 패밀리가 공존할 때 남의 패널을 만지지 않기 위한 가드).
                //   xLabel: x축 눈금 포맷터 / logOn: Log 상태 / legendSuffix: 범례 끝 접미(예: '/ USD')
                var ids = view.ids || {};
                var _idCanvas = ids.canvas || 'cmbDynamicChart';
                // legend: null 을 명시하면 범례 없음 (P6 — 같은 페이지의 남의 범례를 만지지 않기)
                var _idLegend = ids.hasOwnProperty('legend') ? ids.legend : 'cmbChartLegend';
                var _idDispPanel = ids.hasOwnProperty('dispPanel') ? ids.dispPanel : 'cmbDispPanel';
                var _idDispCanvas = ids.dispCanvas || 'cmbDispChart';
                var _idRocPanel = ids.hasOwnProperty('rocPanel') ? ids.rocPanel : 'cmbRocPanel';
                var _idRocCanvas = ids.rocCanvas || 'cmbRocChart';
                var _xLabel = view.xLabel || window.cmbXLabel;
                var _logOn = (view.logOn !== undefined) ? view.logOn : window.cmbLogOn;

                // ※범례 생성은 축 단위(yJo/y1Jo, _cmbAxisUnits) 계산 뒤로 이동 (2026-08-02) —
                //   항목에 단위를 인라인 표기(`고객예탁금(조원) +25.4%`)하려면 조원 승격 판정이 선행돼야 함.
                var legendEl = _idLegend ? document.getElementById(_idLegend) : null;
                function cmbBuildLegend() {
                    // _cmbAux(P4): 평균선 등 보조 계열 — 범례·툴팁·핀 카드에서 제외 (끝값은 _skipEndLabel)
                    // 설정 기간 변화율 (P2b 규격). 자릿수는 항목별 |pct| 가 아니라 범례 전체
                    // 최대 |pct| 공유 기준으로 정한다 (2026-08-04: 주 시리즈 +95.3% 옆 MA20 이
                    // +9.88% 로 자릿수가 어긋나던 문제 — fmtUniformFix 의 '축 공유 기준' 취지와 통일).
                    function _legPctOf(ds) {
                        // pct 모드는 정규화된 값이라 last-first 자체가 변화율,
                        // raw 모드는 (last/first - 1)*100. 첫/마지막 non-null 값으로 계산.
                        var vals = ds.data.filter(function(v) { return v !== null && v !== undefined && !isNaN(v); });
                        if (vals.length < 2) return null;
                        var first = vals[0];
                        var last = vals[vals.length - 1];
                        var pct, sfx = '%';
                        // ★원값 모드의 %·%p 단위 시리즈 = 레벨 차이 %p (P2b 규격 정합, BASELINE 결함 5).
                        //   2026-07-19 확정 규격이 pct 모드에만 적용돼 있었다 — 나눗셈 %는 0 근처
                        //   값에서 발산한다 (괴리율 0.045→-5.33 이 -1,699% 로 표기되던 건).
                        //   MA 파생선은 단위 미등록 → 같은 축 주 시리즈의 단위를 따른다.
                        var _lu = cmbSeriesUnit[ds.label] || '';
                        if (!_lu) {
                            for (var _ai = 0; _ai < _axAssign.length; _ai++) {
                                if (_axAssign[_ai].ax === (ds.yAxisID || 'y')) { _lu = cmbSeriesUnit[_axAssign[_ai].name] || ''; break; }
                            }
                        }
                        if (mode === 'pct' && (ds.yAxisID || 'y') === 'y') {   // P4: pct 분기=좌축 한정
                            pct = last - first;
                        } else if (_lu === '%' || _lu === '%p') {
                            pct = last - first;
                            sfx = '%p';
                        } else if (first > 0) {
                            pct = (last / first - 1) * 100;
                        } else {
                            // 첫값이 0·음수인 원값 계열(FCF 등)은 비율 변화가 무의미 — 표기 생략 (P4b)
                            pct = null;
                        }
                        return pct === null ? null : { pct: pct, sfx: sfx };
                    }
                    var _legMaxAbs = 0;
                    datasets.filter(function(ds) { return !ds._cmbAux; }).forEach(function(ds) {
                        var _r0 = _legPctOf(ds);
                        if (_r0) _legMaxAbs = Math.max(_legMaxAbs, Math.abs(_r0.pct));
                    });
                    var legendHTML = datasets.filter(function(ds) { return !ds._cmbAux; }).map(function(ds) {
                        var c = ds.borderColor;
                        var pctStr = '';
                        var _r = _legPctOf(ds);
                        if (_r) {
                            pctStr = '<span>' + (_r.pct >= 0 ? '+' : '') + fmtUniformFix(_r.pct, _legMaxAbs) + _r.sfx + '</span>';
                        }
                        // 축 단위를 시리즈명 바로 뒤에 표기 (2026-08-02 사용자 확정 — 축 상단 주석 폐지).
                        // MA 등 파생선은 cmbSeriesUnit 미등록이라 자동으로 단위 없음.
                        // 단위 생략은 '정규화된 좌축'만 — 우축(y1·y2) 원값 계열은 pct 모드에도 단위 유지 (codex 8/2)
                        var unitStr = (mode === 'pct' && (ds.yAxisID || 'y') === 'y') ? ''
                            : (cmbUnitLabel(ds.label, (ds.yAxisID === 'y1') ? y1Jo : (ds.yAxisID === 'y2' ? y2Jo : yJo)) || '');
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
                    // 범례 접미 표기 (P3) — 예: INDICES USD 모드의 '/ USD'. 시리즈 항목이 아니라
                    // 컬러닷 없는 순수 텍스트 span — Download 합성 범례에서도 접미로 인식된다.
                    if (view.legendSuffix && datasets.length > 0) {
                        legendHTML += '<span style="font-size:13px;color:#555;font-weight:600;margin-left:4px;">' + view.legendSuffix + '</span>';
                    }
                    if (legendEl) legendEl.innerHTML = legendHTML;
                }

                var _yMaxAbs = 0, _y1MaxAbs = 0, _yMinPos = Infinity, _y1MinPos = Infinity;
                var _yHasNonPos = false, _y1HasNonPos = false;   // 음수·0 포함 축은 로그축 성립 불가 → 선형 폴백
                var _y2MaxAbs = 0, _y2MinPos = Infinity, _y2HasNonPos = false;
                datasets.forEach(function(ds) {
                    if (ds._skipEndLabel) return;
                    ds.data.forEach(function(v) {
                        if (v === null || v === undefined) return;
                        var a = Math.abs(v);
                        if (ds.yAxisID === 'y1') {
                            if (a > _y1MaxAbs) _y1MaxAbs = a;
                            if (v > 0 && v < _y1MinPos) _y1MinPos = v;
                            if (v <= 0) _y1HasNonPos = true;
                        } else if (ds.yAxisID === 'y2') {
                            if (a > _y2MaxAbs) _y2MaxAbs = a;
                            if (v > 0 && v < _y2MinPos) _y2MinPos = v;
                            if (v <= 0) _y2HasNonPos = true;
                        } else {
                            if (a > _yMaxAbs) _yMaxAbs = a;
                            if (v > 0 && v < _yMinPos) _yMinPos = v;
                            if (v <= 0) _yHasNonPos = true;
                        }
                    });
                });
                var yJo = yEok && _yMaxAbs >= 10000, y1Jo = y1Eok && _y1MaxAbs >= 10000;
                var y2Jo = y2Eok && _y2MaxAbs >= 10000;
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
                // ★P3: 축 단위·환산·밴드는 window 전역이 아니라 지역 변수로 계산해 '메인 차트
                //   인스턴스'에 부착한다 (update 직전). 전역이면 한 페이지의 다른 패밀리(idx 등)
                //   끝값·눈금이 남의 밴드를 읽는 오염이 생긴다.
                var _cmbAxisUnits = {
                    y: (mode !== 'pct') ? cmbAxisUnitFor('y', yJo) : null,
                    y1: (mode === 'raw2') ? cmbAxisUnitFor('y1', y1Jo) : null,
                    y2: datasets.some(function(ds){ return ds.yAxisID === 'y2'; }) ? cmbAxisUnitFor('y2', y2Jo) : null
                };
                cmbBuildLegend();   // 단위 인라인 표기 때문에 조원 승격(yJo/y1Jo) 판정 뒤에 렌더
                // 축별 표시 환산 계수 — MA 등 파생선도 같은 축 규칙을 타도록 축 기준으로 기록
                var _cmbAxisConv = { y: (yEok && yJo) ? 10000 : 1, y1: (y1Eok && y1Jo) ? 10000 : 1,
                                     y2: (y2Eok && y2Jo) ? 10000 : 1 };
                // ★자릿수 밴드 기준 = 축의 '최종 끝값' (2026-07-28 사용자 룰 변경. 종전 = 축 최대값).
                //   최대값 기준이면 기간에 큰 값이 한 번만 있어도 축 전체가 정수로 뭉개졌다
                //   (예: ETS 거래대금 끝값 67.56 인데 구간 최대 225.6 -> 68 로 표시).
                //   MA·이격도 파생선은 제외하고 축에 처음 배정된 주 시리즈의 마지막 실측값을 쓴다.
                var _lastAbs = { y: null, y1: null, y2: null };
                datasets.forEach(function(ds) {
                    if (ds._skipEndLabel) return;
                    if (/^MA\d/.test(ds.label || '') || /^이격도/.test(ds.label || '')) return;
                    var _ax = (ds.yAxisID === 'y1' || ds.yAxisID === 'y2') ? ds.yAxisID : 'y';
                    if (_lastAbs[_ax] !== null) return;
                    for (var _i = ds.data.length - 1; _i >= 0; _i--) {
                        var _v = ds.data[_i];
                        if (_v === null || _v === undefined || isNaN(_v)) continue;
                        _lastAbs[_ax] = Math.abs(_v);
                        break;
                    }
                });
                // 끝값을 못 찾으면(전 구간 결측) 종전대로 최대값으로 폴백
                var _cmbAxisBandRef = { y: (_lastAbs.y === null ? _yMaxAbs : _lastAbs.y),
                                        y1: (_lastAbs.y1 === null ? _y1MaxAbs : _lastAbs.y1),
                                        y2: (_lastAbs.y2 === null ? _y2MaxAbs : _lastAbs.y2) };

                // 음수·0 포함 시리즈(괴리율 등)는 Log 자동 무시 — 로그축에 음수가 들어가면
                // 선·끝값 라벨이 축 하단으로 뭉개진다 (2026-08-02 실사고: 삼성전자 현선물 괴리율 -5.33).
                // P6 프리셋: 'line'(기본) | 'stackedBar'(스택 막대 — 합계 라벨·축단위 주석·끝값 없음)
                //           | 'mini'(소형 — 11px 눈금·크로스헤어만·끝값 없음)
                var _preset = view.preset || 'line';
                var _fs = (_preset === 'mini') ? 11 : 15;
                var _stk = (_preset === 'stackedBar') ? true : undefined;
                var _xMaxT = (_preset === 'stackedBar') ? 100 : 6;
                var yType = (mode === 'pct' || _yHasNonPos) ? 'linear' : (_logOn === false ? 'linear' : 'logarithmic');
                var yLogPad = yType === 'logarithmic' ? cmbLogPad(_yMinPos, _yMaxAbs) : null;
                var y1Type = (_logOn === false || _y1HasNonPos) ? 'linear' : 'logarithmic';
                var y1LogPad = y1Type === 'logarithmic' ? cmbLogPad(_y1MinPos, _y1MaxAbs) : null;
                var y2Type = (_logOn === false || _y2HasNonPos) ? 'linear' : 'logarithmic';
                var y2LogPad = y2Type === 'logarithmic' ? cmbLogPad(_y2MinPos, _y2MaxAbs) : null;
                var scalesConfig = {
                    x: { type: 'category', display: datasets.length > 0, stacked: _stk, ticks: { maxTicksLimit: _xMaxT, callback: function(val){ return _xLabel(this.getLabelForValue(val)); }, maxRotation: 0, font: { size: _fs }, color: '#000' }, grid: { color: '#eee', display: true }, border: { color: '#000', width: 2 } },
                    y: {
                        type: yType,
                        position: 'left',
                        stacked: _stk,
                        beginAtZero: view.beginAtZero || undefined,
                        grace: '8%',
                        min: yLogPad ? yLogPad.min : undefined,
                        max: yLogPad ? yLogPad.max : undefined,
                        afterBuildTicks: cmbEnsureBoundTicks,
                        ticks: { maxTicksLimit: 8, autoSkip: false, callback: function(v){ return mode === 'pct' ? v + '%' : cmbTickFmt(v, this, yEok && yJo); }, font: { size: _fs }, color: '#000' },
                        grid: { color: '#eee' },
                        border: { color: '#000', width: 2 }
                    }
                };
                // ★P5: 두 번째 우축(y2) — wrap AUM 등. y2 데이터셋이 있을 때만 생성 (그리드 없음)
                if (datasets.some(function(ds){ return ds.yAxisID === 'y2'; })) {
                    scalesConfig.y2 = {
                        type: y2Type,
                        position: 'right',
                        grace: '8%',
                        min: y2LogPad ? y2LogPad.min : undefined,
                        max: y2LogPad ? y2LogPad.max : undefined,
                        afterBuildTicks: cmbEnsureBoundTicks,
                        ticks: { maxTicksLimit: 6, autoSkip: false, callback: function(v){ return cmbTickFmt(v, this, y2Eok && y2Jo); }, font: { size: _fs }, color: '#000' },
                        grid: { drawOnChartArea: false },
                        border: { color: '#000', width: 2 }
                    };
                }
                // ★P4: y1 축은 mode 무관 'y1 데이터셋 존재'로 생성 — 뷰어는 정규화(pct) 모드에도
                //   우측 레벨 계열을 유지한다 (cmb 는 raw2 외에 y1 배정이 없어 동작 불변)
                if (datasets.some(function(ds){ return ds.yAxisID === 'y1'; })) {
                    scalesConfig.y1 = {
                        type: y1Type,
                        position: 'right',
                        grace: '8%',
                        min: y1LogPad ? y1LogPad.min : undefined,
                        max: y1LogPad ? y1LogPad.max : undefined,
                        afterBuildTicks: cmbEnsureBoundTicks,
                        ticks: { maxTicksLimit: 8, autoSkip: false, callback: function(v){ return cmbTickFmt(v, this, y1Eok && y1Jo); }, font: { size: _fs }, color: '#000' },
                        grid: { drawOnChartArea: false },
                        border: { color: '#000', width: 2 }
                    };
                }

                // 툴팁도 눈금·끝값과 같은 밴드(_cmbAxisBandRef)를 따른다 (2026-07-28).
                // ★억원 계열의 전체형(`34조 2,669억`)만 사용자 확정 예외 — 나머지는 값에 단위를 붙이지 않는다.
                var tooltipLabel = function(ctx) {
                    if (ctx.parsed.y === null || ctx.parsed.y === undefined) return ctx.dataset.label + ': -';
                    var _tax = ctx.dataset.yAxisID || 'y';
                    var _tb = _cmbAxisBandRef[_tax] || 0;   // 지역 클로저 캡처 (P3 — window 전역 폐기)
                    if (mode === 'pct' && _tax === 'y') return ctx.dataset.label + ': ' + fmtUniformFix(ctx.parsed.y, _tb) + '%';   // P4: pct 분기=좌축 한정
                    var _eokAx = _tax === 'y1' ? y1Eok : (_tax === 'y2' ? y2Eok : yEok);
                    if (_eokAx) return ctx.dataset.label + ': ' + fmtEokFull(ctx.parsed.y);
                    var _tf = _cmbAxisConv[_tax] || 1;
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
                    else if (mode === 'pct' && (ds.yAxisID || 'y') === 'y') { var _r = Math.sign(lv) * Math.round(Math.abs(lv)); _lbl = (_r >= 0 ? '+' : '') + _r + '%'; }   // pct 폭 측정도 좌축 한정 (codex 8/2)
                    else { var _mf = (ds.yAxisID === 'y1' ? (y1Eok && y1Jo) : (ds.yAxisID === 'y2' ? (y2Eok && y2Jo) : (yEok && yJo))) ? 10000 : 1; _lbl = fmtUniformFix(lv / _mf, (ds.yAxisID === 'y1' ? _y1MaxAbs : (ds.yAxisID === 'y2' ? _y2MaxAbs : _yMaxAbs)) / _mf); }
                    var _w = _measCtx.measureText(_lbl).width;
                    if (_w > _maxLabelW) _maxLabelW = _w;
                });
                var _rightPad = Math.max(60, Math.ceil(_maxLabelW) + 12);
                // 프리셋별 프레임: 끝값 라벨이 없는 프리셋은 우측 패딩 최소화, 상단은 합계/단위 주석 자리
                var _mainPlugins = (_preset === 'stackedBar') ? [cmbStackTotalPlugin, cmbAxisUnitPlugin]
                    : ((_preset === 'mini') ? [cmbCrosshairPlugin, cmbAxisUnitPlugin]
                    : [cmbEndLabelPlugin, cmbCrosshairPlugin, cmbPinPlugin]);
                var _padTop = (_preset === 'stackedBar') ? 24 : ((_preset === 'mini') ? 20 : 6);
                if (_preset !== 'line') _rightPad = 8;

                if (cmbChart) {
                    // 재사용: 인스턴스 유지하고 데이터/축/툴팁만 교체 (destroy+new 멈칫 제거)
                    cmbChart.options.layout.padding.right = _rightPad;
                    cmbChart.options.layout.padding.top = _padTop;
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
                    // 밴드·환산·단위는 update 전에 인스턴스에 부착 — 눈금 빌드가 읽는다 (P3)
                    cmbChart._cmbAxisBandRef = _cmbAxisBandRef;
                    cmbChart._cmbAxisConv = _cmbAxisConv;
                    cmbChart._cmbAxisUnits = _cmbAxisUnits;
                    cmbChart._cmbPinHost = (_preset === 'line');   // 핀 카드는 기본 프리셋만
                    cmbChart.update('none');
                } else {
                    cmbChart = new Chart(document.getElementById(_idCanvas), {
                        type: 'line',
                        data: { labels: commonDates, datasets: datasets },
                        plugins: _mainPlugins,
                        options: {
                            responsive: true, maintainAspectRatio: false,
                            devicePixelRatio: 2 * (window.devicePixelRatio || 1),
                            layout: { padding: { right: _rightPad, top: _padTop } },
                            interaction: { mode: 'index', intersect: false },
                            plugins: {
                                legend: { display: false },
                                // animation:false — 동기 툴팁이 draw()만으로 위치 갱신되도록 (애니메이션 속성이면 제자리에 멈춤)
                                // 글씨 +1px (12→13, 2026-07-21 사용자 확정 — 클릭 핀 카드와 동일 크기)
                                // 카드 제목 = 원본 날짜(YYYY-MM-DD) — 축약(YY/MM)은 x축 눈금 전용 (2026-08-02 사용자 확정)
                                tooltip: { animation: false, titleFont: { size: 13 }, bodyFont: { size: 13 }, filter: function(c){ return !c.dataset._cmbAux; }, callbacks: { title: function(cs){ return cs.length ? String(cs[0].label) : ''; }, label: tooltipLabel } }
                            },
                            scales: scalesConfig
                        }
                    });
                    cmbChart._cmbMode = mode;   // 생성자 첫 draw는 mode 미설정으로 끝값이 +N% 오표기 -> 재렌더로 교정
                    cmbChart._cmbTipLabel = tooltipLabel;   // 클릭 핀 카드가 같은 포맷 사용
                    // 생성자 첫 draw 는 밴드 미부착(폴백 자릿수)으로 지나가고, 아래 update 가 교정한다
                    cmbChart._cmbAxisBandRef = _cmbAxisBandRef;
                    cmbChart._cmbAxisConv = _cmbAxisConv;
                    cmbChart._cmbAxisUnits = _cmbAxisUnits;
                    cmbChart._cmbPinHost = (_preset === 'line');   // 핀 카드는 기본 프리셋만
                    cmbChart.update('none');
                }

                // 이격도 서브패널 — 100 기준선 점선 + 메인 y축 폭에 맞춰 x축 정렬
                var dispPanel = _idDispPanel ? document.getElementById(_idDispPanel) : null;
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
                            cmbDispChart = new Chart(document.getElementById(_idDispCanvas), {
                                type: 'line',
                                data: { labels: commonDates, datasets: dispDatasets },
                                plugins: [cmbEndLabelPlugin, cmbDisp100Plugin, cmbDispHiLoPlugin, cmbCrosshairPlugin],
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
                                        x: { type: 'category', ticks: { maxTicksLimit: 6, callback: function(val){ return _xLabel(this.getLabelForValue(val)); }, maxRotation: 0, font: { size: 15 }, color: '#000' }, grid: { color: '#eee', display: true }, border: { color: '#000', width: 2 } },
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
                var rocPanel = _idRocPanel ? document.getElementById(_idRocPanel) : null;
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
                            cmbRocChart = new Chart(document.getElementById(_idRocCanvas), {
                                type: 'line',
                                data: { labels: commonDates, datasets: rocDatasets },
                                plugins: [cmbEndLabelPlugin, cmbRoc0Plugin, cmbCrosshairPlugin, cmbAxisUnitPlugin],
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
                                        x: { type: 'category', ticks: { maxTicksLimit: 6, callback: function(val){ return _xLabel(this.getLabelForValue(val)); }, maxRotation: 0, font: { size: 15 }, color: '#000' }, grid: { color: '#eee', display: true }, border: { color: '#000', width: 2 } },
                                        y: {
                                            type: 'linear',
                                            position: 'left',
                                            grace: '8%',
                                            // ★0 을 항상 축 범위에 포함 (2026-07-30 사용자 요청) — RoC² 는 부호가
                                            //   곧 가속/감속이라 0선이 보여야 둔화를 판독할 수 있다. 종전엔 값이
                                            //   전부 한쪽 부호면 0 이 범위 밖으로 나가 cmbRoc0Plugin 이 0선 그리기를
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
                }
                // ── 패밀리 배선 (P3) — 호버·핀 상태와 피어 목록을 이 호출로 묶인 차트들에 공유.
                //    재사용 경로에서는 기존 상태 객체 유지 (핀 날짜·호버가 리빌드에도 살아남는다 —
                //    종전 전역 상태와 동일한 수명).
                var _fam = (view.charts.main && view.charts.main._cmbFamily)
                    || (cmbChart && cmbChart._cmbFamily)
                    || { hover: { idx: null, yPx: null, activeId: null }, pin: { date: null }, peers: [] };
                _fam.peers = [cmbChart, cmbDispChart, cmbRocChart].filter(function(c) { return !!c; });
                _fam.peers.forEach(function(c) { c._cmbFamily = _fam; });
                // 새로 생긴 서브패널이 진행 중인 호버를 즉시 반영하도록 1회 재도장 (codex 지적 8/2)
                if (_fam.hover.idx !== null) _fam.peers.forEach(function(c) { c.draw(); });
                return { main: cmbChart, disp: cmbDispChart, roc: cmbRocChart };
            }
