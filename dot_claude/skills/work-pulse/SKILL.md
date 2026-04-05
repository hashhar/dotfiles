---
name: work-pulse
description: "Unified work-in-progress audit across GitHub PRs/issues, Jira, Slack saves/DMs, Google Docs action items, local git branches, and Obsidian todos. Outputs an Eisenhower matrix report. Use when asked to run a work review, check what's in progress, catch up on tasks, or when the user mentions losing track of work or juggling too many things."
disable-model-invocation: true
---

# Work Pulse

A periodic audit of everything you're working on, unified into one prioritized view.

Run this every few days to avoid losing track of in-flight work.

## Setup

**Start every run by reading `context.md`** in this skill's directory - it contains all environment-specific values (GitHub orgs, Jira site, Slack IDs, team members, paths). If it doesn't exist, read `context.example.md` and tell the user to create `context.md` from it before continuing.

All references to specific orgs, usernames, URLs, paths, and people in this skill come from `context.md`.

## Stakeholder tiers

Derived from the Manager, PM, T2 Stakeholders, and Teammates listed in `context.md`:

| Tier | Source field | Effect on priority |
|------|-------------|--------------------|
| T1 - Manager + PM | Manager, PM | Bump to Q1 or top of Q2 |
| T2 - Stakeholders | T2 Stakeholders | Q2 by default |
| T3 - Teammates | Teammates | Q2/Q3 based on urgency |
| T4 - External / OSS | Anyone else | Q3/Q4 unless escalated |

## Step 1: Collect data in parallel

Run all sources. A partial report with a note about what failed is better than no report.

### 1a. Local git branches

Find every local branch that looks like personal work:

```bash
find $REPOS_DIR -maxdepth 4 -name ".git" -type d | sed 's|/.git||' | while read repo; do
  git -C "$repo" branch --format="%(refname:short)|%(committerdate:iso8601)|%(committerdate:relative)" 2>/dev/null \
  | grep -vE "^\s*(main|master|develop|HEAD)\|" \
  | grep -vE "^\s*release-[0-9]" \
  | grep -vE "^\s*pr-[0-9]" \
  | while IFS="|" read branch date relative; do
    echo "$repo | $branch | $date | $relative"
  done
done
```

**Exclude**: `main`, `master`, `develop`, `release-*` (LTS branches in work org repos, not personal work), `pr-*` (remote tracking branches). Focus on branches that look like work you started.

For each branch, check whether a PR exists:
```bash
gh pr list --head $BRANCH_NAME --state open --json number,title,url 2>/dev/null
```

**Staleness rule**: Any branch with last commit >30 days is stale and must be either deleted or shipped - no exceptions. Show it regardless of priority.

### 1b. GitHub: open PRs authored by you

```bash
gh search prs --author @me --state open --limit 50
```

For each PR note: repo, title, URL, last updated, whether it's a draft, and review decision (if you can get it via `gh pr view $NUMBER --repo $REPO --json reviewDecision,reviews`).

Also fetch PRs where your review is requested:
```bash
gh search prs --review-requested @me --state open --limit 30
```

### 1c. GitHub: open issues assigned to you

```bash
gh search issues --assignee @me --state open --limit 30
```

Focus on issues updated in the last 6 months. Issues last updated before that are low-signal noise.

### 1d. Jira

Use the Jira MCP with the site from `context.md`:

```
JQL: assignee = currentUser() AND status not in (Done, Closed, Resolved) ORDER BY priority ASC, duedate ASC
```

For each issue collect: key, summary, status, priority, due date, reporter name.

**Optional - check RM roadmap for current H1 priorities**: Use the Roadmap URL from `context.md`. Items on the H1 roadmap are implicitly higher priority than items that don't appear there, even if their Jira priority field isn't set accordingly.

### 1e. Slack "Later" saves and reminders

Search for messages saved for later (the "Later" list in Slack UI):
```
is:saved
```

This returns everything in your Later list. Filter for task-like items - messages where:
- Someone is explicitly asking you to do something ("can you", "could you", "please review", "lmk what you think", a question directed at you)
- A doc was shared for your input/review
- You're @mentioned and a response is expected
- It's from the Manager or PM (always worth surfacing - see `context.md`)

Discard informational saves: meeting recordings, link shares, FYI posts, things that don't require action from you.

Also search for active Slack reminders:
```
in:Slackbot
```
Only surface reminders that haven't been marked as done (look for "I'll remind you" messages without a corresponding "marked as complete").

### 1f. Slack unreplied DMs

Two directions matter:
- **You haven't replied**: someone messaged you and you haven't responded
- **They haven't replied**: you messaged someone and are still waiting

**Step 1** - find recently active DM channels. Run both:
```
to:me -from:me channel_types:im after:<date 14 days ago>
```
```
from:me channel_types:im after:<date 14 days ago>
```

**Step 2** - collect the unique DM channel IDs from the results (deduplicate). For each distinct channel, use `slack_read_channel` to fetch the last ~5 messages to see who sent the most recent one.

**Step 3** - classify:
- Last message is from **someone else** -> you haven't replied -> surface as potential action item
- Last message is from **you**, sent >24h ago with no response -> they haven't replied -> surface if it looks like you were waiting on something

**Filtering**: Skip DMs where the conversation clearly ended naturally (e.g., both sides said thanks/goodbye, or it was an FYI with no question). Focus on messages that contain a question, a request, or an open thread. Also skip bot DMs (Jira, GitHub, Slackbot notifications).

