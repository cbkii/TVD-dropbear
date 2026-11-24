#!/usr/bin/env sh
# SPDX-License-Identifier: Apache-2.0
set -eu
cd "$(dirname "$0")/.."
for f in module/*.sh module/common/*.sh module/tvddctl; do sh -n "$f"; done
for f in scripts/build.sh scripts/build-bundles.sh; do bash -n "$f"; done
python3 -m py_compile scripts/package.py tools/*.py
. ./module/common/vddropbear.sh
for bind in 127.0.0.1 192.168.1.22 10.2.3.4 172.16.2.4 172.31.9.4; do valid_bind "$bind"; done
for bind in 0.0.0.0 8.8.8.8 172.32.1.2 127.0.0.2 192.168.001.2 192.168.1.255 192.168.1.0 '127.0.0.1;id' '1.2.3' ''; do
    if valid_bind "$bind"; then echo "unsafe bind accepted: $bind" >&2; exit 1; fi
done
for port in 1024 2222 65535; do valid_port "$port"; done
for port in 0 22 65536 0002222 2e3 '2222;id' ''; do
    if valid_port "$port"; then echo "unsafe port accepted: $port" >&2; exit 1; fi
done
# Pure parser checks use an isolated directory, never Android system paths.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
CONFIG=$tmp/config
private_file() { [ -f "$1" ] && [ ! -L "$1" ]; }
printf 'ENABLED=0\nBIND=127.0.0.1\nPORT=2222\n' > "$CONFIG"
load_config
[ "$ENABLED" = 0 ] && [ "$BIND" = 127.0.0.1 ] && [ "$PORT" = 2222 ]
printf 'ENABLED=0\nBIND=127.0.0.1\nPORT=2222\nENABLED=1\n' > "$CONFIG"
if load_config; then exit 1; fi
printf 'ENABLED=0\nBIND=127.0.0.1\nPORT=2222\nX=$(touch %s/pwned)\n' "$tmp" > "$CONFIG"
if load_config; then exit 1; fi
[ ! -e "$tmp/pwned" ]
# Filesystem regressions: do not pass /dev/null as PID file or kill by process name.
if grep -Ev '^[[:space:]]*#' module/common/vddropbear.sh module/uninstall.sh | grep -Eq '(-P[[:space:]]+/dev/null|pkill|killall)'; then exit 1; fi
grep -Fq 'DROPBEAR_SVR_PASSWORD_AUTH 0' patches/localoptions.h
grep -Fq 'DROPBEAR_SVR_MULTIUSER 0' patches/localoptions.h
grep -Fq 'ENABLED=0' module/common/config.default
test ! -d module/vdlu
test ! -d module/webroot
sh tests/lifecycle.sh
python3 -m unittest discover -s tests -p 'test_*.py'
echo 'Source/host tests passed; physical validation NOT performed.'
