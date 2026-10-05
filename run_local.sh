#!/bin/sh
# Hourly runner. Posts to the LIVE channel. Edit REPO and the env exports for your setup.
# Secrets belong in your keychain or a secrets manager; export them here from there,
# not as literals in this file.
set -u
REPO="${DEMO_INTEL_HOME:-$HOME/demo-request-intel-agent}"
LOG="$REPO/state/runner.log"
mkdir -p "$REPO/state"
cd "$REPO" || exit 1

# Example (macOS keychain): export SLACK_BOT_TOKEN="$(security find-generic-password -s demo-intel-slack -w)"

echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) START" >> "$LOG"
python3 -m demo_intel --live >> "$LOG" 2>&1
rc=$?
echo "----- $(date -u +%Y-%m-%dT%H:%M:%SZ) END exit=$rc" >> "$LOG"
exit $rc
