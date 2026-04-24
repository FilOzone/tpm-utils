#!/usr/bin/env bash
# Run tests across all packages in the tpm-utils monorepo.
#
# Usage:
#   ./scripts/test-all.sh              # run all integration tests
#   ./scripts/test-all.sh -k "test_list"  # pass extra pytest args
#
# Requires: uv, gh (for GITHUB_TOKEN fallback)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Ensure GITHUB_TOKEN is set (integration tests need it).
if [ -z "${GITHUB_TOKEN:-}" ]; then
    if command -v gh &>/dev/null; then
        GITHUB_TOKEN="$(gh auth token 2>/dev/null || true)"
        export GITHUB_TOKEN
    fi
fi

if [ -z "${GITHUB_TOKEN:-}" ]; then
    echo "WARNING: GITHUB_TOKEN not set and gh CLI unavailable — integration tests will be skipped." >&2
fi

PACKAGES=(
    ghprojects-client
    filozzy-mcp
    foc-pr-report
)

FAILED=0
RESULTS=""

for pkg in "${PACKAGES[@]}"; do
    pkg_dir="$REPO_ROOT/$pkg"
    if [ ! -d "$pkg_dir" ]; then
        echo "--- SKIP: $pkg (directory not found) ---"
        RESULTS="$RESULTS|$pkg:skip"
        continue
    fi

    test_dir="$pkg_dir/tests"
    if [ ! -d "$test_dir" ] || [ -z "$(find "$test_dir" -name 'test_*.py' -print -quit 2>/dev/null)" ]; then
        echo "--- SKIP: $pkg (no test files) ---"
        RESULTS="$RESULTS|$pkg:skip"
        continue
    fi

    echo ""
    echo "=== $pkg ==="
    pushd "$pkg_dir" > /dev/null

    set +e
    uv run pytest tests/ -v "$@" 2>&1
    rc=$?
    set -e

    popd > /dev/null
    RESULTS="$RESULTS|$pkg:$rc"
    if [ "$rc" -ne 0 ]; then
        FAILED=1
    fi
done

# Summary
echo ""
echo "============================== Summary =============================="
IFS='|'
for entry in $RESULTS; do
    [ -z "$entry" ] && continue
    pkg="${entry%%:*}"
    code="${entry#*:}"
    if [ "$code" = "skip" ]; then
        printf "  %-25s SKIPPED\n" "$pkg"
    elif [ "$code" -eq 0 ]; then
        printf "  %-25s PASSED\n" "$pkg"
    else
        printf "  %-25s FAILED (exit %s)\n" "$pkg" "$code"
    fi
done
unset IFS
echo "====================================================================="

exit $FAILED
