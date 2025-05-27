#!/bin/bash
set -e

# Default credentials fallback (for dev/test only)
TTYD_USER="${TTYD_USER:-user}"
TTYD_PASS="${TTYD_PASS:-password}"

# Start ttyd in foreground (must be last)
exec /usr/local/bin/ttyd -i 0.0.0.0 -p 7681 --credential "${TTYD_USER}:${TTYD_PASS}" --writable bash -c "cd /workspace && bash"