Key team Slack channels for context: see Team channels in `context.md`.

### 1g. Google Docs action items (via Gmail)

Search Gmail for Google Docs notifications where you were assigned or mentioned:
```
from:comments-noreply@docs.google.com newer_than:90d
```

Surface:
- "assigned you an action item" -> definitely a task
- "mentioned you in a comment" -> likely needs a response
- Recent activity on docs where you've been tagged in a thread

### 1h. Obsidian uncompleted todos

Scan the active vault for recent uncompleted `- [ ]` items (use the Obsidian daily notes path from `context.md`):
```bash
find $OBSIDIAN_DAILY_DIR -name "*.md" | sort | tail -30 | xargs grep -l "- \[ \]" 2>/dev/null
```

Then extract the todos:
```bash
grep -r "- \[ \]" $OBSIDIAN_DAILY_DIR/ 2>/dev/null | tail -50
```

A todo appearing across multiple consecutive daily notes is a **chronic rollover** - flag it as such with a count of how many times it's appeared.

## Step 2: Normalize into tasks

For every item found, note:
- **Source**: `github-pr`, `github-issue`, `jira`, `slack`, `gdocs`, `branch`, `obsidian`
- **Title**: short description
- **Link/ref**: URL or path
- **Last touched**: date of last activity
- **Staleness**: active <=7d, coasting 7-30d, stale >30d
- **Stakeholder signal**: from/involving Manager or PM?
- **Deadline**: explicit due date or milestone?
- **Waiting on you**: is something blocked on your action?

## Step 3: Apply the Eisenhower matrix

### Q1 - Urgent + Important: DO TODAY

- Jira P0 or P1 of any status
- Jira P2 with due date within 14 days, or from Manager/PM
- Anything explicitly requested by the Manager or PM (Slack saves, Jira, Docs action items)
- PRs where you're the author and a reviewer requested changes - they're blocked on you
- Review requests that are >1 business day old (someone is waiting)
- Google Docs action items assigned to you by the Manager or PM
- Unreplied DMs from the Manager or PM that contain a question or request
- Any item stale >30 days with a clear owner (you) - force a decision today

### Q2 - Not Urgent + Important: SCHEDULE THIS WEEK

- Jira P2 with due date 14-45 days out
- Jira P2/P3 from stakeholders with no deadline
- Active PRs you've authored that are awaiting reviewer (you've done your part, but nudge if stale)
- Review requests <1 business day old, or that are OSS/lower-stakes
- Stale review requests (>7 days) that haven't been actioned
- Local branches with open PRs - track to completion
- Local branches without PRs that have commits within 30 days - need a PR or deliberate decision
- Google Docs activity on docs where you're in a comment thread
- Slack saves from teammates (not Manager/PM) asking for review or input
- Unreplied DMs from teammates or external (T3/T4) containing a question/request
- DMs where you messaged someone and are waiting on a reply (>24h, looks like you need an answer to proceed)

### Q3 - Urgent + Not Important: BATCH OR QUICK-WIN

- Slack saves that are requests from non-stakeholders
- Low-priority GitHub issues on personal repos with no deadline
- Obsidian personal todos (non-work)
- OSS PRs awaiting maintainer response - ping them

### Q4 - Not Urgent + Not Important: DECIDE TO ELIMINATE

- Local branches with last commit >30 days and no open PR -> strongly consider deleting
- Very old or clearly abandoned PRs (external repos, drafted 2+ months ago with no activity)
- Low priority Jira issues filed by you years ago with no recent activity
- Chronic Obsidian todos that have rolled over many times with no progress -> kill or commit

## Step 4: Print the report

Use this structure. Keep each item to 1-2 lines - enough to act, not a wall of text.

```
===============================================================
  WORK PULSE  -  <today's date>
===============================================================

SOURCES: GitHub PRs / Jira / Slack / Google Docs / Branches / Obsidian
(note any that failed)

---------------------------------------------------------------
Q1 - URGENT + IMPORTANT  ->  Do today
---------------------------------------------------------------
[TAG]  Title
       URL or path  |  why it's here

---------------------------------------------------------------
Q2 - NOT URGENT + IMPORTANT  ->  Schedule this week
---------------------------------------------------------------

---------------------------------------------------------------
Q3 - URGENT + NOT IMPORTANT  ->  Batch / quick-win
---------------------------------------------------------------

---------------------------------------------------------------
Q4 - NOT URGENT + NOT IMPORTANT  ->  Decide: delete or commit?
---------------------------------------------------------------

---------------------------------------------------------------
SUMMARY
---------------------------------------------------------------
GitHub PRs (authored): N | Reviews requested: N
Jira: N | Slack saves: N | Slack unreplied DMs: N | Google Docs: N
Branches active: N | Branches stale >30d: N
Obsidian todos: N (chronic rollover: N)

Not covered: <any source that errored>
```

**Sorting within each quadrant**: Manager/PM items first -> then by deadline (soonest) -> then by staleness (most stale).

## Notes

- All environment-specific values (Jira site, Slack user ID, paths, team members) come from `context.md` in this directory.
- **release-* branches**: In work org repos these are LTS support branches maintained by the team, not personal work. Exclude them from branch scans.
- **Old Obsidian vault**: if there's a second vault path visible, skip it - only the path in `context.md` is active.
- **Team members**: use the Confluence team page URL from `context.md` if you need the full current roster.
