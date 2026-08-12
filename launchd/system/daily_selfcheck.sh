#!/bin/bash
# daily_selfcheck.sh — once-a-day mac-mini health digest to Telegram (B9 / A17).
#
# WHY
#   A daily health check that messages Telegram ONLY when something is wrong —
#   and, since 2026-08-12, only when something CHANGED (user request):
#   * 2026-07-15: all-healthy runs log locally and stay silent (dead-man role
#     is covered externally by the GHA daily_health_check watchdog, 11:00 KST).
#   * 2026-08-12: an unchanged warning stays silent — one STALE false positive
#     used to send 6 identical daily messages (8/7~8/12). Every warning is now
#     normalized to a stable key (volatile numbers stripped); we alert on NEW
#     keys (🆕) and RESOLVED keys (✅), summarize persisting ones in one line
#     (⏳), and re-send a full digest of persisting warnings at most once per
#     SELFCHECK_DIGEST_SEC (default 7 days). All healthy + no change = silent.
#
# WHAT IT REPORTS (one Telegram message)
#   * bots     — how many of the 4 KeepAlive bots are `state = running`
#   * timers   — per schedule.tsv job, whether its last stamp covers the most
#                recent scheduled fire (OK n/N; STALE ones keyed per job)
#   * restarts — bot (re)starts in the last 24h from starts/<bot>.log (0 = calm)
#   * disk     — free space (GB); low (<SELFCHECK_DISK_MIN_GB) vs critical
#                (<SELFCHECK_DISK_CRIT_GB) are DISTINCT keys so a low→critical
#                slide re-alerts instead of hiding behind "unchanged"
#   * git-pull — consecutive-failure count + how old the synced HEAD is
#   * web      — Caddy / ts.net / snapshot age as three INDEPENDENT keys
#   * oauth    — headless Claude credential expiry (warn / expired / unknown)
#   Restarts / large-log are ℹ️ info lines: attached to sent messages only,
#   never a send trigger by themselves.
#
# GATE STATE (selfcheck_state/active — MUST stay git-untracked: a tracked file
# here gets clobbered by the 5-min auto pull, the exact 8/12 schedule.tsv bug):
#   line 1:  v1 <last_digest_epoch>
#   line 2+: <key> <first_seen_epoch>
# Loss-prevention rules (ported from notify_sisyphe_failure.sh v2 lessons —
# "a change that reduces alerts must first enumerate alert-LOSS paths"):
#   * state is written ONLY after a verified successful send (Telegram replied
#     "ok":true). A failed send leaves state untouched → same diff retries on
#     the next run. Every not-actually-sent branch (.env missing, creds
#     missing, curl failure, ok:false) returns FAILURE for the same reason.
#   * unreadable/garbage state fails OPEN: treated as empty → everything
#     currently wrong is (re)sent as new.
#   * a check that could not run (missing python/schedule/cron_prev, cron
#     parse failure) CARRIES its previous keys forward instead of emitting a
#     false ✅ resolution.
#   * state write failure after a send is surfaced loudly (log + best-effort
#     one-liner) — silent divergence would eat the next resolution alert.
#   * SELFCHECK_DRYRUN=1 renders and logs but never sends nor touches state.
#
# NEW WARNINGS: add them ONLY via add_warn <key> <detail>. Never append to the
# message by hand — a warning without a key silently bypasses the change gate.
#
# SECRETS: the bot token is read from .env into a local var and used ONLY as a
#   curl argument — never echoed, never written to any log.
#
# bash 3.2 / BSD tools / token-free self-locate. CONTRACT env v3 parser for .env.
set -u

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SELF_DIR/../.." && pwd)"          # launchd/system -> repo root
LOGDIR="$REPO/logs/launchd"
LOGFILE="${SELFCHECK_LOG_FILE:-$LOGDIR/daily-selfcheck.log}"
STAMPDIR="$LOGDIR/stamps"
STARTSDIR="$LOGDIR/starts"
SCHEDULE_TSV="${SCHEDULE_TSV:-$LOGDIR/schedule.tsv}"
CRON_PREV="$SELF_DIR/cron_prev.py"
PYTHON="$REPO/venv/bin/python3"; [ -x "$PYTHON" ] || PYTHON="$(command -v python3 || true)"

STATE_DIR="${SELFCHECK_STATE_DIR:-$LOGDIR/selfcheck_state}"
STATE_FILE="$STATE_DIR/active"
ENV_FILE="${SELFCHECK_ENV_FILE:-$REPO/.env}"
DIGEST_SEC="${SELFCHECK_DIGEST_SEC:-604800}"   # persisting-warning digest cadence

