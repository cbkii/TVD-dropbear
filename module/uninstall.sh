#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Keep persistent keys/config for explicit backup or deletion. Never pkill.
MODDIR=${0%/*}
[ -f "$MODDIR/tvddctl" ] && /system/bin/sh "$MODDIR/tvddctl" disable
