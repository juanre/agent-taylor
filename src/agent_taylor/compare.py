# ABOUTME: Compare productivity across beads/beadhub configurations.
# ABOUTME: Aggregates session metrics by configuration (none, beads, beads+beadhub).

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TypedDict

from .config_detection import get_configuration


class CommitInfo(TypedDict):
    """Commit information from git log."""

    sha: str
    timestamp: int
    added: int
    deleted: int
    delta: int


class SessionMetrics(TypedDict):
    """Metrics for a single session."""

    configuration: str
    hours: float
    commits: int
    delta: int
    date: str


class AggregatedMetrics(TypedDict):
    """Aggregated metrics for a configuration."""

    sessions: int
    hours: float
    commits: int
    delta: int
    delta_per_hour: float
    commits_per_hour: float


class DailyMetrics(TypedDict):
    """Aggregated metrics for a single date and configuration."""

    date: str
    configuration: str
    sessions: int
    hours: float
    commits: int
    delta: int
    delta_per_hour: float
    commits_per_hour: float


def get_commits_in_window(
    repo: Path,
    start_ts: float,
    end_ts: float,
    author: Optional[str] = None,
) -> list[CommitInfo]:
    """Get commits in a repository within a time window.

    Args:
        repo: Path to the git repository.
        start_ts: Start of window (Unix timestamp, UTC).
        end_ts: End of window (Unix timestamp, UTC).
        author: Optional author regex to filter commits.

    Returns:
        List of CommitInfo dicts with sha, timestamp, delta keys.
    """
    if not repo.exists():
        return []

    # Format timestamps as ISO 8601 with explicit UTC timezone
    # This avoids ambiguity from local timezone interpretation
    start_iso = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    end_iso = datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    cmd = [
        "git",
        "log",
        "--format=%H|%ct",
        "--numstat",
        f"--after={start_iso}",
        f"--before={end_iso}",
        "--no-merges",
    ]
    if author:
        cmd.extend(["--author", author])

    try:
        result = subprocess.run(
            cmd,
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return []

        return _parse_git_log_numstat(result.stdout)

    except (OSError, subprocess.SubprocessError):
        return []


def _parse_git_log_numstat(output: str) -> list[CommitInfo]:
    """Parse git log --numstat output into commit dicts."""
    commits: list[CommitInfo] = []
    current_commit: Optional[CommitInfo] = None

    for line in output.strip().split("\n"):
        if not line:
            continue

        if "|" in line and not line.startswith("\t"):
            # Commit header line: SHA|timestamp
            if current_commit is not None:
                commits.append(current_commit)
            parts = line.split("|")
            if len(parts) == 2:
                current_commit = CommitInfo(
                    sha=parts[0],
                    timestamp=int(parts[1]),
                    added=0,
                    deleted=0,
                    delta=0,
                )
        elif current_commit is not None:
            # Numstat line: added\tdeleted\tfilename
            parts = line.split("\t")
            if len(parts) >= 2:
                try:
                    added = int(parts[0]) if parts[0] != "-" else 0
                    deleted = int(parts[1]) if parts[1] != "-" else 0
                    current_commit["added"] += added
                    current_commit["deleted"] += deleted
                    current_commit["delta"] += added + deleted
                except ValueError:
                    pass

    if current_commit is not None:
        commits.append(current_commit)

    return commits


def classify_session(
    session_start_date: str,
    beads_date: Optional[str],
    is_beadhub: bool,
) -> str:
    """Classify a session into a configuration bucket.

    Args:
        session_start_date: Date of session start (YYYY-MM-DD).
        beads_date: Date beads was adopted (YYYY-MM-DD), or None.
        is_beadhub: Whether this is a beadhub repo (name starts with beadhub-).

    Returns:
        One of: "none", "beads", "beads+beadhub"
    """
    return get_configuration(beads_date, is_beadhub, session_start_date)


def aggregate_by_configuration(
    session_metrics: list[SessionMetrics],
) -> dict[str, AggregatedMetrics]:
    """Aggregate session metrics by configuration.

    Args:
        session_metrics: List of SessionMetrics dicts.

    Returns:
        Dict mapping configuration to aggregated metrics including rates.
    """
    # Initialize all configurations
    result: dict[str, AggregatedMetrics] = {
        "none": AggregatedMetrics(
            sessions=0,
            hours=0.0,
            commits=0,
            delta=0,
            delta_per_hour=0.0,
            commits_per_hour=0.0,
        ),
        "beads": AggregatedMetrics(
            sessions=0,
            hours=0.0,
            commits=0,
            delta=0,
            delta_per_hour=0.0,
            commits_per_hour=0.0,
        ),
        "beads+beadhub": AggregatedMetrics(
            sessions=0,
            hours=0.0,
            commits=0,
            delta=0,
            delta_per_hour=0.0,
            commits_per_hour=0.0,
        ),
    }

    # Aggregate metrics
    for session in session_metrics:
        config = session["configuration"]
        if config not in result:
            continue
        result[config]["sessions"] += 1
        result[config]["hours"] += session["hours"]
        result[config]["commits"] += session["commits"]
        result[config]["delta"] += session["delta"]

    # Compute rates
    for config in result:
        hours = result[config]["hours"]
        if hours > 0:
            result[config]["delta_per_hour"] = result[config]["delta"] / hours
            result[config]["commits_per_hour"] = result[config]["commits"] / hours

    return result


def aggregate_by_date_and_configuration(
    session_metrics: list[SessionMetrics],
) -> list[DailyMetrics]:
    """Aggregate session metrics by date and configuration.

    Args:
        session_metrics: List of SessionMetrics dicts with date field.

    Returns:
        List of DailyMetrics dicts sorted by date, then by config order.
        Only includes (date, config) pairs that have sessions.
    """
    if not session_metrics:
        return []

    # Group by (date, configuration)
    groups: dict[tuple[str, str], DailyMetrics] = {}
    config_order = ["none", "beads", "beads+beadhub"]

    for session in session_metrics:
        key = (session["date"], session["configuration"])
        if key not in groups:
            groups[key] = DailyMetrics(
                date=session["date"],
                configuration=session["configuration"],
                sessions=0,
                hours=0.0,
                commits=0,
                delta=0,
                delta_per_hour=0.0,
                commits_per_hour=0.0,
            )
        groups[key]["sessions"] += 1
        groups[key]["hours"] += session["hours"]
        groups[key]["commits"] += session["commits"]
        groups[key]["delta"] += session["delta"]

    # Compute rates
    for group in groups.values():
        if group["hours"] > 0:
            group["delta_per_hour"] = group["delta"] / group["hours"]
            group["commits_per_hour"] = group["commits"] / group["hours"]

    # Sort by date, then by config order
    def sort_key(item: DailyMetrics) -> tuple[str, int]:
        config_idx = config_order.index(item["configuration"]) if item["configuration"] in config_order else 99
        return (item["date"], config_idx)

    return sorted(groups.values(), key=sort_key)
