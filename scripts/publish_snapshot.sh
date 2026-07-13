#!/bin/bash
# publish_snapshot.sh — 웹서빙 게시 스냅숏 생성 (designs/web_serving_design_final.md W3)
# 호출: 잡 wrapper 성공 직후(run_gha_job.sh / run_timer_job.sh). 실패해도 잡 rc에 영향 없음(호출측 || 처리).
# 동작: 화이트리스트 rsync → 새 세대 디렉토리 → 검증 → current 심링크 원자 교체(rename(2)).
# 어떤 실패 경로에서도 기존 current는 훼손되지 않는다.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
SRV="${PUBLISH_ROOT:-/Users/sisyphe/srv/dashboard}"
MANIFEST="$REPO/config/publish_manifest.txt"
LOCK="$SRV/.publish.lock"
REL="$SRV/releases/rel-$(date +%Y%m%dT%H%M%S)-$$"

log(){ echo "[publish $(date '+%F %T')] $*"; }

mkdir -p "$SRV/releases" "$SRV/logs" || exit 1

# mkdir 원자 락 (최대 120s 대기 — 게시 직렬화)
waited=0
until mkdir "$LOCK" 2>/dev/null; do
  waited=$((waited+2))
  if [ "$waited" -ge 120 ]; then log "락 타임아웃 - 이번 게시 스킵"; exit 75; fi
  sleep 2
done
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# 1) 화이트리스트 rsync (exclude 기본 — .env/secrets/.git 구조적 배제)
if ! rsync -a \
  --exclude='/.*' \
  --include='/*.html' --include='/*.json' --include='/*.csv' \
  --include='/orders/' --include='/orders/*.json' \
  --include='/architecture/' --include='/architecture/**' \
  --include='/charts/' --include='/charts/**' \
  --exclude='*' \
  "$REPO/" "$REL/"; then
  log "rsync 실패 - 세대 폐기"; rm -rf "$REL"; exit 1
fi

# 1.5) 개인용 뷰 합성 (compose_personal_view.py, 통합 설계 unified_design §3.2): WRAP 제거 +
#      AoE↔Sisyphe 통합 nav 주입 + Sisyphe 평문(~/srv/sisyphe_plain) 합성. repo·GitHub 원본 불변,
#      스냅숏 사본에서만 가공. 검증(sisyphe 존재·staticrypt 0·역방향 nav) 실패 시 세대 폐기.
if ! python3 "$REPO/scripts/compose_personal_view.py" "$REL"; then
  log "개인용 뷰 합성 실패 - 세대 폐기"; rm -rf "$REL"; exit 1
fi
if [ -f "$REL/wrap.html" ]; then log "wrap.html 제거 실패 - 세대 폐기"; rm -rf "$REL"; exit 1; fi

# 2) 검증: 매니페스트 필수 파일 존재·비어있지 않음 + 핵심 JSON 파싱
if [ -f "$MANIFEST" ]; then
  while IFS= read -r f; do
    case "$f" in ''|\#*) continue ;; esac
    if [ ! -s "$REL/$f" ]; then log "필수 파일 누락/빈파일: $f - 세대 폐기"; rm -rf "$REL"; exit 1; fi
  done < "$MANIFEST"
fi
for j in universe.json portfolio_data.json; do
  if [ -f "$REL/$j" ]; then
    if ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$REL/$j" >/dev/null 2>&1; then
      log "JSON 손상: $j - 세대 폐기"; rm -rf "$REL"; exit 1
    fi
  fi
done

# 3) current 원자 교체 — python os.rename=rename(2): 심링크 자체를 교체(BSD mv의 '대상 디렉토리로 이동' 함정 회피)
OLD_TARGET="$(readlink "$SRV/current" 2>/dev/null || true)"
TMPLN="$SRV/.current.tmp.$$"
ln -s "$REL" "$TMPLN"
if ! python3 -c "import os,sys; os.rename(sys.argv[1], sys.argv[2])" "$TMPLN" "$SRV/current"; then
  log "심링크 교체 실패"; rm -f "$TMPLN"; rm -rf "$REL"; exit 1
fi
if [ -n "$OLD_TARGET" ] && [ -d "$OLD_TARGET" ]; then
  ln -s "$OLD_TARGET" "$SRV/.previous.tmp.$$" \
    && python3 -c "import os,sys; os.rename(sys.argv[1], sys.argv[2])" "$SRV/.previous.tmp.$$" "$SRV/previous" \
    || rm -f "$SRV/.previous.tmp.$$"
fi

# 4) 보존: current/previous 대상 제외 최근 3세대만 유지
CUR="$(readlink "$SRV/current" 2>/dev/null || true)"
PRV="$(readlink "$SRV/previous" 2>/dev/null || true)"
n=0
for d in $(ls -1t "$SRV/releases" 2>/dev/null); do
  p="$SRV/releases/$d"
  case "$p" in "$CUR"|"$PRV") continue ;; esac
  n=$((n+1))
  if [ "$n" -gt 3 ]; then rm -rf "$p"; fi
done

log "게시 완료: $(basename "$REL") (이전: ${OLD_TARGET:-없음})"
exit 0
