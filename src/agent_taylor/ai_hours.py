from __future__ import annotations

import csv
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


@dataclass(frozen=True)
class Sitting:
    """A continuous work period across all projects.

    A new sitting starts when there's a gap >= SITTING_GAP_SECONDS between
    any interactions (regardless of project).
    """

    start_ts: float
    end_ts: float
    interactions: int
    projects: tuple[str, ...]  # Unique projects touched in this sitting

    @property
    def duration_seconds(self) -> float:
        """Raw duration from first to last interaction."""
        return max(0.0, self.end_ts - self.start_ts)

    @property
    def estimated_seconds(self) -> float:
        """Duration plus preparation time prefix."""
        return self.duration_seconds + SITTING_PREP_SECONDS


@dataclass(frozen=True)
class DailyProjectHours:
    """Hours worked on a single project in a single day."""

    day: str  # YYYY-MM-DD
    project: str  # Last element of path
    session_hours: float
    sessions: int
    interactions: int


@dataclass(frozen=True)
class DailySittingHours:
    """Total active hours in a single day (across all projects)."""

    day: str  # YYYY-MM-DD
    sitting_hours: float
    sittings: int
    interactions: int
    projects: tuple[str, ...]  # Unique projects touched


# Constants
SESSION_GAP_SECONDS = 5 * 60  # 5 minutes
THINKING_PREFIX_SECONDS = 3 * 60  # 3 minutes thinking before first query
SITTING_GAP_SECONDS = 20 * 60  # 20 minutes
SITTING_PREP_SECONDS = 3 * 60  # 3 minutes preparation before sitting


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


def detect_sittings(interactions: list[Interaction]) -> list[Sitting]:
    """Detect work sittings from interactions.

    A sitting is a continuous work period across all projects. A new sitting
    starts when there's a gap >= SITTING_GAP_SECONDS (20 minutes) between
    any interactions.
    """
    if not interactions:
        return []

    interactions = sorted(interactions, key=lambda i: i.timestamp)
    sittings: list[Sitting] = []

    sitting_start = interactions[0].timestamp
    sitting_end = interactions[0].timestamp
    sitting_count = 0
    sitting_projects: set[str] = set()

    def flush_sitting() -> None:
        nonlocal sitting_start, sitting_end, sitting_count, sitting_projects
        if sitting_count > 0:
            sittings.append(
                Sitting(
                    start_ts=sitting_start,
                    end_ts=sitting_end,
                    interactions=sitting_count,
                    projects=tuple(sorted(sitting_projects)),
                )
            )
        sitting_projects = set()
        sitting_count = 0

    for inter in interactions:
        gap = inter.timestamp - sitting_end
        if gap >= SITTING_GAP_SECONDS:
            flush_sitting()
            sitting_start = inter.timestamp

        sitting_end = inter.timestamp
        sitting_count += 1
        sitting_projects.add(_project_name(inter.project))

    flush_sitting()
    return sittings


def aggregate_daily_project_hours(sessions: list[Session]) -> list[DailyProjectHours]:
    """Aggregate sessions into daily per-project hours."""
    # Group by (day, project)
    by_day_project: dict[tuple[str, str], list[Session]] = {}
    for s in sessions:
        day = datetime.fromtimestamp(s.start_ts).strftime("%Y-%m-%d")
        key = (day, s.project)
        by_day_project.setdefault(key, []).append(s)

    results: list[DailyProjectHours] = []
    for (day, project), day_sessions in sorted(by_day_project.items()):
        total_seconds = sum(s.estimated_seconds for s in day_sessions)
        total_interactions = sum(s.interactions for s in day_sessions)
        results.append(
            DailyProjectHours(
                day=day,
                project=project,
                session_hours=round(total_seconds / 3600, 2),
                sessions=len(day_sessions),
                interactions=total_interactions,
            )
        )
    return results


def aggregate_daily_sitting_hours(sittings: list[Sitting]) -> list[DailySittingHours]:
    """Aggregate sittings into daily totals."""
    by_day: dict[str, list[Sitting]] = {}
    for s in sittings:
        day = datetime.fromtimestamp(s.start_ts).strftime("%Y-%m-%d")
        by_day.setdefault(day, []).append(s)

    results: list[DailySittingHours] = []
    for day, day_sittings in sorted(by_day.items()):
        total_seconds = sum(s.estimated_seconds for s in day_sittings)
        total_interactions = sum(s.interactions for s in day_sittings)
        all_projects: set[str] = set()
        for s in day_sittings:
            all_projects.update(s.projects)
        results.append(
            DailySittingHours(
                day=day,
                sitting_hours=round(total_seconds / 3600, 2),
                sittings=len(day_sittings),
                interactions=total_interactions,
                projects=tuple(sorted(all_projects)),
            )
        )
    return results


def write_sessions_csv(path: Path, daily_hours: list[DailyProjectHours]) -> None:
    """Write daily project hours to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["day", "project", "session_hours", "sessions", "interactions"]
        )
        writer.writeheader()
        for h in daily_hours:
            writer.writerow(
                {
                    "day": h.day,
                    "project": h.project,
                    "session_hours": h.session_hours,
                    "sessions": h.sessions,
                    "interactions": h.interactions,
                }
            )


def write_sittings_csv(path: Path, daily_hours: list[DailySittingHours]) -> None:
    """Write daily sitting hours to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["day", "sitting_hours", "sittings", "interactions", "projects"]
        )
        writer.writeheader()
        for h in daily_hours:
            writer.writerow(
                {
                    "day": h.day,
                    "sitting_hours": h.sitting_hours,
                    "sittings": h.sittings,
                    "interactions": h.interactions,
                    "projects": ";".join(h.projects),
                }
            )


def print_summary(
    daily_project: list[DailyProjectHours],
    daily_sitting: list[DailySittingHours],
    project_filter: Optional[str] = None,
) -> None:
    """Print a summary of hours worked."""
    if project_filter:
        print(f"project_filter: {project_filter}")

    # Sessions summary
    total_session_hours = sum(h.session_hours for h in daily_project)
    total_sessions = sum(h.sessions for h in daily_project)
    total_interactions = sum(h.interactions for h in daily_project)
    active_days = len(set(h.day for h in daily_project))

    print(f"total_session_hours: {total_session_hours:.1f}")
    print(f"total_sessions: {total_sessions}")
    print(f"total_interactions: {total_interactions}")
    print(f"active_days: {active_days}")
    if active_days > 0:
        print(f"avg_session_hours_per_day: {total_session_hours / active_days:.1f}")

    # Sittings summary (only if not filtered to single project)
    if not project_filter:
        print()
        total_sitting_hours = sum(h.sitting_hours for h in daily_sitting)
        total_sittings = sum(h.sittings for h in daily_sitting)
        sitting_days = len(daily_sitting)
        print(f"total_sitting_hours: {total_sitting_hours:.1f}")
        print(f"total_sittings: {total_sittings}")
        if sitting_days > 0:
            print(f"avg_sitting_hours_per_day: {total_sitting_hours / sitting_days:.1f}")

    # Date range
    if daily_project:
        days = sorted(set(h.day for h in daily_project))
        print(f"date_range: {days[0]}..{days[-1]}")

    # Top projects by hours
    if not project_filter:
        print()
        print("hours_by_project:")
        by_project: dict[str, float] = {}
        for h in daily_project:
            by_project[h.project] = by_project.get(h.project, 0) + h.session_hours
        for proj, hours in sorted(by_project.items(), key=lambda x: -x[1])[:10]:
            print(f"  {proj}: {hours:.1f}h")
