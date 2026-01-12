# ABOUTME: Tests for the compare command functionality.
# ABOUTME: Tests commit lookup, session classification, and aggregation.

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest


class TestGetCommitsInWindow:
    """Tests for get_commits_in_window function."""

    def test_returns_empty_for_window_before_commits(self, git_repo: Path) -> None:
        """get_commits_in_window returns empty list when window is before commits."""
        from agent_taylor.compare import get_commits_in_window

        # Use a window far in the past
        result = get_commits_in_window(
            repo=git_repo,
            start_ts=0,
            end_ts=1000,
            author=None,
        )

        assert result == []

    def test_returns_commits_in_window(self, git_repo: Path) -> None:
        """get_commits_in_window returns commits within the time window."""
        from agent_taylor.compare import get_commits_in_window

        # Create a file and commit
        (git_repo / "file.txt").write_text("content")
        subprocess.run(["git", "add", "file.txt"], cwd=git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add file"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        now = time.time()
        result = get_commits_in_window(
            repo=git_repo,
            start_ts=now - 60,
            end_ts=now + 60,
            author=None,
        )

        # Should have 2 commits: initial + file.txt
        assert len(result) == 2
        assert all(r["delta"] > 0 for r in result)

    def test_filters_by_author(self, git_repo: Path) -> None:
        """get_commits_in_window filters commits by author regex."""
        from agent_taylor.compare import get_commits_in_window

        # Create a file and commit
        (git_repo / "file.txt").write_text("content")
        subprocess.run(["git", "add", "file.txt"], cwd=git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add file"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        now = time.time()
        # Filter by non-matching author
        result = get_commits_in_window(
            repo=git_repo,
            start_ts=now - 60,
            end_ts=now + 60,
            author="NonExistentAuthor",
        )

        assert result == []

    def test_excludes_commits_outside_window(self, git_repo: Path) -> None:
        """get_commits_in_window excludes commits outside the time window."""
        from agent_taylor.compare import get_commits_in_window

        # Create a file and commit
        (git_repo / "file.txt").write_text("content")
        subprocess.run(["git", "add", "file.txt"], cwd=git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add file"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        now = time.time()
        # Window in the past
        result = get_commits_in_window(
            repo=git_repo,
            start_ts=now - 7200,
            end_ts=now - 3600,
            author=None,
        )

        assert result == []


class TestClassifySession:
    """Tests for classify_session function."""

    def test_classifies_session_by_configuration(self) -> None:
        """classify_session returns correct configuration for session."""
        from agent_taylor.compare import classify_session

        # Session in June, beads adopted in May, not a beadhub repo
        result = classify_session(
            session_start_date="2025-06-15",
            beads_date="2025-05-01",
            is_beadhub=False,
        )

        assert result == "beads"

    def test_classifies_session_before_any_adoption(self) -> None:
        """classify_session returns 'none' for session before adoption."""
        from agent_taylor.compare import classify_session

        result = classify_session(
            session_start_date="2025-04-15",
            beads_date="2025-05-01",
            is_beadhub=False,
        )

        assert result == "none"

    def test_classifies_session_with_beadhub_repo(self) -> None:
        """classify_session returns 'beads+beadhub' for beadhub repos."""
        from agent_taylor.compare import classify_session

        result = classify_session(
            session_start_date="2025-10-15",
            beads_date="2025-05-01",
            is_beadhub=True,
        )

        assert result == "beads+beadhub"


class TestAggregateByConfiguration:
    """Tests for aggregate_by_configuration function."""

    def test_aggregates_metrics_by_configuration(self) -> None:
        """aggregate_by_configuration sums metrics per configuration."""
        from agent_taylor.compare import aggregate_by_configuration

        session_metrics = [
            {"configuration": "none", "hours": 1.0, "commits": 2, "delta": 100},
            {"configuration": "none", "hours": 0.5, "commits": 1, "delta": 50},
            {"configuration": "beads", "hours": 2.0, "commits": 5, "delta": 300},
        ]

        result = aggregate_by_configuration(session_metrics)

        assert result["none"]["hours"] == 1.5
        assert result["none"]["commits"] == 3
        assert result["none"]["delta"] == 150
        assert result["beads"]["hours"] == 2.0
        assert result["beads"]["commits"] == 5
        assert result["beads"]["delta"] == 300

    def test_computes_rates(self) -> None:
        """aggregate_by_configuration computes delta/hour and commits/hour."""
        from agent_taylor.compare import aggregate_by_configuration

        session_metrics = [
            {"configuration": "beads", "hours": 2.0, "commits": 4, "delta": 200},
        ]

        result = aggregate_by_configuration(session_metrics)

        assert result["beads"]["delta_per_hour"] == 100.0
        assert result["beads"]["commits_per_hour"] == 2.0

    def test_handles_zero_hours(self) -> None:
        """aggregate_by_configuration handles zero hours gracefully."""
        from agent_taylor.compare import aggregate_by_configuration

        session_metrics = [
            {"configuration": "beads", "hours": 0.0, "commits": 0, "delta": 0},
        ]

        result = aggregate_by_configuration(session_metrics)

        assert result["beads"]["delta_per_hour"] == 0.0
        assert result["beads"]["commits_per_hour"] == 0.0

    def test_initializes_all_configurations(self) -> None:
        """aggregate_by_configuration includes all three configurations."""
        from agent_taylor.compare import aggregate_by_configuration

        session_metrics = [
            {"configuration": "beads", "hours": 1.0, "commits": 1, "delta": 100},
        ]

        result = aggregate_by_configuration(session_metrics)

        assert "none" in result
        assert "beads" in result
        assert "beads+beadhub" in result


class TestCompareArgParsing:
    """Tests for compare command argument parsing."""

    def test_requires_author_flag(self) -> None:
        """compare command requires --author flag."""
        from agent_taylor.cli import build_parser

        parser = build_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["compare"])

    def test_accepts_author_flag(self) -> None:
        """compare command accepts --author flag."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["compare", "--author", "Juan"])

        assert ns.author == "Juan"
        assert ns.cmd == "compare"

    def test_accepts_verbose_flag(self) -> None:
        """compare command accepts --verbose flag."""
        from agent_taylor.cli import build_parser

        parser = build_parser()
        ns = parser.parse_args(["compare", "--author", "Juan", "--verbose"])

        assert ns.verbose is True
