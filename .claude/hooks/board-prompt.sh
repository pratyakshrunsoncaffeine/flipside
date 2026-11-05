#!/usr/bin/env bash
# UserPromptSubmit: surface board posts that arrived since the last check. Silent when none. Never fails.
# Team members only: a judge or reviewer who clones the repo has no .claude/settings.local.json
# and no BOARD_SIGN, so the board stays out of their session.
[ -n "${BOARD_SIGN:-}" ] || [ -f "${CLAUDE_PROJECT_DIR:-.}/.claude/settings.local.json" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
out="$(tools/board unread 2>/dev/null)" || exit 0
[ -n "$out" ] && printf 'New board posts (issue #%s):\n%s\n' "${BOARD_ISSUE:-1}" "$out"
exit 0