# The 4 KeepAlive bots (short names; label = com.antigravity.<name>, log = starts/<name>.log).
BOTS="sisyphe-bot ra-sisyphe-bot research-notes-bot seonyuduo-exercise-bot"

# .env variable names holding the Telegram creds (overridable).
TG_TOKEN_VAR="${SELFCHECK_TG_TOKEN_VAR:-TELEGRAM_SISYPHE_BOT_TOKEN}"
TG_CHAT_VAR="${SELFCHECK_TG_CHAT_VAR:-TELEGRAM_CHAT_ID}"

DISK_MIN_GB="${SELFCHECK_DISK_MIN_GB:-5}"      # warn if free disk < this (GB)
DISK_CRIT_GB="${SELFCHECK_DISK_CRIT_GB:-2}"    # distinct key below this (GB)
BIG_LOG_MB="${SELFCHECK_BIG_LOG_MB:-50}"       # note largest log if >= this (MB)
# Grace window after a scheduled fire during which a not-yet-stamped timer is
# treated as "in progress" instead of STALE — but only when the PREVIOUS fire
# was covered. Jobs stamp at COMPLETION, so a long run (earnings-bot: 08:00
# fire, ~09:00 stamp) looked stale to the 08:50 check every single day
# (2026-08-04~06 false alarms). A job that also missed its previous fire still
# alerts immediately.
TIMER_GRACE_S="${SELFCHECK_TIMER_GRACE_S:-7200}"

# Claude 구독 인증(headless 잡 4종 공용: 위키 문답·리서치 태깅·자가치료·지도 주간보정)의
# refresh 토큰 만료를 미리 경고한다. 2026-08-08 사고: 토큰이 07:20에 조용히 만료돼 넷이
# 한꺼번에 죽었는데, `claude -p` 는 인증 실패에도 exit 0 이라 잡 rc 감시로는 못 잡았다.
# 만료 시각은 파일에 적혀 있으므로 날짜로 앞질러 알린다.
CRED_FILE="${SELFCHECK_CRED_FILE:-${REPO%/*}/.claude/.credentials.json}"
OAUTH_WARN_DAYS="${SELFCHECK_OAUTH_WARN_DAYS:-7}"

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

# --- change-gate helpers ------------------------------------------------------
RECORDS=""            # fresh warnings, one per line: <key>\t<detail>
UNKNOWN_PREFIXES=""   # key prefixes whose check could not run (carry forward)
UNKNOWN_KEYS=""       # exact keys whose check could not run (carry forward)

add_warn() {                            # <key> <detail> — sole entry point
  local key="${1// /_}"
  RECORDS="${RECORDS}${key}"$'\t'"$2"$'\n'
}

rec_detail() {                          # <key> -> detail ('' if carried/unknown)
  printf '%s' "$RECORDS" | awk -F'\t' -v k="$1" '$1==k{print $2; exit}'
}

PREV_TABLE="" LAST_DIGEST=0 STATE_CORRUPT=0
load_state() {                          # fail-open: any damage -> empty PREV
  [ -f "$STATE_FILE" ] || return 0
  local first
  first="$(head -n1 "$STATE_FILE" 2>/dev/null)"
  case "$first" in
    v1\ *)
      LAST_DIGEST="${first#v1 }"
      case "$LAST_DIGEST" in ''|*[!0-9]*) LAST_DIGEST=0; STATE_CORRUPT=1 ;; esac ;;
    *)
      STATE_CORRUPT=1
      logf "state file corrupt or unknown version — fail-open, treating as empty"
      return 0 ;;
  esac
  PREV_TABLE="$(sed -n '2,$p' "$STATE_FILE" 2>/dev/null \
                | awk 'NF==2 && $2 ~ /^[0-9]+$/ {print $1" "$2}')"
}

prev_seen() {                           # <key> -> first_seen epoch ('' if new)
  printf '%s\n' "$PREV_TABLE" | awk -v k="$1" '$1==k{print $2; exit}'
}

