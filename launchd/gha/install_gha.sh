#!/bin/bash
# install_gha.sh — Phase 2 컷오버용 GHA-잡 launchd 설치/제거기 (WP-A12)
#
# ★ macOS 기본 /bin/bash 는 3.2 → 이 스크립트는 bash 3.2 호환으로만 작성한다
#   (연관배열·mapfile·${v^^}/${v,,}·;;& 금지). 인덱스 배열/[[]]/case/awk/while-read 만 사용.
#
# 컷오버는 GHA_MIGRATION_PLAN 절차대로 **하루 1개씩** 진행하는 게 기본이다. 이 스크립트는
# 그 한 잡을 설치(토큰 치환→/Library/LaunchDaemons→bootstrap)하고, catch-up 러너(A4)가
# 자동으로 커버하도록 해당 잡의 스케줄 행을 **설치된 공유 schedule.tsv 에 upsert**한다.
#
# 사용법 (반드시 root — /Library/LaunchDaemons 쓰기 + system 도메인 launchctl):
#   sudo ./install_gha.sh <잡이름>        # 잡 1개 설치 (권장: 컷오버 1일 1잡)
#   sudo ./install_gha.sh --wave <N>      # Wave N(1|2|3)의 잡 전부 설치 (일괄 재설치용)
#   sudo ./install_gha.sh --remove <잡>   # 롤백: bootout + plist 삭제 + schedule.tsv 행 제거
#   sudo ./install_gha.sh --list          # 잡/웨이브 목록 출력
#
#   <잡이름> ∈ gha-fred | gha-universe | gha-ecos | gha-kofia | gha-krx-valuation
#             | gha-disclosures | gha-crawl | gha-earnings-calendar-sync | gha-finalize-orders
#
# 맥 사용자(=UserName·HOME 토큰): 환경변수 MACMINI_USER > SUDO_USER > REPO 소유자(stat) > id -un.
# REPO 경로: 이 스크립트가 항상 __REPO__/launchd/gha/ 아래 → 두 단계 상위(self-locate, 토큰 불필요).

set -u

# ── 잡/웨이브 정의 (bash 3.2: 공백구분 문자열) ──────────────────
ALL_JOBS="gha-fred gha-universe gha-ecos gha-kofia gha-krx-valuation gha-disclosures gha-crawl gha-earnings-calendar-sync gha-finalize-orders gha-taiwan-revenue"

wave_jobs() {  # $1=1|2|3 → 해당 웨이브 잡 목록. 미지정 웨이브는 rc 1.
  case "$1" in
    1) echo "gha-fred gha-universe gha-ecos gha-kofia" ;;
    2) echo "gha-krx-valuation gha-disclosures gha-crawl" ;;
    3) echo "gha-earnings-calendar-sync gha-finalize-orders" ;;
    *) return 1 ;;
  esac
}

is_valid_job() {  # $1=잡이름 → rc 0/1
  case " $ALL_JOBS " in *" $1 "*) return 0 ;; *) return 1 ;; esac
}

usage() {
  cat >&2 <<'USAGE'
usage:
  sudo ./install_gha.sh <잡이름>        # 잡 1개 설치 (권장: 컷오버 1일 1잡)
  sudo ./install_gha.sh --wave <N>      # Wave N(1|2|3) 전체 설치
  sudo ./install_gha.sh --remove <잡>   # 롤백(bootout+plist삭제+tsv행 제거)
  sudo ./install_gha.sh --list          # 목록
잡: gha-fred gha-universe gha-ecos gha-kofia gha-krx-valuation
    gha-disclosures gha-crawl gha-earnings-calendar-sync gha-finalize-orders
Wave1: fred/universe/ecos/kofia   Wave2: krx-valuation/disclosures/crawl
Wave3: earnings-calendar-sync/finalize-orders
USAGE
}

# ── 인자 파싱 ───────────────────────────────────────────────────
[ $# -ge 1 ] || { usage; exit 2; }
MODE="install"; TARGET=""
case "$1" in
  -h|--help)  usage; exit 0 ;;
  --list)
    echo "잡 9종: $ALL_JOBS"
    echo "Wave1: $(wave_jobs 1)"
    echo "Wave2: $(wave_jobs 2)"
    echo "Wave3: $(wave_jobs 3)"
    exit 0 ;;
  --remove)   MODE="remove";       TARGET="${2:-}" ;;
  --wave)     MODE="install-wave"; TARGET="${2:-}" ;;
  --*)        echo "알 수 없는 옵션: $1" >&2; usage; exit 2 ;;
  *)          MODE="install";      TARGET="$1" ;;
esac
[ -n "$TARGET" ] || { echo "대상이 비었습니다." >&2; usage; exit 2; }

