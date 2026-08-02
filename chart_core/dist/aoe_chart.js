// aoe_chart.js — AoE 공용 차트 코어 (v0.1.0, P1 착수 2026-08-02)
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
                if (ax.chart && ax.chart.canvas && ax.chart.canvas.id === 'cmbDynamicChart' && window._cmbAxisBandRef)
                    m = (window._cmbAxisBandRef[ax.id] || Math.abs(ax.max || 0)) / f;
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
                        // 차트별 지정(chart._cmbAxisUnits) 우선 — 서브패널은 단위가 고정이라
                        // 전역 _cmbAxisUnits(메인 차트용)를 그대로 쓰면 오표기가 된다.
                        var u = chart._cmbAxisUnits || window._cmbAxisUnits;
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

                function cmbLogPad(minPos, maxV) {
                    if (!(minPos > 0) || !(maxV > 0) || minPos === Infinity) return null;
                    var llo = Math.log10(minPos), lhi = Math.log10(maxV);
                    var pad = (lhi - llo) * (0.05 / 0.90) || 0.02;
                    return { min: Math.pow(10, llo - pad), max: Math.pow(10, lhi + pad) };
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
