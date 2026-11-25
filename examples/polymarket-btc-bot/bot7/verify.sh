#!/bin/bash
# Checks that bot 7's code is exactly the tested version (SHA-256 fingerprints in SHA256SUMS).
cd "$(dirname "$0")"
if shasum -a 256 -c SHA256SUMS --quiet 2>/dev/null; then echo "OK: bot 7 code matches the tested version."; exit 0; fi
echo "STOP: bot 7 code has been changed or damaged. Re-download the folder from the repo."; exit 1
