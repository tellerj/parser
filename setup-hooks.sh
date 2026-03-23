#!/usr/bin/env bash
# Point git at the tracked hooks/ directory so pre-commit checks
# are enforced for every developer.
#
# Run once after cloning:
#   ./setup-hooks.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
git -C "$REPO_ROOT" config core.hooksPath hooks

echo "Git hooks configured — using hooks/ directory."
echo "Pre-commit hook will enforce zero pyright errors in strict mode."