write_state() {                         # <last_digest_epoch>; uses CUR_KEYS/now
  mkdir -p "$STATE_DIR" 2>/dev/null
  local tmp key seen now="$1" digest="$2"
  tmp="$(mktemp "$STATE_DIR/.active.XXXXXX" 2>/dev/null)" || return 1
  {
    echo "v1 $digest"
    while IFS= read -r key; do
      [ -n "$key" ] || continue
      seen="$(prev_seen "$key")"
      case "$seen" in ''|*[!0-9]*) seen="$now" ;; esac
      [ "$seen" -gt "$now" ] && seen="$now"     # clock-skew clamp
      echo "$key $seen"
    done <<< "$CUR_KEYS"
  } > "$tmp" || { rm -f "$tmp"; return 1; }
  chmod 644 "$tmp" 2>/dev/null
  mv "$tmp" "$STATE_FILE" || { rm -f "$tmp"; return 1; }
}

send_telegram() {                       # <message> -> 0 ONLY on verified send
  # Force xtrace OFF here (and swallow the trace line of this very command) so a
  # `bash -x` run — or inherited xtrace — can never print the expanded .env
  # export or the curl URL (which carries the token) to stderr / the .err log.
  { set +x; } 2>/dev/null
  local msg="$1" token="" chat="" resp="" attempt
  case "${SELFCHECK_SEND_MOCK:-}" in    # test hook: never in production .env
    ok)   logf "MOCK send ok: $(printf '%s' "$msg" | head -n1)"; return 0 ;;
    fail) logf "MOCK send fail"; return 1 ;;
  esac
  if ! load_env "$ENV_FILE"; then
    logf "no .env at $ENV_FILE — NOT sent (failure: state stays for retry)"
    return 1
  fi
  eval "token=\${$TG_TOKEN_VAR:-}"
  eval "chat=\${$TG_CHAT_VAR:-}"
  if [ -z "$token" ] || [ -z "$chat" ]; then
    logf "missing telegram creds ($TG_TOKEN_VAR / $TG_CHAT_VAR) — NOT sent (failure: state stays for retry)"
    return 1
  fi
  for attempt in 1 2 3; do
    resp="$(curl -s -m 20 \
         --data-urlencode "chat_id=$chat" \
         --data-urlencode "text=$msg" \
         "https://api.telegram.org/bot$token/sendMessage" 2>/dev/null)"
    case "$resp" in
      *'"ok":true'*)
        logf "selfcheck sent (attempt $attempt): $(printf '%s' "$msg" | head -n1)"
        return 0 ;;
    esac
    [ "$attempt" -lt 3 ] && sleep $(( attempt == 1 ? 5 : 10 ))
  done
  logf "selfcheck telegram send FAILED after 3 attempts — state NOT updated, will retry next run"
  return 1
}

