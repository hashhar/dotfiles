#!/bin/bash
# Blocks file operations targeting the main repo checkout when Claude is running
# in a git worktree. Prevents the common mistake of reading/editing the main
# repo instead of the worktree directory.
#
# Handles: Read, Edit, Write, Glob, Grep
#
# Exceptions (allowed even from main repo):
#   1. $MAIN_REPO_ROOT/.claude/** - meta/config, not branch-specific
#   2. CLAUDE.md files (Read only) - project instructions don't vary per branch;
#      worktrees may not have them if the branch predates the file

set -euo pipefail

INPUT=$(cat)

CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
[ -z "$CWD" ] && exit 0

# Extract tool name and file path early so we can bail before expensive git work
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=""
case "$TOOL_NAME" in
  Read|Edit|Write)
    FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
    ;;
  Glob|Grep)
    FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.path // empty')
    ;;
  *)
    exit 0
    ;;
esac

[ -z "$FILE_PATH" ] && exit 0

# Detect worktree: in a worktree, --git-dir != --git-common-dir
GIT_INFO=$(git -C "$CWD" rev-parse --git-dir --git-common-dir --show-toplevel 2>/dev/null) || exit 0
GIT_DIR=$(sed -n '1p' <<< "$GIT_INFO")
GIT_COMMON=$(sed -n '2p' <<< "$GIT_INFO")
WORKTREE_ROOT=$(sed -n '3p' <<< "$GIT_INFO")
[ "$GIT_DIR" = "$GIT_COMMON" ] && exit 0  # Not a worktree

# git-common-dir is the .git dir of the main repo and its parent is the main repo root
MAIN_REPO_ROOT=$(cd "$GIT_COMMON/.." && pwd 2>/dev/null) || exit 0

[[ "$FILE_PATH" != /* ]] && FILE_PATH="$CWD/$FILE_PATH"

# Normalize FILE_PATH to collapse .. segments. MAIN_REPO_ROOT (from cd+pwd) and
# WORKTREE_ROOT (from git rev-parse --show-toplevel) are already canonical.
# TODO: Find some way to avoid python here, realpath on mac fails if path doesn't exist
FILE_PATH=$(python3 -c "import os,sys; print(os.path.normpath(sys.argv[1]))" "$FILE_PATH")

# Paths outside the main repo entirely (other projects, /tmp/, ~/) are unaffected.
[[ "$FILE_PATH" == "$MAIN_REPO_ROOT"/* ]] || exit 0
[[ "$FILE_PATH" != "$WORKTREE_ROOT"/* ]]  || exit 0

# Exception 1: .claude/ is meta/config, never branch-specific
[[ "$FILE_PATH" == "$MAIN_REPO_ROOT/.claude"/* ]] && exit 0

# Exception 2: CLAUDE.md files (reads only)
if [[ "$TOOL_NAME" == "Read" ]] && [[ "$(basename "$FILE_PATH")" == "CLAUDE.md" ]]; then
  exit 0
fi

echo "Blocked: '$FILE_PATH' is in the main repo ($MAIN_REPO_ROOT) but current session is in worktree ($WORKTREE_ROOT). Use the worktree path." >&2
exit 2
