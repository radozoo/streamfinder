#!/bin/bash
# Daily unattended catalog refresh.
#
# Runs `csfd update`, gates the result, commits and pushes. GitHub Actions then
# deploys. Nothing here asks a human anything: success is silent, failure raises a
# macOS notification and leaves a log.
#
# It is written to survive being run by launchd, which the previous attempt was not:
#
#   * Absolute paths for everything. launchd gives a job almost no PATH, and the last
#     one died on `ModuleNotFoundError: csfd_vod` because it picked up Homebrew's
#     python3.12 while the package is installed into the python.org 3.13 framework.
#   * The repo lives outside ~/Documents. macOS TCC refuses a launchd job access to
#     it there — the previous agent could not even read its own script
#     ("Operation not permitted") and failed silently for days.
#   * Postgres is started if it is down. It is a bare postmaster on a custom data
#     directory, not a brew service, so nothing brings it back after a reboot.
#     `brew services start postgresql@15` would be actively wrong: brew's own data
#     directory exists and is a DIFFERENT, empty database.
#
# Usage:  scripts/refresh.sh [--dry-run] [--no-push] [--force] [any `csfd update` flag]

set -uo pipefail

REPO="/Users/radozoo/dev/csfd"
PYTHON="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
GIT="/usr/bin/git"
GH="/opt/homebrew/bin/gh"
PG_CTL="/opt/homebrew/bin/pg_ctl"
PG_ISREADY="/opt/homebrew/bin/pg_isready"
PGDATA="/Users/radozoo/postgres_data"

# launchd hands a job almost no environment, and with an empty LANG/LC_ALL macOS goes
# multithreaded while looking a locale up — inside postmaster's own startup, which it
# refuses to survive:
#   FATAL:  postmaster became multithreaded during startup
#   HINT:   Set the LC_ALL environment variable to a valid locale.
# This is exactly how the 2026-08-18 run died, and why it took until then: it was the
# first scheduled run that actually had to START postgres. Every earlier one found it
# already up — brought up by hand from a shell that had LANG set — so the fragile path
# never ran under launchd at all. C.UTF-8 is what that shell uses.
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

# This Mac idle-sleeps after one minute (`pmset -g custom` → sleep 1), and a launchd
# job with ProcessType Background holds no wake assertion of its own. Without this
# re-exec the scrape gets only DarkWake bursts — a few seconds of CPU every ~15
# minutes — so Playwright never finishes a page: `BrowserType.launch` hits its 180s
# timeout because the machine sleeps mid-launch, the requests fallback returns the
# Anubis challenge page, and every title is rejected as "Missing mandatory field:
# title". That is how 2026-08-23 → 2026-08-30 were lost: the 08-25 run took until
# 08-28, the 08-29 run was still going 25 hours later, and 08-30 never ran at all
# because launchd will not start a second copy of a label that is still busy.
# The guard variable keeps the re-exec from recursing.
CAFFEINATE="/usr/bin/caffeinate"
if [ -z "${REFRESH_CAFFEINATED:-}" ] && [ -x "$CAFFEINATE" ]; then
  export REFRESH_CAFFEINATED=1
  # -i idle sleep, -m disk sleep, -s system sleep on AC. ${1+"$@"} is the portable
  # guard for an empty argument list under `set -u` in the bash 3.2 macOS ships.
  exec "$CAFFEINATE" -ims /bin/bash "$0" ${1+"$@"}
fi

LOG_DIR="$REPO/logs/refresh"
STAMP="$(date +%Y-%m-%dT%H%M%S)"
LOG="$LOG_DIR/$STAMP.log"
STATUS="$LOG_DIR/last-run.json"
LOCK="$LOG_DIR/.lock"

