#!/usr/bin/env bash
# ======================================================================
#  VD Dropbear  ::  standalone, configurable rooted SSH daemon
#  A private SSH server for KernelSU/APatch/Magisk. No invasive ADB exposure.
#  Build the bundled file-transfer tools (sftp-server, scp, rsync) per ABI.
#
#  Copyright (C) 2026  VD171
#  SPDX-License-Identifier: Apache-2.0
#
#  Licensed under the Apache License, Version 2.0; you may obtain a copy at
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Site           : https://vd171.ru
#  Site           : https://vd.priv8.ru
#  Source         : https://github.com/VD171/VD-dropbear
#  GitHub         : @VD171 https://github.com/VD171
#  XDA-Developers : @VD171 https://xdaforums.com/m/vd171.4699873/
#  XDA thread     : https://xdaforums.com/t/VD-Dropbear.4808524/
#  Telegram       : @VD_Priv8 https://t.me/VD_Priv8
#  Channel        : @Priv8_VD https://t.me/Priv8_VD
#  Discord        : @VD.Priv8 https://discord.com/users/1296831918989639721
#  E-mail         : vd.priv8@pm.me
# ======================================================================
#
# Cross-compiles the bundled tools as DYNAMIC (linker64 + bionic) binaries for ARM Android ABIs:
#     arm64-v8a  armeabi-v7a
# Outputs land in ../module/bin/<abi>/ as `sftp-server` and `rsync`.
#
#   - sftp-server, scp : OpenSSH portable, built --without-openssl (builtin crypto)
#   - rsync            : with bundled popt + zlib
#   - zlib             : a small static dependency for OpenSSH, built here
#
# Why the OpenSSH build needs special care is documented in docs/BUILDING.md:
# Android's bionic is missing several libc functions, and OpenSSH's configure
# mis-detects a few of them when cross-compiling. The cache seed and source fixes
# below are the auditable result.
#
# Requirements: Android NDK (r27+), git, make, patch, curl/tar. Set NDK.
#   NDK=/path/to/android-ndk ./scripts/build-bundles.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${NDK:?set NDK to your Android NDK path}"
# API 28: dynamic linking exposes only functions available at the target API, and OpenSSH's compat
# macro-redefines some that are missing (e.g. mblen/nl_langinfo), which breaks bionic's headers. API 28
# has them, so the compat stays out of the way. (The daemon has no such deps and stays at its own API.)
: "${API:=28}"
ABIS="${ABIS:-arm64-v8a armeabi-v7a}"

ZLIB_VERSION=1.4
RSYNC_VERSION=3.5.2
OPENSSH_VERSION=10.4p1

WORK="$ROOT/build/bundles"
TOOLCHAIN="$NDK/toolchains/llvm/prebuilt/$(uname | tr '[:upper:]' '[:lower:]')-x86_64/bin"
mkdir -p "$WORK"

triple() {
  case "$1" in
    arm64-v8a)   echo aarch64-linux-android ;;
    armeabi-v7a) echo armv7a-linux-androideabi ;;
    x86)         echo i686-linux-android ;;
    x86_64)      echo x86_64-linux-android ;;
    *) echo "unknown ABI: $1" >&2; exit 1 ;;
  esac
}

fetch() { # url outfile expected-sha256
  if [ ! -f "$2" ]; then
    curl --fail --silent --show-error --location --connect-timeout 15 --max-time 180 --retry 2 -o "$2.tmp" "$1"
    mv "$2.tmp" "$2"
  fi
  printf '%s  %s\n' "$3" "$2" | sha256sum -c -
}
# Hashes from upstream GitHub release assets / OpenSSH release notes.
fetch "https://github.com/madler/zlib/releases/download/v$ZLIB_VERSION/zlib-$ZLIB_VERSION.tar.gz" "$WORK/zlib.tar.gz" 02dd159783677a749c04adbdd02b55b8a2bcc7e054f51b76b549199a916ad584
fetch "https://github.com/RsyncProject/rsync/releases/download/v$RSYNC_VERSION/rsync-$RSYNC_VERSION.tar.gz" "$WORK/rsync.tar.gz" a10d591825251e070f74c98df3daad195def4ed81b4a2de16169026aea33f6c8
fetch "https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-$OPENSSH_VERSION.tar.gz" "$WORK/openssh.tar.gz" ef6026dd2aea8d56059638d5d3262902c892ceba9f88395835e0d06d3fb63238

# OpenSSH cross-compile cache seed: functions bionic lacks that configure
# mis-detects, and the few it reports absent but whose symbol lives in libc.a.
# See docs/BUILDING.md. (Values apply to every ABI at a given API.)
write_openssh_cache() {
  cat > "$1" <<'EOF'
ac_cv_func_recallocarray=no
ac_cv_func_reallocarray=no
ac_cv_func_close_range=no
ac_cv_func_setpwent=no
ac_cv_func_getpwent=no
ac_cv_func_endpwent=no
ac_cv_func_crypt=no
ac_cv_func_futimes=no
ac_cv_func_lutimes=no
ac_cv_func_strtonum=no
ac_cv_func_pledge=no
ac_cv_func_explicit_bzero=no
ac_cv_func_bzero=yes
ac_cv_func_openpty=yes
ac_cv_func_setresuid=yes
ac_cv_func_setresgid=yes
EOF
}

