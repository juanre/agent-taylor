# ABOUTME: Compare productivity across beads/beadhub configurations.
# ABOUTME: Aggregates session metrics by configuration (none, beads, beads+beadhub).

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config_detection import get_configuration


def get_commits_in_window(
    repo: Path,
    start_ts: float,
    end_ts: float,
    author: Optional[str] = None,
) -> list[dict[str, object]]:
    """Get commits in a repository within a time window.

    Args:
        repo: Path to the git repository.
        start_ts: Start of window (Unix timestamp, UTC).
        end_ts: End of window (Unix timestamp, UTC).
        author: Optional author regex to filter commits.

    Returns:
        List of commit dicts with 'sha', 'timestamp', 'delta' keys.
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


def _parse_git_log_numstat(output: str) -> list[dict[str, object]]:
    """Parse git log --numstat output into commit dicts."""
    commits: list[dict[str, object]] = []
    current_commit: Optional[dict[str, object]] = None

    for line in output.strip().split("\n"):
        if not line:
            continue

        if "|" in line and not line.startswith("\t"):
            # Commit header line: SHA|timestamp
            if current_commit is not None:
                commits.append(current_commit)
            parts = line.split("|")
            if len(parts) == 2:
                current_commit = {
                    "sha": parts[0],
                    "timestamp": int(parts[1]),
                    "added": 0,
                    "deleted": 0,
                    "delta": 0,
                }
        elif current_commit is not None:
            # Numstat line: added\tdeleted\tfilename
            parts = line.split("\t")
            if len(parts) >= 2:
                try:
                    added = int(parts[0]) if parts[0] != "-" else 0
                    deleted = int(parts[1]) if parts[1] != "-" else 0
                    current_commit["added"] = int(current_commit["added"]) + added
                    current_commit["deleted"] = int(current_commit["deleted"]) + deleted
                    current_commit["delta"] = int(current_commit["delta"]) + added + deleted
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
    session_metrics: list[dict[str, object]],
) -> dict[str, dict[str, float]]:
    """Aggregate session metrics by configuration.

    Args:
        session_metrics: List of dicts with 'configuration', 'hours',
                        'commits', 'delta' keys.

    Returns:
        Dict mapping configuration to aggregated metrics including rates.
    """
    # Initialize all configurations
    result: dict[str, dict[str, float]] = {
        "none": {
            "sessions": 0,
            "hours": 0.0,
            "commits": 0,
            "delta": 0,
            "delta_per_hour": 0.0,
            "commits_per_hour": 0.0,
        },
        "beads": {
            "sessions": 0,
            "hours": 0.0,
            "commits": 0,
            "delta": 0,
            "delta_per_hour": 0.0,
            "commits_per_hour": 0.0,
        },
        "beads+beadhub": {
            "sessions": 0,
            "hours": 0.0,
            "commits": 0,
            "delta": 0,
            "delta_per_hour": 0.0,
            "commits_per_hour": 0.0,
        },
    }

    # Aggregate metrics
    for session in session_metrics:
        config = str(session.get("configuration", "none"))
        if config not in result:
            continue
        result[config]["sessions"] += 1
        result[config]["hours"] += float(session.get("hours", 0))
        result[config]["commits"] += int(session.get("commits", 0))
        result[config]["delta"] += int(session.get("delta", 0))

    # Compute rates
    for config in result:
        hours = result[config]["hours"]
        if hours > 0:
            result[config]["delta_per_hour"] = result[config]["delta"] / hours
            result[config]["commits_per_hour"] = result[config]["commits"] / hours

    return result
