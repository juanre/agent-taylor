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


class TestIsBeadhubRepo:
    """Tests for is_beadhub_repo function."""

    def test_returns_true_for_beadhub_prefix(self, tmp_path: Path) -> None:
        """is_beadhub_repo returns True for repos starting with beadhub-."""
        from agent_taylor.config_detection import is_beadhub_repo

        repo = tmp_path / "beadhub-frontend"
        repo.mkdir()

        assert is_beadhub_repo(repo) is True

    def test_returns_false_for_non_beadhub_repo(self, tmp_path: Path) -> None:
        """is_beadhub_repo returns False for repos not starting with beadhub-."""
        from agent_taylor.config_detection import is_beadhub_repo

        repo = tmp_path / "my-project"
        repo.mkdir()

        assert is_beadhub_repo(repo) is False

    def test_returns_true_for_beadhub_exact(self, tmp_path: Path) -> None:
        """is_beadhub_repo returns True for the main 'beadhub' repo."""
        from agent_taylor.config_detection import is_beadhub_repo

        repo = tmp_path / "beadhub"
        repo.mkdir()

        assert is_beadhub_repo(repo) is True

    def test_returns_true_for_beadhub_api(self, tmp_path: Path) -> None:
        """is_beadhub_repo returns True for beadhub-api."""
        from agent_taylor.config_detection import is_beadhub_repo

        repo = tmp_path / "beadhub-api"
        repo.mkdir()

        assert is_beadhub_repo(repo) is True


class TestGetConfiguration:
    """Tests for get_configuration function."""

    def test_returns_none_when_no_beads(self) -> None:
        """get_configuration returns 'none' when beads not adopted."""
        from agent_taylor.config_detection import get_configuration

        result = get_configuration(
            beads_date=None,
            is_beadhub=False,
            check_date="2025-06-15",
        )

        assert result == "none"

    def test_returns_none_before_beads_adoption(self) -> None:
        """get_configuration returns 'none' before beads was adopted."""
        from agent_taylor.config_detection import get_configuration

        result = get_configuration(
            beads_date="2025-06-01",
            is_beadhub=False,
            check_date="2025-05-15",
        )

        assert result == "none"

    def test_returns_beads_after_beads_adoption(self) -> None:
        """get_configuration returns 'beads' after beads was adopted."""
        from agent_taylor.config_detection import get_configuration

        result = get_configuration(
            beads_date="2025-06-01",
            is_beadhub=False,
            check_date="2025-06-15",
        )

        assert result == "beads"

    def test_returns_beads_on_adoption_date(self) -> None:
        """get_configuration returns 'beads' on the adoption date itself."""
        from agent_taylor.config_detection import get_configuration

        result = get_configuration(
            beads_date="2025-06-01",
            is_beadhub=False,
            check_date="2025-06-01",
        )

        assert result == "beads"

    def test_returns_beads_beadhub_for_beadhub_repo(self) -> None:
        """get_configuration returns 'beads+beadhub' for beadhub repos."""
        from agent_taylor.config_detection import get_configuration

        result = get_configuration(
            beads_date="2025-06-01",
            is_beadhub=True,
            check_date="2025-07-15",
        )

        assert result == "beads+beadhub"

    def test_returns_none_for_beadhub_repo_before_beads(self) -> None:
        """get_configuration returns 'none' for beadhub repo before beads adoption."""
        from agent_taylor.config_detection import get_configuration

        # Even if it's a beadhub repo, before beads adoption it's "none"
        result = get_configuration(
            beads_date="2025-06-01",
            is_beadhub=True,
            check_date="2025-05-15",
        )

        assert result == "none"
