#!/bin/bash
# datalake 타이머 4종 설치 (맥미니, sudo 필요).
# 기존 launchd/timers/install_timers.sh 와 동일 방식: 토큰 치환 → /Library/LaunchDaemons → bootstrap.
# 사용: sudo bash datalake/launchd/install_datalake_timers.sh [사용자명(기본 sisyphe)]
set -euo pipefail

MACMINI_USER="${1:-sisyphe}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEST=/Library/LaunchDaemons

[ "$(id -u)" -eq 0 ] || { echo "sudo로 실행하세요"; exit 1; }
mkdir -p "$REPO/logs/launchd/stamps" "$REPO/logs/launchd/locks"
chown -R "$MACMINI_USER" "$REPO/logs/launchd" 2>/dev/null || true

for plist in "$SCRIPT_DIR"/com.antigravity.datalake-*.plist; do
  label="$(basename "$plist" .plist)"
  sed -e "s|__MACMINI_USER__|$MACMINI_USER|g" \
      -e "s|__REPO__|/Users/$MACMINI_USER/Antigravity_Market_Dashboard|g" \
      "$plist" > "$DEST/$label.plist"
  chown root:wheel "$DEST/$label.plist"
  chmod 644 "$DEST/$label.plist"
  plutil -lint "$DEST/$label.plist" >/dev/null
  launchctl bootout system "$DEST/$label.plist" 2>/dev/null || true
  launchctl bootstrap system "$DEST/$label.plist"
  echo "설치: $label"
done

echo "완료. 확인: launchctl print system | grep datalake"
