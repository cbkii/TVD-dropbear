# TVD engineering reference

## Design
Upstream baseline v1.11 (5db14725c51be34e22c7fa9d3b7df491fa77a4c9). Preserve Dropbear cryptography, Android PTY, dynamic Bionic linkage, issue #1 private /dev key shim and PR #2 normal PID file. Remove VDLU, upstream feed, passwords and UI. ARM32/ARM64; daemon API 24, bundles API 28. No IPv6 or forwarding in first TV profile. IPv4 loopback or explicit RFC1918 address; no wildcard/public binds. No legacy scp -O; modern scp uses SFTP. rsync does not preserve ACL/xattrs in this build. Host key and public keys persist in root-owned /data/adb/tvddropbear. DE storage requires explicit acceptance; device encryption depends on firmware. Root credentials are not a privilege sandbox.

## Before install
Use existing ADB with explicit -s SERIAL; verify root, SDK, ABI, getenforce, /dev/null character device, crypto state, toybox setsid, stat, awk, available listener ports and recovery. Reject coexistence with upstream; stop and remove it separately, preserve backups; never silently import credentials. Build exact ZIP, verify SHA256 and provenance. No physical tests have been run at this baseline. Test disposable extraction at /data/local/tmp with a separate test state namespace only after reviewing path isolation; current module uses fixed /data/adb/tvddropbear even outside Magisk, so do not run on a device with an existing installation.

## Provision
Fresh installation does not enable the listener. Keep ADB reachable; use ADB root for lifecycle. On Magisk installed path:
    adb -s SERIAL shell "su -c '/data/adb/modules/tvddropbear/tvddctl init --accept-de-storage'"
Generate Ed25519 client keys on the host (one per agent). Pass only public key via stdin:
    adb -s SERIAL shell "su -c '/data/adb/modules/tvddropbear/tvddctl keys add'" < agent.pub
    adb -s SERIAL shell "su -c '/data/adb/modules/tvddropbear/tvddctl fingerprint'"
Use authenticated ADB to verify the host fingerprint before trusting SSH. Enable/start only after owner authorises persistent service:
    adb -s SERIAL shell "su -c '/data/adb/modules/tvddropbear/tvddctl enable'"
    adb -s SERIAL shell "su -c '/data/adb/modules/tvddropbear/tvddctl start'"
    adb -s SERIAL forward tcp:2222 tcp:2222
    ssh -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -i agent_key -p 2222 root@127.0.0.1
Provision known_hosts via independently verified fingerprint first. For direct LAN, stop via ADB, set BIND to reserved private address, start. No forwarding or router exposure. The current boot entry makes one bounded start attempt; a LAN address not assigned at boot may require manual start. No automatic retries beyond initial readiness. Use ADB if SSH fails.

## Lifecycle and rollback
tvddctl status --json, doctor, logs, fingerprint, keys list/add/remove, config show/set BIND/PORT, enable/disable/start/stop/restart. Key revocation prevents future use; existing sessions are not forcibly terminated. Stop targets only verified listener; sessions may survive. Disable writes ENABLED=0 then stops listener. If ambiguous state, inspect PID, /proc/PID/exe, /proc/PID/stat and sockets via ADB; never blindly clear ownership or kill by name. For lock left by crash, verify no controller/start in flight before removing the empty control.lock directory. Reboot only after approved rollback and ADB recovery verified. Magisk disable/remove is separate from listener state; uninstall retains keys and configuration. Back up before upgrade; stop via ADB and close sessions before changing native binaries. Never delete /dev/null or chmod Android parent directories. Do not run root agent sessions in parallel for mutations.

## Qualification gates
- Native binaries: ELF ABI/API, on-device help/version, keygen, PTY, command exit status, SFTP and rsync hashes. Reject passwords, unknown keys and non-root usernames.
- Compare SSH-root, ADB-shell and ADB-root: id, getenforce, namespaces and platform tools am, pm, cmd, dumpsys, service, settings, content, app_process, logcat. Do not weaken security.
- Measure baseline ADB only, upstream stock (offline updater risk; controlled test only), configured upstream and TVD. Capture PSS, CPU ticks, process counts, idle outbound traffic, startup, concurrent sessions, transfer hashes and latency, standby/wake, network loss, reboot/upgrade/rollback. No introduced wakelock or idle workers; target under 3 MiB idle PSS, measure rather than assume.
- Verify /dev/null remains a character device through all lifecycle tests; verify unrelated processes untouched, stale PID/lock fail closed, occupied port fails, key revocation and host key persistence.
- Actual A4 acceptance and independent review required before persistent LAN use or stable release. Maintain evidence by SHA and artifact hash.

## Known limitations and follow-up
First candidate has no live-device validation, no IPv6, no legacy SCP, no remote-forwarding, no password, no isolated non-root account, no persistent watchdog. Boot bind timing, platform env, PID races and actual /proc socket availability require qualification. Status logs contain last transition only; no growing daemon log. For detailed errors use a controlled foreground diagnostic after stopping listener; never start a competing listener. Use dedicated host keys and strict host checking. Host helper explicitly selects context, never retries ambiguous mutations.
