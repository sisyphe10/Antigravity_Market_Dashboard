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