main() {
  mkdir -p "$LOGDIR" 2>/dev/null || true
  local now cutoff; now="$(date +%s)"; cutoff=$(( now - 86400 ))
  local summary="" info=""

  if [ -n "${SELFCHECK_FAKE_WARNS:-}" ]; then
    # Test hook: '-' = fake empty; anything else = literal key\tdetail lines.
    # Skips every real check so the gate logic can be exercised in isolation.
    [ "$SELFCHECK_FAKE_WARNS" != "-" ] && RECORDS="${SELFCHECK_FAKE_WARNS}"$'\n'
    UNKNOWN_PREFIXES="${SELFCHECK_FAKE_UNKNOWN:-}"
    summary="맥미니 셀프체크(테스트)"
  else

  # --- bots -----------------------------------------------------------------
  local b bots_up=0 bots_total=0
  for b in $BOTS; do
    bots_total=$((bots_total+1))
    if bot_running "$b"; then bots_up=$((bots_up+1)); else add_warn "bot:$b" "봇 다운: $b"; fi
  done

  # --- restarts (last 24h) --------------------------------------------------
  local crash_total=0 crash_detail="" c
  for b in $BOTS; do
    c="$(count_starts_24h "$b" "$cutoff")"
    crash_total=$((crash_total + c))
    [ "$c" -gt 0 ] && crash_detail="$crash_detail ${b}(${c})"
  done

  # --- timers ---------------------------------------------------------------
  local tim_summary="?" tim_ok=0 tim_total=0
  if [ -f "$SCHEDULE_TSV" ] && [ -n "$PYTHON" ] && [ -f "$CRON_PREV" ]; then
    local name cron cmd last_exp st sf prev_exp
    while IFS=$'\t' read -r name cron cmd || [ -n "$name" ]; do
      case "$name" in ''|\#*) continue ;; esac
      name="$(echo "$name" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      [ -n "$name" ] || continue
      [ -n "${cron:-}" ] || continue
      tim_total=$((tim_total+1))
      last_exp="$("$PYTHON" "$CRON_PREV" "$cron" "$now" 2>/dev/null)"
      sf="$STAMPDIR/$name.last"; st="$(read_int "$sf")"
      if [ -z "$last_exp" ]; then
        # cron unparseable -> cannot judge. Count OK for the header, and carry
        # any previous stale key forward instead of fabricating a resolution.
        tim_ok=$((tim_ok+1))
        UNKNOWN_KEYS="${UNKNOWN_KEYS}timer:${name// /_}"$'\n'
        continue
      fi
      if [ "$st" -ge "$last_exp" ]; then
        tim_ok=$((tim_ok+1))
      elif [ "$st" -eq 0 ]; then
        add_warn "timer:$name" "타이머 무stamp: ${name}"
      else
        # Recently fired + previous fire covered -> assume still running (see
        # TIMER_GRACE_S above). Otherwise it is genuinely stale.
        prev_exp="$("$PYTHON" "$CRON_PREV" "$cron" "$(( last_exp - 60 ))" 2>/dev/null)"
        if [ $(( now - last_exp )) -lt "$TIMER_GRACE_S" ] && [ -n "$prev_exp" ] && [ "$st" -ge "$prev_exp" ]; then
          tim_ok=$((tim_ok+1))
        else
          add_warn "timer:$name" "타이머 STALE: ${name}($(human_dur $(( now - st ))))"
        fi
      fi
    done < "$SCHEDULE_TSV"
    tim_summary="OK ${tim_ok}/${tim_total}"
  else
    # timer check could not run at all — carry all previous timer keys forward
    UNKNOWN_PREFIXES="${UNKNOWN_PREFIXES}timer:"$'\n'
  fi

  # --- disk / logs ----------------------------------------------------------
  local logs_kb biggest big_kb big_path avail_kb disk_gb
  logs_kb="$(du -sk "$LOGDIR" 2>/dev/null | awk '{print $1}')"; case "$logs_kb" in ''|*[!0-9]*) logs_kb=0 ;; esac
  biggest="$(find "$LOGDIR" -type f -exec du -k {} + 2>/dev/null | sort -rn | head -1)"
  big_kb="$(printf '%s' "$biggest" | awk '{print $1}')"; case "$big_kb" in ''|*[!0-9]*) big_kb=0 ;; esac
  big_path="$(printf '%s' "$biggest" | sed 's/^[0-9]*[[:space:]]*//')"
  avail_kb="$(df -Pk "$REPO" 2>/dev/null | awk 'NR==2{print $4}')"; case "$avail_kb" in ''|*[!0-9]*) avail_kb=0 ;; esac
  disk_gb=$(( avail_kb / 1048576 ))
  if [ "$disk_gb" -lt "$DISK_CRIT_GB" ]; then
    add_warn "disk:critical" "디스크 여유 ${disk_gb}G (위험, ${DISK_CRIT_GB}G 미만)"
  elif [ "$disk_gb" -lt "$DISK_MIN_GB" ]; then
    add_warn "disk:low" "디스크 여유 ${disk_gb}G (임계 ${DISK_MIN_GB}G)"
  fi

  # --- git-pull -------------------------------------------------------------
  local gp_fail head_age head_ct
  gp_fail="$(read_int "$LOGDIR/git-pull.failcount")"
  head_age="?"
  if head_ct="$(git -C "$REPO" log -1 --format=%ct origin/main 2>/dev/null)"; then
    case "$head_ct" in ''|*[!0-9]*) : ;; *) head_age="$(human_dur $(( now - head_ct )))" ;; esac
  fi
  [ "$gp_fail" -gt 0 ] && add_warn "gitpull" "git-pull 연속실패 ${gp_fail}회"

  # --- web serving (W9): three independent keys -------------------------------
  local web_stat="OK" http_local http_ts cur_tgt snap_age_s snap_age="?"
  http_local="$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://127.0.0.1:8377/watchlist/ 2>/dev/null || echo 000)"
  # 맥 자신은 MagicDNS 해석 불가(homebrew tailscaled) - tailscale IP를 --resolve로 지정(인증서 검증 유지)
  local ts_ip; ts_ip="$(/opt/homebrew/bin/tailscale ip -4 2>/dev/null | head -1)"
  http_ts="$(curl -s -o /dev/null -m 10 --resolve "sisypheui-macmini.tailae16fa.ts.net:443:${ts_ip}" -w '%{http_code}' https://sisypheui-macmini.tailae16fa.ts.net/watchlist/ 2>/dev/null || echo 000)"
  cur_tgt="$(readlink /Users/sisyphe/srv/dashboard/current 2>/dev/null || true)"
  if [ -n "$cur_tgt" ] && [ -f "$cur_tgt/index.html" ]; then
    snap_age_s=$(( now - $(stat -f %m "$cur_tgt/index.html" 2>/dev/null || echo "$now") ))
    snap_age="$(human_dur "$snap_age_s")"
    [ "$snap_age_s" -gt 86400 ] && { web_stat="STALE"; add_warn "web:snap_stale" "웹 스냅숏 ${snap_age} 경과(24h+)"; }
  else
    web_stat="NO-SNAP"; add_warn "web:snap_broken" "웹 스냅숏 current 깨짐"
  fi
  if [ "$http_local" != "200" ]; then web_stat="DOWN"; add_warn "web:caddy" "Caddy 응답 ${http_local}"; fi
  if [ "$http_ts" != "200" ]; then web_stat="DOWN"; add_warn "web:tsnet" "ts.net 응답 ${http_ts}"; fi

  # --- headless claude 인증 만료 (2026-08-08 추가) ---------------------------
  local oauth_days="ERR"
  if [ -n "$PYTHON" ] && [ -r "$CRED_FILE" ]; then
    oauth_days="$("$PYTHON" -c 'import json,sys,time
