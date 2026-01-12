# ABOUTME: Parses AI assistant logs (Claude Code, Codex) into interactions and sessions.
# ABOUTME: Detects work sessions per project based on interaction timing gaps.

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class Interaction:
    """A single message in an AI conversation."""

    timestamp: float  # Unix seconds
    message_type: str  # "user" or "assistant"
    project: str  # Full path to project directory


@dataclass(frozen=True)
class Session:
    """A continuous work period on a single project.

    A new session starts when the gap between an assistant reply and the next
    user message is >= SESSION_GAP_SECONDS.
    """

    project: str  # Last element of project path (repo name)
    project_full: str  # Full path
    start_ts: float
    end_ts: float
    interactions: int

    @property
    def duration_seconds(self) -> float:
        """Raw duration from first to last interaction."""
        return max(0.0, self.end_ts - self.start_ts)

    @property
    def estimated_seconds(self) -> float:
        """Duration plus thinking time prefix."""
        return self.duration_seconds + THINKING_PREFIX_SECONDS


# Constants
SESSION_GAP_SECONDS = 5 * 60  # 5 minutes
THINKING_PREFIX_SECONDS = 3 * 60  # 3 minutes thinking before first query


def _project_name(full_path: str) -> str:
    """Extract project name from full path (last element)."""
    if not full_path:
        return "unknown"
    return Path(full_path).name


