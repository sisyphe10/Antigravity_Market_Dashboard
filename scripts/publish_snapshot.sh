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

# 1.5) 개인용 뷰 가공 (2026-07-11 사용자 확정, 통합 설계 반영): ts.net 개인 대시보드에는 WRAP 불요 +
#      Sisyphe 탭 주입(통합 대시보드 1단계). 스냅숏에서만 가공 — repo 원본·GitHub(팀원용)는 불변.
rm -f "$REL/wrap.html"
python3 - "$REL" <<'PYEOF'
import re, sys, glob, os
rel = sys.argv[1]
# WRAP topnav 아이템(탭+드롭다운) 통째 제거 → 잔여 wrap 링크 개별 제거
item_pat = re.compile(r'<div class="topnav-item"><a href="wrap\.html"[^>]*>.*?</div></div>', re.S)
link_pat = re.compile(r'<a[^>]*href="wrap\.html[^"]*"[^>]*>.*?</a>\s*', re.S)
SISYPHE = ('<div class="topnav-item"><a href="/sisyphe/index.html" class="topnav-tab">Sisyphe</a>'
           '<div class="topnav-dropdown">'
           '<a href="/sisyphe/dashboard.html" class="topnav-sub">가계부·운동</a>'
           '<a href="/sisyphe/journal.html" class="topnav-sub">투자일지</a>'
           '</div></div>')
NAV_END = '</div></div></nav>'
# 탭 순서 = Market > Sisyphe > Architecture (2026-07-12 사용자 확정)
# → Architecture 아이템 '앞'에 주입 (active 변형 대응 정규식), 없으면 nav 끝 폴백
arch_pat = re.compile(r'<div class="topnav-item"><a href="architecture\.html"')
for f in glob.glob(os.path.join(rel, "*.html")):
    s = open(f, encoding="utf-8").read()
    n = item_pat.sub("", s)
    n = link_pat.sub("", n)
    if 'topnav-tab">Sisyphe' not in n:
        m = arch_pat.search(n)
        if m:
            n = n[:m.start()] + SISYPHE + n[m.start():]
        elif NAV_END in n:
            n = n.replace(NAV_END, SISYPHE + NAV_END, 1)
    if n != s:
        open(f, "w", encoding="utf-8").write(n)
PYEOF
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
