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
# Usage:  scripts/refresh.sh [--dry-run] [--no-push] [any `csfd update` flag]

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

LOG_DIR="$REPO/logs/refresh"
STAMP="$(date +%Y-%m-%dT%H%M%S)"
LOG="$LOG_DIR/$STAMP.log"
STATUS="$LOG_DIR/last-run.json"
LOCK="$LOG_DIR/.lock"

# A refresh takes ~20 minutes; if the Mac wakes twice, two runs must not scrape and
# commit over each other. mkdir is atomic, unlike test -f && touch.
DRY_RUN=0
NO_PUSH=0
PASSTHROUGH=()
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --no-push) NO_PUSH=1 ;;
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

if ! mkdir "$LOCK" 2>/dev/null; then
  # A lock older than three hours is a crashed run, not a running one.
  if [ -n "$(/usr/bin/find "$LOCK" -maxdepth 0 -mmin +180 2>/dev/null)" ]; then
    log "stale lock from a crashed run, taking over"
    /bin/rm -rf "$LOCK" && mkdir "$LOCK"
  else
    log "another refresh is still running, skipping this one"
    exit 0
  fi
fi
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
# no-flags case — i.e. every real launchd run — needs the same guard as line 119.
"$PYTHON" -m csfd_vod.main update "${UPDATE_ARGS[@]+"${UPDATE_ARGS[@]}"}" || fail update "csfd update returned non-zero"

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
