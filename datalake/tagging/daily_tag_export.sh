#!/bin/bash
# Research Notes 일일 파이프라인 — 태깅 → md 아카이브 → parquet → 추이 집계.
#
# 23:20 datalake-research-export 잡의 실체. 태깅을 아카이브 생성보다 **앞**에 두어야
# 당일분 md가 태그와 함께 나온다. tag_worker 는 캐시 미스만 처리하므로 인자 없이
# 부르면 '아직 태깅 안 된 것 전부'가 대상 — 전날 실패분도 자동으로 회수된다.
#
# 실패 정책: 태깅·parquet·집계가 실패해도 **원문 아카이브 생성은 반드시 진행**한다
# (아카이브가 1차 산출물이고, 태그는 그 위에 얹는 파생물이기 때문).
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$REPO/venv/bin/python3"
rc=0

echo "── 1/5 태깅 (미처리분)"
"$PY" "$REPO/datalake/tagging/tag_worker.py" || { echo "[warn] 태깅 실패 — 태그 없이 계속"; rc=1; }

echo "── 2/5 md 아카이브 (어제+오늘)"
"$PY" "$REPO/datalake/export_research_notes.py" || { echo "[error] 아카이브 생성 실패"; exit 1; }

echo "── 3/5 parquet"
"$PY" "$REPO/datalake/tagging/export_tags_parquet.py" || { echo "[warn] parquet 실패"; rc=1; }

echo "── 4/5 추이 집계"
"$PY" "$REPO/datalake/tagging/build_theme_trends.py" || { echo "[warn] 집계 실패"; rc=1; }

echo "── 5/5 관심축 차트"
CHARTS="$HOME/work/charts/260715_현선물공매도"
if [ -f "$CHARTS/build_research_themes.py" ]; then
  ( cd "$CHARTS" && "$PY" build_research_themes.py ) || { echo "[warn] 차트 빌드 실패"; rc=1; }
else
  echo "[skip] 차트 빌더 없음"
fi

exit $rc
