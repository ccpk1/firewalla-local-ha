#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: ./utils/quick_lint.sh [--fix]

Runs the repository Ruff checks from the repo root.

Options:
  --fix    Apply safe Ruff fixes and format the repo in place.
EOF
}

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

mode="check"

case "${1-}" in
    "")
        ;;
    --fix)
        mode="fix"
        ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        echo "Unknown argument: ${1}" >&2
        usage >&2
        exit 2
        ;;
esac

if [[ "$mode" == "fix" ]]; then
    python -m ruff check . --fix
    python -m ruff format .
else
    python -m ruff format --check .
    python -m ruff check .
fi