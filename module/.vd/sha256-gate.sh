#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Integrity of the extracted package. External ZIP digest must be verified separately.
[ -f "$MODPATH/manifest.sha256" ] || abort 'Missing integrity manifest'
( cd "$MODPATH" && sha256sum -c manifest.sha256 ) || abort 'TVD payload integrity check failed'