def _parse_claude_sessions(claude_dir: Path) -> list[Interaction]:
    """Parse Claude Code session files for interactions.

    Claude stores sessions in ~/.claude/projects/<encoded-path>/<session-id>.jsonl
    Each line is a message with type, timestamp, and cwd.
    """
    interactions: list[Interaction] = []
    projects_dir = claude_dir / "projects"
    if not projects_dir.exists():
        return interactions

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for session_file in project_dir.glob("*.jsonl"):
            try:
                with session_file.open("r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        msg_type = msg.get("type", "")
                        if msg_type not in ("user", "assistant"):
                            continue

                        ts_raw = msg.get("timestamp")
                        if ts_raw is None:
                            continue

                        # Parse timestamp (can be milliseconds or ISO string)
                        try:
                            if isinstance(ts_raw, str):
                                # Handle ISO format: 2026-01-02T21:15:17.527Z
                                ts_str = ts_raw.replace("Z", "+00:00")
                                dt = datetime.fromisoformat(ts_str)
                                ts = dt.timestamp()
                            else:
                                ts = float(ts_raw)
                                # Convert milliseconds to seconds
                                if ts > 1e12:
                                    ts = ts / 1000.0
                        except (ValueError, TypeError):
                            continue

                        cwd = msg.get("cwd", "")
                        if not cwd:
                            # Try to infer from project dir name
                            # Format: -Users-name-projects-repo -> /Users/name/projects/repo
                            cwd = project_dir.name.replace("-", "/")
                            if not cwd.startswith("/"):
                                cwd = "/" + cwd

                        interactions.append(
                            Interaction(timestamp=float(ts), message_type=msg_type, project=cwd)
                        )
            except (OSError, IOError):
                continue

    return interactions


def _parse_codex_sessions(codex_dir: Path) -> list[Interaction]:
    """Parse Codex session files for interactions.

    Codex stores sessions in ~/.codex/sessions/YYYY/MM/DD/<session>.jsonl
    First line is session_meta with cwd, subsequent lines are messages.

    Message types:
    - session_meta: contains cwd in payload
    - response_item with payload.type="message": contains role (user/assistant)
    - event_msg with payload.type="user_message": user input
    """
    interactions: list[Interaction] = []
    sessions_dir = codex_dir / "sessions"
    if not sessions_dir.exists():
        return interactions

    for session_file in sessions_dir.rglob("*.jsonl"):
        try:
            cwd: Optional[str] = None
            with session_file.open("r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg_type = msg.get("type", "")
                    payload = msg.get("payload", {})

                    # Extract cwd from session_meta
                    if msg_type == "session_meta":
                        cwd = payload.get("cwd", "")
                        continue

                    # Determine if this is a user or assistant message
                    normalized_type: Optional[str] = None

                    if msg_type == "response_item":
                        payload_type = payload.get("type", "")
                        if payload_type == "message":
                            role = payload.get("role", "")
                            if role in ("user", "assistant"):
                                normalized_type = role
                        elif payload_type == "function_call":
                            # Function calls are assistant actions
                            normalized_type = "assistant"

                    elif msg_type == "event_msg":
                        payload_type = payload.get("type", "")
                        if payload_type == "user_message":
                            normalized_type = "user"

                    if normalized_type is None:
                        continue

                    ts_str = msg.get("timestamp")
                    if ts_str is None:
                        continue

                    # Parse ISO timestamp
                    try:
                        if isinstance(ts_str, str):
                            # Handle ISO format: 2025-11-03T15:29:32.819Z
                            ts_clean = ts_str.replace("Z", "+00:00")
                            dt = datetime.fromisoformat(ts_clean)
                            ts = dt.timestamp()
                        else:
                            ts = float(ts_str)
                            if ts > 1e12:
                                ts = ts / 1000.0
                    except (ValueError, TypeError):
                        continue

                    if not cwd:
                        continue

                    interactions.append(
                        Interaction(timestamp=ts, message_type=normalized_type, project=cwd)
                    )
        except (OSError, IOError):
            continue

    return interactions


def collect_interactions(
    claude_dir: Optional[Path] = None,
    codex_dir: Optional[Path] = None,
) -> list[Interaction]:
    """Collect all interactions from Claude and Codex logs."""
    if claude_dir is None:
        claude_dir = Path.home() / ".claude"
    if codex_dir is None:
        codex_dir = Path.home() / ".codex"

    interactions: list[Interaction] = []
    interactions.extend(_parse_claude_sessions(claude_dir))
    interactions.extend(_parse_codex_sessions(codex_dir))
    interactions.sort(key=lambda i: i.timestamp)
    return interactions


def detect_sessions(
    interactions: list[Interaction],
    project_filter: Optional[str] = None,
) -> list[Session]:
    """Detect work sessions from interactions.

    A new session starts when the gap between an assistant reply and the next
    user message is >= SESSION_GAP_SECONDS (5 minutes).

    Args:
        interactions: Sorted list of interactions
        project_filter: If provided, only include sessions for projects whose
            name (last path element) matches this string
    """
    # Group by project
    by_project: dict[str, list[Interaction]] = {}
    for i in interactions:
        proj_name = _project_name(i.project)
        if project_filter and proj_name != project_filter:
            continue
        by_project.setdefault(i.project, []).append(i)

    sessions: list[Session] = []
    for project_full, proj_interactions in by_project.items():
        proj_interactions.sort(key=lambda x: x.timestamp)
        proj_name = _project_name(project_full)

        session_start: Optional[float] = None
        session_end: Optional[float] = None
        session_count = 0
        last_assistant_ts: Optional[float] = None

        def flush_session() -> None:
            nonlocal session_start, session_end, session_count
            if session_start is not None and session_end is not None and session_count > 0:
                sessions.append(
                    Session(
                        project=proj_name,
                        project_full=project_full,
                        start_ts=session_start,
                        end_ts=session_end,
                        interactions=session_count,
                    )
                )
            session_start = None
            session_end = None
            session_count = 0

        for inter in proj_interactions:
            # Check if this starts a new session
            if inter.message_type == "user" and last_assistant_ts is not None:
                gap = inter.timestamp - last_assistant_ts
                if gap >= SESSION_GAP_SECONDS:
                    flush_session()

            # Initialize or extend session
            if session_start is None:
                session_start = inter.timestamp
            session_end = inter.timestamp
            session_count += 1

            if inter.message_type == "assistant":
                last_assistant_ts = inter.timestamp

        flush_session()

    sessions.sort(key=lambda s: s.start_ts)
    return sessions


def _parse_timestamp_value(ts_raw: object) -> Optional[float]:
    """Parse a timestamp from raw value (ISO string or numeric)."""
    if ts_raw is None:
        return None
    try:
        if isinstance(ts_raw, str):
            ts_str = ts_raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts_str)
            return dt.timestamp()
        elif isinstance(ts_raw, (int, float)):
            ts = float(ts_raw)
            if ts > 1e12:
                ts = ts / 1000.0
            return ts
        else:
            return None
    except (ValueError, TypeError):
        return None


def _earliest_claude_timestamp(claude_dir: Path) -> Optional[float]:
    """Find the earliest timestamp from Claude Code logs."""
    projects_dir = claude_dir / "projects"
    if not projects_dir.exists():
        return None

    earliest: Optional[float] = None

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        for session_file in project_dir.glob("*.jsonl"):
            try:
                with session_file.open("r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        msg_type = msg.get("type", "")
                        if msg_type not in ("user", "assistant"):
                            continue

                        ts = _parse_timestamp_value(msg.get("timestamp"))
                        if ts is not None:
                            if earliest is None or ts < earliest:
                                earliest = ts
            except (OSError, IOError):
                continue

    return earliest


def _earliest_codex_timestamp(codex_dir: Path) -> Optional[float]:
    """Find the earliest timestamp from Codex logs."""
    sessions_dir = codex_dir / "sessions"
    if not sessions_dir.exists():
        return None

    earliest: Optional[float] = None

    for session_file in sessions_dir.rglob("*.jsonl"):
        try:
            with session_file.open("r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg_type = msg.get("type", "")
                    payload = msg.get("payload", {})

                    # Only count actual message types, not session_meta
                    if msg_type == "response_item":
                        payload_type = payload.get("type", "")
                        if payload_type not in ("message", "function_call"):
                            continue
                    elif msg_type == "event_msg":
                        payload_type = payload.get("type", "")
                        if payload_type != "user_message":
                            continue
                    else:
                        continue

                    ts = _parse_timestamp_value(msg.get("timestamp"))
                    if ts is not None:
                        if earliest is None or ts < earliest:
                            earliest = ts
        except (OSError, IOError):
            continue

    return earliest


def detect_source_date_ranges(
    claude_dir: Optional[Path] = None,
    codex_dir: Optional[Path] = None,
) -> dict[str, Optional[str]]:
    """Detect the earliest date from each AI assistant log source.

    Returns:
        Dict with 'claude' and 'codex' keys, each mapping to a date string
        (YYYY-MM-DD) or None if no data found for that source.
    """
    if claude_dir is None:
        claude_dir = Path.home() / ".claude"
    if codex_dir is None:
        codex_dir = Path.home() / ".codex"

    result: dict[str, Optional[str]] = {"claude": None, "codex": None}

    claude_ts = _earliest_claude_timestamp(claude_dir)
    if claude_ts is not None:
        result["claude"] = datetime.fromtimestamp(claude_ts).strftime("%Y-%m-%d")

    codex_ts = _earliest_codex_timestamp(codex_dir)
    if codex_ts is not None:
        result["codex"] = datetime.fromtimestamp(codex_ts).strftime("%Y-%m-%d")

    return result


def effective_start_date(source_dates: dict[str, Optional[str]]) -> Optional[str]:
    """Compute the effective start date from source date ranges.

    Returns the later of the two dates when both sources have data,
    or the single available date when only one source has data.
    """
    claude_date = source_dates.get("claude")
    codex_date = source_dates.get("codex")

    if claude_date is None and codex_date is None:
        return None

    if claude_date is None:
        return codex_date

    if codex_date is None:
        return claude_date

    # Both have data - return the later date
    return max(claude_date, codex_date)
