#!/usr/bin/env sh
# Demo only: a failing test, to show the tests-pointer workflow opens no PR then.
. "$(dirname -- "$0")/lib/common.sh"
fail "deliberately failing demo test"
finish
