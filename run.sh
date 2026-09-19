#!/usr/bin/env sh
# Runs every test case in this directory and reports the result.
#
# Usage:
#   tests/run.sh            run every case
#   tests/run.sh binds      run the cases whose name contains "binds"
#
# A case is any executable tests/test_*.sh. It prints its own diagnostics and
# exits non-zero on failure.

set -u

TESTS_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
export TESTS_DIR
tests_dir=$TESTS_DIR
# Honour a pre-set REPO_ROOT so the suite can be pointed at another tree.
REPO_ROOT=${REPO_ROOT:-$(CDPATH='' cd -- "$tests_dir/.." && pwd)}
export REPO_ROOT

filter=${1:-}
total=0
failed=0

# Colour only where it helps (an attached terminal, or CI's log viewer,
# which renders ANSI); plain text otherwise so redirected/grepped output
# stays exact.
if [ -t 1 ] || [ -n "${CI:-}" ]; then
    c_red='\033[31m'
    c_green='\033[32m'
    c_reset='\033[0m'
else
    c_red=''
    c_green=''
    c_reset=''
fi

for case_path in "$tests_dir"/test_*.sh; do
    [ -f "$case_path" ] || continue

    case_name=$(basename "$case_path" .sh)
    if [ -n "$filter" ]; then
        case "$case_name" in
            *"$filter"*) ;;
            *) continue ;;
        esac
    fi

    total=$((total + 1))
    printf '%s\n' "$case_name"

    # An executable case runs under its own shebang; a plain file still runs,
    # so a forgotten chmod does not silently drop coverage.
    if [ -x "$case_path" ]; then
        "$case_path"
        status=$?
    else
        sh "$case_path"
        status=$?
    fi

    if [ "$status" -eq 0 ]; then
        printf "  ${c_green}ok${c_reset}\n"
    else
        printf "  ${c_red}FAILED${c_reset}\n"
        failed=$((failed + 1))
    fi
done

if [ "$total" -eq 0 ]; then
    printf 'no test cases matched\n' >&2
    exit 1
fi

if [ "$failed" -eq 0 ]; then
    printf '\n%d case(s), %d failed\n' "$total" "$failed"
else
    printf "\n%d case(s), ${c_red}%d failed${c_reset}\n" "$total" "$failed"
fi
[ "$failed" -eq 0 ]
