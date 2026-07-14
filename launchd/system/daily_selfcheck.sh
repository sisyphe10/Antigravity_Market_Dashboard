#!/bin/bash
# daily_selfcheck.sh — once-a-day mac-mini health digest to Telegram (B9 / A17).
#
# WHY
#   A daily health check that messages Telegram ONLY when something is wrong.
#   2026-07-15 (user request): the original design sent an OK message every day
#   as a dead-man's switch, but the daily noise outweighed it. The dead-man role
#   is covered externally by the GHA daily_health_check watchdog (11:00 KST),
#   so an all-healthy run now just logs locally and stays silent.
#
# WHAT IT REPORTS (one Telegram message)
#   * bots     — how many of the 4 KeepAlive bots are `state = running`
#   * timers   — per schedule.tsv job, whether its last stamp covers the most
#                recent scheduled fire (OK n/N; any STALE ones listed)
#   * restarts — bot (re)starts in the last 24h from starts/<bot>.log (0 = calm)
#   * disk     — logs/launchd total size, largest log file, free space (GB)
#   * git-pull — consecutive-failure count + how old the synced HEAD is
#   Header is ✅ when nothing is wrong, ⚠️ when a real problem is present.
#   Restarts / large-log are ℹ️ info lines that do NOT flip the header.
#
# SECRETS: the bot token is read from .env into a local var and used ONLY as a
#   curl argument — never echoed, never written to any log.
#
# bash 3.2 / BSD tools / token-free self-locate. CONTRACT env v3 parser for .env.
set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SELF_DIR/../.." && pwd)"          # launchd/system -> repo root
LOGDIR="$REPO/logs/launchd"
LOGFILE="$LOGDIR/daily-selfcheck.log"
STAMPDIR="$LOGDIR/stamps"
STARTSDIR="$LOGDIR/starts"
SCHEDULE_TSV="${SCHEDULE_TSV:-$LOGDIR/schedule.tsv}"
CRON_PREV="$SELF_DIR/cron_prev.py"
PYTHON="$REPO/venv/bin/python3"; [ -x "$PYTHON" ] || PYTHON="$(command -v python3 || true)"

# The 4 KeepAlive bots (short names; label = com.antigravity.<name>, log = starts/<name>.log).
BOTS="sisyphe-bot ra-sisyphe-bot research-notes-bot seonyuduo-exercise-bot"

# .env variable names holding the Telegram creds (overridable).
TG_TOKEN_VAR="${SELFCHECK_TG_TOKEN_VAR:-TELEGRAM_SISYPHE_BOT_TOKEN}"
TG_CHAT_VAR="${SELFCHECK_TG_CHAT_VAR:-TELEGRAM_CHAT_ID}"

DISK_MIN_GB="${SELFCHECK_DISK_MIN_GB:-5}"      # warn if free disk < this (GB)
BIG_LOG_MB="${SELFCHECK_BIG_LOG_MB:-50}"       # note largest log if >= this (MB)

logf() { echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] $*" >> "$LOGFILE"; }

# --- CONTRACT env v3 safe parser (no `set -a; source`) ------------------------
load_env() {
  local envfile="$1" line key val
  [ -f "$envfile" ] || return 1
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line#"${line%%[![:space:]]*}"}"
    case "$line" in ''|'#'*) continue ;; esac
    case "$line" in export\ *) line="${line#export }" ;; esac
    case "$line" in *=*) : ;; *) continue ;; esac
    key="${line%%=*}"; val="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"; key="${key%"${key##*[![:space:]]}"}"
    case "$val" in
      '"'*'"') val="${val#?}"; val="${val%?}" ;;
      "'"*"'") val="${val#?}"; val="${val%?}" ;;
    esac
    if [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      export "$key=$val"
    fi
  done < "$envfile"
  return 0
}

read_int() {                            # first line as pure integer, else 0
  local v=""
  [ -f "$1" ] && v="$(head -n1 "$1" 2>/dev/null)"
  v="${v#"${v%%[![:space:]]*}"}"; v="${v%"${v##*[![:space:]]}"}"
  case "$v" in ''|*[!0-9]*) echo 0 ;; *) echo "$v" ;; esac
}

human_dur() {                           # seconds -> compact Nd / Nh / Nm
  local s="$1"
  [ "$s" -lt 0 ] && s=0
  if   [ "$s" -ge 86400 ]; then echo "$((s/86400))d"
  elif [ "$s" -ge 3600 ];  then echo "$((s/3600))h"
  else echo "$((s/60))m"; fi
}

bot_running() {                         # <shortname> -> 0 running / 1 not
  local out
  out="$(launchctl print "system/com.antigravity.$1" 2>/dev/null)" || return 1
  case "$out" in *"state = running"*) return 0 ;; *) return 1 ;; esac
}