# ── self-locate: REPO / 경로 ────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
SRC_DIR="$SCRIPT_DIR"                       # launchd/gha (원본 plist + schedule_gha.tsv)
SRC_TSV="$SRC_DIR/schedule_gha.tsv"
DEST_TSV="$REPO/logs/launchd/schedule.tsv" # A4 가 읽는 설치된 공유 스케줄(타이머+GHA 공용)
LD_DIR="/Library/LaunchDaemons"

[ -f "$SRC_TSV" ] || { echo "schedule_gha.tsv 없음: $SRC_TSV" >&2; exit 1; }

# ── root 확인 (/Library/LaunchDaemons 쓰기 + system 도메인 launchctl) ──
if [ "$(id -u)" -ne 0 ]; then
  echo "root 권한 필요 → 'sudo ./install_gha.sh ...' 로 실행하세요." >&2; exit 1
fi

# ── 맥 사용자 결정 (토큰 __MACMINI_USER__ 치환값) ───────────────
MACMINI_USER="${MACMINI_USER:-${SUDO_USER:-}}"
if [ -z "$MACMINI_USER" ]; then
  MACMINI_USER="$(stat -f '%Su' "$REPO" 2>/dev/null || true)"   # BSD stat(macOS): REPO 소유자
fi
[ -n "$MACMINI_USER" ] || MACMINI_USER="$(id -un)"

# 사용자명 형식 엄격 검증 (install_bots.sh valid_user 이식 — 감사 DR3): sed 치환 전 개행/특수문자를
# 차단해 plist 파손·인젝션 방지. grep -Eq 대신 case 글로브 사용(개행 포함 문자열 전체에 매칭).
valid_user() {
  local u="$1"
  [ -n "$u" ] || return 1
  case "$u" in [a-z_]*) ;; *) return 1 ;; esac                 # 첫 글자 소문자/밑줄
  case "$u" in *[!a-z0-9_-]*) return 1 ;; *) return 0 ;; esac  # 허용집합 밖 문자 존재 시 거부
}
if ! valid_user "$MACMINI_USER"; then
  echo "부적합한 사용자명: '$MACMINI_USER' (허용: 소문자/숫자/밑줄/하이픈, 첫 글자 소문자/밑줄)." >&2
  echo "  실사용자명을 지정하세요: sudo MACMINI_USER=<user> ./install_gha.sh ..." >&2
  exit 1
fi

# ── schedule.tsv 행 렌더/병합/제거 (tab 보존, 원자적 mktemp+mv) ──
render_row() {  # $1=잡 → schedule_gha.tsv 의 해당 행에 __REPO__ 치환해 stdout. 없으면 rc 3.
  awk -F'\t' -v j="$1" -v repo="$REPO" '
    $1==j { gsub(/__REPO__/, repo); print; found=1 }
    END   { if (!found) exit 3 }
  ' "$SRC_TSV"
}

upsert_row() {  # $1=잡 → DEST_TSV 에서 동명 행 제거 후 새 행 append (이름 존재 시 교체 = 중복 방지)
  local job="$1" newrow dir tmp
  newrow="$(render_row "$job")" || { echo "schedule_gha.tsv 에 '$job' 행이 없습니다." >&2; return 3; }
  dir="$(dirname "$DEST_TSV")"
  mkdir -p "$dir" || return 1
  [ -f "$DEST_TSV" ] || : > "$DEST_TSV"
  tmp="$(mktemp "$dir/.schedule.XXXXXX")" || return 1
  # $1!=job 인 기존 행만 보존(무수정 재출력 → tab 그대로), 그 뒤 새 행 append.
  awk -F'\t' -v j="$job" '$1!=j' "$DEST_TSV" > "$tmp" || { rm -f "$tmp"; return 1; }
  printf '%s\n' "$newrow" >> "$tmp" || { rm -f "$tmp"; return 1; }
  mv -f "$tmp" "$DEST_TSV" || { rm -f "$tmp"; return 1; }
  # 런타임(래퍼가 user 로 stamps/locks mkdir)·A4 read 를 위해 소유자를 맥 사용자로.
  chown "$MACMINI_USER" "$dir" "$DEST_TSV" 2>/dev/null || true
  return 0
}

remove_row() {  # $1=잡 → DEST_TSV 에서 동명 행 제거(있으면). 없으면 no-op.
  local job="$1" dir tmp
  [ -f "$DEST_TSV" ] || return 0
  dir="$(dirname "$DEST_TSV")"
  tmp="$(mktemp "$dir/.schedule.XXXXXX")" || return 1
  awk -F'\t' -v j="$job" '$1!=j' "$DEST_TSV" > "$tmp" || { rm -f "$tmp"; return 1; }
  mv -f "$tmp" "$DEST_TSV" || { rm -f "$tmp"; return 1; }
  chown "$MACMINI_USER" "$DEST_TSV" 2>/dev/null || true
  return 0
}

