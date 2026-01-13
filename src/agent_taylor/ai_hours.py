# ABOUTME: Parses AI assistant logs (Claude Code, Codex) into interactions and sessions.
# ABOUTME: Detects work sessions per project based on interaction timing gaps.

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
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


def _discover_bundle_sources(bundle: Path) -> tuple[list[Path], list[Path]]:
    """Discover claude and codex directories in a log bundle.

    A log bundle contains machine subdirectories, each with optional
    claude/ and codex/ subdirs.

    Args:
        bundle: Path to the log bundle root directory

    Returns:
        Tuple of (claude_dirs, codex_dirs) found in the bundle
    """
    claude_dirs: list[Path] = []
    codex_dirs: list[Path] = []

    if not bundle.exists():
        return claude_dirs, codex_dirs

    for machine_dir in bundle.iterdir():
        if not machine_dir.is_dir():
            continue
        claude_subdir = machine_dir / "claude"
        if claude_subdir.is_dir():
            claude_dirs.append(claude_subdir)
        codex_subdir = machine_dir / "codex"
        if codex_subdir.is_dir():
            codex_dirs.append(codex_subdir)

    return claude_dirs, codex_dirs


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
    log_bundle: Optional[Path] = None,
    claude_dir: Optional[Path] = None,
    codex_dir: Optional[Path] = None,
) -> list[Interaction]:
    """Collect all interactions from Claude and Codex logs.

    Args:
        log_bundle: If provided, discover sources from bundle structure.
            Bundle mode ignores claude_dir and codex_dir.
        claude_dir: Single Claude directory (default mode only).
        codex_dir: Single Codex directory (default mode only).

    Returns:
        List of interactions sorted by timestamp.
    """
    interactions: list[Interaction] = []

    if log_bundle is not None:
        # Bundle mode: discover sources from bundle structure
        claude_dirs, codex_dirs = _discover_bundle_sources(log_bundle)
        for cdir in claude_dirs:
            interactions.extend(_parse_claude_sessions(cdir))
        for xdir in codex_dirs:
            interactions.extend(_parse_codex_sessions(xdir))
    else:
        # Default mode: use single directories
        if claude_dir is None:
            claude_dir = Path.home() / ".claude"
        if codex_dir is None:
            codex_dir = Path.home() / ".codex"
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


def _latest_claude_timestamp(claude_dir: Path) -> Optional[float]:
    """Find the latest timestamp from Claude Code logs."""
    projects_dir = claude_dir / "projects"
    if not projects_dir.exists():
        return None

    latest: Optional[float] = None

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
                            if latest is None or ts > latest:
                                latest = ts
            except (OSError, IOError):
                continue

    return latest


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


def _latest_codex_timestamp(codex_dir: Path) -> Optional[float]:
    """Find the latest timestamp from Codex logs."""
    sessions_dir = codex_dir / "sessions"
    if not sessions_dir.exists():
        return None

    latest: Optional[float] = None

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
                        if latest is None or ts > latest:
                            latest = ts
        except (OSError, IOError):
            continue

    return latest


def detect_coverage_windows(
    log_bundle: Optional[Path] = None,
    claude_dir: Optional[Path] = None,
    codex_dir: Optional[Path] = None,
) -> dict[str, list[tuple[str, str]]]:
    """Detect coverage windows for each log source.

    For each source (Claude, Codex), returns a list of (start_date, end_date)
    tuples representing coverage windows. In bundle mode, each machine contributes
    one window per source. The returned windows are NOT merged - caller should
    use merge_coverage_windows() if merging is desired.

    Args:
        log_bundle: If provided, discover sources from bundle structure.
            Bundle mode ignores claude_dir and codex_dir.
        claude_dir: Single Claude directory (default mode only).
        codex_dir: Single Codex directory (default mode only).

    Returns:
        Dict with 'claude' and 'codex' keys, each mapping to a list of
        (start_date, end_date) tuples.
    """
    result: dict[str, list[tuple[str, str]]] = {"claude": [], "codex": []}

    if log_bundle is not None:
        # Bundle mode: one window per machine per source
        claude_dirs, codex_dirs = _discover_bundle_sources(log_bundle)

        for cdir in claude_dirs:
            earliest = _earliest_claude_timestamp(cdir)
            latest = _latest_claude_timestamp(cdir)
            if earliest is not None and latest is not None:
                start_date = datetime.fromtimestamp(earliest).strftime("%Y-%m-%d")
                end_date = datetime.fromtimestamp(latest).strftime("%Y-%m-%d")
                result["claude"].append((start_date, end_date))

        for xdir in codex_dirs:
            earliest = _earliest_codex_timestamp(xdir)
            latest = _latest_codex_timestamp(xdir)
            if earliest is not None and latest is not None:
                start_date = datetime.fromtimestamp(earliest).strftime("%Y-%m-%d")
                end_date = datetime.fromtimestamp(latest).strftime("%Y-%m-%d")
                result["codex"].append((start_date, end_date))
    else:
        # Default mode: single directory per source
        if claude_dir is None:
            claude_dir = Path.home() / ".claude"
        if codex_dir is None:
            codex_dir = Path.home() / ".codex"

        earliest = _earliest_claude_timestamp(claude_dir)
        latest = _latest_claude_timestamp(claude_dir)
        if earliest is not None and latest is not None:
            start_date = datetime.fromtimestamp(earliest).strftime("%Y-%m-%d")
            end_date = datetime.fromtimestamp(latest).strftime("%Y-%m-%d")
            result["claude"].append((start_date, end_date))

        earliest = _earliest_codex_timestamp(codex_dir)
        latest = _latest_codex_timestamp(codex_dir)
        if earliest is not None and latest is not None:
            start_date = datetime.fromtimestamp(earliest).strftime("%Y-%m-%d")
            end_date = datetime.fromtimestamp(latest).strftime("%Y-%m-%d")
            result["codex"].append((start_date, end_date))

    return result


