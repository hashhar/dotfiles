#!/usr/bin/env python3
"""Extract Claude Code daily chat transcripts into a clean markdown summary.

Reads JSONL session files from ~/.claude/projects/, filters to a target date,
and produces a structured markdown file suitable for further analysis by an LLM.

This script does extraction only — no analysis, topic detection, or friction
classification. That's delegated to the prompt template.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict, namedtuple
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_HOME = Path.home()
_HOME_STR = str(_HOME)
PROJECTS_DIR = _HOME / ".claude" / "projects"
DEFAULT_OUTPUT_DIR = _HOME / ".claude" / "daily-summaries"

# noise for our purposes
_SYSTEM_TAGS = (
    r"system-reminder|local-command-caveat|local-command-stdout|"
    r"command-name|command-message|command-args|user-prompt-submit-hook|"
    r"antml:[a-z_]+"
)
SYSTEM_TAG_PATTERN = re.compile(
    rf"<(?:{_SYSTEM_TAGS})(?:\s[^>]*)?>.*?</(?:{_SYSTEM_TAGS})>",
    re.DOTALL,
)
SYSTEM_TAG_OPEN_CLOSE = re.compile(
    rf"</?(?:{_SYSTEM_TAGS})(?:\s[^>]*)?>",
)
MULTI_NEWLINE = re.compile(r"\n{3,}")
_UNSAFE_FILENAME_CHARS = re.compile(r"[^\w\-]")

ContentAndTools = tuple[str, list[str]]

ParsedMessage = namedtuple("ParsedMessage", [
    "timestamp",    # datetime
    "role",         # "user" or "assistant"
    "text",         # full text content
    "tool_calls",   # list of str (tool call summaries)
])

ParsedSession = namedtuple("ParsedSession", [
    "session_id",
    "session_name",
    "project_path",
    "git_branch",
    "messages",       # list of ParsedMessage
    "start_time",
    "end_time",
    "input_tokens",
    "output_tokens",
    "first_user_message",  # first user message text for summary
])


def strip_system_tags(text: str) -> str:
    """Remove Claude Code system-injected XML tags from text."""
    if "<" in text:
        text = SYSTEM_TAG_PATTERN.sub("", text)
        text = SYSTEM_TAG_OPEN_CLOSE.sub("", text)
        text = MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def parse_iso_timestamp(ts_str: Any) -> datetime | None:
    try:
        ts_str = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError, AttributeError):
        return None


def file_modified_on_date(filepath: Path, target_date: date) -> bool:
    """Check if file's mtime falls on the target date (local time)."""
    try:
        return datetime.fromtimestamp(filepath.stat().st_mtime).date() == target_date
    except OSError:
        return False


def find_sessions_for_date(target_date: date, projects_dir: Path = PROJECTS_DIR) -> list[Path]:
    """Find all session JSONL files that may contain messages from target_date."""
    sessions = []
    next_day = target_date + timedelta(days=1)

    for jsonl_file in projects_dir.glob("*/*.jsonl"):
        if "subagents" in jsonl_file.parts:
            continue

        # mtime is a heuristic, also check next day for async writes
        if not (file_modified_on_date(jsonl_file, target_date)
                or file_modified_on_date(jsonl_file, next_day)):
            continue

        sessions.append(jsonl_file)

    return sessions


def summarize_tool_call(block: dict[str, Any]) -> str:
    """Produce a concise summary of a tool_use content block."""
    name = block.get("name", "Unknown")
    inp = block.get("input", {})

    if name in ("Read", "Write", "Edit"):
        path = inp.get("file_path", "")
        return f"`{name} {path}`"

    if name == "Bash":
        display = inp.get("description", "") or inp.get("command", "")
        return f"`Bash: {display}`"

    if name in ("Grep", "Glob"):
        pattern = inp.get("pattern", "")
        path = inp.get("path", "")
        suffix = f" in {path}" if path else ""
        return f"`{name} \"{pattern}\"{suffix}`"

    if name == "Agent":
        desc = inp.get("description", "")
        agent_type = inp.get("subagent_type", "")
        type_str = f"({agent_type})" if agent_type else ""
        return f"`Agent{type_str} \"{desc}\"`"

    if name == "Skill":
        skill = inp.get("skill", "")
        return f"`Skill: {skill}`"

    if name == "ToolSearch":
        query = inp.get("query", "")
        return f"`ToolSearch: {query}`"

    # Generic fallback - truncate to avoid dumping large payloads
    inp_str = json.dumps(inp) if inp else ""
    if len(inp_str) > 200:
        inp_str = inp_str[:200] + "..."
    return f"`{name}: {inp_str}`"