# Two different budgets, because "the run is stuck" and "the laptop was shut" are
# two different things and only one of them is a fault.
#
# Closing the lid mid-run is ordinary and always was: the process survives, and
# resumes when the Mac is opened again. That is how the 2026-08-25 run eventually
# finished, and for months it is how a normal day worked. A wall-clock deadline
# punishes exactly that case — 2026-08-31 was opened at 08:13, shut around 08:30
# and would have finished on reopening, but the clock had run out by then and the
# day was thrown away. So the budget counts only the time the machine was actually
# awake and the run actually running.
#
# The hour the plist triggers at. Overridable purely so the early-morning branch and
# the wall cutoff below are testable at any hour of the day.
SCHEDULED_HOUR="${SCHEDULED_HOUR:-8}"

# An hour of awake time is generous: a healthy refresh is ~30 minutes of real work
# (767 titles in 45 minutes on 2026-08-31). Reaching an hour without finishing means
# the run is not making progress, which is a fault worth a notification.
MAX_AWAKE_SECONDS="${MAX_AWAKE_SECONDS:-3600}"

# The wall-clock stop exists for one reason only: a run must not still be holding
# the lock when the next scheduled trigger arrives, or the following day gets
# skipped in silence — the 25-hour run that cost 2026-08-30 its refresh. So it is
# not a duration but a point in time, half an hour before the next trigger. A run
# may legitimately span a whole working day; it may not span two.
wall_cutoff() {
  local h="$1"
  if [ "$((10#$(date +%H)))" -lt "$h" ]; then
    date -v"${h}"H -v0M -v0S -v-30M +%s
  else
    date -v+1d -v"${h}"H -v0M -v0S -v-30M +%s
  fi
}

# Set by the watchdog when it notices the machine was suspended mid-run. The gap is
# overridable so the detection path itself can be exercised without shutting a lid:
# SLEEP_GAP_SECONDS=1 makes every ordinary tick look like a suspend.
SLEPT=0
SLEEP_GAP_SECONDS="${SLEEP_GAP_SECONDS:-60}"

# A refresh takes ~20 minutes; if the Mac wakes twice, two runs must not scrape and
# commit over each other. mkdir is atomic, unlike test -f && touch.
DRY_RUN=0
NO_PUSH=0
FORCE=0
PASSTHROUGH=()
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --no-push) NO_PUSH=1 ;;
    --force)   FORCE=1 ;;
    # Anything else goes to `csfd update`, so the whole path can be exercised with
    # --discover-months 1 --refresh-budget 2 instead of a 20-minute scrape.
    *) PASSTHROUGH+=("$arg") ;;
  esac
done

mkdir -p "$LOG_DIR"
exec >>"$LOG" 2>&1

log() { echo "[$(date +%H:%M:%S)] $*"; }

notify() {
  # Only ever called on failure. Success stays silent — that is the whole point.
  /usr/bin/osascript -e "display notification \"$1\" with title \"Streamfinder refresh failed\"" 2>/dev/null || true
}

STATUS_WRITTEN=0
write_status() {
  STATUS_WRITTEN=1
  /bin/cat >"$STATUS" <<JSON
{
  "outcome": "$1",
  "step": "$2",
  "detail": "$3",
  "started_at": "$STAMP",
  "finished_at": "$(date +%Y-%m-%dT%H:%M:%S)",
  "log": "$LOG",
  "commit": "${COMMIT:-}"
}
JSON
}

fail() {
  log "FAILED at $1: $2"
  write_status failed "$1" "$2"
  notify "$1 — $2"
  exit 1
}