try:
    o = json.load(open(sys.argv[1]))["claudeAiOauth"]
    v = o.get("refreshTokenExpiresAt") or 0
    print(int((v/1000 - time.time())//86400) if v else -999)
except Exception:
    print("ERR")' "$CRED_FILE" 2>/dev/null || echo ERR)"
  fi
  case "$oauth_days" in
    ''|*[!0-9-]*)
      add_warn "oauth:unknown" "Claude 인증 만료일 확인 불가 (${CRED_FILE})" ;;
    *)
      if [ "$oauth_days" -lt 0 ]; then
        add_warn "oauth:expired" "Claude 구독 인증 만료 — 위키 문답·리서치 태깅·자가치료·지도 보정 정지. 맥미니에서 claude 실행 후 /login"
      elif [ "$oauth_days" -le "$OAUTH_WARN_DAYS" ]; then
        add_warn "oauth:warn" "Claude 구독 인증 D-${oauth_days} 만료 예정 — 미리 재로그인 필요(만료되면 headless 잡 4종 동시 정지)"
      fi ;;
  esac

  # --- summary / info ---------------------------------------------------------
  summary="맥미니 셀프체크 | 봇 ${bots_up}/${bots_total} · 타이머 ${tim_summary} · 재시작 ${crash_total} · 디스크 ${disk_gb}G · HEAD ${head_age} · 웹 ${web_stat}(${snap_age})"
  [ "$crash_total" -gt 0 ]            && info="$info"$'\n'"ℹ️ 24h 재시작:$crash_detail"
  [ "$big_kb" -ge $(( BIG_LOG_MB * 1024 )) ] && info="$info"$'\n'"ℹ️ 최대 로그 $(( big_kb / 1024 ))M: ${big_path##*/}"

  fi  # end real checks (vs SELFCHECK_FAKE_WARNS)

  # --- change gate ------------------------------------------------------------
  load_state
  local FRESH_KEYS PREV_KEYS CUR_KEYS CARRY="" k p keep
  FRESH_KEYS="$(printf '%s' "$RECORDS" | cut -f1 | sed '/^$/d' | sort -u)"
  PREV_KEYS="$(printf '%s\n' "$PREV_TABLE" | awk 'NF{print $1}' | sort -u)"
  if [ -n "$UNKNOWN_PREFIXES" ] || [ -n "$UNKNOWN_KEYS" ]; then
    while IFS= read -r k; do
      [ -n "$k" ] || continue
      printf '%s\n' "$FRESH_KEYS" | grep -qxF "$k" && continue
      keep=0
      while IFS= read -r p; do
        [ -n "$p" ] || continue
        case "$k" in "$p"*) keep=1 ;; esac
      done <<< "$UNKNOWN_PREFIXES"
      printf '%s\n' "$UNKNOWN_KEYS" | grep -qxF "$k" && keep=1
      [ "$keep" = 1 ] && CARRY="${CARRY}${k}"$'\n'
    done <<< "$PREV_KEYS"
  fi
  CUR_KEYS="$(printf '%s\n%s' "$FRESH_KEYS" "$CARRY" | sed '/^$/d' | sort -u)"

  local NEW_KEYS GONE_KEYS PERSIST_KEYS
  NEW_KEYS="$(comm -23 <(printf '%s\n' "$CUR_KEYS" | sed '/^$/d') <(printf '%s\n' "$PREV_KEYS" | sed '/^$/d'))"
  GONE_KEYS="$(comm -13 <(printf '%s\n' "$CUR_KEYS" | sed '/^$/d') <(printf '%s\n' "$PREV_KEYS" | sed '/^$/d'))"
  PERSIST_KEYS="$(comm -12 <(printf '%s\n' "$CUR_KEYS" | sed '/^$/d') <(printf '%s\n' "$PREV_KEYS" | sed '/^$/d'))"

  local digest_due=0
  [ -n "$CUR_KEYS" ] && [ $(( now - LAST_DIGEST )) -ge "$DIGEST_SEC" ] && digest_due=1

  if [ -z "$NEW_KEYS" ] && [ -z "$GONE_KEYS" ] && [ "$digest_due" = 0 ]; then
    if [ -z "$CUR_KEYS" ]; then
      logf "selfcheck OK (suppressed): $summary$info"
    else
      logf "selfcheck unchanged (suppressed, $(printf '%s\n' "$CUR_KEYS" | sed '/^$/d' | wc -l | tr -d ' ') active): $summary"
    fi
    # repair a corrupt-but-quiet state file so it stops failing open every day
    [ "$STATE_CORRUPT" = 1 ] && write_state "$now" "$LAST_DIGEST"
    exit 0
  fi

  # --- assemble one message -----------------------------------------------------
  local head="⚠️" msg d seen
  [ -z "$CUR_KEYS" ] && head="✅"
  msg="$head $summary"
  while IFS= read -r k; do
    [ -n "$k" ] || continue
    d="$(rec_detail "$k")"; [ -n "$d" ] || d="$k (판정불가·이월)"
    msg="$msg"$'\n'"🆕 $d"
  done <<< "$NEW_KEYS"
  if [ -n "$GONE_KEYS" ]; then
    msg="$msg"$'\n'"✅ 해소:$(printf '%s\n' "$GONE_KEYS" | sed '/^$/d' | tr '\n' ' ' | sed 's/ $//; s/^/ /')"
  fi
  if [ -n "$PERSIST_KEYS" ]; then
    if [ "$digest_due" = 1 ]; then
      msg="$msg"$'\n'"⏰ 지속 경고 주간 리마인드:"
      while IFS= read -r k; do
        [ -n "$k" ] || continue
        seen="$(prev_seen "$k")"; case "$seen" in ''|*[!0-9]*) seen="$now" ;; esac
        d="$(rec_detail "$k")"; [ -n "$d" ] || d="판정불가·이월"
        msg="$msg"$'\n'"⏳ ${k}($(human_dur $(( now - seen )))): $d"
      done <<< "$PERSIST_KEYS"
    else
      local pline=""
      while IFS= read -r k; do
        [ -n "$k" ] || continue
        seen="$(prev_seen "$k")"; case "$seen" in ''|*[!0-9]*) seen="$now" ;; esac
        pline="$pline ${k}($(human_dur $(( now - seen ))))"
      done <<< "$PERSIST_KEYS"
      msg="$msg"$'\n'"⏳ 지속:$pline"
    fi
  fi
  msg="$msg$info"

  # last_digest advances only when the message carried FULL detail of every
  # current key (a due digest, or everything current was 🆕 in this message).
  local new_digest="$LAST_DIGEST"
  if [ "$digest_due" = 1 ] || [ -z "$PERSIST_KEYS" ]; then new_digest="$now"; fi

  if [ "${SELFCHECK_DRYRUN:-0}" = "1" ]; then
    logf "DRYRUN (no send, no state): $msg"
    exit 0
  fi

  if send_telegram "$msg"; then
    if ! write_state "$now" "$new_digest"; then
      logf "STATE WRITE FAILED after successful send ($STATE_FILE) — next run may duplicate or miss transitions"
      send_telegram "⚠️ selfcheck 상태 기록 실패(${STATE_FILE}) — 다음 알림이 중복/누락될 수 있음. 디스크·권한 확인 필요" || true
    fi
  fi
  exit 0
}

main "$@"
