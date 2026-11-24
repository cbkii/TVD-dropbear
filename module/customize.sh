#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
SKIPUNZIP=0
[ "$API" -ge 28 ] || abort 'TVD Dropbear requires Android API 28+'
case "$ARCH" in arm|arm64) ;; *) abort 'ARM Android required';; esac
[ ! -d /data/adb/modules/vddropbear ] && [ ! -d /data/adb/modules_updates/vddropbear ] ||
    abort 'Remove upstream VD Dropbear explicitly before installing TVD Dropbear'
. "$MODPATH/.vd/sha256-gate.sh"
set_perm_recursive "$MODPATH/bin" 0 0 0755 0755
set_perm "$MODPATH/tvddctl" 0 0 0755
set_perm "$MODPATH/service.sh" 0 0 0755
set_perm "$MODPATH/action.sh" 0 0 0755
set_perm "$MODPATH/uninstall.sh" 0 0 0755
DATA=/data/adb/tvddropbear
umask 077
[ ! -L "$DATA" ] || abort 'Unsafe data path'
[ -d "$DATA" ] || mkdir -m 700 "$DATA" || abort 'Cannot create data directory'
[ "$(stat -c '%u:%a' "$DATA")" = 0:700 ] || abort 'Unsafe data directory permissions'
[ ! -L "$DATA/config" ] || abort 'Unsafe config path'
if [ ! -e "$DATA/config" ]; then
    cp "$MODPATH/common/config.default" "$DATA/config" && chmod 600 "$DATA/config" ||
        abort 'Cannot seed disabled configuration'
fi
ui_print 'TVD Dropbear: disabled on fresh install; configure via existing ADB.'
