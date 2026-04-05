#!/bin/bash
input=$(cat)

# --- Extract fields ---
MODEL_NAME=$(echo "$input"                 | jq -r '.model.display_name')
CWD=$(echo "$input"                        | jq -r '.workspace.current_dir')
PROJECT_DIR=$(echo "$input"                | jq -r '.workspace.project_dir')
CONTEXT_WINDOW_SIZE=$(echo "$input"        | jq -r '.context_window.context_window_size // 200000')
CONTEXT_USED_PERCENT=$(echo "$input"       | jq -r '.context_window.used_percentage // 0 | floor')
TOTAL_INPUT_TOKENS=$(echo "$input"         | jq -r '.context_window.total_input_tokens // 0')
TOTAL_OUTPUT_TOKENS=$(echo "$input"        | jq -r '.context_window.total_output_tokens // 0')
OUTPUT_STYLE=$(echo "$input"               | jq -r '.output_style.name // "default"')
AGENT_NAME=$(echo "$input"                 | jq -r '.agent.name // empty')
WORKTREE_NAME=$(echo "$input"              | jq -r '.worktree.name // empty')
WORKTREE_PATH=$(echo "$input"              | jq -r '.worktree.path // empty')
WORKTREE_BRANCH=$(echo "$input"            | jq -r '.worktree.branch // empty')
TOTAL_COST_USD=$(echo "$input"             | jq -r '.cost.total_cost_usd // empty')
RATE_LIMIT_5H_USED_PERCENT=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
RATE_LIMIT_5H_RESETS_AT=$(echo "$input"    | jq -r '.rate_limits.five_hour.resets_at // empty')
RATE_LIMIT_7D_USED_PERCENT=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
RATE_LIMIT_7D_RESETS_AT=$(echo "$input"    | jq -r '.rate_limits.seven_day.resets_at // empty')

# --- Colors ---
CLR_CYAN='\033[36m'; CLR_GREEN='\033[32m'; CLR_YELLOW='\033[33m'; CLR_RED='\033[31m'
CLR_BLUE='\033[34m'; CLR_MAGENTA='\033[35m'; CLR_DIM='\033[2m'; CLR_BOLD='\033[1m'; CLR_RESET='\033[0m'

# --- Progress bar (20 chars) ---
BAR_WIDTH=20
FILLED=$((CONTEXT_USED_PERCENT * BAR_WIDTH / 100))
EMPTY=$((BAR_WIDTH - FILLED))
BAR=""
[ "$FILLED" -gt 0 ] && printf -v F "%${FILLED}s" && BAR="${F// /█}"
[ "$EMPTY"  -gt 0 ] && printf -v E "%${EMPTY}s"  && BAR="${BAR}${E// /░}"

if   [ "$CONTEXT_USED_PERCENT" -ge 90 ]; then BAR_COLOR="$CLR_RED"
elif [ "$CONTEXT_USED_PERCENT" -ge 70 ]; then BAR_COLOR="$CLR_YELLOW"
else                         BAR_COLOR="$CLR_GREEN"; fi

# --- Token formatting helper (awk rounds to 1 decimal with k/M suffix) ---
format_tokens() {
  awk -v n="$1" 'BEGIN {
    if      (n >= 1000000) printf "%.1fM", n/1000000
    else if (n >= 1000)    printf "%.1fk", n/1000
    else                   printf "%d",    n
  }'
}
IN_FMT=$(format_tokens "$TOTAL_INPUT_TOKENS")
OUT_FMT=$(format_tokens "$TOTAL_OUTPUT_TOKENS")
WIN_FMT=$(format_tokens "$CONTEXT_WINDOW_SIZE")

# --- Git info (run against CWD) ---
git_cmd() { git -C "$CWD" --no-optional-locks "$@"; }

GIT_BRANCH=""; GIT_STATUS=""
if git_cmd rev-parse --git-dir >/dev/null 2>&1; then
  GIT_BRANCH=$(git_cmd branch --show-current 2>/dev/null)

  # Staged / modified / untracked counts
  STAGED=$(git_cmd diff --cached --numstat 2>/dev/null | wc -l | tr -d ' ')
  MODIFIED=$(git_cmd diff --numstat 2>/dev/null | wc -l | tr -d ' ')
  UNTRACKED=$(git_cmd ls-files --others --exclude-standard 2>/dev/null | wc -l | tr -d ' ')

  # Ahead / behind upstream
  AHEAD=0; BEHIND=0
  UPSTREAM=$(git_cmd rev-parse --abbrev-ref '@{upstream}' 2>/dev/null)
  if [ -n "$UPSTREAM" ]; then
    AHEAD=$(git_cmd rev-list --count '@{upstream}..HEAD' 2>/dev/null)
    BEHIND=$(git_cmd rev-list --count 'HEAD..@{upstream}' 2>/dev/null)
  fi

  if [ "$STAGED" -eq 0 ] && [ "$MODIFIED" -eq 0 ] && [ "$UNTRACKED" -eq 0 ]; then
    GIT_STATUS="${CLR_GREEN}✓${CLR_RESET}"
  else
    [ "$STAGED"    -gt 0 ] && GIT_STATUS+="${CLR_GREEN}+${STAGED}${CLR_RESET}"
    [ "$MODIFIED"  -gt 0 ] && GIT_STATUS+="${CLR_YELLOW}~${MODIFIED}${CLR_RESET}"
    [ "$UNTRACKED" -gt 0 ] && GIT_STATUS+="${CLR_RED}?${UNTRACKED}${CLR_RESET}"
  fi
  [ "$AHEAD"  -gt 0 ] && GIT_STATUS+=" ${CLR_CYAN}↑${AHEAD}${CLR_RESET}"
  [ "$BEHIND" -gt 0 ] && GIT_STATUS+=" ${CLR_MAGENTA}↓${BEHIND}${CLR_RESET}"
