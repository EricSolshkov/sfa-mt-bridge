#!/system/bin/sh
# Layout: ../config.json, ../RuleProviders/, ./out/config.json.
# Run with MT Manager (root) or: sh update-now.sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SFA_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
sh "$SCRIPT_DIR/run-android.sh" \
  --config "$SFA_ROOT/config.json" \
  --output "$SCRIPT_DIR/out/config.json" \
  "$@"
