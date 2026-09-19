#!/usr/bin/env sh
# Shared helpers for the test cases.

TESTS_DIR=${TESTS_DIR:-$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)}
export TESTS_DIR

# The tree under test. Defaults to the checkout the suite lives in, and can
# be pointed at another one to check it with this suite.
REPO_ROOT=${REPO_ROOT:-$(CDPATH='' cd -- "$TESTS_DIR/.." && pwd)}
export REPO_ROOT

_failures=0

# Colour only where it helps (an attached terminal, or CI's log viewer,
# which renders ANSI); plain text otherwise so redirected/grepped output
# stays exact.
if [ -t 1 ] || [ -n "${CI:-}" ]; then
    _c_red='\033[31m'
    _c_yellow='\033[33m'
    _c_reset='\033[0m'
else
    _c_red=''
    _c_yellow=''
    _c_reset=''
fi

fail() {
    _failures=$((_failures + 1))
    printf "    ${_c_red}fail: %s${_c_reset}\n" "$1"
}

skip() {
    printf "    ${_c_yellow}skip: %s${_c_reset}\n" "$1"
}

finish() {
    if [ "$_failures" -ne 0 ]; then
        printf "    ${_c_red}%d failure(s)${_c_reset}\n" "$_failures"
        exit 1
    fi
    exit 0
}
