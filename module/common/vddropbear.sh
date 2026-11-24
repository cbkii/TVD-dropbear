#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Derived from VD Dropbear (Copyright 2026 VD171); TV lifecycle implementation.
# This library is sourced; it does not perform mutations on load.
DATA=/data/adb/tvddropbear
SHIM=/dev/tvddropbear
STATE=$SHIM/state
KEYS=$DATA/authorized_keys
HOSTKEY=$DATA/host_ed25519
CONFIG=$DATA/config
PIDFILE=$STATE/listener.pid
OWNER=$STATE/listener.identity
LOCK=$STATE/control.lock
BINLINK=$DATA/bin
TOYBOX=/system/bin/toybox

fail() { printf '%s\n' "$*" >&2; return 1; }
private_dir() {
    [ ! -L "$1" ] || return 1
    [ -d "$1" ] || mkdir -m 700 "$1" || return 1
    [ "$(stat -c '%u:%a' "$1")" = 0:700 ]
}
private_file() {
    [ -f "$1" ] && [ ! -L "$1" ] &&
        [ "$(stat -c '%u:%a' "$1")" = 0:600 ]
}
setup() {
    [ "$(id -u)" = 0 ] || { fail 'root required'; return 1; }
    umask 077
    if [ "${1:-}" = inspect ]; then
        [ -d "$DATA" ] && [ ! -L "$DATA" ] && [ "$(stat -c '%u:%a' "$DATA")" = 0:700 ] || return 1
        for dir in "$SHIM" "$STATE"; do
            if [ -e "$dir" ] || [ -L "$dir" ]; then
                [ -d "$dir" ] && [ ! -L "$dir" ] && [ "$(stat -c '%u:%a' "$dir")" = 0:700 ] || return 1
            fi
        done
    else
        private_dir "$DATA" && private_dir "$SHIM" && private_dir "$STATE" || { fail 'unsafe state directory'; return 1; }
    fi
    ABI=$(getprop ro.product.cpu.abi)
    case "$ABI" in armeabi-v7a|arm64-v8a) ;; *) fail "unsupported ABI: $ABI"; return 1;; esac
    BIN=$MODDIR/bin/$ABI
    DAEMON=$BIN/tvddropbear
    [ -x "$DAEMON" ] && [ -x "$BIN/dropbearkey" ] &&
        [ -x "$BIN/sftp-server" ] && [ -x "$BIN/rsync" ] || { fail 'incomplete native payload'; return 1; }
}
valid_bind() {
    # IPv4 loopback or RFC1918 unicast; no wildcard, public, multicast or ambiguous octal.
    case "$1" in ''|*[!0-9.]*) return 1;; esac
    printf '%s\n' "$1" | awk -F. '
      NF!=4 {exit 1}
      {for(i=1;i<=4;i++) if($i !~ /^(0|[1-9][0-9]*)$/ || $i>255) exit 1
       if($0=="127.0.0.1") exit 0
       if($4==0 || $4==255) exit 1
       if($1==10 || ($1==172 && $2>=16 && $2<=31) || ($1==192 && $2==168)) exit 0
       exit 1}'
}
valid_port() {
    case "$1" in ''|*[!0-9]*|0*) return 1;; esac
    [ "${#1}" -le 5 ] && [ "$1" -ge 1024 ] && [ "$1" -le 65535 ]
}
load_config() {
    private_file "$CONFIG" || return 1
    ENABLED= BIND= PORT=
    while IFS='=' read -r k v || [ -n "$k$v" ]; do
        case "$k" in
            ENABLED) [ -z "$ENABLED" ] || return 1; case "$v" in 0|1) ENABLED=$v;; *) return 1;; esac;;
            BIND) [ -z "$BIND" ] && valid_bind "$v" || return 1; BIND=$v;;
            PORT) [ -z "$PORT" ] && valid_port "$v" || return 1; PORT=$v;;
            *) return 1;;
        esac
    done < "$CONFIG"
    [ -n "$ENABLED" ] && [ -n "$BIND" ] && [ -n "$PORT" ]
}
write_config() {
    tmp=$(mktemp "$DATA/config.XXXXXX") || return 1
    printf 'ENABLED=%s\nBIND=%s\nPORT=%s\n' "$ENABLED" "$BIND" "$PORT" > "$tmp" &&
        chmod 600 "$tmp" && mv -f "$tmp" "$CONFIG" || { rm -f "$tmp"; return 1; }
}
lock() {
    mkdir -m 700 "$LOCK" 2>/dev/null || { fail 'control lock held; inspect over ADB, never clear blindly'; return 1; }
    trap 'rmdir "$LOCK" 2>/dev/null || :' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
}
# /proc stat comm can contain spaces and parentheses. Strip through final ")".
start_id() {
    line=$(cat "/proc/$1/stat" 2>/dev/null) || return 1
    rest=${line##*) }
    set -- $rest
    [ "$#" -ge 20 ] && [ "$1" != Z ] || return 1
    printf '%s\n' "${20}"
}
valid_pid() { case "$1" in ''|*[!0-9]*|0*) return 1;; esac; [ "$1" -gt 1 ] 2>/dev/null; }
same_exe() { valid_pid "$1" && [ "$(readlink "/proc/$1/exe" 2>/dev/null)" = "$DAEMON" ]; }
owned() {
    private_file "$OWNER" || return 1
    IFS=' ' read -r listener token extra < "$OWNER" || return 1
    [ -z "$extra" ] && same_exe "$listener" && [ "$(start_id "$listener")" = "$token" ] && [ -n "$token" ]
}
socket_ready() {
    # Verify that the recorded listener owns the exact expected listening socket.
    address=$(printf '%s\n' "$BIND" | awk -F. '{printf "%02X%02X%02X%02X",$4,$3,$2,$1}')
    hexport=$(printf '%04X' "$PORT")
    for fd in /proc/"$1"/fd/*; do
        link=$(readlink "$fd" 2>/dev/null) || continue
        case "$link" in socket:\[*\]) inode=${link#socket:\[}; inode=${inode%\]};; *) continue;; esac
        awk -v addr="$address:$hexport" -v inode="$inode" \
          '$2==addr && $4=="0A" && $10==inode {found=1} END {exit !found}' /proc/net/tcp && return 0
    done
    return 1
}
record() {
    tmp=$(mktemp "$STATE/result.XXXXXX") || return 1
    printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S')" "$*" > "$tmp" &&
        mv -f "$tmp" "$STATE/last-result" || { rm -f "$tmp"; return 1; }
}
prepare() {
    [ -f "$DATA/de-storage-accepted" ] && private_file "$DATA/de-storage-accepted" ||
        { fail 'run init --accept-de-storage over authenticated ADB first'; return 1; }
    private_file "$HOSTKEY" && private_file "$KEYS" && [ -s "$KEYS" ] ||
        { fail 'host key or authorised keys missing'; return 1; }
    [ ! -d /data/adb/modules/vddropbear ] && [ ! -d /data/adb/modules_update/vddropbear ] ||
        { fail 'upstream installation present; migrate explicitly'; return 1; }
    private_dir "$SHIM" && private_dir "$BINLINK" || return 1
    # The Android /data ancestors fail upstream's permission walk. Preserve
    # upstream issue #1's root-owned /dev shim; do not chmod Android ancestors.
    [ ! -e "$SHIM/authorized_keys" ] || [ -L "$SHIM/authorized_keys" ] || return 1
    ln -sfn "$KEYS" "$SHIM/authorized_keys" || return 1
    for tool in sftp-server rsync; do
        [ ! -e "$BINLINK/$tool" ] || [ -L "$BINLINK/$tool" ] || return 1
        ln -sfn "$BIN/$tool" "$BINLINK/$tool" || return 1
    done
}
start_listener() {
    [ "$ENABLED" = 1 ] || { fail 'disabled; provision and enable first'; return 1; }
    [ ! -e "$MODDIR/disable" ] && [ ! -e "$MODDIR/remove" ] || { fail 'Magisk module disabled or pending removal'; return 1; }
    if owned; then
        socket_ready "$listener" && return 0
        fail 'owned listener exists but configured socket is not ready; inspect before restart'; return 1
    fi
    # A previous interrupted start cannot safely be adopted by guessing a PID.
    [ ! -e "$OWNER" ] && [ ! -e "$PIDFILE" ] &&
        [ ! -L "$OWNER" ] && [ ! -L "$PIDFILE" ] ||
        { fail 'stale/ambiguous ownership; inspect over ADB before clearing state'; return 1; }
    prepare || return 1
    # Pass only platform variables needed by app_process and native tooling.
    # No password support is compiled in; forwarding is disabled.
    "$TOYBOX" setsid env -i \
        "PATH=$BINLINK:/system/bin:/system/xbin" "HOME=$DATA" \
        "ANDROID_ROOT=${ANDROID_ROOT:-/system}" "ANDROID_DATA=${ANDROID_DATA:-/data}" \
        "BOOTCLASSPATH=${BOOTCLASSPATH:-}" "SYSTEMSERVERCLASSPATH=${SYSTEMSERVERCLASSPATH:-}" \
        "ANDROID_STORAGE=${ANDROID_STORAGE:-/storage}" "EXTERNAL_STORAGE=${EXTERNAL_STORAGE:-/sdcard}" \
        "ANDROID_RUNTIME_ROOT=${ANDROID_RUNTIME_ROOT:-}" "ANDROID_ART_ROOT=${ANDROID_ART_ROOT:-}" \
        "ANDROID_I18N_ROOT=${ANDROID_I18N_ROOT:-}" "ANDROID_TZDATA_ROOT=${ANDROID_TZDATA_ROOT:-}" \
        "DROPBEAR_AUTHKEYS=$SHIM/authorized_keys" \
        "$DAEMON" -F -e -j -k -T 3 -r "$HOSTKEY" -P "$PIDFILE" -p "$BIND:$PORT" \
        </dev/null >/dev/null 2>&1 &
    spawned=$!
    spawned_token=$(start_id "$spawned") || spawned_token=
    i=0
    while [ "$i" -lt 10 ]; do
        if [ -f "$PIDFILE" ] && [ ! -L "$PIDFILE" ]; then
            candidate=$(cat "$PIDFILE")
            if same_exe "$candidate"; then
                token=$(start_id "$candidate") || break
                if socket_ready "$candidate"; then
                    tmp=$(mktemp "$STATE/owner.XXXXXX") || break
                    printf '%s %s\n' "$candidate" "$token" > "$tmp" &&
                        mv -f "$tmp" "$OWNER" || { rm -f "$tmp"; break; }
                    record "listening $BIND:$PORT pid=$candidate" || :
                    return 0
                fi
            fi
        fi
        i=$((i+1)); sleep 1
    done
    # Do not kill a guessed PID. Only stop our still-running direct child.
    if [ -n "$spawned_token" ] && same_exe "$spawned" && [ "$(start_id "$spawned")" = "$spawned_token" ]; then
        kill "$spawned" 2>/dev/null || :
    fi
    # A failed launch may leave ambiguous state; report instead of guessing ownership.
    record 'start failed: no verified listener; inspect state over ADB' || :
    fail 'listener startup failed'
}
stop_listener() {
    if ! owned; then
        [ ! -e "$OWNER" ] && [ ! -e "$PIDFILE" ] && [ ! -L "$OWNER" ] && [ ! -L "$PIDFILE" ] && return 0
        fail 'ambiguous listener ownership; inspect via ADB'; return 1
    fi
    p=$listener; identity=$token
    # Never signal by name or a stale PID. Recheck immediately before signal.
    same_exe "$p" && [ "$(start_id "$p")" = "$identity" ] || return 1
    kill "$p" || return 1
    i=0
    while same_exe "$p" && [ "$(start_id "$p")" = "$identity" ]; do
        [ "$i" -lt 10 ] || { fail 'listener did not stop; no automatic SIGKILL'; return 1; }
        i=$((i+1)); sleep 1
    done
    rm -f "$OWNER" "$PIDFILE"
    record 'listener stopped; existing authenticated sessions may remain' || :
    return 0
}
status() {
    state=stopped; pid=null
    if owned; then
        pid=$listener
        state=not-ready
        socket_ready "$listener" && state=listening
    elif [ -e "$OWNER" ] || [ -e "$PIDFILE" ] || [ -L "$OWNER" ] || [ -L "$PIDFILE" ]; then
        state=ambiguous
    elif [ "$ENABLED" = 0 ]; then state=disabled
    fi
    if [ "${1:-}" = --json ]; then
        printf '{"state":"%s","enabled":%s,"bind":"%s","port":%s,"abi":"%s","pid":%s}\n' "$state" "$ENABLED" "$BIND" "$PORT" "$ABI" "$pid"
    else
        printf 'state=%s enabled=%s bind=%s port=%s abi=%s pid=%s\n' "$state" "$ENABLED" "$BIND" "$PORT" "$ABI" "$pid"
    fi
}
