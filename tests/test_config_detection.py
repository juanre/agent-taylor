# ABOUTME: Tests for configuration detection (beads/beadhub adoption dates).
# ABOUTME: Tests git-based and repo name-based detection.

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


class TestDetectBeadsDate:
    """Tests for detect_beads_date function."""

    def test_returns_none_when_no_beads_dir(self, git_repo: Path) -> None:
        """detect_beads_date returns None when .beads/ was never committed."""
        from agent_taylor.config_detection import detect_beads_date

        result = detect_beads_date(git_repo)

        assert result is None

    def test_returns_date_when_beads_committed(self, git_repo: Path) -> None:
        """detect_beads_date returns the date .beads/ was first committed."""
        from agent_taylor.config_detection import detect_beads_date

        # Create and commit .beads directory
        beads_dir = git_repo / ".beads"
        beads_dir.mkdir()
        (beads_dir / "beads.db").write_text("dummy")
        subprocess.run(
            ["git", "add", ".beads"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add beads"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

        result = detect_beads_date(git_repo)

        assert result is not None
        # Should be today's date in YYYY-MM-DD format
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        assert result == today

    def test_returns_none_for_non_git_directory(self, non_git_dir: Path) -> None:
        """detect_beads_date returns None for non-git directory."""
        from agent_taylor.config_detection import detect_beads_date

        result = detect_beads_date(non_git_dir)

        assert result is None


class TestDetectBeadhubDate:
    """Tests for detect_beadhub_date function."""

    def test_returns_none_for_non_beadhub_repo(self, tmp_path: Path) -> None:
        """detect_beadhub_date returns None for repos without .beadhub file."""
        from agent_taylor.config_detection import detect_beadhub_date

        repo = tmp_path / "my-project"
        repo.mkdir()

        assert detect_beadhub_date(repo) is None

    def test_returns_start_date_for_main_beadhub(self, tmp_path: Path) -> None:
        """detect_beadhub_date returns BEADHUB_START_DATE for main beadhub repo."""
        from agent_taylor.config_detection import detect_beadhub_date, BEADHUB_START_DATE

        repo = tmp_path / "beadhub"
        repo.mkdir()

        assert detect_beadhub_date(repo) == BEADHUB_START_DATE

    def test_returns_none_for_beadhub_prefix_without_file(self, tmp_path: Path) -> None:
        """detect_beadhub_date returns None for beadhub-* repos without .beadhub file."""
        from agent_taylor.config_detection import detect_beadhub_date

        repo = tmp_path / "beadhub-cloud"
        repo.mkdir()

        assert detect_beadhub_date(repo) is None

    def test_returns_adoption_date_for_repo_with_beadhub_file(self, tmp_path: Path) -> None:
        """detect_beadhub_date returns delayed adoption date for repos with .beadhub file."""
        from agent_taylor.config_detection import detect_beadhub_date

        repo = tmp_path / "my-project"
        repo.mkdir()
        (repo / ".beadhub").write_text("")  # Create .beadhub file

        result = detect_beadhub_date(repo)
        # Should be 2 weeks after BEADHUB_START_DATE (2025-11-30 + 14 days = 2025-12-14)
        assert result == "2025-12-14"

    def test_ignores_beadhub_directory(self, tmp_path: Path) -> None:
        """detect_beadhub_date ignores .beadhub directory (only checks file)."""
        from agent_taylor.config_detection import detect_beadhub_date

        repo = tmp_path / "my-project"
        repo.mkdir()
        (repo / ".beadhub").mkdir()  # Create .beadhub directory, not file

        assert detect_beadhub_date(repo) is None


class TestGetConfiguration:
    """Tests for get_configuration function."""

    def test_returns_none_when_no_beads(self) -> None:
        """get_configuration returns 'none' when beads not adopted."""
        from agent_taylor.config_detection import get_configuration

        result = get_configuration(
            beads_date=None,
            beadhub_date=None,
            check_date="2025-06-15",
        )

        assert result == "none"

    def test_returns_none_before_beads_adoption(self) -> None:
        """get_configuration returns 'none' before beads was adopted."""
        from agent_taylor.config_detection import get_configuration

        result = get_configuration(
            beads_date="2025-06-01",
            beadhub_date=None,
            check_date="2025-05-15",
        )

        assert result == "none"

    def test_returns_beads_after_beads_adoption(self) -> None:
        """get_configuration returns 'beads' after beads was adopted."""
        from agent_taylor.config_detection import get_configuration

        result = get_configuration(
            beads_date="2025-06-01",
            beadhub_date=None,
            check_date="2025-06-15",
        )

        assert result == "beads"

    def test_returns_beads_on_adoption_date(self) -> None:
        """get_configuration returns 'beads' on the adoption date itself."""
        from agent_taylor.config_detection import get_configuration

        result = get_configuration(
            beads_date="2025-06-01",
            beadhub_date=None,
            check_date="2025-06-01",
        )

        assert result == "beads"

    def test_returns_beads_beadhub_after_beadhub_adoption(self) -> None:
        """get_configuration returns 'beads+beadhub' after beadhub adoption date."""
        from agent_taylor.config_detection import get_configuration

        result = get_configuration(
            beads_date="2025-06-01",
            beadhub_date="2025-07-01",
            check_date="2025-07-15",
        )

        assert result == "beads+beadhub"

    def test_returns_beads_before_beadhub_adoption(self) -> None:
        """get_configuration returns 'beads' before beadhub adoption date."""
        from agent_taylor.config_detection import get_configuration

        result = get_configuration(
            beads_date="2025-06-01",
            beadhub_date="2025-07-01",
            check_date="2025-06-15",
        )

        assert result == "beads"

    def test_returns_none_before_beads_even_with_beadhub(self) -> None:
        """get_configuration returns 'none' before beads even if beadhub is set."""
        from agent_taylor.config_detection import get_configuration

        result = get_configuration(
            beads_date="2025-06-01",
            beadhub_date="2025-07-01",
            check_date="2025-05-15",
        )

        assert result == "none"