def detect_source_date_ranges(
    log_bundle: Optional[Path] = None,
    claude_dir: Optional[Path] = None,
    codex_dir: Optional[Path] = None,
) -> dict[str, Optional[str]]:
    """Detect the earliest date from each AI assistant log source.

    Args:
        log_bundle: If provided, discover sources from bundle structure.
            Bundle mode ignores claude_dir and codex_dir.
        claude_dir: Single Claude directory (default mode only).
        codex_dir: Single Codex directory (default mode only).

    Returns:
        Dict with 'claude' and 'codex' keys, each mapping to a date string
        (YYYY-MM-DD) or None if no data found for that source.
    """
    result: dict[str, Optional[str]] = {"claude": None, "codex": None}

    if log_bundle is not None:
        # Bundle mode: discover sources and find earliest across all
        claude_dirs, codex_dirs = _discover_bundle_sources(log_bundle)

        claude_timestamps = [_earliest_claude_timestamp(d) for d in claude_dirs]
        claude_ts = min((t for t in claude_timestamps if t is not None), default=None)

        codex_timestamps = [_earliest_codex_timestamp(d) for d in codex_dirs]
        codex_ts = min((t for t in codex_timestamps if t is not None), default=None)
    else:
        # Default mode: use single directories
        if claude_dir is None:
            claude_dir = Path.home() / ".claude"
        if codex_dir is None:
            codex_dir = Path.home() / ".codex"

        claude_ts = _earliest_claude_timestamp(claude_dir)
        codex_ts = _earliest_codex_timestamp(codex_dir)

    if claude_ts is not None:
        result["claude"] = datetime.fromtimestamp(claude_ts).strftime("%Y-%m-%d")
    if codex_ts is not None:
        result["codex"] = datetime.fromtimestamp(codex_ts).strftime("%Y-%m-%d")

    return result


def merge_coverage_windows(
    windows: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Merge overlapping or adjacent coverage windows.

    Takes a list of (start_date, end_date) tuples and returns a sorted list
    of non-overlapping windows, with overlapping or adjacent windows merged.

    Args:
        windows: List of (start_date, end_date) tuples as YYYY-MM-DD strings

    Returns:
        Sorted list of merged, non-overlapping windows
    """
    if not windows:
        return []

    # Sort by start date
    sorted_windows = sorted(windows, key=lambda w: w[0])

    merged: list[tuple[str, str]] = []
    current_start, current_end = sorted_windows[0]

    for start, end in sorted_windows[1:]:
        # Parse dates to check adjacency
        current_end_dt = datetime.strptime(current_end, "%Y-%m-%d")
        start_dt = datetime.strptime(start, "%Y-%m-%d")

        # Windows are adjacent if start is at most 1 day after current_end
        # Or overlapping if start <= current_end
        if start_dt <= current_end_dt + timedelta(days=1):
            # Merge: extend current_end if needed
            if end > current_end:
                current_end = end
        else:
            # Gap - save current window, start new one
            merged.append((current_start, current_end))
            current_start, current_end = start, end

    # Don't forget the last window
    merged.append((current_start, current_end))

    return merged


def intersect_coverage_windows(
    windows1: list[tuple[str, str]],
    windows2: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Compute the intersection of two sets of coverage windows.

    Returns periods where BOTH sets have coverage. This is used to find
    time ranges where all log sources have data.

    Args:
        windows1: First list of (start_date, end_date) windows
        windows2: Second list of (start_date, end_date) windows

    Returns:
        List of windows representing the intersection, sorted and merged
    """
    if not windows1 or not windows2:
        return []

    intersections: list[tuple[str, str]] = []

    for start1, end1 in windows1:
        for start2, end2 in windows2:
            # Find overlap
            overlap_start = max(start1, start2)
            overlap_end = min(end1, end2)

            # Valid intersection if start <= end
            if overlap_start <= overlap_end:
                intersections.append((overlap_start, overlap_end))

    # Merge any overlapping intersections
    return merge_coverage_windows(intersections)


def is_date_covered(date: str, windows: list[tuple[str, str]]) -> bool:
    """Check if a date falls within any of the coverage windows.

    Args:
        date: Date string in YYYY-MM-DD format
        windows: List of (start_date, end_date) coverage windows

    Returns:
        True if date is within any window (inclusive), False otherwise
    """
    for start, end in windows:
        if start <= date <= end:
            return True
    return False


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