fi

# --- Line 1: model | cwd | project dir | git | style | agent ---
CWD_NAME="${CWD##*/}"
PROJECT_DIR_NAME="${PROJECT_DIR##*/}"

LINE1="${CLR_CYAN}${CLR_BOLD}[${MODEL_NAME}]${CLR_RESET}"
LINE1+=" ${CLR_DIM}cwd:${CLR_RESET}${CWD_NAME}"
[ "$CWD" != "$PROJECT_DIR" ] && LINE1+=" ${CLR_DIM}proj:${CLR_RESET}${PROJECT_DIR_NAME}"
if [ -n "$GIT_BRANCH" ]; then
  LINE1+=" ${CLR_DIM}on${CLR_RESET} ${CLR_BLUE}${GIT_BRANCH}${CLR_RESET} ${GIT_STATUS}"
fi
LINE1+=" ${CLR_DIM}style:${CLR_RESET}${OUTPUT_STYLE}"
[ -n "$AGENT_NAME" ] && LINE1+=" ${CLR_MAGENTA}agent:${AGENT_NAME}${CLR_RESET}"

# --- Line 2: progress bar | token counts | cost ---
LINE2="${BAR_COLOR}${BAR}${CLR_RESET}"
LINE2+=" ${CLR_YELLOW}${CONTEXT_USED_PERCENT}%${CLR_RESET} used of ${WIN_FMT} ctx"
LINE2+=" ${CLR_DIM}|${CLR_RESET} tokens in:${IN_FMT} out:${OUT_FMT}"
[ -n "$TOTAL_COST_USD" ] && LINE2+=" ${CLR_DIM}|${CLR_RESET} $(printf '$%.4f' "$TOTAL_COST_USD")"

# --- Line 3 (optional): rate limits ---
rl_color() {
  local pct=$1
  if   [ "$pct" -ge 90 ]; then printf '%s' "$CLR_RED"
  elif [ "$pct" -ge 70 ]; then printf '%s' "$CLR_YELLOW"
  else                         printf '%s' "$CLR_GREEN"; fi
}

LINE3=""
if [ -n "$RATE_LIMIT_5H_USED_PERCENT" ]; then
  RL_5H_INT=$(printf '%.0f' "$RATE_LIMIT_5H_USED_PERCENT")
  LINE3+="${CLR_DIM}5h:${CLR_RESET} $(rl_color "$RL_5H_INT")${RL_5H_INT}%${CLR_RESET}"
  [ -n "$RATE_LIMIT_5H_RESETS_AT" ] && LINE3+=" ${CLR_DIM}resets $(date -r "$RATE_LIMIT_5H_RESETS_AT" +"%H:%M")${CLR_RESET}"
fi
if [ -n "$RATE_LIMIT_7D_USED_PERCENT" ]; then
  RL_7D_INT=$(printf '%.0f' "$RATE_LIMIT_7D_USED_PERCENT")
  [ -n "$LINE3" ] && LINE3+=" ${CLR_DIM}|${CLR_RESET} "
  LINE3+="${CLR_DIM}7d:${CLR_RESET} $(rl_color "$RL_7D_INT")${RL_7D_INT}%${CLR_RESET}"
  [ -n "$RATE_LIMIT_7D_RESETS_AT" ] && LINE3+=" ${CLR_DIM}resets $(date -r "$RATE_LIMIT_7D_RESETS_AT" +"%H:%M")${CLR_RESET}"
fi

# --- Line 4 (optional): worktree ---
printf '%b\n' "$LINE1"
printf '%b\n' "$LINE2"
[ -n "$LINE3" ] && printf '%b\n' "$LINE3"
if [ -n "$WORKTREE_NAME" ]; then
  LINE4="${CLR_BLUE}worktree:${CLR_RESET} ${WORKTREE_NAME}"
  [ -n "$WORKTREE_BRANCH" ] && LINE4+=" ${CLR_DIM}(${WORKTREE_BRANCH})${CLR_RESET}"
  [ -n "$WORKTREE_PATH"   ] && LINE4+=" ${CLR_DIM}@ ${WORKTREE_PATH}${CLR_RESET}"
  printf '%b\n' "$LINE4"
fi
