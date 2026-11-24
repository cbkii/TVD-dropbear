#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
MODDIR=${0%/*}
exec /system/bin/sh "$MODDIR/tvddctl" boot
