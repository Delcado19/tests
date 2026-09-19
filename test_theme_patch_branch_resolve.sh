#!/usr/bin/env bash
# theme.patch.sh used to resolve a bare theme-repo URL's branch by calling
# the unauthenticated GitHub REST API (curl .../branches | jq). That API is
# capped at 60 requests/hour for anonymous callers, and the call had no
# error handling: a rate-limited or malformed response left the branch
# array empty, `branch` silently became "", and `git clone -b ""` failed
# with an opaque message (issue #2118 -- bulk theme imports hit the cap and
# some themes failed while others, processed earlier, did not).
#
# The fix lists branches with `git ls-remote --heads` instead: git protocol
# operations are not subject to that REST rate limit, work for a single
# branch, prompt as before for a multi-branch repo, and now fail loudly on
# an unreachable/invalid repo instead of continuing with an empty branch.

. "$(dirname -- "$0")/lib/common.sh"

script="$REPO_ROOT/Configs/.local/lib/hyde/theme.patch.sh"
[ -f "$script" ] || {
    fail "theme.patch.sh not found at $script"
    finish
}

if ! command -v git >/dev/null 2>&1; then
    skip "git is not installed"
    finish
fi

work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT

# Creates a bare-ish git checkout at $1 on initial branch $2, with one
# commit, then adds any further branch names given as extra args (all
# pointing at that same commit).
make_repo() {
    local repo="$1" first="$2"
    git init -q -b "$first" "$repo"
    git -C "$repo" config user.email "test@example.com"
    git -C "$repo" config user.name "test"
    echo readme >"$repo/README.md"
    git -C "$repo" add README.md
    git -C "$repo" commit -q -m init
    shift 2
    for extra in "$@"; do
        git -C "$repo" branch -q "$extra"
    done
}

# Runs theme.patch.sh against an isolated HOME/XDG sandbox so it never
# touches the real machine, feeding $4 to stdin for the branch `select`
# prompt when the repo has more than one branch.
run_patch() {
    local theme="$1" repo_url="$2" home="$3" stdin_input="$4"
    mkdir -p "$home/.config" "$home/.local/share" "$home/.cache" \
        "$home/.local/state" "$home/run"
    env -i \
        HOME="$home" \
        XDG_CONFIG_HOME="$home/.config" \
        XDG_DATA_HOME="$home/.local/share" \
        XDG_CACHE_HOME="$home/.cache" \
        XDG_STATE_HOME="$home/.local/state" \
        XDG_RUNTIME_DIR="$home/run" \
        PATH="${TEST_PATCH_PATH:-/usr/bin:/bin}" \
        bash "$script" "$theme" "$repo_url" --skipcaching \
        <<<"$stdin_input"
}

clone_dir_under() {
    find "$1/.cache/hyde/themepatcher" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -n1
}

# --- a single-branch repo is resolved without any prompt ---
single_repo="$work_dir/single.git"
make_repo "$single_repo" trunk
single_home="$work_dir/home-single"
run_patch demo "file://$single_repo" "$single_home" "" \
    >"$work_dir/single.out" 2>"$work_dir/single.err"

single_clone=$(clone_dir_under "$single_home")
if [ -z "$single_clone" ]; then
    fail "single-branch repo: theme.patch.sh never cloned it (branch resolution failed before git clone)"
else
    got_branch=$(git -C "$single_clone" rev-parse --abbrev-ref HEAD 2>/dev/null)
    [ "$got_branch" = "trunk" ] ||
        fail "single-branch repo: expected 'trunk' checked out, got '$got_branch'"
fi
grep -qi "select a branch" "$work_dir/single.out" "$work_dir/single.err" &&
    fail "single-branch repo: prompted to pick a branch when only one exists"

# --- a multi-branch repo still prompts and clones the selected branch ---
multi_repo="$work_dir/multi.git"
make_repo "$multi_repo" alt main
ordered_branches=$(git ls-remote --heads "file://$multi_repo" | sed 's#.*refs/heads/##')
target_index=$(printf '%s\n' "$ordered_branches" | grep -nx main | cut -d: -f1)
if [ -z "$target_index" ]; then
    fail "multi-branch repo: could not find 'main' via git ls-remote to set up the test"
else
    multi_home="$work_dir/home-multi"
    run_patch demo "file://$multi_repo" "$multi_home" "$target_index" \
        >"$work_dir/multi.out" 2>"$work_dir/multi.err"

    multi_clone=$(clone_dir_under "$multi_home")
    if [ -z "$multi_clone" ]; then
        fail "multi-branch repo: theme.patch.sh never cloned it"
    else
        got_branch=$(git -C "$multi_clone" rev-parse --abbrev-ref HEAD 2>/dev/null)
        [ "$got_branch" = "main" ] ||
            fail "multi-branch repo: expected the selected branch 'main' checked out, got '$got_branch'"
    fi
fi

# --- an unreachable/invalid repo fails loudly instead of cloning branch "" ---
missing_home="$work_dir/home-missing"
run_patch demo "file://$work_dir/does-not-exist.git" "$missing_home" "" \
    >"$work_dir/missing.out" 2>"$work_dir/missing.err"
missing_status=$?
[ "$missing_status" -ne 0 ] ||
    fail "unreachable repo: theme.patch.sh exited 0 instead of reporting the failure"
grep -q "ERROR" "$work_dir/missing.err" ||
    fail "unreachable repo: no [ERROR] reported for an unreachable repository"
stray=$(clone_dir_under "$missing_home")
[ -z "$stray" ] ||
    fail "unreachable repo: a cache directory was created for a repo that was never cloned (branch silently resolved to empty)"

# --- no network/API dependency remains: curl is never invoked ---
fake_bin="$work_dir/fake-bin"
mkdir -p "$fake_bin"
curl_log="$work_dir/curl-calls.log"
: >"$curl_log"
cat >"$fake_bin/curl" <<EOF
#!/bin/sh
echo "curl was called: \$*" >>"$curl_log"
exit 1
EOF
chmod +x "$fake_bin/curl"
curl_home="$work_dir/home-curl"
TEST_PATCH_PATH="$fake_bin:/usr/bin:/bin" \
    run_patch demo "file://$single_repo" "$curl_home" "" >/dev/null 2>&1

[ -s "$curl_log" ] &&
    fail "theme.patch.sh still shells out to curl to resolve branches: $(cat "$curl_log")"

finish
