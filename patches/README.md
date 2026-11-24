# TVD downstream patches
Base Dropbear tag DROPBEAR_2026.94, Android dynamic Bionic, API 24. Retain upstream Android authorised-key path support; root-only login patch restricts shared key store to root. Password auth compiled out, neutral banner patch removed. SFTP path and PATH use TVD namespace. Keep patches small and verify against pinned source. See docs/TVD-ENGINEERING.md.
