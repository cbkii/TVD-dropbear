#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Manager Action is read-only. Activation is explicit through ADB.
MODDIR=${0%/*}
exec /system/bin/sh "$MODDIR/tvddctl" status