# OpenSSH source fixes for Android (auditable; applied to the extracted tree):
#  - explicit_bzero compat uses memset (bionic's bzero is a macro, unusable as a
#    function pointer, and it has no explicit_bzero of its own);
#  - drop xcrypt.o (needs getpwent/crypt, which bionic lacks) and getrrsetbyname.o
#    (DNSSEC resolver internals); neither is used by sftp-server or scp.
patch_openssh() {
  local src="$1"
  perl -0pi -e 's/static void \(\* volatile ssh_bzero\)\(void \*, size_t\) = bzero;/static void vddb_memzero(void *p, size_t n) { (void)memset(p, 0, n); }\nstatic void (* volatile ssh_bzero)(void *, size_t) = vddb_memzero;/' \
    "$src/openbsd-compat/explicit_bzero.c"
  perl -0pi -e 's/\bxcrypt\.o\b//g; s/\bgetrrsetbyname\.o\b//g' "$src/openbsd-compat/Makefile.in"
  # bionic's getpwuid() leaves pw_gecos == NULL (Android has no GECOS field).
  # pwcopy() NULL-guards pw_passwd but not pw_gecos, so sftp-server SIGSEGVs at
  # startup (getpwuid => pwcopy => xstrdup(NULL)); scp survives because its
  # -t/-f path never calls pwcopy. Guard pw_gecos the same way pw_passwd is.
  perl -0pi -e 's/copy->pw_gecos = xstrdup\(pw->pw_gecos\);/copy->pw_gecos = xstrdup(pw->pw_gecos == NULL ? "" : pw->pw_gecos);/' "$src/misc.c"
}

for ABI in $ABIS; do
  TGT="$(triple "$ABI")"
  CC="$TOOLCHAIN/${TGT}${API}-clang"
  export CC AR="$TOOLCHAIN/llvm-ar" RANLIB="$TOOLCHAIN/llvm-ranlib"
  STRIP="$TOOLCHAIN/llvm-strip"
  ABIWORK="$WORK/$ABI"; mkdir -p "$ABIWORK"
  OUT="$ROOT/module/bin/$ABI"; mkdir -p "$OUT"
  echo "==> building bundles for $ABI ($TGT, API $API, dynamic)"

  # --- zlib (static, for OpenSSH) ---
  ZSRC="$ABIWORK/zlib"; ZPREFIX="$ABIWORK/zlib-prefix"
  rm -rf "$ZSRC"; mkdir -p "$ZSRC"; tar -xzf "$WORK/zlib.tar.gz" -C "$ZSRC" --strip-components=1
  ( cd "$ZSRC"
    CFLAGS="-O2 -fPIC" ./configure --static --prefix="$ZPREFIX" >/dev/null
    make -j"$(nproc)" >/dev/null && make install >/dev/null )

  # --- rsync ---
  RSRC="$ABIWORK/rsync"
  rm -rf "$RSRC"; mkdir -p "$RSRC"; tar -xzf "$WORK/rsync.tar.gz" -C "$RSRC" --strip-components=1
  ( cd "$RSRC"
    ./configure --host="$TGT" \
      --disable-openssl --disable-xxhash --disable-zstd --disable-lz4 --disable-idn \
      --disable-iconv --disable-iconv-open --disable-acl-support --disable-xattr-support \
      --disable-md2man --disable-roll-simd --disable-roll-asm \
      --with-included-popt --with-included-zlib \
      ac_cv_func_lutimes=no ac_cv_func_utimensat=yes \
      CFLAGS="-O2 -fPIE" LDFLAGS="-pie"
    make -j"$(nproc)" >/dev/null
    "$STRIP" rsync )
  cp "$RSRC/rsync" "$OUT/rsync"

  # --- OpenSSH sftp-server ---
  OSRC="$ABIWORK/openssh"
  rm -rf "$OSRC"; mkdir -p "$OSRC"; tar -xzf "$WORK/openssh.tar.gz" -C "$OSRC" --strip-components=1
  patch_openssh "$OSRC"
  write_openssh_cache "$ABIWORK/openssh.cache"
  ( cd "$OSRC"
    ./configure --host="$TGT" \
      --without-openssl --without-pam --without-selinux --without-kerberos5 \
      --without-libedit --disable-utmp --disable-wtmp --disable-lastlog \
      --with-zlib="$ZPREFIX" --cache-file="$ABIWORK/openssh.cache" \
      CFLAGS="-O2 -fPIE -DHAVE_ATTRIBUTE__SENTINEL__=1 -DHAVE_ATTRIBUTE__NONNULL__=1" \
      LDFLAGS="-pie -L$ZPREFIX/lib -Wl,--allow-multiple-definition"
    make -j"$(nproc)" sftp-server >/dev/null
    "$STRIP" sftp-server )
  cp "$OSRC/sftp-server" "$OUT/sftp-server"

  chmod 0755 "$OUT/rsync" "$OUT/sftp-server"
  echo "    -> $OUT/{rsync,sftp-server}"
done

(cd "$WORK" && sha256sum zlib.tar.gz rsync.tar.gz openssh.tar.gz > source-sha256.txt)
echo "==> done. Bundled tools in module/bin/<abi>/"