# ── 잡 1개 설치 ─────────────────────────────────────────────────
#   원자성: plist 는 목적지에 직접 쓰지 않고 **같은 디렉토리 temp → mv -f**(동일 FS 원자 rename)로
#   설치 → 부분/실패 sed 가 목적지 plist 를 오염시키지 않는다. 이후 어느 단계든 실패하면 반쪽 설치를
#   남기지 않도록 **bootout + plist 삭제 롤백**한다(bootstrap 실패·upsert 실패 모두).
install_job() {
  local job="$1" label src dst tmp
  label="com.antigravity.$job"
  src="$SRC_DIR/$label.plist"
  dst="$LD_DIR/$label.plist"
  [ -f "$src" ] || { echo "plist 원본 없음: $src" >&2; return 1; }

  # ① 토큰 치환 → 같은 디렉토리 temp (경로에 '/' 있어 sed 구분자는 '|'). temp 는 '.plist' 확장자
  #    없는 hidden 이름이라 launchd 자동 로드 대상 아님.
  tmp="$(mktemp "$LD_DIR/.$label.XXXXXX")" || { echo "temp 생성 실패: $LD_DIR (권한/디스크)" >&2; return 1; }
  if ! sed -e "s|__REPO__|$REPO|g" -e "s|__MACMINI_USER__|$MACMINI_USER|g" "$src" > "$tmp"; then
    rm -f "$tmp"; echo "plist 렌더 실패: $src" >&2; return 1
  fi
  chown root:wheel "$tmp" 2>/dev/null || true
  chmod 644 "$tmp"
  if ! mv -f "$tmp" "$dst"; then
    rm -f "$tmp"; echo "plist 설치(mv) 실패: $dst" >&2; return 1
  fi

  # ② (재)load: 이미 적재됐으면 bootout 후 bootstrap (idempotent). 실패 시 설치 plist 롤백.
  launchctl bootout "system/$label" 2>/dev/null || true
  if ! launchctl bootstrap system "$dst"; then
    launchctl bootout "system/$label" 2>/dev/null || true
    rm -f "$dst"
    echo "launchctl bootstrap 실패: $label → plist 롤백(삭제)" >&2; return 1
  fi
  launchctl enable "system/$label" 2>/dev/null || true

  # ③ 스케줄 병합(upsert) → A4 catch-up 자동 커버. 실패 시 반쪽 설치(load됐으나 tsv 행 없음) 방지
  #    → bootout + plist 삭제 롤백. (upsert_row 자체가 mktemp+mv 원자적이라 실패 시 DEST_TSV 는 무변경.)
  if ! upsert_row "$job"; then
    launchctl bootout "system/$label" 2>/dev/null || true
    rm -f "$dst"
    echo "schedule.tsv 병합 실패: $job → bootout + plist 롤백(삭제)" >&2; return 1
  fi

  echo "[install] $label → $dst 설치+load, schedule.tsv upsert 완료"
  return 0
}

# ── 잡 1개 제거(롤백) ──────────────────────────────────────────
remove_job() {
  local job="$1" label dst
  label="com.antigravity.$job"
  dst="$LD_DIR/$label.plist"
  launchctl bootout "system/$label" 2>/dev/null || true
  rm -f "$dst"
  remove_row "$job" || { echo "schedule.tsv 행 제거 실패: $job" >&2; return 1; }
  echo "[remove] $label bootout+plist삭제, schedule.tsv 행 제거 완료"
  return 0
}

# ── 대상 잡 목록 결정 ───────────────────────────────────────────
JOB_LIST=""
case "$MODE" in
  install|remove)
    is_valid_job "$TARGET" || { echo "알 수 없는 잡: $TARGET" >&2; usage; exit 2; }
    JOB_LIST="$TARGET" ;;
  install-wave)
    JOB_LIST="$(wave_jobs "$TARGET")" || { echo "알 수 없는 Wave: $TARGET (1|2|3)" >&2; exit 2; }
    echo "※ Wave $TARGET 일괄 설치: $JOB_LIST"
    echo "※ 표준 컷오버는 '하루 1잡'이 원칙(GHA_MIGRATION_PLAN). --wave 는 검증 완료 후 일괄/재설치용." ;;
esac

# ── 실행 ────────────────────────────────────────────────────────
RC=0
for job in $JOB_LIST; do
  if [ "$MODE" = "remove" ]; then
    remove_job "$job" || RC=1
  else
    install_job "$job" || RC=1
  fi
done

if [ "$RC" -eq 0 ]; then
  echo "완료. 확인: sudo launchctl list | grep com.antigravity.gha"
else
  echo "일부 작업 실패(rc=$RC) — 위 오류 메시지 확인." >&2
fi
exit "$RC"
