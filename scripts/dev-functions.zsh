#!/usr/bin/env zsh
# SPDX-License-Identifier: Apache-2.0
# doom-bot - plan worktree helpers (source this file, do not execute)
#
# usage:
#   source scripts/dev-functions.zsh
#   plan-merge <slug>     merge a finished worktree branch into trunk and clean up
#   plan-remove <slug>    drop a worktree branch without merging (abandoned / superseded)

# resolve branch for a worktree slug via nameref; tries phase/<slug>, worktree-<slug>, then bare <slug>
_plan_branch() {
    local -n _ret=$1
    local slug="$2"
    local candidate
    for candidate in "phase/${slug}" "worktree-${slug}" "${slug}"; do
        if git show-ref --verify --quiet "refs/heads/${candidate}"; then
            _ret="${candidate}"
            return 0
        fi
    done
    return 1
}

plan-merge() {
    local slug="$1"
    if [[ -z "$slug" ]]; then
        print -u2 -- 'usage: plan-merge <slug>'
        return 2
    fi

    local branch
    _plan_branch branch "$slug" || {
        print -u2 -- "plan-merge: no local branch for '${slug}' (tried phase/${slug}, worktree-${slug}, ${slug})"
        return 1
    }

    local current
    current="$(git symbolic-ref --short HEAD 2>/dev/null)"
    if [[ "$current" == "$branch" ]]; then
        print -u2 -- "plan-merge: on ${branch} now; switch to trunk first"
        return 1
    fi

    git merge --ff-only "$branch" || return 1

    local wt=".claude/worktrees/${slug}"
    if [[ -d "$wt" ]]; then
        # branch content is already in trunk after ff-only; --force drops any leftover working-tree noise
        git worktree remove "$wt" 2>/dev/null || git worktree remove --force "$wt"
    fi

    git branch --delete "$branch"
    print -P "%F{green}[*]%f merged ${slug}."
}

plan-remove() {
    local slug="$1"
    if [[ -z "$slug" ]]; then
        print -u2 -- 'usage: plan-remove <slug>'
        return 2
    fi

    local branch
    _plan_branch branch "$slug" || {
        print -u2 -- "plan-remove: no local branch for '${slug}' (tried phase/${slug}, worktree-${slug}, ${slug})"
        return 1
    }

    local wt=".claude/worktrees/${slug}"
    if [[ -d "$wt" ]]; then
        git worktree remove "$wt" 2>/dev/null || git worktree remove --force "$wt"
    fi

    git branch --delete --force "$branch"
    print -P "%F{green}[*]%f dropped ${slug}."
}
