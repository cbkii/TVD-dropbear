#!/usr/bin/env sh
# SPDX-License-Identifier: Apache-2.0
# Deterministic lifecycle tests: override process inspection, never signal real processes.
set -eu
cd "$(dirname "$0")/.."
. ./module/common/vddropbear.sh
testdir=$(mktemp -d)
trap 'rm -rf "$testdir"' EXIT
STATE=$testdir
OWNER=$STATE/owner
PIDFILE=$STATE/pid
LOCK=$STATE/lock
MODDIR=$testdir
BIND=127.0.0.1
PORT=2222
ABI=armeabi-v7a
ENABLED=0
prepare() { : > "$STATE/prepared"; }
owned() { return 1; }
if start_listener; then exit 1; fi
test ! -e "$STATE/prepared"
ENABLED=1
: > "$OWNER"
if start_listener; then exit 1; fi
if stop_listener; then exit 1; fi
test ! -e "$STATE/prepared"
rm "$OWNER"
# A healthy owned listener is an idempotent start, no spawning or key changes.
owned() { listener=1234; token=5678; return 0; }
socket_ready() { [ "$1" = 1234 ]; }
start_listener
test ! -e "$STATE/prepared"
# Never signal an unverified executable or changed process-start identity.
same_exe() { [ "$1" = 1234 ] && [ ! -f "$STATE/signalled" ]; }
start_id() { printf '9999\n'; }
kill() { printf '%s\n' "$1" > "$STATE/signalled"; }
if stop_listener; then exit 1; fi
test ! -e "$STATE/signalled"
start_id() { printf '5678\n'; }
: > "$OWNER"; : > "$PIDFILE"
stop_listener
test "$(cat "$STATE/signalled")" = 1234
test ! -e "$OWNER"
test ! -e "$PIDFILE"
# Controller lock is exclusive; no stale lock guessing.
mkdir "$LOCK"
if lock; then exit 1; fi
rmdir "$LOCK"
# start_id field extraction against a real process, no signal.
# Use an isolated subshell to recover the real function from the source.
( . ./module/common/vddropbear.sh; value=$(start_id "$$"); case "$value" in ''|*[!0-9]*) exit 1;; esac )
echo 'Lifecycle simulation passed (not device qualification).'