# A run that cannot finish has to die rather than hang. The 2026-08-29 run sat in
# `csfd update` for 25 hours; the cost was not that run but the NEXT one — at 08:00
# launchd found the label still busy and skipped the day in silence. macOS ships no
# coreutils `timeout`, hence the hand-rolled watchdog.
run_with_deadline() {
  # Monitor mode so the child starts its own process group, which is what lets the
  # kill path take Playwright's browser down with it. Without it a killed run leaks a
  # chrome-headless-shell still holding its temp profile — pkill by pattern raced the
  # browser's own launch and lost, observed while testing this on 2026-08-31.
  set -m
  "$@" &
  local pid=$!
  set +m
  local started now last delta awake=0 cutoff
  started="$(date +%s)"; last="$started"
  cutoff="$(wall_cutoff "$SCHEDULED_HOUR")"
  log "budget: ${MAX_AWAKE_SECONDS}s awake, hard stop at $(date -r "$cutoff" +%H:%M)"
  while kill -0 "$pid" 2>/dev/null; do
    sleep 10
    now="$(date +%s)"
    delta=$((now - last)); last="$now"
    # A `sleep 10` that came back minutes later means the machine was suspended, so
    # that stretch was never ours to spend. Anything close to ten seconds was.
    if [ "$delta" -gt "$SLEEP_GAP_SECONDS" ]; then
      SLEPT=1
    else
      awake=$((awake + delta))
    fi
    # Keep the lock's mtime moving so a concurrent trigger can tell a long run from
    # an abandoned one without guessing at durations.
    /usr/bin/touch "$LOCK" 2>/dev/null
    if [ "$awake" -ge "$MAX_AWAKE_SECONDS" ]; then
      log "update used ${awake}s of awake time without finishing, killing pid $pid"
      _kill_tree "$pid"
      return 125
    fi
    if [ "$now" -ge "$cutoff" ]; then
      log "reached the hard stop with ${awake}s awake, killing pid $pid"
      _kill_tree "$pid"
      return 124
    fi
  done
  wait "$pid"
}

_kill_tree() {
  # A negative pid is the whole process group — python, Playwright's node shim and
  # the browser it spawned — rather than just the process we happen to hold.
  kill -TERM -- "-$1" 2>/dev/null || kill -TERM "$1" 2>/dev/null
  sleep 10
  kill -KILL -- "-$1" 2>/dev/null || kill -KILL "$1" 2>/dev/null
  # Last net, for a browser that already escaped its group. The profile name is
  # unique to Playwright's own chromium launcher, so this cannot hit a browser the
  # user is looking at.
  /usr/bin/pkill -f 'playwright_chromiumdev_profile' 2>/dev/null
}

if ! mkdir "$LOCK" 2>/dev/null; then
  # Liveness by pid rather than by the lock's age. Age was a fair proxy while a run
  # could not outlive three hours, but a run is now allowed to span a working day
  # while the lid is shut — and an age rule would hand its lock to a second copy
  # while the first was still scraping.
  OTHER="$(/bin/cat "$LOCK/pid" 2>/dev/null || true)"
  if [ -n "$OTHER" ] && kill -0 "$OTHER" 2>/dev/null; then
    log "refresh $OTHER is still running, skipping this one"
    exit 0
  fi
  log "lock held by a process that is gone (${OTHER:-no pid recorded}), taking over"
  /bin/rm -rf "$LOCK" && mkdir "$LOCK"
fi
echo $$ >"$LOCK/pid"
# A bash fatal (unbound variable, syntax error) kills the script mid-line, past every
# fail() call — the run then dies leaving last-run.json describing the PREVIOUS run and
# no notification at all. That silent death is the one failure mode this script exists
# to prevent, so the exit trap reports anything that got out without a status.
on_exit() {
  local code=$?
  /bin/rm -rf "$LOCK"
  if [ "$code" != "0" ] && [ "$STATUS_WRITTEN" = "0" ]; then
    log "died with exit code $code before recording a status"
    write_status failed crash "script aborted with exit code $code, see the log"
    notify "script aborted (exit $code) — see $LOG"
  fi
}
trap on_exit EXIT