def extract_user_content(message_obj: dict[str, Any]) -> ContentAndTools:
    """Extract text content from a user message, skipping tool_result blocks."""
    content = message_obj.get("message", {}).get("content", "")

    if isinstance(content, str):
        return strip_system_tags(content), []

    if not isinstance(content, list):
        return "", []

    texts = []
    for block in content:
        if isinstance(block, str):
            texts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            texts.append(block.get("text", ""))
    return strip_system_tags("\n".join(texts)), []


def extract_assistant_content(message_obj: dict[str, Any]) -> ContentAndTools:
    """Extract text and tool calls from an assistant message."""
    content = message_obj.get("message", {}).get("content", [])

    if isinstance(content, str):
        return content, []

    if not isinstance(content, list):
        return "", []

    texts = []
    tool_calls = []

    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", "")

        if block_type == "text":
            texts.append(block.get("text", ""))
        elif block_type == "tool_use":
            tool_calls.append(summarize_tool_call(block))

    return strip_system_tags("\n".join(texts)), tool_calls


def parse_session(jsonl_path: Path, target_date: date) -> ParsedSession | None:
    """Parse a session JSONL file, extracting messages from target_date."""
    messages = []
    seen_uuids: set[str] = set()
    session_id = jsonl_path.stem

    custom_title = None
    agent_name = None
    slug = None
    project_path = None
    git_branch = None
    input_tokens = 0
    output_tokens = 0
    first_user_message = None

    try:
        with open(jsonl_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                entry_type = obj.get("type", "")

                # Metadata - extract from every entry, take first non-null
                custom_title = custom_title or obj.get("customTitle")
                agent_name = agent_name or obj.get("agentName")
                slug = slug or obj.get("slug")
                git_branch = git_branch or obj.get("gitBranch")
                if not project_path and entry_type == "user":
                    project_path = obj.get("cwd", "")

                if entry_type not in ("user", "assistant") or obj.get("isSidechain"):
                    continue

                ts = parse_iso_timestamp(obj.get("timestamp"))
                if not ts or ts.date() != target_date:
                    continue

                uuid = obj.get("uuid")
                if uuid:
                    if uuid in seen_uuids:
                        continue
                    seen_uuids.add(uuid)

                if entry_type == "assistant":
                    usage = obj.get("message", {}).get("usage", {})
                    input_tokens += usage.get("input_tokens", 0)
                    input_tokens += usage.get("cache_creation_input_tokens", 0)
                    input_tokens += usage.get("cache_read_input_tokens", 0)
                    output_tokens += usage.get("output_tokens", 0)

                extract = extract_user_content if entry_type == "user" else extract_assistant_content
                text, tool_calls = extract(obj)

                if not text and not tool_calls:
                    continue

                if first_user_message is None and entry_type == "user" and text:
                    first_user_message = text

                messages.append(ParsedMessage(
                    timestamp=ts,
                    role=entry_type,
                    text=text,
                    tool_calls=tool_calls,
                ))

    except OSError as e:
        print(f"Warning: could not read {jsonl_path}: {e}", file=sys.stderr)
        return None

    if not messages:
        return None

    messages.sort(key=lambda m: m.timestamp)
    session_name = custom_title or agent_name or slug or session_id[:12]

    return ParsedSession(
        session_id=session_id,
        session_name=session_name,
        project_path=project_path or "unknown",
        git_branch=git_branch,
        messages=messages,
        start_time=messages[0].timestamp,
        end_time=messages[-1].timestamp,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        first_user_message=first_user_message or "",
    )


def shorten_project_path(full_path: str) -> str:
    """Shorten a full project path for display.

    /Users/ashhar.hasan/code/src/github.com/trinodb/trino → trinodb/trino
    /Users/ashhar.hasan/Downloads → ~/Downloads
    """
    if not full_path.startswith(_HOME_STR):
        return full_path

    relative = full_path.removeprefix(_HOME_STR)

    for prefix in ["/code/src/github.com/", "/code/src/", "/code/"]:
        if relative.startswith(prefix):
            return relative.removeprefix(prefix)

    return "~" + relative


def format_time(dt: datetime) -> str:
    """Format datetime as HH:MM in local time."""
    return dt.astimezone().strftime("%H:%M")


def format_tokens(n: int) -> str:
    """Format token count with K suffix for readability."""
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


def format_token_pair(input_tokens: int, output_tokens: int) -> str:
    """Format an input/output token pair for display."""
    return f"{format_tokens(input_tokens)} in / {format_tokens(output_tokens)} out"


def session_filename(session: ParsedSession) -> str:
    """Generate a safe filename for a session."""
    name = session.session_name
    safe_name = _UNSAFE_FILENAME_CHARS.sub("-", name).strip("-")
    return f"session-{safe_name}.md"


def render_session(session: ParsedSession, project_display: str) -> str:
    """Render a single session into markdown."""
    time_range = f"{format_time(session.start_time)} – {format_time(session.end_time)}"
    msg_count = len(session.messages)

    lines = [
        f"# Session: {session.session_name}",
        "",
        f"- **Project:** {project_display}",
        f"- **Time:** {time_range}",
        f"- **Messages:** {msg_count}",
        f"- **Git branch:** `{session.git_branch or 'N/A'}`",
        f"- **Token usage:** {format_token_pair(session.input_tokens, session.output_tokens)}",
        "",
        "---",
        "",
        "## Conversation",
        "",
    ]

    for msg in session.messages:
        time_str = format_time(msg.timestamp)
        role_label = "User" if msg.role == "user" else "Claude"

        if msg.text:
            text_lines = msg.text.split("\n")
            first_line = text_lines[0]
            lines.append(f"- [{time_str}] **{role_label}:** {first_line}")
            for continuation in text_lines[1:]:
                lines.append(f"  {continuation}")

        for tc in msg.tool_calls:
            lines.append(f"- [{time_str}] **Claude:** {tc}")

    lines.append("")
    return "\n".join(lines)


def render_index(projects_data: dict[str, list[ParsedSession]], target_date: date, session_files_map: dict[str, str]) -> str:
    """Render the _index.md file listing all sessions for the day."""
    lines = [
        f"# Claude Code Daily Transcript — {target_date.isoformat()}",
        "",
    ]

    total_input = 0
    total_output = 0

    for project_display, sessions in sorted(projects_data.items()):
        lines.append(f"## Project: {project_display}")
        lines.append("")

        for session in sorted(sessions, key=lambda s: s.start_time):
            time_range = f"{format_time(session.start_time)} – {format_time(session.end_time)}"
            msg_count = len(session.messages)
            filename = session_files_map[session.session_id]
            tokens = format_token_pair(session.input_tokens, session.output_tokens)
            branch = f" on `{session.git_branch}`" if session.git_branch else ""

            # First line of first user message as summary, truncated
            summary = session.first_user_message.split("\n")[0]
            if len(summary) > 200:
                summary = summary[:117] + "..."

            lines.append(f"- **[{session.session_name}]({filename})** — {time_range}, {msg_count} messages, {tokens}{branch}")
            lines.append(f"  > {summary}")

            total_input += session.input_tokens
            total_output += session.output_tokens

        lines.append("")

    lines.append("## Totals")
    lines.append("")
    lines.append(f"- **Token usage:** {format_token_pair(total_input, total_output)}")
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract Claude Code daily transcripts into a clean markdown summary."
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Target date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()

    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"Error: invalid date format '{args.date}'. Use YYYY-MM-DD.", file=sys.stderr)
            sys.exit(1)
    else:
        target_date = date.today()

    output_base = Path(args.output_dir)
    day_dir = output_base / target_date.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)

    print(f"Scanning for sessions on {target_date}...", file=sys.stderr)

    session_files = find_sessions_for_date(target_date)
    print(f"Found {len(session_files)} candidate session files.", file=sys.stderr)

    projects_data = defaultdict(list)

    for jsonl_path in session_files:
        session = parse_session(jsonl_path, target_date)
        if session:
            display_name = shorten_project_path(session.project_path)
            projects_data[display_name].append(session)

    total_sessions = sum(len(v) for v in projects_data.values())
    if total_sessions == 0:
        print(f"No sessions found for {target_date}.", file=sys.stderr)
        sys.exit(0)

    print(f"Parsed {total_sessions} sessions across {len(projects_data)} projects.", file=sys.stderr)

    session_files_map = {}  # session_id -> filename
    used_filenames = set()
    for project_display, sessions in projects_data.items():
        for session in sessions:
            fname = session_filename(session)
            if fname in used_filenames:
                base, ext = fname.rsplit(".", 1)
                fname = f"{base}-{session.session_id[:8]}.{ext}"
            used_filenames.add(fname)
            session_files_map[session.session_id] = fname

            session_md = render_session(session, project_display)
            (day_dir / fname).write_text(session_md, encoding="utf-8")

    index_md = render_index(projects_data, target_date, session_files_map)
    (day_dir / "_index.md").write_text(index_md, encoding="utf-8")

    print(f"Written {total_sessions} session files + _index.md to {day_dir}/", file=sys.stderr)


if __name__ == "__main__":
    main()
