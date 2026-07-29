#!/usr/bin/env bash
# Thin delegator: the real implementation is init.py (see that file for why —
# short version: a few bash pitfalls around `local` chaining and `pipefail`
# on empty-match greps caused silent early exits, and Python's stdlib handles
# the config-file reconcile logic far more safely).
#
#   ./infra/init.sh            # provision + reconcile tfvars + .env
#   ./infra/init.sh env        # reconcile backend/.env only
#   ./infra/init.sh destroy    # tear everything down
set -euo pipefail
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/init.py" "$@"
