# ABOUTME: Configuration detection for beads and beadhub adoption.
# ABOUTME: Detects beads adoption via git, beadhub via repo naming convention.

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


def detect_beads_date(repo: Path) -> Optional[str]:
    """Detect when .beads/ was first committed to the repo.

    Args:
        repo: Path to the git repository root.

    Returns:
        Date string (YYYY-MM-DD) when .beads/ was first committed,
        or None if .beads/ was never committed or repo is not a git repo.
    """
    if not repo.exists():
        return None

    try:
        result = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%cs", "--", ".beads/"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None

        lines = result.stdout.strip().split("\n")
        # Last line is the earliest commit (git log is newest first)
        if lines and lines[-1]:
            return lines[-1]
        return None

    except (OSError, subprocess.SubprocessError):
        return None


def is_beadhub_repo(repo: Path) -> bool:
    """Check if a repo is a beadhub repo based on its name.

    Beadhub repos are identified by the name "beadhub" or names starting with
    "beadhub-". These repos are assumed to always use beadhub (the .beadhub/
    directory is frequently deleted and recreated, so filesystem detection
    is unreliable).

    Args:
        repo: Path to the git repository root.

    Returns:
        True if the repo name is "beadhub" or starts with "beadhub-".
    """
    name = repo.name
    return name == "beadhub" or name.startswith("beadhub-")


def get_configuration(
    beads_date: Optional[str],
    is_beadhub: bool,
    check_date: str,
) -> str:
    """Determine the configuration for a given date.

    Args:
        beads_date: Date when beads was adopted (YYYY-MM-DD), or None.
        is_beadhub: Whether this is a beadhub repo (name starts with beadhub-).
        check_date: Date to check configuration for (YYYY-MM-DD).

    Returns:
        One of: "none", "beads", "beads+beadhub"
    """
    # If beads not adopted, or check_date is before beads adoption
    if beads_date is None or check_date < beads_date:
        return "none"

    # Beadhub repos are always "beads+beadhub" once beads is adopted
    if is_beadhub:
        return "beads+beadhub"

    return "beads"