# The plist fires this at 08:00 AND at every login (RunAtLoad). The second trigger is
# the whole point: launchd's own catch-up covers a Mac that SLEPT through 08:00, but
# not one that was switched off — that job would otherwise wait for tomorrow. Booting
# at 16:30 should refresh at 16:30.
#
# Two triggers mean this has to decide for itself whether today is already done, so
# the rule is "at most one good run a day": a today-dated ok/no-change is enough to
# stop here. A failed or skipped run is deliberately NOT enough — those should be
# retried at the next opportunity, which is exactly what the next login is.
refreshed_today() {
  [ -f "$STATUS" ] || return 1
  local outcome started
  outcome="$(/usr/bin/sed -n 's/.*"outcome": "\([^"]*\)".*/\1/p' "$STATUS")"
  started="$(/usr/bin/sed -n 's/.*"started_at": "\([^"]*\)".*/\1/p' "$STATUS")"
  case "$outcome" in ok|no-change) ;; *) return 1 ;; esac
  [ "${started%%T*}" = "$(date +%Y-%m-%d)" ]
}
if [ "$FORCE" = "0" ]; then
  if refreshed_today; then
    log "today is already refreshed, nothing to do"
    exit 0
  fi
  # A login before 08:00 is not a missed day, it is an early morning. Running now
  # would only publish staler data and then make the 08:00 trigger a no-op.
  # 10# because `date +%H` yields 08 and the shell would read that as octal.
  if [ "$((10#$(date +%H)))" -lt "$SCHEDULED_HOUR" ]; then
    log "before ${SCHEDULED_HOUR}:00 and today has not run yet — leaving it to the 08:00 trigger"
    exit 0
  fi
fi

cd "$REPO" || fail startup "cannot enter $REPO"
log "refresh starting (dry_run=$DRY_RUN no_push=$NO_PUSH)"

# ── preconditions ────────────────────────────────────────────────────────────
[ -x "$PYTHON" ] || fail startup "python not found at $PYTHON"

if ! "$PG_ISREADY" -q 2>/dev/null; then
  log "postgres is down, starting it on $PGDATA"
  "$PG_CTL" -D "$PGDATA" -l "$PGDATA/server.log" start >/dev/null 2>&1
  for _ in 1 2 3 4 5 6 7 8 9 10; do "$PG_ISREADY" -q 2>/dev/null && break; sleep 2; done
fi
"$PG_ISREADY" -q 2>/dev/null || fail startup "postgres will not start on $PGDATA"

TMDB_API_KEY="$(/usr/bin/grep '^TMDB_API_KEY=' "$REPO/.env" 2>/dev/null | /usr/bin/cut -d= -f2-)"
[ -n "$TMDB_API_KEY" ] || fail startup "TMDB_API_KEY missing from .env"
export TMDB_API_KEY

META="$REPO/streamfinder/static/data/meta.json"
COUNT_BEFORE="$("$PYTHON" -c "import json;print(json.load(open('$META'))['title_count'])" 2>/dev/null || echo 0)"
log "catalog holds $COUNT_BEFORE titles"

# ── the run ──────────────────────────────────────────────────────────────────
UPDATE_ARGS=("${PASSTHROUGH[@]+"${PASSTHROUGH[@]}"}")
[ "$DRY_RUN" = "1" ] && UPDATE_ARGS+=(--dry-run)
log "running csfd update"
# bash 3.2 (what macOS ships) treats an empty array as unbound under `set -u`, so the
# no-flags case — i.e. every real launchd run — needs the same guard as PASSTHROUGH above.
run_with_deadline "$PYTHON" -m csfd_vod.main update "${UPDATE_ARGS[@]+"${UPDATE_ARGS[@]}"}"
UPDATE_RC=$?

# A laptop that spent the day shut is not a broken pipeline. Missing one day costs
# nothing — launchd fires again tomorrow, and `update` is incremental, so the next
# run picks up everything this one would have caught. So a run the Mac slept through
# exits clean and quiet; only a run that stalled while genuinely awake is a fault
# worth waking a human for.
# 125 = an hour of awake time and still not done. The machine was there and the run
# got nowhere, so something is actually wrong and a human should hear about it.
[ "$UPDATE_RC" = "125" ] && fail update "csfd update ran ${MAX_AWAKE_SECONDS}s awake without finishing, killed"

# 124 = the day ran out before enough of it was spent awake. Nothing is broken; the
# laptop was simply shut for most of it. Quiet, and tomorrow starts clean — `update`
# is incremental, so the next run picks up whatever this one would have caught.
if [ "$UPDATE_RC" = "124" ]; then
  log "the day ran out before this run could finish — skipping, the next trigger retries"
  write_status skipped update "machine was asleep for most of the run, nothing published"
  exit 0
fi
# 3 = csfd_vod could not reach csfd.cz at all — no DNS, no interface. The 08:00
# trigger wakes a laptop whose lid has been shut since the night before, and on
# battery `caffeinate -s` cannot hold it awake, so it works in DarkWake bursts with no
# network. That is not a fault to wake a human for; it is the wrong moment. The scrape
# now says so in seconds instead of grinding DNS failures for hours — on 2026-09-01 it
# spent 2h16m that way and then had no budget left for the work once the lid opened.
if [ "$UPDATE_RC" = "3" ]; then
  log "no network reachable — skipping, the next trigger retries"
  write_status skipped update "csfd.cz unreachable (no DNS), nothing published"
  exit 0
fi
[ "$UPDATE_RC" = "0" ] || fail update "csfd update returned $UPDATE_RC"

# It finished, but in fits and starts — say so, because the yield will look thin and
# the reason belongs in the log rather than in a future debugging session.
[ "$SLEPT" = "1" ] && log "note: the Mac slept at least once during this run"

if [ "$DRY_RUN" = "1" ]; then
  log "dry run, stopping before the gates"
  write_status dry-run update ""
  exit 0
fi

# ── gates ────────────────────────────────────────────────────────────────────
log "running the completeness gate"
"$PYTHON" scripts/check_completeness.py || fail gate "check_completeness failed — nothing pushed"

COUNT_AFTER="$("$PYTHON" -c "import json;print(json.load(open('$META'))['title_count'])")"
# A catalog does not shrink on its own. If it does, something upstream broke and the
# gate's canaries are too coarse to see it — a 5% drop is ~2,500 titles.
DROP_OK="$("$PYTHON" -c "print(1 if $COUNT_AFTER >= $COUNT_BEFORE * 0.95 else 0)")"
[ "$DROP_OK" = "1" ] || fail gate "catalog shrank $COUNT_BEFORE → $COUNT_AFTER, refusing to publish"
log "catalog now holds $COUNT_AFTER titles"

# ── publish ──────────────────────────────────────────────────────────────────
if [ -z "$("$GIT" status --porcelain streamfinder/static/data)" ]; then
  log "no data changed, nothing to publish"
  write_status no-change publish ""
  exit 0
fi

"$GIT" add streamfinder/static/data || fail publish "git add failed"
CHANGED="$("$GIT" diff --cached --name-only streamfinder/static/data | /usr/bin/wc -l | /usr/bin/tr -d ' ')"
"$GIT" -c user.name="streamfinder-refresh" -c user.email="toolchest@revolt.bi" \
  commit -q -m "chore(data): daily refresh — $COUNT_AFTER titles, $CHANGED files" \
  || fail publish "git commit failed"
COMMIT="$("$GIT" rev-parse --short HEAD)"
log "committed $COMMIT ($CHANGED files)"

if [ "$NO_PUSH" = "1" ]; then
  log "--no-push, leaving $COMMIT local"
  write_status committed publish "not pushed"
  exit 0
fi

# The account with access is not gh's active one, so the token is fetched per-push
# rather than by switching the user's global account under them.
TOKEN="$("$GH" auth token -u radozoo 2>/dev/null)"
[ -n "$TOKEN" ] || fail publish "gh auth token returned nothing (keychain locked?)"
"$GIT" -c credential.helper= \
  -c credential.helper='!f() { echo "username=radozoo"; echo "password='"$TOKEN"'"; }; f' \
  push -q origin main || fail publish "git push failed"
log "pushed $COMMIT"

write_status ok publish "$CHANGED files"
log "done"
