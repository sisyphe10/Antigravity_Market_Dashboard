#!/usr/bin/env python3
"""aoe_chart.js manifest 빌더 — 코어 수정 후 반드시 실행.

manifest(sha256)와 코어 파일이 어긋나면 create_dashboard가 생성 자체를 거부한다
(코어만 고치고 소비자 재생성을 잊는 사고를 강제로 드러내는 장치, DECISION Q2).
"""
import hashlib
import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(BASE, 'dist', 'aoe_chart.js')
MANIFEST = os.path.join(BASE, 'dist', 'aoe_chart.manifest.json')
CORE_VERSION = '0.2.0'   # P2b: cmb 렌더 프레임(cmbRenderCharts) 편입
CHARTJS_VERSION = '4.5.1'   # assets/vendor/js/chart.umd.min.js — P1은 페이지 전역 로드에 의존


def main():
    with open(CORE, encoding='utf-8') as f:
        core = f.read()
    if '</script>' in core.lower():
        print('FATAL: 코어에 </script> 문자열 — 인라인 임베드 불가')
        return 1
    try:
        commit = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True,
                                text=True, cwd=BASE).stdout.strip()
    except Exception:
        commit = 'unknown'
    manifest = {
        'coreVersion': CORE_VERSION,
        'coreSha256': hashlib.sha256(core.encode('utf-8')).hexdigest(),
        'coreBytes': len(core.encode('utf-8')),
        'chartJsVersion': CHARTJS_VERSION,
        'sourceCommit': commit,
    }
    with open(MANIFEST, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=1)
        f.write('\n')
    print('manifest written:', manifest['coreSha256'][:12], f"({manifest['coreBytes']}B, {commit})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
