#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
cd "$(dirname "$0")/.."
sh tests/run.sh
test "$(sed -n 's/^id=//p' module/module.prop)" = tvddropbear
! grep -q '^updateJson=' module/module.prop
