# ABOUTME: Configuration detection for beads and beadhub adoption.
# ABOUTME: Detects beads adoption via git, beadhub via .beadhub file presence.

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Date when the main beadhub project started using beadhub
BEADHUB_START_DATE = "2025-11-30"
# Projects with .beadhub file started using it 2 weeks after beadhub started
BEADHUB_ADOPTION_DELAY_DAYS = 14


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


def detect_beadhub_date(repo: Path) -> Optional[str]:
    """Detect when a repo started using beadhub.

    - Main beadhub repo: uses beadhub from BEADHUB_START_DATE
    - Repos with .beadhub file: uses beadhub from 2 weeks after BEADHUB_START_DATE
    - Other repos: don't use beadhub

    Args:
        repo: Path to the git repository root.

    Returns:
        Date string (YYYY-MM-DD) when beadhub adoption started, or None.
    """
    if not repo.exists():
        return None

    # Main beadhub repo uses beadhub from the start
    if repo.name == "beadhub":
        return BEADHUB_START_DATE

    # Check for .beadhub file (not directory)
    beadhub_file = repo / ".beadhub"
    if beadhub_file.is_file():
        # Adoption date is 2 weeks after beadhub started
        start = datetime.strptime(BEADHUB_START_DATE, "%Y-%m-%d")
        adoption = start + timedelta(days=BEADHUB_ADOPTION_DELAY_DAYS)
        return adoption.strftime("%Y-%m-%d")

    return None


def get_configuration(
    beads_date: Optional[str],
    beadhub_date: Optional[str],
    check_date: str,
) -> str:
    """Determine the configuration for a given date.

    Args:
        beads_date: Date when beads was adopted (YYYY-MM-DD), or None.
        beadhub_date: Date when beadhub was adopted (YYYY-MM-DD), or None.
        check_date: Date to check configuration for (YYYY-MM-DD).

    Returns:
        One of: "none", "beads", "beads+beadhub"
    """
    # If beads not adopted, or check_date is before beads adoption
    if beads_date is None or check_date < beads_date:
        return "none"

    # If beadhub adopted and check_date is on or after beadhub adoption
    if beadhub_date is not None and check_date >= beadhub_date:
        return "beads+beadhub"

    return "beads"
