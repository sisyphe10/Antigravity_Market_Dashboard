#!/usr/bin/env python3
"""cron_prev.py — compute the most recent scheduled fire time (<= now) for a
5-field cron expression, in Korea Standard Time (KST, fixed UTC+9).

Used by catchup_runner.sh to decide whether a launchd timer job missed its
last scheduled run while the mac mini was powered off / asleep.

Why fixed UTC+9 instead of the system TZ?
  Korea abolished DST in 1988, so KST is a permanent UTC+9 offset. Using a
  fixed offset (a) makes the result independent of a possibly-misconfigured
  system clock TZ and (b) lets this script be unit-tested on any OS
  (time.tzset() does not exist on Windows). The launchd schedules are defined
  in KST per the migration CONTRACT (system TZ = Asia/Seoul), so this matches.

Usage:
    cron_prev.py "<min> <hour> <dom> <mon> <dow>" [now_epoch]

  - now_epoch (optional): reference "now" as a Unix epoch (int). Defaults to
    the current time. Provided mainly for deterministic testing / desk-checks.

Output:
    Prints the integer Unix epoch of the previous fire time (<= now) on stdout.
    Exit 0 on success. Exit 2 if the expression never matches within the
    lookback window (treated by the caller as "cannot determine -> skip").

Supported cron syntax (Vixie-compatible subset):
    field       lo  hi   forms: *  a  a-b  a-b/s  */s  and comma lists of these
    minute       0  59
    hour         0  23
    day-of-month 1  31
    month        1  12
    day-of-week  0   7   (0 and 7 both mean Sunday)

Day-of-month / day-of-week rule (classic Vixie cron):
    If BOTH dom and dow are restricted (neither is '*'), a timestamp matches
    when EITHER field matches (logical OR). Otherwise the restricted fields
    are ANDed as usual.
"""

import sys
import time
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

# How far back to search for a matching minute. The jobs this serves are daily,
# weekly and monthly; 400 days covers those with wide margin. (A schedule that
# can recur less often than the window — e.g. Feb 29, which fires only on leap
# years — may return no previous fire; the caller treats that as "cannot
# determine -> skip".) A power-off longer than the window is caught by the job's
# own next scheduled fire anyway.
LOOKBACK_MINUTES = 400 * 24 * 60


def parse_field(expr, lo, hi):
    """Expand one cron field into a set of ints within [lo, hi]."""
    values = set()
    for part in expr.split(','):
        part = part.strip()
        if part == '':
            continue
        step = 1
        rng = part
        if '/' in part:
            rng, step_s = part.split('/', 1)
            step = int(step_s)
            if step <= 0:
                raise ValueError("step must be positive: %r" % part)
        if rng == '*':
            start, end = lo, hi
        elif '-' in rng:
            a, b = rng.split('-', 1)
            start, end = int(a), int(b)
        else:
            start = end = int(rng)
        if start > end:
            raise ValueError("range start > end: %r" % part)
        v = start
        while v <= end:
            if lo <= v <= hi:
                values.add(v)
            v += step
    if not values:
        raise ValueError("empty field: %r" % expr)
    return values


def normalize_dow(values):
    """cron day-of-week: 7 == Sunday == 0. Fold 7 into 0."""
    out = set()
    for v in values:
        out.add(0 if v == 7 else v)
    return out


def parse_cron(expr):
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError("expected 5 cron fields, got %d: %r" % (len(fields), expr))
    minute_s, hour_s, dom_s, mon_s, dow_s = fields
    spec = {
        'minutes': parse_field(minute_s, 0, 59),
        'hours': parse_field(hour_s, 0, 23),
        'doms': parse_field(dom_s, 1, 31),
        'months': parse_field(mon_s, 1, 12),
        'dows': normalize_dow(parse_field(dow_s, 0, 7)),
        'dom_restricted': dom_s.strip() != '*',
        'dow_restricted': dow_s.strip() != '*',
    }
    return spec


def matches(dt, spec):
    if dt.minute not in spec['minutes']:
        return False
    if dt.hour not in spec['hours']:
        return False
    if dt.month not in spec['months']:
        return False
    dom_ok = dt.day in spec['doms']
    # datetime.isoweekday(): Mon=1 .. Sun=7. cron wants Mon=1 .. Sat=6, Sun=0.
    cron_dow = dt.isoweekday() % 7
    dow_ok = cron_dow in spec['dows']
    if spec['dom_restricted'] and spec['dow_restricted']:
        return dom_ok or dow_ok
    if spec['dom_restricted'] and not dom_ok:
        return False
    if spec['dow_restricted'] and not dow_ok:
        return False
    return True


def previous_fire(expr, now_epoch):
    spec = parse_cron(expr)
    now = datetime.fromtimestamp(now_epoch, KST).replace(second=0, microsecond=0)
    dt = now
    for _ in range(LOOKBACK_MINUTES + 1):
        if matches(dt, spec):
            return int(dt.timestamp())
        dt -= timedelta(minutes=1)
    return None


def main(argv):
    if len(argv) < 2 or argv[1] in ('-h', '--help'):
        sys.stderr.write(__doc__)
        return 2
    expr = argv[1]
    if len(argv) >= 3:
        now_epoch = int(argv[2])
    else:
        now_epoch = int(time.time())
    try:
        result = previous_fire(expr, now_epoch)
    except (ValueError, IndexError) as exc:
        sys.stderr.write("cron_prev: bad cron expression %r: %s\n" % (expr, exc))
        return 2
    if result is None:
        sys.stderr.write("cron_prev: no match within lookback window for %r\n" % expr)
        return 2
    print(result)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