count_starts_24h() {                    # <shortname> <cutoff> -> restart count
  local f="$STARTSDIR/$1.log" cutoff="$2" line c=0
  [ -f "$f" ] || { echo 0; return; }
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line#"${line%%[![:space:]]*}"}"; line="${line%"${line##*[![:space:]]}"}"
    case "$line" in ''|*[!0-9]*) continue ;; esac
    [ "${#line}" -ge 9 ] && [ "${#line}" -le 12 ] || continue
    [ "$line" -ge "$cutoff" ] && c=$((c+1))
  done < "$f"
  echo "$c"
}

send_telegram() {                       # <message> — token used only as curl arg
  # Force xtrace OFF here (and swallow the trace line of this very command) so a
  # `bash -x` run — or inherited xtrace — can never print the expanded .env
  # export or the curl URL (which carries the token) to stderr / the .err log.
  # No restore needed: this is the last thing main() does before exit.
  { set +x; } 2>/dev/null
  local msg="$1" token="" chat=""
  if ! load_env "$REPO/.env"; then
    logf "no .env at $REPO/.env — skipping send (health computed but not delivered)"
    return 0
  fi
  eval "token=\${$TG_TOKEN_VAR:-}"
  eval "chat=\${$TG_CHAT_VAR:-}"
  if [ -z "$token" ] || [ -z "$chat" ]; then
    logf "missing telegram creds ($TG_TOKEN_VAR / $TG_CHAT_VAR) in .env — skipping send"
    return 0
  fi
  if curl -s -m 15 \
       --data-urlencode "chat_id=$chat" \
       --data-urlencode "text=$msg" \
       "https://api.telegram.org/bot$token/sendMessage" >/dev/null 2>&1; then
    logf "selfcheck sent: $(printf '%s' "$msg" | head -n1)"
  else
    logf "selfcheck telegram send FAILED (curl rc=$?)"   # never logs the token
  fi
}

main() {
  mkdir -p "$LOGDIR" 2>/dev/null || true
  local now cutoff; now="$(date +%s)"; cutoff=$(( now - 86400 ))

  # --- bots -----------------------------------------------------------------
  local b bots_up=0 bots_total=0 bots_down=""
  for b in $BOTS; do
    bots_total=$((bots_total+1))
    if bot_running "$b"; then bots_up=$((bots_up+1)); else bots_down="$bots_down $b"; fi
  done

  # --- restarts (last 24h) --------------------------------------------------
  local crash_total=0 crash_detail="" c
  for b in $BOTS; do
    c="$(count_starts_24h "$b" "$cutoff")"
    crash_total=$((crash_total + c))
    [ "$c" -gt 0 ] && crash_detail="$crash_detail ${b}(${c})"
  done

  # --- timers ---------------------------------------------------------------
  local tim_summary="?" tim_stale="" tim_ok=0 tim_total=0
  if [ -f "$SCHEDULE_TSV" ] && [ -n "$PYTHON" ] && [ -f "$CRON_PREV" ]; then
    local name cron cmd last_exp st sf
    while IFS=$'\t' read -r name cron cmd || [ -n "$name" ]; do
      case "$name" in ''|\#*) continue ;; esac
      name="$(echo "$name" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      [ -n "$name" ] || continue
      [ -n "${cron:-}" ] || continue
      tim_total=$((tim_total+1))
      last_exp="$("$PYTHON" "$CRON_PREV" "$cron" "$now" 2>/dev/null)"
      sf="$STAMPDIR/$name.last"; st="$(read_int "$sf")"
      if [ -z "$last_exp" ]; then tim_ok=$((tim_ok+1)); continue; fi   # can't judge -> assume ok
      if [ "$st" -ge "$last_exp" ]; then
        tim_ok=$((tim_ok+1))
      elif [ "$st" -eq 0 ]; then
        tim_stale="$tim_stale ${name}(무stamp)"
      else
        tim_stale="$tim_stale ${name}($(human_dur $(( now - st ))))"
      fi
    done < "$SCHEDULE_TSV"
    tim_summary="OK ${tim_ok}/${tim_total}"
  fi

  # --- disk / logs ----------------------------------------------------------
  local logs_kb logs_mb biggest big_kb big_path avail_kb disk_gb
  logs_kb="$(du -sk "$LOGDIR" 2>/dev/null | awk '{print $1}')"; case "$logs_kb" in ''|*[!0-9]*) logs_kb=0 ;; esac
  logs_mb=$(( logs_kb / 1024 ))
  biggest="$(find "$LOGDIR" -type f -exec du -k {} + 2>/dev/null | sort -rn | head -1)"
  big_kb="$(printf '%s' "$biggest" | awk '{print $1}')"; case "$big_kb" in ''|*[!0-9]*) big_kb=0 ;; esac
  big_path="$(printf '%s' "$biggest" | sed 's/^[0-9]*[[:space:]]*//')"
  avail_kb="$(df -Pk "$REPO" 2>/dev/null | awk 'NR==2{print $4}')"; case "$avail_kb" in ''|*[!0-9]*) avail_kb=0 ;; esac
  disk_gb=$(( avail_kb / 1048576 ))

  # --- git-pull -------------------------------------------------------------
  local gp_fail head_age head_ct
  gp_fail="$(read_int "$LOGDIR/git-pull.failcount")"
  head_age="?"
  if head_ct="$(git -C "$REPO" log -1 --format=%ct origin/main 2>/dev/null)"; then
    case "$head_ct" in ''|*[!0-9]*) : ;; *) head_age="$(human_dur $(( now - head_ct )))" ;; esac
  fi

  # --- web serving (W9) -------------------------------------------------------
  local web_stat="OK" web_warn="" http_local http_ts cur_tgt snap_age_s snap_age="?"
  http_local="$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://127.0.0.1:8377/index.html 2>/dev/null || echo 000)"
  # 맥 자신은 MagicDNS 해석 불가(homebrew tailscaled) - tailscale IP를 --resolve로 지정(인증서 검증 유지)
  local ts_ip; ts_ip="$(/opt/homebrew/bin/tailscale ip -4 2>/dev/null | head -1)"
  http_ts="$(curl -s -o /dev/null -m 10 --resolve "sisypheui-macmini.tailae16fa.ts.net:443:${ts_ip}" -w '%{http_code}' https://sisypheui-macmini.tailae16fa.ts.net/index.html 2>/dev/null || echo 000)"
  cur_tgt="$(readlink /Users/sisyphe/srv/dashboard/current 2>/dev/null || true)"
  if [ -n "$cur_tgt" ] && [ -f "$cur_tgt/index.html" ]; then
    snap_age_s=$(( now - $(stat -f %m "$cur_tgt/index.html" 2>/dev/null || echo "$now") ))
    snap_age="$(human_dur "$snap_age_s")"
    [ "$snap_age_s" -gt 86400 ] && { web_stat="STALE"; web_warn="⚠️ 웹 스냅숏 ${snap_age} 경과(24h+)"; }
  else
    web_stat="NO-SNAP"; web_warn="⚠️ 웹 스냅숏 current 깨짐"
  fi
  if [ "$http_local" != "200" ]; then web_stat="DOWN"; web_warn="⚠️ Caddy 응답 ${http_local}"; fi
  if [ "$http_ts" != "200" ]; then web_stat="DOWN"; web_warn="${web_warn}"$'\n'"⚠️ ts.net 응답 ${http_ts}"; fi

  # --- assemble -------------------------------------------------------------
  local summary warn="" info=""
  summary="맥미니 셀프체크 | 봇 ${bots_up}/${bots_total} · 타이머 ${tim_summary} · 재시작 ${crash_total} · 디스크 ${disk_gb}G · HEAD ${head_age} · 웹 ${web_stat}(${snap_age})"

  [ -n "$bots_down" ]                 && warn="$warn"$'\n'"⚠️ 봇 다운:$bots_down"
  [ -n "$tim_stale" ]                 && warn="$warn"$'\n'"⚠️ 타이머 STALE:$tim_stale"
  [ "$gp_fail" -gt 0 ]                && warn="$warn"$'\n'"⚠️ git-pull 연속실패 ${gp_fail}회"
  [ "$disk_gb" -lt "$DISK_MIN_GB" ]   && warn="$warn"$'\n'"⚠️ 디스크 여유 ${disk_gb}G (임계 ${DISK_MIN_GB}G)"
  [ -n "$web_warn" ]                  && warn="$warn"$'\n'"$web_warn"
  [ "$crash_total" -gt 0 ]            && info="$info"$'\n'"ℹ️ 24h 재시작:$crash_detail"
  [ "$big_kb" -ge $(( BIG_LOG_MB * 1024 )) ] && info="$info"$'\n'"ℹ️ 최대 로그 $(( big_kb / 1024 ))M: ${big_path##*/}"

  # 2026-07-15 사용자 지시: 이상 없으면 무음 — warn 없을 땐 로그만 남기고 발송 생략.
  # (데드맨 감시는 GHA daily_health_check 11:00 KST가 외부에서 담당)
  if [ -z "$warn" ]; then
    logf "selfcheck OK (suppressed): $summary$info"
    exit 0
  fi

  send_telegram "⚠️ $summary$warn$info"
  exit 0
}

main "$@"
